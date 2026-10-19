---
title: 'Freeze Atari ATR disk conformance fixtures'
type: 'feature'
created: '2026-10-19'
status: 'draft'
review_loop_iteration: 0
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Atari disk boot and mounted ATR behavior has no implementation-independent contract, so firmware and virtual SIO work could reproduce incompatible or legacy behavior before an adapter exists.

**Approach:** Establish `integration-tests/atari-sio` as the canonical, literal source for a v1 disk matrix, scenario manifests, vectors, and a small self-validating projection format. Future firmware, NetSIO, and AltirraSDL adapters consume those stable scenario identifiers rather than generating their expectations from production framing code.

## Boundaries & Constraints

**Always:** Specify only standard Atari `D1:`–`D8:` boot and mounted ATR read, put/write, and status exchanges. Freeze device-to-slot routing, one-based sector numbering, boot-sector geometry/byte counts, response/status/error outcomes, config-mode `boot.config_uri` selection, and normal-mode restored-slot selection. Make every expected command, AUX/sector field, data length, checksum, reply phase, and payload literal or independently recomputed by the stdlib-only fixture validator. Give each scenario a stable identifier and label projections as virtual protocol evidence with no physical timing/electrical claim.

**Ask First:** Adding a v1 disk command beyond `0x50`/`0x52`/`0x53`/`0x57`; accepting a geometry other than classic 128- or 256-byte ATR; changing the frozen SIO reply/error semantics; making a production repository consume the projection; or redefining config/normal boot policy.

**Never:** Use `DiskDevice`, FujiBus, `LegacyTransport`, the current Atari SLIP/padded-read/`0x71` channel, or a production framer as fixture oracle. Do not add formatting, PERCOM, high-speed SIO, non-ATR media, NIO `0x7F` traffic, emulator integration, or any electrical/timing assertion.

## Normative Disk SIO v1 Contract

All vectors use the five literal command bytes `{device, command, AUX1, AUX2, checksum}`. `device` is `0x31`–`0x38`; `AUX1 | AUX2 << 8` is a one-based sector number for `0x50`, `0x52`, and `0x57`. The command and every data frame use Atari end-around-carry checksum: add each byte, fold each carry into the low byte, and store the final low byte. `A=0x41`, `N=0x4E`, `C=0x43`, and `E=0x45` are unchecksummed control replies.

| Command | Accepted sequence | Execution and terminal sequence |
| --- | --- | --- |
| `0x52` READ | valid command → `A` | resolve/lazy-mount slot; success → `C`, actual sector bytes, data checksum; failure → `E`, no data frame |
| `0x50` PUT | valid command → `A`; host sends actual sector bytes plus checksum | bad data checksum → `N`, no DiskService call; valid data → `A`; write and flush success → `C`, otherwise `E` |
| `0x57` WRITE WITH VERIFY | same receive sequence as `0x50` | after data `A`, write, flush, reread, and byte-compare the sector; match → `C`, otherwise `E` |
| `0x53` STATUS | valid command with AUX `0,0` → `A` | `C`, four status bytes, status checksum; it is available even when the selected slot is unavailable |

A malformed command frame or bad command checksum receives `N` and does not enter DiskService. A well-formed but unsupported command also receives `N`. A syntactically valid supported command with sector `0`, unsupported geometry, missing media, or an execution failure receives `A` then `E`; it is never conflated with a malformed frame. A disk device ID outside `D1:`–`D8:` is not this frontend's traffic.

