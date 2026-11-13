from __future__ import annotations

import json
import os
import re
import shutil
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

try:
    from PIL import Image as _PILImage
    _PILLOW = True
except ImportError:
    _PILLOW = False


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "integration-tests" / "amiberry"
sys.path.insert(0, str(ROOT / "tools" / "build"))
from nio_build.amiga_config import filesystem2_setting, resolve_fast_file_system
DEFAULT_EVIDENCE_DIR = ROOT / "test-evidence"
# Legacy startup sequences target the WB3.x Shell and dynamic DOS-node
# lifecycle, so every such case runs under both WB3.2 and WB3.1.  WB1.3 must be
# opted into explicitly after its commands, artefacts, and MountList lifecycle
# have been validated there.
DEFAULT_CASE_ENVIRONMENTS = ["wb32", "wb31"]

# Add tools/ to path so we can call amiga_emulator.ipc directly.
_TOOLS = ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from amiga_emulator import ipc as _amiberry_ipc  # noqa: E402
from amiga_emulator.debug_snapshot import capture_debug_snapshot as _capture_debug_snapshot  # noqa: E402


def resolve_case_for_environment(case_name: str, registered_case: dict[str, Any],
                                 active_environment: str | None) -> dict[str, Any]:
    """Return a case with its active Workbench guest-plan override applied."""
    case = dict(registered_case)
    supported_environments = case.get("environments", DEFAULT_CASE_ENVIRONMENTS)
    if (not isinstance(supported_environments, list)
            or not all(isinstance(item, str) for item in supported_environments)):
        raise AssertionError(
            f"Amiberry case '{case_name}' has invalid environments: "
            f"{supported_environments!r}"
        )
    if "wb32" in supported_environments and "wb31" not in supported_environments:
        raise AssertionError(
            f"Amiberry case '{case_name}' lists wb32 without wb31; WB3.x "
            "cases must run under both releases"
        )
    if active_environment not in supported_environments:
        pytest.skip(
            f"Amiberry case '{case_name}' supports only "
            f"{', '.join(supported_environments)}; active environment is "
            f"{active_environment or 'unknown'}"
        )

    variants = case.pop("environment_variants", {})
    if not isinstance(variants, dict):
        raise AssertionError(
            f"Amiberry case '{case_name}' has invalid environment_variants: "
            f"{variants!r}"
        )
    for environment, override in variants.items():
        if environment not in supported_environments or not isinstance(override, dict):
            raise AssertionError(
                f"Amiberry case '{case_name}' has invalid variant "
                f"for {environment!r}: {override!r}"
            )
    if active_environment in variants:
        case.update(variants[active_environment])
    # Every guest plan must deploy artifacts compiled for that same Workbench
    # generation.  Falling back to build/amiga/ makes the outcome depend on
    # whichever profile was built most recently (and can silently put a
    # nix13 binary into a WB3.x control run).  Environment IDs intentionally
    # match the named Amiga artifact profiles.
    if "amiga_artifact_profile" not in case and active_environment:
        case["amiga_artifact_profile"] = active_environment
    return case


def xdf_command(environment: dict[str, str]) -> list[str]:
    if shutil.which("xdftool", path=environment.get("PATH")):
        return ["xdftool"]
    if shutil.which("uvx", path=environment.get("PATH")):
        return ["uvx", "--from", "amitools", "xdftool"]
    raise RuntimeError("xdftool or uvx is required")


@dataclass(frozen=True)
class MonitorSnapshot:
    completion_seen: bool
    requester_seen: bool
    runner_returncode: int | None
    now: float
    deadline: float
    debugger_mode: bool = False
    debugger_paused: bool = False
    capture_mode: bool = False
    guest_reset_seen: bool = False


@dataclass(frozen=True)
class CompletionLogState:
    pending_line: str = ""
    current_payload: bytes = b""
    current_marker_match: bool = False


@dataclass
class SecondBootMonitor:
    offset: int
    state: CompletionLogState = CompletionLogState()

    def poll(self, text: str, marker: str, *, peer_exited: bool, guest_log: str):
        if peer_exited:
            return False, "native peer exited"
        if guest_reset_from_amiberry_log(guest_log):
            return False, "guest reset"
        found, self.state = scan_completion_log_chunk(text[self.offset:], marker, self.state)
        self.offset = len(text)
        return found, None


def guest_reset_from_amiberry_log(text: str) -> bool:
    """A second DH0 HDF mount means Kickstart remounted after a Guru reset."""
    return text.count("Mounting uaehf.device:0 0") > 1


def host_file_is_pass(path: Path) -> bool:
    try:
        return path.is_file() and path.read_text(
            encoding="ascii", errors="ignore"
        ) == "PASS\n"
    except OSError:
        return False


def native_test_objects_omit_serial_session_slip(makefile_text: str) -> bool:
    start = makefile_text.find("NIO_NATIVE_TEST_OBJECTS")
    end = makefile_text.find("SERIAL_OBJECTS", start)
    if start < 0 or end < 0:
        return False
    block = makefile_text[start:end]
    return (
        "fujinet_nio_directory_backend" in block
        and "fujinet_nio_packet_backend" in block
        and "fujinet_nio_serial_backend" not in block
        and "fn_session" not in block
        and "fn_slip" not in block
    )


def native_test_map_omits_serial_session_slip(map_text: str) -> bool:
    return (
        "fn_stream_session" not in map_text
        and "fn_slip_" not in map_text
        and "fujinet_nio_serial_backend" not in map_text
    )


def evaluate_monitor_state(snapshot: MonitorSnapshot) -> tuple[str, str | None]:
    if snapshot.guest_reset_seen and not snapshot.capture_mode:
        return ("failure", "guest_reset")
    if snapshot.requester_seen and not snapshot.capture_mode:
        return ("failure", "requester")
    if snapshot.runner_returncode is not None:
        return ("failure", "runner_exit")
    if snapshot.completion_seen:
        return ("success", "completion_log")
    if (not snapshot.debugger_mode and not snapshot.debugger_paused and
            snapshot.now >= snapshot.deadline):
        return ("failure", "timeout")
    return ("continue", None)


def read_log_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except OSError:
        return ""


def append_monitor_trace(path: Path, line: str) -> None:
    try:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    except OSError:
        pass


_FUJIBUS_RECEIVE_RE = re.compile(r"fujibus: receive: id=(\d+) dev=(0x[0-9A-Fa-f]+) cmd=(0x[0-9A-Fa-f]+)")
_FUJIBUS_SEND_RE = re.compile(r"fujibus: send: dev=(0x[0-9A-Fa-f]+) status=(\d+) cmd=(0x[0-9A-Fa-f]+)")
_FUJIBUS_HEX_RE = re.compile(r"fujibus:\s+[0-9a-f]{4}:\s+([0-9a-f ]+)\|", re.IGNORECASE)


def _completion_state_with_payload_finalized(state: CompletionLogState, marker_bytes: bytes) -> CompletionLogState:
    if not state.current_payload:
        return state
    return CompletionLogState(
        pending_line=state.pending_line,
        current_payload=state.current_payload,
        current_marker_match=marker_bytes in state.current_payload,
    )


def scan_completion_log_chunk(chunk: str, marker: str,
                              state: CompletionLogState | None = None) -> tuple[bool, CompletionLogState]:
    state = state or CompletionLogState()
    marker_bytes = marker.encode("latin-1", errors="ignore")
    text = state.pending_line + chunk
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        pending_line = lines.pop()
    else:
        pending_line = ""

    current_payload = bytearray(state.current_payload)
    current_marker_match = state.current_marker_match

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")

        if _FUJIBUS_RECEIVE_RE.search(line):
            current_payload = bytearray()
            current_marker_match = False
            continue

        hex_match = _FUJIBUS_HEX_RE.search(line)
        if hex_match:
            current_payload.extend(bytes.fromhex(hex_match.group(1)))
            continue

        if current_payload:
            current_marker_match = marker_bytes in current_payload

        send_match = _FUJIBUS_SEND_RE.search(line)
        if send_match and current_marker_match:
            return (send_match.group(2) == "0", CompletionLogState(
                pending_line=pending_line,
                current_payload=bytes(current_payload),
                current_marker_match=current_marker_match,
            ))

    next_state = _completion_state_with_payload_finalized(
        CompletionLogState(
            pending_line=pending_line,
            current_payload=bytes(current_payload),
            current_marker_match=current_marker_match,
        ),
        marker_bytes,
    )
    return (False, next_state)


