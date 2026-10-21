---
title: 'Serve standard Atari ATR drives through DiskService'
type: 'feature'
created: '2026-10-20'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'f234f30147ed1a6a2550203dd28afbf68be21491'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/SPEC.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-epic-1-context.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-1-1-freeze-atr-disk-conformance-fixtures.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-1-1-fixture-hardening.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The current Atari SIO profile is a single `Channel` carrying legacy FujiBus/SLIP traffic; it cannot own standard disk transactions or share the physical bus safely with a future native `0x7F` endpoint.

**Approach:** Replace that ownership seam with one logical SIO transaction ingress. It owns CMD/UART/GPIO sequencing, sends `D1:`–`D8:` to a portable disk frontend that directly composes the existing shared `DiskService`, and reserves an independent `0x7F` attachment for Story 2.2.

## Boundaries & Constraints

**Always:** Consume the canonical Story 1.1 fixture matrix in production C++ tests; preserve its byte-exact v1 commands, STATUS, geometry, and error behavior. Reuse the `DiskDevice`-owned `DiskService`, never `DiskDevice` protocol handling. Correct generic malformed classic-256 ATR counting in `AtrDiskImage`; keep SIO-only rejection of ordinary 512-byte ATRs in the Atari frontend. Allocate 256 bytes but transmit `DiskResult.bytes`. STATUS inspects `info()`/pending state only and never calls `ensure_mounted()`. Register the ingress as a core work source so its wait delegates to ESP32 `UartChannel::wait_for_readable()` and wakes on the existing UART event queue, rather than the 20 ms fallback cadence.

**Ask First:** Any change to fixture protocol, command surface, boot policy, status mapping, physical timing/electrical policy, a second UART/GPIO owner, or an enabled `0x7F` protocol before Story 2.2.

**Never:** Put disk traffic in `Channel`, `ITransport`, `DiskDevice`, FujiBus, SLIP, or `LegacyTransport`; create another `DiskService`; modify Atari NIO library/guest code; implement `0x7F`, AltirraSDL/NetSIO, physical timing acceptance, or Story 1.3 boot-media packaging.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| Disk transaction | CMD-delimited valid D1–D8 v1 command | Sole ingress wakes on UART readiness and dispatches portable frontend to matching shared slot | Non-disk/non-`0x7F` device is ignored; `0x7F` has no disk parse |
| ATR read/write | 128/classic-256, writable/read-only, lazy slot | Exact fixture phases, actual transfer size, nonzero write/readback | Checksum/pre-write rejection is non-mutating; accepted verify failure may persist data |
| STATUS lifecycle | Pending, failed, retained, then successful slot operation | Non-mounting STATUS reports frozen state and clears only after success | Invalid sector is deliberate v1 `A,E`, not malformed `N` |
| Geometry | Malformed small-256 or ordinary 512 ATR | Generic parser rejects malformed classic-256; Atari frontend rejects 512 | No platform policy leaks into generic `DiskService` |

</frozen-after-approval>

## Code Map

- `repos/fujinet-nio/src/platform/esp32/atari_sio_fujibus_channel.cpp:94` -- replace stream-only UART/GPIO/framer owner with the sole transaction ingress; `UartChannel` must remain uniquely owned.
- `repos/fujinet-nio/src/platform/esp32/channel_factory.cpp:76` and `build_profile.cpp:22` -- migrate `SioGpio` selection away from `FujiBusSlip`; retain the build flag only if it names the dual-plane owner accurately.
- `repos/fujinet-nio/src/app/main_esp32.cpp:272` -- currently constructs channel/transport before `DiskDevice` registration at 301; reorder/attach after registration to inject `disk_service()` and explicitly poll ingress every main-loop tick.
- `repos/fujinet-nio/include/fujinet/io/transport/{io_service,transport}.h` and `src/lib/io_service.cpp:28` -- extend the existing waitable-work mechanism with a non-transport work source; do not represent disk SIO as an `ITransport`.
- `repos/fujinet-nio/include/fujinet/platform/esp32/uart_channel.h:44` and `src/platform/esp32/uart_channel.cpp:345` -- existing event-queue wait is the ingress wake primitive; do not add another UART driver or RX task.
- `repos/fujinet-nio/include/fujinet/io/devices/disk_device.h:14` -- authoritative boundary: obtain its existing `DiskService&`, do not instantiate another.
- `repos/fujinet-nio/src/lib/disk/disk_service.cpp:405` and `include/fujinet/disk/disk_service.h:71` -- reads/writes lazy-mount; `info()` and `get_pending_mount()` support non-mutating STATUS.
- `repos/fujinet-nio/src/lib/disk/atr_image.cpp:78` -- fix classic-256 payload/count validation; preserve generic ATR concerns only.
- `repos/fujinet-nio/tests/test_disk_image_cursor.cpp:103` and `test_disk_device_protocol.cpp` -- reusable in-memory file/DiskService test patterns; add production frontend/ingress tests and test-only fixture loader consuming `integration-tests/atari-sio` literals.
- `repos/fujinet-nio/build-artifacts/{CMakeLists_posix.cmake,src/CMakeLists.txt}` and `scripts/update_cmake_sources.py:1` -- generated source lists; update through the script and review its diff before adding sources.

