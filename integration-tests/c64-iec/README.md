# C64 boot acceptance in VICE

`run_boot_acceptance.py` takes a C64 with a stock KERNAL, in VICE, through what a person
does with FujiNet NIO. It lists the boot disk, loads and runs the config app, runs the demo
from it, adds a TNFS host, browses it, and assigns a D64 and a loose PRG. Then it boots, and
loads and runs a program from each. Every screen is saved as text and as a PNG, with the
firmware, VICE and TNFS logs, in `test-evidence/c64-iec/<time>/`.

From the workspace root:

```sh
source scripts/env.sh
export VICE_FN_ROOT=~/vice-fn          # see below
./scripts/build.sh c64
python3 integration-tests/c64-iec/run_boot_acceptance.py
```

It prints each step, then `PASS` or `FAIL` with the evidence folder. It exits 0 on a
pass, 1 on a failure, and 2 when something it needs is missing.

## What it needs

- **Docker**, for `tnfsd`: the `zaqu/tnfsd` image the firmware's test services use, pinned
  by digest. The test reaches it over TCP, because Docker Desktop's published UDP ports
  don't reach the daemon on macOS.
- **The `vice-fn` build of VICE**, with `VICE_FN_ROOT` set to it (below).
- **The firmware**, `repos/fujinet-nio/build/c64-netiec-debug/fujinet-nio`.
- **The boot disk**, `repos/nio-core-apps/build/c64/disk/boot/autorun.d64`, which holds
  the config app and the demo. `./scripts/build.sh c64` builds it and the firmware. It needs
  cc65, and Python with PyYAML.

`--firmware`, `--boot-disk` and `--vice-root` point it elsewhere. `--window` uses the SDL
build so you can watch. `--netiec-port` and `--monitor-port` let it run beside another VICE.

## vice-fn

Stock VICE can hand units 8-11 to a real drive through OpenCBM, from its KERNAL traps. The
`vice-fn` branch of [dillera/vice-fn](https://github.com/dillera/vice-fn), a fork of
VICE-Team/svn-mirror, makes units 12-30 real devices too, and carries 5-bit device numbers
through the traps, so device 30, NIO's packet channel, is reachable. It also adds
`fujinet/opencbm-netiec`, an OpenCBM library that carries those calls to NetIEC over TCP,
which is what the firmware's `c64-netiec` presets serve.

This test last passed at `7f4e5520f2`. The VICE source change is `65abb661a3`, "Let real
devices use units 12-30 through the KERNAL traps".

`VICE_FN_ROOT` is a folder holding the clone and its builds:

```text
$VICE_FN_ROOT/svn-mirror       the clone, on the vice-fn branch
$VICE_FN_ROOT/build-headless   --enable-headlessui: what the test uses
$VICE_FN_ROOT/build-sdl2       --enable-sdl2ui: for --window and scripts/c64-run
```

On macOS (`brew install xa dos2unix bison`):

```sh
git clone --branch vice-fn --single-branch https://github.com/dillera/vice-fn.git "$VICE_FN_ROOT/svn-mirror"
(cd "$VICE_FN_ROOT/svn-mirror/vice" && ./autogen.sh)
for ui in headless sdl2; do
  mkdir -p "$VICE_FN_ROOT/build-$ui"
  (cd "$VICE_FN_ROOT/build-$ui" &&
   ../svn-mirror/vice/configure --enable-${ui}ui --disable-pdf-docs --disable-html-docs \
       YACC="$(brew --prefix bison)/bin/bison -y" &&
   make -j)
done
```

The launcher, `svn-mirror/fujinet/run-vice-fujinet.sh`, builds the bridge the first time it
runs. It has only been built and run on macOS.

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
