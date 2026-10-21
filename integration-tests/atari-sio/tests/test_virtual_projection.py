"""Stdlib tests for the reference-only virtual projection/result layer."""

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import virtual_projection as projection
import run_boot_acceptance as boot_runner


class VirtualProjectionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = projection.load_manifest()

    def test_manifest_references_fixture_authority_and_required_families(self):
        projection.validate_manifest(self.manifest)
        ids = {entry["id"] for entry in self.manifest["projections"]}
        self.assertTrue({"native-q-capability", "native-core-dispatch", "native-rejected-w",
                         "native-wrong-r-retention", "native-reset-to-idle",
                         "native-capacity-bounds"} <= ids)
        self.assertEqual(self.manifest["boot_projections"][0]["id"], "boot-page6-config")

    def test_validator_rejects_unknown_duplicate_legacy_and_missing_observations(self):
        invalid = copy.deepcopy(self.manifest)
        invalid["projections"][0]["operations"][0]["fixture"] = "not-a-fixture"
        with self.assertRaises(projection.ProjectionError):
            projection.validate_manifest(invalid)
        invalid = copy.deepcopy(self.manifest)
        invalid["projections"].append(copy.deepcopy(invalid["projections"][0]))
        with self.assertRaises(projection.ProjectionError):
            projection.validate_manifest(invalid)
        invalid = copy.deepcopy(self.manifest)
        invalid["forbidden_paths"].remove("slip")
        with self.assertRaises(projection.ProjectionError):
            projection.validate_manifest(invalid)
        invalid = copy.deepcopy(self.manifest)
        invalid["projections"][0]["operations"][0]["observe"] = []
        with self.assertRaises(projection.ProjectionError):
            projection.validate_manifest(invalid)

    def test_deliberately_wrong_order_or_response_fails_comparison_then_literal_values_pass(self):
        entry = next(item for item in self.manifest["projections"] if item["id"] == "native-core-dispatch")
        expected = projection.expected_operation_ids(entry)
        projection.compare_observed_operations(entry, expected)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_observed_operations(entry, list(reversed(expected)))
        responses = projection.expected_responses(entry)
        projection.compare_observed_responses(entry, responses)
        wrong_response = list(responses)
        wrong_response[0] = (wrong_response[0][0], ["N"])
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_observed_responses(entry, wrong_response)

    def test_result_is_adapter_scoped_and_missing_evidence_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            paths = projection.evidence_paths_for_boot(run, "netsio")
            incomplete = projection.scenario_result("netsio", "boot-page6-config", {}, paths)
            self.assertEqual(incomplete["status"], "incomplete")
            self.assertFalse(incomplete["passed"])
            for path in paths.values():
                path.write_text("evidence\n")
            passed = projection.scenario_result("netsio", "boot-page6-config", {"commands": []}, paths)
            self.assertEqual(passed["status"], "pass")
            result_path = projection.write_scenario_result(run / "results", passed)
            self.assertEqual(result_path.parent.name, "netsio")
            self.assertTrue(result_path.is_file())
            embedded_paths = projection.evidence_paths_for_boot(run / "embedded-run", "altirra-embedded")
            embedded = projection.scenario_result("altirra-embedded", "boot-page6-config", {}, embedded_paths)
            self.assertEqual(embedded["status"], "incomplete")
            self.assertIn("altirra-embedded", projection.REQUIRED_EVIDENCE)

    def test_boot_runner_reuses_common_result_and_evidence_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            for path in projection.evidence_paths_for_boot(run, "netsio").values():
                path.write_text("evidence\n")
            result = boot_runner.write_netsio_boot_projection({
                "run_dir": str(run),
                "signature": "NIO!",
                "trace": {
                    "d1_status": "31 53 00 00 84",
                    "boot_reads_128": ["31 52 01 00 84", "31 52 02 00 85", "31 52 03 00 86"],
                    "first_dd_read_256": "31 52 69 01 ED",
                },
            })
            self.assertEqual((result["adapter"], result["scenario_id"], result["status"]),
                             ("netsio", "boot-page6-config", "pass"))
            self.assertTrue(Path(result["result_path"]).is_file())
