# fujinet-nio-workspace

Workspace and build orchestration for the **FujiNet NIO** product (the
`fujinet-nio` adapter/runtime repo is one component, not the whole stack).

This repository owns no product source code. It pins the related repositories as
submodules and provides one place to set environment variables, build the stack,
create images, and record exactly which commits were used.

## Repository Layout

Product and integration repos (see `.gitmodules` and `repos/` for the source of
truth):

```text
fujinet-nio-workspace/
  repos/
    fujinet-nio/                 # adapter/runtime
    fujinet-nio-lib/             # client library
    fujinet-nio-driver/          # MS-DOS + Amiga native drivers
    nio-core-apps/               # portable F* utilities
    nio-config/                  # config-nio
    nio-apps/                    # examples / diagnostics
    fn-rom/                      # BBC/Master native ROM + boot utils
    fujinet-qemu-msdos/
    bounce-world-client-nio/
    cc65/  cc65-clib/            # toolchains
    AltirraSDL/  fujinet-emulator-bridge/  qemu-msdos-init/
  external/
    palmdev-toolchain/           # Palm OS toolchain by another project; opt-in, see below
    PDCurses/                    # curses library for the MS-DOS nio-config; opt-in, see below
    vice-fn/                     # VICE that reaches FujiNet's C64 devices, for the C64 tests; opt-in
  scripts/
  docs/
  backlog/
  completed/
  build/                         # gitignored
  local/                         # gitignored config
```

`build/` and `local/config.env` are intentionally ignored.

## Clone

```sh
git clone --recurse-submodules <workspace-url>
cd fujinet-nio-workspace
```

For an existing clone:

```sh
scripts/update-all.sh
```

### Palm OS toolchain (optional)

Everything under `repos/` is NIO's own. `external/` holds other people's tools
that NIO uses but does not control. They are pinned like any submodule, cloned
over https with no fork, and opt-in: a normal `--recurse-submodules` clone and
`scripts/update-all.sh` skip them, so nobody downloads a toolchain they do not need.

To build the Palm OS targets of `fujinet-nio-lib`:

```sh
git submodule update --init external/palmdev-toolchain
cd external/palmdev-toolchain && ./setup.sh   # interactive: you supply the Palm and Handspring SDKs
cd ../.. && source scripts/env.sh             # exports PALMDEV_TOOLCHAIN
cd repos/fujinet-nio-lib && make check-palmos
```

`make check` does not need any of this. The SDKs are not part of NIO; the toolchain's
installer asks for them. Docker (or native prc-tools) is required.

### PDCurses (MS-DOS nio-config)

The MS-DOS `nio-config` links PDCurses, which `scripts/build-pdcurses-msdos.sh` builds
(Open Watcom required) into `build/pdcurses/`:

```sh
git submodule update --init external/PDCurses
scripts/build-pdcurses-msdos.sh
```

### VICE for the C64 tests

The C64 acceptance test and `scripts/c64-run` need `vice-fn`, a fork of VICE whose
real-device support reaches the firmware's IEC devices over NetIEC; stock VICE can't.
`scripts/build-vice-fn.sh` builds it into `build/vice-fn/`:

```sh
git submodule update --init external/vice-fn
scripts/build-vice-fn.sh
```

What it needs, and what the test proves: `integration-tests/c64-iec/README.md`.

### Reference checkouts

`reference/` is gitignored and holds look-at-only repositories that are not part of
NIO. Put anything you want to read beside the code there; nothing in the build uses it.

To work on your own forks of the submodules, and for what a workspace pull
request may contain, see [CONTRIBUTING.md](CONTRIBUTING.md).

To move submodules to their configured remote branches:

```sh
scripts/update-all.sh --remote
git status
```

Review and commit the changed submodule pointers in this workspace repo when you
want to pin a new integrated stack.

## Environment

Every script sources:

```sh
scripts/env.sh
```

The defaults point at the submodules:

```sh
FUJINET_NIO=repos/fujinet-nio
FUJINET_NIO_LIB=repos/fujinet-nio-lib
FUJINET_NIO_DRIVER=repos/fujinet-nio-driver
NIO_CORE_APPS=repos/nio-core-apps
NIO_CONFIG=repos/nio-config
NIO_APPS=repos/nio-apps
FN_ROM_HOME=repos/fn-rom
FUJINET_QEMU_MSDOS=repos/fujinet-qemu-msdos
BOUNCE_WORLD_CLIENT_NIO=repos/bounce-world-client-nio
```

Override any of them in `local/config.env`:

