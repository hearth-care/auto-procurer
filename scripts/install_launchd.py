#!/usr/bin/env python3
"""Install local launchd jobs for xsource.

Default is dry-run: print the plist paths and launchctl commands. Use
``--write`` to write plists, and ``--load`` to load them after confirmation.
"""

import argparse
import dataclasses
import pathlib
import plistlib
import subprocess


@dataclasses.dataclass(frozen=True)
class Job:
    label: str
    argv: list[str]
    start_interval: int | None = None
    start_calendar: dict[str, int] | None = None

    def plist(self) -> dict:
        data = {
            "Label": self.label,
            "ProgramArguments": self.argv,
            "WorkingDirectory": self.argv[2]
            if len(self.argv) > 2 and self.argv[1] == "--project"
            else str(pathlib.Path.home()),
            "RunAtLoad": False,
            "StandardOutPath": str(pathlib.Path.home() / f"Library/Logs/{self.label}.out.log"),
            "StandardErrorPath": str(pathlib.Path.home() / f"Library/Logs/{self.label}.err.log"),
        }
        if self.start_interval is not None:
            data["StartInterval"] = self.start_interval
        if self.start_calendar is not None:
            data["StartCalendarInterval"] = self.start_calendar
        return data


def jobs(project_dir: str) -> list[Job]:
    uv = "uv"
    return [
        Job(
            label="care.clonway.xsource.watcher",
            argv=[uv, "--project", project_dir, "run", "xsource", "watcher", "run"],
            start_interval=60,
        ),
        Job(
            label="care.clonway.xsource.sync",
            argv=[uv, "--project", project_dir, "run", "xsource", "request", "sync-all"],
            start_calendar={"Hour": 2, "Minute": 10},
        ),
        Job(
            label="care.clonway.xsource.signals",
            argv=[uv, "--project", project_dir, "run", "xsource", "signals", "scan"],
            start_calendar={"Hour": 7, "Minute": 5},
        ),
    ]


def _write(path: pathlib.Path, job: Job) -> None:
    print(f"write {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(job.plist()))


def _run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-dir",
        default="/Users/olliepage/Developer/Auto-Procurer",
        help="Auto-Procurer checkout to run.",
    )
    parser.add_argument(
        "--write", action="store_true", help="Write plists to ~/Library/LaunchAgents."
    )
    parser.add_argument(
        "--load", action="store_true", help="Load plists with launchctl after writing."
    )
    args = parser.parse_args()

    launch_agents = pathlib.Path.home() / "Library/LaunchAgents"
    for job in jobs(args.project_dir):
        path = launch_agents / f"{job.label}.plist"
        if args.write:
            _write(path, job)
        else:
            print(f"would write {path}")
        if args.load:
            answer = input(f"Load {job.label}? Type yes: ").strip().lower()
            if answer == "yes":
                _run(["launchctl", "bootstrap", f"gui/{subprocess.getoutput('id -u')}", str(path)])
            else:
                print(f"skip load {job.label}")


if __name__ == "__main__":
    main()
