---
title: 'Freeze Atari ATR disk conformance fixtures'
type: 'feature'
created: '2026-10-19'
status: 'done'
review_loop_iteration: 0
baseline_commit: '0a98f783b18248f8c51ad31d57a3a17d09d55782'
context:
  - 'docs/agent-test-policy.md'
  - '_bmad-output/implementation-artifacts/atari-nio-physical-sio-epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Atari disk boot and mounted ATR behavior lacks an implementation-independent contract, so adapters could reproduce incompatible or legacy behavior.

**Approach:** Establish `integration-tests/atari-sio` as the canonical v1 disk matrix, manifest, vector, and projection source. Future adapters consume stable identifiers, never production-framing output.

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
| `0x57` WRITE WITH VERIFY | same receive sequence as `0x50` | after data `A`, write, flush, reread, and byte-compare the sector; match → `C`, otherwise `E` (the accepted data may already have modified media) |
| `0x53` STATUS | valid command with AUX `0,0` → `A` | `C`, four status bytes, status checksum; it is available even when the selected slot is unavailable |

A malformed command frame or bad command checksum receives `N` and does not enter DiskService. A well-formed but unsupported command also receives `N`. A syntactically valid supported command with sector `0`, unsupported geometry, missing media, or an execution failure receives `A` then `E`; it is never conflated with a malformed frame. In particular, `A,E` for a valid sector command with invalid sector parameters is an explicit v1 policy, not a claim about every historical SIO drive. A disk device ID outside `D1:`–`D8:` is not this frontend's traffic.

STATUS is non-blocking inspection: it must not call `ensure_mounted`, resolve a URI, or activate a pending mount. Byte 0 is Atari drive status: bit 0 command-frame, bit 1 data-frame checksum, bit 2 operation, bit 3 write-protect, bit 5 256-byte geometry; bits 4, 6, and 7 are zero because an ATR has no physical motor, side, or track geometry. Byte 1 is inverted FDC-style controller status: ready/clear is `0xDF`; unavailable media is `0x5F` (not-ready); read-only media/write rejection is `0x9F` (write-protect); an out-of-range sector, bad image, or unsupported geometry is `0xCF` (record-not-found); and I/O/internal failure is `0xDB` (lost-data). Byte 2 is `0x0F`, the conventional non-format-operation timeout; byte 3 is `0x00`. The older FujiNet disk frontend uses the format-oriented `0xE0` timeout because it also serves FORMAT; v1 does not.

STATUS itself always returns `A,C,status,sum`; it retains, rather than clears, the last non-STATUS disk outcome. A successful READ/PUT/WRITE replaces the transient bits 0–2 and controller error with ready/clear; write protection and density remain media properties. A never-activated pending slot returns the non-blocking unavailable base state `{geometry=0,0x5F,0x0F,0x00}` without an operation bit. `NotMounted`, `NoSuchFileSystem`, `FileNotFound`, `OpenFailed`, `BadImage`, and `GeometryRequired` map after a failed data command to terminal `E` and STATUS `{0x04,0x5F,0x0F,0x00}`; `ReadOnly` maps to `E`, `{0x0C,0x9F,0x0F,0x00}`; `InvalidRequest`, `OutOfRange`, `InvalidSlot`, and `InvalidGeometry` map to `E`, `{0x04,0xCF,0x0F,0x00}`; `IoError` and `InternalError` map to `E`, `{0x04,0xDB,0x0F,0x00}`. A bad command frame records bit 0 and a bad incoming write-data checksum records bit 1; both leave media unmodified. Consecutive STATUS vectors must prove retention, then a successful command proves clearing.

The accepted ATR geometries are: 128-byte sectors with integral payload length, and classic 256-byte ATR where sectors 1–3 transfer 128 bytes and sectors 4 onward transfer 256 bytes. For the latter, payload bytes must be at least 384 and satisfy `(payload_bytes - 384) % 256 == 0`; its sector count is `3 + (payload_bytes - 384) / 256`. SIO sector `n` maps to DiskService LBA `n-1`; offsets after the 16-byte ATR header are `128*(n-1)` for 128-byte ATR and `0,128,256,384+256*(n-4)` for classic 256-byte ATR. Allocate to the maximum 256-byte supported sector size, but transmit and checksum only the actual `DiskResult.bytes` (128 for 256-byte ATR sectors 1–3). Ordinary 512-byte ATR geometry is rejected before sector execution.

The reference configuration medium is the reproducible `repos/fujinet-nio/distfiles/boot/atari/autorun.atr`, built by `make TARGET=atari boot-disk` in `repos/nio-core-apps` from `boot-disk/manifests/atari.yaml` and PicoBoot. It supplies the current configuration application bundle, not a named general-purpose DOS. v1 therefore supports both `0x50` and `0x57`: the former covers ordinary PUT callers and the latter matches the Atari resident disk handler's write-with-verify path. Story 1.3 must record a boot/launch command trace of the packaged ATR before claiming general DOS compatibility; untraced external DOS commands remain unsupported.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Boot read | `D1:` config ATR, sectors 1–3 and sector 4 | `0x52` vectors prove 128/256 transfer boundary, LBA, offset, checksum, and `A,C,data,sum` ordering | Missing media produces `A,E` then the frozen unavailable STATUS |
| Mounted I/O | Routed writable/read-only ATR slot, valid one-based sector | `0x50` and `0x57` cover distinct PUT/verify execution; `0x53` returns virtual-drive STATUS `0xDF`/`0x0F` baseline | Bad checksums and pre-write rejection prove non-mutation; a post-accept verify failure may retain modified media |
| Invalid request | Bad frame/checksum, unsupported command, zero/out-of-range sector, bad data checksum | Fixture distinguishes `N` rejection from deliberate v1 `A,E` execution failure and records two consecutive STATUS replies | No DiskService/FujiBus fallback |
| Boot policy | Config mode versus normal restored slots | Config chooses only `boot.config_uri` for `D1:`; normal maps each `D1:`–`D8:` to its restored slot | STATUS never activates a pending mount; pending-mount success/failure vectors preserve the frozen slot error mapping |

