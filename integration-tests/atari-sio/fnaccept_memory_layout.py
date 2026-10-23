#!/usr/bin/env python3
"""Map and runtime safety checks for the public Atari acceptance XEX."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAIN_START = 0x0D00
# The deterministic Atari profile reports MEMTOP=$9C1F.  The linked image
# must stay below its 2 KiB cc65 C-stack floor, not merely below the linker
# configuration's theoretical $B420 ceiling.
MAIN_LIMIT = 0x941F
C_STACK_BYTES = 0x0800
RESULT = (0x0B00, 0x0B80)
DISK_WRITE = (0x0B80, 0x0C00)
DISK_READ = (0x0C00, 0x0C80)
DISPLAY_LIST_BYTES = 32
TEXT_SCREEN_BYTES = 40 * 24
SEGMENT_RE = re.compile(r"^(\S+)\s+([0-9A-F]{6})\s+([0-9A-F]{6})\s+([0-9A-F]{6})\s+", re.M)


def _intervals_overlap(left, right):
    return left[0] < right[1] and right[0] < left[1]


def parse_map(path):
    """Read the cc65 Segment list, returning half-open address ranges."""
    text = Path(path).read_text()
    try:
        section = text.split("Segment list:", 1)[1].split("Exports list:", 1)[0]
    except IndexError as exc:
        raise RuntimeError(f"{path} has no cc65 Segment list") from exc
    segments = {}
    for name, start, end, size in SEGMENT_RE.findall(section):
        start_i, end_i, size_i = int(start, 16), int(end, 16), int(size, 16)
        if end_i - start_i + 1 != size_i:
            raise RuntimeError(f"{path} has inconsistent {name} segment")
        segments[name] = (start_i, end_i + 1)
    return segments


def layout_report(map_path, xex_path):
    segments = parse_map(map_path)
    required = ("ZEROPAGE", "STARTUP", "CODE", "RODATA", "DATA", "BSS")
    missing = [name for name in required if name not in segments]
    if missing:
        raise RuntimeError(f"missing required fnaccept segments: {missing}")
    loaded_end = segments["DATA"][1]
    bss_end = segments["BSS"][1]
    report = {
        "segments": {name: {"start": start, "end_exclusive": end, "size": end - start}
                     for name, (start, end) in segments.items()},
        "optional_segments": {name: {"present": name in segments,
                                      "size": segments.get(name, (0, 0))[1] - segments.get(name, (0, 0))[0]}
                              for name in ("LOWBSS", "LOWCODE", "INIT", "EXTZP")},
        "xex_bytes": Path(xex_path).stat().st_size,
        "loaded_span_bytes": loaded_end - MAIN_START,
        "bss_bytes": segments["BSS"][1] - segments["BSS"][0],
        "main_footprint_bytes": bss_end - MAIN_START,
        "c_stack_reserved": {"start": MAIN_LIMIT, "end_exclusive": 0x9C1F,
                               "bytes": C_STACK_BYTES},
        "heap_gap": {"start": bss_end, "end_exclusive": MAIN_LIMIT,
                     "bytes": MAIN_LIMIT - bss_end},
        "fixed_application_regions": {
            "result": {"start": RESULT[0], "end_exclusive": RESULT[1]},
            "disk_write": {"start": DISK_WRITE[0], "end_exclusive": DISK_WRITE[1]},
            "disk_read": {"start": DISK_READ[0], "end_exclusive": DISK_READ[1]},
        },
    }
    return report


def validate_link_layout(map_path, xex_path):
    report = layout_report(map_path, xex_path)
    segments = {name: (entry["start"], entry["end_exclusive"])
                for name, entry in report["segments"].items()}
    if segments["STARTUP"][0] != MAIN_START:
        raise RuntimeError(f"fnaccept start {segments['STARTUP'][0]:#06x} is not {MAIN_START:#06x}")
    if segments["ZEROPAGE"][0] < 0x82 or segments["ZEROPAGE"][1] > 0x100:
        raise RuntimeError(f"fnaccept zero page escapes cc65 allocation: {segments['ZEROPAGE']}")
    if segments["BSS"][1] > MAIN_LIMIT:
        raise RuntimeError(f"fnaccept BSS enters reserved C stack: {segments['BSS']}")
    for name, interval in report["fixed_application_regions"].items():
        if interval["end_exclusive"] > MAIN_START:
            raise RuntimeError(f"{name} is not below the linked XEX image: {interval}")
    # The public acceptance guest and its selected archive members do not use
    # malloc; retain a bounded guard gap rather than promising a general heap.
    if report["heap_gap"]["bytes"] < 0x0200:
        raise RuntimeError(f"fnaccept leaves too little heap headroom: {report['heap_gap']}")
    return report


def validate_runtime_snapshot(snapshot, report):
    """Validate memory recorded by the pre-BSS assembly gate."""
    if snapshot.get("magic") != "HMS1" or snapshot.get("version") != 1:
        raise RuntimeError(f"missing pre-BSS memory snapshot: {snapshot}")
    if snapshot.get("dma_transition") != 0:
        raise RuntimeError(f"unexpected display-DMA transition in safe layout: {snapshot}")
    if not snapshot.get("sdmctl") or not snapshot.get("dmactl"):
        raise RuntimeError(f"snapshot was not captured with active display DMA: {snapshot}")
    if snapshot["memlo"] > RESULT[0]:
        raise RuntimeError(f"result block lies below guest MEMLO: {snapshot}")
    if snapshot["memtop"] < MAIN_LIMIT + C_STACK_BYTES:
        raise RuntimeError(f"guest MEMTOP cannot support configured stack: {snapshot}")
    if report["segments"]["BSS"]["end_exclusive"] > snapshot["memtop"] - C_STACK_BYTES:
        raise RuntimeError(f"linked BSS enters runtime C stack: {snapshot}, {report}")
    display = (snapshot["sdlstl"], snapshot["sdlstl"] + DISPLAY_LIST_BYTES)
    screen = (snapshot["savmsc"], snapshot["savmsc"] + TEXT_SCREEN_BYTES)
    image = (MAIN_START, report["segments"]["BSS"]["end_exclusive"])
    if _intervals_overlap(display, image) or _intervals_overlap(screen, image):
        raise RuntimeError(f"linked image overlaps live display memory: {snapshot}, {report}")
    return {
        "pre_service_display": {"display_list": display, "screen": screen,
                                "overlaps_linked_image": False},
        "runtime_stack": {"top": snapshot["memtop"],
                          "floor": snapshot["memtop"] - C_STACK_BYTES,
                          "bytes": C_STACK_BYTES},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--xex", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_link_layout(args.map, args.xex), indent=2))


if __name__ == "__main__":
    main()
