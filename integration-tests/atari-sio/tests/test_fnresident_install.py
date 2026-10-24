import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compose = load_module("compose_resident_xex", ROOT / "integration-tests/atari-sio/compose_resident_xex.py")
layout = load_module("fnresident_memory_layout", ROOT / "integration-tests/atari-sio/fnresident_memory_layout.py")


def segment(start, data):
    end = start + len(data) - 1
    return bytes((start & 255, start >> 8, end & 255, end >> 8)) + data


class ResidentInstallTests(unittest.TestCase):
    def test_composite_runs_installer_as_init_then_probe(self):
        installer = b"\xff\xff" + segment(0x1D00, b"\x60") + segment(0x02E0, b"\x00\x1d")
        probe = b"\xff\xff" + segment(0x4000, b"\x60") + segment(0x02E0, b"\x00\x40")
        composed = list(compose.segments(compose.compose(installer, probe)))
        self.assertEqual(composed[1], (0x02E2, 0x02E3, b"\x00\x1d"))
        self.assertEqual(composed[-1], (0x02E0, 0x02E1, b"\x00\x40"))

    def test_foreign_fixture_precedes_installer_init(self):
        installer = b"\xff\xff" + segment(0x1D00, b"\x60") + segment(0x02E0, b"\x00\x1d")
        probe = b"\xff\xff" + segment(0x4000, b"\x60") + segment(0x02E0, b"\x00\x40")
        composed = list(compose.segments(compose.compose(installer, probe, foreign_hatabs=True)))
        self.assertEqual(composed[0][0], 0x3000)
        self.assertEqual(composed[1], (0x02E2, 0x02E3, b"\x00\x30"))

    def test_map_gate_rejects_missing_or_wrong_resident_range(self):
        good = {"STARTUP": (0x1D00, 0x1D62), "ONCE": (0x1D63, 0x1D6E),
                "CODE": (0x1D6F, 0x27B0), "RODATA": (0x27B1, 0x27C2),
                "DATA": (0x27C3, 0x27F2), "BSS": (0x27F3, 0x2EC9)}
        self.assertEqual(layout.validate_map(good)["resident_end"], 0x2ECA)
        bad = dict(good); bad["STARTUP"] = (0x2400, 0x2462)
        with self.assertRaises(ValueError):
            layout.validate_map(bad)
        bad = dict(good); del bad["BSS"]
        with self.assertRaises(ValueError):
            layout.validate_map(bad)
