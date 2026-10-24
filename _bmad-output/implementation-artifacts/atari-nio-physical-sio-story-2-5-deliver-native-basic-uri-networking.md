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

## Resident relocation feasibility report

This is a focused architecture investigation.  It adds no production
relocator, CIO network operation, BASIC tokenizer, or embedded-adapter work.

### Measured present scaffold

The committed `fnresident` linker map uses the fixed `$1d00` image below.
`LOWBSS` and `INIT` are absent, not zero-sized hidden allocations.

| segment | linked range | bytes |
|---|---:|---:|
| ZEROPAGE | `$0082-$009b` | 26 |
| STARTUP | `$1d00-$1d62` | 99 |
| ONCE | `$1d63-$1d6e` | 12 |
| CODE | `$1d6f-$27ac` | 2,622 |
| RODATA | `$27ad-$27be` | 18 |
| DATA | `$27bf-$27ee` | 48 |
| BSS | `$27ef-$2ec5` | 1,751 |
| **resident range** | **`$1d00-$2ec5`** | **4,550** |

Its initialized bytes total 2,799; the XEX is 2,811 bytes including the Atari
load/run records.  The current range starts 5,632 bytes above live
`MEMLO=$0700`, so raising MEMLO to `$2ec6` reserves 10,182 bytes.  The extra
5,632 bytes are fixed-address waste, not payload.  The biggest contributors
are `fn_state` (267 code + 1,217 BSS + 1 data = 1,485), `fnresident` (1,252
code + 2 rodata = 1,254), `fn_transport` (585 code + 529 BSS + 6 data =
1,120), `fn_init` (108), and the cc65 startup/runtime closure (401 code, 41
data, 12 ONCE, 5 BSS, 99 STARTUP, and 26 ZP).  The handler table itself is
only 25 bytes (9 code + 16 rodata); the footprint is library state and the
fixed link address, not the six vectors.

The existing live map/runtime gate reports `MEMTOP=$9c1f`, a 2,048-byte cc65
stack reserve with floor `$941f`, and Graphics-0 display allocation above
that floor.  The C stack is an upper-memory reservation, not part of the
resident image.  The 26-byte cc65 ZP allocation is likewise shared runtime
state: it cannot be copied to a new base and an installed image must retain
its compiler/runtime ZP contract.

### Complete public-API closure measurement

`integration-tests/atari-sio/resident-relocation/resident_api_closure.c`
links exactly the current Atari archive closure for `fn_init`, `fn_open`,
`fn_write`, `fn_read`, `fn_info`, and `fn_close`.  It is a link-only
measurement, never an installed handler.  It includes two handles and two
128-byte cache buffers, which exercises the configured two-session API limit.

| segment | linked range | bytes |
|---|---:|---:|
| ZEROPAGE | `$0082-$009b` | 26 |
| STARTUP | `$1d00-$1d62` | 99 |
| ONCE | `$1d63-$1d6e` | 12 |
| CODE | `$1d6f-$444d` | 9,951 |
| RODATA | `$444e-$447f` | 50 |
| DATA | `$4480-$44af` | 48 |
| BSS | `$44b0-$4ca1` | 2,034 |
| **closure range** | **`$1d00-$4ca1`** | **12,194** |

It has 10,160 initialized bytes and a 10,172-byte XEX.  Its largest linked
members are `fn_rw` (1,517), `fn_state` (1,485), `fn_open` (1,263),
`fn_transport` (1,120), `fn_packet_build_rw` (927),
`fn_packet_build_open` (734), the closure caller (601, including 271 BSS),
`fn_packet_parse_common` (560), `fn_packet_parse_read` (528),
`fn_packet_parse_info` (436), `fn_info_close` (427), and
`fn_packet_header` (389).  This identifies normal public API packet build and
parse code—not duplicate storage—as the reason a real N: handler is much
larger than the current installer scaffold.

The two cache buffers are exactly 256 of the caller's 271 BSS bytes.  A final
handler may map all eight IOCBs to a bounded set of **two active cache/handle
records** because `FN_MAX_SESSIONS=2`; a third concurrent OPEN must fail.  It
does not need eight 128-byte buffers.  Conservatively allow another 48 bytes
for eight IOCB-to-slot records and status flags, plus the actual CIO adapter,
handler table, URI/mode parsing scratch, and result/state.  The 12,194-byte
closure is therefore a measured lower bound, not an asserted final size; the
first real CIO-operation map must replace this link-only caller before fixing
the final allocation ceiling.

