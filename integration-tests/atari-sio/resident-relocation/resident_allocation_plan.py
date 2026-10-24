#!/usr/bin/env python3
"""Pure arithmetic gate for the proposed dynamic-resident staging contract.

This is not the installer.  It keeps its allocation invariants executable
until a real o65 arena loader replaces the fixed-image scaffold.
"""
from __future__ import annotations

import argparse

RESULT_END = 0x0B28              # current 40-byte result at $0B00
BOOTSTRAP = 0x5600               # fixed transient code, below staged input
STAGE = 0x5800                   # o65 initialized bytes
STACK_FLOOR = 0x941F             # observed Graphics-0 cc65 runtime floor


def align2(value: int) -> int:
    return (value + 1) & ~1


def plan(memlo: int, module_size: int, initialized_size: int,
         result_end: int = RESULT_END, bootstrap: int = BOOTSTRAP,
         stage: int = STAGE, stack_floor: int = STACK_FLOOR) -> tuple[int, int, int]:
    base = align2(max(memlo, result_end))
    end = base + module_size
    stage_end = stage + initialized_size
    if end > bootstrap:
        raise ValueError("resident target would overwrite transient bootstrap")
    if stage_end > stack_floor:
        raise ValueError("staged initialized image reaches cc65 stack reserve")
    return base, end, stage_end


def self_test() -> None:
    # Current real o65 public API closure: 12,054 total / 10,007 loaded.
    assert plan(0x0700, 12054, 10007) == (0x0B28, 0x3A3E, 0x7F17)
    # Boundary checks are intentionally one byte past each protected region.
    try:
        plan(0x0700, BOOTSTRAP - 0x0B28 + 1, 10007)
    except ValueError as exc:
        assert "bootstrap" in str(exc)
    else:
        raise AssertionError("target/bootstrap overlap was accepted")
    try:
        plan(0x0700, 12054, STACK_FLOOR - STAGE + 1)
    except ValueError as exc:
        assert "stack" in str(exc)
    else:
        raise AssertionError("staging/stack overlap was accepted")
    print("allocation plan: base=$0b28 end=$3a3e stage_end=$7f17; boundary rejections verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--memlo", type=lambda text: int(text, 0))
    parser.add_argument("--module-size", type=lambda text: int(text, 0))
    parser.add_argument("--initialized-size", type=lambda text: int(text, 0))
    parser.add_argument("--result-end", type=lambda text: int(text, 0), default=RESULT_END)
    parser.add_argument("--bootstrap", type=lambda text: int(text, 0), default=BOOTSTRAP)
    parser.add_argument("--stage", type=lambda text: int(text, 0), default=STAGE)
    parser.add_argument("--stack-floor", type=lambda text: int(text, 0), default=STACK_FLOOR)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif None not in (args.memlo, args.module_size, args.initialized_size):
        base, end, stage_end = plan(args.memlo, args.module_size, args.initialized_size,
                                    args.result_end, args.bootstrap, args.stage,
                                    args.stack_floor)
        print(f"allocation plan: base=${base:04x} end=${end:04x} stage_end=${stage_end:04x}")
    elif any(value is not None for value in (args.memlo, args.module_size, args.initialized_size)):
        parser.error("--memlo, --module-size, and --initialized-size must be supplied together")
