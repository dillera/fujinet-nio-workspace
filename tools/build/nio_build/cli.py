from __future__ import annotations

import sys

from .context import BuildContext
from .manifest import write_manifest
from .tasks import Build, Task, build_tasks


def print_usage(tasks: dict[str, Task], *, all_targets: bool = False) -> None:
    print("Usage: scripts/build.sh <target> [target...]")
    print()
    print("Workflow targets:")
    for task in tasks.values():
        if task.workflow:
            print(f"  {task.name:<16} {task.description}")
    print()
    print("Common artifact targets:")
    for task in tasks.values():
        if not task.workflow and not task.hidden:
            print(f"  {task.name:<24} {task.description}")
    if all_targets:
        print()
        print("Hidden/compatibility targets:")
        for task in tasks.values():
            if task.hidden:
                print(f"  {task.name:<24} {task.description}")
    print()
    print("Options:")
    print("  --list             List public targets")
    print("  --list --all       List all targets, including compatibility aliases")
    print("  --explain TARGET   Show what TARGET means")
    print()
    print("Environment overrides live in local/config.env.")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    ctx = BuildContext.create()
    build = Build(ctx)
    tasks = build_tasks(build)

    if args and args[0] in ("-h", "--help", "help"):
        print_usage(tasks, all_targets="--all" in args)
        return 0

    if not args:
        print_usage(tasks)
        return 1
    if args[0] == "--list":
        print_usage(tasks, all_targets="--all" in args[1:])
        return 0 if args else 1
    if args[0] == "--explain":
        if len(args) < 2:
            print("--explain needs a target", file=sys.stderr)
            return 1
        task = tasks.get(args[1])
        if task is None:
            print(f"Unknown target: {args[1]}", file=sys.stderr)
            return 1
        kind = "workflow" if task.workflow else "artifact/repo task"
        if task.hidden:
            kind = "hidden compatibility task"
        print(f"{task.name}: {kind}")
        print(task.description)
        if task.help_text is not None:
            print()
            print(task.help_text(build))
        elif task.consumes_args:
            print()
            print("This target accepts arguments after '--'. Run the delegated command with '--help' for details.")
        return 0

    targets = args
    while targets:
        target = targets.pop(0)
        task = tasks.get(target)
        if task is None:
            print(f"Unknown target: {target}", file=sys.stderr)
            print_usage(tasks)
            return 1
        if task.consumes_args:
            if target == "qemu-run":
                build.qemu_run(targets)
            elif target == "qemu-monitor":
                build.qemu_monitor(targets)
            elif target == "atari-run":
                build.atari_run(targets)
            elif target == "atari-boot-acceptance":
                build.atari_boot_acceptance(targets)
            elif target == "bbc-pty":
                build.run_bbc_pty_for_machine("bbc")
            elif target == "master-pty":
                build.run_bbc_pty_for_machine("master")
            elif target == "msdos-dev-curses":
                build.msdos_dev_curses()
            elif target == "atari-stop":
                build.atari_stop()
            elif target == "amiga-run":
                build.amiga_run(targets, build_adf=False)
            elif target == "amiga-e2e":
                build.amiga_run(targets, build_adf=True)
            elif target == "amiga-workbench":
                build.amiga_workbench(targets)
            elif target == "amiga-test-adf":
                build.amiga_test_adf(targets)
            elif target == "amiga-tests":
                build.amiga_tests(targets)
            return 0
        task.action(build)
        if target != "manifest":
            write_manifest(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
