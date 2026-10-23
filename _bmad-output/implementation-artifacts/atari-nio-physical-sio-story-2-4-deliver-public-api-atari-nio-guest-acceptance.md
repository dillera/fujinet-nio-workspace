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
whole-image identity (the current `disk_v1.json` pin is maintained by each
accepted guest increment);
the independently pinned first four D1 sectors remain byte-identical.

Additional verification performed:

- Atari library archive build (`make atari`); no library source/API changed.
- Rebuilt configuration ATR and the 38-test Atari fixture/runner suite.
- Focused public Clock/File runner tests, full firmware POSIX CTest, live
  `--public-api-clock`, and the explicit-cold-reset D1 page-6 boot regression
  (`NIO!` for native and NetSIO; projection `pass`).

Network, Disk, recovery, PROC, and embedded-adapter acceptance remain outside
this focused increment and are still open.

## Implemented increment: NetSIO public Network acceptance

`fnaccept.xex` now preserves the Clock and durable File proofs and adds the
Network row through public `fn_open()`, `fn_write()`, `fn_read()`, and
`fn_close()` only.  The guest opens `fixture://nio-accept` with `POST`, writes
the bounded `NET-WRITE-24` marker, reads the independently defined
`NET-REPLY-24` response, checks the exact 12-byte counts and EOF flag, then
closes the returned handle.  It owns neither a FujiBus header nor any SIO/DCB
or Q/W/P/R framing.  The result block is version 3: `ANP!` at stage 9 records
all Network transport statuses, handle, write/read counts, read flags, reply
bytes, verification result, and the retained heartbeat alongside the existing
Clock/File fields.

The real-core NetSIO acceptance composition registers the production
`NetworkDevice` with its normal `ProtocolRegistry`.  Its only deterministic
test component is the small `fixture:` protocol implementation behind that
device—not a substitute device or protocol peer.  It accepts exactly the
fixture POST URL, records the exact write bytes, supplies the fixed reply, and
records `close()`.  The runner rejects the guest result unless it observes
four real NetworkDevice requests in Open/Write/Read/Close order, the fixture's
one exact 12-byte write, and its one close.  No service-level `NOT_READY`
condition is required by this deterministic backend; normal public-library P
polling remains unchanged.

The Network application payloads are 34 bytes (Open), 21 bytes (Write), 9
bytes (Read), and 3 bytes (Close), so their complete FujiBus packets including
the five-byte header remain below 512 bytes.  The rebuilt map puts loaded
code/data at `$2400`–`$8766` and BSS at `$8767`–`$951c`; the XEX's own BSS is
160 bytes, and the stable `$0a00` result block remains outside application and
library storage.

Live evidence:
`test-evidence/atari-sio-public-api-clock-20261023-184628/` records `ANP!`,
version `03`, stage `09`, the previous Clock/File successes, Network handle
`$0100`, all four Network public-call statuses `00`, exact 12-byte write and
read counts, EOF/verification flags, the literal reply bytes, advancing
heartbeats, and seven ordered W/P/R exchanges through production NetSIO.  The
firmware log records exactly one Clock dispatch, two File dispatches
(WriteFile then ReadFile), and four Network dispatches (Open, Write, Read,
Close), with the fixture's exact write and close evidence.  The existing D1
page-6 gate also remains green at
`test-evidence/atari-sio-boot-20261023-184246/`: native and NetSIO both reach
`NIO!`, and the boot projection result is `pass`.

Additional verification performed:

- Rebuilt the Atari archive, the XEX, and the configuration ATR; the later
  Disk increment repins the whole-image identity while retaining the
  independent D1 sector literals.
- Focused public acceptance checks plus the full 39-test Atari fixture/runner
  suite; the focused guard requires exactly seven ordered native W/P/R
  operations and rejects a reordered P.
- Full POSIX firmware CTest (3/3), live `--public-api-clock` Clock+File+
  Network acceptance, and the unchanged explicit-cold-reset D1 page-6 boot
  regression.

Disk, recovery, PROC, and embedded-adapter acceptance remain outside this
focused increment; Story 2.4 remains in progress.

