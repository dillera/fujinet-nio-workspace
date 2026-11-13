#!/usr/bin/env python3
"""C64 boot acceptance over IEC: a stock KERNAL in VICE against fujinet-nio.

The whole path a person takes: list the boot disk, load and run the config app, run the
demo from it, add a TNFS host, browse it, assign a disk image and a loose program, boot,
and load a program from each. TNFS is the daemon image the firmware's own test services
use. Evidence (each screen, the firmware log) goes to test-evidence/c64-iec/<time>/.

What this cannot show: the bus runs through VICE's KERNAL traps and NetIEC, so it says
nothing about line timing on real hardware. See README.md beside this file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "tools"))

from c64_emulator.basic import basic_hello  # noqa: E402
from c64_emulator.vice import KEY_DOWN, KEY_F1, KEY_F5, KEY_RETURN, Vice, ViceConfig  # noqa: E402

# The image repos/fujinet-nio/scripts/start_test_services.sh uses. It has only a latest
# tag, so this pins the image that tag pointed at on 2026-11-07.
TNFS_IMAGE = "zaqu/tnfsd@sha256:1dd216bcf120deb269feb83feddc6d1e7f7897c02469aaa195c5146a587fcdb0"
TNFS_CONTAINER = "fujinet-tnfs-c64-acceptance"
TNFS_PORT = 16384
NETIEC_PORT = 1541
CREATE_D64 = WORKSPACE / "repos" / "nio-core-apps" / "boot-disk" / "scripts" / "create_d64.py"
README = "integration-tests/c64-iec/README.md"


class Evidence:
    """Each named moment: the screen's text, and a picture of it for a person."""

    def __init__(self, root: Path, vice: Vice) -> None:
        self.root = root
        self.vice = vice
        self.index = 0
        root.mkdir(parents=True, exist_ok=True)

    def screen(self, name: str, text: str) -> None:
        self.index += 1
        (self.root / f"{self.index:02d}-{name}.txt").write_text(text + "\n", encoding="latin-1")
        try:
            self.vice.screenshot(self.root / f"{self.index:02d}-{name}.png")
        except RuntimeError as error:  # a picture is a convenience: the text is the record
            print(f"   no screenshot: {error}")


def step(message: str) -> None:
    print(f"== {message}", flush=True)


def expect(text: str, *fragments: str) -> None:
    lowered = text.lower()
    for fragment in fragments:
        if fragment.lower() not in lowered:
            raise AssertionError(f"expected {fragment!r} on the screen:\n{text}")


def prepare_tnfs_root(root: Path) -> None:
    source = root.parent / "tnfs-source"
    source.mkdir(parents=True, exist_ok=True)
    (source / "HELLO.prg").write_bytes(basic_hello("HELLO FROM TNFS"))
    (root / "games").mkdir(parents=True, exist_ok=True)
    (root / "readme.txt").write_text("not a disk image\n")
    (root / "games" / "loose.prg").write_bytes(basic_hello("HELLO FROM A LOOSE PRG"))
    subprocess.run(
        [sys.executable, str(CREATE_D64), "-i", str(source), "-o", str(root / "games" / "hello.d64"),
         "-t", "TNFS DISK", "--id", "TN"],
        check=True, stdout=subprocess.DEVNULL,
    )


