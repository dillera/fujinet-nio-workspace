#!/usr/bin/env bash
# Builds vice-fn, the fork of VICE the C64 tests use, from the opt-in external/vice-fn
# submodule (integration-tests/c64-iec/README.md).
#
#   scripts/build-vice-fn.sh [headless|sdl2]...      (default: both)
#
# headless is what run_boot_acceptance.py runs; sdl2 is the window, for its --window and
# for scripts/c64-run. Each is configured out of tree in $VICE_FN_BUILD/<ui> (default
# build/vice-fn/<ui>), so a rerun only rebuilds what changed. Then it builds the
# opencbm-netiec bridge that carries VICE's real-device calls to the firmware.
#
# Needs autoconf, automake, pkg-config, xa, dos2unix and GNU bison, and SDL2 and
# SDL2_image for sdl2. On macOS: brew install autoconf automake pkgconf xa dos2unix bison sdl2 sdl2_image
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
source "$SCRIPT_DIR/env.sh"

if [ ! -x "$VICE_FN_ROOT/vice/autogen.sh" ]; then
  echo "vice-fn not found at $VICE_FN_ROOT." >&2
  echo "Get the pinned copy: git submodule update --init external/vice-fn" >&2
  exit 1
fi

uis=("$@")
[ ${#uis[@]} -gt 0 ] || uis=(headless sdl2)
for ui in "${uis[@]}"; do
  case "$ui" in
    headless|sdl2) ;;
    *) echo "build-vice-fn: unknown UI '$ui': headless or sdl2" >&2; exit 2 ;;
  esac
done

# VICE needs GNU bison 3; macOS ships an older one, and Homebrew's isn't on the PATH.
yacc=()
if command -v brew >/dev/null 2>&1; then
  bison_prefix=$(brew --prefix bison 2>/dev/null || true)
  if [ -x "$bison_prefix/bin/bison" ]; then
    yacc=("YACC=$bison_prefix/bin/bison -y")
  fi
fi

# autogen.sh writes configure and the Makefile.in files into the checkout, where
# .gitmodules (ignore = untracked) keeps them out of the workspace's git status.
if [ ! -x "$VICE_FN_ROOT/vice/configure" ]; then
  (cd "$VICE_FN_ROOT/vice" && ./autogen.sh)
fi

jobs=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)
for ui in "${uis[@]}"; do
  build="$VICE_FN_BUILD/$ui"
  mkdir -p "$build"
  if [ ! -f "$build/Makefile" ]; then
    (cd "$build" &&
     "$VICE_FN_ROOT/vice/configure" "--enable-${ui}ui" --disable-pdf-docs --disable-html-docs \
       ${yacc[@]+"${yacc[@]}"})
  fi
  make -C "$build" -j"$jobs"
  echo "Built $build/src/x64sc"
done

make -C "$VICE_FN_ROOT/fujinet/opencbm-netiec"
