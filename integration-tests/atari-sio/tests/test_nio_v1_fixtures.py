import json
from pathlib import Path
import unittest

DATA = json.loads((Path(__file__).parents[1] / "fixtures/nio_v1.json").read_text())


def sio_checksum(data):
    total = sum(data)
    while total > 0xFF:
        total = (total & 0xFF) + (total >> 8)
    return total


def valid_raw_fujibus_packet(data):
    if len(data) < 6 or (data[2] | data[3] << 8) != len(data):
        return False
    expected = data[4]
    check = bytearray(data)
    check[4] = 0
    return sio_checksum(check) == expected


class NioV1FixtureTest(unittest.TestCase):
    def test_contract_literals(self):
        self.assertEqual((DATA["wire_revision"], DATA["address"], DATA["capacity"]), (1, 0x7f, 512))
        scenarios = {s["id"]: s for s in DATA["scenarios"]}
        self.assertEqual(len(scenarios), len(DATA["scenarios"]))
        self.assertEqual(scenarios["q-idle"]["dcb_count"], 4)
        self.assertEqual(scenarios["q-valid-larger"]["reply"][-1], "01 00 04 a5")
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
            self.assertEqual(s["aux"], s["dcb_count"] if s["command"] in ("W", "R") else 0)
            if s.get("local_only"):
                self.assertGreater(s["aux"], DATA["capacity"])
                self.assertEqual(s["client_outcome"], "transport-error")
                continue
            self.assertLessEqual(s["aux"], DATA["capacity"])
            frame = bytes.fromhex(s["frame"])
            self.assertEqual(len(frame), 5)
            self.assertEqual(frame[0], DATA["address"])
            self.assertEqual(frame[1], ord(s["command"]))
            self.assertEqual(frame[2] | frame[3] << 8, s["aux"])
            self.assertEqual(frame[4], sio_checksum(frame[:4]))
            if s["command"] in ("Q", "P"):
                self.assertEqual(s["aux"], 0)
            else:
                self.assertEqual(s["aux"], s["dcb_count"])
            if "payload" in s:
                self.assertEqual(int(s["payload_checksum"], 16),
                                 sio_checksum(bytes.fromhex(s["payload"])))

    def test_capacity_and_exact_length_vectors(self):
        scenarios = {s["id"]: s for s in DATA["scenarios"]}
        for identifier, size in (("w-511", 511), ("w-512", 512),
                                 ("r-ready-512", 512)):
            vector = scenarios[identifier]
            self.assertEqual((vector["aux"], vector["dcb_count"],
                              vector["payload_length"]), (size, size, size))
        self.assertEqual(scenarios["p-ready-512"]["reply"][-1], "02 00 02")
        self.assertEqual(scenarios["p-ready-513-retains"]["reply"][-1], "02 01 02")
        self.assertEqual(scenarios["p-ready-513-retains"]["client_outcome"],
                         "transport-error-retains")
        for identifier in ("w-512", "r-ready-512"):
            vector = scenarios[identifier]
            self.assertEqual(vector["payload_pattern"], "i ^ (i >> 8) ^ 0xa5")
            pattern = bytes((i ^ (i >> 8) ^ 0xA5) & 0xFF for i in range(512))
            self.assertEqual(sio_checksum(pattern), int(vector["payload_checksum"], 16))

    def test_recovery_and_malformed_poll_vectors(self):
        scenarios = {s["id"]: s for s in DATA["scenarios"]}
        self.assertEqual(scenarios["w-rejected-busy"]["reply"], ["N"])
        self.assertEqual(scenarios["r-wrong-length-retains"]["state"], "ready")
        self.assertEqual(scenarios["r-siov-error-retains"]["client_outcome"],
                         "transport-error-retains")
        self.assertEqual(scenarios["r-interrupted-consumes"]["state"], "idle")
        self.assertEqual(scenarios["timeout-retains"]["state"], "pending")
        self.assertEqual(scenarios["reset-clears"]["reply"][-1], "00 00 00")
        for identifier in ("p-unknown-retains", "p-ready-zero-retains",
                           "p-siov-error-retains"):
            vector = scenarios[identifier]
            self.assertEqual(vector["command"], "P")
            self.assertEqual((vector["aux"], vector["dcb_count"]), (0, 3))
            self.assertEqual(vector["client_outcome"], "timeout-retains")

    def test_q_rejections_restore_the_v1_baseline(self):
        scenarios = {s["id"]: s for s in DATA["scenarios"]}
        for identifier in ("q-invalid-revision", "q-invalid-capacity",
                           "q-siov-error"):
            vector = scenarios[identifier]
            self.assertEqual(vector["command"], "Q")
            self.assertEqual((vector["aux"], vector["dcb_count"]), (0, 4))
            self.assertEqual(vector["client_outcome"], "transport-error-baseline")

    def test_core_dispatch_pair_is_literal_raw_fujibus(self):
        scenarios = {s["id"]: s for s in DATA["scenarios"]}
        pairs = {p["id"]: p for p in DATA["packet_pairs"]}
        self.assertEqual(set(pairs), {"core-dispatch"})
        pair = pairs["core-dispatch"]
        request = scenarios[pair["request_scenario"]]
        response = scenarios[pair["response_scenario"]]
        self.assertEqual((request["command"], response["command"]), ("W", "R"))
        self.assertEqual(request["aux"], len(bytes.fromhex(request["payload"])))
        self.assertEqual(response["aux"], len(bytes.fromhex(response["payload"])))
        self.assertTrue(valid_raw_fujibus_packet(bytes.fromhex(request["payload"])))
        self.assertTrue(valid_raw_fujibus_packet(bytes.fromhex(response["payload"])))
        self.assertEqual(sio_checksum(bytes.fromhex(request["payload"])),
                         int(request["payload_checksum"], 16))
        self.assertEqual(sio_checksum(bytes.fromhex(response["payload"])),
                         int(response["payload_checksum"], 16))
