---
title: 'Deliver native BASIC URI networking'
feature: 'atari-nio-physical-sio'
story: '2.5'
type: 'feature'
created: '2026-10-24'
status: 'draft'
baseline_workspace_commit: 'f88e24c8'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/SPEC.md'
  - '_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md'
  - '_bmad-output/planning-artifacts/epics-atari-nio-physical-sio.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-2-1-implement-bounded-native-atari-nio-client-backend.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-story-2-4-deliver-public-api-atari-nio-guest-acceptance.md'
---

# Story 2.5: Deliver native BASIC URI networking

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Atari configuration ATR proves the public cc65 API but does
not expose native URI networking to Atari BASIC through CIO `N1:` syntax.

**Approach:** Install a bounded resident CIO `N:` handler from the supported
ATR.  It owns only CIO adaptation and per-IOCB state; all networking remains
the public Atari `fujinet-nio-lib` client over native `0x7F`.

## Boundaries & Constraints

**Always:** Call `fn_init()` before publishing HATABS; install resident code,
library state, handler table, and caches below the raised `MEMLO`; preserve the
Graphics-0/runtime-memory gate.  Register `N` idempotently only when the entry
points to this handler; report a foreign `N:` entry without replacing it.
Map each CIO IOCB to its returned `fn_handle_t`; use no dynamic allocation,
legacy IDs, `$71`, SLIP, padded reads, raw SIO/DCB/FujiBus frames, or IRQ-time
network calls.  Serialize foreground library calls.  Keep a 128-byte cache per
open IOCB and commit unknown POST/PUT exactly once with zero-length
`fn_write()` before first STATUS, read, or CLOSE.

**Ask First:** Freeze the CIO error/status table in the first increment from
the named Atari OS error constants.  The canonical contract requires recording
the table but does not select every `FN_ERR_*` mapping; implementation must not
invent values.  Select the BASIC tokenization/load mechanism only after proving
it actually loads a BASIC program after installation without overwriting the
resident allocation.

**Never:** Add an Atari-specific network-slot protocol, alter the synchronous
endpoint to create PENDING, replace NetworkDevice, create a second ATR or
emulator runner, or treat virtual results as physical-SIO proof.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected behavior | Error handling |
|---|---|---|---|
| install | no `N` HATABS entry | resident range is reserved, then `N` is registered | `fn_init`/space failure rolls back with no entry or MEMLO change |
| reinstall/collision | own / foreign `N` entry | own entry is unchanged / foreign entry is preserved | explicit idempotent success / collision result |
| OPEN | `N1:fixture://...` with read/write/update mode | URI is parsed without `N1:` prefix; one public `fn_open` and handle ownership | malformed URI, session exhaustion, and stale IOCB map through frozen CIO errors |
| GET/PUT | byte CIO calls | 128-byte read refill and write flush preserve order and ownership | EOF, full cache, reset, and transport failure retain no unsafe retry |
| boundary | STATUS, first read, or CLOSE after POST/PUT | buffered bytes flush; exactly one zero-length commit precedes info/read/close | failed commit is reported and never duplicated |
</frozen-after-approval>

## Implementation-preparation evidence

- **Completed prerequisite (library `82a23cce`).** `fn_open_exchange()` now
  reserves a local session record before sending Open.  A full local table
  returns `FN_ERR_NO_HANDLES`, leaves the output at `FN_INVALID_HANDLE`, and
  emits no remote Open, including when `FN_OPEN_ALLOW_EVICT` is supplied.
  The flag remains a service-side wire option when local capacity exists; it
  never evicts an owned local session.  The BBC-specific Open path continues
  to close an already-opened OS channel on local exhaustion and now clears the
  caller's handle before returning the same error.
- The focused `open_wire_test` covers full/released tables, ordinary and
  translated Open, the allow-evict flag, ownership preservation, and the
  no-dispatch condition.  Verification passed: library `make check`; rebuilt
  Atari public-API acceptance (`ADP!`, including real Network Open); all 54
  Atari fixture tests; and the native/NetSIO D1 page-6 boot gate.  The latter
  evidence is retained at
  `test-evidence/atari-sio-boot-20261024-093602`.

