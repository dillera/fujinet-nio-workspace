"""Reference-only Atari native-v1 virtual projection/result helpers.

This module deliberately does not serialize or emulate Q/W/P/R.  It validates
the independent fixture references and gives both virtual adapters one result
schema and evidence policy.  Adapter playback is intentionally a later story
increment.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
MANIFEST_PATH = FIXTURES / "nio_v1.virtual.manifest.json"
NIO_PATH = FIXTURES / "nio_v1.json"
DISK_PATH = FIXTURES / "disk_v1.json"
ADAPTERS = {"netsio", "altirra-embedded"}
OBSERVATIONS = {"command", "data", "response", "state", "client-outcome", "transport-error", "page-6-signature"}
FORBIDDEN = {"legacy-$71", "slip", "padded-read", "stream-chunking"}
REQUIRED_EVIDENCE = {
    "netsio": ("altirra_log", "hub_log", "nio_log", "pokey_siodata", "screenshot", "inspection"),
    "altirra-embedded": ("altirra_log", "pokey_siodata", "screenshot", "inspection"),
}


class ProjectionError(ValueError):
    pass


class ProjectionMismatch(AssertionError):
    pass


def load_json(path: Path):
    return json.loads(path.read_text())


def load_manifest(path: Path = MANIFEST_PATH):
    return load_json(path)


def _ids(path: Path, key: str):
    return {item["id"] for item in load_json(path)[key]}


def validate_manifest(manifest, nio_ids=None, disk_ids=None):
    """Reject non-reference projections before an adapter run can start."""
    nio_ids = _ids(NIO_PATH, "scenarios") if nio_ids is None else set(nio_ids)
    disk_ids = _ids(DISK_PATH, "scenarios") if disk_ids is None else set(disk_ids)
    if manifest.get("format") != "atari-native-nio-v1-virtual-projection":
        raise ProjectionError("unsupported virtual projection format")
    if manifest.get("fixture_authority") != "nio_v1.json" or not manifest.get("native_v1_only"):
        raise ProjectionError("projection must declare independent native-v1 authority")
    if set(manifest.get("adapters", ())) != ADAPTERS:
        raise ProjectionError("projection must name netsio and altirra-embedded independently")
    if set(manifest.get("forbidden_paths", ())) != FORBIDDEN:
        raise ProjectionError("projection must exclude every obsolete native path")

    projection_ids = set()
    for projection in manifest.get("projections", ()):
        identifier = projection.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in projection_ids:
            raise ProjectionError("projection IDs must be unique nonempty strings")
        projection_ids.add(identifier)
        operations = projection.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ProjectionError(f"{identifier}: ordered operations are required")
        for operation in operations:
            fixture = operation.get("fixture")
            observed = operation.get("observe")
            if fixture not in nio_ids:
                raise ProjectionError(f"{identifier}: unknown native fixture {fixture!r}")
            if not isinstance(observed, list) or not observed or not set(observed) <= OBSERVATIONS:
                raise ProjectionError(f"{identifier}: expected observations are required")

    boot_ids = set()
    for projection in manifest.get("boot_projections", ()):
        identifier = projection.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in boot_ids:
            raise ProjectionError("boot projection IDs must be unique nonempty strings")
        boot_ids.add(identifier)
        if projection.get("fixture_authority") != "disk_v1.json":
            raise ProjectionError(f"{identifier}: disk fixture authority is required")
        scenario_ids = projection.get("scenario_ids")
        observed = projection.get("observe")
        if not isinstance(scenario_ids, list) or not scenario_ids or any(item not in disk_ids for item in scenario_ids):
            raise ProjectionError(f"{identifier}: unknown disk fixture reference")
        if not isinstance(observed, list) or not observed or not set(observed) <= OBSERVATIONS:
            raise ProjectionError(f"{identifier}: expected observations are required")
    if not projection_ids or not boot_ids:
        raise ProjectionError("native and D1 boot projections are both required")
    return manifest


def expected_operation_ids(projection):
    return [operation["fixture"] for operation in projection["operations"]]


def compare_observed_operations(projection, observed_operation_ids):
    expected = expected_operation_ids(projection)
    observed = list(observed_operation_ids)
    if observed != expected:
        raise ProjectionMismatch(f"{projection['id']}: expected {expected}, observed {observed}")


def expected_responses(projection, fixture_data=None):
    """Resolve expected responses only from the independent literal fixture."""
    fixture_data = load_json(NIO_PATH) if fixture_data is None else fixture_data
    scenarios = {scenario["id"]: scenario for scenario in fixture_data["scenarios"]}
    return [(operation["fixture"], scenarios[operation["fixture"]].get("reply"))
            for operation in projection["operations"]
            if "reply" in scenarios[operation["fixture"]]]


def compare_observed_responses(projection, observed_responses, fixture_data=None):
    expected = expected_responses(projection, fixture_data)
    observed = list(observed_responses)
    if observed != expected:
        raise ProjectionMismatch(f"{projection['id']}: expected responses {expected}, observed {observed}")


def sio_checksum(payload):
    """Atari end-around-carry checksum used by the literal SIO fixture."""
    total = sum(payload)
    while total > 0xff:
        total = (total & 0xff) + (total >> 8)
    return total


def native_core_dispatch_fixture_ids(manifest=None):
    """Return the guest sequence around the manifest-owned core projection.

    `native-core-dispatch` owns W/P/R.  The required Q preflight and terminal
    idle poll are existing literal vectors, not another response generator.
    """
    manifest = load_manifest() if manifest is None else manifest
    validate_manifest(manifest)
    projection = next(item for item in manifest["projections"]
                      if item["id"] == "native-core-dispatch")
    ids = expected_operation_ids(projection)
    if ids != ["w-core-dispatch", "p-core-dispatch-ready", "r-core-dispatch"]:
        raise ProjectionError("native-core-dispatch projection no longer names the approved W/P/R sequence")
    return ["q-idle", *ids, "reset-clears"]


def _hex(value):
    return bytes.fromhex(value) if value else b""


def _nio_datagrams(log):
    """Extract complete UDP frames from the production NetSIO process log."""
    events = []
    pattern = re.compile(r"udp: (Received|Sending) (\d+) bytes: ([0-9A-F ]+)$", re.MULTILINE)
    for match in pattern.finditer(log):
        data = _hex(match.group(3))
        if len(data) != int(match.group(2)):
            raise ProjectionMismatch(f"NetSIO log byte-count mismatch: {match.group(0)!r}")
        events.append((match.group(1).lower(), data))
    if not events:
        raise ProjectionMismatch("NetSIO log contains no captured UDP datagrams")
    return events


def compare_netsio_native_core_dispatch(log, manifest=None, fixture_data=None):
    """Byte-verify the real NetSIO trace for the approved guest sequence.

    This consumes the production adapter's UDP capture.  It does not create a
    peer or call the frontend; it only checks observed command, control, data,
    and checksum datagrams against the independent fixture literals.
    """
    manifest = load_manifest() if manifest is None else manifest
    fixture_data = load_json(NIO_PATH) if fixture_data is None else fixture_data
    if log.count("core-dispatch fixture route invocation 1") != 1 or \
       "core-dispatch fixture route invocation 2" in log:
        raise ProjectionMismatch("native-core-dispatch did not route exactly once through the real core fixture")
    fixtures = {item["id"]: item for item in fixture_data["scenarios"]}
    ids = native_core_dispatch_fixture_ids(manifest)
    events = _nio_datagrams(log)
    command_positions = [index for index, (direction, data) in enumerate(events)
                         if direction == "received" and len(data) == 7 and data[0] == 0x02
                         and data[1] == 0x7f and data[2] in b"QWPR"]
    if len(command_positions) != len(ids):
        raise ProjectionMismatch(f"expected {len(ids)} native command frames, found {len(command_positions)}")

    observed = []
    for ordinal, (identifier, position) in enumerate(zip(ids, command_positions)):
        fixture = fixtures[identifier]
        expected_command = _hex(fixture["frame"])
        direction, command_datagram = events[position]
        if command_datagram[1:6] != expected_command:
            raise ProjectionMismatch(
                f"{identifier}: expected command {expected_command.hex(' ')}, "
                f"observed {command_datagram[1:6].hex(' ')}")
        end = command_positions[ordinal + 1] if ordinal + 1 < len(command_positions) else len(events)
        window = events[position + 1:end]
        entry = {"fixture": identifier, "command": command_datagram[1:6].hex(' ')}

        if identifier == "w-core-dispatch":
            write_ack = next((data for direction, data in window
                              if direction == "sending" and len(data) == 6 and data[0] == 0x81), None)
            if write_ack is None or write_ack[3] != ord("A") or write_ack[4:6] != b"\x07\x00":
                raise ProjectionMismatch("w-core-dispatch: missing exact accepted-W ACK/write count")
            payload = _hex(fixture["payload"])
            data_frame = next((data for direction, data in window
                               if direction == "received" and len(data) == len(payload) + 2 and data[0] == 0x02), None)
            checksum_frame = next((data for direction, data in window
                                   if direction == "received" and len(data) == 4 and data[0] == 0x09), None)
            if data_frame is None or data_frame[1:-1] != payload:
                raise ProjectionMismatch("w-core-dispatch: payload differs from literal fixture")
            expected_checksum = int(fixture["payload_checksum"], 16)
            if checksum_frame is None or checksum_frame[1] != expected_checksum:
                raise ProjectionMismatch("w-core-dispatch: payload checksum differs from literal fixture")
            completion = [(data[3],) if len(data) == 6 and data[0] == 0x81 else (data[1],)
                          for direction, data in window if direction == "sending" and
                          ((len(data) == 6 and data[0] == 0x81) or (len(data) == 2 and data[0] == 0x01))]
            if completion[-2:] != [(ord("A"),), (ord("C"),)]:
                raise ProjectionMismatch("w-core-dispatch: missing terminal A/C after data checksum")
            entry.update({"data": payload.hex(' '), "checksum": f"{expected_checksum:02x}",
                          "response": ["A", "C"]})
        else:
            controls = []
            payload = b""
            checksum = None
            for direction, data in window:
                if direction != "sending":
                    continue
                if len(data) == 6 and data[0] == 0x81:
                    controls.append(chr(data[3]))
                elif len(data) == 2 and data[0] == 0x01:
                    controls.append(chr(data[1]))
                    checksum = data[1]
                elif len(data) >= 2 and data[0] == 0x02:
                    payload = data[1:]
            expected_reply = fixture["reply"]
            expected_controls = [part for part in expected_reply if len(part) == 1]
            expected_payload = _hex(next((part for part in expected_reply if len(part) > 1),
                                         fixture.get("payload", "")))
            if controls[:len(expected_controls)] != expected_controls:
                raise ProjectionMismatch(f"{identifier}: expected controls {expected_controls}, observed {controls}")
            if payload != expected_payload:
                raise ProjectionMismatch(
                    f"{identifier}: expected payload {expected_payload.hex(' ')}, observed {payload.hex(' ')}")
            expected_checksum = (int(fixture["payload_checksum"], 16)
                                 if "payload_checksum" in fixture else sio_checksum(expected_payload))
            if checksum != expected_checksum:
                raise ProjectionMismatch(f"{identifier}: response checksum differs from canonical SIO checksum")
            entry.update({"response": expected_controls, "payload": payload.hex(' '),
                          "checksum": None if checksum is None else f"{checksum:02x}"})
        observed.append(entry)

    core = next(item for item in manifest["projections"] if item["id"] == "native-core-dispatch")
    compare_observed_operations(core, [entry["fixture"] for entry in observed[1:4]])
    compare_observed_responses(core, [(entry["fixture"], fixtures[entry["fixture"]]["reply"])
                                      for entry in observed[1:4]])
    return observed


def evidence_paths_for_boot(run_dir: Path, adapter: str):
    run_dir = Path(run_dir)
    paths = {
        "altirra_log": run_dir / "altirra.log",
        "pokey_siodata": run_dir / "pokey-siodata.log",
        "screenshot": run_dir / "screen.png",
        "inspection": run_dir / "inspection.json",
    }
    if adapter == "netsio":
        paths.update({"hub_log": run_dir / "hub.log", "nio_log": run_dir / "nio.log"})
    return paths


def scenario_result(adapter, scenario_id, observed, evidence_paths, passed=True, error=None):
    """Return a machine-readable result; missing evidence is never a pass."""
    if adapter not in ADAPTERS:
        raise ProjectionError(f"unknown adapter {adapter!r}")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ProjectionError("scenario ID is required")
    normalized_paths = {name: str(Path(path)) for name, path in evidence_paths.items()}
    missing = [name for name in REQUIRED_EVIDENCE[adapter]
               if name not in normalized_paths or not Path(normalized_paths[name]).is_file()]
    status = "pass" if passed and not missing else "incomplete" if missing else "fail"
    return {
        "format": "atari-native-nio-v1-virtual-result",
        "scope": "virtual protocol/scheduling evidence only",
        "adapter": adapter,
        "scenario_id": scenario_id,
        "status": status,
        "passed": status == "pass",
        "observed": observed,
        "evidence_paths": normalized_paths,
        "missing_evidence": missing,
        "error": error,
    }


def write_scenario_result(output_dir: Path, result):
    output_dir = Path(output_dir) / result["adapter"]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result['scenario_id']}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    return path
