"""Stdlib-only consistency checks for the literal Atari Disk SIO v1 contract."""

import json
import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKSPACE = ROOT.parents[1]
FIXTURE = json.loads((ROOT / "fixtures" / "disk_v1.json").read_text())
MANIFEST = json.loads((ROOT / "fixtures" / "disk_v1.manifest.json").read_text())
SUPPORTED = {0x50, 0x52, 0x53, 0x57}
ERROR_STATUS = {
    "BadImage": "04 5f 0f 00", "FileNotFound": "04 5f 0f 00",
    "GeometryRequired": "04 5f 0f 00", "NoSuchFileSystem": "04 5f 0f 00",
    "NotMounted": "04 5f 0f 00", "OpenFailed": "04 5f 0f 00",
    "ReadOnly": "0c 9f 0f 00", "InvalidGeometry": "04 cf 0f 00",
    "InvalidRequest": "04 cf 0f 00", "InvalidSlot": "04 cf 0f 00",
    "OutOfRange": "04 cf 0f 00", "InternalError": "04 db 0f 00",
    "IoError": "04 db 0f 00",
}


def octets(value):
    return bytes.fromhex(value)


def checksum(data):
    total = sum(data)
    while total > 0xFF:
        total = (total & 0xFF) + (total >> 8)
    return total


