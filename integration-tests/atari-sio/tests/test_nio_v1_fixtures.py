import json
from pathlib import Path
import unittest

DATA = json.loads((Path(__file__).parents[1] / "fixtures/nio_v1.json").read_text())

class NioV1FixtureTest(unittest.TestCase):
    def test_contract_literals(self):
        self.assertEqual((DATA["wire_revision"], DATA["address"], DATA["capacity"]), (1, 0x7f, 512))
        scenarios = {s["id"]: s for s in DATA["scenarios"]}
        self.assertEqual(scenarios["q-idle"]["dcb_count"], 4)
        self.assertEqual(scenarios["p-pending"]["dcb_count"], 3)
        self.assertEqual(scenarios["p-ready"]["reply"][-1], "02 04 00")
        self.assertEqual(scenarios["r-wrong-length-retains"]["reply"], ["N"])
        self.assertEqual(scenarios["r-wrong-length-retains"]["state"], "ready")
        self.assertEqual(scenarios["w-rejected-busy"]["reply"], ["N"])
        self.assertEqual(scenarios["r-interrupted-consumes"]["state"], "idle")
        self.assertEqual(scenarios["timeout-retains"]["state"], "pending")
        self.assertEqual(scenarios["reset-clears"]["state"], "idle")
        self.assertTrue(scenarios["q-invalid-revision"]["reply"][-1].startswith("02"))
        self.assertEqual(scenarios["q-invalid-capacity"]["reply"][-1], "01 ff 01 00")
        self.assertEqual(scenarios["w-idle"]["payload"], scenarios["r-ready"]["payload"])
        for s in DATA["scenarios"]:
            self.assertIn(s["command"], "QWPR")
            self.assertLessEqual(s["aux"], DATA["capacity"])
            if s["command"] in ("Q", "P"):
                self.assertEqual(s["aux"], 0)
            else:
                self.assertEqual(s["aux"], s["dcb_count"])