## Increment 1 implementation evidence

- `repos/nio-core-apps` now builds `fnresident.xex` as a dedicated `$1d00`
  image with the real Atari archive and an explicit resident linker map.  The
  current linked range is `$1d00-$2ec6` (4,550 bytes, including library state
  and BSS), below the live `$941f` cc65-stack floor and Graphics-0 display.
- The installer calls `fn_init()` before changing HATABS, checks an existing
  `N:` entry by its table pointer, never replaces a foreign entry, and publishes
  MEMLO before the three-byte HATABS entry.  Its six address-minus-one vectors
  are deterministic CIO ABI stubs: X remains the IOCB offset, GET returns an
  A byte, and unsupported operations return the checked-in Atari OS `FNCNOT`
  (`$92`) status in Y.  `SUCCES=$01` and `FNCNOT=$92` are the only CIO status
  constants frozen in this increment.
- The existing ATR builder stages a composite executable whose installer runs
  as the genuine DOS `INITAD` phase and whose separately linked `$4000` probe
  is then loaded by DOS.  The probe verifies retained installer bytes, MEMLO,
  the N: HATABS entry/table, all six in-range handler vectors, and an actual
  call to the OPEN stub after the installer has returned.  The live NetSIO
  evidence is `test-evidence/atari-sio-resident-installer-20261024-101202`.
- `fnresident_memory_layout.py` and its unit test reject malformed maps;
  runtime inspection rejects stale vectors, changed MEMLO, missing N:, a
  failed initializer, or a resident range overlapping stack/display memory.
  A second real INITAD fixture preinstalls a foreign `N:` table at `$d000` and
  proves the installer reports the foreign outcome while retaining MEMLO
  `$0700` and the exact foreign HATABS bytes; evidence is
  `test-evidence/atari-sio-resident-foreign-live/netsio/resident-foreign.json`.

## Lifecycle hardening evidence

- The target profile is XL/XE. Checked-in cc65 layout gives eleven legal
  three-byte HATABS entries at `$031a-$033a`; `$033b/$033c` are the required
  zero terminator and `$033d+` are PUP validation bytes. The installer scans
  only those eleven entries, stops at the first terminator, and the runtime
  inspectors reject a changed terminator. It never scans or writes PUP bytes.
- The current linked resident image is `$1d00-$2ec6` (4,550 bytes). Raising
  live MEMLO from `$0700` to `$2ec6` reserves 10,182 bytes: the image plus the
  intentionally protected 5,632-byte `$0700-$1cff` load-address gap. The map
  and runtime gates quantify and verify this; no speculative relocation of
  the resident image was performed.
- A negative live experiment showed MyPicoDOS will copy an explicit XEX
  segment without consulting MEMLO. The shipped installer therefore stages
  its initialized `$1d00` image at `$5000-$5aee` and runs a small `$3800`
  bootstrap. The bootstrap checks HATABS first and copies/clears BSS into the
  protected range only when N: is absent. Its bounds are generated from the
  actual linker map. This is an independently designed NIO lifecycle shim,
  not legacy-handler code.
- The executable `resident-overlap` fixture performs two genuine MyPicoDOS
  loader phases. The second stages a fresh installer image but has no `$1d00`
  segment; it sees the active N:, returns outcome 1 with `init_status=$ff`,
  leaves MEMLO `$2ec6`, HATABS/terminator, table, and resident bytes unchanged.
  Evidence: `test-evidence/atari-sio-resident-reinstall-bootstrap-live-3/netsio/resident-overlap.json`.
  The separate owned-entry and foreign-entry live gates are retained at
  `test-evidence/atari-sio-resident-owned-live-final/netsio/resident-owned.json`
  and
  `test-evidence/atari-sio-resident-foreign-bootstrap-final/netsio/resident-foreign.json`.
