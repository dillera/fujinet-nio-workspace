# Atari NIO Physical SIO — Epic 1 Context: Atari boots and uses NIO-backed ATR drives

<!-- Feature-qualified derived context. Regenerate only from the Atari planning artifacts. -->

## Goal

Establish the standard Atari disk experience needed for FujiNet-NIO: a selected configuration ATR boots as `D1:`, and normal operation exposes restored URI-backed ATR slots through `D1:`–`D8:`. Literal, independent disk and boot scenarios are the conformance authority before an adapter exists, without conflating the disk plane with native `0x7F` traffic or physical-bus proof.

## Stories

- Story 1.1: Freeze Atari ATR disk conformance fixtures
- Story 1.2: Serve standard Atari ATR drives through DiskService
- Story 1.3: Boot the selected configuration or mapped ATR disk

## Requirements & Constraints

Standard Atari disk device IDs `D1:` through `D8:` select their corresponding runtime `DiskService` slots. The v1 surface is ATR-backed boot and mounted-media read, write, and status only; it fixes commands, one-based sector numbering, byte counts, boot geometry, protection/status/error results, invalid requests, and config-versus-normal slot choice.

In config mode, `boot.config_uri` prepares the active `D1:` candidate. In normal mode, restored URI-backed slots determine `D1:`–`D8:`. The configuration ATR contains the configuration and acceptance programs and does not rely on legacy FujiNet services.

Formatting, PERCOM, high-speed SIO, non-ATR media, legacy transport/framing, proprietary legacy commands, and legacy Atari compatibility paths are excluded. Virtual conformance is protocol regression evidence only, never electrical or timing proof.

The fixture story creates the matrix plus literal vectors/manifests for boot, mounted read/write/status, malformed or invalid disk requests, and config/restored-slot selection. Fixtures are independent expectations rather than production-framer output. Every future firmware, NetSIO, or AltirraSDL projection reports the shared scenario identifier.

## Technical Decisions

At the SIO boundary, only `0x7F` routes to native NIO and only `D1:`–`D8:` route to standard disk handling; other device IDs are ignored. Disk traffic composes `DiskService` directly, while `DiskDevice` remains the distinct FujiBus wrapper. Disk traffic must not pass through FujiBus framing or `LegacyTransport`.

Workspace-owned `integration-tests/atari-sio` is the single authority for literal vectors and scenario manifests. Production implementations consume projections from it but may not use a production serializer or framer as fixture oracle. AltirraSDL and NetSIO are independent conformance adapters, not substitutes for hardware.

## Cross-Story Dependencies

Story 1.1 freezes the command, sector, geometry, status/error, boot, and routing expectations used by Stories 1.2 and 1.3. Story 1.2 establishes direct `DiskService` disk handling. Story 1.3 applies boot policy and packages reproducible media. Epic 2 shares DiskService slot state but cannot alter this disk contract or use disk SIO as a FujiBus selector.