def scan_ordered_results(environment: dict[str, str], image: Path,
                         ordered_results: list[str]) -> list[str]:
    present: list[str] = []
    with tempfile.TemporaryDirectory(prefix="amiga-progress-") as result_dir:
        for result_name in ordered_results:
            destination = Path(result_dir) / result_name.replace("/", "_")
            extracted = subprocess.run(
                [*xdf_command(environment), str(image), "read", result_name, str(destination)],
                cwd=ROOT,
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if extracted.returncode != 0:
                break
            present.append(result_name)
    return present


def checkpoint_progress(ordered_results: list[str], present_results: list[str]) -> tuple[str, str]:
    last_present = present_results[-1] if present_results else "<none>"
    if len(present_results) < len(ordered_results):
        first_missing = ordered_results[len(present_results)]
    else:
        first_missing = "<none>"
    return last_present, first_missing


def build_failure_report(*, case_name: str, termination_reason: str,
                         ordered_results: list[str], present_results: list[str],
                         requester_seen: bool, recent_activity: bool,
                         runner_exit_state: str) -> str:
    last_present, first_missing = checkpoint_progress(ordered_results, present_results)
    return (
        f"Amiberry case '{case_name}' did not reach its completion condition. "
        f"termination reason: {termination_reason}; "
        f"last checkpoint present: {last_present}; "
        f"first checkpoint missing: {first_missing}; "
        f"requester seen: {'yes' if requester_seen else 'no'}; "
        f"recent NIO/serial activity: {'yes' if recent_activity else 'no'}; "
        f"runner exit state: {runner_exit_state}"
    )


def load_workspace_env() -> dict[str, str]:
    command = ["bash", "-lc", 'source "$1" >/dev/null && env -0', "_", str(ROOT / "scripts/env.sh")]
    output = subprocess.check_output(command, cwd=ROOT)
    environment = os.environ.copy()
    for item in output.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            environment[key.decode()] = value.decode(errors="replace")
    return environment


def load_suite_config() -> dict[str, Any]:
    with (SUITE / "tests.toml").open("rb") as stream:
        return tomllib.load(stream)


def load_env_manifest(env_id: str, machine_id: str | None = None) -> dict[str, Any]:
    """Load the manifest.json for a built environment.

    For machine-agnostic environments (wb31): build/amiga-envs/<env_id>/manifest.json
    For machine-keyed environments (wb32):    build/amiga-envs/<env_id>/<machine_id>/manifest.json
    """
    envs_root = ROOT / "build" / "amiga-envs"
    if machine_id:
        machine_path = envs_root / env_id / machine_id / "manifest.json"
        agnostic_path = envs_root / env_id / "manifest.json"
        if machine_path.is_file():
            manifest_path = machine_path
        elif agnostic_path.is_file():
            # Environment is machine-agnostic; --amiga-machine selects hardware only.
            manifest_path = agnostic_path
        else:
            raise SystemExit(
                f"AmigaOS environment '{env_id}/{machine_id}' has not been built.\n"
                f"Run: scripts/amiga-env build {env_id} --machine {machine_id}\n"
                f"Or (if {env_id} is machine-agnostic): scripts/amiga-env build {env_id}"
            )
    else:
        manifest_path = envs_root / env_id / "manifest.json"
        if not manifest_path.is_file():
            raise SystemExit(
                f"AmigaOS environment '{env_id}' has not been built.\n"
                f"Run: scripts/amiga-env build {env_id}"
            )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_cases() -> dict[str, dict]:
    return {case["name"]: case for case in load_suite_config()["test"]}


def _load_machine_profile_yaml(machine_id: str) -> dict[str, Any]:
    """Load a machine YAML profile, returning a nested dict.

    The ``uae_config`` field, if present, is resolved to an absolute path
    relative to ``configs/amiga/`` (the amiga config root), where .uae files
    live alongside the machines/ subdirectory.

    Uses PyYAML if available; otherwise uses a minimal two-level parser
    sufficient for the machine profile format (scalar values and one level
    of nested dicts — no lists, no anchors).
    """
    amiga_cfg_dir = ROOT / "configs" / "amiga"
    machine_path = amiga_cfg_dir / "machines" / f"{machine_id}.yaml"
    if not machine_path.is_file():
        raise FileNotFoundError(f"Machine profile not found: {machine_path}")
    text = machine_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import]
        profile = yaml.safe_load(text)
    except ImportError:
        # Minimal fallback: parse two-level key: value / key:\n  subkey: value
        profile: dict[str, Any] = {}
        current_dict: dict[str, Any] | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if ":" not in stripped:
                continue
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if indent == 0:
                if v:
                    profile[k] = v
                    current_dict = None
                else:
                    current_dict = {}
                    profile[k] = current_dict
            elif current_dict is not None:
                try:
                    current_dict[k] = int(v)
                except (ValueError, TypeError):
                    current_dict[k] = v

    # Resolve uae_config to an absolute path (relative to configs/amiga/).
    uae_config = profile.get("uae_config", "")
    if uae_config:
        resolved = (amiga_cfg_dir / uae_config).resolve()
        profile["uae_config"] = str(resolved)

    return profile


def machine_environment(machine: dict[str, Any]) -> dict[str, str]:
    """Translate a machine profile dict into AMIBERRY_* environment variables.

    Accepts two formats:
    - YAML profile (settings is a dict of {key: value}): machine-specific UAE
      overrides.  Runtime invocation args (AMIBERRY_EXTRA_ARGS) come from the
      suite config [amiberry].args so they are not baked into the machine
      profile.
    - Legacy tests.toml format (settings is a list[str] of "key=value"):
      used when --amiga-machine is not given.
    """
    settings = machine.get("settings", {})
    if isinstance(settings, dict):
        # YAML machine profile: convert {key: value} to "key=value" list
        settings_list = [f"{k}={v}" for k, v in settings.items()]
        # Invocation flags (e.g. -w -1) live in tests.toml, not the machine profile
        suite_args: list[str] = list(load_suite_config().get("amiberry", {}).get("args", []))
    else:
        # Legacy tests.toml format
        if not (isinstance(settings, list) and
                all(isinstance(v, str) for v in settings)):
            raise ValueError("[amiberry].settings must be an array of strings")
        settings_list = list(settings)
        suite_args = machine.get("args", [])
        if not (isinstance(suite_args, list) and
                all(isinstance(v, str) for v in suite_args)):
            raise ValueError("[amiberry].args must be an array of strings")

    result: dict[str, str] = {
        "AMIBERRY_EXTRA_ARGS": shlex.join(suite_args),
        "AMIBERRY_EXTRA_SETTINGS": ";".join(settings_list),
    }
    uae_config = machine.get("uae_config", "")
    if uae_config:
        result["AMIBERRY_UAE_CONFIG"] = uae_config
    return result


def build_nio_binary(environment: dict[str, str]) -> None:
    """Build the TCP NIO binary without coupling E2E setup to ctest."""
    nio_root = ROOT / "repos" / "fujinet-nio"
    build_dir = nio_root / "build" / "fujibus-tcp-debug"
    binary = build_dir / "fujinet-nio"
    if not binary.is_file():
        subprocess.run(
            ["cmake", "--preset", "fujibus-tcp-debug"],
            cwd=nio_root,
            env=environment,
            check=True,
        )
    subprocess.run(
        ["cmake", "--build", "--preset", "fujibus-tcp-debug-build"],
        cwd=nio_root,
        env=environment,
        check=True,
    )


def build_native_test_runner(environment: dict[str, str]) -> Path:
    """Build the Story 1.9 host directory endpoint used by native-test guest cases."""
    nio_root = ROOT / "repos" / "fujinet-nio"
    binary = nio_root / "build" / "fujibus-pty-debug" / "tests" / "fujinet-nio-native-test"
    if not binary.is_file():
        subprocess.run(
            ["cmake", "--preset", "fujibus-pty-debug"],
            cwd=nio_root,
            env=environment,
            check=True,
        )
    subprocess.run(
        ["cmake", "--build", "--preset", "fujibus-pty-debug-build",
         "--target", "fujinet-nio-native-test"],
        cwd=nio_root,
        env=environment,
        check=True,
    )
    if not binary.is_file():
        raise AssertionError(f"native-test host runner was not built: {binary}")
    return binary