`DiskError::NotMounted`, `NoSuchFileSystem`, `FileNotFound`, `OpenFailed`, `BadImage`, and `GeometryRequired` map to terminal `E`, STATUS `{0x04,0x80,0x00,0x00}`; `ReadOnly` maps to `E`, `{0x0C,0x00,0x00,0x00}`; `InvalidRequest`, `OutOfRange`, `InvalidSlot`, `InvalidGeometry`, `IoError`, and `InternalError` map to `E`, `{0x04,0x00,0x00,0x00}`. STATUS byte 0 is the Atari command-status bits: bit 0 command-frame, bit 1 data-checksum, bit 2 operation, bit 3 write-protect, bit 5 256-byte geometry. A ready writable slot reports `{0x00|geometry_bit,0x00,0x00,0x00}`; a read-only ready slot sets bit 3. Bits 0–2 describe the last disk exchange and must be covered by follow-up STATUS vectors.

The accepted ATR geometries are: 128-byte sectors with integral payload length, and classic 256-byte ATR where sectors 1–3 transfer 128 bytes and sectors 4 onward transfer 256 bytes. For the latter, payload bytes must be at least 384 and satisfy `(payload_bytes - 384) % 256 == 0`; its sector count is `3 + (payload_bytes - 384) / 256`. SIO sector `n` maps to DiskService LBA `n-1`; offsets after the 16-byte ATR header are `128*(n-1)` for 128-byte ATR and `0,128,256,384+256*(n-4)` for classic 256-byte ATR. Allocate to the maximum 256-byte supported sector size, but transmit and checksum only the actual `DiskResult.bytes` (128 for 256-byte ATR sectors 1–3). Ordinary 512-byte ATR geometry is rejected before sector execution.

The reference configuration medium is the reproducible `repos/fujinet-nio/distfiles/boot/atari/autorun.atr`, built by `make TARGET=atari boot-disk` in `repos/nio-core-apps` from `boot-disk/manifests/atari.yaml` and PicoBoot. It supplies the current configuration application bundle, not a named general-purpose DOS. v1 therefore supports both `0x50` and `0x57`: the former covers ordinary PUT callers and the latter matches the Atari resident disk handler's write-with-verify path. Story 1.3 must record a boot/launch command trace of the packaged ATR before claiming general DOS compatibility; untraced external DOS commands remain unsupported.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Boot read | `D1:` config ATR, sectors 1–3 and sector 4 | `0x52` vectors prove 128/256 transfer boundary, LBA, offset, checksum, and `A,C,data,sum` ordering | Missing media produces `A,E` then the frozen unavailable STATUS |
| Mounted I/O | Routed writable/read-only ATR slot, valid one-based sector | `0x50` and `0x57` cover distinct PUT/verify execution; `0x53` returns frozen four bytes | Rejected writes prove no write/flush or media mutation before a valid data checksum |
| Invalid request | Bad frame/checksum, unsupported command, zero/out-of-range sector, bad data checksum | Fixture distinguishes `N` rejection from `A,E` execution failure and records the subsequent STATUS | No DiskService/FujiBus fallback |
| Boot policy | Config mode versus normal restored slots | Config chooses only `boot.config_uri` for `D1:`; normal maps each `D1:`–`D8:` to its restored slot | Pending-mount success/failure vectors preserve the frozen slot error mapping |

</frozen-after-approval>

## Code Map

- `integration-tests/atari-sio/` -- new workspace-owned canonical fixture root; it is deliberately the authority before any production adapter is added.
- `repos/fujinet-nio/src/lib/disk/atr_image.cpp:17` -- existing ATR-geometry reference: sectors 1–3 are 128 bytes for a 256-byte base ATR. It is not a fixture oracle; its small-256-byte count arithmetic is covered by negative fixture cases.
- `repos/fujinet-nio/src/lib/disk/disk_service.cpp:612` -- lazy mount boundary; frontend calls DiskService and maps its result, rather than resolving URIs or accessing image files itself.
- `repos/nio-core-apps/boot-disk/manifests/atari.yaml:1` -- reproducible current configuration-ATR content inventory; Story 1.3 owns runtime boot/launch trace evidence.
- `repos/fujinet-nio/include/fujinet/disk/disk_service.h:45` -- future disk adapter boundary: eight slots and direct sector operations, not a fixture dependency.
- `repos/fujinet-nio/tests/fujibus_wire_fixtures.h:1` -- structural precedent for documented independent literals and checksum arithmetic; FujiBus/SLIP values are not reusable for Atari disk fixtures.
- `repos/fujinet-nio/src/platform/posix/atari_netsio_fujibus_channel.cpp:109` -- legacy padded-response/alias implementation; read-only evidence of behavior excluded from v1 fixture authority.
- `_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md` -- governing disk-plane and virtual-versus-physical contract.

