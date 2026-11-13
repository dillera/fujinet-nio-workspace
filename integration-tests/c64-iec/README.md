# C64 boot acceptance in VICE

`run_boot_acceptance.py` takes a C64 with a stock KERNAL, in VICE, through what a person
does with FujiNet NIO. It lists the boot disk, loads and runs the config app, runs the demo
from it, adds a TNFS host, browses it, and assigns a D64 and a loose PRG. Then it boots, and
loads and runs a program from each. Every screen is saved as text and as a PNG, with the
firmware, VICE and TNFS logs, in `test-evidence/c64-iec/<time>/`.

From the workspace root:

```sh
source scripts/env.sh
git submodule update --init external/vice-fn   # once: VICE, see below
scripts/build-vice-fn.sh headless              # once
./scripts/build.sh c64
python3 integration-tests/c64-iec/run_boot_acceptance.py
```

It prints each step, then `PASS` or `FAIL` with the evidence folder. It exits 0 on a
pass, 1 on a failure, and 2 when something it needs is missing.

## What it needs

- **Docker**, for `tnfsd`: the `zaqu/tnfsd` image the firmware's test services use, pinned
  by digest. The test reaches it over TCP, because Docker Desktop's published UDP ports
  don't reach the daemon on macOS.
- **The `vice-fn` build of VICE**, from the opt-in `external/vice-fn` submodule (below).
  Stock VICE can't reach the firmware.
- **The firmware**, `repos/fujinet-nio/build/c64-netiec-debug/fujinet-nio`.
- **The boot disk**, `repos/nio-core-apps/build/c64/disk/boot/autorun.d64`, which holds
  the config app and the demo. `./scripts/build.sh c64` builds it and the firmware. It needs
  cc65, and Python with PyYAML.

`--firmware`, `--boot-disk`, `--vice-root` and `--vice-build` point it elsewhere. `--window`
uses the SDL build so you can watch. `--netiec-port` and `--monitor-port` let it run beside
another VICE.

## vice-fn

Stock VICE can hand units 8-11 to a real drive through OpenCBM, from its KERNAL traps. The
`vice-fn` branch of [dillera/vice-fn](https://github.com/dillera/vice-fn), a fork of
VICE-Team/svn-mirror, makes units 12-30 real devices too, and carries 5-bit device numbers
through the traps, so device 30, NIO's packet channel, is reachable. It also adds
`fujinet/opencbm-netiec`, an OpenCBM library that carries those calls to NetIEC over TCP,
which is what the firmware's `c64-netiec` presets serve.

`external/vice-fn` pins that fork at `7f4e5520f2`, where this test last passed. The VICE
source change is `65abb661a3`, "Let real devices use units 12-30 through the KERNAL traps".
Like everything under `external/`, it's opt-in: a normal `--recurse-submodules` clone and
`scripts/update-all.sh` skip it. To get it and build it:

```sh
git submodule update --init external/vice-fn
scripts/build-vice-fn.sh                       # both UIs; or name one: headless, sdl2
```

The script runs VICE's `autogen.sh` in the checkout, configures each UI out of tree, and
builds the `opencbm-netiec` bridge. A rerun only rebuilds what changed.

```text
build/vice-fn/headless   --enable-headlessui: what the test uses
build/vice-fn/sdl2       --enable-sdl2ui: for --window and scripts/c64-run
```

It needs autoconf, automake, pkg-config, xa, dos2unix and GNU bison, and SDL2 and
SDL2_image for the window. On macOS:
`brew install autoconf automake pkgconf xa dos2unix bison sdl2 sdl2_image`. It has only
been built and run on macOS.

`autogen.sh` leaves its output in the checkout as untracked files; `ignore = untracked` in
`.gitmodules` keeps them out of the workspace's `git status`. `VICE_FN_ROOT` and
`VICE_FN_BUILD`, which `scripts/env.sh` sets to `external/vice-fn` and `build/vice-fn`,
point the script, the test and `scripts/c64-run` at another checkout or build.

## What it proves, and what it can't

It covers everything above the bus's electrical behaviour, on a stock KERNAL: the drive's
directory, LOAD and status channel, NIO's packet channel on device 30 (the config app, and
the demo's clock), mounting from TNFS through `DiskService`, D64 and loose PRG media, and
booting from the config app.

It says nothing about **bus timing**. VICE hooks the KERNAL's serial routines, and each
makes one NetIEC request, so no line is ever driven. That also means a real drive sharing
the bus can't be modelled, and JiffyDOS and fast loaders, which bypass those routines, are
out of reach. Nothing here has run on a real C64.

## The helpers' own tests

`tools/c64_emulator` drives VICE through its binary monitor. Its pure functions have
tests:

```sh
python3 -m pytest tools/c64_emulator/tests
```

`scripts/c64-run` starts the same firmware and boot disk in a VICE window, to use by hand.
