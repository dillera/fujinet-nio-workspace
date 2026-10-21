---
title: 'Serve packet-native NIO on the Atari SIO channel'
feature: 'atari-nio-physical-sio'
story: '2.2'
type: 'feature'
created: '2026-10-21'
status: 'done'
baseline_workspace_commit: '8d0ce005'
baseline_library_commit: 'b7fc675c'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/SPEC.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-fujinet-nio-workspace-2026-10-19/ARCHITECTURE-SPINE.md'
  - '_bmad-output/planning-artifacts/epics-atari-nio-physical-sio.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-1-2-serve-standard-atr-drives-through-diskservice.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-2-1-implement-bounded-native-atari-nio-client-backend.md'
---

# Story 2.2: Serve packet-native NIO on the Atari SIO channel

## Intent

As an Atari NIO client, I want FujiNet to route native SIO device `0x7F`
`Q`/`W`/`P`/`R` transactions into the existing FujiBus core, so Clock,
Network, File, and Disk use their existing services without a legacy adapter.

This is the firmware half of the completed Story 2.1 client. It changes only
`repos/fujinet-nio` and the existing workspace NIO fixture evidence as needed
to express an already-approved literal case. It does not implement NetSIO or
AltirraSDL parity (Story 2.3), a guest XEX/BASIC handler (Story 2.4), or
physical timing/electrical acceptance (Epic 3).

## Governing boundaries

`wire-and-acceptance.md`, AD-1 through AD-9, and
`integration-tests/atari-sio/fixtures/nio_v1.json` are authoritative. In
particular:

- `AtariSioIngress` remains the only CMD/UART/GPIO sequencer. `D1:`--`D8:`
  continue directly to `AtariSioDiskFrontend` and its shared `DiskService`.
  The NIO endpoint must neither parse disk traffic nor create another
  `DiskService`.
- `0x7F` is solely an SIO address. Its `W` and `R` payloads are complete raw
  FujiBus packets, never SLIP or a stream/chunk protocol. Existing services
  remain owned by `FujinetCore`/`RoutingManager`/`IODeviceManager`.
- The endpoint validates observable command-frame checksum, command, AUX,
  transport state, payload checksum, and the 512-byte bound. It must not
  purport to validate DCB byte count: only the client has that value for
  `Q`/`P`, and it is not carried on physical SIO.
- A CMD edge resets only ingress byte collection. It must not clear a queued
  NIO response. A real device restart constructs the endpoint idle; that is
  the reset that releases an outstanding request.

## Implemented production design

### 1. Portable native endpoint attached to the existing ingress

`AtariSioNioFrontend` is a host-testable endpoint under `include/fujinet/io/`
and `src/lib/`. It accepts a five-byte SIO command frame and, only for an accepted
`W`, the exact AUX-sized data frame plus its SIO checksum. Its result mirrors
the existing disk frontend: reply bytes and an optional expected incoming-data
length. `AtariSioIngress` extends its pending-write discriminator from
disk-only state to `{none, disk, nio}` and delegates `0x7F` command/data work
to this object. No second UART, `Channel`, `ITransport`, task, or ingress is
introduced.

The frontend is constructed with `io::IRequestHandler&`; production passes
`core.routingManager()` when constructing the existing ingress. On one valid
raw FujiBus `W` packet, the frontend uses the existing raw packet mapping to
create one `IORequest`, invokes that handler once, maps the returned
`IOResponse` back to one raw FujiBus response, and queues it. The former
small raw-packet-to-`IORequest`/`IOResponse` mapping in `FujiBusTransport` is
now the shared packet-codec helper used by both callers; this is a codec
extraction, not a service or transport implementation.

The frontend owns exactly one response slot and has explicit idle,
receiving/pending, and ready state. Synchronous core handlers will normally
make the slot ready before the first poll; the state model still forbids a
second request while it is receiving, pending, or ready. Do not add an async
service scheduler merely to manufacture a pending interval.

### 2. Native-v1 transaction rules

The endpoint implements the literal command/reply/checksum conventions in
`nio_v1.json`:

| Command | Idle/valid behavior | Rejection and retention behavior |
| --- | --- | --- |
| `Q` | AUX zero only; return `A,C`, four capability bytes `{1, 0x00, 0x02, 0x00}`, and their SIO checksum. It creates/consumes no slot. Flags are zero until the firmware actually emits the optional advisory PROC pulse. | Nonzero AUX or non-idle state returns `N`; queued state is unchanged. |
| `W` | Idle only; AUX is the exact nonzero raw-packet length, at most 512. A valid command is acknowledged, then an exact data frame with valid SIO checksum and valid raw FujiBus packet dispatches once to the core and completes. | Bad command/data checksum, zero/oversize AUX, malformed raw FujiBus, or non-idle state returns `N`; no core dispatch and no slot on rejection. |
| `P` | AUX zero only; return `A,C`, exactly `{state,length-lo,length-hi}` plus its SIO checksum. Idle/pending length is zero; ready length is the queued raw-response size. | Bad frame or nonzero AUX returns `N` and changes no slot. |
| `R` | Ready only; AUX must equal the queued response size. Emit `A,C`, exactly that raw response, and its SIO checksum. Consume the slot when this valid terminal command is accepted, before transmitting data. | Wrong AUX, non-ready state, or bad command frame returns `N` and retains the queued response. |