At an initial `$0700` allocation base, this measured closure would end at
`$36a2`.  It must not actually start there while the installer result occupies
`$0b00-$0b27`: that current 40-byte machine-readable result would be
overwritten.  A dynamic allocator must reserve the contiguous region from old
MEMLO and use at least aligned `$0b28` as the payload base (or relocate the
installer result below/away from the allocation).  This makes the result
window and any probe records explicit allocation constraints rather than
assuming that a raised MEMLO protects them automatically.

### Relocation and staging findings

`relocation_feasibility.s` is a soft65c02 executable proof, not a protocol
peer.  It copies one code/data blob, applies its recorded absolute-word
fixup, publishes an address-minus-one `N` HATABS vector, and calls it at both
`$3000` and `$4800`.  Both calls read their distinct relocated data.  Its
negative control copies the same bytes to `$5800` without the fixup and proves
that the absolute operand still reads the source data rather than destination
data.  Thus byte-copying an XEX or a fixed linked segment is not relocation.

ld65 `load`/`run` is useful but deliberately not mistaken for this requirement.
The executable `load_run_probe` links DATA with `load=$5004`, `run=$2400`,
and `define=yes`; it verifies generated `__DATA_LOAD__=$5004`,
`__DATA_RUN__=$2400`, and `__DATA_SIZE__=2`.  The linked `LDA` operand is
`$2400`, while the file carries the two data bytes at `$5004`.  This is the
supported model described in the cc65 discussion
<https://cc65.github.io/mailarchive/2003-10/3700.html>: it lets a transient
loader copy a known source to a **fixed link-time RUN address** using generated
symbols.  It does not make RUN equal to a runtime-selected `MEMLO`, and so
cannot by itself provide a compact dynamic resident handler.

cc65 also supports o65 modules, whose ld65 writer emits text/data relocation
records (`WORD`, `HIGH`, `LOW`, and segment forms).  The `o65_probe` links a
CODE-to-DATA absolute reference; `co65 --no-output --verbose` verifies exactly
one text relocation.  The checked-in `libsrc/common/modload.s` is an existing
cc65 o65 parser/relocator, but it allocates with the application heap.  That
does not meet the resident contract on its own: an installer needs an explicit
live-MEMLO arena and must raise MEMLO only after ownership and bounds checks.

**Recommendation:** use an o65 resident payload plus a small, bounded
address-taking loader based on the supported o65 format/relocation semantics,
not a hand-maintained table and not `load/run` alone.  Keep the transient
installer/bootstrap at a fixed staging address; it must first inspect HATABS
ownership, calculate `base=align(max(live_MEMLO, result_window_end))`, reject
if `[old_MEMLO, base+module_size)` conflicts with stack, display, or staging,
then load/relocate/zero BSS, call `fn_init`, raise MEMLO, and publish HATABS.
The following production increment (recorded below) supersedes this proposed
layout with an executable bounded loader and two live MEMLO-derived bases.

MyPicoDOS ignores MEMLO for explicit XEX segments, so staging is a separate
safety condition.  The current fixed-image bootstrap avoids an `$1d00`
segment on reload, but its `$3800` bootstrap cannot coexist with the measured
dynamic closure (payload from `$0b28` would reach `$3aca`).  A feasible next
layout is a fixed transient bootstrap at `$5600`, initialized o65 staging at
`$5800`, and a hard target-end ceiling of `$5600`.  With the measured closure,
the target is `$0b28-$3ac9` and staging ends `$7faf`, below the observed
`$941f` stack floor.  `resident_allocation_plan.py` makes those arithmetic
constraints executable and rejects one-byte target/bootstrap and
staging/stack overruns.  The real loader must retain the same checks and a
second-XEX test proving no active resident interval is written before its
HATABS ownership check.

### Executable gates added by this investigation

- `make -C integration-tests/atari-sio/resident-relocation relocation-feasibility`
  -- two relocated bases, HATABS-compatible vector, and unrelocated absolute
  reference negative control.
