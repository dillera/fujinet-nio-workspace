---
title: 'Harden Atari Disk SIO Story 1.1 fixtures'
type: 'feature'
created: '2026-10-20'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'd631605c639493dfd22dd8b5b607d7308c0dac5b'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-1-1-freeze-atr-disk-conformance-fixtures.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 1.1 fixtures establish protocol shape, but several vectors do not independently prove their source data, state transitions, or command grammar.

**Approach:** Harden only the workspace fixture matrix, virtual projection, and stdlib validator with reproducible ATR goldens, nonzero write/readback evidence, explicit transition chains, and command-specific protocol checks.

## Boundaries & Constraints

**Always:** Preserve the approved v1 commands, STATUS mapping, geometries, exclusions, and virtual-only scope. Use `repos/nio-core-apps/build/atari/disk/boot/autorun.atr` only as a source-image golden: record SHA-256 and literal sectors 1–4 independently extracted from the ATR payload. Require structured, reproducible preconditions and observable effects in each projection. Validate phases from the command contract, not merely manifest agreement.

**Ask First:** A changed source-image hash, a new command/geometry/status policy, production-repository code, boot/emulator integration, or any change to the existing architectural boundaries.

**Never:** Start Story 1.2; modify `repos/fujinet-nio`, `repos/nio-core-apps`, Amiga artifacts, or the Atari physical/SIO architecture; infer golden bytes through production adapters.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| Config boot goldens | Pinned classic-256 `autorun.atr` sectors 1–4 | Literal extracted bytes, checksum, hash, and offset prove the boot READ vectors | Hash mismatch is validator failure, not boot integration |
| Successful write | Writable classic-256 sector 4 with nonzero initial bytes | PUT/WRITE data acknowledgement, final image, and successor READ prove the 256-byte boundary | Rejected/bad data retains declared initial image; verify failure may retain postimage |
| Error clearing | Invalid sector → two STATUS reads → valid READ → STATUS | One contiguous same-slot chain proves error retention then clearing | Broken order, slot/device change, or status mismatch fails |
| Deferred mount | Pending slot or rejected write | Projection names mount/action preconditions and declared side effects | STATUS remains non-mounting and rejection is non-mutating |

</frozen-after-approval>

## Code Map

- `integration-tests/atari-sio/fixtures/disk_v1.json` -- authoritative literals; add source-image metadata, structured state, and successor evidence.
- `integration-tests/atari-sio/fixtures/disk_v1.manifest.json` -- virtual adapter projection; expose reproducible preconditions and effects.
- `integration-tests/atari-sio/tests/test_disk_v1_fixtures.py` -- stdlib validator; derive grammar, verify goldens, chains, and side effects.
- `repos/nio-core-apps/build/atari/disk/boot/autorun.atr` -- read-only source golden, SHA-256 `a4bec3fa87bb0355815d66bb28356222bf0001e4212441e7b5b2eb128a986a20`.

## Tasks & Acceptance

**Execution:**
- [x] `integration-tests/atari-sio/fixtures/disk_v1.json` -- replace config synthetic sectors with pinned image goldens; add a nonzero classic-256 successful write and explicit transition/state fields.
- [x] `integration-tests/atari-sio/fixtures/disk_v1.manifest.json` -- project structured preconditions and observable effects for all scenarios.
- [x] `integration-tests/atari-sio/tests/test_disk_v1_fixtures.py` -- independently validate source bytes/hash, command grammars, chains, mutation/readback, and projection metadata.
- [x] `integration-tests/atari-sio/README.md` -- distinguish pinned boot goldens from synthetic framing vectors and document the extraction recipe.

**Acceptance Criteria:**
- Given the recorded source hash and ATR offsets, when the validator runs, then it verifies sectors 1–4 are literal nonzero `autorun.atr` goldens without invoking production code.
- Given a successful nonzero sector-4 write, when its successor READ runs, then acknowledged data, final image, 256-byte size, checksum, and readback agree.
- Given any fixture command, when its phase list is validated, then it exactly satisfies that command’s normative v1 grammar.
- Given the invalid-sector chain, when the validator runs, then it requires contiguous same-slot predecessors through retained and cleared STATUS observations.
- Given a virtual projection, when consumed by an adapter, then its mount, mutation, and outcome conditions are structured and reproducible.

## Design Notes

The ATR is an immutable test input, not an integration dependency. Golden extraction uses the ATR’s 16-byte header: classic-256 sectors 1–3 are 128 bytes at offsets 16, 144, and 272; sector 4 is 256 bytes at offset 400. The existing fixture test remains the complete, cheapest verification gate.

## Verification

**Commands:**
- `source "$NIO_WORKSPACE/scripts/env.sh" && python3 -m unittest discover -s integration-tests/atari-sio/tests -v` -- expected: all hardened fixture checks pass.
- `sha256sum repos/nio-core-apps/build/atari/disk/boot/autorun.atr` -- expected: recorded source-image hash.
