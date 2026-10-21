---
title: 'Boot the selected configuration or mapped ATR disk'
type: 'feature'
created: '2026-10-20'
status: 'in-progress'
baseline_commit: '6756149d4f56743dbb9a98fce43dfd63ef79ec59'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/SPEC.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-epic-1-context.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-1-1-freeze-atr-disk-conformance-fixtures.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-1-2-serve-standard-atr-drives-through-diskservice.md'
---

# Story 1.3: Boot the selected configuration or mapped ATR disk

As an Atari operator,
I want config mode to boot the supplied configuration ATR and normal mode to boot my chosen mapped drive,
So that FujiNet-NIO is usable as the machine's only disk peripheral.

## Intent

Finish Epic 1 at the boot-policy and evidence seam.  Story 1.2 already supplies
the sole ESP32 CMD/UART/GPIO ingress and its direct `DiskService` disk frontend;
this story must not alter that architecture.  It makes boot projection
deterministic across restart, packages the existing Atari boot medium through its
current build/install pipeline, and proves a real Atari OS boot and launch in a
virtual SIO run rather than treating fixture-sector reads as boot evidence.

The normative wire and disk requirements remain the canonical SPEC, wire-and-
acceptance contract, and Story 1.1 fixture contract.  This story adds no SIO
command, geometry, status mapping, NIO `0x7F` behavior, or physical acceptance
criterion.

## Confirmed current state and approved boot precedence

- `main_esp32.cpp` and `main_posix.cpp` register `DiskDevice`, restore persisted
  runtime mounts, and conditionally call `apply_boot_mount()` for unit zero.
  `DiskDevice::restore_runtime_mounts()` restores every persisted slot as a
  pending `DiskService` mount, so Atari `D1:`--`D8:` remain slots 0--7.
- `apply_boot_mount()` correctly stages a config URI lazily (including a network
  filesystem) and `AtariSioDiskFrontend` activates it on the first real disk
  data operation.  `STATUS` remains non-mounting as established by Story 1.1.
- **Previous behavior (superseded):** bootstrap restored persisted mappings, then, in config
  mode, stages `boot.config_uri` only when restored slot 0 is absent.  A
  persisted user `D1:` therefore wins today; config mode supplies the ATR only
  when D1 was not restored.  Normal mode never stages `boot.config_uri`.
  Restored `D2:`--`D8:` are not replaced by the config projection.
- **Approved policy:** in config mode `boot.config_uri` temporarily overlays
  active D1 regardless of a persisted user D1.  The overlay is never written to
  runtime-mount persistence.  Normal mode restores the saved user D1 on the
  next cold start; D2--D8 remain restored and unchanged in either mode.  A
  missing or failed configuration ATR is reported as a config-boot failure and
  must never silently fall back to the persisted D1.
- `configure_boot_mount()` only records the `DiskDevice` RestoreBoot setting; it
  does not set a `DiskService` mount.  Keep that API for its existing FujiBus
  RestoreBoot callers, but do not mistake it for bootstrap projection.  Make the
  restore-then-project ordering explicit so a future refactor cannot reverse it.
- The packaged input already exists: `make TARGET=atari boot-disk` stages
  `fhost.xex`, `fls.xex`, `fin.xex`, `fmount.xex`, `fdrive.xex`, and `fapp.xex`
  from `boot-disk/manifests/atari.yaml`, builds the pinned MyPicoDOS
  `picobootcode-dd.bin`, then uses `dir2atr -m -D -B` to make
  `build/atari/disk/boot/autorun.atr`.
  `install-boot-disk` copies that same image to both firmware boot-asset roots.
  Reuse this pipeline; do not create another ATR builder or commit generated ATRs.

The existing bundle is a current utility/configuration bundle, not the Epic 2
public-API NIO acceptance XEX and not a general-purpose DOS claim.  Story 2.4
owns the Clock/Network/File/Disk/recovery/BASIC guest acceptance application;
Story 2.2 owns the native endpoint it needs.  This story may launch a present
bundle program solely to prove that the packaged ATR reaches an Atari launch
point, but must not make an Epic 2 service assertion.

## Atari boot/launch contract for this story