- `make -C integration-tests/atari-sio/resident-relocation load-run-symbols`
  -- independent `__DATA_LOAD__`, `__DATA_RUN__`, and `__DATA_SIZE__` proof.
- `make -C integration-tests/atari-sio/resident-relocation o65-relocation-metadata`
  -- ld65 o65 output parsed by `co65`, with one real relocation record.
- `make -C integration-tests/atari-sio/resident-relocation allocation-plan`
  -- dynamic MEMLO/result-window calculation and staging/target boundary
  rejection for the measured closure.
- `make -C integration-tests/atari-sio/resident-relocation api-closure-map`
  -- reproducible current public-API closure map and largest-module report.
- `python3 -m unittest discover -s integration-tests/atari-sio/tests -p
  'test_resident_relocation_feasibility.py' -q` -- runs the four executable
  mechanism checks.

The accepted fixed installer, its idempotence/foreign-owner tests, the public
API acceptance, library gate, and D1 boot regression remain unchanged by this
investigation.

## Real public-API o65 closure feasibility

This follow-on remains an experiment only: it does not alter the fixed
installer, add a production o65 loader, install CIO OPEN/GET/PUT, or package a
BASIC application.

### Candidate and exact closure

`resident_api_o65.c` invokes the real Atari archive's `fn_init`, `fn_open`,
`fn_write`, `fn_read`, `fn_info`, and `fn_close`, and owns two handles plus two
128-byte cache records.  It is linked directly with `ld65`'s checked-in
`module.cfg`, `fujinet-nio-atari.lib`, and `atari.lib`, deliberately without
`crt0`: a CIO-resident module is entered through a handler vector, not an XEX
startup sequence.  The toolchain accepts that actual closure directly with no
unresolved imports.

| o65 allocation part | bytes | linked relative range |
|---|---:|---:|
| TEXT (CODE + RODATA) | 10,000 | `$0000-$270f` |
| initialized DATA | 7 | `$2710-$2716` |
| BSS | 2,047 | `$2717-$2f15` |
| cc65 ZP | 26 | `$0000-$0019` before runtime ZP placement |
| **initialized / resident allocation** | **10,007 / 12,054** | **`$0000-$2f15`** |

This is 140 bytes below the earlier 12,194-byte link-only XEX measurement:
the o65 candidate correctly omits XEX-only `crt0`/constructor scaffolding,
not library state.  The seven initialized bytes are the `"atari\0"` platform
name; there are no initialized pointer records.  Major retained code remains
the real `fn_rw` (1,517), `fn_state` (1,485), `fn_open` (1,263),
`fn_transport` (1,120), packet builders/parsers, and cc65 arithmetic/stack
helpers.  The candidate's representative C object contributes 706 bytes.

### Relocation audit and execution evidence

`co65 --verbose --no-output` reports 2,433 text relocations, zero data
relocations, zero imports, and zero emitted o65 exports.  The checked parser
accepts exactly the relocation forms supported by cc65 `modload.s` and reports:

| form / target segment | count |
|---|---:|
| low/text, low/data, low/BSS, low/ZP | 2, 1, 58, 1,461 |
| high/text, high/data, high/BSS | 2, 1, 58 |
| word/text, word/data, word/BSS | 490, 7, 353 |

Thus the real code exercises code-to-code, code-to-data, BSS, and cc65 ZP
fixups; its DATA has no relocation records.  The parser rejects undefined,
segment-address, segment-only, unsupported segment IDs, malformed streams,
and trailing unparsed export metadata.  Its deliberate `SEGADR` negative test
proves that an unsupported relocation cannot silently become an address.

`o65_api_runtime.txt` uses the exact one generated module as its source bytes,
relocates it to `$2000` and `$5000` without rebuilding, and executes both
copies in soft65c02.  A narrow SIOV interceptor at `$e459` validates device
`$7f`, W/P/R order, DCB direction, count and AUX; it returns literal checked
FujiBus replies only.  Each real copy completes `fn_init/open/write/read/info/
close`, emits five W/P/R triplets, parses handle `$1234`, accepts/writes four
bytes, reads `R65!`, parses HTTP 200 and content length four, and retains its
own mutable BSS result.  This is executable 6502 evidence for the actual
library and transport, not a C/Python reimplementation of its public API.

