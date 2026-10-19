---
id: SPEC-atari-nio-physical-sio
companions:
  - wire-and-acceptance.md
sources:
  - repos/fujinet-nio/docs/architecture.md
  - repos/fujinet-nio/docs/build_profiles.md
  - repos/fujinet-nio/docs/disk_device_protocol.md
  - repos/fujinet-nio/docs/poc_altirrasdl_embedding.md
  - repos/fujinet-nio-lib/docs/transport-backends.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate.

# Atari NIO over Physical SIO

## Why

FujiNet-NIO needs Atari to be a first-class host alongside BBC, Amiga, and MS-DOS. A stock Atari must boot from an ATR supplied by its only FujiNet peripheral, then use the public NIO API for the same FujiBus services available on other hosts.

## Capabilities

- **CAP-1**
  - **intent:** Atari SIO provides a defined NIO application channel and a separate standard disk frontend while keeping their protocols and routing isolated.
  - **success:** Independent fixtures prove the `0x7F` NIO `W`/`P`/`R` contract and Atari OS-compatible `D1:`–`D8:` sector exchanges, including boot from the selected ATR, and route each only to its intended core contract.

- **CAP-2**
  - **intent:** Atari software uses the public `fujinet-nio-lib` API through a supported backend, and configuration software selects URI-backed Atari disk units.
  - **success:** A cc65 XEX on the flashed configuration ATR builds and demonstrates public-API NIO exchanges; `fujinet-nio-config` maps configured URIs to `D1:`–`D8:` without application SIO framing code.

- **CAP-3**
  - **intent:** An official Atari FujiNet v1 ESP32 board reliably provides standard-speed physical SIO for boot disks and NIO application traffic.
  - **success:** The documented 16 MB Atari profile builds, flashes, boots the configuration ATR as `D1:`, and passes physical timing, recovery, and service acceptance on a real Atari.

- **CAP-4**
  - **intent:** Maintainers can regress Atari NIO and disk-bootstrap behavior without requiring physical hardware for every change.
  - **success:** Shared fixtures, disk boot, and the guest acceptance program run through AltirraSDL and NetSIO, with evidence explicitly distinguished from physical-bus proof.

- **CAP-5**
  - **intent:** An operator can install, configure, diagnose, and verify Atari FujiNet-NIO on official hardware.
  - **success:** Documentation covers the selected profile, flashing, boot-mode selection, URI-to-drive mapping, diagnostics, and the real-hardware acceptance matrix.

- **CAP-6**
  - **intent:** Atari BASIC can use a native NIO network device with `N1:`-style supported URIs.
  - **success:** The supported startup/config ATR installs a CIO `N:` handler; a BASIC program opens a supported URI, performs stream I/O and status through NetworkService, then closes it, with proof that the handler uses only the public NIO client and `0x7F`.

## Constraints

- `0x7F` is permanently reserved for the NIO application channel; it is an SIO address, never a FujiBus service ID. A collision reports NIO unavailable without fallback or discovery.
- The NIO channel carries packet-native FujiBus, not SLIP. Every wire-revision-1 device supports `W` and `R` exact packet sizes up to the shared, compile-time 512-byte baseline limit; oversized packets fail explicitly and are never implicitly segmented. An application may optionally issue fixed-size `Q` to discover the device maximum, but no application is required to do so. A smaller capacity requires a new wire revision/profile and may not be advertised as v1.
- `P` is a fixed three-byte NIO readiness/length poll: byte 0 is `0` idle, `1` pending, or `2` ready; its little-endian length is nonzero only when ready. `NAK` denotes only malformed or rejected transport transactions, never a pending response.
- Atari `D1:`–`D8:` disk transactions are a purpose-built standard SIO frontend that composes the existing `DiskService` directly; it shares slot/media state, but no framing or routing, with the `0x7F` FujiBus path through `DiskDevice`.
- Config mode prepares the flashed configuration ATR as the `D1:` candidate; normal mode restores configured URI-backed disk slots. The boot disk contains the cc65 XEX configuration and acceptance programs.
- The supported startup/config ATR installs a native Atari CIO `N:` handler resident below adjusted `MEMLO` and registered in `HATABS`. Same-handler installation is idempotent; a different existing `N:` handler is a reported collision, never overwritten. CIO `OPEN` calls public `fn_open` and associates its returned `fn_handle_t` with the Atari IOCB; GET, PUT, STATUS, and CLOSE call public `fn_read`, `fn_write`, `fn_info`, and `fn_close` for that handle. `N1:` is user-facing syntax, not a network-slot protocol; capacity is the existing library session limit. The handler uses neither legacy SIO network IDs nor legacy command encodings.
- Native `N:` installation calls `fn_init` before making the handler usable and rolls back on failure. It maps CIO read/write/update opens to public `fn_open` GET/PUT/POST; write/update sets `FN_OPEN_BODY_UNKNOWN`. It uses a bounded 128-byte cache per open IOCB for byte-stream GET/PUT, maps STATUS through `fn_info`, and flushes then commits a write/update body exactly once with zero-length `fn_write` before first STATUS, read, or CLOSE. CLOSE then calls `fn_close`. It uses neither dynamic allocation nor retry beyond the existing `fn_write` library policy.
- PROC is opt-in and application-owned. The library supplies only an ISR-safe notification hook and remains polling-correct; it never installs or replaces an Atari IRQ handler.
- Physical v1 NIO requires CMD and UART data lines at 19,200 baud. Board-driven data output and PROC are released-idle open-drain; INT, MTR, CKI, and CKO are electrically benign and have no NIO semantics.
- Shared wire fixtures are independent of production framing code. Every repository changed by implementation follows the workspace test policy; a `fujinet-nio-lib` change requires complete `make check`.

## Non-goals

- `LegacyTransport`, legacy FujiNet framing, and compatibility with old FujiNet Atari software.
- Legacy FujiNet device/configuration adapters, legacy `N:`/`R:` wire behavior, proprietary legacy commands, or extending their device mappings. This does not exclude the separately defined native NIO CIO `N:` handler.
- SLIP framing or a stream transport on the Atari NIO application channel.
- High-speed SIO support or treating AltirraSDL/NetSIO results as electrical or timing proof.

## Success signal

A real Atari boots the selected ATR from an official FujiNet v1 as `D1:`, runs a public-API Atari NIO program, and uses the native BASIC `N:` handler for a verified NetworkService URI exchange alongside Clock, File, and Disk responses. The same defined NIO, disk, BASIC-handler, and recovery exchanges reproduce in AltirraSDL and NetSIO; the physical run separately records its electrical, timing, and PROC/polling evidence.

## Assumptions

- The configured workspace `project-context.md` was absent while this spec was created; listed source documents provide the current evidence base.