The generated golden currently has SHA-256
`8f1cd8f689936ab5c94def50176ecab721f78a739e9aa117b0908c8b255c24f4`.
Its sector 1 header is `00 03 00 08`: standard boot flags, three 128-byte boot
sectors, and load address `$0800`.  Atari OS must issue standard `D1:` READ
command frames (`0x31, 0x52`) for one-based sectors 1, 2, and 3, each with a
128-byte data transfer and its data checksum.  The boot loader's subsequent
directory/file reads are image- and PicoBoot-dependent; record them from the
actual run rather than inventing a fixed list.  Every recorded exchange must be
a Story 1.1-supported D1--D8 command with its observed transfer length and
terminal phase.  A successful trace ends at an observable launch sentinel from
the bundled program (or the emulator's documented program-entry state), not at
the first three sector replies.

The evidence fixture records: boot-image SHA-256, PicoBoot artifact identity,
manifest digest/list, emulator and bridge revisions, generated firmware config,
ordered command/reply trace, and launch sentinel.  It must assert the initial
three reads exactly and validate all later trace rows against the literal disk
matrix.  Rebuilding the image and rerunning the same virtual lane must reproduce
the trace fixture or deliberately update it with the image hash/manifest change.

## Boundaries

**Always:** use the `DiskDevice`-owned shared `DiskService`; keep
`AtariSioIngress` the only ESP32 CMD/UART/GPIO owner; retain direct D1--D8 disk
dispatch; use the existing boot-disk build/install targets; test cold-start
persistence (not an in-memory continuation); and label virtual evidence as
virtual protocol/boot evidence only.

**Never:** create a second `DiskService`; route disk boot through `DiskDevice`,
FujiBus, `Channel`, `ITransport`, SLIP, or `LegacyTransport`; add/enable native
`0x7F`; change the Story 1.1 fixture protocol; add Epic 2 guest acceptance;
claim an electrical, UART-timing, or real-Atari pass; or modify Amiga artifacts.

**Ask first:** a different boot image format/PicoBoot, new disk commands, or a
request to make a physical boot claim.

## Implementation plan

### 1. Make projection order a tested bootstrap operation

- `repos/fujinet-nio/include/fujinet/fs/boot_mount.h` and
  `src/lib/boot_mount.cpp` gain the smallest testable bootstrap-projection
  helper (or equivalent narrowly scoped `DiskDevice` helper).  It restores the
  persisted map, then overlays active D1 in config mode without mutating the
  persisted map, and reports the selected projection.  It must not duplicate
  `DiskService` mounting logic.
- `repos/fujinet-nio/src/app/main_esp32.cpp` and `src/app/main_posix.cpp`: use
  that one ordering.  Continue calling `configure_boot_mount()` only to retain
  RestoreBoot API configuration; it must not influence D1 projection order.
- `repos/fujinet-nio/tests/test_boot_mount.cpp` (and a focused
  `DiskDevice`-persistence test if required): prove two fresh service/device
  instances against persisted runtime-mount data:
  1. config mode, no restored D1 -> pending read-only `boot.config_uri` at slot
     0, with restored D2--D8 unchanged;
  2. normal mode -> restored D1--D8 only, no config URI staged;
  3. config mode with restored D1 -> the config URI temporarily overlays active
     D1 while persisted user URI/mode remains unchanged; D2--D8 remain isolated
     and a normal-mode restart restores the saved D1;
  4. missing/empty config URI and failed lazy mount report config-boot failure,
     do not fall back to the persisted D1, and do not corrupt restored slots.

### 2. Keep the build image authoritative and verify its contents

- `repos/nio-core-apps/boot-disk/manifests/atari.yaml` needs no speculative
  acceptance-XEX addition.  Add a focused manifest/image inspection test only
  if the current build cannot assert all required current entries and the
  PicoBoot boot header.  Keep the manifest as the source of the list.
- Rebuild with `make TARGET=atari boot-disk`, verify the ATR header, hash, and
  staged filenames, then use `make TARGET=atari install-boot-disk` so the exact
  generated `autorun.atr` becomes the ESP32 flash asset at
  `repos/fujinet-nio/distfiles/esp32-data/boot/atari/autorun.atr`.
- Do not add a separate image copy to tests.  The existing Story 1.1 source-
  image metadata is the golden-input seam; update it only when an intentional
  manifest/PicoBoot/image revision changes and then refresh the trace evidence.

### 3. Add an executable virtual boot lane and trace oracle

- Refactor only the standard-D1--D8 disk seam in
  `repos/fujinet-nio/src/platform/posix/atari_netsio_fujibus_channel.cpp` and
  its factory/header wiring so D1--D8 requests use `AtariSioDiskFrontend` over
  the same shared `DiskService` state.  The current POSIX NetSIO/Altirra custom
  device implements a legacy FujiBus wrapper/`0x71` channel and cannot itself
  prove this story.  Leave it untouched and outside the new disk test lane;
  neither revive it nor implement/migrate `0x7F` here.  The adapter is a
  portable-frontend consumer, deliberately reusable by Story 2.3 rather than
  a Story 2.3 conformance framework.
- Add `configs/atari/profiles/atari-nio-config-boot.yaml` plus a focused
  `integration-tests/atari-sio/tests/test_virtual_config_boot.py` runner.  It
  boots the installed `autorun.atr` through the NetSIO bridge with
  `sio_patch: false` and `accurate_disk: true`, using the existing
  `scripts/atari-run` profile renderer and Altirra Bridge control API rather
  than a second emulator runner.
- Add the trace capture/oracle beside that runner (for example,
  `integration-tests/atari-sio/fixtures/boot_v1_trace.json`) and a focused
  `repos/fujinet-nio/tests/test_atari_netsio_disk_boot.cpp` host test for the
  adapter.  They record full command bytes, reply control phases, payload
  length/checksum result, and stable scenario IDs.  The virtual test asserts the
  sector-1--3 bootstrap exchange, then runs through the packaged loader to its
  launch sentinel.  It rejects a trace that stops after fixture sectors, uses
  unsupported SIO commands, reaches legacy `0x71`, or uses `0x7F`.
- Run the same fixture-driven virtual endpoint for config/no-restored-D1,
  normal/restored-D1, and restored D1--D8 cases.  For the latter, give each ATR
  a unique sector signature and prove a D1 read cannot return D2--D8 data,
  then restart the sidecar/config directory and prove the mapping again.

## Acceptance criteria

1. Given config mode, valid installed `boot.config_uri`, and no restored D1,
   when a cold virtual Atari starts, then D1 lazily mounts the packaged ATR and
   the OS completes its actual PicoBoot path and reaches the launch sentinel;
   the stored trace contains initial READ sectors 1, 2, and 3 with 128-byte
   transfers and all later observed exchanges are valid v1 disk exchanges.
2. Given normal mode and persisted mappings for D1--D8, when a cold virtual
   Atari starts and applications address each unit, then each uses its matching
   restored `DiskService` slot, distinctive test data proves isolation, and a
   restart reproduces the mapping.
3. Given config mode and a persisted D1, when bootstrap runs, then
   `boot.config_uri` overlays active D1 without altering saved runtime-mount
   data.  D2--D8 remain unchanged, and a normal-mode restart restores the saved
   D1 URI and access mode.  A missing or failed config ATR reports failure and
   never falls back to persisted D1.
4. Given the supported environment, when the existing core-apps boot-disk and
   install targets run, then the installed firmware asset is byte-identical to
   the generated ATR and the trace evidence records its hash and staged manifest
   contents.
5. Given the virtual lane passes, its report explicitly says it does not prove
   ESP32 UART/GPIO timings, open-drain idle behavior, cable contention, or a
   real Atari boot.  Those are Epic 3 gates.  A clean classic-ESP32 Atari v1
   Debug/Release build links successfully; build success is still not physical
   acceptance.

## Verification

Source the workspace environment first.  The implementation must record each
actual result and its trace artifact in the story's implementation evidence.

```sh
source "$NIO_WORKSPACE/scripts/env.sh"
python3 -m unittest discover -s integration-tests/atari-sio/tests -v

cd repos/nio-core-apps && make TARGET=atari boot-disk && make TARGET=atari install-boot-disk

cd ../fujinet-nio && ./build.sh -cp fujibus-pty-debug && \
  ctest --test-dir build/fujibus-pty-debug -R 'fujinet-nio-tests|atari.*boot' --output-on-failure

./build.sh -cb

cd ../.. && ./scripts/atari-run altirra --profile configs/atari/profiles/atari-nio-config-boot.yaml
```

The final command becomes the executable virtual boot gate only after its
profile, trace capture, launch sentinel, and required Altirra/bridge inputs are
implemented.  If the licensed ROMs, `AltirraSDL`, bridge checkout, `dir2atr`,
or cc65 toolchain are unavailable, report that exact dependency as an
environment blocker; do not replace this with sector-fixture success.  Run the
classic ESP32 `./build.sh -cb` after touching ESP32 bootstrap files; its clean
Debug build is currently 124,283 of 131,072 IRAM bytes.  Do not report a
compile/link result as physical acceptance.

## Dependencies and blockers

Depends on completed Stories 1.1 and 1.2.  It does not depend on Story 2.2 or
2.4 for disk boot; it must specifically avoid their native endpoint and guest
acceptance scope.  The current virtual sidecar is a genuine implementation gap
because it is legacy-channel based; the scoped D1--D8 portable-frontend adapter
and trace capture above are required before the story can claim a virtual Atari
boot.  There are no remaining policy blockers.

## Implementation evidence

### AltirraSDL upstream refresh — 2026-10-20

- Preserved local NIO range before integration:
  `d2dc14a1f80cc4cc469f603e5134540633c5e643..23ac3b1de1e94e156b7023963acd962c8f876492`.
  Safety branch: `safety/story-1.3-pre-upstream-rebase-23ac3b1d`.
- Rebased the four NIO commits onto `upstream/main` at
  `fed78544` without conflicts.  `git range-diff` records the one-to-one
  mapping: `bc797515..23ac3b1d` to `addd3638..b5daac48`.
- The current shared NIO headers required a small post-rebase compatibility
  commit, `0bbfa6b6`: use `TransportKind::FujiBusSlip` and pass
  `config.translation` to `register_network_device`.  This is independent of
  the production NetSIO D1--D8 frontend and native-endpoint scope.
- `source "$NIO_WORKSPACE/scripts/env.sh" && cd repos/AltirraSDL &&
  ./build.sh --debug` passed after that compatibility adjustment.  The initial
  failure was only the above stale embedded-device API, not an upstream raw-SIO
  regression.
- Identical config-mode virtual run used the rebuilt binary, the existing
  `atari-nio-config-boot.yaml`, generated `autorun.atr`, NIO NetSIO frontend,
  and hub.  Trace logs:
  `/tmp/atari-story13-run/nio-20261020-173248-upstream.log` and
  `/tmp/atari-story13-run/hub-20261020-173248-upstream.log`.
  It again reads sectors 1--3, then repeats D1 sector 361
  (`31 52 69 01 ED`) after every dispatched 256-byte `DATA_BLOCK`; it later
  retries sector 4.  Thus upstream refresh did not resolve the 256-byte
  custom-device failure and does not constitute launch evidence.
- Deterministic bridge breakpoints captured the boot-sector DCB at `$0300`:
  `31 01 52 40 00 04 07 00 80 00 01 00` (and sectors 2/3), proving a standard
  D1 read with `DBYT=$0080` for the Atari OS boot sectors.  At the actual
  PicoBoot sector-361 SIOV entry (`$E459`), the DCB is
  `31 01 52 40 00 07 07 00 80 00 69 01`: D1 READ, sector 361, and again
  `DBYT=$0080`.  The call returns to `$0832` with `Y=$8F`, carry set, and
  `DSTATS=$8F`, after the production frontend correctly dispatched the ATR's
  256-byte sector.  This is the concrete guest-side failure, not a bridge
  credit/READY or upstream scheduling regression.
- The workspace submodule pointer remains unchanged pending a passing virtual
  launch gate.  A named stash retains only generated AltirraBridge Python
  bytecode caches from the earlier probe; it contains no source or settings.

### Source-built DD PicoBoot and virtual launch — 2026-10-20

- `repos/MyPicoDOS` is pinned at `933c1040` on
  `feature/story-1.3-dd-bootq`.  Its unmodified `bootq` source builds with
  ATASM 1.30 to the published FujiNet `picoboot.bin` byte-for-byte
  (`6850ad99d911556fd640e1aca846ec6847218ffc9baf71aab4457e42bf0a5f99`).
  The DD target changes only the first boot byte from `$80` to `$00`, retaining
  the existing autorun and linked-XEX loader.
- `make TARGET=atari boot-disk install-boot-disk` in `repos/nio-core-apps`
  builds `picobootcode-dd.bin` through the pinned submodule and generated the
  above `autorun.atr` hash; both POSIX and ESP32 firmware asset copies matched.
- Native Altirra control (no NIO, hub, or custom device) and the production
  NIO/NetSIO lane both reached the FAPP launch sentinel `PC=$5060`.  The common
  DCB trace is standard D1 STATUS, READ 1--3 with `DBYT=$0080`, then READ 361
  with `DBYT=$0100`, followed by linked file sectors 4, 5, 6, 7, and 8.  The
  virtual run continued through sector 98 before the same launch breakpoint.
  Trace logs: `/tmp/story13-native-altirra.log` and
  `/tmp/atari-story13-run/source-dd-netsio.log`.
- This is virtual protocol/boot evidence only; it proves neither ESP32
  electrical/timing behavior nor a real-Atari boot.

### Superseded launch interpretation — 2026-10-20

The prior `$5060` breakpoint was subsequently shown to be insufficient: XL
Self Test can execute that address before FAPP is loaded. It is retained as
investigation history only, not launch acceptance. Story 1.3 remains in
progress until the executable virtual test observes the FAPP bytes at `$5060`,
actual D1 traffic through the production frontend, and continued application
execution.

### Prior verification record — 2026-10-20

- The controlled reference found no post-loader transport divergence. With the
  identical ATR, native Altirra (no NIO, hub, or custom device) and the
  production NetSIO lane both completed sector 361 at `DBYT=$0100`, traversed
  the linked program sectors, and stopped at `PC=$5060`. The earlier
  sector-361 failure was the old `$80` PicoBoot header causing `DBYT=$0080`,
  not a 256-byte delivery, checksum, or READY-handshake failure.
- The production trace is
  `/tmp/atari-story13-run/source-dd-netsio.log`; the native control trace is
  `/tmp/story13-native-altirra.log`. Their common initial sequence is D1
  STATUS, READ sectors 1--3 at 128 bytes, READ sector 361 at 256 bytes, then
  the program's linked-sector traversal. `PC=$5060` is the FAPP launch
  sentinel, not a claim about any Epic 2 guest acceptance service.
- The Story 1.1 fixture and projection manifest deliberately pin the new image:
  sector 1 begins `00 03 00 08`, has checksum `$94`, and image SHA-256 is
  `8f1cd8f689936ab5c94def50176ecab721f78a739e9aa117b0908c8b255c24f4`.
  `python3 -m unittest discover -s integration-tests/atari-sio/tests -v`
  passed all 14 tests.
- `make picobootcode.bin picobootcode-dd.bin` in `repos/MyPicoDOS` and
  `make TARGET=atari boot-disk install-boot-disk` in `repos/nio-core-apps`
  passed. The generated ATR and both installed firmware assets have the same
  SHA-256 above.
- `ctest --test-dir repos/fujinet-nio/build/atari-fujibus-netsio-debug
  --output-on-failure` passed all three tests. A clean
  `repos/fujinet-nio/./build.sh -cb` linked the classic Atari v1 Debug image;
  the follow-up `./build.sh -b` size check passed. During that clean build,
  the ESP32 channel-factory definition was aligned with its existing shared
  three-argument declaration. It remains behaviorally unchanged and does not
  add a disk path.

### Execution checklist

- [x] Config boot policy overlay and normal-mode restoration, including missing
  config and D2--D8 preservation, are covered by the focused bootstrap tests.
- [x] Source-built DD PicoBoot is reproducible from the pinned MyPicoDOS commit
  and produces byte-identical installed boot assets.
- [ ] Native Altirra control and production `AtariSioDiskFrontend`/shared
  `DiskService`/NetSIO boot runs must demonstrate FAPP-specific execution,
  rather than an address-only breakpoint.
- [x] Story 1.1 goldens, host regressions, and the clean classic ESP32 build
  passed.
- [x] Evidence is explicitly virtual only; real SIO electrical/timing and
  real-Atari acceptance remain Epic 3 work.
