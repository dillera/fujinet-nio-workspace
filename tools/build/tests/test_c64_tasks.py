from pathlib import Path
import tempfile
import unittest
from unittest.mock import DEFAULT, Mock, patch

from nio_build.context import BuildContext
from nio_build.runner import Runner
from nio_build.tasks import Build, build_tasks


def run_task(name: str) -> list:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        env = {name: str(root / name) for name in (
            "FUJINET_NIO_LIB", "NIO_CONFIG", "NIO_CORE_APPS", "FUJINET_NIO",
            "NIO_LOG_DIR", "NIO_IMAGE_DIR", "PDCURSES_DIR", "PDCURSES_MSDOS_LIB")}
        build = Build(BuildContext(root, env))
        build.runner = Mock(spec=Runner)
        build_tasks(build)[name].action(build)
        return build.runner.run.call_args_list


class C64TaskTests(unittest.TestCase):
    def test_boot_disk_builds_library_then_config_then_installs_disk(self):
        calls = run_task("c64-boot-disk")
        self.assertEqual([call.args[0] for call in calls], ["lib-c64", "config-c64", "boot-disk-c64"])
        self.assertIn("TARGET=c64", calls[1].args[1])
        self.assertIn("TARGET=c64", calls[2].args[1])
        self.assertIn("install-boot-disk", calls[2].args[1])

    def test_workflow_adds_the_netiec_firmware(self):
        names = [call.args[0] for call in run_task("c64")]
        self.assertEqual(names, ["lib-c64", "config-c64", "boot-disk-c64", "fujinet-c64-netiec-build"])

    def test_lib_includes_c64(self):
        self.assertIn("lib-c64", [call.args[0] for call in run_task("lib")])

    # The other platforms' steps need more of the build environment, so they are stubbed.
    def test_boot_disks_include_c64(self):
        others = ("boot_disk_msdos", "boot_disk_atari", "boot_disk_bbc",
                  "amiga_default_disk_wb13", "amiga_default_disk_wb31", "amiga_default_disk_wb32")
        with patch.multiple(Build, boot_disk_c64=DEFAULT, **{name: DEFAULT for name in others}) as mocks:
            run_task("boot-disks")
        mocks["boot_disk_c64"].assert_called_once()

    def test_all_runs_the_c64_workflow(self):
        others = ("workflow_linux", "workflow_msdos", "workflow_atari", "workflow_bbc", "workflow_amiga")
        with patch.multiple(Build, c64=DEFAULT, **{name: DEFAULT for name in others}) as mocks:
            run_task("all")
        mocks["c64"].assert_called_once()


if __name__ == "__main__":
    unittest.main()