```sh
export FUJINET_NIO=$HOME/dev/nio/repos/fujinet-nio
export FUJINET_NIO_LIB=$HOME/dev/nio/repos/fujinet-nio-lib
export NIO_APPS=$HOME/dev/nio/repos/nio-apps
export FUJINET_NIO_DRIVER=$HOME/dev/nio/repos/fujinet-nio-driver
```

`env.sh` also sets up Open Watcom for the workspace scripts: it uses an install
the caller has already configured (`WATCOM`, as the CI setup action does) and
otherwise `/opt/watcom`.

Amiga builds use `m68k-amigaos-gcc` from `/opt/amiga/bin` by default. Override
that location with `AMIGA_TOOLCHAIN_BIN` in `local/config.env` if needed.

## Build

Build the usual integrated stack:

```sh
scripts/build.sh all
```

The main workspace targets are platform workflows:

```sh
scripts/build.sh bbc
scripts/build.sh master
scripts/build.sh msdos
scripts/build.sh atari
scripts/build.sh linux
scripts/build.sh amiga
```

Run the host-side `fujinet-nio-lib` wire tests with:

```sh
scripts/build.sh lib-tests
```

List the available targets with:

```sh
scripts/build.sh --list
scripts/build.sh --list --all
scripts/build.sh --explain bbc
```

Disk and image build ownership is documented in
[docs/disk-image-builds.md](docs/disk-image-builds.md). Start there when
deciding whether a disk recipe belongs in a sub-repo or the workspace.
The workflow-oriented build surface is documented in
[docs/build-orchestration.md](docs/build-orchestration.md).

`scripts/build.sh` is now a thin wrapper around the Python build front end in
`tools/build/nio_build`.

`scripts/build.sh all` runs the platform workflows. That covers:

- host/Linux fujinet-nio TCP, PTY, and RS-232 presets
- BBC and Master cc65/cc65-clib prerequisites, config disks, and boot disks
- MS-DOS driver, core apps, config app, boot/config disks, and QEMU image
- Atari libraries, apps, boot disk, and emulator-side FujiNet build
- Amiga `fujinet-nio-lib`, `nio-apps`, and `nio-core-apps` applications

Legacy aliases remain available under `--list --all` pending the compatibility
audit tracked in `backlog/build-orchestration-followups.md`:

```sh
scripts/build.sh msdos-image
scripts/build.sh apps-image
scripts/build.sh qemu-image
```

To build a mountable MS-DOS utility disk containing the current
`FUJINET.SYS` plus `config-nio` and the command-line tools:

```sh
scripts/build.sh msdos-boot-config-image
```

The QEMU image builder defaults to `repos/fujinet-qemu-msdos/msdos.qcow2`.
Set `BASE_IMAGE` only when you want to use a different base image:

```sh
BASE_IMAGE=/path/to/base-dos.qcow2 scripts/build.sh qemu-msdos-image
```

## QEMU

After building the TCP fujinet binary and a QEMU image:

```sh
scripts/build.sh qemu-run
```

Additional arguments are passed to `run-qemu-nio`:

```sh
scripts/build.sh qemu-run -- --hda repos/fujinet-qemu-msdos/build/msdos-nio-apps.qcow2
```

For MS-DOS NIO app UI work, use the terminal/curses feedback loop:

```sh
scripts/build.sh msdos-dev-curses
```

That ensures the POSIX TCP FujiNet exists, builds `FUJINET.SYS`, MS-DOS apps,
the boot disks, the QEMU image, then runs QEMU with `--display curses`. See
[docs/msdos/qemu-nio-curses.md](docs/msdos/qemu-nio-curses.md).

While QEMU is running, drive keys through the QEMU monitor from another terminal:

```sh
scripts/build.sh qemu-monitor type CONFNIO ret
scripts/build.sh qemu-monitor sendkey q
```

## Status And Manifest

Show workspace and submodule state:

```sh
scripts/status-all.sh
```

Each build writes:

```text
build/manifest.txt
```

The manifest records the workspace path, submodule commits, dirty markers, and
important output paths. It is meant to catch stale binaries and image mismatches.

## Notes

- Subprojects remain independently buildable. The workspace only supplies a
  common environment and build order.
- `nio-docs` currently has no remote configured in its source checkout, so its
  submodule URL is a local relative path. Update `.gitmodules` when it has a
  remote.
- If you are actively editing original checkouts outside the workspace,
  set those paths in `local/config.env` so the workspace builds your working
  trees rather than the pinned submodule clones.
