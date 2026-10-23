---
title: 'Deliver public-API Atari NIO guest acceptance'
feature: 'atari-nio-physical-sio'
story: '2.4'
type: 'feature'
created: '2026-10-23'
status: 'in-progress'
baseline_workspace_commit: '204887e1'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/SPEC.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md'
  - '_bmad-output/planning-artifacts/epics-atari-nio-physical-sio.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-1-3-boot-selected-configuration-or-mapped-atr-disk.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-2-1-implement-bounded-native-atari-nio-client-backend.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-2-2-serve-packet-native-nio-on-the-atari-sio-channel.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-2-3-establish-independent-virtual-atari-nio-parity.md'
---

# Story 2.4: Deliver public-API Atari NIO guest acceptance

## Intent and boundary

Add one cc65 acceptance XEX to the existing Atari configuration ATR.  It must
use the public `fujinet-nio-lib` surface—not SIOV, DCB addresses, `$7f`, or
application-owned Q/W/P/R framing—to prove Clock, File, Network, and Disk
service behavior from an Atari guest.

The completed Story 2.1 client owns transport recovery, Story 2.2 owns the
endpoint, and Story 2.3 owns virtual adapter conformance.  This story composes
those parts through the public API.  It does not add BASIC `N:` (Story 2.5),
change the synchronous endpoint to manufacture `P=pending`, create a boot
pipeline, or claim physical SIO proof.

`SPEC.md`, `wire-and-acceptance.md`, and the literal native-v1 fixtures remain
authoritative.  The existing `run_boot_acceptance.py` lifecycle/result and
evidence utilities are reused; the new guest result is a service-acceptance
record, not an alternative protocol oracle.

## Guest application and observable contract

`repos/nio-core-apps` owns a small noninteractive Atari XEX and adds it to the
existing `boot-disk/manifests/atari.yaml` configuration-ATR staging list.  It
links the published Atari archive through the normal cc65 application build;
generated XEX/ATR output remains untracked.  The manifest/image hash fixture
is deliberately updated only alongside a rebuilt, verified configuration ATR;
no second ATR builder or emulator launch route is introduced.

The XEX calls `fn_init()` once and writes a versioned result block at a stable
documented RAM address.  It contains a completion signature, per-operation
result codes, service byte/count checks, recovery-stage results, and a
monotonic execution marker.  The runner reads that block through the existing
bridge and rejects a pass unless every required stage succeeds.  It must not
link or define `SIOV`, DCB addresses, `$7f`, `Q`, `W`, `P`, or `R`; a focused
source/link-map guard enforces that the application layer contains none of
those symbols or literals.  Transport captures remain adapter evidence, not
the application's implementation.

Keep all guest buffers static.  Use short fixture URIs and data small enough
that every complete FujiBus packet remains within the established 512-byte
transport limit.  Disk uses a dedicated mounted writable 128-byte-sector
image (not D1, which remains the configuration ATR), and the XEX verifies
write, flush where required, and readback.  The link map and result block
must record enough free/static-memory information to make the cc65 RAM budget
reviewable; no multi-kilobyte `fn_disk_client_context_t` is placed on the C
stack.

## Required service scenarios

The runner starts a per-run deterministic **real** `FujinetCore` composition
for each adapter: production `ClockDevice`, `FileDevice`, `DiskDevice`, and
`NetworkDevice`, together with a temporary persistent filesystem and a
prebuilt writable disk image.  Network uses a deterministic protocol registry
behind the production `NetworkDevice`, rather than CURL, the Internet, or a
replacement FujiBus/NIO endpoint.  The service fixture records request counts
and durable backing bytes; it is not a Q/W/P/R peer.

| Guest stage | Public call surface and required observation |
| --- | --- |
| Clock | `fn_clock_get()` returns the configured deterministic valid time (including all eight cc65 time bytes). |
| File | A public File-service operation writes a fixed value to a `persist:` URI, then reads the same value after a new operation; the runner also verifies the per-run backing store. |
| Network | `fn_open()`, `fn_write()`, `fn_read()`, and `fn_close()` exchange a short fixed request/response with the real `NetworkDevice`. A service-level first-not-ready result may be retried by the documented API/application policy; every transport exchange still uses default `P` polling. |
| Disk | `fn_disk_info()`, `fn_disk_read_sector()`, `fn_disk_write_sector()`, `fn_disk_flush()`, and a readback prove the exact changed sector on the mounted non-D1 image. |

The runner captures native traffic and requires that ordinary public calls
contain W/P/R in the production endpoint path.  A synchronous core may report
READY on the first P; this is a valid observed outcome.  Story 2.1 remains the
evidence for client polling timeout/pending behavior and must not be relabelled
as a synchronous endpoint observation.

## Recovery scenarios

Use scoped, one-shot virtual SIO-boundary fault scripts, shared by the current
NetSIO and embedded Altirra runner paths.  They operate before/after the
production frontend as appropriate and never replace it or emulate Q/W/P/R:

1. Corrupt the first outgoing W command checksum before it reaches the
   frontend.  The frontend rejects it, the public call returns a transport
   error, the service dispatch count remains zero, and a distinct subsequent
   public call starts directly with W and succeeds.