- The current post-install proof is a real separately loaded `$4000` XEX which
  validates retained bytes, vectors, and an OPEN-stub call. A reproducible
  tokenized BASIC load is not yet available, so this increment explicitly does
  not claim BASIC-load survival. It remains the later packaging increment.
  Cold reset begins a new explicit installation lifecycle: no DOSINI hook is
  needed for the approved in-session DOS/XEX-load contract.

## Legacy NDEV behavioural comparison

The original FujiNet NDEV source was reviewed at
`https://github.com/FujiNetWIFI/fujinet-nhandler` as a behavioural coverage
reference only. No NDEV code, relocation routine, CIO implementation, SIO
command, or unit/session scheme was copied, translated, or adapted.

- NDEV illustrates relevant Atari-facing concerns—address-minus-one vectors,
  HATABS installation, resident lifetime, and DOSINI/reset reinsertion—and
  historical risks such as replacing any matching N: entry.
- NIO independently supplies the selected parity: bounded HATABS ownership,
  foreign-entry rejection, protected resident bytes, own-entry idempotence,
  and executable second-XEX survival. It intentionally does not use NDEV's
  legacy `$71-$78` SIO path, unit-based sessions, or reset hook; later CIO
  operations will use public `fn_*` APIs and native `$7f` only.
- NDEV's DOSINI behaviour is deliberately not parity-required. The approved
  NIO lifecycle is explicit reinstall after reset and persistence through
  supported same-session program loads. The missing BASIC fixture is recorded
  above as a real deferred gap, not a pass.

## Code Map

- `repos/cc65/include/_atarios.h:69-131` and
  `repos/cc65/asminc/atari.inc:18-145` -- authoritative local CIO layout:
  eight 16-byte IOCBs, HATABS `{id, table}`, six table vectors stored as
  address-minus-one, commands/open modes, and named CIO status codes.
- `repos/AltirraSDL/src/Kernel/source/Shared/cio.s:19-44,170-251,470-497` --
  executable OS ABI evidence: X is the IOCB offset, PUT receives A, GET
  returns A, handler returns Y status, and CIO owns `ICSTA`/must retain BUFADR.
- `repos/fujinet-nio-lib/include/fujinet-nio.h:35-54,217-248,590-805` --
  cc65 limits (128-byte URL, two sessions), `fn_handle_t`, GET/PUT/POST,
  unknown-body flag, and required public calls.  No new public API is needed.
- `repos/fujinet-nio-lib/src/common/fn_open.c:8-49` -- session ownership is
  reserved before Open is sent (library `82a23cce`), so a full local table
  returns `FN_ERR_NO_HANDLES` without an untracked remote handle.  CIO OPEN
  may depend on this prerequisite.
- `repos/nio-core-apps/makefiles/build.mk:31-110` and
  `makefiles/cc65-atari-nio.cfg` -- current cc65 XEX/archive pattern, ZP
  `$82-$ff`, 2 KiB C stack, and `fnaccept` constrained-link precedent.
- `repos/nio-core-apps/boot-disk/manifests/atari.yaml` and
  `makefiles/boot-disk.mk` -- reuse the staged MyPicoDOS/`dir2atr` config-ATR
  pipeline; add artifacts here, never a second builder.
- `integration-tests/atari-sio/fnaccept_memory_layout.py` and
  `run_boot_acceptance.py:2170-2335,2974-3160` -- adapt the existing map,
  Altirra lifecycle, NetSIO, embedded POKEY, evidence, and result mechanisms.
- `repos/fujinet-nio/tests/atari_netsio_clock_acceptance_runner.cpp:42-157`
  and embedded `fujinetnio.cpp` public fixture setup -- extend the registered
  deterministic Network protocol backend, not NetworkDevice or NIO framing.

## Execution increments and acceptance gates

1. **Resident ABI/install contract.** Add a dedicated resident-handler image,
   installer, linker/map gate, and a machine-readable install result.  Given a
   cold configuration ATR, when install succeeds, then `fn_init` precedes a
   HATABS entry pointing at resident vectors and raised `MEMLO`; failed init or
   insufficient RAM leaves both unchanged.