## Tasks & Acceptance

**Execution:**
- [ ] `integration-tests/atari-sio/README.md` -- publish the normative contract above as the disk v1 conformance matrix, including literal checksum algorithm, command/data phases, error-to-STATUS table, geometry equations/offsets, lazy-mount behavior, reference-ATR limitation, routing, and exclusions.
- [ ] `integration-tests/atari-sio/fixtures/disk_v1.json` -- encode every matrix scenario as literal, stable-ID fixture data, including positive and negative 128/256 geometry, rejected 512 geometry, pending-mount outcomes, and non-mutation follow-up reads; never generate it from production output.
- [ ] `integration-tests/atari-sio/fixtures/disk_v1.manifest.json` -- publish the adapter projection manifest: input/state references, ordered expected SIO phases, scenario identifiers, and an explicit `evidence_scope` excluding electrical/timing proof.
- [ ] `integration-tests/atari-sio/tests/test_disk_v1_fixtures.py` -- validate JSON schema shape, unique IDs, literal command/data checksum arithmetic, phase ordering, command/AUX/data-length consistency, error/status mapping, geometry equations, required coverage, non-mutation follow-ups, matrix/manifest cross-references, and prohibited scope claims using only the Python standard library.

**Acceptance Criteria:**
- Given the fixture root, when an adapter selects any listed scenario, then it can report the scenario identifier and consume a complete literal SIO expectation without importing production framing code.
- Given a valid v1 disk scenario, when it targets `D1:` through `D8:`, then its matrix entry identifies the corresponding DiskService slot and separates config `D1:` selection from normal restored mappings.
- Given boot, mounted ATR, invalid sector/command, and write-protected inputs, when the validator runs, then it proves their required vectors and error/status expectations are complete and internally consistent.
- Given a malformed frame, bad write data checksum, and a valid command whose DiskService operation fails, when fixtures are selected, then they prove `N`, `A,N`, and `A,E` remain distinct and their follow-up STATUS bytes are exact.
- Given classic 256-byte, malformed small-256-byte, and ordinary 512-byte ATR descriptions, when geometry fixtures validate them, then they prove only the specified 128/256 layouts and actual transfer lengths are accepted.
- Given a virtual projection, when its manifest is read, then it is explicitly protocol/scheduling evidence only and cannot be represented as physical SIO proof.

## Design Notes

Use JSON for adapter-neutral data and a short Markdown matrix for maintainers. An adapter-specific importer belongs to the adapter story, not here. The current `AtrDiskImage` accepts malformed small 256-byte layouts through its sector-count arithmetic; Story 1.2 must correct that implementation before exposing it through disk SIO, while Story 1.1 keeps the independent negative fixtures as the acceptance authority. Cross-story invariant: Story 1.2 establishes one physical SIO bus owner for CMD/UART/GPIO sequencing and dispatches independent disk and NIO frontend callbacks; neither frontend may independently own that sequencing. Story 2.2 replaces or refactors the current `FN_BUILD_ATARI_FUJIBUS_SIO` `FujiBusSlip`/`SioGpio` composition so it selects that dual-plane owner without SLIP or `0x71`; Story 2.3 proves NetSIO/AltirraSDL consume the shared scenarios without physical claims.

## Verification

**Commands:**
- `python3 -m unittest discover -s integration-tests/atari-sio/tests -v` -- expected: all fixture schema, checksum, coverage, and manifest-scope tests pass.
