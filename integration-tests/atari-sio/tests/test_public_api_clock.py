"""Focused guards for the Story 2.4 public Clock/File acceptance increment."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
import run_boot_acceptance as boot_runner


class PublicApiClockTests(unittest.TestCase):
    def test_guest_uses_public_clock_and_raw_file_calls_without_sio_framing(self):
        source = (WORKSPACE / "repos/nio-core-apps/apps/platform/atari/fnaccept.c").read_text()
        for forbidden in ("SIOV", "ddevic", "dcomnd", "dstats", "0x7f"):
            self.assertNotIn(forbidden, source)
        self.assertIn("fn_init()", source)
        self.assertIn("fn_clock_get(&clock_value)", source)
        self.assertEqual(source.count("fn_raw_call(FN_DEVICE_FILE"), 2)
        self.assertIn("FNACCEPT_FILE_CMD_WRITE", source)
        self.assertIn("FNACCEPT_FILE_CMD_READ", source)
        self.assertIn("persist:///fnaccept-v1.bin", source)

    def test_native_clock_file_trace_requires_exact_three_w_p_r_exchanges(self):
        trace = "\n".join((
            "udp: Received 7 bytes: 02 7F 57 06 00 DC 02",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 05",
            "udp: Received 7 bytes: 02 7F 52 10 00 E1 06",
            "udp: Received 7 bytes: 02 7F 57 20 00 FF 07",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 08",
            "udp: Received 7 bytes: 02 7F 52 0A 00 DB 09",
            "udp: Received 7 bytes: 02 7F 57 12 00 F1 0A",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 0B",
            "udp: Received 7 bytes: 02 7F 52 17 00 E8 0C",
        ))
        self.assertEqual(boot_runner._clock_native_commands(trace), ["57", "50", "52"] * 3)
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


if __name__ == "__main__":
    unittest.main()