## Implemented increment: NetSIO public DiskDevice sector acceptance

`fnaccept.xex` now preserves the Clock, durable File, and Network stages and
adds the public DiskDevice row using only `fn_disk_info()`,
`fn_disk_write_sector()`, `fn_disk_flush()`, and `fn_disk_read_sector()`.
The guest queries slot 2, requires a writable inserted 128-byte-sector image
with 16 sectors, writes a deterministic nonconstant 128-byte pattern to LBA
5, flushes it, reads it back, and checks every returned byte and both transfer
lengths.  The complete Disk application payloads are 2 bytes (Info), 136
bytes (Write), 2 bytes (Flush), and 8 bytes (Read); including the FujiBus
header, each remains within the 512-byte transport limit.  The guest neither
constructs FujiBus/SIO frames nor owns SIOV/DCB/Q/W/P/R.

The real-core NetSIO composition creates and mounts `/fnaccept-disk.atr`
through the production `DiskService` and `StorageManager` in DiskDevice's
zero-based slot 1 (guest-visible slot 2).  It is a fresh writable 16-sector,
128-byte ATR in the per-run storage root; D1 remains the configuration/boot
ATR and is never written.  The runner requires exactly four production
DiskDevice dispatches in Info (`5`), Write (`4`), Flush (`14`), Read (`3`)
order.  After guest completion it reads the backing ATR directly, verifies the
full LBA-5 pattern at the ATR-header-adjusted offset, and verifies both
adjacent sectors remain zero.

The result record is version 4 at `$0b00`, with success signature `ADP!` at
stage 13.  It retains the prior service results and heartbeat, then records
Disk Info status, flags, slot/type, 16-bit sector size, 32-bit sector count,
last service error, Write/Flush/Read statuses, both 16-bit transfer lengths,
and byte-for-byte verification.  The Disk linked archive needed more static
space than the previous XEX layout: `fnaccept` alone now starts at `$2000`
(all other Atari apps retain their normal start address), its result record is
at `$0b00`, and its static sector buffers occupy `$0b80` and `$0c00`.
The reviewed final map is STARTUP `$2000`--`$2062`, CODE `$206f`--`$9075`,
RODATA `$9076`--`$919a`, DATA `$919b`--`$91d7`, and BSS `$91d8`--`$9f8d`;
the transport context is at `$9d48`.  This keeps all observable and sector
buffers outside library/application static storage.  The cc65 Disk API also
reuses the library's synchronous packet buffers rather than allocating a
second 1 KiB request/reply pair; all other target backends retain their
existing storage and behavior.

Live evidence:
`test-evidence/atari-sio-public-api-clock-20261023-193125/` records `ADP!`,
version `04`, stage `0d`, complete successful Clock/File/Network results, Disk
slot `02`, sector size `128`, count `16`, all Disk statuses `00`, both lengths
`128`, verification `01`, advancing heartbeats, and eleven ordered native
W/P/R exchanges.  Its production firmware log contains the exact four
DiskDevice dispatches, and the retained per-run ATR has the full expected
LBA-5 pattern with LBA 4 and 6 unchanged.  The regenerated configuration ATR
is pinned in `disk_v1.json` as
`0d824da3bf8addf568af3224de73c89adb0e71eb679f7778c01264a22e751eb6`, while
the independently literal first four D1 sectors remain unchanged.

Verification performed:

- Complete `make -C repos/fujinet-nio-lib check`, including all configured
  library targets, public archive-link coverage, host wire tests, and the
  123-case assembled Atari transport suite.
- Rebuilt `fnaccept` and the existing configuration ATR with
  `make -C repos/nio-core-apps -f makefiles/build.mk TARGET=atari fnaccept
  boot-disk`.
- Full 40-test Atari fixture/runner suite, focused public acceptance runner,
  and the live `--public-api-clock` Clock+File+Network+Disk NetSIO run.
- POSIX firmware build plus full CTest (3/3); the existing explicit-cold-reset
  D1 page-6 boot regression is retained as a separate gate and passed at
  `test-evidence/atari-sio-boot-20261023-193150/` (`NIO!` for native and
  NetSIO, projection `pass`).

