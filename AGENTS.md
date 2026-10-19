# Workspace agent instructions

## Environment and toolchains

Before building or testing repositories in this workspace, source the shared
environment setup:

```sh
source "$NIO_WORKSPACE/scripts/env.sh"
```

The same setup exports `CC65_HOME` for Atari/BBC builds and adds the configured
Amiga cross-toolchain directory when available.

For Amiga builds, the compiler and NDK headers must also be readable by the
current user. A toolchain that is present but contains unreadable headers is an
environment failure, not a source-build pass.

## Library change check

For every change under `repos/fujinet-nio-lib`, run:

```sh
cd "$NIO_WORKSPACE/repos/fujinet-nio-lib"
make check
```

`make check` first builds every configured library target, then runs the fast
host-side wire tests and public archive-link test. A partial build is not an
all-target pass; if a toolchain is genuinely unavailable, record the exact
target and toolchain in the task review.

## Cross-repository work

A firmware protocol change or new setting isn't finished in `repos/fujinet-nio`
alone: its Python client (`py/fujinet_tools`) is always updated with it, and
diagnostics console support is offered to the user (expected for
configurable values). See "Changing a device protocol or adding a setting" in
`repos/fujinet-nio/AGENTS.md`. C clients get the matching
`repos/fujinet-nio-lib` call.

Use `backlog/` for active workspace-level goals and move completed goal files
to `completed/`. Keep repository-specific implementation details in the
owning repository's documentation. Active BMad spec folders live in
`_bmad-output/specs/`; accepted specs move to `_bmad-output/completed-specs/`
and are not living requirements. `_bmad-output/archive/` holds superseded
snapshots (including the 2026-08-28 Amiga RS-232 overrun handoff); do not
treat those files as current diagnosis or work plans. For RS-232 above 9600
baud, use `_bmad-output/planning-artifacts/research/technical-amiga-rs-232-disk-operation-failures-abo-2026-09-03/research.md`.
Amiga RS-232 hardware is defined by print-validated AHRM extracts under
`repos/fujinet-nio-driver/docs/amiga/` (`Serial-IO-Interface.md`,
`serial-interface-connector.md`, `cia-port-signal-assigments.md`,
`cia-chip-register-map.md`), not by the AHRM PDF and not by CIA 8520
serial-shift folklore. Paula owns TXD/RXD (`MR_SERIALPORT`); CIA-B port A
owns RTS/CTS and the other modem lines (`MR_SERIALBITS`). Process map:
`docs/amiga/rs232-paula-and-cia-handshake.md`.

## BMad artifact namespaces

`_bmad-output/planning-artifacts/epics.md` and the generic
`_bmad-output/implementation-artifacts/epic-<N>-context.md` files belong to
the active Amiga Zorro-II packet-native-backend program. They are not shared
number spaces and must not be rewritten, regenerated, renamed, or used as
context for another feature.

The Atari physical-SIO program is independently owned by
`_bmad-output/planning-artifacts/epics-atari-nio-physical-sio.md` and
`_bmad-output/specs/spec-atari-nio-physical-sio/`. Its derived contexts and
implementation specs must use an `atari-nio-physical-sio-` filename prefix
(for example, `atari-nio-physical-sio-epic-1-context.md`). Before changing a
BMad planning/context artifact, verify both its feature identity and story
title. A bare numeric Epic/Story label is never sufficient identification.

## Amiga DiskDevice status and future media work

Stage 8, its hardening work, and DiskDevice Phase 2 are complete. Do not reopen
their implementation or replay their history unless a regression is found.
The completed acceptance record is
`completed/amiga-diskdevice-phase-2.md`; the durable user and architecture
contract is `docs/amiga/disk-media-architecture.md`.

Current production support is standard DD and high-density-floppy ADF media.
The standard `FMOUNT`/`FUMOUNT`/`FMOUNTRESTORE` workflow owns normal mounting,
eject, replacement, and persisted restoration. Amiga units `DN0:`–`DN7:` map
independently to the resident driver's eight DiskDevice slots; catalogue media
selection is not restricted to catalogue entries 1–8.