The endpoint rejects any generated core response larger than 512 without
padding or truncating it. It must instead queue a bounded, normal FujiBus
error response using the established `IOResponse` status convention; a valid
`W` never becomes an SIO `NAK` merely because service processing failed. This
keeps `NAK` exclusively for malformed/rejected transport transactions.

### 3. Retired native-profile obsolete path

The unselected ESP32 `AtariSioFujiBusChannel`, its padded/SLIP
`AtariSioFujiBusFramer`, and their composition regression from the native
firmware source/test lists are removed. Hand-maintained textual architecture
and profile documentation are updated; generated UML/SVG artifacts are not
edited. The separate legacy profile family remains unchanged and is neither
selected by `FN_BUILD_ATARI_FUJIBUS_SIO` nor counted by native-v1 tests.

## Executable conformance seam

The smallest test seam is the portable `AtariSioNioFrontend`, constructed with
a real `FujinetCore::routingManager()` and a test-only registered
`VirtualDevice` that records one `IORequest` and returns a deterministic
`IOResponse`. This proves the actual core routing boundary without creating a
firmware endpoint or emulator peer. It also lets host tests feed literal SIO
command/data frames and inspect every emitted byte.

`tests/test_atari_sio_nio_frontend.cpp` loads
`integration-tests/atari-sio/fixtures/nio_v1.json` as the envelope oracle in
the same manner as the completed disk frontend test. It must assert scenario
IDs and literal `A`/`C`/`N`, AUX-derived exact payloads, and independently
calculated SIO checksums. It must cover:

- `Q` capability bytes, `Q` non-idle/nonzero-AUX rejection, and no state
  mutation;
- one valid `W` mapping to exactly one core request, then `P(ready)`, exact
  `R`, and post-consumption `P(idle)`;
- second `W` rejection while a response is ready, wrong-length `R` retention,
  malformed command/data/FujiBus rejection without a core call, and 513-byte
  rejection;
- response-bound handling, interrupted-client semantics (valid `R` consumes
  before bytes leave the device), and endpoint reconstruction/reset returning
  to idle without a stale reply;
- the completed `D1:`--`D8:` frontend tests continue unchanged; the native
  frontend is only attached after `AtariSioIngress` has selected `0x7F`, so it
  cannot consume a disk frame.

The test explicitly documents that fixture `dcb_count` fields are client-side
assertions, not inputs to or validation by the firmware endpoint. It runs in
the existing POSIX CTest binary. The Atari ESP32 profile is built after wiring
the endpoint; virtual NetSIO/Altirra and guest-XEX execution are deliberately
not added here.

## Acceptance checklist

1. A valid `0x7F` `W` has one complete raw FujiBus request, dispatches exactly
   once through the existing core route, and blocks another `W` until valid
   terminal `R` or device restart.
2. `Q`/`P`/`R` obey the canonical observable AUX, state, control-byte, exact
   data-size, and SIO-checksum rules. Tests do not pretend firmware observes
   a client DCB count.
3. Rejection, bad checksums, malformed raw packet, wrong `R` AUX, interrupted
   terminal delivery, response oversize, and reset preserve/consume state as
   specified and never produce padding, implicit segmentation, cancellation,
   or automatic replay.
4. `D1:`--`D8:`, the single physical ingress, shared `DiskService`, and all
   pre-existing FujiBus service implementations remain unchanged in ownership
   and behavior.
5. The native profile no longer builds or treats the old SLIP/padded
   `0x7F` framer as v1 conformance. NetSIO/Altirra migration remains Story 2.3.

## Verification

Source the workspace environment first, then run the fixture validator and
the focused host lane before the normal firmware gates:

```sh
source "$NIO_WORKSPACE/scripts/env.sh"
python3 -m unittest discover -s integration-tests/atari-sio/tests -v

cd repos/fujinet-nio
./build.sh -cp fujibus-pty-debug
ctest --test-dir build/fujibus-pty-debug -R 'fujinet-nio-tests' --output-on-failure
./build.sh -b
```

