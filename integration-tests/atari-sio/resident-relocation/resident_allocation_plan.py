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


def plan(memlo: int, module_size: int, initialized_size: int) -> tuple[int, int, int]:
    base = align2(max(memlo, RESULT_END))
    end = base + module_size
    stage_end = STAGE + initialized_size
    if end > BOOTSTRAP:
        raise ValueError("resident target would overwrite transient bootstrap")
    if stage_end > STACK_FLOOR:
        raise ValueError("staged initialized image reaches cc65 stack reserve")
    return base, end, stage_end


def self_test() -> None:
    # Current measured full public API closure: 12,194 total / 10,160 loaded.
    assert plan(0x0700, 12194, 10160) == (0x0B28, 0x3ACA, 0x7FB0)
    # Boundary checks are intentionally one byte past each protected region.
    try:
        plan(0x0700, BOOTSTRAP - 0x0B28 + 1, 10160)
    except ValueError as exc:
        assert "bootstrap" in str(exc)
    else:
        raise AssertionError("target/bootstrap overlap was accepted")
    try:
        plan(0x0700, 12194, STACK_FLOOR - STAGE + 1)
    except ValueError as exc:
        assert "stack" in str(exc)
    else:
        raise AssertionError("staging/stack overlap was accepted")
    print("allocation plan: base=$0b28 end=$3aca stage_end=$7fb0; boundary rejections verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