</frozen-after-approval>

## Code Map

- `integration-tests/atari-sio/` -- new workspace-owned canonical fixture root; it is deliberately the authority before any production adapter is added.
- `repos/fujinet-nio/src/lib/disk/atr_image.cpp:17` -- geometry reference only, not a fixture oracle; Story 1.2 corrects its malformed-small-256 count arithmetic.
- `repos/fujinet-nio/src/lib/disk/disk_service.cpp:612` -- lazy mount and direct sector-operation boundary; the frontend neither resolves URIs nor accesses images.
- `repos/fujinet-nio/src/platform/posix/atari_netsio_fujibus_channel.cpp:109` -- legacy padded-response/alias evidence excluded from v1 fixture authority.

## Tasks & Acceptance

**Execution:**
- [x] `integration-tests/atari-sio/README.md` -- publish the contract as the disk-v1 matrix: checksum, phases, STATUS/retention, geometry, lazy mount, reference limit, routing, and exclusions.
- [x] `integration-tests/atari-sio/fixtures/disk_v1.json` -- encode each matrix scenario as literal stable-ID data, including geometry, pending STATUS/mount, retained/cleared STATUS, and write postimages; never generate production output.
- [x] `integration-tests/atari-sio/fixtures/disk_v1.manifest.json` -- publish projection input/state, ordered SIO phases, IDs, and non-physical evidence scope.
- [x] `integration-tests/atari-sio/tests/test_disk_v1_fixtures.py` -- stdlib-only validation of schema, IDs, checksums, phase/length/status/geometry rules, coverage, postimages, references, and scope.

**Acceptance Criteria:**
- Given the fixture root, when an adapter selects any listed scenario, then it can report the scenario identifier and consume a complete literal SIO expectation without importing production framing code.
- Given a valid v1 disk scenario, when it targets `D1:` through `D8:`, then its matrix entry identifies the corresponding DiskService slot and separates config `D1:` selection from normal restored mappings.
- Given boot, mounted ATR, invalid sector/command, and write-protected inputs, when the validator runs, then vectors and error/status expectations are complete and internally consistent.
- Given a malformed frame, bad write data checksum, and a valid command whose DiskService operation fails, when fixtures are selected, then they prove `N`, `A,N`, and deliberate-v1 `A,E` remain distinct and their follow-up STATUS bytes are exact.
- Given a STATUS request before and after failed and successful disk exchanges, when consecutive STATUS vectors run, then they prove its non-blocking inspection, retained error state, success clearing, density, write-protection, FDC-style controller state, and `0x0F` timeout.
- Given classic 256-byte, malformed small-256-byte, and ordinary 512-byte ATR descriptions, when geometry fixtures validate them, then they prove only the specified 128/256 layouts and actual transfer lengths are accepted.
- Given a virtual projection, when its manifest is read, then it is protocol/scheduling evidence only, never physical SIO proof.

## Design Notes

Use JSON plus a short Markdown matrix; adapter importers belong to later stories. Story 1.2 corrects `AtrDiskImage` small-256 arithmetic and owns the sole CMD/UART/GPIO sequencer, dispatching disk/NIO callbacks. Story 2.2 migrates `FN_BUILD_ATARI_FUJIBUS_SIO` from `FujiBusSlip`/`SioGpio` to that dual-plane owner without SLIP or `0x71`; Story 2.3 proves virtual consumption without physical claims.

## Verification

**Commands:**
- `python3 -m unittest discover -s integration-tests/atari-sio/tests -v` -- expected: all fixture schema, checksum, coverage, and manifest-scope tests pass.

## Suggested Review Order

**Protocol contract**

- Defines the bounded virtual disk surface and immutable fixture authority.
  [README.md:13](../../integration-tests/atari-sio/README.md#L13)

- Freezes literal error-to-STATUS bytes, supported commands, and device routing.
  [disk_v1.json:2](../../integration-tests/atari-sio/fixtures/disk_v1.json#L2)

**Independent virtual evidence**

- Projects every scenario without presenting virtual scheduling as physical SIO proof.
  [disk_v1.manifest.json:2](../../integration-tests/atari-sio/fixtures/disk_v1.manifest.json#L2)

**Executable guardrails**

- Validates literal frames, geometry, STATUS retention, checksums, mutation boundaries, and projection completeness.
  [test_disk_v1_fixtures.py:47](../../integration-tests/atari-sio/tests/test_disk_v1_fixtures.py#L47)