The o65 header does not emit public export names for this link despite the
ld65 map labels.  That is a viable, explicit constraint: the production
payload needs a small versioned header/jump table at the start of TEXT (or an
equivalent generated entry-offset record); it must not depend on a host map.

### Resident invocation contract

The experiment makes the omitted startup work visible.  Before every later
foreground CIO invocation, the resident assembly gateway must:

1. Serialize entry with a resident busy latch; no `fn_*` call is legal from
   an interrupt or concurrently re-entered CIO path.
2. Save the 26-byte cc65 ZP bank at its chosen live placement, establish the
   resident-owned cc65 software-stack pointer (`c_sp`), and preserve the 6502
   hardware stack/CIO ABI frame.
3. Call the resident C entry.  The loader—not `crt0`—must have copied DATA,
   zeroed the 2,047-byte BSS, installed the fixed ZP placement, and performed
   the one-time `fn_init()` before HATABS publication.
4. Restore the caller's ZP/CPU-facing state before returning Y/A as required
   by CIO.  This prevents a later BASIC/DOS program from inheriting cc65
   scratch state while preserving the module's relocated BSS/library state.

The runtime test explicitly clears the ZP bank and establishes `c_sp=$9000`
for each base before entering the C function; it sets the hardware stack to
`$ff`.  That proves the required inputs, not that arbitrary BASIC/OS state is
already preserved by the current scaffold.  The permanent resident allocation
must additionally include a bounded cc65 software stack; the o65 header's
zero stack request means the loader must choose and reserve it explicitly.

### Staging/result-window conclusion

The parameterized allocation gate now uses the actual o65 sizes: with live
`MEMLO=$0700`, current result end `$0b28`, transient bootstrap `$5600`, staging
`$5800`, and observed stack floor `$941f`, it computes target
`$0b28-$3a3d` and staged initialized bytes ending `$7f16`.  One-byte target /
bootstrap and staging / stack overruns fail the gate.  The future installer
must obtain all of those bounds at runtime and perform its existing HATABS
ownership check before writing either target memory or raising MEMLO; the
accepted live `resident-overlap` second-XEX test remains the evidence that
MyPicoDOS otherwise ignores MEMLO.

`$0b00-$0b27` should remain an **installer-transient** diagnostic ABI only,
not a permanent resident hole.  The maintainable approach is for the
transient loader to write it before/after installation, place the payload at
`align(max(MEMLO, $0b28))`, then let ordinary allocation own the entire range
from old MEMLO through the resident stack.  A later guest inspection can use
the handler's versioned query/status entry or a separate transient probe;
neither requires reserving `$0b00` after installation.

**Conclusion: o65 is viable with specific constraints.**  The actual library
closure has only relocation forms handled by the supported cc65 model and runs
unchanged at two bases.  The remaining implementation work is deliberately
bounded: a fixed-stage, explicit-arena o65 loader; a versioned module entry
header; one-time DATA/BSS/ZP/stack initialization; and a save/restore CIO
gateway.  `load/run` remains useful for transient staging, but cannot replace
that runtime relocation step.

### Verification retained for this increment

The focused experiment gate passes with `make -C
integration-tests/atari-sio/resident-relocation o65-api-closure o65-api-runtime
allocation-plan allocation-plan-o65`; its soft65c02 run has 27 assertions for
the two independently relocated copies.  The complete Atari integration test
discovery (`65` tests) and `repos/fujinet-nio-lib` `make check` also pass.

No production resident, public-library, endpoint, or boot code changed in
this increment.  The existing live gates therefore retain their current
evidence: resident installer `RPR!` at
`test-evidence/atari-sio-resident-installer-20261024-194913/`, public API
acceptance `ADP!` at
`test-evidence/atari-sio-public-api-clock-20261024-195015/`, and D1 boot
`NIO!` at `test-evidence/atari-sio-boot-20261024-195026/`.

## Production o65 resident-loader increment

`repos/nio-core-apps` now supplies a separate, crt0-free
`fnresident-module.o65` rather than reusing the fixed `$1d00` image.  It
contains the real public Atari archive closure (`fn_init`, `fn_open`,
`fn_read`, `fn_write`, `fn_info`, and `fn_close`), the eventual two handle
records and two 128-byte caches, library DATA/BSS, and a minimal six-vector
address-minus-one CIO table.  This increment still exposes only deterministic
`FNCNOT` stubs; no network operation is published yet.