2. Alter one observed READY length after the frontend has queued the response.
   The client emits a wrong terminal R, receives NAK while the real endpoint
   retains the original response, then its next public exchange performs the
   library's P/R recovery before a distinct new W.  The original application
   request is never replayed automatically.
3. Reuse the existing accepted-terminal-R delivery corruption at the Altirra
   SIO scheduling boundary and its NetSIO equivalent.  The service operation
   executes once, the guest receives failure, P subsequently reports idle,
   and only a distinct later public request succeeds.
4. Reuse the supported NetSIO reset and embedded `ColdReset()` controls after
   the first READY reply and before R.  The stale response is discarded; the
   failed public operation is not replayed, and a distinct later request
   proves idle recovery.

For the three uncertain cases use a side-effecting persistent File or Disk
write carrying a unique marker.  The runner verifies exactly one backend
operation and the marker's single durable effect before allowing the distinct
follow-up call.  This makes unsafe automatic application replay observable.

## Polling and optional PROC

Default polling is mandatory: capture the P exchange issued by normal public
calls and retain Story 2.1's assembled-client evidence for pending/deadline
recovery.  The guest may install/chains only an application-owned PROC handler
which calls `fn_atari_proc_notify()` and returns; it performs no SIO and owns
no library vector installation.  Foreground always confirms P before any R.

The completed endpoint currently returns Q feature flags zero, so it does not
advertise or emit an advisory PROC pulse.  Accordingly this XEX must report
the PROC subtest as `not-advertised` unless a real adapter/device advertises
bit 0; it must never fabricate a PENDING interval or synthetic endpoint pulse
to turn that into a pass.  Where bit 0 is genuinely available, the runner
records the application-owned notification, then independently confirms its
following P/R trace.  The existing Story 2.1 runtime test remains the required
proof that the latch itself is ISR-safe and SIO-free.

## Executable verification and evidence

Extend—not replace—`run_boot_acceptance.py`, its process lifecycle, bridge
inspection, screenshot, Altirra/POKEY diagnostics, NetSIO hub/NIO logs, and
adapter-scoped result schema.  Add stable service scenario IDs under the
existing virtual manifest/result authority.  Each result names exactly one of
`netsio` or `altirra-embedded`, requires genuine guest completion, result-block
checks, captured-wire validation, deterministic core/service counters, and all
required evidence paths.  Missing evidence is `incomplete`/failure.

Focused tests cover fixture validation, result decoding, source/link guards,
fault-script ordering, service backing-store checks, and corrupted/missing
guest result or wire evidence.  Run the guest suite through NetSIO and the
embedded Altirra device where the deterministic composition is supported, then
retain the Story 1.3 D1 page-6 boot regression.  Required gates include the
Atari library build/check after library API work, focused firmware and Altirra
tests, relevant CTests, the configuration-ATR build/inspection, and each live
adapter run.

## Genuine pre-implementation decisions

1. **File API (approved):** File acceptance uses the existing public
   `fn_raw_call()` with a small bounded test-local FileDevice payload helper.
   It does not add typed `fn_file_*` APIs, use `fuji_*appkey`, or implement
   SIO/FujiBus framing in the guest.
2. **PROC evidence (approved):** capability bit 0 is currently not advertised;
   the guest reports `not-advertised`.  A live pulse requires a real advertised
   capability, never a test-only fake.
3. **Deterministic services (approved):** the current Story 2.3 projection fixture is a
   single downstream `VirtualDevice`, not a Clock/File/Network/Disk service
   fixture.  Story 2.4 needs the real-core deterministic composition described
   above, shared by both adapter runners.  This is new test composition, not a
   new service or transport.

## Implemented increment: NetSIO public Clock acceptance

This increment implements only the Clock row over NetSIO. The configuration
ATR now stages `fnaccept.xex` through the existing Atari manifest. The XEX
links the published Atari `fujinet-nio-lib` archive and calls only `fn_init()`
and `fn_clock_get()`; it contains no guest SIOV/DCB/native-channel framing.
Its version-1 result block at `$0a00` records `ACP!`/`ACF!`, init and Clock
statuses, all eight `FN_TIME_T` bytes, and a two-byte heartbeat. The runner
rejects completion unless the heartbeat continues advancing after the
successful public call.

`fujinet-nio-atari-netsio-clock-acceptance` composes a real `FujinetCore`, its
production `ClockDevice`, production NetSIO ingress/router/frontend, and the
existing Altirra/NetSIO lifecycle. The only test control is the POSIX Clock
device's existing deterministic Unix-time hook, set to `$0102030405060708`.
The runner requires one real routed Clock request and captures native W/P/R
traffic; it compares the guest's returned bytes to literal
`08 07 06 05 04 03 02 01` rather than manufacturing a reply.

