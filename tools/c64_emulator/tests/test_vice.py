from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from c64_emulator.vice import KEY_RETURN, ViceConfig, petscii, screen_code_to_text, write_png


class PetsciiTests(unittest.TestCase):
    def test_letters_go_unshifted_and_capitals_shifted(self):
        self.assertEqual(petscii("load"), b"LOAD")
        self.assertEqual(petscii("A"), bytes([0xC1]))
        self.assertEqual(petscii("Z"), bytes([0xDA]))

    def test_newline_is_return(self):
        self.assertEqual(petscii("run\n"), b"RUN" + bytes([KEY_RETURN]))

    def test_punctuation_and_digits_pass_through(self):
        self.assertEqual(petscii('load"*",8,1'), b'LOAD"*",8,1')
        self.assertEqual(petscii("$:;=?[]"), b"$:;=?[]")

    def test_characters_with_no_key_are_refused(self):
        for ch in ("^", "_", "`", "{", "~", "\t", "é"):
            with self.subTest(ch=ch), self.assertRaises(ValueError):
                petscii(ch)


class ScreenCodeTests(unittest.TestCase):
    def test_letters_read_as_small_in_both_sets(self):
        for lower_upper in (False, True):
            with self.subTest(lower_upper=lower_upper):
                self.assertEqual(screen_code_to_text(0x01, lower_upper), "a")
                self.assertEqual(screen_code_to_text(0x1A, lower_upper), "z")

    def test_capitals_only_in_the_lower_upper_set(self):
        self.assertEqual(screen_code_to_text(0x41, True), "A")
        self.assertEqual(screen_code_to_text(0x5A, True), "Z")
        # On the power-on set these codes are graphics characters.
        self.assertEqual(screen_code_to_text(0x41, False), "#")

    def test_symbols_digits_and_space(self):
        expected = {0x00: "@", 0x1B: "[", 0x1C: "\\", 0x1D: "]", 0x1E: "^", 0x1F: "<",
                    0x20: " ", 0x22: '"', 0x2A: "*", 0x30: "0", 0x39: "9", 0x3F: "?", 0x60: " "}
        for code, text in expected.items():
            with self.subTest(code=hex(code)):
                self.assertEqual(screen_code_to_text(code, False), text)
                self.assertEqual(screen_code_to_text(code, True), text)

    def test_reverse_video_reads_as_the_same_character(self):
        for code in (0x00, 0x01, 0x1A, 0x20, 0x30, 0x41, 0x60):
            for lower_upper in (False, True):
                with self.subTest(code=hex(code), lower_upper=lower_upper):
                    self.assertEqual(screen_code_to_text(code | 0x80, lower_upper),
                                     screen_code_to_text(code, lower_upper))

    def test_typed_letters_read_back_as_typed(self):
        # The KERNAL puts a typed letter on the screen as its PETSCII code less 0x40.
        for ch in "abcxyz":
            with self.subTest(ch=ch):
                self.assertEqual(screen_code_to_text(petscii(ch)[0] - 0x40, False), ch)


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    chunks = []
    at = 8
    while at < len(data):
        (length,) = struct.unpack_from(">I", data, at)
        kind = data[at + 4 : at + 8]
        body = data[at + 8 : at + 8 + length]
        (crc,) = struct.unpack_from(">I", data, at + 8 + length)
        if crc != zlib.crc32(kind + body):
            raise AssertionError(f"bad CRC in {kind!r}")
        chunks.append((kind, body))
        at += 12 + length
    return chunks


class WritePngTests(unittest.TestCase):
    def test_writes_an_rgb_png_with_the_rows_given(self):
        rows = [b"\xff\x00\x00\x00\xff\x00", b"\x00\x00\xff\x10\x20\x30"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a" / "b" / "shot.png"  # makes the folders it needs
            write_png(path, 2, 2, rows)
            data = path.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        chunks = png_chunks(data)
        self.assertEqual([kind for kind, _ in chunks], [b"IHDR", b"IDAT", b"IEND"])
        width, height, depth, colour, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunks[0][1])
        self.assertEqual((width, height, depth, colour), (2, 2, 8, 2))  # 8-bit RGB
        self.assertEqual((compression, filtering, interlace), (0, 0, 0))
        # Each row is stored with filter type 0 in front of it.
        self.assertEqual(zlib.decompress(chunks[1][1]), b"\0" + rows[0] + b"\0" + rows[1])


class ViceConfigTests(unittest.TestCase):
    # The layout scripts/build-vice-fn.sh makes: the launcher in the external/vice-fn
    # checkout, each UI built out of tree beside the other.
    def test_launcher_is_in_the_checkout(self):
        config = ViceConfig(root=Path("/ws/external/vice-fn"), build=Path("/ws/build/vice-fn"))
        self.assertEqual(config.launcher, Path("/ws/external/vice-fn/fujinet/run-vice-fujinet.sh"))

    def test_headless_by_default_and_sdl2_for_a_window(self):
        root, build = Path("/ws/external/vice-fn"), Path("/ws/build/vice-fn")
        self.assertEqual(ViceConfig(root=root, build=build).build_dir, build / "headless")
        self.assertEqual(ViceConfig(root=root, build=build, headless=False).build_dir, build / "sdl2")


if __name__ == "__main__":
    unittest.main()
