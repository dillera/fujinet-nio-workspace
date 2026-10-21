---
title: 'Serve packet-native NIO on the Atari SIO channel'
feature: 'atari-nio-physical-sio'
story: '2.2'
type: 'feature'
created: '2026-10-21'
status: 'draft'
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

## Current production seam

Story 1.2 already has the required ingress boundary:
`AtariSioIngress` owns the one `UartChannel`, records CMD edges, routes
`D1:`--`D8:` to its disk frontend, and reserves `0x7F`. Its current
`NativeHandler` receives only a five-byte command frame, so it cannot validate
or receive a `W` data frame, retain a response, or emit `Q`/`P`/`R` replies.
`main_esp32.cpp` constructs the ingress after `DiskDevice` registration, so
`core.routingManager()` is available at the attachment point.

The older `AtariSioFujiBusChannel`/`AtariSioFujiBusFramer` is not selected by
the current `FN_BUILD_ATARI_FUJIBUS_SIO` profile, but is still compiled under
that macro. It implements the obsolete two-command, padded, SLIP composition
and therefore cannot be retained as a native-v1 implementation or test oracle.

## Implementation design

### 1. Add one portable native endpoint and attach it to the existing ingress

Add a host-testable `AtariSioNioFrontend` under `include/fujinet/io/` and
`src/lib/`. It accepts a five-byte SIO command frame and, only for an accepted
`W`, the exact AUX-sized data frame plus its SIO checksum. Its result mirrors
the existing disk frontend: reply bytes and an optional expected incoming-data
length. `AtariSioIngress` changes its one pending-write discriminator from
disk-only state to `{none, disk, nio}` and delegates `0x7F` command/data work
to this object. No second UART, `Channel`, `ITransport`, task, or ingress is
introduced.

Construct the frontend with `io::IRequestHandler&`; production passes
`core.routingManager()` when constructing the existing ingress. On one valid
raw FujiBus `W` packet, the frontend uses the existing raw packet mapping to
create one `IORequest`, invokes that handler once, maps the returned
`IOResponse` back to one raw FujiBus response, and queues it. Refactor the
small raw-packet-to-`IORequest`/`IOResponse` mapping currently embedded in
`FujiBusTransport` into a shared packet-codec helper used by both callers;
this is a codec extraction, not a service or transport implementation.

The frontend owns exactly one response slot and has explicit idle,
receiving/pending, and ready state. Synchronous core handlers will normally
make the slot ready before the first poll; the state model still forbids a
second request while it is receiving, pending, or ready. Do not add an async
service scheduler merely to manufacture a pending interval.

### 2. Implement the native-v1 transaction rules exactly

Use the literal command/reply/checksum conventions in `nio_v1.json`:

| Command | Idle/valid behavior | Rejection and retention behavior |
| --- | --- | --- |
| `Q` | AUX zero only; return `A,C`, four capability bytes `{1, 0x00, 0x02, 0x00}`, and their SIO checksum. It creates/consumes no slot. Flags are zero until the firmware actually emits the optional advisory PROC pulse. | Nonzero AUX or non-idle state returns `N`; queued state is unchanged. |
| `W` | Idle only; AUX is the exact nonzero raw-packet length, at most 512. A valid command is acknowledged, then an exact data frame with valid SIO checksum and valid raw FujiBus packet dispatches once to the core and completes. | Bad command/data checksum, zero/oversize AUX, malformed raw FujiBus, or non-idle state returns `N`; no core dispatch and no slot on rejection. |
| `P` | AUX zero only; return `A,C`, exactly `{state,length-lo,length-hi}` plus its SIO checksum. Idle/pending length is zero; ready length is the queued raw-response size. | Bad frame or nonzero AUX returns `N` and changes no slot. |
| `R` | Ready only; AUX must equal the queued response size. Emit `A,C`, exactly that raw response, and its SIO checksum. Consume the slot when this valid terminal command is accepted, before transmitting data. | Wrong AUX, non-ready state, or bad command frame returns `N` and retains the queued response. |

The endpoint must reject any generated core response larger than 512 without
padding or truncating it. It must instead queue a bounded, normal FujiBus
error response using the established `IOResponse` status convention; a valid
`W` never becomes an SIO `NAK` merely because service processing failed. This
keeps `NAK` exclusively for malformed/rejected transport transactions.

### 3. Retire the native-profile obsolete path

Remove the unselected ESP32 `AtariSioFujiBusChannel`, its padded/SLIP
`AtariSioFujiBusFramer`, and their composition regression from the native
firmware source/test lists; update only hand-maintained textual architecture
and profile documentation that still describes this obsolete path. Do not
edit generated UML/SVG artifacts. Keep the separate legacy profile family
unchanged, but ensure it is neither selected by `FN_BUILD_ATARI_FUJIBUS_SIO`
nor counted by native-v1 tests.

## Executable conformance seam

The smallest test seam is the portable `AtariSioNioFrontend`, constructed with
a real `FujinetCore::routingManager()` and a test-only registered
`VirtualDevice` that records one `IORequest` and returns a deterministic
`IOResponse`. This proves the actual core routing boundary without creating a
firmware endpoint or emulator peer. It also lets host tests feed literal SIO
command/data frames and inspect every emitted byte.

Add `tests/test_atari_sio_nio_frontend.cpp`, loading
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

The test must explicitly document that fixture `dcb_count` fields are
client-side assertions, not inputs to or validation by the firmware endpoint.
Run it in the existing POSIX CTest binary. Build the Atari ESP32 profile after
wiring the endpoint; virtual NetSIO/Altirra and guest-XEX execution are
deliberately not added here.

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

## Review question

`nio_v1.json` is sufficient as the literal SIO-envelope authority, but its
current four-byte `w-idle`/`r-ready` payload is intentionally a transport
vector, not a parseable raw FujiBus packet (`FujiBusPacket::fromRaw()` rejects
it). To prove the required real core dispatch without making a production
serializer the oracle, Story 2.2 needs one additional literal, parseable
raw-request/raw-response fixture scenario (or explicit companion fields on
the existing W/R scenario) with independently checked FujiBus bytes. This is
fixture evidence only and does not alter the approved SIO protocol. Approval
is requested for that smallest fixture extension; no other design decision is
blocked.

## Out of scope

No change to `repos/fujinet-nio-lib`, the public Atari API, disk fixture
semantics, DiskService/DiskDevice service behavior, CIO `N:`, NetSIO,
AltirraSDL, an emulator, configuration ATR/XEX, or physical SIO timing and
electrical work.