The bounded loader accepts only the validated FNR1-wrapped cc65 16-bit/small
o65 profile: contiguous TEXT/DATA/BSS, no imports/exports, and TEXT/DATA/BSS/
ZP low, high, and word relocations.  It saves the 26-byte cc65 ZP bank,
relocates to `align(live MEMLO)`, copies initialized bytes, zeroes BSS,
establishes the resident software stack, calls `fn_init`, validates the copied
marker/table/vectors, then atomically publishes HATABS and MEMLO.  Wrapper,
stage, target, stack, display, and transient-loader bounds are checked before
destination writes.  HATABS is scanned *before* range allocation: an owned
entry is idempotent even when raised MEMLO could not fit another copy; a
foreign entry is left untouched.

| measured component | size / live range |
|---|---:|
| initialized TEXT+DATA | 9,923 bytes |
| BSS / cc65 ZP | 2,027 bytes / 26 bytes at `$82-$9b` while resident C runs |
| payload allocation / resident C stack | 11,950 / 256 bytes |
| permanent allocation at MEMLO `$0700` | `$0700-$36ad` (`MEMLO=$36ae`, 12,206 bytes) |
| permanent allocation at MEMLO `$0702` | `$0702-$36af` (`MEMLO=$36b0`) |
| observed free range below `$941f` stack floor | 23,921 / 23,919 bytes respectively |
| transient loader / staged FNR1 / probe | `$3800-$3f7d` (1,918 bytes) / `$5800-$924d` (14,926 bytes) / `$4000-$4123` (292 bytes) |

The installer result is transient at `$5400`; it is explicitly outside the
resident interval.  The loader and the probe are both above the target range.
MyPicoDOS demonstrably continues using low RAM after an `INITAD` routine, so
the configuration-ATR composition first loads the staged module and the
independently linked probe, then uses a six-byte `$4200` transient launcher to
call the loader and enter the probe.  This is a loader-safety arrangement for
the engineering launcher, not a DOS requirement or a permanent low-memory
reservation.  It proves the retained handler bytes and an OPEN-stub call from
the independent program.  A reproducible genuine BASIC/DOS post-install load
remains the intentionally deferred packaging/BASIC fixture increment; none is
claimed here.

### Executed evidence

- `make -C integration-tests/atari-sio/boot-app test-resident-o65` passed:
  actual cc65 module relocation and `fn_init` at `$0700`; copied BSS state;
  FNR1/o65 relocation and vector publication; and a corrupted-wrapper
  negative test that leaves MEMLO, HATABS, and `$0700` unchanged.
- Live production NetSIO/Altirra runs passed with retained evidence:
  - `--resident-o65-installer`: `RPR!`, `$0700 -> $36ae`,
    `test-evidence/atari-sio-resident-o65-normal-cli/netsio/`.
  - `--resident-o65-altbase`: `RPR!`, `$0702 -> $36b0`,
    `test-evidence/atari-sio-resident-o65-altbase-cli/netsio/`.
  - `--resident-o65-idempotent`: `RPR!`, outcome 1, unchanged `$36ae`,
    `test-evidence/atari-sio-resident-o65-idempotent-cli/netsio/`.
  - `--resident-o65-foreign`: outcome 4, unchanged `$0700` and foreign
    `N:$d000`,
    `test-evidence/atari-sio-resident-o65-foreign-cli/netsio/`.

The fixed `$1d00` installer and its independent lifecycle regressions remain
in place as reference coverage.  The next increment may add CIO operations,
but must retain this bounded loader, transient-result discipline, and the
two-base/ownership gates.

## Resident public-library footprint reduction

This bounded optimization retained the same public API closure, o65 format,
two-base relocation and handler lifecycle.  It did not add a CIO operation or
change the native transport contract.

### Measured production module

`resident-o65-footprint` parses the actual production
`fnresident-module.map`, ranks every CODE/RODATA/DATA/BSS contributor, and
fails if the bounded N: closure exceeds its recorded post-change allocation or
links the optional TCP formatter.  The post-change module is:

