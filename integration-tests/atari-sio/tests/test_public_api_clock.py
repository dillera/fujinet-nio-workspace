"""Focused guards for the Story 2.4 public Clock/File acceptance increment."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
import run_boot_acceptance as boot_runner


class PublicApiClockTests(unittest.TestCase):
    def test_guest_uses_public_apis_without_sio_framing(self):
        source = (WORKSPACE / "repos/nio-core-apps/apps/platform/atari/fnaccept.c").read_text()
        for forbidden in ("SIOV", "ddevic", "dcomnd", "dstats", "0x7f"):
            self.assertNotIn(forbidden, source)
        self.assertIn("fn_init()", source)
        self.assertIn("fn_clock_get(&clock_value)", source)
        self.assertEqual(source.count("fn_raw_call(FN_DEVICE_FILE"), 2)
        self.assertIn("FNACCEPT_FILE_CMD_WRITE", source)
        self.assertIn("FNACCEPT_FILE_CMD_READ", source)
        self.assertIn("persist:///fnaccept-v1.bin", source)
        for call in ("fn_open(&network_handle", "fn_write(network_handle", "fn_read(network_handle", "fn_close(network_handle"):
            self.assertIn(call, source)
        self.assertIn("fixture://nio-accept", source)

    def test_native_trace_requires_exact_clock_file_network_w_p_r_exchanges(self):
        commands = ("57", "50", "52") * 7
        trace = "\n".join(
            f"udp: Received 7 bytes: 02 7F {command} 00 00 CF {index:02X}"
            for index, command in enumerate(commands, start=1)
        )
        self.assertEqual(boot_runner._clock_native_commands(trace), list(commands))
        with self.assertRaises(RuntimeError):
            boot_runner._clock_native_commands(trace.replace(" 50 ", " 52 ", 1))

    def test_expected_cc65_clock_is_full_little_endian_eight_bytes(self):
        self.assertEqual(boot_runner.PUBLIC_API_CLOCK_BYTES,
                         bytes.fromhex("08 07 06 05 04 03 02 01"))
        self.assertEqual(len(boot_runner.PUBLIC_API_CLOCK_BYTES), 8)

    def test_file_marker_is_bounded_and_expected_in_result(self):
        self.assertEqual(boot_runner.PUBLIC_API_FILE_MARKER, b"ATARI-FILE-24")
        self.assertEqual(boot_runner.PUBLIC_API_FILE_WRITE_PAYLOAD_BYTES, 48)
        self.assertEqual(boot_runner.PUBLIC_API_FILE_READ_PAYLOAD_BYTES, 35)
        self.assertLessEqual(boot_runner.PUBLIC_API_FUJIBUS_HEADER_BYTES +
                             boot_runner.PUBLIC_API_FILE_WRITE_PAYLOAD_BYTES, 512)
        self.assertLessEqual(boot_runner.PUBLIC_API_FUJIBUS_HEADER_BYTES +
                             boot_runner.PUBLIC_API_FILE_READ_PAYLOAD_BYTES, 512)

    def test_network_fixture_payloads_and_reply_fit_native_packet_limit(self):
        self.assertEqual(boot_runner.PUBLIC_API_NETWORK_WRITE_MARKER, b"NET-WRITE-24")
        self.assertEqual(boot_runner.PUBLIC_API_NETWORK_REPLY_BYTES, b"NET-REPLY-24")
        for payload_length in (
                boot_runner.PUBLIC_API_NETWORK_OPEN_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_NETWORK_WRITE_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_NETWORK_READ_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_NETWORK_CLOSE_PAYLOAD_BYTES):
            self.assertLessEqual(boot_runner.PUBLIC_API_FUJIBUS_HEADER_BYTES + payload_length, 512)


if __name__ == "__main__":
    unittest.main()
