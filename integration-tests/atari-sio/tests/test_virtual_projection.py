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
                         "native-interrupted-r-recovery",
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

    def test_netsio_core_dispatch_capture_requires_exact_response_streams(self):
        # This is a parser regression only.  The executable projection feeds
        # its real production UDP capture to the same comparison function.
        log = "\n".join((
            "core-dispatch fixture route invocation 1",
            "udp: Received 7 bytes: 02 7F 51 00 00 D0 01",
            "udp: Sending 6 bytes: 81 01 01 41 00 00",
            "udp: Sending 2 bytes: 01 43",
            "udp: Sending 5 bytes: 02 01 00 02 00",
            "udp: Sending 2 bytes: 01 03",
            "udp: Received 7 bytes: 02 7F 57 06 00 DC 02",
            "udp: Sending 6 bytes: 81 02 01 41 07 00",
            "udp: Received 8 bytes: 02 01 02 06 00 09 00 03",
            "udp: Received 4 bytes: 09 12 04 12",
            "udp: Sending 6 bytes: 81 04 01 41 00 00",
            "udp: Sending 2 bytes: 01 43",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 05",
            "udp: Sending 6 bytes: 81 05 01 41 00 00",
            "udp: Sending 2 bytes: 01 43",
            "udp: Sending 4 bytes: 02 02 09 00",
            "udp: Sending 2 bytes: 01 0B",
            "udp: Received 7 bytes: 02 7F 52 09 00 DA 06",
            "udp: Sending 6 bytes: 81 06 01 41 00 00",
            "udp: Sending 2 bytes: 01 43",
            "udp: Sending 10 bytes: 02 01 02 09 00 0D 01 00 AA 55",
            "udp: Sending 2 bytes: 01 1A",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 07",
            "udp: Sending 6 bytes: 81 07 01 41 00 00",
            "udp: Sending 2 bytes: 01 43",
            "udp: Sending 4 bytes: 02 00 00 00",
            "udp: Sending 2 bytes: 01 00",
        ))
        observed = projection.compare_netsio_native_core_dispatch(log, self.manifest)
        self.assertEqual([item["fixture"] for item in observed],
                         ["q-idle", "w-core-dispatch", "p-core-dispatch-ready",
                          "r-core-dispatch", "reset-clears"])
        self.assertEqual(observed[3]["response"], {
            "controls": ["A", "C"],
            "payload": "01 02 09 00 0d 01 00 aa 55",
            "checksum": "1a",
        })
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_netsio_native_core_dispatch(log.replace("01 1A", "01 1B"), self.manifest)
        terminal_response = "\n".join((
            "udp: Sending 6 bytes: 81 06 01 41 00 00",
            "udp: Sending 2 bytes: 01 43",
            "udp: Sending 10 bytes: 02 01 02 09 00 0D 01 00 AA 55",
            "udp: Sending 2 bytes: 01 1A",
        ))
        reordered = "\n".join((
            "udp: Sending 6 bytes: 81 06 01 41 00 00",
            "udp: Sending 10 bytes: 02 01 02 09 00 0D 01 00 AA 55",
            "udp: Sending 2 bytes: 01 43",
            "udp: Sending 2 bytes: 01 1A",
        ))
        self.assertIn(terminal_response, log)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_netsio_native_core_dispatch(log.replace(terminal_response, reordered), self.manifest)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_netsio_native_core_dispatch(
                log.replace("\n" + terminal_response, "\n" + terminal_response +
                            "\nudp: Sending 2 bytes: 01 1A"), self.manifest)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_netsio_native_core_dispatch(
                log.replace("\nudp: Sending 10 bytes: 02 01 02 09 00 0D 01 00 AA 55", ""), self.manifest)

    def test_altirra_embedded_core_dispatch_requires_exact_pokey_wire_bytes(self):
        def pokey(direction, value):
            if direction == "Receive":
                return f"[SIODATA] [  0] Receive      < ${value:02X}"
            return f"[SIODATA] [  0] {direction:<8} ${value:02X} >"

        lines = []
        frames = (
            bytes.fromhex("7f 51 00 00 d0"), bytes.fromhex("7f 57 06 00 dc"),
            bytes.fromhex("7f 50 00 00 cf"), bytes.fromhex("7f 52 09 00 da"),
            bytes.fromhex("7f 50 00 00 cf"),
        )
        replies = (
            b"AC\x01\x00\x02\x00\x03", b"AAC", b"AC\x02\x09\x00\x0b",
            bytes.fromhex("41 43 01 02 09 00 0d 01 00 aa 55 1a"),
            b"AC\x00\x00\x00\x00",
        )
        for index, (frame, reply) in enumerate(zip(frames, replies)):
            lines.extend(pokey("SendCmd", value) for value in frame)
            if index == 1:
                lines.extend(pokey("Send", value) for value in bytes.fromhex("01 02 06 00 09 00 12"))
            lines.extend(pokey("Receive", value) for value in reply)
        trace = "\n".join(lines) + "\n"
        core_log = "[fujinetnio-projection] core dispatch fixture route invocation 1\n"
        observed = projection.compare_altirra_embedded_native_core_dispatch(
            trace, core_log, self.manifest)
        self.assertEqual([entry["fixture"] for entry in observed], [
            "q-idle", "w-core-dispatch", "p-core-dispatch-ready",
            "r-core-dispatch", "reset-clears",
        ])
        self.assertEqual(observed[3]["response"], {
            "controls": ["A", "C"],
            "payload": "01 02 09 00 0d 01 00 aa 55",
            "checksum": "1a",
        })
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_altirra_embedded_native_core_dispatch(
                trace.replace("Receive      < $AA", "Receive      < $AB", 1),
                core_log, self.manifest)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_altirra_embedded_native_core_dispatch(
                boot_runner._swap_embedded_terminal_r_response(trace), core_log, self.manifest)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_altirra_embedded_native_core_dispatch(trace, "", self.manifest)

    def test_altirra_embedded_wrong_r_groups_every_nak_retry_and_retains_reply(self):
        def pokey(direction, value):
            if direction == "Receive":
                return f"[SIODATA] [  0] Receive      < ${value:02X}"
            return f"[SIODATA] [  0] {direction:<8} ${value:02X} >"

        frames = (
            bytes.fromhex("7f 51 00 00 d0"), bytes.fromhex("7f 57 06 00 dc"),
            bytes.fromhex("7f 50 00 00 cf"), bytes.fromhex("7f 52 03 00 d4"),
            bytes.fromhex("7f 52 03 00 d4"), bytes.fromhex("7f 50 00 00 cf"),
            bytes.fromhex("7f 52 09 00 da"), bytes.fromhex("7f 50 00 00 cf"),
        )
        replies = (
            b"AC\x01\x00\x02\x00\x03", b"AAC", b"AC\x02\x09\x00\x0b",
            b"N", b"N", b"AC\x02\x09\x00\x0b",
            bytes.fromhex("41 43 01 02 09 00 0d 01 00 aa 55 1a"),
            b"AC\x00\x00\x00\x00",
        )
        lines = []
        for index, (frame, reply) in enumerate(zip(frames, replies)):
            lines.extend(pokey("SendCmd", value) for value in frame)
            if index == 1:
                lines.extend(pokey("Send", value)
                             for value in bytes.fromhex("01 02 06 00 09 00 12"))
            lines.extend(pokey("Receive", value) for value in reply)
        trace = "\n".join(lines) + "\n"
        core_log = "[fujinetnio-projection] core dispatch fixture route invocation 1\n"
        observed = projection.compare_altirra_embedded_native_wrong_r_retention(
            trace, core_log, self.manifest)
        self.assertEqual([entry["fixture"] for entry in observed], [
            "q-idle", "w-core-dispatch", "p-core-dispatch-ready",
            "r-wrong-length-retains", "p-core-dispatch-ready",
            "r-core-dispatch", "reset-clears",
        ])
        self.assertEqual(observed[3]["siov_attempts"], 2)
        self.assertEqual(observed[3]["response"], {
            "controls": ["N"], "payload": "", "checksum": None,
        })
        self.assertEqual(observed[4]["response"]["payload"], "02 09 00")
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_altirra_embedded_native_wrong_r_retention(
                boot_runner._embedded_wrong_r_mutation(trace),
                core_log, self.manifest)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_altirra_embedded_native_wrong_r_retention(
                boot_runner._embedded_wrong_r_mutation(trace, retained_response=True),
                core_log, self.manifest)

    def test_netsio_wrong_r_retention_requires_nak_then_unchanged_response(self):
        log = "\n".join((
            "core-dispatch fixture route invocation 1",
            "udp: Received 7 bytes: 02 7F 51 00 00 D0 01",
            "udp: Sending 6 bytes: 81 01 01 41 00 00", "udp: Sending 2 bytes: 01 43",
            "udp: Sending 5 bytes: 02 01 00 02 00", "udp: Sending 2 bytes: 01 03",
            "udp: Received 7 bytes: 02 7F 57 06 00 DC 02",
            "udp: Sending 6 bytes: 81 02 01 41 07 00",
            "udp: Received 8 bytes: 02 01 02 06 00 09 00 03", "udp: Received 4 bytes: 09 12 04 12",
            "udp: Sending 6 bytes: 81 04 01 41 00 00", "udp: Sending 2 bytes: 01 43",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 05",
            "udp: Sending 6 bytes: 81 05 01 41 00 00", "udp: Sending 2 bytes: 01 43",
            "udp: Sending 4 bytes: 02 02 09 00", "udp: Sending 2 bytes: 01 0B",
            "udp: Received 7 bytes: 02 7F 52 03 00 D4 06",
            "udp: Sending 6 bytes: 81 06 01 4E 00 00",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 07",
            "udp: Sending 6 bytes: 81 07 01 41 00 00", "udp: Sending 2 bytes: 01 43",
            "udp: Sending 4 bytes: 02 02 09 00", "udp: Sending 2 bytes: 01 0B",
            "udp: Received 7 bytes: 02 7F 52 09 00 DA 08",
            "udp: Sending 6 bytes: 81 08 01 41 00 00", "udp: Sending 2 bytes: 01 43",
            "udp: Sending 10 bytes: 02 01 02 09 00 0D 01 00 AA 55", "udp: Sending 2 bytes: 01 1A",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 09",
            "udp: Sending 6 bytes: 81 09 01 41 00 00", "udp: Sending 2 bytes: 01 43",
            "udp: Sending 4 bytes: 02 00 00 00", "udp: Sending 2 bytes: 01 00",
        ))
        observed = projection.compare_netsio_native_wrong_r_retention(log, self.manifest)
        self.assertEqual([item["fixture"] for item in observed], [
            "q-idle", "w-core-dispatch", "p-core-dispatch-ready", "r-wrong-length-retains",
            "p-core-dispatch-ready", "r-core-dispatch", "reset-clears",
        ])
        self.assertEqual(observed[3]["response"], {"controls": ["N"], "payload": "", "checksum": None})
        self.assertEqual(observed[3]["siov_attempts"], 1)
        self.assertEqual(observed[4]["response"]["payload"], "02 09 00")
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_netsio_native_wrong_r_retention(log.replace("81 06 01 4E", "81 06 01 45"), self.manifest)
        wrong_r_and_retained_p = "\n".join((
            "udp: Received 7 bytes: 02 7F 52 03 00 D4 06", "udp: Sending 6 bytes: 81 06 01 4E 00 00",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 07", "udp: Sending 6 bytes: 81 07 01 41 00 00",
            "udp: Sending 2 bytes: 01 43", "udp: Sending 4 bytes: 02 02 09 00", "udp: Sending 2 bytes: 01 0B",
        ))
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_netsio_native_wrong_r_retention(
                log.replace(wrong_r_and_retained_p, wrong_r_and_retained_p.replace("02 02 09 00", "02 02 08 00")),
                self.manifest)

    def test_netsio_reset_to_idle_requires_captured_reset_and_distinct_second_dispatch(self):
        def read(frame, sequence, response):
            return [f"udp: Received 7 bytes: 02 {frame} {sequence:02X}", *response]

        q = ["udp: Sending 6 bytes: 81 01 01 41 00 00", "udp: Sending 2 bytes: 01 43",
             "udp: Sending 5 bytes: 02 01 00 02 00", "udp: Sending 2 bytes: 01 03"]
        w = ["udp: Sending 6 bytes: 81 02 01 41 07 00",
             "udp: Received 8 bytes: 02 01 02 06 00 09 00 03",
             "udp: Received 4 bytes: 09 12 04 12",
             "udp: Sending 6 bytes: 81 04 01 41 00 00", "udp: Sending 2 bytes: 01 43"]
        p_ready = ["udp: Sending 6 bytes: 81 05 01 41 00 00", "udp: Sending 2 bytes: 01 43",
                   "udp: Sending 4 bytes: 02 02 09 00", "udp: Sending 2 bytes: 01 0B"]
        p_idle = ["udp: Sending 6 bytes: 81 06 01 41 00 00", "udp: Sending 2 bytes: 01 43",
                  "udp: Sending 4 bytes: 02 00 00 00", "udp: Sending 2 bytes: 01 00"]
        second_w = ["udp: Sending 6 bytes: 81 07 01 41 07 00",
                    "udp: Received 8 bytes: 02 01 03 06 00 0A 00 08",
                    "udp: Received 4 bytes: 09 14 09 14",
                    "udp: Sending 6 bytes: 81 09 01 41 00 00", "udp: Sending 2 bytes: 01 43"]
        second_p = ["udp: Sending 6 bytes: 81 0A 01 41 00 00", "udp: Sending 2 bytes: 01 43",
                    "udp: Sending 4 bytes: 02 02 09 00", "udp: Sending 2 bytes: 01 0B"]
        second_r = ["udp: Sending 6 bytes: 81 0B 01 41 00 00", "udp: Sending 2 bytes: 01 43",
                    "udp: Sending 10 bytes: 02 01 03 09 00 0E 01 00 33 CC", "udp: Sending 2 bytes: 01 1C"]
        final_idle = ["udp: Sending 6 bytes: 81 0C 01 41 00 00", "udp: Sending 2 bytes: 01 43",
                      "udp: Sending 4 bytes: 02 00 00 00", "udp: Sending 2 bytes: 01 00"]
        log = "\n".join((
            *read("7F 51 00 00 D0", 1, q),
            *read("7F 57 06 00 DC", 2, w),
            "core-dispatch fixture route invocation 1",
            *read("7F 50 00 00 CF", 5, p_ready),
            "udp: Received 1 bytes: FF", "l_netsio: COLD_RESET",
            *read("7F 50 00 00 CF", 6, p_idle),
            *read("7F 57 06 00 DC", 7, second_w),
            "core-dispatch fixture route invocation 2",
            *read("7F 50 00 00 CF", 10, second_p),
            *read("7F 52 09 00 DA", 11, second_r),
            *read("7F 50 00 00 CF", 12, final_idle),
        ))
        observed = projection.compare_netsio_native_reset_to_idle(log, self.manifest)
        self.assertEqual([item["fixture"] for item in observed], [
            "q-idle", "w-core-dispatch", "p-core-dispatch-ready", "reset-clears",
            "w-core-dispatch-after-reset", "p-core-dispatch-ready",
            "r-core-dispatch-after-reset", "reset-clears",
        ])
        self.assertEqual(observed[6]["response"]["payload"], "01 03 09 00 0e 01 00 33 cc")
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_netsio_native_reset_to_idle(
                log.replace("udp: Received 1 bytes: FF\n", "", 1), self.manifest)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_netsio_native_reset_to_idle(
                log.replace("udp: Sending 4 bytes: 02 00 00 00", "udp: Sending 4 bytes: 02 00 01 00", 1),
                self.manifest)

    def test_altirra_embedded_reset_to_idle_requires_lifecycle_idle_and_distinct_w(self):
        def pokey(direction, value):
            if direction == "Receive":
                return f"[SIODATA] [  0] Receive      < ${value:02X}"
            return f"[SIODATA] [  0] {direction:<8} ${value:02X} >"

        frames = (
            bytes.fromhex("7f 51 00 00 d0"), bytes.fromhex("7f 57 06 00 dc"),
            bytes.fromhex("7f 50 00 00 cf"), bytes.fromhex("7f 50 00 00 cf"),
            bytes.fromhex("7f 57 06 00 dc"), bytes.fromhex("7f 50 00 00 cf"),
            bytes.fromhex("7f 52 09 00 da"), bytes.fromhex("7f 50 00 00 cf"),
        )
        replies = (
            b"AC\x01\x00\x02\x00\x03", b"AAC", b"AC\x02\x09\x00\x0b",
            b"AC\x00\x00\x00\x00", b"AAC", b"AC\x02\x09\x00\x0b",
            bytes.fromhex("41 43 01 03 09 00 0e 01 00 33 cc 1c"),
            b"AC\x00\x00\x00\x00",
        )
        data = {
            1: bytes.fromhex("01 02 06 00 09 00 12"),
            4: bytes.fromhex("01 03 06 00 0a 00 14"),
        }
        lines = []
        for index, (frame, reply) in enumerate(zip(frames, replies)):
            lines.extend(pokey("SendCmd", value) for value in frame)
            lines.extend(pokey("Send", value) for value in data.get(index, b""))
            lines.extend(pokey("Receive", value) for value in reply)
        trace = "\n".join(lines) + "\n"
        core_log = "\n".join((
            "[fujinetnio-projection] core dispatch fixture route invocation 1",
            "[fujinetnio] embedded FujiNet-NIO device ColdReset",
            "[fujinetnio-projection] core dispatch fixture route invocation 2",
        )) + "\n"
        observed = projection.compare_altirra_embedded_native_reset_to_idle(
            trace, core_log, self.manifest)
        self.assertEqual([entry["fixture"] for entry in observed], [
            "q-idle", "w-core-dispatch", "p-core-dispatch-ready", "reset-clears",
            "w-core-dispatch-after-reset", "p-core-dispatch-ready",
            "r-core-dispatch-after-reset", "reset-clears",
        ])
        self.assertEqual(observed[6]["response"]["payload"], "01 03 09 00 0e 01 00 33 cc")
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_altirra_embedded_native_reset_to_idle(
                boot_runner._embedded_replace_response(
                    trace, bytes.fromhex("7f 50 00 00 cf"), 1, b"AC\x02\x09\x00\x0b"),
                core_log, self.manifest)
        with self.assertRaises(projection.ProjectionMismatch):
            projection.compare_altirra_embedded_native_reset_to_idle(
                boot_runner._embedded_replace_w_data(
                    trace, 1, bytes.fromhex("01 02 06 00 09 00"), 0x12),
                core_log, self.manifest)
        run = {
            "siov_statuses": "01 01 01 01 01 01 01 01",
            "p_ready": "02 09 00", "post_reset_idle": "00 00 00",
            "post_reset_ready": "02 09 00",
            "post_reset_reply": "01 03 09 00 0e 01 00 33 cc",
            "post_reset_terminal_idle": "00 00 00",
            "reset_event": {"kind": "altirra-embedded-device-cold-reset", "lifecycle": "cold",
                            "tag": "fujinetnio", "path": "/fujinetnio",
                            "guest_step_before_reset": 4},
        }
        boot_runner._assert_embedded_reset_to_idle_guest_state(run)
        run.pop("reset_event")
        with self.assertRaises(RuntimeError):
            boot_runner._assert_embedded_reset_to_idle_guest_state(run)

    def test_interrupted_r_fixture_sequence_and_guest_failure_check(self):
        self.assertEqual(projection.native_projection_fixture_ids(
            "native-interrupted-r-recovery", self.manifest), [
                "q-idle", "w-core-dispatch", "p-core-dispatch-ready",
                "r-core-dispatch-interrupted-consumes", "p-idle-after-consumed-r",
                "w-core-dispatch-after-interrupted-r", "p-core-dispatch-ready",
                "r-core-dispatch-after-interrupted-r", "p-idle-after-consumed-r",
            ])
        run = {
            "siov_statuses": "01 01 01 8b 01 01 01 01 01",
            "post_interruption_idle": "00 00 00",
            "recovery_ready": "02 09 00",
            "recovery_reply": "01 04 09 00 0f 01 00 5a a5",
            "recovery_terminal_idle": "00 00 00",
        }
        boot_runner._assert_interrupted_r_guest_state(run)
        run["siov_statuses"] = "01 01 01 01 01 01 01 01 01"
        with self.assertRaises(RuntimeError):
            boot_runner._assert_interrupted_r_guest_state(run)

    def test_capacity_fixture_sequence_and_guest_boundary_checks(self):
        self.assertEqual(projection.native_projection_fixture_ids(
            "native-capacity-bounds", self.manifest), [
                "q-idle", "w-511", "p-ready-7", "r-ready-7", "w-512",
                "p-ready-512", "r-ready-512", "p-idle-after-consumed-r",
                "w-513-rejected", "w-oversize-response", "p-ready-7",
                "r-bounded-error-response", "p-idle-after-consumed-r",
            ])
        fixtures = {item["id"]: item for item in projection.load_json(projection.NIO_PATH)["scenarios"]}
        run = {
            "siov_statuses": "01 01 01 01 01 01 01 01 8b 01 01 01 01",
            "capacity_ready_512": "02 00 02",
            "capacity_idle_after_512": "00 00 00",
            "capacity_bounded_ready": "02 07 00",
            "capacity_bounded_reply": "01 07 07 00 17 01 07",
            "capacity_terminal_idle": "00 00 00",
            "capacity_response": projection.fixture_payload(fixtures["r-ready-512"]).hex(" "),
            "capacity_canaries": {"request_low": "5a", "request_high": "a5",
                                  "response_low": "5a", "response_high": "a5"},
        }
        boot_runner._assert_capacity_guest_state(run)
        run["capacity_canaries"]["response_high"] = "00"
        with self.assertRaises(RuntimeError):
            boot_runner._assert_capacity_guest_state(run)

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
