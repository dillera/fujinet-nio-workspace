---
title: 'Establish independent virtual Atari NIO parity'
feature: 'atari-nio-physical-sio'
story: '2.3'
type: 'feature'
created: '2026-10-21'
status: 'in-progress'
baseline_workspace_commit: '2b8c4c37'
baseline_firmware_commit: '0581bd3f'
baseline_altirra_commit: '1456ba08'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/SPEC.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-fujinet-nio-workspace-2026-10-19/ARCHITECTURE-SPINE.md'
  - '_bmad-output/planning-artifacts/epics-atari-nio-physical-sio.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-1-3-boot-selected-configuration-or-mapped-atr-disk.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-2-1-implement-bounded-native-atari-nio-client-backend.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-2-2-serve-packet-native-nio-on-the-atari-sio-channel.md'
---

# Story 2.3: Establish independent virtual Atari NIO parity

## Intent and boundary

As a maintainer, I want NetSIO and AltirraSDL to execute the same literal
native SIO scenarios, so a scheduling or adapter regression is caught before a
physical Atari run.

This story makes the two virtual SIO adapters use the completed production
`AtariSioNioFrontend`, with their own SIO framing/scheduling code.  It proves
virtual protocol and scheduling behavior only.  It does not claim electrical
or physical timing compatibility (Epic 3), and it does not add the public API
guest XEX/BASIC acceptance application (Story 2.4).

`SPEC.md`, `wire-and-acceptance.md`, AD-1 through AD-9, and the independent
`integration-tests/atari-sio/fixtures/nio_v1.json` remain authoritative.  This
story creates a projection/sequence manifest only; it does not duplicate or
regenerate protocol byte literals from a production framer.

## Confirmed starting point

Story 1.3's deterministic page-6 boot lane is working and must remain intact:
`run_boot_acceptance.py` boots the acceptance ATR through the production
NetSIO process with `sio_patch: false`, `accurate_disk: true`, and records
Altirra, hub, NIO, DCB, and optional POKEY evidence.

The current virtual native adapters are deliberately pre-v1 and cannot count
as acceptance evidence:

- `repos/fujinet-nio/src/platform/posix/atari_netsio_fujibus_channel.cpp`
  accepts both `$7f` and legacy `$71`, implements only `W`/`R`, forwards a
  byte stream to `FujiBusTransport`, defaults reads to 768 bytes, and pads
  them.  Its `FN_BUILD_ATARI_FUJIBUS_NETSIO` profile selects
  `TransportKind::FujiBusSlip`.
- `repos/AltirraSDL/src/AltirraSDL/source/devices/fujinetnio.cpp` has the same
  `$7f`/`$71`, W/R-only, worker-plus-channel, padded-read model.  It must not
  become another packet endpoint.

Both already have a real SIO framing/scheduling boundary.  Story 2.2's
portable endpoint owns the native transaction semantics and core routing;
this story supplies it to those boundaries instead of reproducing it.

## Production changes

### 1. NetSIO becomes one virtual SIO ingress, not a FujiBus byte channel

Replace the native portion of `AtariNetSioFujiBusChannel` with a single
NetSIO ingress/work source (rename when that makes the ownership clear).  It
owns UDP/NetSIO framing, sync-credit exchange, device connect/alive lifecycle,
and SIO response emission.  It must compose:

- the existing `AtariSioDiskFrontend` for `D1:`--`D8:`;
- `AtariSioNioFrontend(core.routingManager())` for `$7f`; and
- `AtariSioIngressRouter` (or a factored byte-equivalent shared router) for
  complete five-byte command frames, exact accepted W data plus checksum, and
  CMD-edge collection reset.

The POSIX Atari-NetSIO startup path constructs this ingress only after the
real `FujinetCore`, `RoutingManager`, and `DiskService` are registered.  The
native profile becomes a direct SIO ingress profile (`TransportKind::None`);
it must not call `setup_transports()` or construct a `FujiBusTransport` for
native traffic.  The UDP socket is retained as the ingress's transport, not as
the application channel.  Other POSIX FujiBus/SLIP profiles and the supported
legacy SIO family remain unchanged.

NetSIO emission must preserve the endpoint result buffer until all partial or
credit-gated UDP output has been queued.  For `$7f`, it emits exactly the
frontend's `A`/`C`/`N`, payload, and SIO checksum bytes: no default read size,
padding, segmentation, `$71`, or legacy read helper.  A new command edge only
calls `reset_command_collection()`; an actual NetSIO warm/cold reset calls
`AtariSioNioFrontend::reset()`.  Thus an interrupted terminal R remains
consumed, a ready response survives a new CMD edge, and a reset is the only
virtual event that discards it.