Recovery fault injection, conditional PROC evidence, and embedded-Altirra
public-service acceptance are deliberately still open; this increment does
not mark Story 2.4 complete.

## Implemented increment: NetSIO public rejected-W recovery

The public acceptance guest now records a bounded rejected-W branch without
replaying the side-effecting File write.  If its ordinary public
`fn_raw_call(FN_DEVICE_FILE, WriteFile, ...)` returns a transport error, it
records that status and issues one *distinct* public File write to
`persist:///fnaccept-recovered-v1.bin`, with the literal
`ATARI-FILE-RECOVERY-24` marker.  The following public File read targets that
new URI.  The application continues to own only documented FileDevice
application payload encoding; it does not construct FujiBus headers,
SIOV/DCB commands, or native Q/W/P/R frames.

The result record is version 5 and remains at `$0b00`.  It retains all
Clock/File/Network/Disk results and adds the original rejected transport
status, a recovery-attempt flag, recovery Write transport/device statuses,
response length and transferred count, and recovery verification flag.  A
normal run records no recovery attempt.  A faulted run must reach `ADP!` at
stage `$0e`, preserve the original error, and report the distinct Write and
Read as successful.

The live fault is a narrowly scoped NetSIO carrier relay, not a protocol
peer: it changes only the selected File-W command checksum while forwarding
the real guest, hub, production endpoint, and endpoint responses unchanged.
Atari OS may physically retry a failed command.  The relay therefore corrupts
each identical retry of that one logical W and requires a corresponding real
endpoint NAK for every observed retry; it becomes transparent at the first
different W.  It rejects evidence if a recovery P or R appears before that
distinct W.  The production log must show exactly two FileDevice dispatches
(the recovery Write then its Read), never a dispatch or backing file for the
rejected original URI.  The runner reads the real StorageManager backing
file and requires only the recovery marker.

The enlarged guest image also uncovered an actual display-list corruption:
the earlier `$2000` placement allowed its BSS/library state to reach RAM
scanned by the default Atari OS display list.  `fnaccept` alone now starts at
`$1d00`; the reviewed link map is STARTUP `$1d00`--`$1d62`, CODE
`$1d6f`--`$8fdc`, RODATA `$8fdd`--`$9141`, DATA `$9142`--`$917e`, and BSS
`$917f`--`$9f54` (transport context `$9d0f`).  It is intentionally a headless
acceptance XEX and disables ANTIC display DMA before public packet buffers are
touched.  Normal and fault screenshots are consequently clean black frames,
not corrupted display lists.  The generated configuration ATR whole-image pin
is now `afd9cb3290dcdf291c47e9d7da586a1624951827fd3e4aa1e933c939340bdb4a`;
the independent literal D1 boot sectors remain unchanged.

Live evidence:

- `test-evidence/atari-sio-public-api-clock-20261023-202532/` records the
  unaffected normal version-5 Clock/File/Network/Disk run: `ADP!`, stage
  `$0e`, eleven ordered W/P/R exchanges, and a clean headless screenshot.
- `test-evidence/atari-sio-public-api-rejected-w-recovery-20261023-202553/`
  records the faulted run: `ADP!`, original File transport status `$10`,
  recovery-attempt `$01`, successful distinct 22-byte Write/Read, no original
  backing file, and the exact recovery marker in the independently inspected
  backing file.  Its relay evidence records 56 observed physical malformed-W
  retry/real-NAK pairs for that one run, no P/R before the distinct recovery
  W, and transparent subsequent W/P/R exchanges.  The observed retry count is
  evidence, not a prescribed contract value.

Verification performed:

- Focused public acceptance guards (including checksum-mutation/NAK-count and
  direct-new-W negative checks) and the complete 41-test Atari fixture/runner
  suite.
- Rebuilt the Atari XEX/configuration ATR; full POSIX NetSIO firmware CTest
  passed (3/3).
