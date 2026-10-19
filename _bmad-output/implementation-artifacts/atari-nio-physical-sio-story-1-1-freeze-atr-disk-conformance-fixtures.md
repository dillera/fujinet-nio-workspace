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

**Always:** Specify only standard Atari `D1:`–`D8:` boot and mounted ATR read, write, and status exchanges. Freeze device-to-slot routing, one-based sector numbering, boot-sector geometry/byte counts, response/status/error outcomes, config-mode `boot.config_uri` selection, and normal-mode restored-slot selection. Make every expected command, AUX/sector field, data length, checksum, reply phase, and payload literal or independently computed in the fixture validator. Give each scenario a stable identifier and label projections as virtual protocol evidence with no physical timing/electrical claim. Keep the fixture validator stdlib-only and independent of every production serializer/framer.

**Ask First:** Adding a v1 disk command beyond read, write, and status; changing ATR geometry semantics or standard SIO reply/error semantics; making a production repository consume the projection; or redefining config/normal boot policy.

**Never:** Use `DiskDevice`, FujiBus, `LegacyTransport`, the current Atari SLIP/padded-read/`0x71` channel, or a production framer as fixture oracle. Do not add formatting, PERCOM, high-speed SIO, non-ATR media, NIO `0x7F` traffic, emulator integration, or any electrical/timing assertion.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Boot read | `D1:` config ATR, sectors 1–3 | Standard read reply uses the fixture-defined boot-sector bytes and 128-byte transfer geometry | Missing boot ATR is a literal disk error scenario |
| Mounted I/O | Routed writable/read-only ATR slot, valid one-based sector | `R`/`W` data length follows literal ATR sector geometry; `S` returns the frozen status bytes | Write-protected media rejects write without mutation |
| Invalid request | Unsupported command or zero/out-of-range sector | No DiskService/FujiBus fallback; response matches the named rejected-SIO vector | The scenario remains observable by its identifier |
| Boot policy | Config mode versus normal restored slots | Config chooses only `boot.config_uri` for `D1:`; normal maps each `D1:`–`D8:` to its restored slot | An absent selected slot returns the frozen not-ready/error result |

</frozen-after-approval>

## Code Map

- `integration-tests/atari-sio/` -- new workspace-owned canonical fixture root; it is deliberately the authority before any production adapter is added.
- `repos/fujinet-nio/src/lib/disk/atr_image.cpp:17` -- current ATR geometry reference: sectors 1–3 are 128 bytes for a 256-byte base ATR; fixture literals must not be generated through this code.
- `repos/fujinet-nio/include/fujinet/disk/disk_service.h:45` -- future disk adapter boundary: eight slots and direct sector operations, not a fixture dependency.
- `repos/fujinet-nio/tests/fujibus_wire_fixtures.h:1` -- structural precedent for documented independent literals and checksum arithmetic; FujiBus/SLIP values are not reusable for Atari disk fixtures.
- `repos/fujinet-nio/src/platform/posix/atari_netsio_fujibus_channel.cpp:109` -- legacy padded-response/alias implementation; read-only evidence of behavior excluded from v1 fixture authority.
- `_bmad-output/specs/spec-atari-nio-physical-sio/wire-and-acceptance.md` -- governing disk-plane and virtual-versus-physical contract.

## Tasks & Acceptance

**Execution:**
- [ ] `integration-tests/atari-sio/README.md` -- author the disk v1 conformance matrix: supported read/write/status commands; command frame and reply phases; one-based sector/AUX encoding; ATR 128/256 boot geometry and byte counts; D1–D8-to-slot routing; status/error mapping; config versus normal selection; and explicit exclusions.
- [ ] `integration-tests/atari-sio/fixtures/disk_v1.json` -- add canonical literal scenario data for boot reads, mounted read/write/status, read-only write rejection, invalid sector, unsupported command, and config/restored-slot selection. Store payload bytes and all transaction expectations as fixture data with stable scenario IDs, never as production-generated output.
- [ ] `integration-tests/atari-sio/fixtures/disk_v1.manifest.json` -- publish the adapter projection manifest: input/state references, ordered expected SIO phases, scenario identifiers, and an explicit `evidence_scope` excluding electrical/timing proof.
- [ ] `integration-tests/atari-sio/tests/test_disk_v1_fixtures.py` -- validate JSON schema shape, unique IDs, literal checksum arithmetic, command/AUX/data-length consistency, required coverage, matrix/manifest cross-references, and prohibited scope claims using only the Python standard library.

**Acceptance Criteria:**
- Given the fixture root, when an adapter selects any listed scenario, then it can report the scenario identifier and consume a complete literal SIO expectation without importing production framing code.
- Given a valid v1 disk scenario, when it targets `D1:` through `D8:`, then its matrix entry identifies the corresponding DiskService slot and separates config `D1:` selection from normal restored mappings.
- Given boot, mounted ATR, invalid sector/command, and write-protected inputs, when the validator runs, then it proves their required vectors and error/status expectations are complete and internally consistent.
- Given a virtual projection, when its manifest is read, then it is explicitly protocol/scheduling evidence only and cannot be represented as physical SIO proof.

## Spec Change Log

## Design Notes

Use JSON for adapter-neutral data and a short Markdown matrix for maintainers. The fixture validator may calculate a checksum only to check manually stored expected bytes; it must never derive expected payloads, framing, or scenarios from an adapter implementation. An adapter-specific importer belongs to the adapter story, not here.

## Verification

**Commands:**
- `python3 -m unittest discover -s integration-tests/atari-sio/tests -v` -- expected: all fixture schema, checksum, coverage, and manifest-scope tests pass.