Future whole-volume HDF and partitioned RDB work is tracked in
`backlog/amiga-hdf-rdb-support.md`. Do not treat it as unfinished Phase 2 or
broaden media support without satisfying that task's staged validation.

For an HDF/RDB scratch session, read only these files first:

1. `AGENTS.md`
2. `backlog/amiga-hdf-rdb-support.md`
3. `docs/amiga/disk-media-architecture.md`
4. `repos/fujinet-nio-driver/amiga/README.md`
5. `repos/fujinet-nio-driver/amiga/WRITE_MEDIA_POLICY.md`

Then inspect the current commits and status in the workspace plus these
repositories:

```sh
git status --short
git log --oneline -10
git -C repos/fujinet-nio-driver log --oneline -5
git -C repos/fujinet-nio-lib log --oneline -5
```

Before implementation, identify the owning repository from the active ticket:

- `repos/nio-core-apps`: standard `FMOUNT`/`FUMOUNT` command behavior.
- `repos/fujinet-nio-driver`: Amiga resident device, dynamic geometry,
  MountLists/device integration, and native tests.
- `repos/fujinet-nio-lib`: shared DiskDevice/session contracts and target
  transport only when a library change is required.
- Workspace `integration-tests/amiberry`: cross-repository acceptance tests.
- Workspace `backlog/`: active goal scope, dependencies, checkboxes, and exit
  criteria only.
- Workspace `docs/amiga/`: durable user and architecture documentation.
- Workspace `completed/`: closed acceptance records and historical evidence.

Use the smallest context sufficient for the ticket. Quote the relevant active
checkbox and read only the owning implementation file, its focused tests, and
the associated architecture section. Do not load completed Stage 8/Phase 2
history unless the ticket explicitly concerns a regression or an established
contract.

## Amiga NIO broker Stage 3

Stage 3 cut-over is accepted. Do not reopen its implementation or replay 3A/3B
unless a regression is found. The completed record is
`completed/amiga-nio-broker-stage-3.md`; the durable contract is
`docs/amiga/nio-broker-architecture.md`. Remaining checkpoint is Stage 5
(extra backends) in `backlog/nio-broker.md`. Stage 4 idle-close removal is
accepted (`completed/amiga-nio-broker-stage-4.md`); do not restore FIFO-empty
`fn_transport_close` on `fujinet-disk.device`.

## Git commits

When completing a story, commit its changes with a message describing the change
and relevant verification. Never push changes.

Never add a `Co-authored-by` (or `Co-Authored-By`) trailer to any commit.
Do not attribute Cursor, Copilot, Claude, or any other agent as a co-author.
Commit as the person doing the work, not as an agent identity, and leave out
agent session links (such as `Claude-Session:` lines).

Never commit changes to submodule URLs in `.gitmodules`: they must stay on
`github.com/markjfisher/`. To work against a fork, override the URL in local
git config (`git config submodule.<path>.url <fork>`, then
`git submodule sync <path>`), which is never committed.
`scripts/check-gitmodules.sh` checks this, and CI runs it on every pull request.

Workspace pull requests never carry submodule pin changes: pins move only to
commits already merged into the submodule's repository, after its PR is
merged. CI checks this with `scripts/check-submodule-pins.sh`. Work against
forks as `CONTRIBUTING.md` describes (a `fork` remote inside each submodule).

## Verification (FujiNet NIO product)

Follow `docs/agent-test-policy.md`. Every repo you touch needs the cheapest
test that can fail for that change, recorded and run. Do not default to the
full Amiberry suite, every firmware preset, or `scripts/build.sh all`.

When changing `repos/fujinet-nio-lib`, run complete `make check`. Amiga guest
procedure: `docs/amiga/amiberry-testing.md`. Amiga CLI tools: default Shell
STACK is 4096; do not `WaitIO` an OpenDevice-only IORequest
(`docs/amiga/cli-stack-and-iorequest.md`).
