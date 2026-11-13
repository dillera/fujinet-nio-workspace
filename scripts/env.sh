#!/usr/bin/env bash

# avoid zd/zoxide/z interfering with cd functionality via aliases in shell
CD=cd

# Append an optional tool directory to PATH. A missing directory is not an
# error: scripts source this file under `set -e`, where a non-zero return
# would silently abort them on machines without that toolchain (e.g. CI).
pathadd_end() {
  [ -d "$1" ] || return 0
  [[ ":$PATH:" == *":$1:"* ]] || export PATH="$PATH:$1"
}

workspace_dir() {
  local src="${BASH_SOURCE[0]}"

  while [ -L "$src" ]; do
    local dir
    dir="$(${CD} -P "$(dirname "$src")" && pwd)" || return 1
    src="$(readlink "$src")" || return 1

    case "$src" in
      /*) ;;
      *) src="$dir/$src" ;;
    esac
  done

  ${CD} -P "$(dirname "$src")/.." && pwd
}

setup_nio_environment() {
  local workspace

  if [[ -n ${NIO_WORKSPACE:-} ]]; then
    workspace="$NIO_WORKSPACE"
  else
    workspace="$(workspace_dir)" || return 1
  fi

  export NIO_WORKSPACE="$workspace"
  export FUJINET_NIO="$NIO_WORKSPACE/repos/fujinet-nio"
  export FUJINET_NIO_LIB="$NIO_WORKSPACE/repos/fujinet-nio-lib"
  export NIO_APPS="$NIO_WORKSPACE/repos/nio-apps"
  export NIO_CORE_APPS="$NIO_WORKSPACE/repos/nio-core-apps"
  export NIO_CONFIG="$NIO_WORKSPACE/repos/nio-config"
  export FUJINET_QEMU_MSDOS="$NIO_WORKSPACE/repos/fujinet-qemu-msdos"
  export FUJINET_NIO_DRIVER="$NIO_WORKSPACE/repos/fujinet-nio-driver"
  export FUJINET_LIB="$NIO_WORKSPACE/repos/fujinet-lib"
  # fn-rom checkout. FN_ROM itself is left for the ROM image, which is what
  # the Beebium test runners (fn-rom, fujinet-nio-lib, nio-config) read it as.
  export FN_ROM_HOME="${FN_ROM_HOME:-$NIO_WORKSPACE/repos/fn-rom}"
  export BOUNCE_WORLD_CLIENT_NIO="$NIO_WORKSPACE/repos/bounce-world-client-nio"
  export BOUNCE_WORLD="$BOUNCE_WORLD_CLIENT_NIO"
  export CC65_HOME="$NIO_WORKSPACE/repos/cc65"
  export CC65_ROOT="${CC65_ROOT:-$CC65_HOME}"
  export CC65_SRC="${CC65_SRC:-$CC65_ROOT}"
  export CC65_CLIB="$NIO_WORKSPACE/repos/cc65-clib"
  export QEMU_MSDOS_INIT="$NIO_WORKSPACE/repos/qemu-msdos-init"
  # Opt-in third-party tools: git submodule update --init external/<name>
  export PALMDEV_TOOLCHAIN="${PALMDEV_TOOLCHAIN:-$NIO_WORKSPACE/external/palmdev-toolchain}"
  export PDCURSES_DIR="${PDCURSES_DIR:-$NIO_WORKSPACE/external/PDCurses}"
  # vice-fn, the VICE the C64 tests use; scripts/build-vice-fn.sh builds it into VICE_FN_BUILD.
  export VICE_FN_ROOT="${VICE_FN_ROOT:-$NIO_WORKSPACE/external/vice-fn}"

  if [ -f "$NIO_WORKSPACE/local/config.env" ]; then
    # shellcheck source=/dev/null
    source "$NIO_WORKSPACE/local/config.env"
  fi
  # Older local/config.env files set FN_ROM to the fn-rom checkout.
  if [[ -d ${FN_ROM:-} ]]; then
    export FN_ROM_HOME="$FN_ROM"
    unset FN_ROM
  fi

  # amiga-gcc is commonly installed by the official cross-toolchain bundle.
  # Keep the location configurable for developers using a different install.
  export AMIGA_TOOLCHAIN_BIN="${AMIGA_TOOLCHAIN_BIN:-/opt/amiga/bin}"
  pathadd_end "$AMIGA_TOOLCHAIN_BIN"
  
  export NIO_BUILD_DIR="${NIO_BUILD_DIR:-$NIO_WORKSPACE/build}"
  export NIO_LOG_DIR="${NIO_LOG_DIR:-$NIO_BUILD_DIR/logs}"
  export NIO_IMAGE_DIR="${NIO_IMAGE_DIR:-$NIO_BUILD_DIR/images}"
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$NIO_BUILD_DIR/uv-cache}"
  export UV_TOOL_DIR="${UV_TOOL_DIR:-$NIO_BUILD_DIR/uv-tools}"
  
  export FUJINET_NIO_TCP_DEBUG_BIN="${FUJINET_NIO_TCP_DEBUG_BIN:-$FUJINET_NIO/build/fujibus-tcp-debug/fujinet-nio}"
  export FUJINET_NIO_TCP_RELEASE_BIN="${FUJINET_NIO_TCP_RELEASE_BIN:-$FUJINET_NIO/build/fujibus-tcp-release/fujinet-nio}"
  export FUJINET_NIO_ATARI_FUJIBUS_NETSIO_BIN="${FUJINET_NIO_ATARI_FUJIBUS_NETSIO_BIN:-$FUJINET_NIO/build/atari-fujibus-netsio-debug/fujinet-nio}"
  export AMIBERRY_BIN="${AMIBERRY_BIN:-amiberry}"
  export AMIGA_ENV_ROOT="${AMIGA_ENV_ROOT:-$NIO_BUILD_DIR/amiga-envs}"
  export AMIGA_WORKBENCH_CONFIG_FILE="${AMIGA_WORKBENCH_CONFIG_FILE:-$NIO_WORKSPACE/configs/amiga/workbenches.yaml}"
  # Source local/amiga.env for licensed media paths (gitignored, never committed).
  if [[ -f "$NIO_WORKSPACE/local/amiga.env" ]]; then
    # shellcheck disable=SC1090
    source "$NIO_WORKSPACE/local/amiga.env"
  fi
  export AMIGA_WORKBENCH_CONFIG="${AMIGA_WORKBENCH_CONFIG:-}"
  export AMIBERRY_HOST="${AMIBERRY_HOST:-127.0.0.1}"
  export AMIBERRY_PORT="${AMIBERRY_PORT:-23462}"
  export FUJINET_NIO_AMIGA_BIN="${FUJINET_NIO_AMIGA_BIN:-$FUJINET_NIO_TCP_DEBUG_BIN}"
  export AMIGA_TEST_APP="${AMIGA_TEST_APP:-wifitest}"
  export AMIGA_TEST_PROJECT="${AMIGA_TEST_PROJECT:-apps}"
  export AMIGA_TEST_COMMAND="${AMIGA_TEST_COMMAND:-$AMIGA_TEST_APP}"
  export AMIGA_TEST_INTERACTIVE="${AMIGA_TEST_INTERACTIVE:-0}"
  export AMIGA_TEST_DISK="${AMIGA_TEST_DISK:-$NIO_BUILD_DIR/images/amiga-$AMIGA_TEST_APP.hdf}"
  export ALTIRRA_WORKSPACE_BIN="${ALTIRRA_WORKSPACE_BIN:-$NIO_WORKSPACE/repos/AltirraSDL/build/linux-debug/src/AltirraSDL/AltirraSDL}"
  export FUJINET_EMULATOR_BRIDGE="${FUJINET_EMULATOR_BRIDGE:-$NIO_WORKSPACE/repos/fujinet-emulator-bridge}"
  export ATARI_DOS_BOOT_DISK="${ATARI_DOS_BOOT_DISK:-$HOME/dev/atari/fujinet-apps/netcat/atari/ados20d.atr}"
  
  export NIO_APPS_MSDOS_BIN="${NIO_APPS_MSDOS_BIN:-$NIO_APPS/build/msdos/bin}"
  export NIO_APPS_ATARI_BIN="${NIO_APPS_ATARI_BIN:-$NIO_APPS/build/atari/bin}"
  export NIO_CORE_APPS_MSDOS_BIN="${NIO_CORE_APPS_MSDOS_BIN:-$NIO_CORE_APPS/build/msdos/bin}"
  export NIO_CORE_APPS_ATARI_BIN="${NIO_CORE_APPS_ATARI_BIN:-$NIO_CORE_APPS/build/atari/bin}"
  export NIO_CONFIG_MSDOS_BIN="${NIO_CONFIG_MSDOS_BIN:-$NIO_CONFIG/build/msdos/bin}"
  export NIO_CONFIG_ATARI_BIN="${NIO_CONFIG_ATARI_BIN:-$NIO_CONFIG/build/atari/bin}"
  export NIO_CONFIG_C64_BIN="${NIO_CONFIG_C64_BIN:-$NIO_CONFIG/build/c64/bin}"
  export VICE_FN_BUILD="${VICE_FN_BUILD:-$NIO_BUILD_DIR/vice-fn}"
  export FUJINET_NIO_C64_NETIEC_BIN="${FUJINET_NIO_C64_NETIEC_BIN:-$FUJINET_NIO/build/c64-netiec-debug/fujinet-nio}"
  export PDCURSES_MSDOS_LIB="${PDCURSES_MSDOS_LIB:-$NIO_BUILD_DIR/pdcurses/msdos-small/pdcurses.lib}"

  # Keep an Open Watcom install the caller already set up (e.g. the CI
  # setup-watcom action); otherwise use the default location.
  if [[ -z ${WATCOM:-} ]]; then
    export WATCOM=/opt/watcom
    export EDPATH=$WATCOM/eddat
    export INCLUDE=$WATCOM/h
  else
    export EDPATH="${EDPATH:-$WATCOM/eddat}"
    export INCLUDE="${INCLUDE:-$WATCOM/h}"
  fi
  pathadd_end "$WATCOM/binl64"
  pathadd_end "$WATCOM/binl"

  mkdir -p "$NIO_LOG_DIR" "$NIO_IMAGE_DIR" || return 1
}

setup_nio_environment
status=$?

unset -f setup_nio_environment

return "$status"

