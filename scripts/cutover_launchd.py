#!/usr/bin/env python3
"""Archive, unload, or restore legacy xsource launchd jobs.

Stdlib-only and paste-safe: run the script, choose a subcommand, and confirm
before any launchd mutation.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess

LABELS = (
    "care.clonway.xsource.watcher",
    "care.clonway.xsource.sync",
    "care.clonway.xsource.signals",
)


def print_command(command: list[str]) -> None:
    print("+ " + " ".join(command))


def run(command: list[str], *, dry_run: bool) -> None:
    print_command(command)
    if not dry_run:
        subprocess.run(command, check=True)


def uid() -> str:
    return subprocess.getoutput("id -u")


def plist_path(label: str) -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def archive_dir(path: str | None) -> pathlib.Path:
    if path:
        return pathlib.Path(path).expanduser()
    return pathlib.Path.home() / ".claude-inbox" / "xsource" / "launchd-archive"


def archive_plists(destination: pathlib.Path, *, dry_run: bool) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for label in LABELS:
        src = plist_path(label)
        dst = destination / src.name
        print(f"archive {src} -> {dst}")
        if src.exists() and not dry_run:
            shutil.copy2(src, dst)


def bootout(*, dry_run: bool) -> None:
    for label in LABELS:
        run(["launchctl", "bootout", f"gui/{uid()}", str(plist_path(label))], dry_run=dry_run)


def bootstrap(source: pathlib.Path, *, dry_run: bool) -> None:
    for label in LABELS:
        run(["launchctl", "bootstrap", f"gui/{uid()}", str(source / f"{label}.plist")], dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["archive", "bootout", "rollback"])
    parser.add_argument("--archive-dir", nargs="?", help="Archive directory; prompts default if omitted.")
    parser.add_argument("--apply", action="store_true", help="Run commands after printing them.")
    args = parser.parse_args()

    dry_run = not args.apply
    target = archive_dir(args.archive_dir)
    if args.apply:
        confirm = input(f"Apply {args.action} for xsource launchd jobs? Type APPLY: ").strip()
        if confirm != "APPLY":
            raise SystemExit("aborted")

    if args.action == "archive":
        archive_plists(target, dry_run=dry_run)
    elif args.action == "bootout":
        archive_plists(target, dry_run=dry_run)
        bootout(dry_run=dry_run)
    elif args.action == "rollback":
        bootstrap(target, dry_run=dry_run)


if __name__ == "__main__":
    main()
