from __future__ import annotations

import os
import shutil
import subprocess
import time
import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .context import BuildContext
from .manifest import (
    default_msdos_apps_manifest,
    default_msdos_boot_config_manifest,
    default_qemu_msdos_apps_manifest,
    write_manifest,
)
from .runner import Runner


@dataclass(frozen=True)
class Task:
    name: str
    description: str
    action: Callable[["Build"], None]
    workflow: bool = False
    hidden: bool = False
    consumes_args: bool = False
    help_text: Callable[["Build"], str] | None = None


class Build:
    def __init__(self, ctx: BuildContext):
        self.ctx = ctx
        self.runner = Runner(ctx)

    def p(self, name: str) -> Path:
        return self.ctx.path(name)

    def external_help(self, command: list[str], *, cwd: Path | None = None) -> str:
        """Return help from the actual delegated command without starting it."""
        result = subprocess.run(
            [*map(str, command), "--help"],
            cwd=cwd,
            env=self.ctx.env,
            capture_output=True,
            text=True,
            check=False,
        )
        return (result.stdout or result.stderr).rstrip()

    def amiga_run_help(self, *, build_adf: bool) -> str:
        parser_help = self.amiga_target_parser(build_adf=build_adf).format_help()
        runner_help = self.external_help([self.ctx.root / "scripts" / "run-amiberry-nio"])
        return parser_help + "\nAmiberry runner options:\n\n" + runner_help

    def qemu_run_help(self) -> str:
        return self.external_help([self.p("FUJINET_QEMU_MSDOS") / "run-qemu-nio"])

    def qemu_monitor_help(self) -> str:
        return self.external_help([self.p("FUJINET_QEMU_MSDOS") / "qemu-nio-monitor"])

    def atari_run_help(self) -> str:
        return self.external_help([self.ctx.root / "scripts" / "atari-run"])

    def atari_boot_acceptance_help(self) -> str:
        return self.external_help([
            "python3",
            self.ctx.root / "integration-tests" / "atari-sio" / "run_boot_acceptance.py",
        ])

    def run_make(self, name: str, repo: str, *args: str, env: dict[str, str] | None = None) -> None:
        path = self.p(repo)
        self.runner.require_dir(path)
        self.runner.run(name, ["make", *args], cwd=path, extra_env=env)

    def altirra(self) -> None:
        repo = self.ctx.root / "repos" / "AltirraSDL"
        self.runner.require_dir(repo)
        preset = self.ctx.env.get("ALTIRRA_CMAKE_PRESET", "linux-debug")
        jobs = self.ctx.env.get("ALTIRRA_BUILD_JOBS", str(os.cpu_count() or 1))
        self.runner.run("altirra-configure", ["cmake", "--preset", preset], cwd=repo)
        self.runner.run("altirra-build", ["cmake", "--build", f"build/{preset}", "--target", "AltirraSDL", "-j", jobs], cwd=repo)

    def fujinet_tcp_debug(self) -> None:
        self.runner.require_dir(self.p("FUJINET_NIO"))
        self.runner.run("fujinet-tcp-debug-build", ["./build.sh", "-cp", "fujibus-tcp-debug"], cwd=self.p("FUJINET_NIO"))

    def fujinet_tcp(self) -> None:
        self.fujinet_tcp_debug()
        self.runner.run("fujinet-tcp-debug-test", ["ctest", "--test-dir", "build/fujibus-tcp-debug", "--output-on-failure"], cwd=self.p("FUJINET_NIO"))
        self.runner.run("fujinet-tcp-release-build", ["./build.sh", "-cp", "fujibus-tcp-release"], cwd=self.p("FUJINET_NIO"))

    def fujinet_pty_debug(self) -> None:
        self.runner.require_dir(self.p("FUJINET_NIO"))
        self.runner.run("fujinet-pty-debug-build", ["./build.sh", "-cp", "fujibus-pty-debug"], cwd=self.p("FUJINET_NIO"))

    def fujinet_pty(self) -> None:
        self.fujinet_pty_debug()
        self.runner.run("fujinet-pty-debug-test", ["ctest", "--test-dir", "build/fujibus-pty-debug", "--output-on-failure"], cwd=self.p("FUJINET_NIO"))

    def fujinet_rs232(self) -> None:
        self.runner.require_dir(self.p("FUJINET_NIO"))
        self.runner.run("fujinet-rs232-debug-build", ["./build.sh", "-cp", "fujibus-rs232-debug"], cwd=self.p("FUJINET_NIO"))
        self.runner.run("fujinet-rs232-debug-test", ["ctest", "--test-dir", "build/fujibus-rs232-debug", "--output-on-failure"], cwd=self.p("FUJINET_NIO"))

    def fujinet_atari_netsio(self) -> None:
        self.runner.require_dir(self.p("FUJINET_NIO"))
        self.runner.run("fujinet-atari-fujibus-netsio-build", ["./build.sh", "-cp", "atari-fujibus-netsio-debug"], cwd=self.p("FUJINET_NIO"))

    def rp2350_pio_tests(self) -> None:
        bridge = self.p("FUJINET_NIO") / "bridges" / "rp2350-zorro"
        self.runner.require_dir(bridge)
        self.runner.run("rp2350-host-dependencies", ["python3", "scripts/bootstrap.py", "--mode", "host"], cwd=bridge)
        for preset in ("host", "host-release"):
            self.runner.run(f"rp2350-{preset}-configure", ["cmake", "--preset", preset], cwd=bridge)
            self.runner.run(f"rp2350-{preset}-build", ["cmake", "--build", "--preset", preset], cwd=bridge)
            self.runner.run(f"rp2350-{preset}-test", ["ctest", "--preset", preset], cwd=bridge)

    def rp2350_firmware(self) -> None:
        self.bridge_firmware("rp2350-firmware", "firmware", "firmware", "bridge_capture")

    def rp2040_stimulus(self) -> None:
        self.bridge_firmware("rp2040-stimulus", "stimulus", "stimulus-rp2040", "feasibility_stimulus")

    def rp2040_stimulus_help(self) -> str:
        bridge = self.p("FUJINET_NIO") / "bridges" / "rp2350-zorro"
        return (
            "scripts/build.sh rp2040-stimulus   Build the RP2040 W0 laboratory generator.\n"
            "Build only: no USB loading, flashing or signal generation.\n"
            "Uses pinned Pico SDK/apio and an independent stimulus-rp2040 cache.\n"
            "Compiler: PICO_TOOLCHAIN_PATH, arm-none-eabi-gcc on PATH, cached compiler,\n"
            "or workspace build/toolchains/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi/bin.\n"
            "PICO_SDK_PATH overrides must match the bridge's clean pinned SDK.\n"
            "Run scripts/build.sh rp2350-pio-tests for native waveform/control tests.\n"
            f"Artifacts: {bridge / 'build/stimulus-rp2040'}/feasibility_stimulus.{{elf,uf2}}\n"
            f"Load/run/capture instructions: {bridge / 'docs/rp2040-generator.md'}"
        )

    def bridge_firmware(self, task: str, mode: str, preset: str, artifact: str) -> None:
        bridge = self.p("FUJINET_NIO") / "bridges" / "rp2350-zorro"
        self.runner.require_dir(bridge)
        env = {}
        local_compiler = self.ctx.root / "build" / "toolchains" / "arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi" / "bin"

        def executable(path: Path) -> bool:
            return path.is_file() and os.access(path, os.X_OK)

        configured_toolchain = self.ctx.env.get("PICO_TOOLCHAIN_PATH")
        if configured_toolchain:
            directory = Path(configured_toolchain)
            if not any(executable(candidate) for candidate in (
                directory / "arm-none-eabi-gcc", directory / "bin" / "arm-none-eabi-gcc",
            )):
                raise SystemExit(f"No executable arm-none-eabi-gcc in PICO_TOOLCHAIN_PATH: {directory}")
        elif not shutil.which("arm-none-eabi-gcc", path=self.ctx.env.get("PATH", "")):
            # CMake retains toolchain selection across invocations without exports.
            cache = bridge / "build" / preset / "CMakeCache.txt"
            cached_compiler = None
            if cache.is_file():
                for line in cache.read_text().splitlines():
                    if line.startswith("CMAKE_C_COMPILER:") and "=" in line:
                        cached_compiler = Path(line.split("=", 1)[1])
                        break
            if cached_compiler is not None and executable(cached_compiler):
                pass
            elif executable(local_compiler / "arm-none-eabi-gcc"):
                env["PICO_TOOLCHAIN_PATH"] = str(local_compiler)
            else:
                raise SystemExit(
                    "Bridge firmware needs arm-none-eabi-gcc on PATH or PICO_TOOLCHAIN_PATH "
                    "set to its toolchain directory (for example in local/config.env). "
                    f"Run scripts/build.sh --explain {task} for details."
                )
        self.runner.run(f"{task}-dependencies", ["python3", "scripts/bootstrap.py", "--mode", mode], cwd=bridge, extra_env=env)
        self.runner.run(f"{task}-configure", ["cmake", "--preset", preset], cwd=bridge, extra_env=env)
        self.runner.run(f"{task}-build", ["cmake", "--build", "--preset", preset], cwd=bridge, extra_env=env)
        print(f"Artifacts: {bridge / 'build' / preset / (artifact + '.elf')}")
        print(f"           {bridge / 'build' / preset / (artifact + '.uf2')}")

    def workflow_rp2350(self) -> None:
        self.rp2350_pio_tests()
        self.rp2350_firmware()

    def rp2350_help(self) -> str:
        bridge = self.p("FUJINET_NIO") / "bridges" / "rp2350-zorro"
        return (
            "scripts/build.sh rp2350             Run PIO tests, then build RP2350B firmware.\n"
            "scripts/build.sh rp2350-pio-tests   Build/run native epio Debug and Release tests; no SDK/ARM compiler.\n"
            "scripts/build.sh rp2350-firmware    Build waveshare_core2350b / rp2350-arm-s ELF and UF2.\n\n"
            "Prerequisites: Git, Python 3, CMake >=3.21, Ninja, native C compiler; firmware also needs native C++.\n"
            "Dependencies are bootstrapped from pinned sources (first use needs network access).\n"
            "Firmware uses PICO_SDK_PATH when set, otherwise the bridge's local pinned SDK.\n"
            "An SDK override must match the exact pinned revision, be clean and include required submodules.\n"
            "Compiler: explicit PICO_TOOLCHAIN_PATH or arm-none-eabi-gcc on PATH; existing CMake cache\n"
            "choices are retained. Without those, use the workspace-local\n"
            "build/toolchains/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi/bin installation.\n"
            "Overrides in local/config.env must be exported, for example:\n"
            "  export PICO_TOOLCHAIN_PATH=/path/to/arm-toolchain/bin\n"
            "  export PICO_SDK_PATH=/path/to/pinned-pico-sdk\n"
            "CMake retains prior SDK/compiler choices; clear\n"
            "the bridge's build/firmware directory when changing them. No flashing is performed.\n"
            f"Artifacts: {bridge / 'build' / 'firmware'}/bridge_capture.{{elf,uf2}}\n"
            f"Compiler installation instructions: {bridge / 'README.md'}"
        )

    def lib_linux(self) -> None:
        self.run_make("lib-linux", "FUJINET_NIO_LIB", "linux")

    def lib_msdos(self) -> None:
        self.run_make("lib-msdos", "FUJINET_NIO_LIB", "msdos")

    def lib_atari(self) -> None:
        self.run_make("lib-atari", "FUJINET_NIO_LIB", "atari")

    def lib_bbc(self) -> None:
        self.run_make("lib-bbc", "FUJINET_NIO_LIB", "bbc")

    def lib_amiga(self) -> None:
        self.run_make("lib-amiga", "FUJINET_NIO_LIB", "amiga")

    def amiga_driver_sdk(self) -> None:
        driver_amiga = self.p("FUJINET_NIO_DRIVER") / "amiga"
        self.runner.require_dir(driver_amiga)
        self.runner.run("amiga-driver-sdk", ["make", "all", "sdk"], cwd=driver_amiga)

    def _ensure_amiga_nio_broker_artifacts(self) -> None:
        """Ensure native broker, loader, and disk artifacts via make native."""
        driver_amiga = self.p("FUJINET_NIO_DRIVER") / "amiga"
        self.runner.require_dir(driver_amiga)
        self.runner.run("amiga-nio-broker-native", ["make", "native"], cwd=driver_amiga)

    def lib_tests(self) -> None:
        self.run_make("lib-tests", "FUJINET_NIO_LIB", "test")

    def cc65_tools(self) -> None:
        self.runner.require_dir(self.p("CC65_HOME"))
        self.runner.run("cc65-tools", ["make", "-C", "src"], cwd=self.p("CC65_HOME"))

    def cc65_bbc(self) -> None:
        self.runner.require_dir(self.p("CC65_HOME"))
        self.runner.run("cc65-bbc-libs", ["make", "-C", "libsrc", "bbc", "bbc-clib"], cwd=self.p("CC65_HOME"))

    def cc65(self) -> None:
        self.cc65_tools()
        self.cc65_bbc()

    def cc65_clib(self) -> None:
        self.runner.require_dir(self.p("CC65_CLIB"))
        self.runner.require_dir(self.p("CC65_SRC"))
        env = {
            "CC65_ROOT": self.ctx.env["CC65_ROOT"],
            "CC65_SRC": self.ctx.env["CC65_SRC"],
            "CC65_HOME": self.ctx.env["CC65_HOME"],
            "CLIB_ROOT": self.ctx.env["CC65_CLIB"],
            "BEEBIUM_HOME": self.ctx.env.get("BEEBIUM_HOME", str(Path.home() / "dev/bbc/beebium")),
            "PATH": f"{self.p('CC65_HOME') / 'bin'}:{self.ctx.env['PATH']}",
        }
        self.runner.run("cc65-clib", ["make", "-C", "build-rom", "all"], cwd=self.p("CC65_CLIB"), extra_env=env)

    def cc65_clib_tests(self, full: bool) -> None:
        self.runner.require_dir(self.p("CC65_CLIB"))
        self.runner.require_dir(self.p("CC65_SRC"))
        env = {
            "CC65_ROOT": self.ctx.env["CC65_ROOT"],
            "CC65_SRC": self.ctx.env["CC65_SRC"],
            "CC65_HOME": self.ctx.env["CC65_HOME"],
            "CLIB_ROOT": self.ctx.env["CC65_CLIB"],
            "BEEBIUM_HOME": self.ctx.env.get("BEEBIUM_HOME", str(Path.home() / "dev/bbc/beebium")),
            "PATH": f"{self.p('CC65_HOME') / 'bin'}:{self.ctx.env['PATH']}",
        }
        args = ["bash", "scripts/run_tests.sh"]
        if not full:
            args.append("--no-beebium")
        self.runner.run("cc65-clib-full-tests" if full else "cc65-clib-tests", args, cwd=self.p("CC65_CLIB"), extra_env=env)

    def pdcurses_msdos(self) -> None:
        self.runner.run("pdcurses-msdos", [self.ctx.root / "scripts" / "build-pdcurses-msdos.sh"])

    def msdos_driver(self) -> None:
        self.run_make("msdos-driver-clean", "FUJINET_NIO_DRIVER", "clean")
        self.run_make("msdos-driver-build", "FUJINET_NIO_DRIVER")

    def msdos_tests(self) -> None:
        self.run_make("msdos-tests", "FUJINET_NIO_DRIVER", "tests")

    def apps_msdos(self) -> None:
        self.pdcurses_msdos()
        self.run_make("apps-msdos", "NIO_APPS", "TARGET=msdos", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", f"PDCURSES_DIR={self.p('PDCURSES_DIR')}", f"PDCURSES_MSDOS_LIB={self.p('PDCURSES_MSDOS_LIB')}")

    def apps_atari(self) -> None:
        self.lib_atari()
        self.run_make("apps-atari", "NIO_APPS", "TARGET=atari", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}")

    def apps_amiga(self) -> None:
        raise SystemExit(
            "Unprofiled Amiga application builds are disabled. "
            "Run: scripts/build.sh amiga-artifacts-wb13|amiga-artifacts-wb31|amiga-artifacts-wb32"
        )

    def amiga_test_app(self) -> tuple[str, Path]:
        app_name = self.ctx.env.get("AMIGA_TEST_APP", "wifitest")
        project = self.ctx.env.get("AMIGA_TEST_PROJECT", "apps").lower()
        profile = self.ctx.env.get("AMIGA_ARTIFACT_PROFILE", "")
        if profile not in {"wb13", "wb31", "wb32"}:
            raise SystemExit(
                "AMIGA_ARTIFACT_PROFILE must be wb13, wb31, or wb32; "
                "unprofiled Amiga test applications are disabled"
            )
        self.amiga_artifacts(profile)
        if project == "core":
            app = self.p("NIO_CORE_APPS") / "build" / "amiga" / profile / "bin" / app_name
        elif project == "apps":
            app = self.p("NIO_APPS") / "build" / "amiga" / profile / "bin" / app_name
        else:
            raise SystemExit("AMIGA_TEST_PROJECT must be 'apps' or 'core'")
        if not app.is_file():
            raise SystemExit(f"Amiga test application not found: {app}")
        return app_name, app

    @staticmethod
    def amiga_test_adf_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="amiga-test-adf",
            description="Build an Amiga test ADF containing one nio app.",
        )
        parser.add_argument(
            "--label", metavar="NAME",
            help="volume label to write (default: preserve Workbench label, or use app name for --blank)",
        )
        parser.add_argument(
            "--blank", action="store_true",
            help="create a blank formatted ADF with the app in C: and no Workbench files",
        )
        parser.epilog = (
            "The normal image is a bootable Workbench derivative. A --blank image is\n"
            "a formatted, non-bootable ADF intended for fmount/TNFS media tests.\n"
            "The application is selected with AMIGA_TEST_APP (default: wifitest)."
        )
        return parser

    @classmethod
    def amiga_test_adf_help(cls, _build: "Build") -> str:
        return cls.amiga_test_adf_parser().format_help()

    def amiga_test_adf(self, args: list[str] | None = None) -> None:
        parsed = self.amiga_test_adf_parser().parse_args(args or [])
        app_name, app = self.amiga_test_app()
        base_adf = Path(self.ctx.env.get("AMIBERRY_WORKBENCH_ADF", ""))
        if not parsed.blank and not base_adf.is_file():
            raise SystemExit(
                f"Amiga Workbench ADF not found: {base_adf}\n"
                "Set AMIBERRY_WORKBENCH_ADF to a licensed Workbench 3.2 ADF."
            )
        output = self.ctx.image_dir / f"amiga-{app_name}.adf"
        command = [
            self.ctx.root / "scripts" / "build-amiga-test-adf",
            "--app", app,
            "--app-name", app_name,
            "--output", output,
        ]
        if not parsed.blank:
            command.extend(["--base-adf", base_adf])
        if parsed.label:
            command.extend(["--label", parsed.label])
        if parsed.blank:
            command.append("--blank")
        self.runner.run("amiga-test-adf", command)
        self.ctx.env["AMIBERRY_ADF"] = str(output)

    def amiga_test_disk(
        self,
        *,
        all_apps: bool = False,
        with_driver: bool = False,
        install_archives: list[Path] | None = None,
        output: Path | None = None,
        volume_label: str | None = None,
    ) -> None:
        app_name, app = self.amiga_test_app()
        self.core_apps_amiga()
        core_app_dir = self.p("NIO_CORE_APPS") / "build" / "amiga" / "bin"
        output = output or (self.ctx.image_dir / f"amiga-{app_name}.hdf")

        env_id = self.ctx.env.get("AMIGA_ENV_ID", "")
        machine_id = self.ctx.env.get("AMIGA_MACHINE_ID", "")
        base_hdf = self.ctx.env.get("AMIGA_ENV_BASE_HDF", "")
        manifest = None

        if env_id:
            # Resolve base HDF / kickstart / FFS from the built environment manifest.
            from .amiga_config import (
                _load_env_manifest,
                _load_machine_profile,
                resolve_fast_file_system,
            )
            manifest = _load_env_manifest(self.ctx.root, env_id, machine_id or None)
            if not base_hdf:
                base_hdf = manifest["base_hdf"]
            self.ctx.env["AMIBERRY_KICKSTART"] = manifest["kickstart"]
            if manifest.get("rom_key"):
                self.ctx.env["AMIBERRY_ROM_KEY"] = manifest["rom_key"]
            if machine_id:
                machine = _load_machine_profile(self.ctx.root, machine_id)
                settings = machine.get("settings", {})
                self.ctx.env["AMIBERRY_EXTRA_SETTINGS"] = ";".join(
                    f"{k}={v}" for k, v in settings.items()
                )
                if machine.get("uae_config"):
                    self.ctx.env["AMIBERRY_UAE_CONFIG"] = machine["uae_config"]

        if not self.ctx.env.get("AMIBERRY_FAST_FILE_SYSTEM"):
            from .amiga_config import resolve_fast_file_system
            lookup = manifest or ({"base_hdf": base_hdf} if base_hdf else {})
            fast_file_system = resolve_fast_file_system(
                lookup, self.ctx.root, self.ctx.env
            )
            if fast_file_system:
                self.ctx.env["AMIBERRY_FAST_FILE_SYSTEM"] = fast_file_system

        if not base_hdf or not Path(base_hdf).is_file():
            raise SystemExit(
                "No AmigaOS base HDF available for amiga-e2e.\n"
                "Set AMIGA_ENV_ID (and optionally AMIGA_MACHINE_ID) to a built environment,\n"
                "or set AMIGA_ENV_BASE_HDF directly.\n"
                "Build with: scripts/amiga-env build <env_id> [--machine <machine_id>]"
            )

        self._ensure_amiga_nio_broker_artifacts()

        disk_args = [
            self.ctx.root / "scripts" / "build-amiga-test-disk",
            "--base-hdf", base_hdf,
            "--app", app,
            "--app-name", app_name,
            "--extra-app-dir", core_app_dir,
            "--command", self.ctx.env.get("AMIGA_TEST_COMMAND", app_name),
            "--output", output,
        ]
        volume_label = volume_label or self.ctx.env.get("AMIGA_TEST_VOLUME_LABEL")
        if volume_label:
            disk_args.extend(["--volume-label", volume_label])
        if all_apps:
            disk_args.extend([
                "--extra-app-dir", self.p("NIO_APPS") / "build" / "amiga" / "bin",
            ])
        driver_root = self.p("FUJINET_NIO_DRIVER")
        disk_args.extend([
            "--nio-device", driver_root / "build/amiga/fujinet-nio.device",
            "--resident-loader", driver_root / "build/amiga/fujinet-load-resident",
            "--resident-unloader", driver_root / "build/amiga/fujinet-unload-resident",
            "--load-nio",
        ])
        if with_driver:
            disk_args.extend([
                "--disk-device", driver_root / "build/amiga/fujinet-disk.device",
                "--disk-mount-tool", driver_root / "build/amiga/fujinet-mount",
                "--load-driver",
            ])
        for archive in install_archives or []:
            disk_args.extend(["--install-archive", archive])
        startup_script = self.ctx.env.get("AMIGA_TEST_STARTUP_SCRIPT", "")
        if startup_script:
            startup_path = Path(startup_script).expanduser()
            if not startup_path.is_absolute():
                startup_path = self.ctx.root / startup_path
            disk_args.extend(["--startup-script", startup_path])
        if self.ctx.env.get("AMIGA_TEST_INTERACTIVE", "0") == "1":
            disk_args.append("--interactive")
        self.runner.run(
            "amiga-test-disk",
            disk_args,
        )
        self.ctx.env["AMIBERRY_DISK"] = str(output)
        self.ctx.env["AMIBERRY_DISK_KIND"] = "harddrive"

    @staticmethod
    def amiga_target_parser(*, build_adf: bool) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="amiga-e2e" if build_adf else "amiga-run",
            description="Build/select an Amiga test application and run it in Amiberry.",
            add_help=True,
        )
        parser.add_argument(
            "--app",
            metavar="NAME",
            help="nio-apps or nio-core-apps application to install/run "
            "(default: AMIGA_TEST_APP, normally wifitest)",
        )
        parser.add_argument(
            "--project",
            choices=("apps", "core"),
            help="application project containing NAME (default: AMIGA_TEST_PROJECT)",
        )
        parser.add_argument(
            "--command",
            metavar="COMMAND",
            help="Amiga startup command (default: selected application name)",
        )
        parser.add_argument(
            "--interactive",
            action="store_true",
            help="keep the Workbench shell instead of running the app at boot",
        )
        if build_adf:
            parser.add_argument(
                "--amiga-env",
                metavar="ENV_ID",
                help="AmigaOS environment id (e.g. wb31, wb32); reads base HDF from "
                     "build/amiga-envs/<id>/manifest.json (or AMIGA_ENV_ID env var)",
            )
            parser.add_argument(
                "--amiga-machine",
                metavar="MACHINE_ID",
                help="machine profile id (e.g. a1200-030); selects machine-keyed "
                     "environment sub-directory (or AMIGA_MACHINE_ID env var)",
            )
        parser.epilog = (
            "Amiberry options go after '--', for example:\n"
            "  scripts/build.sh amiga-e2e --amiga-env wb32 --amiga-machine a1200-030 --app wifitest -- --external-nio\n"
            "Environment equivalents: AMIGA_TEST_APP, AMIGA_TEST_PROJECT, "
            "AMIGA_TEST_COMMAND, AMIGA_TEST_INTERACTIVE, AMIGA_ENV_ID, AMIGA_MACHINE_ID"
        )
        return parser

    def _parse_amiga_target_args(self, args: list[str], *, build_adf: bool) -> list[str]:
        if "--" in args:
            separator = args.index("--")
            target_args, runner_args = args[:separator], args[separator + 1:]
        else:
            target_args, runner_args = args, []
        parsed = self.amiga_target_parser(build_adf=build_adf).parse_args(target_args)
        if parsed.app:
            self.ctx.env["AMIGA_TEST_APP"] = parsed.app
        if parsed.project:
            self.ctx.env["AMIGA_TEST_PROJECT"] = parsed.project
        if parsed.command:
            self.ctx.env["AMIGA_TEST_COMMAND"] = parsed.command
        if parsed.interactive:
            self.ctx.env["AMIGA_TEST_INTERACTIVE"] = "1"
        if build_adf:
            if getattr(parsed, "amiga_env", None):
                self.ctx.env["AMIGA_ENV_ID"] = parsed.amiga_env
            if getattr(parsed, "amiga_machine", None):
                self.ctx.env["AMIGA_MACHINE_ID"] = parsed.amiga_machine
        return runner_args

    def amiga_run(self, args: list[str], *, build_adf: bool) -> None:
        args = self._parse_amiga_target_args(args, build_adf=build_adf)
        if build_adf:
            self.amiga_test_disk()
        env = self.ctx.env.copy()
        env["AMIBERRY_DISK"] = env.get("AMIBERRY_DISK", env.get("AMIGA_TEST_DISK", ""))
        self.runner.run(
            "amiga-run",
            [self.ctx.root / "scripts" / "run-amiberry-nio", *args],
            extra_env=env,
        )

    @staticmethod
    def amiga_workbench_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="amiga-workbench",
            description="Run a named Amiga Workbench profile in Amiberry.",
        )
        parser.add_argument("--profile", metavar="NAME", help="profile name")
        parser.add_argument(
            "--config", "--profile-file", dest="profile_file", metavar="PATH",
            help="alternate workbenches YAML file",
        )
        parser.epilog = (
            "Profiles are defined in configs/amiga/workbenches.yaml.\n"
            "Each profile declares an environment (e.g. wb32) and machine (e.g. a1200-030),\n"
            "plus a harddrive path pointing to your persistent VHD/HDF.\n"
            "Amiberry options go after '--', for example: -- --external-nio"
        )
        return parser

    @classmethod
    def amiga_workbench_help(cls, _build: "Build") -> str:
        return cls.amiga_workbench_parser().format_help()

    def amiga_workbench(self, args: list[str]) -> None:
        """Boot a named Amiberry Workbench profile from an existing disk image."""
        self.ctx.env["AMIGA_TEST_INTERACTIVE"] = "1"
        from .amiga_config import load_profile

        profile_name = self.ctx.env.get("AMIGA_WORKBENCH_CONFIG", "")
        config_file = Path(self.ctx.env["AMIGA_WORKBENCH_CONFIG_FILE"])
        separator = args.index("--") if "--" in args else len(args)
        parsed = self.amiga_workbench_parser().parse_args(args[:separator])
        runner_args = args[separator + 1:] if separator < len(args) else []
        if parsed.profile:
            profile_name = parsed.profile
        if parsed.profile_file:
            config_file = Path(parsed.profile_file).expanduser()
            if not config_file.is_absolute():
                config_file = self.ctx.root / config_file

        profile = load_profile(
            config_file,
            profile_name,
            self.ctx.root,
            self.ctx.env,
        )
        self.ctx.env["AMIGA_WORKBENCH_CONFIG"] = profile["name"]
        artifact_profile = profile.get("artifact_profile")
        if artifact_profile:
            if not isinstance(artifact_profile, str):
                raise SystemExit(
                    f"Amiga Workbench profile '{profile['name']}' has an invalid artifact_profile"
                )
            self.runner.run(
                "amiga-artifacts",
                [self.ctx.root / "scripts" / "amiga-artifacts", artifact_profile],
            )
        for key, env_var in (
            ("kickstart", "AMIBERRY_KICKSTART"),
            ("rom_key", "AMIBERRY_ROM_KEY"),
            ("fast_file_system", "AMIBERRY_FAST_FILE_SYSTEM"),
            ("uae_config", "AMIBERRY_UAE_CONFIG"),
        ):
            if profile.get(key):
                self.ctx.env[env_var] = profile[key]
        settings = profile.get("settings", {})
        self.ctx.env["AMIBERRY_EXTRA_SETTINGS"] = ";".join(
            f"{k}={v}" for k, v in settings.items()
        )

        from .amiga_config import encode_dir_mounts, sync_development_share

        shares = profile.get("shares") or []
        for share in shares:
            share_path = Path(share["path"])
            if share.get("sync", True):
                linked = sync_development_share(self.ctx.root, share_path)
                print(
                    f"Development share {share['volume']}: "
                    f"synced {len(linked)} artifact(s) into {share_path}"
                )
            elif not share_path.is_dir():
                share_path.mkdir(parents=True, exist_ok=True)
        if shares:
            self.ctx.env["AMIBERRY_DIR_MOUNTS"] = encode_dir_mounts(shares)
        else:
            self.ctx.env.pop("AMIBERRY_DIR_MOUNTS", None)

        harddrive = profile.get("harddrive")
        disk = Path(harddrive or profile.get("disk", ""))
        if not disk.is_file():
            raise SystemExit(
                f"Amiga Workbench disk not found for profile '{profile['name']}': {disk}\n"
                "Set harddrive in the profile to an existing VHD/HDF path."
            )
        self.ctx.env["AMIBERRY_DISK"] = str(disk)
        self.ctx.env["AMIBERRY_DISK_KIND"] = (
            "harddrive" if harddrive or disk.suffix.lower() in {".hdf", ".vhd"} else "floppy"
        )
        # Preserve the '--' separator so amiga_run forwards Amiberry options
        # instead of treating them as amiga-run build-target flags.
        forwarded = ["--", *runner_args] if runner_args else []
        self.amiga_run(forwarded, build_adf=False)

    def amiga_tests(self, args: list[str]) -> None:
        """Build all Amiga artefacts then run the integration-test suite.

        Each case builds its explicit Workbench artifact profile, plus the
        POSIX NIO binary.  The suite never consumes an unprofiled Amiga app.
        Additional arguments (including --amiga-env / --amiga-machine) are
        forwarded verbatim to scripts/amiga-tests → pytest.
        """
        if args[:1] == ["--"]:
            args = args[1:]
        self.fujinet_tcp_debug()
        self.runner.run(
            "amiga-e2e-tests",
            [self.ctx.root / "scripts" / "amiga-tests", *args],
        )

    def apps_bbc(self) -> None:
        self.lib_bbc()
        self.run_make("apps-bbc", "NIO_APPS", "TARGET=bbc", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}")

    def apps_all(self) -> None:
        self.pdcurses_msdos()
        self.run_make("apps-all", "NIO_APPS", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", f"PDCURSES_DIR={self.p('PDCURSES_DIR')}", f"PDCURSES_MSDOS_LIB={self.p('PDCURSES_MSDOS_LIB')}")

    def core_apps_msdos(self) -> None:
        self.pdcurses_msdos()
        self.run_make("core-apps-msdos", "NIO_CORE_APPS", "TARGET=msdos", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}")

    def core_apps_atari(self) -> None:
        self.lib_atari()
        self.run_make("core-apps-atari", "NIO_CORE_APPS", "TARGET=atari", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}")

    def core_apps_amiga(self) -> None:
        raise SystemExit(
            "Unprofiled Amiga core-app builds are disabled. "
            "Run: scripts/build.sh amiga-artifacts-wb13|amiga-artifacts-wb31|amiga-artifacts-wb32"
        )

    def core_apps_all(self) -> None:
        self.pdcurses_msdos()
        self.run_make("core-apps-all", "NIO_CORE_APPS", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}")

    def config_msdos(self) -> None:
        self.pdcurses_msdos()
        self.run_make("config-msdos", "NIO_CONFIG", "TARGET=msdos", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", f"PDCURSES_DIR={self.p('PDCURSES_DIR')}", f"PDCURSES_MSDOS_LIB={self.p('PDCURSES_MSDOS_LIB')}")

    def config_atari(self) -> None:
        self.lib_atari()
        self.run_make("config-atari", "NIO_CONFIG", "TARGET=atari", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}")

    def config_bbc(self) -> None:
        self.lib_bbc()
        self.run_make("config-bbc", "NIO_CONFIG", "TARGET=bbc", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}")

    def config_all(self) -> None:
        self.pdcurses_msdos()
        self.run_make("config-all", "NIO_CONFIG", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", f"PDCURSES_DIR={self.p('PDCURSES_DIR')}", f"PDCURSES_MSDOS_LIB={self.p('PDCURSES_MSDOS_LIB')}")

    def boot_disk_msdos(self) -> None:
        self.pdcurses_msdos()
        self.run_make("boot-disk-msdos", "NIO_CORE_APPS", "TARGET=msdos", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", f"FUJINET_NIO={self.p('FUJINET_NIO')}", "install-boot-disk")

    def boot_disk_atari(self) -> None:
        self.lib_atari()
        self.run_make("boot-disk-atari", "NIO_CORE_APPS", "TARGET=atari", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", f"FUJINET_NIO={self.p('FUJINET_NIO')}", "install-boot-disk")

    def amiga_artifacts(self, profile: str) -> None:
        if profile not in {"wb13", "wb31", "wb32"}:
            raise SystemExit(f"Unknown Amiga artifact profile: {profile}")
        self.runner.run("amiga-artifacts-" + profile,
                        [self.ctx.root / "scripts" / "amiga-artifacts", profile])

    def amiga_artifacts_wb13(self) -> None:
        self.amiga_artifacts("wb13")

    def amiga_artifacts_wb31(self) -> None:
        self.amiga_artifacts("wb31")

    def amiga_artifacts_wb32(self) -> None:
        self.amiga_artifacts("wb32")

    def amiga_default_disk(self, profile: str) -> None:
        """Build and install the profile-specific FujiNet default ADF.

        This is a data/configuration disk that FujiNet exposes on unit zero
        when no recovered user mount occupies it; it is not an Amiga system
        boot disk.
        """
        names = {
            "wb13": "FujiNet-Default-WB13.adf",
            "wb31": "FujiNet-Default-WB31.adf",
            "wb32": "FujiNet-Default-WB32.adf",
        }
        if profile not in names:
            raise SystemExit(f"Unknown Amiga default-disk profile: {profile}")
        manifest = self.ctx.root / "configs" / "amiga" / f"default-disk-adf-{profile}.yaml"
        output = self.ctx.build_dir / names[profile]

        self.amiga_artifacts(profile)
        self.runner.run("amiga-default-adf-" + profile,
                        [self.ctx.root / "scripts" / "amiga", "adf", "release",
                         "--manifest", manifest])
        for base in (self.p("FUJINET_NIO") / "distfiles" / "boot",
                     self.p("FUJINET_NIO") / "distfiles" / "esp32-data" / "boot"):
            target = base / "amiga" / profile
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output, target / names[profile])
            print(f"Installed {target / names[profile]}")

    def amiga_default_disk_wb13(self) -> None:
        self.amiga_default_disk("wb13")

    def amiga_default_disk_wb31(self) -> None:
        self.amiga_default_disk("wb31")

    def amiga_default_disk_wb32(self) -> None:
        self.amiga_default_disk("wb32")

    def boot_disks(self) -> None:
        self.boot_disk_msdos()
        self.boot_disk_atari()
        self.boot_disk_bbc()
        self.amiga_default_disk_wb13()
        self.amiga_default_disk_wb31()
        self.amiga_default_disk_wb32()

    def confnio_stage_target(self, machine: str, boot: bool = False) -> str:
        if machine == "BBC":
            return "config-nio-bbc-boot-stage" if boot else "config-nio-bbc-stage"
        if machine == "MASTER":
            return "config-nio-master-boot-stage" if boot else "config-nio-master-stage"
        raise SystemExit(f"Invalid config-nio machine: {machine}")

    def bbc_keycode_binary(self) -> None:
        self.runner.require_dir(self.p("NIO_CONFIG"))
        self.runner.run(
            "bbc-keycode-build",
            ["make", "-f", "makefiles/build.mk", "TARGET=bbc", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", "keycode"],
            cwd=self.p("NIO_CONFIG"),
        )

    def stage_confnio_bbc_for_machine(
        self, machine: str, label: str, stage: Path, boot: bool = False
    ) -> None:
        target = self.confnio_stage_target(machine, boot=boot)
        nio_stage = self.p("NIO_CONFIG") / "build" / "bbc" / "disk" / "config-nio"
        self.runner.run(
            f"confnio-{label}-stage",
            ["make", "-f", "makefiles/build.mk", "TARGET=bbc", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", target],
            cwd=self.p("NIO_CONFIG"),
        )
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        for item in nio_stage.iterdir():
            dest = stage / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    def confnio_disk_for_machine(self, machine: str, label: str) -> None:
        stage = self.ctx.build_dir / f"confnio-{label}-ssd"
        out = self.ctx.image_dir / f"confnio-{label}.ssd"
        self.stage_confnio_bbc_for_machine(machine, label, stage)
        self.runner.run("confnio-" + label + "-ssd", ["python3", self.p("FUJINET_NIO_LIB") / "scripts" / "create_ssd.py", "-i", stage, "-o", out, "-t", "CONFNIO"])
        print(f"Built config-nio {label} SSD: {out}")

    def boot_disk_for_machine(self, machine: str, label: str, ssd_name: str) -> None:
        extra_stage = self.ctx.build_dir / f"{label}-fn-boot-extra"
        if extra_stage.exists():
            shutil.rmtree(extra_stage)
        extra_stage.mkdir(parents=True)
        self.stage_confnio_bbc_for_machine(machine, label, extra_stage, boot=True)
        self.runner.run(
            f"{label}-fn-boot",
            ["./scripts/build_fn_boot.sh"],
            cwd=self.p("FN_ROM_HOME"),
            extra_env={"BUILD_MACHINE": machine, "FN_BOOT_SSD": str(self.p("FN_ROM_HOME") / "build" / ssd_name), "FN_BOOT_EXTRA_STAGE": str(extra_stage)},
        )
        src = self.p("FN_ROM_HOME") / "build" / ssd_name
        for out_dir in [self.p("FUJINET_NIO") / "distfiles" / "boot" / "bbc", self.p("FUJINET_NIO") / "distfiles" / "esp32-data" / "boot" / "bbc"]:
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out_dir / ssd_name)
            print(f"Installed {out_dir / ssd_name}")

    def boot_disk_bbc(self) -> None:
        self.boot_disk_for_machine("BBC", "bbc", "FN-BOOT.ssd")

    def boot_disk_master(self) -> None:
        self.boot_disk_for_machine("MASTER", "master", "FN-BOOT-M.ssd")

    def write_bbc_pty_config(self, label: str) -> None:
        run_dir = self.p("FUJINET_NIO") / "build" / "fujibus-pty-debug"
        data_dir = run_dir / "fujinet-data"
        data_dir.mkdir(parents=True, exist_ok=True)
        if label == "master":
            pty_path = self.ctx.env.get("MASTER_PTY_PATH", self.ctx.env.get("BBC_PTY_PATH", "/tmp/fujinet-pty"))
            boot_uri = self.ctx.env.get("MASTER_BOOT_URI", self.ctx.env.get("BBC_BOOT_URI", "persist:/boot/bbc/FN-BOOT-M.ssd"))
        else:
            pty_path = self.ctx.env.get("BBC_PTY_PATH", "/tmp/fujinet-pty")
            boot_uri = self.ctx.env.get("BBC_BOOT_URI", "persist:/boot/bbc/FN-BOOT.ssd")
        (data_dir / "fujinet.yaml").write_text(
            f"fujinet:\n  device_name: fuji-nio\nboot:\n  mode: config\n  config_uri: {boot_uri}\n  readonly: true\nchannel:\n  pty_path: {pty_path}\n",
            encoding="utf-8",
        )
        print(f"Wrote {label} PTY config: {data_dir / 'fujinet.yaml'}")
        print(f"PTY symlink: {pty_path}")
        print(f"Boot URI: {boot_uri}")

    def run_bbc_pty_for_machine(self, label: str) -> None:
        if label == "master":
            self.boot_disk_master()
        else:
            self.boot_disk_bbc()
        self.fujinet_pty_debug()
        self.write_bbc_pty_config(label)
        run_dir = self.p("FUJINET_NIO") / "build" / "fujibus-pty-debug"
        runner = run_dir / "run-fujinet-nio"
        if not runner.exists():
            raise SystemExit(f"Missing runner: {runner}")
        print(f"==> {label}-pty")
        print(f"    cwd: {run_dir}")
        os.chdir(run_dir)
        os.execv(str(runner), [str(runner)])

    def clean_apps_all(self) -> None:
        self.run_make("apps-all", "NIO_APPS", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", "clean")
        self.run_make("core-apps-clean", "NIO_CORE_APPS", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", "clean")
        self.run_make("config-clean", "NIO_CONFIG", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", "clean")

    def bounce_world(self, backend: str | None = None) -> None:
        env = {"MSDOS_NIO_BACKEND": backend} if backend else None
        self.run_make("bounce-world-clean", "BOUNCE_WORLD_CLIENT_NIO", "clean", env=env)
        self.run_make("bounce-world-build", "BOUNCE_WORLD_CLIENT_NIO", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", env=env)

    def bounce_world_disk(self) -> None:
        self.runner.require_dir(self.p("BOUNCE_WORLD_CLIENT_NIO"))
        self.runner.run(
            "bounce-world-disk",
            ["make", f"FUJINET_NIO_LIB={self.p('FUJINET_NIO_LIB')}", f"CREATE_MSDOS_IMG={self.p('NIO_APPS') / 'msdos' / 'scripts' / 'create_msdos_img.py'}", f"MSDOS_IMAGE={self.ctx.image_dir / 'bwcn-msdos.img'}", "disk-msdos"],
            cwd=self.p("BOUNCE_WORLD_CLIENT_NIO"),
        )

    def build_manifest_msdos_image(self, name: str, apps_manifest: str, output: Path, label: str) -> None:
        self.runner.run(
            name,
            [
                self.ctx.root / "scripts" / "build-msdos-manifest-img",
                "--apps-manifest",
                apps_manifest,
                "--output",
                output,
                "--label",
                label,
            ],
            extra_env={
                "NIO_APPS_MSDOS": self.ctx.env["NIO_APPS_MSDOS_BIN"],
                "NIO_APPS_MSDOS_BIN": self.ctx.env["NIO_APPS_MSDOS_BIN"],
                "NIO_CORE_APPS_MSDOS_BIN": self.ctx.env["NIO_CORE_APPS_MSDOS_BIN"],
                "NIO_CONFIG_MSDOS_BIN": self.ctx.env["NIO_CONFIG_MSDOS_BIN"],
                "FUJINET_NIO_DRIVER": self.ctx.env["FUJINET_NIO_DRIVER"],
                # build-nio-qcow uses this directory to locate the generated
                # driver.
                "FUJINET_NIO_DRIVER": self.ctx.env["FUJINET_NIO_DRIVER"],
                "BOUNCE_WORLD_CLIENT_NIO": self.ctx.env["BOUNCE_WORLD_CLIENT_NIO"],
                "BOUNCE_WORLD": self.ctx.env["BOUNCE_WORLD_CLIENT_NIO"],
            },
        )

    def msdos_apps_image(self) -> None:
        self.apps_msdos()
        self.core_apps_msdos()
        self.config_msdos()
        self.build_manifest_msdos_image("msdos-apps-image", default_msdos_apps_manifest(self.ctx), self.ctx.image_dir / "msdos-apps.img", "NIOAPPS")

    def msdos_boot_config_image(self) -> None:
        self.msdos_driver()
        self.core_apps_msdos()
        self.config_msdos()
        self.build_manifest_msdos_image("msdos-boot-config-image", default_msdos_boot_config_manifest(self.ctx), self.ctx.image_dir / "msdos-boot-config.img", "FNCONFIG")

    def qemu_image(self) -> None:
        self.msdos_driver()
        self.apps_msdos()
        self.core_apps_msdos()
        self.config_msdos()
        self.boot_disk_msdos()
        self.runner.run(
            "qemu-image",
            [
                self.p("FUJINET_QEMU_MSDOS") / "build-nio-qcow",
                "--repo-root",
                self.ctx.root,
                "--apps-dir",
                "FNAPPS",
                "--apps-manifest",
                default_qemu_msdos_apps_manifest(self.ctx),
            ],
            extra_env={
                "FUJINET_NIO_DRIVER": self.ctx.env["FUJINET_NIO_DRIVER"],
                "FUJINET_NIO_LIB": self.ctx.env["FUJINET_NIO_LIB"],
                "NIO_APPS": self.ctx.env["NIO_APPS"],
                "NIO_APPS_MSDOS_BIN": self.ctx.env["NIO_APPS_MSDOS_BIN"],
                "NIO_CORE_APPS_MSDOS_BIN": self.ctx.env["NIO_CORE_APPS_MSDOS_BIN"],
                "NIO_CONFIG_MSDOS_BIN": self.ctx.env["NIO_CONFIG_MSDOS_BIN"],
                "BOUNCE_WORLD_CLIENT_NIO": self.ctx.env["BOUNCE_WORLD_CLIENT_NIO"],
                "BOUNCE_WORLD": self.ctx.env["BOUNCE_WORLD_CLIENT_NIO"],
                "DRIVER": self.ctx.env.get("DRIVER", str(self.p("FUJINET_NIO_DRIVER") / "build" / "dos" / "fujinet.sys")),
            },
        )

    def qemu_run(self, args: list[str]) -> None:
        if args[:1] == ["--"]:
            args = args[1:]
        display = self.ctx.env.get("QEMU_DISPLAY")
        if display == "curses" or "--display=curses" in args or ("--display" in args and args[args.index("--display") + 1 : args.index("--display") + 2] == ["curses"]):
            self.qemu_run_interactive(args)
            return
        hda = self.ctx.env.get("HDA") or self.ctx.env.get("OUTPUT_IMAGE") or str(self.p("FUJINET_QEMU_MSDOS") / "build" / "msdos-nio-apps.qcow2")
        self.runner.run(
            "qemu-run",
            [self.p("FUJINET_QEMU_MSDOS") / "run-qemu-nio", *args],
            extra_env={
                "HDA": hda,
                "FUJINET_NIO_PATH": self.ctx.env["FUJINET_NIO"],
                "FUJINET_NIO_BIN": self.ctx.env.get("FUJINET_NIO_BIN", self.ctx.env["FUJINET_NIO_TCP_DEBUG_BIN"]),
                "NIO_BOOT_DISK": self.ctx.env.get("NIO_BOOT_DISK", str(self.p("FUJINET_NIO") / "distfiles" / "boot" / "msdos" / "autorun.img")),
            },
        )

    def qemu_run_interactive(self, args: list[str]) -> None:
        hda = self.ctx.env.get("HDA") or self.ctx.env.get("OUTPUT_IMAGE") or str(self.p("FUJINET_QEMU_MSDOS") / "build" / "msdos-nio-apps.qcow2")
        env = self.ctx.env.copy()
        env.update({
            "HDA": hda,
            "FUJINET_NIO_PATH": self.ctx.env["FUJINET_NIO"],
            "FUJINET_NIO_BIN": self.ctx.env.get("FUJINET_NIO_BIN", self.ctx.env["FUJINET_NIO_TCP_DEBUG_BIN"]),
            "NIO_BOOT_DISK": self.ctx.env.get("NIO_BOOT_DISK", str(self.p("FUJINET_NIO") / "distfiles" / "boot" / "msdos" / "autorun.img")),
        })
        os.execve(str(self.p("FUJINET_QEMU_MSDOS") / "run-qemu-nio"), [str(self.p("FUJINET_QEMU_MSDOS") / "run-qemu-nio"), *args], env)

    def qemu_monitor(self, args: list[str]) -> None:
        if args[:1] == ["--"]:
            args = args[1:]
        os.execv(str(self.p("FUJINET_QEMU_MSDOS") / "qemu-nio-monitor"), [str(self.p("FUJINET_QEMU_MSDOS") / "qemu-nio-monitor"), *args])

    def msdos_dev_curses(self) -> None:
        if not Path(self.ctx.env["FUJINET_NIO_TCP_DEBUG_BIN"]).exists():
            self.fujinet_tcp_debug()
        self.qemu_image()
        write_manifest(self.ctx)
        self.qemu_run_interactive(["--display", "curses"])

    def atari_run(self, args: list[str]) -> None:
        if args[:1] == ["--"]:
            args = args[1:]
        if not args or args[0].startswith("-"):
            args = ["altirra", *args]
        if not self.p("NIO_APPS_ATARI_BIN").is_dir():
            self.apps_atari()
        if not self.p("NIO_CORE_APPS_ATARI_BIN").is_dir():
            self.core_apps_atari()
        if not Path(self.ctx.env["FUJINET_NIO_ATARI_FUJIBUS_NETSIO_BIN"]).exists():
            self.fujinet_atari_netsio()
        self.runner.run("atari-run", [self.ctx.root / "scripts" / "atari-run", *args])

    def atari_boot_acceptance(self, args: list[str]) -> None:
        """Build and execute the isolated Atari Story 1.3 virtual boot gate."""
        if args[:1] == ["--"]:
            args = args[1:]
        self.altirra()
        self.fujinet_atari_netsio()
        boot_app = self.ctx.root / "integration-tests" / "atari-sio" / "boot-app"
        bridge = self.ctx.root / "repos" / "fujinet-emulator-bridge" / "fujinet-bridge"
        self.runner.require_dir(bridge)
        if not (bridge / "netsiohub" / "__main__.py").is_file():
            raise SystemExit(
                f"Missing NetSIO hub module: {bridge / 'netsiohub' / '__main__.py'}\n"
                "Initialize repos/fujinet-emulator-bridge first."
            )
        self.runner.run("atari-boot-acceptance-image", ["make"], cwd=boot_app)
        self.runner.run(
            "atari-boot-acceptance",
            ["python3", self.ctx.root / "integration-tests" / "atari-sio" / "run_boot_acceptance.py", *args],
        )

    def atari_stop(self) -> None:
        patterns = [
            f"python3 -m netsiohub --port {self.ctx.env.get('ATARI_NETSIO_ATDEV_PORT', '9996')} --netsio-port {self.ctx.env.get('ATARI_NETSIO_PORT', '9997')}",
            self.ctx.env["FUJINET_NIO_ATARI_FUJIBUS_NETSIO_BIN"],
        ]
        for pattern in patterns:
            subprocess.run(["pkill", "-TERM", "-f", pattern], check=False)
        time.sleep(1)
        for pattern in patterns:
            subprocess.run(["pkill", "-KILL", "-f", pattern], check=False)

    def workflow_bbc(self) -> None:
        self.cc65_bbc()
        self.cc65_clib()
        self.lib_bbc()
        self.apps_bbc()
        self.config_bbc()
        self.confnio_disk_for_machine("BBC", "bbc")
        self.boot_disk_bbc()

    def workflow_master(self) -> None:
        self.cc65_bbc()
        self.cc65_clib()
        self.lib_bbc()
        self.confnio_disk_for_machine("MASTER", "master")
        self.boot_disk_master()

    def workflow_msdos(self) -> None:
        self.lib_msdos()
        self.msdos_driver()
        self.apps_msdos()
        self.core_apps_msdos()
        self.config_msdos()
        self.boot_disk_msdos()
        self.msdos_apps_image()
        self.msdos_boot_config_image()
        self.qemu_image()

    def workflow_atari(self) -> None:
        self.altirra()
        self.fujinet_atari_netsio()
        self.lib_atari()
        self.apps_atari()
        self.core_apps_atari()
        self.config_atari()
        self.boot_disk_atari()

    def workflow_linux(self) -> None:
        self.fujinet_tcp()
        self.fujinet_pty()
        self.fujinet_rs232()
        self.lib_linux()

    def workflow_amiga(self) -> None:
        self.lib_amiga()
        self.apps_amiga()
        self.core_apps_amiga()

    def workflow_all(self) -> None:
        self.workflow_linux()
        self.workflow_msdos()
        self.workflow_atari()
        self.workflow_bbc()
        self.workflow_amiga()


def build_tasks(build: Build) -> dict[str, Task]:
    def t(name: str, desc: str, action: Callable[[Build], None], *, workflow: bool = False, hidden: bool = False, consumes_args: bool = False, help_text: Callable[[Build], str] | None = None) -> tuple[str, Task]:
        return name, Task(name, desc, action, workflow, hidden, consumes_args, help_text)

    items = [
        t("all", "Build the usual integrated stack", Build.workflow_all, workflow=True),
        t("bbc", "Build all BBC-facing prerequisites, config, apps, and boot disks", Build.workflow_bbc, workflow=True),
        t("master", "Build all Master-facing prerequisites, config, and boot disks", Build.workflow_master, workflow=True),
        t("msdos", "Build all MS-DOS-facing driver, apps, disks, and QEMU image", Build.workflow_msdos, workflow=True),
        t("atari", "Build all Atari-facing libraries, apps, boot disk, and emulator-side FujiNet", Build.workflow_atari, workflow=True),
        t("linux", "Build host/Linux FujiNet presets and library", Build.workflow_linux, workflow=True),
        t("amiga", "Build Amiga-facing library and nio-apps test apps", Build.workflow_amiga, workflow=True),
        t("rp2040-stimulus", "Build RP2040 W0 PIO laboratory generator (no flashing)", Build.rp2040_stimulus, help_text=Build.rp2040_stimulus_help),
        t("rp2350", "Test PIO and build the RP2350B Zorro bridge skeleton", Build.workflow_rp2350, workflow=True, help_text=Build.rp2350_help),
        t("rp2350-pio-tests", "Build/run native epio PIO tests (Debug + Release; no hardware)", Build.rp2350_pio_tests, help_text=Build.rp2350_help),
        t("rp2350-firmware", "Bootstrap/build RP2350B bridge ELF and UF2 (Pico SDK)", Build.rp2350_firmware, help_text=Build.rp2350_help),
        t("altirra", "Configure/build AltirraSDL with the workspace preset", Build.altirra),
        t("fujinet", "Build/test fujinet-nio TCP, PTY, and RS-232 presets", lambda b: (b.fujinet_tcp(), b.fujinet_pty(), b.fujinet_rs232())),
        t("fujinet-tcp", "Build/test fujinet-nio TCP debug and release", Build.fujinet_tcp),
        t("fujinet-tcp-debug", "Build fujinet-nio TCP debug only", Build.fujinet_tcp_debug),
        t("fujinet-pty", "Build/test fujinet-nio PTY debug", Build.fujinet_pty),
        t("fujinet-rs232", "Build/test fujinet-nio RS-232 debug", Build.fujinet_rs232),
        t("fujinet-atari-netsio", "Build fujinet-nio Atari FujiBus over NetSIO debug", Build.fujinet_atari_netsio),
        t("lib", "Build fujinet-nio-lib Linux, MS-DOS, BBC, Atari, and Amiga libraries", lambda b: (b.lib_linux(), b.lib_msdos(), b.lib_atari(), b.lib_bbc(), b.lib_amiga())),
        t("lib-linux", "Build fujinet-nio-lib Linux library", Build.lib_linux),
        t("lib-msdos", "Build fujinet-nio-lib MS-DOS library", Build.lib_msdos),
        t("lib-atari", "Build fujinet-nio-lib Atari library", Build.lib_atari),
        t("lib-bbc", "Build fujinet-nio-lib BBC library", Build.lib_bbc),
        t("lib-amiga", "Build fujinet-nio-lib Amiga library", Build.lib_amiga),
        t("amiga-driver-sdk", "Build the public Amiga DiskDevice SDK archive", Build.amiga_driver_sdk),
        t("lib-tests", "Run fujinet-nio-lib host-side wire tests", Build.lib_tests),
        t("cc65", "Incrementally build cc65 tools and BBC libraries", Build.cc65),
        t("cc65-bbc", "Incrementally build cc65 BBC and bbc-clib libraries", Build.cc65_bbc),
        t("cc65-clib", "Build cc65-clib ROM and rebuild cc65 BBC libraries", Build.cc65_clib),
        t("cc65-clib-tests", "Run cc65-clib tests without Beebium integration", lambda b: b.cc65_clib_tests(False)),
        t("cc65-clib-full-tests", "Run cc65-clib full test matrix", lambda b: b.cc65_clib_tests(True)),
        t("pdcurses-msdos", "Fetch/build PDCurses for Open Watcom MS-DOS", Build.pdcurses_msdos),
        t("msdos-driver", "Build fujinet-nio-driver FUJINET.SYS", Build.msdos_driver),
        t("msdos-tests", "Run fujinet-nio-driver host unit tests", Build.msdos_tests),
        t("apps-all", "Build all nio-apps targets", Build.apps_all),
        t("apps-clean", "Clean nio-apps, nio-core-apps, and nio-config builds", Build.clean_apps_all),
        t("apps-msdos", "Build nio-apps MS-DOS test apps", Build.apps_msdos),
        t("apps-atari", "Build nio-apps Atari test apps", Build.apps_atari),
        t("apps-amiga", "Deprecated: unprofiled Amiga apps are disabled", Build.apps_amiga),
        t("amiga-test-adf", "Build an AmigaOS test ADF containing the selected nio-apps test app", lambda b: b.amiga_test_adf([]), consumes_args=True, help_text=Build.amiga_test_adf_help),
        t("amiga-test-disk", "Build an AmigaOS HDF containing the selected nio-apps test app", Build.amiga_test_disk),
        t("apps-bbc", "Build nio-apps BBC test apps", Build.apps_bbc),
        t("core-apps-all", "Build all nio-core-apps targets", Build.core_apps_all),
        t("core-apps-msdos", "Build nio-core-apps MS-DOS utilities", Build.core_apps_msdos),
        t("core-apps-atari", "Build nio-core-apps Atari utilities", Build.core_apps_atari),
        t("core-apps-amiga", "Deprecated: unprofiled Amiga core apps are disabled", Build.core_apps_amiga),
        t("config-all", "Build all nio-config targets", Build.config_all),
        t("config-msdos", "Build nio-config MS-DOS app", Build.config_msdos),
        t("config-atari", "Build nio-config Atari app", Build.config_atari),
        t("config-bbc", "Build nio-config BBC app", Build.config_bbc),
        t("boot-disks", "Build/install platform boot disks into fujinet-nio distfiles", Build.boot_disks),
        t("boot-disk", "Alias for boot-disks", Build.boot_disks, hidden=True),
        t("bbc-boot-disk", "Build/install BBC FN-BOOT.ssd", Build.boot_disk_bbc),
        t("master-boot-disk", "Build/install Master FN-BOOT-M.ssd", Build.boot_disk_master),
        t("msdos-boot-disk", "Build/install MS-DOS boot disk", Build.boot_disk_msdos),
        t("atari-boot-disk", "Build/install Atari boot disk", Build.boot_disk_atari),
        t("amiga-artifacts-wb13", "Build/stage WB1.3 Amiga artifacts", Build.amiga_artifacts_wb13),
        t("amiga-artifacts-wb31", "Build/stage WB3.1 Amiga artifacts", Build.amiga_artifacts_wb31),
        t("amiga-artifacts-wb32", "Build/stage WB3.2 Amiga artifacts", Build.amiga_artifacts_wb32),
        t("amiga-default-disk-wb13", "Build/install WB1.3 FujiNet default ADF", Build.amiga_default_disk_wb13),
        t("amiga-default-disk-wb31", "Build/install WB3.1 FujiNet default ADF", Build.amiga_default_disk_wb31),
        t("amiga-default-disk-wb32", "Build/install WB3.2 FujiNet default ADF", Build.amiga_default_disk_wb32),
        t("confnio-bbc-disk", "Build standalone BBC CONFNIO SSD", lambda b: b.confnio_disk_for_machine("BBC", "bbc")),
        t("confnio-master-disk", "Build standalone Master CONFNIO SSD", lambda b: b.confnio_disk_for_machine("MASTER", "master")),
        t("bbc-pty", "Build BBC boot disk and run fujinet-nio PTY", lambda b: b.run_bbc_pty_for_machine("bbc"), consumes_args=True),
        t("master-pty", "Build Master boot disk and run fujinet-nio PTY", lambda b: b.run_bbc_pty_for_machine("master"), consumes_args=True),
        t("bounce-world", "Build bounce-world-client-nio", lambda b: b.bounce_world()),
        t("bounce-world-f5", "Build bounce-world-client-nio with F5 backend", lambda b: b.bounce_world("f5")),
        t("bounce-world-ioctl", "Build bounce-world-client-nio with ioctl backend", lambda b: b.bounce_world("ioctl")),
        t("bounce-world-disk", "Build Bounce World MS-DOS raw FAT disk image", Build.bounce_world_disk),
        t("msdos-apps-image", "Build workspace raw FAT MS-DOS apps image", Build.msdos_apps_image),
        t("msdos-boot-config-image", "Build workspace raw FAT MS-DOS FUJINET.SYS/config image", Build.msdos_boot_config_image),
        t("qemu-msdos-image", "Build workspace QEMU MS-DOS qcow2 image", Build.qemu_image),
        t("msdos-image", "Compatibility alias for msdos-apps-image", lambda b: (print("msdos-image is a compatibility alias; use msdos-apps-image."), b.msdos_apps_image(), shutil.copy2(b.ctx.image_dir / "msdos-apps.img", b.ctx.image_dir / "nio-apps.img")), hidden=True),
        t("apps-image", "Compatibility alias for msdos-apps-image", lambda b: (print("apps-image is a compatibility alias; use msdos-apps-image."), b.msdos_apps_image(), shutil.copy2(b.ctx.image_dir / "msdos-apps.img", b.ctx.image_dir / "msdos-nio-apps.img")), hidden=True),
        t("qemu-image", "Compatibility alias for qemu-msdos-image", Build.qemu_image, hidden=True),
        t("qemu-run", "Run fujinet-qemu-msdos with workspace defaults", lambda b: b.qemu_run([]), consumes_args=True, help_text=lambda b: b.qemu_run_help()),
        t("qemu-monitor", "Send a command/key to active qemu-run monitor socket", lambda b: b.qemu_monitor([]), consumes_args=True, help_text=lambda b: b.qemu_monitor_help()),
        t("msdos-dev-curses", "Build and run MS-DOS NIO app image in QEMU curses mode", Build.msdos_dev_curses, consumes_args=True),
        t("atari-run", "Run an Atari app under the configured emulator", lambda b: b.atari_run([]), consumes_args=True, help_text=lambda b: b.atari_run_help()),
        t("atari-boot-acceptance", "Run the deterministic Altirra/NetSIO Atari boot acceptance", lambda b: b.atari_boot_acceptance([]), consumes_args=True, help_text=lambda b: b.atari_boot_acceptance_help()),
        t("atari-stop", "Stop stale Atari emulator sidecars", Build.atari_stop, consumes_args=True),
        t("amiga-run", "Run the selected Amiga test app in Amiberry", lambda b: b.amiga_run([], build_adf=False), consumes_args=True, help_text=lambda b: b.amiga_run_help(build_adf=False)),
        t("amiga-e2e", "Build and run the selected Amiga test app in Amiberry against FujiNet NIO", lambda b: b.amiga_run([], build_adf=True), consumes_args=True, help_text=lambda b: b.amiga_run_help(build_adf=True)),
        t("amiga-workbench", "Run a named Amiga Workbench profile in Amiberry", lambda b: b.amiga_workbench([]), consumes_args=True, help_text=Build.amiga_workbench_help),
        t("amiga-tests", "Run the Amiberry guest integration-test suite", lambda b: b.amiga_tests([]), consumes_args=True),
        t("manifest", "Write build/manifest.txt only", lambda b: write_manifest(b.ctx)),
    ]
    return dict(items)