def _patch_boot_block(image: Path) -> None:
    """Replace the xdftool boot block with a minimal KS 3.x-compatible one.

    xdftool's generated OFS boot block uses exec.library LVOs that are
    incompatible with Kickstart 3.2, causing a crash or hang when KS tries
    to boot from the floppy.  OFS validates the boot block checksum as part
    of its mount logic (separate from KS boot logic), so corrupting the
    checksum breaks mounting too.

    This function writes a minimal boot block that:
    - Has the "DOS\\x00" magic so OFS recognises it as an OFS disk
    - Points at root block 880 (standard DD floppy)
    - Has valid checksum (so OFS will mount the disk)
    - Contains boot code ``MOVEQ #-1, D0 ; RTS`` (70 FF 4E 75) that tells
      Kickstart "boot from this device failed, try the next one", causing
      KS to silently fall through to DH0:
    - Leaves the rest of the boot block as zeros (no code to crash)
    """
    import struct

    # Build the 1024-byte boot block (2 sectors).
    bb = bytearray(1024)
    # "DOS\x00" = OFS type
    bb[0:4] = b"DOS\x00"
    # Checksum placeholder (word 1, offset 4-7) — computed below
    # Root block pointer at offset 8-11 = 880
    struct.pack_into(">I", bb, 8, 880)
    # Boot code at offset 12: MOVEQ #-1, D0 (70 FF) ; RTS (4E 75)
    bb[12:16] = bytes([0x70, 0xFF, 0x4E, 0x75])

    # Compute checksum using the Amiga end-around-carry algorithm.
    # Treat the checksum word (word 1, offset 4-7) as 0 for the sum.
    words = list(struct.unpack_from(">256I", bb))  # 256 longwords = 1024 bytes
    total = 0
    for i, w in enumerate(words):
        if i == 1:
            continue  # skip checksum word
        total += w
        if total > 0xFFFFFFFF:
            total = (total & 0xFFFFFFFF) + 1  # end-around carry
    checksum = (~total) & 0xFFFFFFFF
    struct.pack_into(">I", bb, 4, checksum)

    # Patch the first 1024 bytes of the ADF in-place; leave the rest intact.
    data = bytearray(image.read_bytes())
    data[0:1024] = bb
    image.write_bytes(bytes(data))


