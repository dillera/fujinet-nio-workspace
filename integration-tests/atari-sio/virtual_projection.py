"""Reference-only Atari native-v1 virtual projection/result helpers.

This module deliberately does not serialize or emulate Q/W/P/R.  It validates
the independent fixture references and gives both virtual adapters one result
schema and evidence policy.  Adapter playback is intentionally a later story
increment.
"""
from __future__ import annotations

import json
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