def start_tnfs(root: Path) -> None:
    subprocess.run(["docker", "rm", "-f", TNFS_CONTAINER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", TNFS_CONTAINER,
         "--user", f"{os.getuid()}:{os.getgid()}",
         "-p", f"127.0.0.1:{TNFS_PORT}:{TNFS_PORT}/udp",
         "-p", f"127.0.0.1:{TNFS_PORT}:{TNFS_PORT}/tcp",
         "-v", f"{root}:/data", TNFS_IMAGE],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def stop_tnfs(log_path: Path) -> None:
    with log_path.open("wb") as log:
        subprocess.run(["docker", "logs", TNFS_CONTAINER], stdout=log, stderr=subprocess.STDOUT)
    subprocess.run(["docker", "rm", "-f", TNFS_CONTAINER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_firmware(binary: Path, run_dir: Path, boot_disk: Path, log_path: Path, netiec_port: int) -> subprocess.Popen:
    target = run_dir / "fujinet-data" / "boot" / "c64"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(boot_disk, target / "autorun.d64")
    (run_dir / "fujinet-data" / "fujinet.yaml").write_text(f"channel:\n  tcp_port: {netiec_port}\n")
    with log_path.open("wb") as log:  # the firmware keeps its own copy of the file
        # stdin stays open: the firmware's console treats EOF as a request to quit.
        return subprocess.Popen([str(binary.resolve())], cwd=run_dir, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)


def wait_for_netiec(port: int, firmware: subprocess.Popen, log_path: Path, timeout: float = 15.0) -> None:
    """Until the firmware takes connections for VICE's bridge."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if firmware.poll() is not None:
            raise RuntimeError(f"firmware exited at once; see {log_path}")
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"firmware is not listening on port {port}; see {log_path}")


def start_config_app(vice: Vice, load_timeout: float) -> str:
    started = time.monotonic()
    vice.type_text('load"*",8,1\n')
    vice.wait_for(r"searching for \*\s*\nloading\s*\nready\.", timeout=load_timeout)
    print(f"   loaded in {time.monotonic() - started:.1f} s")
    vice.type_text("run\n")
    vice.wait_for(r"FujiNet NIO Config", timeout=30)
    text = vice.wait_for(r"Ready", timeout=30)
    expect(text, "Hosts", "Browse", "Drives", "Setup", "F1 Boot")
    return text


def run_scenario(vice: Vice, evidence: Evidence, load_timeout: float) -> None:
    step("C64 starts at the BASIC prompt")
    text = vice.wait_for(r"ready\.", timeout=20)
    evidence.screen("power-on", text)

    step('LOAD"$",8 and LIST show the boot disk')
    vice.type_text('load"$",8\n')
    vice.wait_for(r"loading\s*\nready\.", timeout=20)
    vice.type_text("list\n")
    text = vice.wait_for(r"blocks free", timeout=10)
    evidence.screen("boot-disk-directory", text)
    expect(text, '"fujinet nio', 'fn 2a', '"config"', '"fujidemo"', "prg")

    step("A file that is not there is FILE NOT FOUND, and the status channel says why")
    vice.type_text('load"nope",8\n')
    text = vice.wait_for(r"file not found", timeout=15)
    evidence.screen("file-not-found", text)
    # INPUT# is not allowed in direct mode, so this needs a program.
    vice.type_text("new\n10 open15,8,15:input#15,a,b$,c,d:close15:print a;b$\nrun\n")
    text = vice.wait_for(r"62 *file not found", timeout=15)
    evidence.screen("status-channel", text)

    step('LOAD"*",8,1 and RUN start the config app')
    evidence.screen("config-hosts", start_config_app(vice, load_timeout))

    step("F5 runs the demo, which reads the date and time over the NIO channel")
    vice.press(bytes([KEY_F5]))
    vice.wait_for(r"f u j i n e t   n i o", timeout=30)
    text = vice.wait_for(r"fujinet online", timeout=15)
    evidence.screen("demo", text)
    expect(text, str(time.localtime().tm_year))

    step("Reset, and the boot disk still starts the config app")
    vice.reset()
    vice.wait_for(r"(?s)commodore 64 basic v2.*ready\.", timeout=20)
    start_config_app(vice, load_timeout)

    step("Add the TNFS host")
    vice.type_text("a")
    vice.wait_for(r"New host or URI", timeout=10)
    # Over TCP: Docker Desktop's published UDP ports do not reach the daemon on macOS.
    vice.type_text(f"tnfs+tcp://127.0.0.1:{TNFS_PORT}/\n")
    text = vice.wait_for(rf"127\.0\.0\.1:{TNFS_PORT}", timeout=10)
    evidence.screen("config-host-added", text)

    step("Browse it")
    # The new host is last, and the selection stays on the first: go down to it.
    rows = [row for row in text.split("\n") if row[:3].strip().isdigit()]
    index = next(i for i, row in enumerate(rows) if "127.0.0.1" in row)
    vice.press(bytes([KEY_DOWN]) * index)
    vice.press(bytes([KEY_RETURN]))
    text = vice.wait_for(r"games +<DIR>", timeout=30)
    evidence.screen("config-browse-root", text)
    expect(text, "readme.txt")

    step("Open the folder and assign the disk image")
    # Folders sort first, and the cursor starts on the first row.
    vice.press(bytes([KEY_RETURN]))
    text = vice.wait_for(r"hello\.d64", timeout=30)
    evidence.screen("config-browse-games", text)
    vice.press(bytes([KEY_RETURN]))
    text = vice.wait_for(r"Press 1-8", timeout=20)
    evidence.screen("config-assign-dialog", text)
    vice.type_text("1")
    text = vice.wait_for(r"D1 <- hello\.d64", timeout=20)
    evidence.screen("config-assigned", text)

    step("Assign the loose program too: it sorts next")
    vice.press(bytes([KEY_DOWN]))
    vice.press(bytes([KEY_RETURN]))
    vice.wait_for(r"Press 1-8", timeout=20)
    vice.type_text("2")
    text = vice.wait_for(r"D2 <- loose\.prg", timeout=20)
    evidence.screen("config-assigned-prg", text)

    step("Boot: F1 mounts it from TNFS and restarts the machine")
    vice.press(bytes([KEY_F1]))
    text = vice.wait_for(r"(?s)commodore 64 basic v2.*ready\.", timeout=60)
    evidence.screen("rebooted", text)

    step("The disk from TNFS is now drive 8")
    vice.type_text('load"$",8\n')
    vice.wait_for(r"loading\s*\nready\.", timeout=30)
    vice.type_text("list\n")
    text = vice.wait_for(r"blocks free", timeout=10)
    evidence.screen("tnfs-disk-directory", text)
    expect(text, '"tnfs disk', 'tn 2a', '"hello"')

    step("A program from it loads and runs")
    vice.type_text('load"hello",8\n')
    vice.wait_for(r"searching for hello\s*\nloading\s*\nready\.", timeout=30)
    vice.type_text("run\n")
    text = vice.wait_for(r"hello from tnfs", timeout=15)
    evidence.screen("program-from-tnfs", text)

    step("The loose program is drive 9: a one-file disk, named after its file")
    vice.type_text("?chr$(147)\n")  # clears the screen, so the waits below see only this drive
    vice.type_text('load"$",9\n')
    vice.wait_for(r"searching for \$\s*\nloading\s*\nready\.", timeout=30)
    vice.type_text("list\n")
    text = vice.wait_for(r"blocks free", timeout=10)
    evidence.screen("loose-prg-directory", text)
    expect(text, '"loose', 'fn 2a', "prg")

    vice.type_text('load"*",9\n')
    vice.wait_for(r"searching for \*\s*\nloading\s*\nready\.", timeout=30)
    vice.type_text("run\n")
    text = vice.wait_for(r"hello from a loose prg", timeout=15)
    evidence.screen("program-from-loose-prg", text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path,
                        default=WORKSPACE / "repos" / "fujinet-nio" / "build" / "c64-netiec-debug" / "fujinet-nio")
    parser.add_argument("--boot-disk", type=Path,
                        default=WORKSPACE / "repos" / "nio-core-apps" / "build" / "c64" / "disk" / "boot" / "autorun.d64")
    parser.add_argument("--vice-root", type=Path,
                        default=os.environ.get("VICE_FN_ROOT") or WORKSPACE / "external" / "vice-fn",
                        help="the vice-fn checkout (default: $VICE_FN_ROOT, else external/vice-fn)")
    parser.add_argument("--vice-build", type=Path,
                        default=os.environ.get("VICE_FN_BUILD") or WORKSPACE / "build" / "vice-fn",
                        help="its builds, from scripts/build-vice-fn.sh (default: $VICE_FN_BUILD, else build/vice-fn)")
    parser.add_argument("--window", action="store_true", help="use the windowed VICE build")
    parser.add_argument("--load-timeout", type=float, default=120.0, help="seconds to allow for loading the config app")
    parser.add_argument("--netiec-port", type=int, default=NETIEC_PORT, help="for the firmware and VICE's bridge")
    parser.add_argument("--monitor-port", type=int, default=6502, help="VICE's binary monitor")
    args = parser.parse_args()

    vice_config = ViceConfig(root=Path(args.vice_root), build=Path(args.vice_build), units=(8, 9, 30),
                             headless=not args.window,
                             netiec_port=args.netiec_port, monitor_port=args.monitor_port)
    for path, what in ((args.firmware, "firmware (scripts/build.sh c64)"),
                       (args.boot_disk, "boot disk (scripts/build.sh c64)"),
                       (vice_config.launcher,
                        f"the vice-fn checkout (git submodule update --init external/vice-fn; see {README})"),
                       (vice_config.build_dir / "src" / "x64sc",
                        f"this VICE build (scripts/build-vice-fn.sh {vice_config.build_dir.name}; see {README})")):
        if not path.exists():
            print(f"missing {what}: {path}", file=sys.stderr)
            return 2
    if shutil.which("docker") is None:
        print("docker is required for the TNFS daemon", file=sys.stderr)
        return 2

    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    evidence_root = WORKSPACE / "test-evidence" / "c64-iec"
    evidence_root.mkdir(parents=True, exist_ok=True)
    for again in range(1, 100):  # a run that started in the same second has the first name
        evidence_dir = evidence_root / (stamp if again == 1 else f"{stamp}-{again}")
        try:
            evidence_dir.mkdir()
            break
        except FileExistsError:
            continue
    run_dir = evidence_dir / "run"
    run_dir.mkdir()

    tnfs_root = evidence_dir / "tnfs"
    prepare_tnfs_root(tnfs_root)

    firmware_log = evidence_dir / "firmware.log"
    firmware: subprocess.Popen | None = None
    vice = Vice(vice_config, evidence_dir / "vice.log")
    evidence = Evidence(evidence_dir, vice)
    result = 1
    try:
        start_tnfs(tnfs_root)
        firmware = start_firmware(args.firmware, run_dir, args.boot_disk, firmware_log, args.netiec_port)
        wait_for_netiec(args.netiec_port, firmware, firmware_log)
        vice.start()
        run_scenario(vice, evidence, args.load_timeout)
        result = 0
        print(f"PASS  evidence: {evidence_dir}")
    except (AssertionError, TimeoutError, RuntimeError, StopIteration, OSError,
            subprocess.CalledProcessError) as error:
        print(f"FAIL  {error}\nevidence: {evidence_dir}", file=sys.stderr)
        if vice.sock is not None:
            try:
                evidence.screen("at-failure", vice.screen_text())
            except (OSError, RuntimeError, TimeoutError):
                pass
    finally:
        vice.stop()
        if firmware is not None:
            firmware.terminate()
            try:
                firmware.wait(timeout=5)
            except subprocess.TimeoutExpired:
                firmware.kill()
        stop_tnfs(evidence_dir / "tnfs.log")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