## Tasks & Acceptance

**Execution:**
- [x] `repos/fujinet-nio/include/fujinet/io/atari_sio_disk_frontend.h`, `src/lib/atari_sio_disk_frontend.cpp`, `include/fujinet/platform/esp32/atari_sio_ingress.h`, and `src/platform/esp32/atari_sio_ingress.cpp` -- add a portable transaction-oriented disk frontend plus the sole ESP32 ingress. It owns one `UartChannel`, records CMD edges as transaction boundaries, dispatches D1–D8 now, implements the core work-source wait by delegating to the existing UART event queue, and exposes a future `0x7F` handler registration point.
- [x] `repos/fujinet-nio/include/fujinet/io/core/work_source.h`, `include/fujinet/io/transport/io_service.h`, `include/fujinet/core/core.h`, `src/lib/{io_service,fujinet_core}.cpp`, `src/app/main_esp32.cpp`, `src/platform/esp32/{channel_factory,build_profile}.cpp`, `build-artifacts/{CMakeLists_posix.cmake,src/CMakeLists.txt}`, and `scripts/update_cmake_sources.py` output -- add a non-transport waitable-work registration path; construct/register `DiskDevice`, restore boot mounts, construct/inject ingress, then run ingress polling and `core.waitForWork()` without a Channel, FujiBus transport, or dummy endpoint.
- [x] `repos/fujinet-nio/src/lib/disk/atr_image.cpp` and focused host tests -- enforce exact classic-256 payload arithmetic and reject malformed layouts; leave 512 acceptance/rejection policy outside generic disk code.
- [x] `repos/fujinet-nio/tests/test_atari_sio_disk_*.cpp` plus fixture loader -- execute Story 1.1 scenarios through real frontend/DiskService memory media: all D1–D8 slots, phases/checksums, lazy mounts, STATUS state, errors, and nonzero sector-4 write/readback.
- [x] `repos/fujinet-nio/docs/{architecture,build_profiles}.md` -- replace obsolete raw-FujiBus SIO ownership description with the disk ingress and explicitly mark native `0x7F` attachment as Story 2.2.

**Acceptance Criteria:**
- Given every canonical disk fixture selected by a production C++ test, when real frontend code processes it, then exact phases/payloads/checksums and the scenario identifier agree without fixture-generated production framing.
- Given D1–D8 and a pending slot, when READ/PUT/WRITE/STATUS execute, then slots remain isolated, data operations lazy-mount, and STATUS is non-blocking.
- Given malformed, unsupported, invalid-sector, read-only, I/O, and verify-failure cases, when processed, then `N` versus `A,E`, retained/cleared STATUS, and mutation guarantees match Story 1.1.
- Given malformed classic-256 and ordinary 512 ATRs, when mounted/served, then the former is rejected generically and the latter is rejected only by the Atari disk frontend.
- Given future Story 2.2 supplies a `0x7F` handler, when it attaches to the ingress, then it needs neither UART/GPIO ownership nor disk-frontend restructuring.

## Design Notes

`AtariSioIngress` is the only CMD/UART/GPIO sequencer and has an explicit `poll()` called from the ESP32 main loop; an injected physical-port interface makes transaction ordering host-testable. It is also a non-transport core work source: `wait_for_work()` delegates to the already event-aware `UartChannel`, so UART arrival wakes the loop promptly instead of falling through to 20 ms sleep. A lightweight CMD GPIO edge handler only records/reset-bounds the current transaction; the arrival of its UART command frame is the readiness wakeup, so no second UART driver, RX task, or stream transport is introduced. `AtariDiskFrontend(DiskService&)` has no ESP32, Channel, or transport dependency. The disk-only profile creates no Channel and no FujiBus transport. The ingress ignores `0x7F` until Story 2.2 registers its packet-native endpoint. Epic 3 measures and accepts the resulting physical timing/electrical behavior; it does not supply this ingress mechanism.

## Verification

**Commands:**
- `source "$NIO_WORKSPACE/scripts/env.sh" && python3 -m unittest discover -s integration-tests/atari-sio/tests -v` -- expected: canonical fixture authority remains valid.
- `source "$NIO_WORKSPACE/scripts/env.sh" && ./build.sh -cp fujibus-pty-debug && ctest --test-dir build/fujibus-pty-debug -R fujinet-nio-tests --output-on-failure` -- expected: all production disk/frontend/ATR host tests pass.
- `source "$NIO_WORKSPACE/scripts/env.sh" && ./build.sh -b` -- expected: configured ESP32 Atari profile compiles its sole ingress owner.

**Execution result:** Canonical fixtures, focused frontend tests, and the complete host CTest suite pass. The Atari PlatformIO target compiles the new ingress and frontend but its final link exceeds the ESP32 IRAM segment by 4,840 bytes; no protocol contradiction was found. The target needs an independent board-image/IRAM-budget resolution before hardware acceptance.