The CTest evidence proves the portable endpoint/core-dispatch contract, not
UART timing, real hardware, NetSIO, AltirraSDL, or public guest-XEX behavior.

## Completion audit and executable evidence

The implementation is complete for this story's independently testable
firmware scope.

| Acceptance criterion | Production implementation | Executed evidence |
| --- | --- | --- |
| One complete `W` dispatches once and one slot blocks later `W` until `R` or reset. | `AtariSioNioFrontend` owns `Idle`/`Receiving`/`Ready`, decodes through `fujibus_packet_codec`, and invokes the injected `RoutingManager` once only after a valid data checksum and raw packet. | `test_atari_sio_nio_frontend.cpp` uses a real `FujinetCore` plus a recording `VirtualDevice`; it proves the literal `core-dispatch` pair, one request, busy-W rejection, terminal consumption, reset, and a full 512-byte exchange. |
| `Q`/`W`/`P`/`R` use the native-v1 control bytes, AUX, exact lengths, and SIO checksums. | `AtariSioNioFrontend::begin()` and `complete_write()` validate command/data checksums, AUX, state, and the 512-byte bound; response data is emitted as `A,C,payload,checksum`. Firmware intentionally has no DCB-count input. | The independent fixture validator checks all `nio_v1.json` literals. Focused endpoint tests load the literal envelope frames and explicitly document that DCB counts are client-side-only. |
| Rejection and recovery preserve or consume state correctly. | Invalid command/data/raw packet, zero/oversize W, busy W, wrong R AUX, and non-idle Q return `N` without dispatching or losing a ready response. A valid R copies reply bytes before consuming its slot; `abort_write()` only cancels an incomplete W; `reset()` clears the slot. Oversize service output is converted to a bounded normal FujiBus error response. | Endpoint and ingress-router tests cover malformed/truncated W, wrong-R retention, terminal-R lifetime, CMD-edge preservation of ready data, reset, oversize response handling, and subsequent valid W. |
| Single ingress and disk ownership remain intact. | `AtariSioIngressRouter` is the sole byte collector with `{none,disk,nio}` pending-write state; ESP32 `AtariSioIngress` remains the only CMD/UART/GPIO owner. `main_esp32.cpp` constructs it with `disk_service()` and `core.routingManager()` after disk registration. | `test_atari_sio_ingress_router.cpp` verifies D1 and D8 reads stay in `AtariSioDiskFrontend`/`DiskService`, while `$7F` reaches the real core route and malformed data does not dispatch. |
| Reply bytes remain valid across terminal consumption and transmission. | Terminal R returns an owning `Result::bytes` copy before clearing the frontend slot. ESP32 `UartChannel::write()` now retries partial ESP-IDF enqueues until its supplied buffer is fully queued, then ingress flushes it. | The terminal-R test retains and verifies its result after a subsequent idle poll; the focused full-512-byte test verifies one complete response payload plus checksum. The ESP32 native-profile build compiles the UART retry path. |
| The old native padded SLIP path cannot count as v1. | `AtariSioFujiBusChannel`/`AtariSioFujiBusFramer` and their composition test are deleted; both POSIX and ESP source lists omit them. The native profile is `TransportKind::None` + `SioGpio` and uses ingress only. | `test_atari_nio_profile_has_no_legacy_padded_slip_sio_adapter` checks obsolete paths and source-list references are absent and rejects `FujiBusSlip` in the native branch. |

Verification run after the final audit changes:

```sh
source /home/markf/dev/nio/fujinet-nio-workspace/scripts/env.sh
python3 -m unittest discover -s integration-tests/atari-sio/tests -v
# 19 tests passed

cd repos/fujinet-nio
./build.sh -cp fujibus-pty-debug
build/fujibus-pty-debug/tests/fujinet-nio-tests \
  --test-case="Atari native NIO frontend*,Atari SIO ingress router*" --no-skip
# 7 cases, 184 assertions passed
ctest --test-dir build/fujibus-pty-debug --output-on-failure
# 3/3 passed
python3 -m unittest discover -s py/tests -p 'test_platformio_board_config.py' -v
# 8 tests passed, including the no-legacy-adapter profile assertion
./build.sh -b
# atari-nio-fujibus-sio-gpio-fujinet-v1-16mb passed
```

This evidence does not claim NetSIO/Altirra interoperability, guest-XEX
execution, or physical SIO timing/electrical proof. Those remain explicitly
deferred to Stories 2.3/2.4 and Epic 3.

## Out of scope

No change to `repos/fujinet-nio-lib`, the public Atari API, disk fixture
semantics, DiskService/DiskDevice service behavior, CIO `N:`, NetSIO,
AltirraSDL, an emulator, configuration ATR/XEX, or physical SIO timing and
electrical work.
