"""Executable bounds gate for the Atari public-API acceptance XEX."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
import fnaccept_memory_layout as layout


class FnacceptMemoryLayoutTests(unittest.TestCase):
    def test_fnaccept_common_object_exception_is_atari_only(self):
        build = (WORKSPACE / 'repos/nio-core-apps/makefiles/build.mk').read_text()
        self.assertIn('FNACCEPT_COMMON_OBJS := $(COMMON_OBJS)', build)
        scoped = build.index('ifeq ($(TARGET),atari)', build.index('FNACCEPT_COMMON_OBJS'))
        self.assertLess(scoped, build.index('FNACCEPT_COMMON_OBJS :=', scoped + 1))

    def test_linked_image_fits_approved_display_and_stack_bounds(self):
        map_path = WORKSPACE / 'repos/nio-core-apps/build/atari/bin/fnaccept.map'
        report = layout.validate_link_layout(
            map_path,
            WORKSPACE / 'repos/nio-core-apps/build/atari/bin/fnaccept.xex')
        self.assertEqual(report['segments']['STARTUP']['start'], 0x0d00)
        self.assertLessEqual(report['segments']['BSS']['end_exclusive'], layout.MAIN_LIMIT)
        self.assertGreaterEqual(report['heap_gap']['bytes'], 0x0200)
        self.assertEqual(report['c_stack_reserved']['bytes'], 0x800)
        module_list = map_path.read_text().split('Segment list:', 1)[0]
        self.assertNotIn('fnsvc.o:', module_list)
        self.assertNotIn('fnctl.o:', module_list)

    def test_runtime_snapshot_rejects_unproven_or_overlapping_stack(self):
        report = {
            'segments': {'BSS': {'end_exclusive': 0x8f97}},
        }
        snapshot = {
            'magic': 'HMS1', 'version': 1, 'dma_transition': 0,
            'memlo': 0x0700, 'memtop': 0xbc20, 'ramtop': 0xbc,
            'sdlstl': 0x9c00, 'savmsc': 0x9c20, 'sdmctl': 0x22, 'dmactl': 0x22,
        }
        result = layout.validate_runtime_snapshot(snapshot, report)
        self.assertFalse(result['pre_service_display']['overlaps_linked_image'])
        snapshot['dma_transition'] = 0xa5
        with self.assertRaises(RuntimeError):
            layout.validate_runtime_snapshot(snapshot, report)
        snapshot['dma_transition'] = 0
        snapshot['memtop'] = 0x9600
        with self.assertRaises(RuntimeError):
            layout.validate_runtime_snapshot(snapshot, report)


if __name__ == '__main__':
    unittest.main()
