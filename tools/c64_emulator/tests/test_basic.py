from __future__ import annotations

import unittest

from c64_emulator.basic import BASIC_START, TOKEN_PRINT, basic_hello


class BasicHelloTests(unittest.TestCase):
    def test_bytes_of_a_one_line_program(self):
        self.assertEqual(
            basic_hello("HI"),
            bytes([0x01, 0x08, 0x0B, 0x08, 10, 0, TOKEN_PRINT]) + b'"HI"\0' + b"\0\0",
        )

    def test_the_line_link_points_at_the_end_of_the_program(self):
        for message in ("", "HI", "HELLO FROM TNFS"):
            with self.subTest(message=message):
                prg = basic_hello(message)
                self.assertEqual(prg[0] | prg[1] << 8, BASIC_START)
                link = prg[2] | prg[3] << 8
                at = 2 + (link - BASIC_START)  # where that address is in the file
                self.assertEqual(prg[at:], b"\0\0")

    def test_the_message_must_be_ascii(self):
        with self.assertRaises(UnicodeEncodeError):
            basic_hello("café")


if __name__ == "__main__":
    unittest.main()
