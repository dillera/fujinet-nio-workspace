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
bootstrap = load_module("make_resident_bootstrap_include", ROOT / "integration-tests/atari-sio/make_resident_bootstrap_include.py")


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

    def test_owned_fixture_precedes_installer_without_replacing_table(self):
        installer = b"\xff\xff" + segment(0x1D00, b"\x60") + segment(0x02E0, b"\x00\x1d")
        probe = b"\xff\xff" + segment(0x4000, b"\x60") + segment(0x02E0, b"\x00\x40")
        composed = list(compose.segments(compose.compose(installer, probe, own_hatabs=0x27b3)))
        self.assertEqual(composed[0][0], 0x3000)
        self.assertEqual(composed[0][2][5:10], bytes((0xa9, 0xb3, 0x8d, 0x1b, 0x03)))
        self.assertEqual(composed[1], (0x02E2, 0x02E3, b"\x00\x30"))

    def test_repeat_bootstrap_stages_second_install_without_a_resident_segment(self):
        installer = b"\xff\xff" + segment(0x1D00, b"\x60") + segment(0x02E0, b"\x00\x1d")
        probe = b"\xff\xff" + segment(0x4000, b"\x60") + segment(0x02E0, b"\x00\x40")
        bootstrap = b"\xff\xff" + segment(0x4000, b"\x60") + segment(0x02E0, b"\x00\x40")
        composed = list(compose.segments(compose.compose(
            installer, probe, bootstrap=bootstrap, repeat_bootstrap=True)))
        self.assertEqual([item for item in composed if item[0] == 0x1D00], [])
        self.assertEqual(sum(item[0] == 0x5000 for item in composed), 2)
        self.assertEqual(sum(item[0] == 0x02E2 for item in composed), 2)

    def test_map_gate_rejects_missing_or_wrong_resident_range(self):
        good = {"STARTUP": (0x1D00, 0x1D62), "ONCE": (0x1D63, 0x1D6E),
                "CODE": (0x1D6F, 0x27AC), "RODATA": (0x27AD, 0x27BE),
                "DATA": (0x27BF, 0x27EE), "BSS": (0x27EF, 0x2EC5)}
        self.assertEqual(layout.validate_map(good)["resident_end"], 0x2EC6)
        bad = dict(good); bad["STARTUP"] = (0x2400, 0x2462)
        with self.assertRaises(ValueError):
            layout.validate_map(bad)
        bad = dict(good); del bad["BSS"]
        with self.assertRaises(ValueError):
            layout.validate_map(bad)

    def test_bootstrap_bounds_reject_noncontiguous_or_unsafe_staging(self):
        good = {"STARTUP": (0x1D00, 0x1D62), "ONCE": (0x1D63, 0x1D6E),
                "CODE": (0x1D6F, 0x27AC), "RODATA": (0x27AD, 0x27BE),
                "DATA": (0x27BF, 0x27EE), "BSS": (0x27EF, 0x2EC5)}
        result = bootstrap.bounds(good, 0x1D01)
        self.assertEqual(result["stage"], 0x5000)
        self.assertEqual(result["end"], 0x2EC6)
        bad = dict(good); bad["BSS"] = (0x2800, 0x2EC5)
        with self.assertRaises(ValueError):
            bootstrap.bounds(bad, 0x1D01)
        with self.assertRaises(ValueError):
            bootstrap.bounds(good, 0x1CFF)