| segment | bytes | largest contributors |
|---|---:|---|
| CODE | 9,158 | `fn_rw` 1,505; `fn_packet_build_rw` 927; `fn_packet_build_open` 734; `fn_open` 726; `fn_transport` 585 |
| RODATA | 66 | module URI 30; handler table 20; response parser 16 |
| DATA | 7 | transport platform name 6; state 1 |
| BSS | 1,387 | `fn_state` 1,089; resident IOCB handles/caches 269; transport state 17; `fn_rw` diagnostics 12 |
| cc65 ZP / C stack | 26 / 256 | established resident ABI requirements |

The 1,089-byte `fn_state` allocation is the necessary pair of bounded
512-byte raw FujiBus request/reply buffers plus session and parser context.
The module's 269 bytes are the deliberate two 128-byte CIO caches, two
handles and small per-handler state.  These are not duplicate packet copies.
The remaining major code is required to build/parse public Open, Read, Write,
Info and Close packets; no low-risk removal was found there without removing
an approved future N: operation.

| measurement | before | after | change |
|---|---:|---:|---:|
| initialized CODE+RODATA+DATA | 9,923 | 9,231 | -692 |
| BSS | 2,027 | 1,387 | -640 |
| payload allocation | 11,950 | 10,618 | -1,332 |
| payload plus 256-byte C stack | 12,206 | 10,874 | -1,332 |
| live `$0700` reservation / new MEMLO | `$0700-$36ad` / `$36ae` | `$0700-$3179` / `$317a` | 1,332 bytes reclaimed |

The FNR1 wrapped stage is now 13,903 bytes at `$5800-$8e4e`; its o65 module
contains 9,231 initialized bytes, 1,387 BSS bytes and the unchanged 26-byte
cc65 ZP requirement.  The transient loader segment is 1,951 bytes at
`$3800-$3f9e` (1,957 bytes in its XEX record), and the resident C stack is
still the explicit 256-byte allocation included in the permanent reservation.
Neither transient artifact is retained after installation.  The loader's
staging and stack/display checks therefore remain parameterized rather than
relying on the former larger footprint.

### Changes and regression evidence

- `fn_tcp_open()` was split into its own archive member with its private
  128-byte TCP URL formatter.  URI-based N: code calls `fn_open()` and no
  longer links that optional member, its decimal conversion helpers or its
  scratch storage.  The exported function and its existing TCP wire method
  are unchanged; `open_wire_test` now asserts its exact generated Open packet.
- Atari recovery now drains a retained response into the existing internal
  bounded reply buffer before a new application W.  It previously retained a
  second, independent 512-byte discard buffer.  The operation occurs only
  while an outstanding response is being intentionally retired, so it cannot
  overrun caller storage or alter the retained-response recovery contract.
  The real assembled soft65c02 transport suite continues to cover timeout,
  malformed P, interrupted R, reset and 512-byte recovery ordering.
- The smaller allocation exposed a carry-loss bug in the production o65
  loader's `initialized + BSS` validation: the former low-byte comparison
  happened to restore the needed carry.  The loader now preserves that carry
  explicitly, and its assembly test proves copied/relocated `fn_init`, BSS
  initialization, MEMLO publication and failure rollback with the new image.

Executed focused gates: `test-open-wire`, `test-atari-transport`,
`resident-o65-footprint`, `test-resident-o65`, and the existing real-library
two-base `o65-api-closure o65-api-runtime` test.  `make -C
repos/fujinet-nio-lib check` passed across its configured cc65, hosted,
MS-DOS and Amiga targets.

Fresh live evidence is retained at:

- `test-evidence/atari-sio-resident-o65-installer-20261024-214621/` —
  production NetSIO installation result `RPR!`, live `MEMLO=$317a`, retained
  relocated head `4c921a201028a90f`, and a separate post-install probe call.
- `test-evidence/atari-sio-public-api-clock-20261024-214706/` — normal
  public API acceptance result `ADP!`, all Clock/File/Network/Disk stages and
  backing effects intact after rebuilding against the smaller archive.
- `test-evidence/atari-sio-boot-20261024-214919/` — the deterministic D1
  regression reached `NIO!` through both the native control and production
  NetSIO path; its D1 service counters and first-read traffic remain present.
