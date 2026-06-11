#!/usr/bin/env python3
"""Install local launchd jobs for xsource (legacy/rollback-only).

Default is dry-run: print the plist paths and launchctl commands. Use
``--write`` to write plists, and ``--load`` to load them after confirmation.
"""

import argparse
import dataclasses
import pathlib
import plistlib
import shutil
import subprocess

_DIRECT_SECRET_KEYS = {"ANTHROPIC_API_KEY"}


@dataclasses.dataclass(frozen=True)
class Job:
    label: str
    argv: list[str]
    start_interval: int | None = None
    start_calendar: dict[str, int] | None = None
    environment: dict[str, str] | None = None

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
        if self.environment:
            data["EnvironmentVariables"] = self.environment
        return data


def jobs(
    project_dir: str,
    *,
    uv_path: str = "uv",
    environment: dict[str, str] | None = None,
) -> list[Job]:
    return [
        Job(
            label="care.clonway.xsource.watcher",
            argv=[uv_path, "--project", project_dir, "run", "xsource", "watcher", "run"],
            start_interval=60,
            environment=environment,
        ),
        Job(
            label="care.clonway.xsource.sync",
            argv=[uv_path, "--project", project_dir, "run", "xsource", "request", "sync-all"],
            start_calendar={"Hour": 2, "Minute": 10},
            environment=environment,
        ),
        Job(
            label="care.clonway.xsource.signals",
            argv=[uv_path, "--project", project_dir, "run", "xsource", "signals", "scan"],
            start_calendar={"Hour": 7, "Minute": 5},
            environment=environment,
        ),
    ]


def _job_name(job: Job) -> str:
    return job.label.rsplit(".", 1)[-1]


def filter_jobs(jobs_: list[Job], only: list[str]) -> list[Job]:
    if not only:
        return jobs_
    wanted = set(only)
    known = {_job_name(job) for job in jobs_}
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError(f"unknown job(s): {', '.join(unknown)}")
    return [job for job in jobs_ if _job_name(job) in wanted]


def read_env_file(path: pathlib.Path) -> dict[str, str]:
    environment = {}
    for lineno, raw in enumerate(path.expanduser().read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{lineno}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if not key:
            raise ValueError(f"{path}:{lineno}: empty key")
        if key in _DIRECT_SECRET_KEYS:
            raise ValueError(f"{path}:{lineno}: use {key}_FILE instead of embedding {key}")
        environment[key] = value
    return environment


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
        "--env-file",
        help="Optional KEY=VALUE file to embed into each launchd plist EnvironmentVariables.",
    )
    parser.add_argument(
        "--uv-path",
        default=shutil.which("uv") or "uv",
        help="uv executable path to write into ProgramArguments.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        choices=["watcher", "sync", "signals"],
        help="Install/load only this job name. Repeat to select multiple jobs.",
    )
    parser.add_argument(
        "--write", action="store_true", help="Write plists to ~/Library/LaunchAgents."
    )
    parser.add_argument(
        "--load", action="store_true", help="Load plists with launchctl after writing."
    )
    args = parser.parse_args()

    environment = read_env_file(pathlib.Path(args.env_file)) if args.env_file else None
    launch_agents = pathlib.Path.home() / "Library/LaunchAgents"
    selected_jobs = filter_jobs(
        jobs(args.project_dir, uv_path=args.uv_path, environment=environment), args.only
    )
    for job in selected_jobs:
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
