---
title: 'Implement the bounded native Atari NIO client backend'
feature: 'atari-nio-physical-sio'
story: '2.1'
type: 'feature'
created: '2026-10-21'
status: 'done'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/SPEC.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-fujinet-nio-workspace-2026-10-19/ARCHITECTURE-SPINE.md'
  - '_bmad-output/planning-artifacts/epics-atari-nio-physical-sio.md'
---

# Story 2.1: Implement the bounded native Atari NIO client backend

## Intent

As an Atari application developer, I want the public NIO library to exchange
one bounded packet-native request and response over SIO device `0x7F`, so that
the same FujiBus service API is available without application SIO framing
logic.

This story changes only `repos/fujinet-nio-lib`. It replaces the Atari
target's current direct-but-stream-shaped backend with the client half of the
approved v1 `Q`/`W`/`P`/`R` contract. It does not implement the server endpoint
(Story 2.2), emulators/NetSIO (Story 2.3), the guest XEX (Story 2.4), disk
boot, BASIC `N:`, or physical acceptance.

## Governing contract

`SPEC.md`, `wire-and-acceptance.md`, and Architecture Decisions AD-1 through
AD-4 are authoritative. In particular, this is the Atari application plane
only: `0x7F` is an SIO address, not a FujiBus service ID; the packet is a raw
FujiBus packet, not SLIP; and the disk `D1:`--`D8:`/`DiskService` plane is
untouched.

## Delivered implementation

`repos/fujinet-nio-lib/src/platform/atari/fn_transport.s` is now the native
packet client. It sends raw complete FujiBus packets through SIO device `0x7F`
with a named 512-byte capacity, never uses SLIP or chunking, and derives every
`W`/`R` DCB count and AUX from the exact packet length. `P` and optional `Q`
use their fixed client receive counts and AUX zero.

The target preserves the existing `fn_transport_*` ABI and common packet layer.
The Atari-only declarations in `include/fujinet-nio.h` expose explicit
capability discovery, baseline capacity, and the ISR-safe PROC latch; the
library-link test references them under `__ATARI__`. No common backend or
non-Atari source selection changed.

## Interface decisions

- Keep `fn_init`, `fn_is_ready`, `fn_raw_call`, service APIs, and the
  `fn_transport_*` ABI compatible. The common layer continues to supply a
  complete FujiBus request and response buffer.
- `fn_transport_exchange` first validates that the complete request fits the
  shared 512-byte v1 limit and that its response capacity can receive the
  returned exact packet. It sends no partial packet, padding, SLIP delimiter,
  escape byte, or implicit segment. An oversize request/advertised response is
  an explicit transport failure using an existing suitable public error; do
  not add a wire command or silently truncate.
- The normal exchange is `W` only while locally idle, then polling `P`, then
  terminal `R` using precisely the ready length as AUX and DCB count. `P` is
  always the fixed three-byte receive; `Q`, when explicitly requested, is the
  fixed four-byte receive with AUX zero. The backend never probes with `Q` on
  ordinary initialization or exchange.
- Baseline capacity is 512 bytes without `Q`. An opt-in capability helper may
  cache only a valid wire-revision-1 `Q` result and selects
  `min(compiled_capacity, advertised_maximum)`. It rejects an incompatible
  revision or an advertised v1 maximum below 512 rather than creating a
  lower-capacity v1 mode.
- Default readiness is polling. The optional ISR-safe hook is exactly a
  constant-time flag latch for an application-owned/chained `VPRCED` handler;
  it installs, replaces, and chains no vector, performs no SIO, and does not
  make readiness true. Non-IRQ code still confirms with `P` before `R`.
- A valid accepted `W` creates one outstanding transaction. On local polling
  deadline expiry return `FN_ERR_TIMEOUT` without sending a cancellation or a
  second `W`. Before later traffic attempts a new request, the backend must
  observe `P`; when ready it must perform a valid terminal `R` to consume the
  old response (even if that old caller can no longer use it). It must never
  issue automatic application replay after a timeout. Rejected/malformed local
  commands create no transaction; a failed terminal `R` remains recoverable as
  defined by the wire contract.
- If recovery cannot complete, return a transport error and retain the
  uncertain outstanding state. In particular, a ready length larger than the
  caller response capacity must not overrun that buffer or cause the backend
  to forget the request; it remains recoverable only by a later valid terminal
  `R` with adequate storage.
- Preserve the existing common-layer rule that an actual FujiBus service error
  is returned in a normal response. Map only rejected/malformed SIO operations,
  exhausted local deadline, and local bounds/response corruption to transport
  errors. Do not infer pending from `NAK`.

## Acceptance criteria

1. Given canonical native-NIO literal fixtures, the focused backend tests
   prove optional idle-only `Q`, idle-only `W`, fixed `P`, and exact-length
   `R`, including the DCB client invariants and control/data/checksum sequence.
2. The Atari archive exchanges unmodified complete FujiBus packets up to 512
   bytes with no SLIP, padding, or implicit segmentation. Its public API and
   non-Atari archives remain compatible.
