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
        self.assertEqual(source.count("fn_raw_call(FN_DEVICE_FILE"), 3)
        self.assertIn("FNACCEPT_FILE_CMD_WRITE", source)
        self.assertIn("FNACCEPT_FILE_CMD_READ", source)
        self.assertIn("persist:///fnaccept-v1.bin", source)
        self.assertIn("persist:///fnaccept-recovered-v1.bin", source)
        self.assertIn("capture_memory_snapshot()", source)
        self.assertNotIn("*dmactl", source)
        for call in ("fn_open(&network_handle", "fn_write(network_handle", "fn_read(network_handle", "fn_close(network_handle"):
            self.assertIn(call, source)
        self.assertIn("fixture://nio-accept", source)
        for call in ("fn_disk_info(FNACCEPT_DISK_SLOT", "fn_disk_write_sector(FNACCEPT_DISK_SLOT",
                     "fn_disk_flush(FNACCEPT_DISK_SLOT", "fn_disk_read_sector(FNACCEPT_DISK_SLOT"):
            self.assertIn(call, source)

    def test_native_trace_requires_exact_clock_file_network_w_p_r_exchanges(self):
        commands = ("57", "50", "52") * 11
        trace = "\n".join(
            f"udp: Received 7 bytes: 02 7F {command} 00 00 CF {index:02X}"
            for index, command in enumerate(commands, start=1)
        )
        self.assertEqual(boot_runner._clock_native_commands(trace), list(commands))
        with self.assertRaises(RuntimeError):
            boot_runner._clock_native_commands(trace.replace(" 50 ", " 52 ", 1))

    def test_rejected_file_w_relay_requires_bad_checksum_nak_and_direct_new_w(self):
        original = bytes((0x7f, ord('W'), 0x30, 0x00))
        original += bytes((boot_runner._sio_checksum(original),))
        delivered = original[:-1] + bytes((original[-1] ^ 1,))
        recovery_w = bytes((0x7f, ord('W'), 0x40, 0x00, 0))
        commands = [recovery_w,
                    bytes((0x7f, ord('P'), 0, 0, 0)),
                    bytes((0x7f, ord('R'), 0, 0, 0)),
                    recovery_w,
                    bytes((0x7f, ord('P'), 0, 0, 0)),
                    bytes((0x7f, ord('R'), 0, 0, 0))]
        summary = {
            'failure': None,
            'rejected_attempts': [{'original': original.hex(' '),
                                   'delivered': delivered.hex(' ')}],
            'endpoint_naks': ['01 4e'],
            'recovery_w_seen': True,
            'unexpected_recovery_commands': [],
            'commands_after_rejection': [command.hex(' ') for command in commands],
        }
        boot_runner._validate_rejected_file_w_relay(summary)
        summary['endpoint_naks'].append('01 4e')
        with self.assertRaises(RuntimeError):
            boot_runner._validate_rejected_file_w_relay(summary)
        summary['endpoint_naks'].pop()
        summary['commands_after_rejection'][0] = bytes((0x7f, ord('P'), 0, 0, 0)).hex(' ')
        with self.assertRaises(RuntimeError):
            boot_runner._validate_rejected_file_w_relay(summary)

    def test_ready_length_relay_requires_retained_response_drain_before_new_w(self):
        def frame(command, aux=0):
            value = bytes((0x7f, ord(command), aux & 0xff, aux >> 8))
            return value + bytes((boot_runner._sio_checksum(value),))

        # The initial accepted W/P is followed by one physical wrong-length
        # R, then recovery P/R using the original length before distinct W.
        original = bytes((2, 15, 0))
        delivered = bytes((2, 14, 0))
        def write_packet(uri, marker):
            body = bytes((1, len(uri), 0)) + uri + b'\0\0\0\0' + bytes((len(marker), 0)) + marker
            packet = bytearray((0xfe, 4, 6 + len(body), 0, 0, 0)) + body
            packet[4] = boot_runner._sio_checksum(packet[:4] + packet[5:])
            return bytes(packet)
        initial_w = write_packet(boot_runner.PUBLIC_API_FILE_URI,
                                 boot_runner.PUBLIC_API_FILE_MARKER)
        distinct_w = write_packet(boot_runner.PUBLIC_API_FILE_RECOVERY_URI,
                                  boot_runner.PUBLIC_API_FILE_RECOVERY_MARKER)
        recovery_reply = bytearray((0xfe, 4, 15, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0))
        recovery_reply[4] = boot_runner._sio_checksum(recovery_reply[:4] + recovery_reply[5:])
        summary = {
            'failure': None,
            'fault_applied': True,
            'ready_payload': original.hex(' '),
            'delivered_ready_payload': delivered.hex(' '),
            'ready_checksums': {'original': boot_runner._sio_checksum(original),
                                'delivered': boot_runner._sio_checksum(delivered)},
            'recovery_ready_payload': original.hex(' '),
            'recovery_ready_checksum': boot_runner._sio_checksum(original),
            'wrong_r_attempts': [frame('R', 14).hex(' ')],
            'wrong_r_naks': ['01 4e'],
            'recovery_p_seen': True,
            'recovery_r_seen': True,
            'distinct_w_seen': True,
            'command_frames': [frame('W', len(initial_w)).hex(' '), frame('P').hex(' '),
                               frame('R', 14).hex(' '), frame('P').hex(' '),
                               frame('R', 15).hex(' '), frame('W', len(distinct_w)).hex(' '),
                               frame('P').hex(' '), frame('R', 15).hex(' ')],
            'w_payloads': {'initial': initial_w.hex(' '), 'distinct': distinct_w.hex(' ')},
            'w_checksums': {'initial': boot_runner._sio_checksum(initial_w),
                            'distinct': boot_runner._sio_checksum(distinct_w)},
            'recovery_r_payload': bytes(recovery_reply).hex(' '),
            'recovery_r_checksum': boot_runner._sio_checksum(recovery_reply),
        }
        boot_runner._validate_ready_length_relay(summary)
        # Negative: a new W before recovery R is unsafe and must fail.
        summary['command_frames'][4] = frame('W', len(distinct_w)).hex(' ')
        with self.assertRaises(RuntimeError):
            boot_runner._validate_ready_length_relay(summary)
        summary['command_frames'][4] = frame('R', 15).hex(' ')
        summary['recovery_ready_payload'] = delivered.hex(' ')
        with self.assertRaises(RuntimeError):
            boot_runner._validate_ready_length_relay(summary)
        summary['recovery_ready_payload'] = original.hex(' ')
        summary['wrong_r_naks'] = ['01 41']
        with self.assertRaises(RuntimeError):
            boot_runner._validate_ready_length_relay(summary)

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
        self.assertLessEqual(boot_runner.PUBLIC_API_FUJIBUS_HEADER_BYTES +
                             boot_runner.PUBLIC_API_FILE_RECOVERY_WRITE_PAYLOAD_BYTES, 512)
        self.assertLessEqual(boot_runner.PUBLIC_API_FUJIBUS_HEADER_BYTES +
                             boot_runner.PUBLIC_API_FILE_RECOVERY_READ_PAYLOAD_BYTES, 512)

    def test_network_fixture_payloads_and_reply_fit_native_packet_limit(self):
        self.assertEqual(boot_runner.PUBLIC_API_NETWORK_WRITE_MARKER, b"NET-WRITE-24")
        self.assertEqual(boot_runner.PUBLIC_API_NETWORK_REPLY_BYTES, b"NET-REPLY-24")
        for payload_length in (
                boot_runner.PUBLIC_API_NETWORK_OPEN_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_NETWORK_WRITE_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_NETWORK_READ_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_NETWORK_CLOSE_PAYLOAD_BYTES):
            self.assertLessEqual(boot_runner.PUBLIC_API_FUJIBUS_HEADER_BYTES + payload_length, 512)

    def test_disk_fixture_is_a_complete_bounded_128_byte_sector_pattern(self):
        self.assertEqual(len(boot_runner.PUBLIC_API_DISK_PATTERN), 128)
        self.assertNotEqual(boot_runner.PUBLIC_API_DISK_PATTERN[:64],
                            boot_runner.PUBLIC_API_DISK_PATTERN[64:])
        self.assertEqual(boot_runner.PUBLIC_API_DISK_PATTERN[0], 0xa5)
        for payload_length in (
                boot_runner.PUBLIC_API_DISK_INFO_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_DISK_WRITE_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_DISK_FLUSH_PAYLOAD_BYTES,
                boot_runner.PUBLIC_API_DISK_READ_PAYLOAD_BYTES):
            self.assertLessEqual(boot_runner.PUBLIC_API_FUJIBUS_HEADER_BYTES + payload_length, 512)


if __name__ == "__main__":
    unittest.main()