### 2. AltirraSDL uses the same production endpoint through its real SIO API

Replace `AltirraFujiBusChannel`, the worker hand-off, and the W/R padded-read
state in `fujinetnio.cpp` with a device-local `AtariSioNioFrontend` bound to
the embedded core's `routingManager()`.  Keep Altirra's existing custom-device
SIO callbacks, ACK/NAK/COMPLETE scheduling, data receive callback, and
`IATDeviceSIO` command lifetime.  They are the independent virtual adapter;
they must not contain a second Q/W/P/R state machine or packet codec.

The adapter converts an accepted Altirra command into the literal five-byte
frame expected by the frontend, then sends only the returned bytes.  On W it
receives exactly AUX data bytes plus the SIO checksum, passes them once to
`complete_write`, and keeps frontend reply storage alive through queued
Altirra transmission.  On Q/P/R it sends the result directly.  `$71`, a
zero-AUX/default padded read, and stream chunking are removed from this native
device path.  Disk boot remains on the existing disk device/NetSIO path; this
device must not take ownership of `D1:`--`D8:`.

Altirra's SIO manager already rejects a command whose fifth byte fails the
Atari SIO checksum before it builds `ATDeviceSIOCommand`
(`src/Altirra/source/siomanager.cpp`).  The adapter therefore records that
boundary explicitly and constructs the verified fifth byte for the frontend.
Malformed data-frame checksums still reach the device receive callback and
must produce the frontend's canonical rejection.  Do not add an unchecked
command shortcut merely to exercise a malformed-command fixture; the host
manager rejection is the correct emulator-level observation.

### 3. Fixture projection and executable virtual evidence

Add the smallest workspace-owned virtual projection manifest, for example
`integration-tests/atari-sio/fixtures/nio_v1.virtual.manifest.json`.  It names
only stable scenario IDs and ordered operations from `nio_v1.json` plus the
existing disk/boot manifest.  It references canonical literal command,
payload, control, checksum, reset, and recovery vectors by ID; it does not
copy response generation rules or invoke production serializers.

The stdlib validator must validate every manifest reference, uniqueness of
scenario IDs, and the native-v1 exclusion marker.  It is the fixture oracle.
The adapter runners consume the projection and compare their observed SIO
bytes against those literals/checksums independently.  Add these native
scenario families:

- Q capability and invalid/unsupported command rejection;
- accepted W, P ready, exact R, one real core dispatch, and response ownership
  after terminal R;
- rejected W, wrong-length R retention, interrupted-R recovery, malformed
  P/data, and reset-to-idle recovery, followed by a successful new W/P/R;
- 511/512-byte accepted bounds, local/endpoint 513-byte rejection, exact
  512-byte response and checksum; and
- existing D1 boot/config-disk scenario IDs in the same run record.

Use the existing `run_boot_acceptance.py` lifecycle or factor its process and
evidence helpers into a small shared helper; do not create a second emulator
runner.  A fixture playback driver may inject observed SIO/NetSIO frames, but
it may not implement a Q/W/P/R peer: every reply must come from the production
endpoint through the production NetSIO or Altirra SIO adapter.  This is a
transport conformance driver, not the Story 2.4 public-API guest program.

For each stable scenario ID retain one timestamped run directory containing
the Altirra log, hub log where applicable, NIO log, POKEY SIODATA capture, and
machine/fixture result JSON.  Record adapter (`netsio` or `altirra-embedded`),
fixture ID, observed command/data/control bytes, and pass/fail.  Native runs
are labelled `virtual protocol/scheduling evidence only`.

## Focused tests and acceptance evidence

1. A POSIX CTest drives the NetSIO ingress with literal projection frames and
   a real `FujinetCore`/routing device.  It verifies exact incoming/outgoing
   NetSIO-to-SIO framing, `$7f` only, command and data checksum behavior,
   one dispatch, exact P/R state retention, reset, and no padded output.
2. An AltirraSDL device test exercises its SIO callback/queue through the
   projection, including command validation at the SIO manager boundary and
   the same recovery sequences.  It observes bytes emitted by the real
   production frontend, not an emulator-side response model.
3. The deterministic virtual integration lane runs the projection against
   both adapters and reports the same IDs.  It retains the existing page-6
   boot assertion and D1 trace unchanged, with native traffic added as a
   separate phase.  The fixture validator precedes both runs.