def create_ffs_adf(environment: dict[str, str], image: Path,
                   marker_name: str = "KNOWN.TXT",
                   marker_text: str = "FUJINET FFS ADF READ PASSED\n",
                   volume_name: str = "NIOFFS") -> None:
    image.unlink(missing_ok=True)
    marker = image.parent / marker_name
    marker.write_text(marker_text, encoding="ascii")
    subprocess.run(
        [*xdf_command(environment), str(image), "create", "+", "format", volume_name, "ffs",
         "+", "boot", "install", "+", "write", str(marker), marker_name],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    if image.stat().st_size != 1760 * 512:
        raise AssertionError("FFS ADF is not standard 880 KiB geometry")


def create_standard_adf(environment: dict[str, str], image: Path,
                        marker_name: str = "KNOWN.TXT",
                        marker_text: str = "FUJINET ADF READ PASSED\n",
                        volume_name: str = "NIOADF") -> None:
    image.unlink(missing_ok=True)
    marker = image.parent / marker_name
    marker.write_text(marker_text, encoding="ascii")
    subprocess.run(
        [*xdf_command(environment), str(image), "create", "+", "format", volume_name,
         "+", "boot", "install", "+", "write", str(marker), marker_name],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    if image.stat().st_size != 1760 * 512:
        raise AssertionError("deterministic ADF is not standard 880 KiB geometry")


def create_hd_adf(environment: dict[str, str], image: Path,
                  marker_name: str = "HD.TXT",
                  marker_text: str = "FUJINET HD ADF READ PASSED\n") -> None:
    """Create a deterministic HD ADF (1.76 MiB, 3520 sectors)."""
    image.unlink(missing_ok=True)
    marker = image.parent / marker_name
    marker.write_text(marker_text, encoding="ascii")
    subprocess.run(
        [*xdf_command(environment), str(image), "create", "type=adf_hd",
         "+", "format", "NIOHD",
         "+", "boot", "install",
         "+", "write", str(marker), marker_name],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    if image.stat().st_size != 3520 * 512:
        raise AssertionError("HD ADF is not 1.76 MiB geometry")


def create_hd_ffs_adf(environment: dict[str, str], image: Path,
                      marker_name: str = "BASEHN.TXT",
                      marker_text: str = "FUJINET WRITABLE HD FFS BASE\n") -> None:
    """Create a deterministic FFS high-density ADF (1.76 MiB, 3520 sectors)."""
    image.unlink(missing_ok=True)
    marker = image.parent / marker_name
    marker.write_text(marker_text, encoding="ascii")
    subprocess.run(
        [*xdf_command(environment), str(image), "create", "type=adf_hd",
         "+", "format", "NIOHDFFS", "ffs",
         "+", "boot", "install",
         "+", "write", str(marker), marker_name],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    if image.stat().st_size != 3520 * 512:
        raise AssertionError("HD FFS ADF is not 1.76 MiB geometry")


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--run-amiga",
        action="store_true",
        default=False,
        help="run the Amiberry integration tests; otherwise skip them",
    )
    parser.addoption(
        "--amiga-env",
        default=None,
        help="AmigaOS environment id (e.g. wb31, wb32). The built base HDF and "
             "kickstart are read from build/amiga-envs/<id>/manifest.json. "
             "Build with: scripts/amiga-env build <id> [--machine <machine_id>]",
    )
    parser.addoption(
        "--amiga-machine",
        default=None,
        help="Machine profile id (e.g. a1200-030). When given, the machine YAML "
             "from configs/amiga/machines/<id>.yaml overrides amiberry settings.",
    )


@pytest.fixture(scope="session")
def amiga_environment(pytestconfig: Any) -> dict[str, str]:
    if not pytestconfig.getoption("--run-amiga") and os.environ.get("AMIGA_E2E") != "1":
        pytest.skip("Amiberry tests disabled; use --run-amiga or AMIGA_E2E=1")

    environment = load_workspace_env()
    missing: list[str] = []

    env_id: str | None = pytestconfig.getoption("--amiga-env")
    machine_id: str | None = pytestconfig.getoption("--amiga-machine")
    if env_id:
        # New path: load OS root and kickstart from the built environment manifest.
        # Pass machine_id when given — machine-keyed envs live under <env_id>/<machine_id>/.
        manifest = load_env_manifest(env_id, machine_id)
        base_hdf = Path(manifest["base_hdf"])
        label = f"{env_id}/{machine_id}" if machine_id else env_id
        machine_flag = f" --machine {machine_id}" if machine_id else ""
        if not base_hdf.is_file():
            pytest.skip(
                f"AmigaOS environment '{label}' base HDF is missing: {base_hdf}\n"
                f"Run: scripts/amiga-env build {env_id}{machine_flag}"
            )
        environment["AMIGA_ENV_ID"] = env_id
        environment["AMIGA_ENV_BASE_HDF"] = str(base_hdf)
        environment["AMIBERRY_KICKSTART"] = manifest["kickstart"]
        if manifest.get("rom_key"):
            environment["AMIBERRY_ROM_KEY"] = manifest["rom_key"]
        fast_file_system = resolve_fast_file_system(manifest, ROOT, environment)
        if fast_file_system:
            environment["AMIBERRY_FAST_FILE_SYSTEM"] = fast_file_system
    else:
        pytest.skip(
            "No AmigaOS environment specified. "
            "Re-run with --amiga-env <id> (e.g. --amiga-env wb32 --amiga-machine a1200-030). "
            "Build first with: scripts/amiga-env build <id> [--machine <machine_id>]"
        )

    # Check the binary the runner will actually launch: AMIBERRY_BIN may be an
    # absolute path (e.g. inside a macOS .app bundle) rather than a PATH entry.
    for command in (environment.get("AMIBERRY_BIN") or "amiberry", "socat"):
        if shutil.which(command, path=environment.get("PATH")) is None:
            missing.append(command)
    if not shutil.which("xdftool", path=environment.get("PATH")) and not shutil.which("uvx", path=environment.get("PATH")):
        missing.append("xdftool or uvx")
    if missing:
        pytest.skip("Amiga E2E prerequisites unavailable: " + ", ".join(missing))

    # Each case builds its declared artifact profile below.  Do not populate
    # the legacy build/amiga/bin tree as a session-level side effect.
    build_nio_binary(environment)
    return environment


@pytest.fixture(scope="session")
def amiga_cases() -> dict[str, dict]:
    return load_cases()


@pytest.fixture(scope="session")
def amiga_machine(pytestconfig: Any) -> dict[str, Any]:
    machine_id: str | None = pytestconfig.getoption("--amiga-machine")
    if machine_id:
        try:
            return _load_machine_profile_yaml(machine_id)
        except FileNotFoundError as exc:
            pytest.skip(str(exc))
    return dict(load_suite_config().get("amiberry", {}))


@pytest.fixture(scope="session")
def amiga_evidence_root() -> Path:
    configured = os.environ.get("AMIGA_E2E_EVIDENCE_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        root = DEFAULT_EVIDENCE_DIR / f"amiberry-{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# IPC helpers — call Amiberry directly without spawning a subprocess
# ---------------------------------------------------------------------------

def _ipc_screenshot(sock: Path, output: Path) -> bool:
    """Take a screenshot via Amiberry IPC. Returns True on success."""
    try:
        _amiberry_ipc.request(sock, "SCREENSHOT", str(output), timeout=3.0)
        return output.is_file()
    except Exception:
        return False


def _ipc_quit(sock: Path) -> bool:
    """Send QUIT to Amiberry. Returns True if accepted."""
    try:
        _amiberry_ipc.request(sock, "QUIT", timeout=3.0)
        return True
    except Exception:
        return False


def _ipc_insert_floppy(sock: Path, adf_path: Path, drive: int = 0) -> bool:
    """Insert an ADF into Amiberry drive N via IPC. Returns True on success."""
    try:
        _amiberry_ipc.request(sock, "INSERTFLOPPY", str(adf_path), str(drive), timeout=3.0)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Screenshot analysis (Pillow-based, gracefully degraded if unavailable)
# ---------------------------------------------------------------------------

def _has_amiga_content(screenshot: Path) -> bool:
    """Return True only when the screenshot shows real Amiga display content.

    Amiberry starts with a uniform black or dark-grey framebuffer before the
    Amiga display is initialized. Real Amiga output can still be mostly flat
    grey, for example an empty Workbench screen with only a title bar, so a
    whole-frame variance threshold is too strict and causes false negatives.

    Treat the frame as valid Amiga content when it is not near-uniform and it
    includes a visible number of non-background pixels.
    """
    if not _PILLOW or not screenshot.is_file():
        return False
    try:
        img = _PILImage.open(screenshot).convert("L")
        pixels = list(img.getdata())  # type: ignore[attr-defined]
        if not pixels:
            return False

        lo = min(pixels)
        hi = max(pixels)
        if (hi - lo) < 8:
            return False

        # Count pixels that are clearly away from the dominant mid-grey or
        # black background. Text, borders, and icons provide enough signal even
        # on a mostly empty Workbench screen.
        foreground = sum(1 for p in pixels if p <= 64 or p >= 224)
        return foreground >= 100
    except Exception:
        return False


def _screenshots_differ(path1: Path | None, path2: Path) -> bool:
    """Return True if the two screenshots are visually different.

    Falls back to True (always-changed) when Pillow is unavailable or either
    file is missing, which keeps the harness functioning without the library.
    """
    if not _PILLOW or path1 is None or not path1.is_file() or not path2.is_file():
        return True
    try:
        img1 = _PILImage.open(path1).convert("RGB")
        img2 = _PILImage.open(path2).convert("RGB")
        if img1.size != img2.size:
            return True
        changed = sum(
            1 for p1, p2 in zip(img1.getdata(), img2.getdata())
            if abs(p1[0] - p2[0]) > 8 or abs(p1[1] - p2[1]) > 8 or abs(p1[2] - p2[2]) > 8
        )
        # Require at least 100 differing pixels to count as changed.
        return changed >= 100
    except Exception:
        return True


def _has_requester(screenshot: Path) -> bool:
    """Detect an AmigaOS system requester in the top-left corner of the screen.

    AmigaOS dialog requesters have a PURE WHITE (255, 255, 255) interior body.
    Normal Workbench and CLI backgrounds are grey (~170, 170, 170) and contain
    no pure-white pixels in the dialog interior region.

    We check an interior rectangle offset from the very top-left (where border
    decorations live) to avoid false positives from window shine/highlight pixels
    that appear in both requester and non-requester states.

    Signal: pure-white pixel fraction in the dialog interior region (x=85..250, y=60..150).
      - Normal Workbench / CLI:  0.000
      - Requester present:       ~0.105
    Threshold of 0.05 validated against all collected test-evidence runs.

    Returns False gracefully when Pillow is unavailable.
    """
    if not _PILLOW or not screenshot.is_file():
        return False
    try:
        img = _PILImage.open(screenshot).convert("RGB")
        w, h = img.size
        # Dialog interior: fixed pixel region where requester body appears.
        # Scaled to 75% of reference 752x576 to handle minor size variation.
        x0, y0 = max(0, 85), max(0, 60)
        x1, y1 = min(w, 250), min(h, 150)
        if x1 <= x0 or y1 <= y0:
            return False
        region = img.crop((x0, y0, x1, y1))
        pixels = list(region.getdata())
        if not pixels:
            return False
        white = sum(1 for r, g, b in pixels if r == 255 and g == 255 and b == 255)
        return (white / len(pixels)) > 0.05
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Port / process cleanup
# ---------------------------------------------------------------------------

def _kill_port_holders(port: int) -> None:
    """Kill any process currently listening on *port* so the next test can bind it."""
    try:
        result = subprocess.run(
            ["lsof", "-t", "-i", f"TCP:{port}", "-s", "TCP:LISTEN"],
            capture_output=True,
            text=True,
        )
        for pid_str in result.stdout.split():
            try:
                os.kill(int(pid_str), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
    except FileNotFoundError:
        pass  # lsof not available


def _stop_process(proc: subprocess.Popen[object] | None,
                  timeout: float = 5) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _terminate_runner(runner: subprocess.Popen[object]) -> None:
    """Shut down the runner process, escalating to SIGKILL if needed."""
    _stop_process(runner, timeout=8)


# ---------------------------------------------------------------------------
# Main test fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def run_amiga_case(amiga_environment: dict[str, str],
                   amiga_cases: dict[str, dict],
                   amiga_machine: dict[str, Any],
    amiga_evidence_root: Path) -> Any:
    def run(name: str, *, installation: str | None = None) -> dict[str, str]:
        active_environment = amiga_environment.get("AMIGA_ENV_ID")
        case = resolve_case_for_environment(name, amiga_cases[name], active_environment)
        if installation not in {None, "serial", "native"}:
            raise ValueError(f"Unknown installation: {installation}")
        if installation == "native":
            case["nio_native_test"] = True
        elif installation == "serial":
            case["nio_native_test"] = False
        ordered_results = list(case.get("results", []))
        completion_mode = case.get("completion_mode")
        completion_log = case.get("completion_log")
        if completion_mode not in {"nio_marker", "expected_timeout", "host_file"}:
            raise AssertionError(
                f"Amiberry case '{name}' has invalid completion_mode: {completion_mode!r}"
            )
        if completion_mode in {"nio_marker", "host_file"} and not completion_log:
            raise AssertionError(
                f"Amiberry case '{name}' uses {completion_mode} but has no completion_log"
            )
        if completion_mode == "expected_timeout" and completion_log:
            raise AssertionError(
                f"Amiberry case '{name}' uses expected_timeout but declares completion_log"
            )
        native_disk = bool(case.get("native_disk_fixture"))
        ordinary_disk = bool(case.get("ordinary_disk_fixture"))
        broker_disk = native_disk or ordinary_disk
        if native_disk and not (case.get("nio_broker") and case.get("nio_native_test") and case.get("driver")):
            raise AssertionError("native_disk_fixture requires native broker and driver")
        if case.get("nio_broker") and case.get("driver") and not broker_disk:
            raise AssertionError(
                f"Amiberry case '{name}' sets nio_broker and driver; "
                "isolated broker images must not install fujinet-disk.device"
            )
        if completion_mode == "host_file" and not case.get("nio_native_test"):
            raise AssertionError(
                f"Amiberry case '{name}' uses host_file without nio_native_test"
            )
        if case.get("nio_native_test") and case.get("fujinet_serial"):
            raise AssertionError(
                f"Amiberry case '{name}' sets nio_native_test and fujinet_serial"
            )
        artifact_profile = case.get("amiga_artifact_profile")
        core_tools = case.get("core_tools", [])
        if artifact_profile is not None:
            if not isinstance(artifact_profile, str) or not artifact_profile:
                raise AssertionError(
                    f"Amiberry case '{name}' has invalid amiga_artifact_profile: "
                    f"{artifact_profile!r}"
                )
            subprocess.run(
                [str(ROOT / "scripts/amiga-artifacts"), artifact_profile],
                cwd=ROOT, env=amiga_environment, check=True,
            )
        if core_tools and artifact_profile is None:
            raise AssertionError(
                f"Amiberry case '{name}' uses core_tools without amiga_artifact_profile"
            )
        driver_root = ROOT / "repos/fujinet-nio-driver"
        driver_build_dir = driver_root / "build/amiga"
        if artifact_profile:
            driver_build_dir /= artifact_profile
        nio_device = driver_build_dir / "fujinet-nio.device"
        if case.get("nio_native_test"):
            nio_device = driver_build_dir / "fujinet-nio-native-test.device"
        resident_loader = driver_build_dir / "fujinet-load-resident"
        resident_unloader: Path | None = driver_build_dir / "fujinet-unload-resident"
        # fujinet-unload-resident uses newer DOS node-removal support and is
        # deliberately not a WB1.3 artefact.  Passing a stale binary from a
        # previous build would make the guest plan non-reproducible.
        if artifact_profile == "wb13":
            resident_unloader = None
        if case.get("nio_broker"):
            build_dir_rel = "../build/amiga"
            make_args = ["make"]
            if artifact_profile:
                build_dir_rel += f"/{artifact_profile}"
                make_args.append(f"BUILD_DIR={build_dir_rel}")
            make_args.append(
                f"AMIGA_WB13={1 if artifact_profile == 'wb13' else 0}"
            )
            make_args.append(
                f"NIO_TEST_CRT={'nix13' if artifact_profile == 'wb13' else 'clib2'}"
            )
            make_args.extend([
                f"{build_dir_rel}/fujinet-nio.device",
                f"{build_dir_rel}/fujinet-load-resident",
                f"{build_dir_rel}/{case['app']}",
            ])
            if case.get("nio_native_test"):
                make_args.append(f"{build_dir_rel}/fujinet-nio-native-test.device")
            if case.get("fujinet_serial"):
                make_args.append(f"{build_dir_rel}/fujinet-serial.device")
            if resident_unloader is not None:
                make_args.append(f"{build_dir_rel}/fujinet-unload-resident")
            subprocess.run(
                make_args,
                cwd=driver_root / "amiga",
                env=amiga_environment,
                check=True,
            )
            app = driver_build_dir / case["app"]
        else:
            app_dir = ROOT / "repos" / {
                "apps": "nio-apps",
                "config": "nio-config",
            }.get(case["project"], "nio-core-apps") / "build" / "amiga"
            if artifact_profile:
                app_dir /= artifact_profile
            app_dir /= "bin"
            app = app_dir / case["app"]
            if case.get("nio_native_test"):
                # scripts/amiga-artifacts builds only release devices; without
                # this the case would use whatever native-test device a broker
                # case last left in this profile, or fail if none has run yet.
                build_dir_rel = "../build/amiga"
                if artifact_profile:
                    build_dir_rel += f"/{artifact_profile}"
                subprocess.run(
                    ["make", f"BUILD_DIR={build_dir_rel}",
                     f"AMIGA_WB13={1 if artifact_profile == 'wb13' else 0}",
                     f"{build_dir_rel}/fujinet-nio-native-test.device"],
                    cwd=driver_root / "amiga",
                    env=amiga_environment,
                    check=True,
                )
        if not app.is_file():
            raise AssertionError(f"Amiga test application was not built: {app}")

        run_dir = amiga_evidence_root / (f"{name}-{installation}" if installation else name)
        run_dir.mkdir(parents=True, exist_ok=True)
        readonly_catalog_dir = None
        if case.get("nio_native_test"):
            shutil.rmtree(run_dir / "native-test-records", ignore_errors=True)
        host_root = (run_dir / "native-test-records" / "host-fs"
                     if case.get("nio_native_test") else run_dir / "fujinet-data")
        stale_catalog_dir = host_root / "FujiNet" / "app-store" / "v1" / "config-nio"
        if stale_catalog_dir.is_dir():
            stale_catalog_dir.chmod(0o755)
        shutil.rmtree(host_root, ignore_errors=True)
        host_root.mkdir(parents=True, exist_ok=True)
        if completion_mode == "nio_marker":
            (host_root / "amiga-e2e-complete" / name).mkdir(parents=True, exist_ok=True)
        if case.get("big_dir"):
            # More entries than config-nio's table holds, with a directory that
            # sorts last by name but must be listed first.
            big = host_root / "big"
            (big / "zdir").mkdir(parents=True, exist_ok=True)
            for n in range(300):
                (big / f"f{n:03d}.txt").write_text("x")
        if case.get("driver") and not case.get("nio_broker"):
            # scripts/amiga-artifacts above has already built this case's
            # profile.  Rebuilding the driver's historical generic output
            # here would make the test depend on a last-built artefact.
            create_standard_adf(amiga_environment, host_root / "standard.adf")
            create_standard_adf(amiga_environment, host_root / "second.adf",
                                "SECOND.TXT", "FUJINET SECOND DRIVE PASSED\n")
            create_standard_adf(amiga_environment, host_root / "writable.adf",
                                "BASE.TXT", "FUJINET WRITABLE BASE\n", "NIOWRITABLE")
            create_standard_adf(amiga_environment, host_root / "writable-second.adf",
                                "BASE2.TXT", "FUJINET SECOND WRITABLE BASE\n",
                                "NIOWRITABLE2")
            create_hd_adf(amiga_environment, host_root / "hd.adf")
            create_hd_adf(amiga_environment, host_root / "hd-second.adf",
                          "SECONDHD.TXT", "FUJINET SECOND HD PASSED\n")
            create_hd_adf(amiga_environment, host_root / "hd-writable.adf",
                          "BASEHD.TXT", "FUJINET WRITABLE HD BASE\n")
            if case.get("default_disk"):
                boot_dir = host_root / "boot"
                boot_dir.mkdir(exist_ok=True)
                create_ffs_adf(amiga_environment, boot_dir / "default.adf",
                               "DEFAULT.TXT", "FUJINET DEFAULT DISK PASSED\n",
                               "FNDEFAULT")
            if case.get("hd_ffs_adf"):
                create_hd_ffs_adf(amiga_environment,
                                  host_root / "hd-ffs-writable.adf")
            if case.get("inhibit_poc"):
                create_standard_adf(amiga_environment, host_root / "inhibit-a.adf",
                                    "KNOWN.TXT", "INHIBIT VOLUME A\n", "INHIBIT_A")
                create_standard_adf(amiga_environment, host_root / "inhibit-b.adf",
                                    "KNOWN.TXT", "INHIBIT VOLUME B\n", "INHIBIT_B")
            catalog_dir = host_root / "FujiNet" / "app-store" / "v1" / "config-nio"
            catalog_dir.mkdir(parents=True, exist_ok=True)
            (catalog_dir / "slot-011.bin").write_bytes(b"\x01\x01host:/standard.adf")
            (catalog_dir / "slot-012.bin").write_bytes(b"\x01\x01host:/second.adf")
            (catalog_dir / "slot-013.bin").write_bytes(b"\x01\x00host:/writable.adf")
            (catalog_dir / "slot-020.bin").write_bytes(
                b"\x01\x00host:/writable-second.adf"
            )
            (catalog_dir / "slot-014.bin").write_bytes(b"\x01\x01host:/hd.adf")
            (catalog_dir / "slot-017.bin").write_bytes(b"\x01\x01host:/hd-second.adf")
            (catalog_dir / "slot-018.bin").write_bytes(b"\x01\x00host:/hd-writable.adf")
            if case.get("restore_invalid_mapping"):
                (catalog_dir / "mappings.bin").write_bytes(
                    b"\x01\x03\x63" + b"\x00" * 14
                )
            if case.get("ffs_adf"):
                create_ffs_adf(amiga_environment, host_root / "ffs.adf")
                (catalog_dir / "slot-019.bin").write_bytes(b"\x01\x01host:/ffs.adf")
            if case.get("inhibit_poc"):
                (catalog_dir / "slot-015.bin").write_bytes(b"\x01\x01host:/inhibit-a.adf")
                (catalog_dir / "slot-016.bin").write_bytes(b"\x01\x01host:/inhibit-b.adf")
            if case.get("mapping_readonly"):
                catalog_dir.chmod(0o555)
                readonly_catalog_dir = catalog_dir
        elif not case.get("nio_broker"):
            subprocess.run(
                ["make", "native"],
                cwd=driver_root / "amiga",
                env=amiga_environment,
                check=True,
            )

        if broker_disk:
            native_host = host_root
            native_host.mkdir(exist_ok=True)
            # Originals stay outside the service's host root.
            for fixture in (("fault", "resident") if case.get("native_fault") else ("read", "write", "bounds")):
                original = run_dir / f"{fixture}-original.adf"
                create_standard_adf(amiga_environment, original,
                                    volume_name=f"NIO{fixture.upper()}")
                # Seed the tested sector independently; keep a valid ADF header.
                seeded = bytearray(original.read_bytes())
                seeded[17 * 512:18 * 512] = bytes((i * 7 + 31) & 255 for i in range(512))
                original.write_bytes(seeded)
                shutil.copyfile(original, native_host / f"{fixture}.adf")
        if case.get("tool_parity"):
            (host_root / "listing").mkdir()
            (host_root / "listing/parity.txt").write_bytes(b"parity\n")

        image = run_dir / f"amiga-{name}.hdf"
        startup = SUITE / case["startup"]
        if case.get("tool_parity"):
            text = startup.read_text().replace("@INSTALLATION@", installation or "serial")
            startup = run_dir / "tool-parity.sequence"
            startup.write_text(text)
        base_hdf = amiga_environment["AMIGA_ENV_BASE_HDF"]
        build_cmd = [
            str(ROOT / "scripts/build-amiga-test-disk"),
            "--base-hdf", base_hdf,
            "--app", app,
            "--app-name", case["app"],
            "--startup-script", startup,
            "--no-workbench",
            "--output", image,
        ]
        if case.get("startup_target"):
            build_cmd.extend(["--startup-target", case["startup_target"]])
        if not case.get("nio_broker"):
            if not artifact_profile:
                raise AssertionError(
                    f"Amiberry case '{name}' needs an amiga_artifact_profile for guest tools"
                )
            core_app_dir = ROOT / "repos/nio-core-apps/build/amiga"
            core_app_dir /= artifact_profile
            core_app_dir /= "bin"
            build_cmd.extend([
                "--extra-app-dir", ROOT / "repos/nio-apps/build/amiga" /
                artifact_profile / "bin",
                "--extra-app-dir", core_app_dir,
            ])
        if case.get("nio_broker"):
            build_cmd.extend([
                "--nio-device", nio_device,
                "--resident-loader", resident_loader,
            ])
            if resident_unloader is not None:
                build_cmd.extend(["--resident-unloader", resident_unloader])
            if broker_disk:
                build_cmd.extend(["--devs-file", driver_build_dir / "fujinet-disk.device"])
            if case.get("fujinet_serial"):
                serial_device = driver_build_dir / "fujinet-serial.device"
                if not serial_device.is_file():
                    raise AssertionError(
                        f"Amiga Paula serial device was not built: {serial_device}"
                    )
                build_cmd.extend(["--devs-file", serial_device])
        else:
            build_cmd.extend([
                "--nio-device", nio_device,
                "--resident-loader", resident_loader,
            ])
            if resident_unloader is not None:
                build_cmd.extend(["--resident-unloader", resident_unloader])
            if not case.get("defer_nio_load"):
                build_cmd.append("--load-nio")
        if case.get("driver") and not case.get("nio_broker"):
            build_cmd.extend([
                "--disk-device", driver_build_dir / "fujinet-disk.device",
                "--disk-mount-tool", driver_build_dir / "fujinet-mount",
            ])
            if not case.get("no_static_mountlists"):
                for unit in range(8):
                    build_cmd.extend(["--disk-mountlist", driver_root / f"amiga/config/DN{unit}"])
                build_cmd.extend(["--disk-mountlist", driver_root / "amiga/config/DN0HD"])
            if case.get("wb13_mountlist"):
                mountlist_source = case.get(
                    "wb13_mountlist_source",
                    ROOT / "configs/amiga/install/MountList-FujiNet-WB13",
                )
                if not isinstance(mountlist_source, Path):
                    mountlist_source = ROOT / str(mountlist_source)
                if not mountlist_source.is_file():
                    raise AssertionError(
                        f"Amiberry case '{name}' has no WB1.3 MountList: "
                        f"{mountlist_source}"
                    )
                build_cmd.extend([
                    "--disk-mountlist-target",
                    mountlist_source,
                    "Devs/MountList",
                ])
        for tool in case.get("driver_tools", []):
            if not isinstance(tool, str):
                raise AssertionError(
                    f"Amiberry case '{name}' has invalid driver_tools entry: {tool!r}"
                )
            tool_path = driver_build_dir / tool
            if not tool_path.is_file():
                raise AssertionError(f"Amiga driver tool was not built: {tool_path}")
            build_cmd.extend(["--extra-app-file", tool_path])
        for tool in core_tools:
            if not isinstance(tool, str):
                raise AssertionError(
                    f"Amiberry case '{name}' has invalid core_tools entry: {tool!r}"
                )
            tool_path = (ROOT / "repos/nio-core-apps/build/amiga" /
                         artifact_profile / "bin" / tool)
            if not tool_path.is_file():
                raise AssertionError(f"Amiga core tool was not built: {tool_path}")
        subprocess.run(build_cmd, cwd=ROOT, env=amiga_environment, check=True)

        native_adf: Path | None = None
        if case.get("native_floppy"):
            native_adf = run_dir / "native-floppy.adf"
            create_standard_adf(amiga_environment, native_adf)

        test_env = amiga_environment.copy()
        test_env["AMIGA_RUN_DIR"] = str(run_dir)
        case_index = list(amiga_cases).index(name)
        test_env["FUJINET_NIO_PORT"] = str(64000 + case_index)
        test_env["AMIBERRY_PORT"] = str(23470 + case_index)
        if case.get("default_disk"):
            test_env["AMIBERRY_NIO_BOOT_URI"] = "persist:/boot/default.adf"
        test_env.update(machine_environment(amiga_machine))

        # Timing parameters — screen-quiet is for screenshot/evidence cadence only.
        screenshot_quiet = float(case.get("screenshot_quiet", 15))
        activity_timeout = float(case.get("activity_timeout", test_env.get("AMIGA_E2E_ACTIVITY_TIMEOUT", "30")))
        debugger_mode = test_env.get("AMIGA_E2E_DEBUGGER", "0") == "1"
        capture_mode = test_env.get("AMIGA_E2E_CHECKPOINT_BEGINIO_CAPTURE", "0") == "1"
        screenshot_interval = float(case.get("screenshot_interval", 1.0))
        external_activity_evidence = bool(case.get("silent_peer") or case.get("native_floppy"))
        # How long after boot with NO screen movement before giving up.
        no_activity_timeout = float(case.get("no_activity_timeout", 20))
        runner_timeout = str(
            3600 if (debugger_mode or capture_mode) else
            case.get("timeout", os.environ.get("AMIGA_E2E_TIMEOUT", "20"))
        )

        # Kill any stale processes left from a prior crashed run of THIS test
        # by checking the specific ports this test uses.  We do NOT pkill by
        # process name — that would also kill instances the user started
        # independently for other purposes.
        _kill_port_holders(int(test_env["FUJINET_NIO_PORT"]))
        _kill_port_holders(int(test_env["AMIBERRY_PORT"]))
        for stale_name in (
            "amiberry.sock.path", "amiberry-screen.png",
            "amiberry.log", "fujinet-nio.log", "bridge.log",
        ):
            (run_dir / stale_name).unlink(missing_ok=True)

        native_record_dir: Path | None = None
        native_test_proc = None
        if case.get("nio_native_test"):
            native_runner = build_native_test_runner(amiga_environment)
            native_record_dir = run_dir / "native-test-records"
            native_record_dir.mkdir(parents=True, exist_ok=True)
            native_log = run_dir / "fujinet-nio-native-test.log"
            native_test_proc = subprocess.Popen(
                [str(native_runner), "--dir", str(native_record_dir)],
                cwd=ROOT,
                env=amiga_environment,
                stdout=native_log.open("w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
            )
            identity = native_record_dir / "IDENTITY"
            identity_deadline = time.monotonic() + 10
            while time.monotonic() < identity_deadline:
                if identity.is_file() and identity.read_text(encoding="ascii", errors="ignore") == "native-test\n":
                    break
                if native_test_proc.poll() is not None:
                    native_test_proc = None
                    raise AssertionError(
                        "fujinet-nio-native-test exited before writing IDENTITY"
                    )
                time.sleep(0.1)
            else:
                _stop_process(native_test_proc)
                native_test_proc = None
                raise AssertionError(
                    "fujinet-nio-native-test did not write IDENTITY as native-test"
                )
            test_env["AMIBERRY_SKIP_NIO"] = "1"
            test_env["AMIBERRY_DIR_MOUNTS"] = filesystem2_setting({
                "writable": True,
                "device": "DH1",
                "volume": "NATIVE",
                "path": str(native_record_dir),
                "bootpri": 0,
            })

        silent_peer = None
        if case.get("silent_peer"):
            silent_peer = subprocess.Popen(
                [sys.executable, "-c",
                 "import socket, sys, time; "
                 "s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); "
                 "s.bind(('127.0.0.1', int(sys.argv[1]))); s.listen(1); "
                 "c, _ = s.accept(); c.sendall(b'\\xc0'); time.sleep(120)",
                 test_env["FUJINET_NIO_PORT"]],
                cwd=ROOT,
                env=test_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        runner_args = [str(ROOT / "scripts/run-amiberry-nio"), "--tcp", "--disk", str(image),
                       "--timeout", runner_timeout]
        if case.get("silent_peer"):
            runner_args.append("--external-nio")
        runner = subprocess.Popen(runner_args, cwd=ROOT, env=test_env)

        ipc_sock: Path | None = None
        quit_sent = False
        requester_seen = False
        termination_reason: str | None = None
        recent_activity = False
        runner_returncode: int | None = None
        first_run_results: dict[str, str] = {}

        try:
            # ---------------------------------------------------------------
            # Phase 1: Wait for Amiberry to boot and expose its IPC socket.
            # ---------------------------------------------------------------
            socket_file = run_dir / "amiberry.sock.path"
            boot_deadline = time.monotonic() + 30
            while time.monotonic() < boot_deadline:
                if runner.poll() is not None:
                    break
                if socket_file.is_file():
                    try:
                        ipc_sock = Path(socket_file.read_text(encoding="utf-8").strip())
                    except OSError:
                        pass
                    if ipc_sock:
                        break
                time.sleep(0.1)

            if ipc_sock is None:
                raise AssertionError(
                    "Amiberry did not start or did not create an IPC socket within 30 s"
                )

            # For native-floppy tests: insert the ADF now that Amiberry is
            # running.  Kickstart will already be booting from DH0: (no floppy
            # was pre-mounted), so inserting here is safe.  The startup
            # sequence contains a Wait to give AmigaDOS time to mount DF0:.
            if native_adf is not None:
                time.sleep(2.0)  # let Kickstart fully hand off to AmigaDOS
                _ipc_insert_floppy(ipc_sock, native_adf, drive=0)

            # ---------------------------------------------------------------
            # Phase 2: Monitor loop.
            #
            # Primary completion signal: screen has not changed for
            # `screenshot_quiet` seconds (works whether or not NIO ran).
            # Secondary: NIO log watched for FujiBus activity evidence.
            # Fast-fail: if screen shows no movement at all for
            # `no_activity_timeout` s after boot, something is badly stuck.
            # ---------------------------------------------------------------
            nio_log = run_dir / ("fujinet-nio-native-test.log" if case.get("nio_native_test") else "fujinet-nio.log")
            shots_dir = run_dir / "screenshots"
            shots_dir.mkdir(exist_ok=True)
            monitor_trace = run_dir / "completion-monitor.trace"
            monitor_trace.unlink(missing_ok=True)

            saw_activity = False
            last_activity_at: float | None = None
            last_nio_receive_count = 0
            last_serial_line_count = 0
            last_serial_activity_at: float | None = None
            last_nio_read_offset = 0
            completion_log_state = CompletionLogState()
            prev_shot: Path | None = None
            screen_quiet_since: float | None = None
            screen_ever_changed = False
            last_shot_at = 0.0
            shot_index = 0
            debugger_paused = False
            boot_time = time.monotonic()
            activity_deadline = boot_time + activity_timeout
            completion_seen = False
            host_file_pass_at: float | None = None
            if debugger_mode or capture_mode:
                # The external controller owns the session duration; retain the
                # normal deadline as a fallback after the controller finishes.
                activity_deadline = boot_time + max(activity_timeout, 3600)

            while time.monotonic() < activity_deadline:
                now = time.monotonic()

                # Host-side debugger work may intentionally pause the emulator
                # while resolving resident state or collecting a breakpoint
                # snapshot. Do not let the normal activity deadline terminate
                # that diagnostic session.
                if debugger_mode and ipc_sock is not None:
                    try:
                        status = _amiberry_ipc.request(ipc_sock, "GET_STATUS",
                                                       timeout=0.25)
                        debugger_paused = "Paused=true" in status
                        if debugger_paused:
                            activity_deadline = max(
                                activity_deadline, now + activity_timeout
                            )
                    except (OSError, RuntimeError):
                        pass

                # NIO log — check for any FujiBus traffic (evidence only).
                if native_test_proc is not None and native_test_proc.poll() is not None:
                    raise AssertionError(
                        "fujinet-nio-native-test exited during the guest run"
                    )

                if (completion_mode == "host_file" and native_record_dir is not None
                        and completion_log):
                    marker_path = native_record_dir / completion_log
                    if host_file_is_pass(marker_path):
                        if host_file_pass_at is None:
                            host_file_pass_at = now
                        elif now - host_file_pass_at >= 0.6:
                            completion_seen = True
                    else:
                        host_file_pass_at = None

                if nio_log.is_file():
                    try:
                        current_nio_log_size = nio_log.stat().st_size
                    except OSError:
                        current_nio_log_size = 0
                    nio_text = read_log_text(nio_log)
                    receive_count = nio_text.count("fujibus: receive:")
                    if receive_count:
                        saw_activity = True
                        if receive_count != last_nio_receive_count:
                            last_activity_at = now
                            last_nio_receive_count = receive_count
                    if completion_mode == "nio_marker":
                        chunk = nio_text[last_nio_read_offset:]
                        found_marker, completion_log_state = scan_completion_log_chunk(
                            chunk, completion_log, completion_log_state
                        )
                        if found_marker:
                            completion_seen = True
                    new_bytes = max(0, current_nio_log_size - last_nio_read_offset)
                    new_lines = nio_text[last_nio_read_offset:].count("\n") if last_nio_read_offset <= len(nio_text) else 0
                    append_monitor_trace(
                        monitor_trace,
                        f"t={now:.3f} size={current_nio_log_size} offset={last_nio_read_offset} new_bytes={new_bytes} new_lines={new_lines} marker_found={'yes' if completion_seen else 'no'}"
                    )
                    last_nio_read_offset = len(nio_text)
                else:
                    append_monitor_trace(
                        monitor_trace,
                        f"t={now:.3f} size=0 offset={last_nio_read_offset} new_bytes=0 new_lines=0 marker_found={'yes' if completion_seen else 'no'}"
                    )

                amiberry_log_text = read_log_text(run_dir / "amiberry.log")
                serial_line_count = amiberry_log_text.count("SERIAL:")
                if serial_line_count != last_serial_line_count:
                    last_serial_activity_at = now
                    last_serial_line_count = serial_line_count

                runner_returncode = runner.poll()

                # Periodic screenshot.
                if now - last_shot_at >= screenshot_interval:
                    shot = shots_dir / f"{shot_index:04d}.png"
                    last_shot_at = now
                    shot_index += 1
                    _ipc_screenshot(ipc_sock, shot)

                    if shot.is_file():
                        # Requester detection — save evidence; in capture mode,
                        # continue running so the diagnostic controller can finish.
                        if _has_requester(shot):
                            requester_seen = True
                            shutil.copy2(shot, run_dir / "amiberry-screen.png")
                            requester_hold = float(
                                test_env.get("AMIGA_E2E_REQUESTER_HOLD", "0")
                            )
                            if requester_hold > 0:
                                time.sleep(requester_hold)
                                _ipc_screenshot(
                                    ipc_sock, run_dir / "amiberry-requester-held.png"
                                )
                            if not capture_mode:
                                termination_reason = "requester"
                                break

                        # Screen-change detection.
                        # Only count a change as meaningful when the screenshot
                        # shows actual Amiga content (not the uniform dark-grey
                        # uninitialized framebuffer Amiberry shows before the
                        # Amiga OS sets up its display mode).
                        if _screenshots_differ(prev_shot, shot) and _has_amiga_content(shot):
                            screen_ever_changed = True
                            screen_quiet_since = None
                        elif screen_ever_changed:
                            if screen_quiet_since is None:
                                screen_quiet_since = now
                        prev_shot = shot

                action, reason = evaluate_monitor_state(MonitorSnapshot(
                    completion_seen=completion_seen,
                    requester_seen=requester_seen,
                    runner_returncode=runner_returncode,
                    now=now,
                    deadline=activity_deadline,
                    debugger_mode=debugger_mode,
                    debugger_paused=debugger_paused,
                    capture_mode=capture_mode,
                    guest_reset_seen=guest_reset_from_amiberry_log(
                        amiberry_log_text
                    ),
                ))
                if action == "success":
                    # The host-side completion marker is emitted by the
                    # final NIO reply, a few guest instructions before the
                    # redirected CLI tool closes its result file.  Give DOS
                    # that bounded interval before IPC quits Amiberry; on
                    # WB3.2 an immediate quit can leave an FFS file chain
                    # visible but not yet complete to xdf.
                    settle = float(case.get("completion_settle", 1.0))
                    if settle > 0:
                        time.sleep(settle)
                    termination_reason = reason
                    break
                if action == "failure":
                    if reason == "timeout" and completion_mode == "expected_timeout":
                        termination_reason = "expected_timeout"
                        break
                    termination_reason = reason
                    break

                time.sleep(0.2)

            if termination_reason is None:
                termination_reason = (
                    "expected_timeout" if completion_mode == "expected_timeout" else "timeout"
                )

            # Promote the most recent screenshot to the canonical evidence file.
            if prev_shot and prev_shot.is_file():
                shutil.copy2(prev_shot, run_dir / "amiberry-screen.png")
            elif shot_index > 0:
                # Look for the last shot that was actually created.
                for i in range(shot_index - 1, -1, -1):
                    candidate = shots_dir / f"{i:04d}.png"
                    if candidate.is_file():
                        shutil.copy2(candidate, run_dir / "amiberry-screen.png")
                        break

            recent_activity = any(
                stamp is not None and (time.monotonic() - stamp) <= 2.0
                for stamp in (last_activity_at, last_serial_activity_at)
            )

            # ---------------------------------------------------------------
            # Phase 3: Quit Amiberry cleanly, wait for runner.
            # ---------------------------------------------------------------
            if ipc_sock is not None and termination_reason == "timeout":
                _capture_debug_snapshot(ipc_sock, run_dir / "amiberry-timeout-debug.log")
            quit_sent = _ipc_quit(ipc_sock)
            runner_returncode = runner.wait(timeout=10)
            if (termination_reason == "completion_log" and runner_returncode and
                    not (quit_sent and runner_returncode == 250)):
                raise subprocess.CalledProcessError(runner_returncode, runner.args)

            if case.get("second_startup") and termination_reason == "completion_log":
                first_results = set(case.get("first_results", []))
                with tempfile.TemporaryDirectory(prefix="amiga-first-results-") as result_dir:
                    for result_name in first_results:
                        destination = Path(result_dir) / result_name.replace("/", "_")
                        subprocess.run(
                            [*xdf_command(test_env), str(image), "read", result_name, str(destination)],
                            cwd=ROOT, env=test_env, check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        )
                        first_run_results[result_name] = destination.read_text(encoding="latin-1")

                second_build_cmd = list(build_cmd)
                startup_index = second_build_cmd.index("--startup-script") + 1
                second_build_cmd[startup_index] = SUITE / case["second_startup"]
                subprocess.run(second_build_cmd, cwd=ROOT, env=amiga_environment, check=True)
                for stale_name in ("amiberry.sock.path", "amiberry.log", "fujinet-nio.log", "bridge.log"):
                    (run_dir / stale_name).unlink(missing_ok=True)
                second_log = run_dir / ("fujinet-nio-native-test.log" if case.get("nio_native_test") else "fujinet-nio.log")
                second_offset = len(read_log_text(second_log)) if case.get("nio_native_test") else 0
                second_runner = subprocess.Popen(runner_args, cwd=ROOT, env=test_env)
                second_deadline = time.monotonic() + activity_timeout
                second_marker = False
                second_monitor = SecondBootMonitor(second_offset)
                second_failure = None
                while time.monotonic() < second_deadline:
                    second_marker, second_failure = second_monitor.poll(
                        read_log_text(second_log), completion_log,
                        peer_exited=native_test_proc is not None and native_test_proc.poll() is not None,
                        guest_log=read_log_text(run_dir / "amiberry.log"),
                    )
                    if second_failure or second_marker:
                        break
                    if second_runner.poll() is not None:
                        break
                    time.sleep(0.2)
                second_socket_file = run_dir / "amiberry.sock.path"
                if second_socket_file.is_file():
                    second_socket = Path(second_socket_file.read_text(encoding="utf-8").strip())
                    _ipc_quit(second_socket)
                _terminate_runner(second_runner)
                if second_failure or not second_marker:
                    raise AssertionError(f"Amiberry second run failed: {second_failure or 'completion marker missing'}")

        finally:
            # Always ensure Amiberry and the runner are gone.
            if ipc_sock and not quit_sent:
                _ipc_quit(ipc_sock)
            _terminate_runner(runner)
            if silent_peer is not None and silent_peer.poll() is None:
                silent_peer.terminate()
                silent_peer.wait(timeout=5)
            _stop_process(native_test_proc)
            if readonly_catalog_dir is not None and readonly_catalog_dir.is_dir():
                readonly_catalog_dir.chmod(0o755)

        if termination_reason not in {"completion_log", "expected_timeout"}:
            if termination_reason == "timeout" and completion_mode == "nio_marker":
                termination_reason = "nio_marker_timeout"
            present_results = scan_ordered_results(test_env, image, ordered_results)
            runner_exit_state = (
                "not-started" if runner_returncode is None else
                ("ipc-quit-250" if quit_sent and runner_returncode == 250 else str(runner_returncode))
            )
            raise AssertionError(build_failure_report(
                case_name=name,
                termination_reason=termination_reason or "timeout",
                ordered_results=ordered_results,
                present_results=present_results,
                requester_seen=requester_seen,
                recent_activity=recent_activity,
                runner_exit_state=runner_exit_state,
            ))

        # -------------------------------------------------------------------
        # Collect result files from the HDF image.
        # -------------------------------------------------------------------
        results: dict[str, str] = {}
        with tempfile.TemporaryDirectory(prefix="amiga-results-") as result_dir:
            for result_name in ordered_results:
                if result_name in first_run_results:
                    results[result_name] = first_run_results[result_name]
                    continue
                destination = Path(result_dir) / result_name.replace("/", "_")
                subprocess.run(
                    [*xdf_command(test_env), str(image), "read", result_name, str(destination)],
                    cwd=ROOT,
                    env=test_env,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                results[result_name] = destination.read_text(encoding="latin-1")
        mappings = host_root / "FujiNet" / "app-store" / "v1" / "config-nio" / "mappings.bin"
        if mappings.is_file():
            results["_mappings"] = mappings.read_bytes().hex()
        return results

    return run