Live evidence: `test-evidence/atari-sio-public-api-clock-20261023-180818/`
records `ACP!`, init and Clock status `00`, the complete expected eight-byte
value, advancing heartbeats, and native command order `W/P/R`. The ordinary
D1 page-6 gate remains independently green at
`test-evidence/atari-sio-boot-20261023-180829/`. The configuration-ATR's
changed directory sector is pinned separately by the rebuilt literal
`disk_v1.json` source-image fixture.

The live XEX exposed a concrete library defect: Atari `fn_transport_init`
established its 512-byte baseline but returned the high capacity byte (`02`)
instead of `FN_OK`. The assembly now explicitly returns `FN_OK`, with an
additional actual-6502 soft65c02 assertion. This is a production correctness
fix, not guest-side accommodation.

The reviewed link map places loaded code/data at `$2400`–`$6429` and BSS at
`$642a`–`$7133`; the `$0a00` result block is outside all application and
library static storage. File, Network, Disk, recovery, PROC, and embedded
adapter acceptance remain deliberately unimplemented in this increment.

Verification performed:

- `make -C repos/fujinet-nio-lib test-atari-transport`, `make atari`, and
  complete `make check` (including the 123-case assembled Atari transport
  suite).
- `make -C repos/nio-core-apps -f makefiles/build.mk TARGET=atari boot-disk`.
- Firmware build target and full POSIX CTest in
  `repos/fujinet-nio/build/atari-fujibus-netsio-debug`.
- `python3 -m unittest discover -s integration-tests/atari-sio/tests -p
  'test_*.py'` (37 tests), live `--public-api-clock`, and the existing
  explicit-cold-reset D1 page-6 boot regression.

## Implemented increment: NetSIO public File persistence acceptance

The same `fnaccept.xex` now retains the Clock proof and adds a bounded,
test-local FileDevice application-payload helper. It uses the existing public
`fn_raw_call()` only for FileDevice `WriteFile` (`0x04`) and `ReadFile`
(`0x03`); it constructs neither FujiBus headers nor SIO/DCB/Q/W/P/R frames.
The short `persist:///fnaccept-v1.bin` URI and `ATARI-FILE-24` marker produce
48-byte Write and 35-byte Read application requests, well below the 512-byte
native packet bound.

Result-block version 2 preserves the original init/Clock status, complete
eight-byte Clock value, and heartbeat, then adds File transport/device status,
response length, transferred length, and exact readback verification. A pass
is `AFP!` at stage 5. The NetSIO acceptance runner creates a per-run POSIX
`host` filesystem using the production filesystem factory, registers it with
the real core `StorageManager`, and registers the production `FileDevice`.
It independently reads `fnaccept-v1.bin` after guest completion and rejects
anything other than the exact 13-byte marker.

Live evidence:
`test-evidence/atari-sio-public-api-clock-20261023-182619/` records Clock
`00`, File Write and Read transport/device status `00`, Write response length
10, Read response length 23, both transferred lengths 13, advancing guest
heartbeat, the persisted backing-file bytes, exactly one Clock dispatch, and
exactly two FileDevice dispatches in `WriteFile` then `ReadFile` order. The
captured native sequence is three ordered W/P/R exchanges (Clock, Write,
Read), all through the production NetSIO ingress/frontend/core route.

The revised link map places loaded code/data at `$2400`–`$6987` and BSS at
`$6988`–`$7711`; the stable `$0a00` result block remains outside library and
application static storage. The rebuilt configuration ATR changes only its
whole-image identity (`disk_v1.json` now pins
`53063f1b6118424fb6e0ca7a0e9920ada6bfd924b908c1a07c46349fce083eda`);
the independently pinned first four D1 sectors remain byte-identical.

Additional verification performed:

- Atari library archive build (`make atari`); no library source/API changed.
- Rebuilt configuration ATR and the 38-test Atari fixture/runner suite.
- Focused public Clock/File runner tests, full firmware POSIX CTest, live
  `--public-api-clock`, and the explicit-cold-reset D1 page-6 boot regression
  (`NIO!` for native and NetSIO; projection `pass`).

Network, Disk, recovery, PROC, and embedded-adapter acceptance remain outside
this focused increment and are still open.

## Acceptance criteria

1. A configuration-ATR cc65 XEX built from the normal pipeline proves Clock,
   persistent File write/read, Network open/write/read/close, and mounted Disk
   read/write through public `fn_*` APIs only.
2. Both practical virtual adapters independently produce guest/result/captured
   evidence; D1 boot and existing native-v1 adapter projections remain green.
3. Default P polling is observed without inventing endpoint pending behavior;
   PROC is conditional on an advertised real capability and remains
   application-owned/foreground-confirmed.
4. Rejected W, malformed-length R, interrupted terminal R, and reset prove
   safe subsequent exchange behavior, exact service-dispatch effects, and no
   automatic replay of an uncertain side-effecting application request.
5. No legacy `$71`, SLIP, padded reads, application SIO framing, alternate
   boot pipeline, or replacement core/endpoint can satisfy this story.

## Out of scope

Native BASIC `N:` installation/CIO behavior (Story 2.5), firmware endpoint or
library transport redesign, new public FujiBus services, physical SIO timing
or Atari hardware proof (Epic 3), and changes to D1--D8 disk ingress behavior.
