"""Named Amiberry Workbench profiles."""

from __future__ import annotations

import json
import os
import shutil
import string
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - depends on host setup
    raise SystemExit(
        "Amiga Workbench profiles require PyYAML; install it with "
        "'python3 -m pip install PyYAML'"
    ) from exc


def _load_local_amiga_env(root: Path) -> dict[str, str]:
    """Load local/amiga.env key=value pairs without shell evaluation."""
    env_file = root / "local" / "amiga.env"
    result: dict[str, str] = {}
    if not env_file.is_file():
        return result
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            result[key.strip()] = value
    return result


def _expand(value: Any, root: Path, environment: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    variables = dict(os.environ)
    variables.setdefault("NIO_WORKSPACE", str(root))
    variables.update(environment)
    expanded = os.path.expanduser(string.Template(value).safe_substitute(variables))
    path = Path(expanded)
    if not path.is_absolute():
        path = root / path
    return str(path)


def resolve_fast_file_system(
    manifest: dict[str, Any],
    root: Path,
    environment: dict[str, str] | None = None,
) -> str | None:
    """Return the host FastFileSystem path for a built Amiga environment."""
    # Prefer the Amiberry runner module so every boot path shares one resolver.
    # build.sh may only put tools/build on PYTHONPATH; fall back to local logic.
    try:
        from amiga_emulator.ffs import resolve_fast_file_system as resolve_from_runner
    except ImportError:
        resolve_from_runner = None
    if resolve_from_runner is not None:
        return resolve_from_runner(root, environment=environment, manifest=manifest)

    recorded = manifest.get("fast_file_system")
    if recorded and Path(recorded).is_file():
        return str(Path(recorded).resolve())

    base_hdf = manifest.get("base_hdf")
    if base_hdf:
        sibling = Path(base_hdf).parent / "FastFileSystem"
        if sibling.is_file():
            return str(sibling.resolve())

    local_env = {**_load_local_amiga_env(root), **(environment or {})}
    expanded = local_env.get("AMIGA_WB32_EXPANDED", "")
    if expanded:
        for rel in ("L/FastFileSystem", "FastFileSystem"):
            candidate = Path(expanded).expanduser() / rel
            if candidate.is_file():
                return str(candidate.resolve())
    return None


def _load_env_manifest(root: Path, env_id: str, machine_id: str | None) -> dict[str, Any]:
    """Load build/amiga-envs/<env_id>[/<machine_id>]/manifest.json."""
    envs_root = root / "build" / "amiga-envs"
    if machine_id:
        machine_path = envs_root / env_id / machine_id / "manifest.json"
        agnostic_path = envs_root / env_id / "manifest.json"
        if machine_path.is_file():
            manifest_path = machine_path
        elif agnostic_path.is_file():
            manifest_path = agnostic_path
        else:
            raise SystemExit(
                f"AmigaOS environment '{env_id}/{machine_id}' has not been built.\n"
                f"Run: scripts/amiga-env build {env_id} --machine {machine_id}"
            )
    else:
        manifest_path = envs_root / env_id / "manifest.json"
        if not manifest_path.is_file():
            raise SystemExit(
                f"AmigaOS environment '{env_id}' has not been built.\n"
                f"Run: scripts/amiga-env build {env_id}"
            )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _load_machine_profile(root: Path, machine_id: str) -> dict[str, Any]:
    """Load configs/amiga/machines/<machine_id>.yaml."""
    machine_path = root / "configs" / "amiga" / "machines" / f"{machine_id}.yaml"
    if not machine_path.is_file():
        raise SystemExit(f"Machine profile not found: {machine_path}")
    with machine_path.open("r", encoding="utf-8") as fh:
        profile = yaml.safe_load(fh) or {}
    uae_config = profile.get("uae_config", "")
    if uae_config:
        resolved = (root / "configs" / "amiga" / uae_config).resolve()
        profile["uae_config"] = str(resolved)
    return profile


def _normalize_volume(name: str) -> str:
    volume = name.strip().rstrip(":")
    if not volume or ":" in volume or "/" in volume or "\\" in volume:
        raise SystemExit(
            f"Invalid Amiga share volume name {name!r}; use a simple label like NIO"
        )
    return volume


def resolve_profile_shares(
    document: dict[str, Any],
    profile: dict[str, Any],
    root: Path,
    environment: dict[str, str],
    *,
    profile_name: str,
) -> list[dict[str, Any]]:
    """Resolve named development shares selected by a workbench profile."""
    requested = profile.get("shares")
    if not requested:
        return []
    if isinstance(requested, str):
        requested = [requested]
    if not isinstance(requested, list):
        raise SystemExit(
            f"Amiga profile '{profile_name}' shares must be a list of share names"
        )

    catalog = document.get("shares", {})
    if catalog is None:
        catalog = {}
    if not isinstance(catalog, dict):
        raise SystemExit("Amiga workbench 'shares' must be a mapping of name → definition")

    resolved: list[dict[str, Any]] = []
    for entry in requested:
        if not isinstance(entry, str) or not entry.strip():
            raise SystemExit(
                f"Amiga profile '{profile_name}' shares entries must be share names"
            )
        share_name = entry.strip()
        definition = catalog.get(share_name)
        if not isinstance(definition, dict):
            available = ", ".join(sorted(str(key) for key in catalog)) or "(none)"
            raise SystemExit(
                f"Unknown development share '{share_name}' in profile '{profile_name}'. "
                f"Available: {available}"
            )
        path_value = definition.get("path")
        if not path_value:
            raise SystemExit(f"Development share '{share_name}' requires a path")
        volume = _normalize_volume(str(definition.get("volume", share_name)))
        writable = bool(definition.get("writable", False))
        sync = bool(definition.get("sync", True))
        bootpri = int(definition.get("bootpri", 0))
        device = definition.get("device")
        if device is not None:
            device = str(device).strip().rstrip(":")
            if not device or ":" in device:
                raise SystemExit(
                    f"Development share '{share_name}' device must be a simple "
                    f"unit name like DH1, not {definition.get('device')!r}"
                )
        host_path = Path(_expand(str(path_value), root, environment))
        resolved.append(
            {
                "name": share_name,
                "volume": volume,
                "path": str(host_path),
                "writable": writable,
                "sync": sync,
                "bootpri": bootpri,
                "device": device,
            }
        )
    # Assign DH1+ when device is omitted so DH0 stays free for the boot hardfile.
    next_unit = 1
    for share in resolved:
        if not share["device"]:
            share["device"] = f"DH{next_unit}"
            next_unit += 1
        else:
            if share["device"].upper().startswith("DH"):
                try:
                    next_unit = max(next_unit, int(share["device"][2:]) + 1)
                except ValueError:
                    pass
    return resolved


def filesystem2_setting(share: dict[str, Any]) -> str:
    """Return an Amiberry/UAE ``filesystem2=`` value for a resolved share.

    Format matches Amiberry GUI saves, e.g.::

        filesystem2=ro,DH1:NIO:/path/to/share,0
    """
    mode = "rw" if share.get("writable") else "ro"
    device = share["device"]
    volume = share["volume"]
    path = share["path"]
    bootpri = int(share.get("bootpri", 0))
    return f"{mode},{device}:{volume}:{path},{bootpri}"


def encode_dir_mounts(shares: list[dict[str, Any]]) -> str:
    """Encode resolved shares as semicolon-separated filesystem2 values."""
    return ";".join(filesystem2_setting(share) for share in shares)


def sync_development_share(root: Path, share_path: Path) -> list[str]:
    """Refresh a host share directory with current Amiga build artifacts.

    Uses symlinks when possible so the guest always sees the latest binaries
    without copying into the persistent Workbench HDF.
    """
    share_path.mkdir(parents=True, exist_ok=True)
    sources: list[Path] = []
    driver = root / "repos" / "fujinet-nio-driver" / "build" / "amiga"
    for name in (
        "fujinet-nio.device",
        "fujinet-disk.device",
        "fujinet-serial.device",
        "fujinet-load-resident",
        "fujinet-unload-resident",
        "fujinet-mount",
        "fujinet-nio-exchange",
        "fujinet-nio-baud",
        "fujinet-nio-serial",
    ):
        sources.append(driver / name)
    for bin_dir in (
        root / "repos" / "nio-core-apps" / "build" / "amiga" / "bin",
        root / "repos" / "nio-apps" / "build" / "amiga" / "bin",
    ):
        if bin_dir.is_dir():
            sources.extend(sorted(path for path in bin_dir.iterdir() if path.is_file()))
    bounce_bin = root / "repos" / "bounce-world-client-nio" / "build" / "bwcn.amiga"
    if bounce_bin.is_file():
        sources.append(bounce_bin)

    linked: list[str] = []
    for source in sources:
        if not source.is_file():
            continue
        target = share_path / source.name
        if target.is_symlink() or target.exists():
            target.unlink()
        try:
            target.symlink_to(source.resolve())
        except OSError:
            shutil.copy2(source, target)
        linked.append(source.name)
    return linked


def load_profile(path: Path, name: str, root: Path, environment: dict[str, str] | None = None) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    if not isinstance(document, dict):
        raise SystemExit(f"Amiga profile file must contain a mapping: {path}")

    profiles = document.get("profiles", {})
    if not isinstance(profiles, dict):
        raise SystemExit(f"Amiga profile 'profiles' must be a mapping: {path}")
    selected = name or str(document.get("default", "wb3.2"))
    profile = profiles.get(selected)
    if not isinstance(profile, dict):
        available = ", ".join(sorted(str(key) for key in profiles))
        raise SystemExit(f"Unknown Amiga Workbench profile '{selected}'; available: {available}")

    result = dict(profile)
    # Merge local/amiga.env so workbenches.yaml can reference variables like
    # ${AMIGA_WB32_KICKSTART} even when build.sh does not source env.sh first.
    local_env = _load_local_amiga_env(root)
    environment = {
        "NIO_WORKSPACE": str(root),
        **local_env,
        **(environment or {}),
    }

    # Resolve environment + machine references to a concrete disk and kickstart.
    env_id: str | None = result.pop("environment", None)
    machine_id: str | None = result.pop("machine", None)
    if env_id:
        manifest = _load_env_manifest(root, env_id, machine_id)
        result.setdefault("harddrive", manifest["base_hdf"])
        result.setdefault("kickstart", manifest["kickstart"])
        if manifest.get("rom_key"):
            result.setdefault("rom_key", manifest["rom_key"])
        fast_file_system = resolve_fast_file_system(manifest, root, environment)
        if fast_file_system:
            result.setdefault("fast_file_system", fast_file_system)
        result["_env_id"] = env_id
        result["_machine_id"] = machine_id
    if machine_id and not env_id:
        # machine without environment: just apply hardware settings
        machine_profile = _load_machine_profile(root, machine_id)
        result.setdefault("uae_config", machine_profile.get("uae_config", ""))
        if "settings" not in result:
            result["settings"] = machine_profile.get("settings", {})
        result["_machine_id"] = machine_id
    elif machine_id and env_id:
        machine_profile = _load_machine_profile(root, machine_id)
        result.setdefault("uae_config", machine_profile.get("uae_config", ""))
        if "settings" not in result:
            result["settings"] = machine_profile.get("settings", {})

    config_keys = [key for key in ("config_file", "uae_config") if key in result]
    if len(config_keys) > 1:
        raise SystemExit(
            f"Amiga profile must use only one of config_file/uae_config: {selected}"
        )
    if config_keys:
        result["uae_config"] = result.pop(config_keys[0])
    # rom_key is optional: a plain (non-Amiga Forever) ROM needs none, so a
    # reference to an unset or empty variable means "no key", not a path.
    rom_key = result.get("rom_key")
    if isinstance(rom_key, str):
        substituted = string.Template(rom_key).safe_substitute(
            {**os.environ, **environment}).strip()
        if not substituted or "$" in substituted:
            del result["rom_key"]
    for key in ("disk", "harddrive", "kickstart", "rom_key",
                "fast_file_system", "uae_config"):
        if key in result:
            result[key] = _expand(result[key], root, environment)
    archive_keys = [key for key in ("install_archives", "install_archive") if key in result]
    if len(archive_keys) > 1:
        raise SystemExit(
            f"Amiga profile must use only one of install_archives/install_archive: {selected}"
        )
    if archive_keys:
        archives = result.pop(archive_keys[0])
        if not isinstance(archives, list):
            raise SystemExit(f"Amiga profile archive list must be a list: {selected}")
        result["install_archives"] = [
            _expand(archive, root, environment) for archive in archives
        ]
    settings = result.get("settings", {})
    if not isinstance(settings, dict):
        raise SystemExit(f"Amiga profile settings must be a mapping: {selected}")
    result["settings"] = {str(key): str(value).lower() if isinstance(value, bool) else str(value)
                           for key, value in settings.items()}
    result["shares"] = resolve_profile_shares(
        document, result, root, environment, profile_name=selected
    )
    result["name"] = selected
    return result