- Live normal `--public-api-clock` and faulted
  `--public-api-rejected-w-recovery` runs through the production endpoint,
  plus the explicit-cold-reset D1 page-6 boot regression at
  `test-evidence/atari-sio-boot-20261023-202642/` (`NIO!` for native and
  NetSIO).

Malformed/wrong-length R, accepted-but-interrupted R, device-reset recovery,
conditional PROC, and embedded-Altirra public-service acceptance remain open;
this increment does not mark Story 2.4 complete.

## Memory-layout investigation and hardening

This focused hardening pass pauses further Story 2.4 feature work.  It reviews
the generated `fnaccept.map`, `fnaccept.lbl`, C listing, linker configuration,
and live guest state rather than inferring safety from the linker ceiling.

### Measured layout

The accepted `fnaccept` link is deliberately separate from ordinary Atari
utilities and starts at `$0d00`, immediately above the fixed result/disk
windows.  The generated map reports these exact half-open ranges:

| Region | Range | Bytes |
| --- | --- | ---: |
| zero page | `$0082`--`$009c` | 26 |
| STARTUP | `$0d00`--`$0d63` | 99 |
| LOWBSS / LOWCODE / INIT | absent | 0 / 0 / 0 |
| CODE | `$0d6f`--`$565e` | 18,671 |
| RODATA | `$565e`--`$570f` | 177 |
| DATA | `$570f`--`$5740` | 49 |
| BSS | `$5740`--`$5ee2` | 1,954 |

The XEX is 19,020 bytes on disk; its contiguous loaded span is 19,008 bytes
and loaded-plus-BSS footprint is 20,962 bytes.  The `cc65-atari-nio.cfg`
reserves 2,048 C-stack bytes.  In the measured configuration this stack is
`$941f`--`$9c1f`, leaving a 13,629-byte no-heap gap between BSS and the stack
floor.  `fnaccept` and its selected archive members do not link `malloc` or
use a dynamic heap; the gap is a guard, not an advertised allocation surface.

The result record remains `$0b00`--`$0b80`; its two fixed 128-byte Disk API
buffers are `$0b80`--`$0c00` and `$0c00`--`$0c80`.  All are above the measured
MEMLO and below the XEX start.  The app's ordinary static buffers are 96-byte
File request, 64-byte File reply, and 32-byte Network reply.  Disk's two
sector buffers are the fixed 128-byte windows, not BSS.

The dominant linked contributors are the acceptance application (5,023 CODE,
154 RODATA, 192 BSS), public-library `fn_disk.o` (2,708 CODE), `fn_rw.o`
(1,505 CODE), `fn_state.o` (1,217 BSS plus 267 CODE), `fn_open.o` (1,255
CODE), and Atari `fn_transport.o` (528 BSS plus 563 CODE).  The selected
library totals 12,523 CODE, 23 RODATA, 8 DATA, and 1,757 BSS; cc65 runtime
totals 1,125 CODE, 41 DATA, and 5 BSS.  The shared library state is exactly
two 512-byte packet buffers, 28 bytes of sessions, 128-byte TCP URL scratch,
10-byte transport context, 27-byte parse context, and the transport's
512-byte recovery discard buffer plus 16 control bytes.  No duplicate packet
pair was found.

The largest storage symbols are therefore `_fn_req_buf` at `$581c` and
`_fn_resp_buf` at `$5a1c` (512 bytes each), the transport discard buffer
(512 bytes within its `$5ccd`--`$5edd` allocation), `_fn_tcp_url` at `$5c1c`
(128 bytes), and the application File request/reply/Network reply block at
`$5740`--`$5800` (96/64/32 bytes).  The public Disk transfer windows are the
separate `$0b80` and `$0c00` fixed addresses.  Code is dominated by the
acceptance application's `_main` module and the selected Disk/Read-Write/Open
library modules listed above; cc65's `start`, `zerobss`, stack helpers and
copy/string routines together account for the 1,125-byte runtime total.