2. **HATABS lifecycle.** Implement exact self-entry detection, foreign-entry
   collision, and reinstallation tests.  Given BASIC/DOS loads after install,
   when they reuse ordinary allocatable memory, then the handler range and
   HATABS entry remain valid; a foreign `N` is never overwritten.
3. **Public-session prerequisite and OPEN.** Correct the common-library
   session-exhaustion regression and add its `make check` coverage.  Implement
   `N1:` OPEN parsing/modes and IOCB-to-handle records; given two live sessions,
   a third OPEN fails through the frozen CIO table rather than creating a new
   Atari slot scheme.
4. **GET cache.** Implement 128-byte bounded refill, offsets, EOF and stale
   handle handling.  Given byte GETs across a cache boundary, returned bytes
   and service reads are ordered exactly once.
5. **PUT/update cache and commit.** Implement 128-byte flush, unknown-body
   POST/PUT, STATUS/read/CLOSE barrier, and exactly-once zero-length commit.
   Given repeated STATUS/CLOSE after commitment, no second zero-length write is
   emitted.
6. **CIO errors/reset/serialization.** Freeze and test the table, recovery of
   reset/stale handles, close-after-failure, and foreground re-entry exclusion.
   No handler path calls `fn_*` from an interrupt or replays an uncertain write.
7. **Packaging and BASIC fixture.** Add the resident installer and tokenized or
   loader-proven BASIC acceptance program to the existing manifest.  Its result
   block records install/collision, handles, CIO statuses, commit count, data,
   memory, and heartbeat after a real BASIC/DOS load.
8. **NetSIO acceptance.** Extend the real-core fixture protocol for explicit
   GET and unknown-body POST/PUT state/counts; run the BASIC fixture through
   existing NetSIO capture and require service dispatch, actual datagrams,
   backing evidence, and negative mutations.
9. **Embedded acceptance and regression.** Execute the same ATR/BASIC fixture
   through Altirra’s embedded production device with POKEY capture; require
   adapter-scoped evidence and retain the D1 boot, Story 2.3, and Story 2.4
   gates.

## Decisions, risks, and genuine gaps

- The handler is a new resident program/image, not an extension of
  `fnaccept`: every callable library member and state it needs must survive
  later BASIC/DOS loads.  Its map gate must calculate the raised-MEMLO range
  against live display/stack memory; the existing `$0b00` result/disk windows
  are not its storage contract.
- No Atari BASIC tokenization/loader pipeline exists today.  This is a real
  build gap, not authorization for a second boot pipeline; increment 7 must
  choose the smallest reproducible tool/path and prove a post-install load.
- The deterministic production Network fixture currently accepts only the
  Story-2.4 POST exchange.  It must gain declared URI/method/offset/commit
  expectations plus dispatch counters for this story, while still using the
  real NetworkDevice, RoutingManager, and endpoint.
- `FN_MAX_URL_LEN=128`, `FN_MAX_SESSIONS=2`, and packet limit 512 bound the
  supported URI, cache and BASIC test cases.  The handler must reject rather
  than truncate.  PROC stays unadvertised/polling-only and is out of scope.

## Verification

- `source scripts/env.sh && make -C repos/fujinet-nio-lib check` -- required
  after the session-exhaustion fix or any library change.
- `source scripts/env.sh && make -C repos/nio-core-apps -f makefiles/build.mk TARGET=atari <resident-target> boot-disk` -- build/map/ATR gate.
- `python3 -m unittest discover -s integration-tests/atari-sio/tests -q` plus
  focused resident-map/runner tests -- installation, collision, cache, commit,
  result/evidence validation.
- Focused POSIX firmware CTest and embedded Altirra SIO CTest -- deterministic
  production NetworkDevice fixture behavior.
- Existing runner scenario flags for NetSIO and `altirra-embedded` -- live
  BASIC result, guest execution, captured native traffic, dispatch count,
  screenshots/logs and retained backing evidence; then D1 page-6 boot gate.

## Out of scope

Physical SIO timing/electrical validation (Epic 3), legacy FujiNet `N:`
protocols or device IDs, PROC delivery, BASIC `N:` compatibility beyond the
defined supported URI/modes, and a transport or NetworkDevice redesign.
