from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nio_build.amiga_config import (
    encode_dir_mounts,
    load_profile,
    resolve_profile_shares,
    sync_development_share,
)


class DevelopmentShareTests(unittest.TestCase):
    def test_profile_expands_quoted_local_media_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "local"
            local.mkdir()
            (local / "amiga.env").write_text(
                'AMIGA_WB13_ADF_WORKBENCH="/media/workbench13.adf"\n',
                encoding="utf-8",
            )
            config = root / "workbenches.yaml"
            config.write_text(
                "profiles:\n"
                "  wb1.3:\n"
                "    disk: ${AMIGA_WB13_ADF_WORKBENCH}\n"
                "    kickstart: ${NIO_WORKSPACE}/kick13.rom\n",
                encoding="utf-8",
            )
            profile = load_profile(config, "wb1.3", root, {})
            self.assertEqual(profile["disk"], "/media/workbench13.adf")

    def test_wb13_profile_uses_nio_share_and_rom_key(self) -> None:
        root = Path(__file__).resolve().parents[3]
        profile = load_profile(
            root / "configs" / "amiga" / "workbenches.yaml",
            "wb13-adf",
            root,
            {
                "AMIGA_WB13_ADF_WORKBENCH": "/media/workbench13.adf",
                "AMIGA_WB13_KICKSTART": "/media/kick13.rom",
                "AMIGA_WB13_ROM_KEY": "/media/rom.key",
            },
        )
        self.assertEqual(profile["rom_key"], "/media/rom.key")
        self.assertEqual(profile["shares"][0]["volume"], "NIO")

    def test_unset_or_empty_rom_key_means_no_key(self) -> None:
        # A plain Kickstart ROM needs no key, so AMIGA_WB13_ROM_KEY is often
        # unset; the profile must not turn the bare reference into a path.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "workbenches.yaml"
            config.write_text(
                "profiles:\n"
                "  wb1.3:\n"
                "    disk: /media/workbench13.adf\n"
                "    kickstart: /media/kick13.rom\n"
                "    rom_key: ${AMIGA_WB13_ROM_KEY}\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ):
                os.environ.pop("AMIGA_WB13_ROM_KEY", None)
                for environment in ({}, {"AMIGA_WB13_ROM_KEY": ""}):
                    with self.subTest(environment=environment):
                        profile = load_profile(config, "wb1.3", root, environment)
                        self.assertNotIn("rom_key", profile)
                        self.assertEqual(profile["kickstart"], "/media/kick13.rom")

    def test_profile_without_shares_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "workbenches.yaml"
            config.write_text(
                "profiles:\n"
                "  bare:\n"
                "    disk: ${NIO_WORKSPACE}/boot.adf\n"
                "    kickstart: ${NIO_WORKSPACE}/kick.rom\n",
                encoding="utf-8",
            )
            (root / "boot.adf").write_bytes(b"adf")
            (root / "kick.rom").write_bytes(b"rom")
            profile = load_profile(config, "bare", root, {})
            self.assertEqual(profile["shares"], [])

    def test_named_share_resolves_read_only_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "workbenches.yaml"
            config.write_text(
                "shares:\n"
                "  NIO:\n"
                "    volume: NIO\n"
                "    path: ${NIO_WORKSPACE}/build/amiga-share\n"
                "profiles:\n"
                "  with-share:\n"
                "    disk: ${NIO_WORKSPACE}/boot.adf\n"
                "    kickstart: ${NIO_WORKSPACE}/kick.rom\n"
                "    shares:\n"
                "      - NIO\n",
                encoding="utf-8",
            )
            (root / "boot.adf").write_bytes(b"adf")
            (root / "kick.rom").write_bytes(b"rom")
            profile = load_profile(config, "with-share", root, {})
            self.assertEqual(len(profile["shares"]), 1)
            share = profile["shares"][0]
            self.assertEqual(share["volume"], "NIO")
            self.assertEqual(share["device"], "DH1")
            self.assertFalse(share["writable"])
            self.assertTrue(share["sync"])
            self.assertEqual(share["bootpri"], 0)
            self.assertEqual(share["path"], str(root / "build" / "amiga-share"))
            self.assertEqual(
                encode_dir_mounts(profile["shares"]),
                f"ro,DH1:NIO:{root / 'build' / 'amiga-share'},0",
            )

    def test_unknown_share_name_fails(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            resolve_profile_shares(
                {"shares": {}},
                {"shares": ["MISSING"]},
                Path("/tmp"),
                {},
                profile_name="demo",
            )
        self.assertIn("Unknown development share", str(raised.exception))

    def test_sync_development_share_links_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            driver = root / "repos" / "fujinet-nio-driver" / "build" / "amiga"
            apps = root / "repos" / "nio-core-apps" / "build" / "amiga" / "bin"
            bounce = root / "repos" / "bounce-world-client-nio" / "build"
            driver.mkdir(parents=True)
            apps.mkdir(parents=True)
            bounce.mkdir(parents=True)
            (driver / "fujinet-nio.device").write_bytes(b"nio")
            (driver / "fujinet-disk.device").write_bytes(b"disk")
            (driver / "fujinet-nio-exchange").write_bytes(b"exchange")
            (apps / "fls").write_bytes(b"fls")
            (bounce / "bwcn.amiga").write_bytes(b"bwc")
            share = root / "build" / "amiga-share"
            linked = sync_development_share(root, share)
            self.assertIn("fujinet-nio.device", linked)
            self.assertIn("fujinet-nio-exchange", linked)
            self.assertIn("fls", linked)
            self.assertIn("bwcn.amiga", linked)
            self.assertTrue((share / "fujinet-nio.device").is_symlink())
            self.assertEqual((share / "fls").resolve(), (apps / "fls").resolve())
            self.assertEqual((share / "bwcn.amiga").resolve(), (bounce / "bwcn.amiga").resolve())

    def test_sync_development_share_without_bounce_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            driver = root / "repos" / "fujinet-nio-driver" / "build" / "amiga"
            driver.mkdir(parents=True)
            (driver / "fujinet-nio.device").write_bytes(b"nio")
            share = root / "build" / "amiga-share"
            linked = sync_development_share(root, share)
            self.assertEqual(linked, ["fujinet-nio.device"])
            self.assertFalse((share / "bwcn.amiga").exists())


if __name__ == "__main__":
    unittest.main()