3. Pending/ready, rejected `W`, malformed command, wrong `R` AUX length,
   interrupted terminal `R`, and reset recovery prove the one-outstanding
   consume/retain behavior. No cancellation command, transaction ID, or
   automatic post-timeout application retry is introduced.
4. A caller that does not opt in to `Q` uses 512 bytes. Capability discovery is
   explicit and uses the lesser capacity rule above. Polling is correct without
   PROC; the notification hook is bounded and performs no IRQ/vector ownership.
5. Focused host-side backend tests pass, then
   `source "$NIO_WORKSPACE/scripts/env.sh" && cd repos/fujinet-nio-lib && make check`
   passes in full.

## Focused implementation/test map

| Area | Required work | Boundary |
| --- | --- | --- |
| `repos/fujinet-nio-lib/src/platform/atari/fn_transport.s` and its local includes | Replace stream/SLIP chunk exchange with native DCB `Q`/`W`/`P`/`R`, bounded state/recovery, and SIO status mapping. | No firmware server behavior or disk dispatch. |
| `repos/fujinet-nio-lib/include/` plus Atari-local source as needed | Add the narrowly Atari-scoped capability/notification API and one shared v1 capacity definition. | Do not alter established generic API semantics or other target ABI. |
| `repos/fujinet-nio-lib/tests/` and Makefile test registration | Add a host-side DCB/SIO seam test that consumes literal NIO fixture cases and asserts command, AUX, receive count, payload exactness, state transitions, deadline recovery, and hook behavior. | The test oracle must not import the production backend/framer. |
| `repos/fujinet-nio-lib/docs/transport-backends.md` | Correct Atari backend documentation from SLIP/chunking to the approved packet-native contract. | Reference the canonical wire contract; do not duplicate it. |

The focused runtime test is `tests/atari_transport_soft65c02.s`. It includes
the production assembly and intercepts its SIOV call, rejecting unexpected
calls while asserting device, command, direction, 16-bit count, AUX, packet
data, response data, returned length, and ordering. It covers accepted timeout
recovery, rejected `W`, interrupted `R`, 511/512/513 boundaries, canaries,
invalid `Q`, malformed `P`, reset-to-idle, and the PROC latch. It is executed
by `make test-atari-transport`, which is a dependency of `make check`.

## Fixture prerequisite resolved

`integration-tests/atari-sio/fixtures/nio_v1.json` and its stdlib validator
now provide stable, production-independent native-v1 literals: SIO command
frames/checksums, exact DCB/AUX values, small packet checksums, the 512-byte
pattern checksum, rejection, timeout/recovery, malformed poll, reset, and
invalid-capability cases. The fixture describes observable wire/client facts;
it does not implement either endpoint.

## Acceptance evidence

| Criterion | Implementation and executed evidence |
| --- | --- |
| 1 | `nio_v1.json` plus `test_nio_v1_fixtures.py` validate literal frames, checksums, fixed `Q`/`P`, exact `W`/`R`, boundaries, and recovery facts. The assembled soft65c02 SIOV test verifies every DCB field and rejects unexpected calls. |
| 2 | `fn_transport.s` uses `NIO_CAPACITY = 512`, raw caller buffers, and exact lengths. The runtime test verifies 511/512 requests, a full 512-byte non-repeating request/response pattern, canaries, and local 513 rejection. `make check` builds Atari, BBC, MS-DOS, Linux, and Amiga archives. |
| 3 | Runtime modes prove pending timeout retain/recovery, rejected `W` direct retry, interrupted `R` recovery, unknown/zero/error `P` retention, oversized ready retention, and reset idle release before a distinct new `W`. |
| 4 | `fn_atari_max_payload()` starts at 512; explicit `Q` verifies revision/capacity and restores baseline on failure. `fn_atari_proc_notify()` is a one-store latch; the runtime test proves it causes no SIOV call or transaction. Foreground still polls `P`. |
| 5 | Executed: `python3 -m unittest discover -s integration-tests/atari-sio/tests -v`; `make test-atari-transport`; `make atari`; and `make check` after sourcing the workspace environment. |

## Dependencies and hand-off

- Depends on the completed Epic 1 single ingress/disk frontend only as an
  architectural preservation boundary; it requires no changes there.
- Does not depend on Story 2.2 implementation, but its client tests must use
  the approved fixture contract so Story 2.2 can independently implement the
  peer.
- Hands the exact client contract and fixture cases to Story 2.2; Story 2.2
  owns the sole firmware `0x7F` server route and must not change library
  behavior or the `D1:`--`D8:` frontend.

## Out of scope

No changes to `repos/fujinet-nio`, `repos/nio-core-apps`, the production
`AtariSioDiskFrontend`/`DiskService` path, firmware ingress topology, legacy
FujiNet commands, CIO `N:`, AltirraSDL/NetSIO, or physical hardware/timing.

## Remaining limitation

The completed soft65c02 evidence executes the real assembled client with an
intercepted SIOV peer; it is not a live client-to-production-firmware run.
That integration, emulator/NetSIO behavior, and physical SIO proof remain the
explicit scope of Stories 2.2 and 2.3.