4. Profile/source assertions reject `$71`, `FujiBusSlip`,
   `DEFAULT_SIO_READ_SIZE`, padded-read helpers, and legacy W/R-only tests in
   the native-v1 adapter/test targets.  A legacy-control run, if retained,
   is labelled legacy and cannot write a native-v1 result.

The implementation must demonstrate one negative ordering or response-size
mutation in each adapter lane fails before restoring the expected fixture
sequence.  This validates the runner observes actual SIO traffic rather than
advancing an expected transcript unconditionally.

## Acceptance checklist

1. NetSIO and embedded AltirraSDL each route only `$7f` Q/W/P/R through
   `AtariSioNioFrontend` and the real core route, and both report the same
   canonical scenario IDs from an independent fixture projection.
2. The adapters preserve every production-endpoint native-v1 behavior: exact
   AUX and payload lengths, SIO checksums, `A`/`C`/`N`, a 512-byte bound, one
   outstanding response, wrong-R retention, interrupted-R consumption
   semantics, and reset-to-idle recovery.
3. `D1:`--`D8:` direct disk routing and Story 1.3's deterministic page-6
   boot remain passing.  Native traffic is additional evidence, never a
   replacement for the boot trace.
4. No native-v1 profile, test, report, or acceptance result can select `$71`,
   SLIP, padded reads, default transfer sizes, a FujiBus byte channel, or a
   legacy historical pass as evidence.
5. Each run retains stable-ID emulator/hub/NIO/POKEY evidence and labels its
   result virtual protocol/scheduling only.  It makes no physical-SIO claim.

Accepted-W polling timeout remains Story 2.1 client evidence.  The synchronous
production endpoint is not required to manufacture an externally observable
post-W `P(pending)` interval, and virtual reports must contain only states the
actual adapter observes.

## Verification

The exact target names are selected during implementation, but the completed
story must run the independent fixture validator, focused NetSIO and Altirra
adapter tests, the existing deterministic boot gate, complete relevant POSIX
CTest, and the embedded Altirra build.  The virtual integration command must
write evidence per scenario ID, not only a combined pass/fail summary.

```sh
source "$NIO_WORKSPACE/scripts/env.sh"
python3 -m unittest discover -s integration-tests/atari-sio/tests -v

# Focused adapter tests and complete POSIX CTest in repos/fujinet-nio.
# Existing page-6 D1 boot gate plus native virtual projection evidence.
./scripts/build.sh atari-boot-acceptance

# AltirraSDL embedded device build and its focused SIO device test target.
```

## Genuine implementation question

The current fixture matrix has literal vectors and recovery facts, but no
ordered, runnable virtual-adapter projection that pairs all recovery steps
with a stable report ID and required evidence fields.  The small reference-only
manifest above is therefore required.  It introduces no protocol choice and
needs no new wire fixture bytes.

The synchronous endpoint has no externally reachable *post-data*
`P(pending)` interval: after a valid W data frame it routes synchronously and
becomes ready; while it is receiving, SIO cannot begin P without the ingress
cancelling the incomplete W.  This is accepted.  Story 2.1 remains the
independent client proof for accepted-W polling timeout and P/R recovery;
virtual acceptance reports only endpoint states actually observed.  Do not add
asynchronous dispatch merely to manufacture a pending interval.

## Implementation status: NetSIO ingress

The first deliverable is complete in `repos/fujinet-nio`: the POSIX native
profile is now `TransportKind::None` plus an `AtariNetSioIngress` work source.
It owns the existing UDP/NetSIO lifecycle and feeds exact SIO command/data
frames to `AtariSioIngressRouter`, `AtariSioDiskFrontend`, and the production
`AtariSioNioFrontend(core.routingManager())`.  The former `$71`, W/R-only,
SLIP stream, default 768-byte read, and padded-output behavior is absent from
that adapter.

`tests/test_atari_netsio_ingress.cpp` drives the real NetSIO parser/adapter
with `nio_v1.json` literals and a real core route.  It proves Q/W/P/R payload
ordering and lengths, one dispatch, `$71` exclusion, rejected W, wrong-R
retention, and cold-reset-to-idle.  It is not a direct-frontend substitute.

Executed evidence for this increment:

```sh
python3 -m unittest discover -s integration-tests/atari-sio/tests -v
# 19 passed

cd repos/fujinet-nio
build/atari-fujibus-netsio-debug/tests/fujinet-nio-tests \
  --test-case='Atari NetSIO ingress*' --no-skip
# 2 cases, 88 assertions passed
ctest --test-dir build/atari-fujibus-netsio-debug --output-on-failure
# 3/3 passed
ctest --test-dir build/fujibus-pty-debug --output-on-failure
# 3/3 passed

cd ../..
python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --trace-serial --capture-dcb --explicit-cold-reset
# native and production-NetSIO page-6 NIO! boot passed
```

Altirra's embedded native device, the cross-adapter projection runner, and
Story 2.3 completion remain intentionally outstanding.

## Implementation status: embedded AltirraSDL adapter

The embedded `ATDeviceFujiNetNIO` now composes the production
`AtariSioNioFrontend(mCore.routingManager())` directly.  It constructs the
SIO-manager-validated five-byte command frame, receives literal W data plus
its checksum, and schedules only the endpoint result through Altirra's
existing ACK/NAK/COMPLETE/data queue.  The retired worker, FujiBus channel,
SLIP setup, `$71` alias, padded reads, default read size, and read retry loop
are absent.  `ColdReset()` and the embedded Fuji reset hook reset the endpoint
explicitly; a command abort only aborts an unfinished W.

`altirra-fujinet-nio-sio` compiles the production device and invokes its real
`IATDeviceSIO` callbacks with a recording Altirra scheduling interface.  It
loads the independent `nio_v1.json` vectors and proves the command/data
checksums, Q reply, `$71` exclusion, unsupported-command NAK, exact W data
length plus checksum, routing to the embedded real core, ready P response,
wrong-R retention, terminal-R payload lifetime, malformed-W rejection and
fresh-W recovery, and reset-to-idle.  Command-frame checksum rejection itself
remains correctly owned by Altirra's SIO manager before this callback boundary.

Executed evidence for this increment:

```sh
source "$NIO_WORKSPACE/scripts/env.sh"
python3 -m unittest discover -s integration-tests/atari-sio/tests -v
# 19 passed

cd repos/AltirraSDL
cmake -S . -B build/linux-debug -DALTIRRA_BUILD_TESTS=ON
cmake --build build/linux-debug --target altirra-fujinet-nio-sio-test -j2
ctest --test-dir build/linux-debug -R '^altirra-fujinet-nio-sio$' --output-on-failure
# 1/1 passed
cmake --build build/linux-debug --target AltirraSDL -j2
# passed
```

The cross-adapter projection runner and Story 2.3 completion remain
intentionally outstanding.

## Implementation status: virtual projection infrastructure

`integration-tests/atari-sio/fixtures/nio_v1.virtual.manifest.json` now
projects the independent native fixture IDs into ordered Q/W/P/R, rejection,
wrong-R, reset, recovery, capacity, and existing D1/page-6 boot groups. It is
reference-only: no packet literals are copied and client-only malformed-peer
or timeout observations are labelled rather than manufactured by the
synchronous endpoint. The stdlib validator rejects unknown or duplicate IDs,
missing observations, and any incomplete legacy-path exclusion.

`virtual_projection.py` is the shared result/evidence layer. Results are
adapter-scoped (`netsio` or `altirra-embedded`) and require the appropriate
logs, POKEY capture, screenshot, and inspection before a pass is possible.
The existing boot runner now optionally writes `boot-page6-config` through
that layer when invoked with `--write-projection-results`; its lifecycle and
diagnostics remain unchanged. Focused tests deliberately reverse an expected
operation order and corrupt manifest references/observations, confirming the
comparison or validator fails before restoring the canonical values.

Executed evidence for this increment:

```sh
source "$NIO_WORKSPACE/scripts/env.sh"
python3 -m unittest discover -s integration-tests/atari-sio/tests -v
# 24 passed

python3 integration-tests/atari-sio/run_boot_acceptance.py \
  --trace-serial --capture-dcb --explicit-cold-reset \
  --write-projection-results
# page-6 native + production-NetSIO boot passed; adapter=netsio,
# scenario_id=boot-page6-config, status=pass
```

Full native operation playback through each virtual adapter remains the next
Story 2.3 increment; Story 2.3 is not complete.

## Out of scope

Public `fn_*` Clock/File/Network/Disk guest-XEX acceptance, CIO `N:`/BASIC
acceptance, physical SIO timing/electrical tests, an Atari hardware run, a new
FujiBus service or core instance, disk protocol changes, and library changes
belong elsewhere.  Do not alter the supported legacy firmware family while
removing it from native-v1 acceptance.
