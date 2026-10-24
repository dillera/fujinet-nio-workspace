import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class ResidentRelocationFeasibilityTests(unittest.TestCase):
    def test_relocation_table_and_negative_absolute_reference(self):
        subprocess.run(
            ["make", "-C", str(ROOT / "integration-tests/atari-sio/resident-relocation"),
             "relocation-feasibility"],
            check=True,
        )

    def test_o65_relocation_metadata_is_emitted_and_parseable(self):
        subprocess.run(
            ["make", "-C", str(ROOT / "integration-tests/atari-sio/resident-relocation"),
             "o65-relocation-metadata"],
            check=True,
        )

    def test_ld65_load_run_symbols_describe_a_fixed_copy_destination(self):
        subprocess.run(
            ["make", "-C", str(ROOT / "integration-tests/atari-sio/resident-relocation"),
             "load-run-symbols"],
            check=True,
        )

    def test_dynamic_allocation_plan_reserves_result_staging_and_stack_regions(self):
        subprocess.run(
            ["make", "-C", str(ROOT / "integration-tests/atari-sio/resident-relocation"),
             "allocation-plan"],
            check=True,
        )

    def test_real_public_api_o65_closure_relocates_and_executes_at_two_bases(self):
        subprocess.run(
            ["make", "-C", str(ROOT / "integration-tests/atari-sio/resident-relocation"),
             "o65-api-closure", "o65-api-runtime"],
            check=True,
        )