class DiskV1FixtureTests(unittest.TestCase):
    def setUp(self):
        self.scenarios = FIXTURE["scenarios"]
        self.by_id = {item["id"]: item for item in self.scenarios}
        self.geometries = {item["id"]: item for item in FIXTURE["geometries"]}

    def status(self, item):
        return octets(item["status_after"])

    def transfer_length(self, item):
        geometry = self.geometries[item["geometry"]]
        return 128 if geometry["sector_bytes"] == 256 and item["sector"] <= 3 else geometry["sector_bytes"]

    def test_schema_stable_ids_and_normal_routing(self):
        self.assertEqual(FIXTURE["format"], "atari-disk-sio-v1")
        self.assertEqual(FIXTURE["supported_commands"], ["0x50", "0x52", "0x53", "0x57"])
        self.assertIn("no physical timing", FIXTURE["scope"])
        self.assertEqual(len(self.by_id), len(self.scenarios))
        self.assertEqual(set(FIXTURE["devices"].values()), set(range(8)))
        for item in self.scenarios:
            self.assertRegex(item["id"], r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
            self.assertTrue(item["label"])
            self.assertIn(item["device"], FIXTURE["devices"])
            self.assertEqual(item["slot"], FIXTURE["devices"][item["device"]])
        normal_devices = {item["device"] for item in self.scenarios if item.get("mode") == "normal"}
        self.assertEqual(normal_devices, set(FIXTURE["devices"]))

    def test_command_frame_and_v1_rejection_rules(self):
        for item in self.scenarios:
            command = octets(item["command"])
            self.assertEqual(command[0], int(item["device"], 16), item["id"])
            if item.get("malformed") == "length":
                self.assertEqual(len(command), 4, item["id"])
                self.assertEqual(item["phases"], ["N"])
                self.assertFalse(item["disk_service"])
                continue
            self.assertEqual(len(command), 5, item["id"])
            if item.get("malformed") == "checksum":
                self.assertNotEqual(checksum(command[:4]), command[4])
                self.assertEqual(item["phases"], ["N"])
                self.assertFalse(item["disk_service"])
                continue
            self.assertEqual(checksum(command[:4]), command[4], item["id"])
            if item.get("unsupported"):
                self.assertNotIn(command[1], SUPPORTED)
                self.assertEqual(item["phases"], ["N"])
                self.assertFalse(item["disk_service"])
                continue
            self.assertIn(command[1], SUPPORTED, item["id"])
            if command[1] == 0x53:
                self.assertEqual(command[2:4], b"\0\0", item["id"])
            else:
                self.assertEqual(command[2] | command[3] << 8, item["sector"], item["id"])

    def test_literal_data_checksums_lengths_and_geometry_mapping(self):
        for item in self.scenarios:
            phases = item["phases"]
            data_phases = [phase for phase in phases if phase.startswith("data:")]
            if data_phases:
                self.assertEqual(len(data_phases), 1, item["id"])
                data = octets(item["data"])
                declared = int(data_phases[0].split(":")[1])
                declared_sum = next(int(p.split(":")[1], 16) for p in phases if p.startswith("sum:"))
                self.assertEqual(len(data), declared, item["id"])
                self.assertEqual(checksum(data), declared_sum, item["id"])
                self.assertIn(item["geometry"], self.geometries)
                self.assertTrue(self.geometries[item["geometry"]]["accepted"])
                self.assertEqual(declared, self.transfer_length(item), item["id"])
                self.assertEqual(item["lba"], item["sector"] - 1, item["id"])
                expected_offset = 128 * (item["sector"] - 1)
                if self.geometries[item["geometry"]]["sector_bytes"] == 256 and item["sector"] >= 4:
                    expected_offset = 384 + 256 * (item["sector"] - 4)
                self.assertEqual(item["offset"], expected_offset, item["id"])
            if "write_data" in item:
                data = octets(item["write_data"])
                self.assertEqual(len(data), item["write_length"], item["id"])
                self.assertEqual(len(data), self.transfer_length(item), item["id"])
                valid = checksum(data) == int(item["write_sum"], 16)
                self.assertEqual(valid, item["id"] != "bad-put-data-checksum", item["id"])
                self.assertEqual(phases[:2], ["A", f"host-data:{len(data)}"])
                if item.get("postimage") is None:
                    self.assertIn(phases[-1], ("N", "E"))
                else:
                    self.assertEqual(item["postimage"], item["write_data"])

    def test_pinned_autorun_boot_goldens_are_literal_payload_slices(self):
        source = FIXTURE["source_image"]
        image = WORKSPACE / source["path"]
        self.assertEqual(source["atr_header_bytes"], 16)
        self.assertEqual(source["atr_header"], "96 02 e8 2c 00 01 00 00 00 00 00 00 00 00 00 00")
        self.assertEqual(source["sha256"], "0d824da3bf8addf568af3224de73c89adb0e71eb679f7778c01264a22e751eb6")
        for sector in range(1, 5):
            golden = source["sectors"][str(sector)]
            literal = octets(golden["data"])
            self.assertNotEqual(literal, b"\\0" * len(literal))
            self.assertEqual(checksum(literal), int(golden["checksum"], 16))
            self.assertEqual(hashlib.sha256(literal).hexdigest(), golden["sha256"])
            scenario = self.by_id[f"boot-config-read-sector-{sector}"]
            self.assertEqual(octets(scenario["data"]), literal)
            self.assertEqual(scenario["source_image_sector"], sector)
        if image.exists():
            payload = image.read_bytes()
            self.assertEqual(payload[:source["atr_header_bytes"]], octets(source["atr_header"]))
            self.assertEqual(hashlib.sha256(payload).hexdigest(), source["sha256"])
            for golden in source["sectors"].values():
                self.assertEqual(octets(golden["data"]), payload[golden["atr_offset"]:golden["atr_offset"] + golden["bytes"]])

    def test_command_phases_follow_the_normative_v1_grammar(self):
        for item in self.scenarios:
            command = octets(item["command"])
            if len(command) != 5 or item.get("malformed") == "checksum" or item.get("unsupported"):
                continue
            kind = command[1]
            phases = item["phases"]
            if kind == 0x52:
                if phases == ["A", "E"]:
                    continue
                self.assertEqual(phases, ["A", "C", next(p for p in phases if p.startswith("data:")), next(p for p in phases if p.startswith("sum:"))], item["id"])
            elif kind == 0x53:
                self.assertEqual(phases[:2], ["A", "C"], item["id"])
            elif kind in (0x50, 0x57):
                self.assertEqual(phases[:2], ["A", next(p for p in phases if p.startswith("host-data:"))], item["id"])
                self.assertIn(phases[2:], (["N"], ["A", "C"], ["A", "E"]), item["id"])

    def test_structured_projection_state_and_effects_are_reproducible(self):
        projections = {entry["id"]: entry for entry in MANIFEST["projections"]}
        for item in self.scenarios:
            self.assertIsInstance(item["initial_state"], dict, item["id"])
            self.assertIsInstance(item["effects"], dict, item["id"])
            self.assertEqual(projections[item["id"]]["preconditions"], item["initial_state"])
            self.assertEqual(projections[item["id"]]["effects"], item["effects"])

    def test_write_success_has_nonzero_classic_256_readback_successor(self):
        write = self.by_id["normal-restored-write-verify"]
        readback = self.by_id["normal-restored-write-verify-readback"]
        self.assertEqual(write["geometry"], "geo-classic-256")
        self.assertNotEqual(octets(write["initial_image"]), octets(write["write_data"]))
        self.assertNotEqual(octets(write["write_data"]), b"\\0" * 256)
        self.assertEqual(len(octets(write["write_data"])), 256)
        self.assertEqual(checksum(octets(write["write_data"])), int(write["write_sum"], 16))
        self.assertEqual(readback["predecessor"], write["id"])
        self.assertEqual(readback["data"], write["postimage"])
        self.assertEqual(readback["phases"][-1], f"sum:{write['write_sum']}")

    def test_geometry_acceptance_and_rejection_vectors(self):
        self.assertEqual(set(self.geometries), {"geo-128", "geo-classic-256", "geo-malformed-128", "geo-malformed-small-256", "geo-ordinary-512"})
        for geometry in self.geometries.values():
            if geometry["sector_bytes"] == 128:
                self.assertEqual(geometry["accepted"], geometry["payload_bytes"] % 128 == 0)
            elif geometry["sector_bytes"] == 256:
                valid = geometry["payload_bytes"] >= 384 and (geometry["payload_bytes"] - 384) % 256 == 0
                self.assertEqual(geometry["accepted"], valid)
            else:
                self.assertFalse(geometry["accepted"])
        for identifier in ("malformed-128-geometry", "malformed-small-256-geometry", "ordinary-512-geometry"):
            item = self.by_id[identifier]
            self.assertFalse(self.geometries[item["geometry"]]["accepted"])
            self.assertEqual(item["phases"], ["A", "E"])
            self.assertEqual(item["error"], "InvalidGeometry")

    def test_error_mapping_status_bits_and_predecessor_traces(self):
        self.assertEqual(FIXTURE["error_mapping"], {name: ["E", status] for name, status in ERROR_STATUS.items()})
        observed = {item.get("error") for item in self.scenarios} - {None}
        self.assertTrue({"OpenFailed", "ReadOnly", "InvalidRequest", "OutOfRange", "InvalidGeometry", "IoError"} <= observed)
        for item in self.scenarios:
            if "error" in item:
                self.assertEqual(item["phases"][-1], "E", item["id"])
                self.assertEqual(item["status_after"], ERROR_STATUS[item["error"]], item["id"])
            if "status_after" in item:
                status = self.status(item)
                self.assertEqual(len(status), 4, item["id"])
                self.assertEqual(status[2:], b"\x0f\0", item["id"])
                self.assertEqual(status[0] & 0xD0, 0, item["id"])
        for item in self.scenarios:
            if "predecessor" in item:
                prior = self.by_id[item["predecessor"]]
                self.assertEqual((item["device"], item["slot"]), (prior["device"], prior["slot"]), item["id"])
                self.assertIn("status_after", prior, item["id"])
                if octets(item["command"])[1] == 0x53:
                    status_phase = next(phase for phase in item["phases"] if phase.startswith("status:"))
                    self.assertEqual(status_phase.split(":", 1)[1], prior["status_after"], item["id"])

    def test_complete_nonblocking_status_phases_and_clearing(self):
        for item in self.scenarios:
            if octets(item["command"])[1:2] == b"S":
                self.assertEqual(item["phases"][:2], ["A", "C"], item["id"])
                self.assertEqual(len(item["phases"]), 4, item["id"])
                status = octets(item["phases"][2].split(":", 1)[1])
                self.assertEqual(checksum(status), int(item["phases"][3].split(":", 1)[1], 16), item["id"])
                self.assertFalse(item.get("ensure_mounted", False), item["id"])
        self.assertEqual(self.by_id["status-after-successful-read"]["phases"][2], "status:00 df 0f 00")
        self.assertEqual(self.by_id["status-after-bad-put-checksum"]["phases"][2], "status:02 df 0f 00")
        self.assertEqual(self.by_id["status-after-malformed-command"]["phases"][2], "status:01 df 0f 00")

    def test_write_verify_failure_records_accepted_postimage(self):
        item = self.by_id["write-verify-readback-failure"]
        self.assertEqual(item["phases"], ["A", "host-data:128", "A", "E"])
        self.assertEqual(item["verify"], "readback-mismatch")
        self.assertEqual(item["postimage"], item["write_data"])
        self.assertEqual(item["error"], "IoError")

    def test_density_bit_tracks_classic_256_media(self):
        self.assertEqual(self.by_id["normal-restored-write-verify"]["status_after"], "20 df 0f 00")
        self.assertEqual(self.by_id["normal-restored-put"]["status_after"], "00 df 0f 00")
        self.assertEqual(self.by_id["status-after-classic-256-write"]["phases"][2], "status:20 df 0f 00")

    def test_manifest_is_complete_virtual_projection(self):
        self.assertEqual(MANIFEST["format"], "atari-disk-sio-v1-projection")
        self.assertIn("not physical", MANIFEST["scope"])
        projected = {entry["id"]: entry for entry in MANIFEST["projections"]}
        self.assertEqual(set(projected), set(self.by_id))
        for identifier, item in self.by_id.items():
            self.assertEqual(projected[identifier]["ordered_phases"], item["phases"], identifier)
            self.assertTrue(projected[identifier]["input_state"])

    def test_invalid_sector_status_chain_is_contiguous_and_clears(self):
        chain = ["zero-sector-execution-failure", "status-retains-error", "status-retains-error-again", "successful-read-clears-error", "status-after-successful-read"]
        for previous, current in zip(chain, chain[1:]):
            item = self.by_id[current]
            self.assertEqual(item["predecessor"], previous)
            self.assertEqual((item["device"], item["slot"]), (self.by_id[previous]["device"], self.by_id[previous]["slot"]))
            self.assertEqual(item["initial_state"], self.by_id[previous]["initial_state"])
        self.assertEqual(self.by_id["status-retains-error"]["phases"][2], "status:04 cf 0f 00")
        self.assertEqual(self.by_id["status-retains-error-again"]["phases"][2], "status:04 cf 0f 00")
        self.assertEqual(self.by_id["status-after-successful-read"]["phases"][2], "status:00 df 0f 00")


if __name__ == "__main__":
    unittest.main()