One concrete excess was found and removed: the generic app rule had linked
the unused interactive `fnsvc.o` and `fnctl.o` into `fnaccept`, adding 6,462
bytes of code and 1,588 BSS bytes.  The acceptance guest
uses public `fujinet-nio-lib` calls directly, so its narrow link now excludes
only those two helpers while leaving every other application unchanged.

### Runtime proof and collision result

The guest records a versioned memory snapshot in its existing result block
before any service operation, DMA modification, or intentional memory
relocation.  Live normal and rejected-W runs report MEMLO `$0700`, MEMTOP
`$9c1f`, RAMTOP `$a0`, SDLSTL `$9c20`, SAVMSC `$9c40`, SDMCTL `$22`, and
DMACTL `$ff`.  Thus the default 32-byte display list is `$9c20`--`$9c40` and
the 960-byte Graphics-0 screen is `$9c40`--`$a000`; neither overlaps the
linked image ending `$5ee2`.  The stack's last address is immediately below
the display list, as the Atari OS memory map intends.

This disproved the prior `$1d00`/headless rationale: its BSS reached `$9f97`
while the real guest's MEMTOP was only `$9c1f`, so it overlapped both active
display memory and the C stack.  Disabling ANTIC in `main()` was also too late
to protect cc65's pre-main BSS clear.  The accepted fix is not a cosmetic
display restoration: it restores the documented OS reservation layout, makes
no DMA writes, and preserves the normal empty Graphics-0 screen without
reopening `E:`.

`integration-tests/atari-sio/fnaccept_memory_layout.py` is the executable
map gate.  It rejects a start/range outside the approved regions, zero-page
escape, BSS/stack collision, inadequate guard gap, result/disk window
collision, or accidental `fnsvc`/`fnctl` linkage.  The live runner additionally
rejects missing/changed pre-service snapshot data or any linked overlap with
the active display list/screen.  Its focused unittest has negative snapshot
mutations for both an unproven transition and a stack collision.

Evidence and verification:

- `test-evidence/atari-sio-public-api-clock-20261023-210551/` and
  `test-evidence/atari-sio-public-api-rejected-w-recovery-20261023-210600/`
  show `ADP!`, the same measured safe memory map, preserved normal and
  rejected-W semantics, and stable Graphics-0 screenshots.
- Rebuilt the Atari XEX/configuration ATR and ran the layout gate, focused
  public/memory tests, and the full 43-test Atari fixture/runner suite.
- Complete `repos/fujinet-nio-lib make check` passed, including assembled
  Atari transport execution coverage; the D1 page-6 regression at
  `test-evidence/atari-sio-boot-20261023-210020/` reaches `NIO!` through both
  native and NetSIO paths.

The new configuration-ATR whole-image pin is
`939d3c38cbca3d4db706a6ef109d84229a7103a192135b11075efb476ee8b85b`;
the independent literal D1 boot sectors remain unchanged.  Story 2.4 remains
open and no further feature/recovery scenario was added by this hardening pass.

## Malformed READY-length terminal-R recovery

This increment closes the malformed/wrong-length terminal-R item only.  The
public guest remains public-API-only: its initial `fn_raw_call()` File Write is
accepted by the production endpoint, then a one-shot NetSIO carrier relay
changes the *delivered* READY P length from 17 to 16 and recomputes that P
packet's SIO checksum.  It neither implements a peer nor alters the frontend.
The guest consequently uses the altered length for R; every physical OS retry
receives a real endpoint NAK.  Its public call returns `FN_ERR_TRANSPORT`
`($10)` and it makes one distinct File Write/Read call.  The native transport
first performs P(READY, 17) and R(17) to drain the retained original reply,
then sends the new W.  It does not replay the accepted side-effecting request.

The live run uncovered and corrected a concrete common-library defect:
`fn_raw_call()` used to replay all non-timeout exchange errors, including an
Atari terminal-R transport failure.  It now retries only `FN_ERR_IO` short or
corrupt FujiBus bodies.  The new host `raw_transport_retry_test` proves both
that transport errors issue exactly one exchange and that the intentional
short-body retry remains one retry.  This shared correction preserves the
Atari recovery contract and is built for every supported library target.

