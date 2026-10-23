"""Focused guards for the Story 2.4 public Clock acceptance increment."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
import run_boot_acceptance as boot_runner


class PublicApiClockTests(unittest.TestCase):
    def test_guest_contains_no_application_owned_sio_surface(self):
        source = (WORKSPACE / "repos/nio-core-apps/apps/platform/atari/fnaccept.c").read_text()
        for forbidden in ("SIOV", "ddevic", "dcomnd", "dstats", "0x7f", "fn_raw_call"):
            self.assertNotIn(forbidden, source)
        self.assertIn("fn_init()", source)
        self.assertIn("fn_clock_get(&clock_value)", source)

    def test_native_clock_trace_requires_exact_w_p_r_order(self):
        trace = "\n".join((
            "udp: Received 7 bytes: 02 7F 57 06 00 DC 02",
            "udp: Received 7 bytes: 02 7F 50 00 00 CF 05",
            "udp: Received 7 bytes: 02 7F 52 10 00 E1 06",
        ))
        self.assertEqual(boot_runner._clock_native_commands(trace), ["57", "50", "52"])
        with self.assertRaises(RuntimeError):
            boot_runner._clock_native_commands(trace.replace(" 50 ", " 52 ", 1))

    def test_expected_cc65_clock_is_full_little_endian_eight_bytes(self):
        self.assertEqual(boot_runner.PUBLIC_API_CLOCK_BYTES,
                         bytes.fromhex("08 07 06 05 04 03 02 01"))
        self.assertEqual(len(boot_runner.PUBLIC_API_CLOCK_BYTES), 8)


if __name__ == "__main__":
    unittest.main()
