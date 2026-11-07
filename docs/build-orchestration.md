# Workspace build orchestration

The workspace build entry point is `scripts/build.sh`, a thin launcher for the
Python package under `tools/build/nio_build`. Normal use is organized around
platform workflows:

```sh
./scripts/build.sh bbc
./scripts/build.sh master
./scripts/build.sh msdos
./scripts/build.sh atari
./scripts/build.sh c64
./scripts/build.sh linux
./scripts/build.sh amiga
./scripts/build.sh all
```

Use `./scripts/build.sh --list` for the public workflows and common artifact
targets, `--list --all` for compatibility/internal targets, and
`--explain TARGET` to inspect a target before running it.

To rebuild and stage the Atari config boot disk for firmware flashing, run
`./scripts/build.sh atari-boot-disk`. This builds the Atari library, standard
and banked config applications, and the ATR, then installs it into the POSIX
and ESP32 firmware distfiles. It does not flash the device; use
`./build.sh -f` from `repos/fujinet-nio` when ready.

`./scripts/build.sh c64` builds the C64 library, config app and D64 boot disk,
installs the disk into the firmware distfiles, and builds the `c64-netiec-debug`
firmware that serves it to VICE. `all`, `lib` and `boot-disks` include the C64.
Running it in VICE is described in `integration-tests/c64-iec/README.md`.

## Target layers

| Layer | Examples | Purpose |
| --- | --- | --- |
| Platform workflow | `bbc`, `master`, `msdos`, `atari`, `c64`, `linux`, `amiga`, `all` | Normal daily builds with the platform's required dependencies and artifacts |
| Artifact workflow | `bbc-boot-disk`, `qemu-msdos-image`, `amiga-driver-sdk` | Build or diagnose one composed output |
| Repository task | Repo-local `make`/CMake invocation wrapped by Python | Internal orchestration and CI building blocks |

Prefer a platform workflow unless a focused artifact or test is the objective.
Compatibility aliases may appear under `--list --all`, but are not the public
interface for new scripts.

## Ownership

- A repository builds artifacts composed only from files it owns.
- The workspace orchestrates artifacts composed from multiple repositories.
- `fujinet-nio` consumes completed boot/config images from its `distfiles`;
  it does not own their source recipes.
- Emulator runners are workspace workflows, while emulator-specific image
  manipulation remains in the relevant emulator/tool repository.
- Every completed task records its outputs in `build/manifest.txt` through the
  shared manifest writer.

The main owners are:

- `nio-apps`: test/example applications and repo-local app disks;
- `nio-core-apps`: standard utilities and applicable utility boot disks;
- `nio-config`: configuration applications and platform-specific config
  stages;
- `fn-rom`: BBC/Master transient utilities and `FN-BOOT*.ssd`;
- workspace: cross-repository boot/config images, installation into
  `fujinet-nio` distfiles, and emulator/device-side workflows.

Current disk-image targets and ownership are documented in
[`disk-image-builds.md`](disk-image-builds.md). Remaining build-tool cleanup is
tracked in [`../backlog/disk-image-tooling-cleanup.md`](../backlog/disk-image-tooling-cleanup.md),
and optional planner/alias work in
[`../backlog/build-orchestration-followups.md`](../backlog/build-orchestration-followups.md).