The version-6 result block records the initial failure status and recovery
kind alongside the established service results.  The relay evidence records
the literal five-byte command frames, both complete File W raw packets and SIO
checksums, original/delivered P bytes and checksums, each wrong-R/NAK physical
pair, retained P bytes/checksum, and the complete recovery-R raw packet and
checksum before the first distinct W.  Its validator compares both W packets
to independent File payload literals and verifies each DCB AUX against the
captured packet length.  It rejects stale retained P bytes, an altered NAK, a
wrong R AUX, a bad raw packet/checksum, a missing drain, or a W that precedes
recovery R.  The focused unit test deliberately changes recovery order,
retained P bytes, and NAK and requires failure.

Live evidence:

- `test-evidence/atari-sio-public-api-malformed-r-recovery-20261023-214820/`
  records `ADP!`, one initial File write dispatch, 28 observed physical
  wrong-R/real-NAK pairs (an observed OS retry count, not a requirement), a
  retained P of `02 11 00`, recovery R AUX `$0011`, then a distinct File W.
  The production trace contains exactly three FileDevice dispatches in
  Write/Write/Read order.  The independently inspected backing store contains
  the original marker once and the distinct recovery marker once.
- `test-evidence/atari-sio-public-api-clock-20261023-214233/` and
  `test-evidence/atari-sio-public-api-rejected-w-recovery-20261023-214242/`
  retain the normal and rejected-W `ADP!` acceptance paths with the same
  memory-layout gate and Graphics-0 display.
- `test-evidence/atari-sio-boot-20261023-214326/` records the preserved D1
  page-6 `NIO!` native and production-NetSIO boot gate.

Verification performed: rebuilt the library/Atari archive and configuration
ATR; ran all 45 Atari fixture/runner tests; ran all three live public-API
paths; ran the D1 boot gate; and ran complete `repos/fujinet-nio-lib make
check`, including all 123 assembled soft65c02 transport assertions and the
new raw retry guard.  Accepted-but-interrupted R, reset, conditional PROC, and
embedded-Altirra public-service acceptance remain open.  Story 2.4 is not
complete.

## Generic raw-call replay hardening

The first no-replay correction stopped `FN_ERR_TRANSPORT` replay.  A follow-up
audit found that the generic `fn_raw_call()` still replayed the entire request
once for `FN_ERR_IO`.  That error is not evidence that the device rejected W:
it is produced after a completed exchange for a short/truncated reply,
wrong response device/command, checksum failure, or caller response-capacity
failure.  Packet parsing can additionally return `FN_ERR_INVALID` for a
malformed declared length.  Each outcome is ambiguous for a side-effecting
operation, so the generic API now performs exactly one exchange and returns
the observed error without replaying the application request.

`tests/raw_transport_retry_test.c` now proves exactly one exchange for
transport error, truncated reply, malformed length, mismatched identity,
checksum-corrupt packet, and insufficient caller capacity, plus one exchange
for a valid successful response.  This is common code and was compiled under
the full all-target library check; it introduces no API or ABI change.  The
packet-native Atari transport still owns outstanding-response draining before
a later distinct public call.

Fresh live evidence retains all public acceptance behavior:

- `test-evidence/atari-sio-public-api-malformed-r-recovery-20261023-220309/`
  proves the retained response is drained before the distinct File write.
- `test-evidence/atari-sio-public-api-rejected-w-recovery-20261023-220319/`
  proves a rejected W starts its distinct operation directly.
- `test-evidence/atari-sio-public-api-clock-20261023-220328/` preserves normal
  Clock/File/Network/Disk acceptance.
- `test-evidence/atari-sio-boot-20261023-220700/` freshly preserves the D1
  page-6 `NIO!` native and production-NetSIO boot gate with the rebuilt ATR.

The configuration ATR pin above reflects this library change.  The fixture
validator, focused public runner tests, fresh live public paths, fresh D1 boot
gate, and complete all-target `repos/fujinet-nio-lib make check` pass.
Interrupted-R, reset, PROC, and embedded public-service acceptance remain
deliberately out of scope.

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
