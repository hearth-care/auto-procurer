#!/usr/bin/env python3
"""Provision xsource Cloud Run secret containers and IAM bindings.

Stdlib-only by design. This script never accepts secret values on argv; it only
creates containers/bindings. Operators add secret values separately with a
trusted local flow.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretSpec:
    env_key: str
    purpose: str


SECRETS = (
    SecretSpec("XSOURCE_GMAIL_TOKEN_SECRET", "Gmail OAuth authorized-user token JSON"),
    SecretSpec("XSOURCE_SHEETS_TOKEN_SECRET", "Sheets OAuth authorized-user token JSON"),
    SecretSpec("XSOURCE_ANTHROPIC_API_KEY_SECRET", "Anthropic API key"),
    SecretSpec("XSOURCE_GOOGLE_MAPS_API_KEY_SECRET", "Google Maps API key"),
    SecretSpec("XSOURCE_COMPANIES_HOUSE_API_KEY_SECRET", "Companies House API key"),
)


def print_command(command: list[str]) -> None:
    print("+ " + " ".join(shlex.quote(part) for part in command))


def run(command: list[str], *, dry_run: bool) -> None:
    print_command(command)
    if not dry_run:
        subprocess.run(command, check=True)


def _prompt(default: str | None, label: str) -> str:
    if default:
        return default.strip()
    return input(f"{label}: ").strip()


def create_secret_commands(*, project: str, region: str, service_account: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for spec in SECRETS:
        secret_name = _prompt(None, f"{spec.env_key} ({spec.purpose})")
        commands.append(
            [
                "gcloud",
                "secrets",
                "create",
                secret_name,
                "--project",
                project,
                "--replication-policy",
                "automatic",
            ]
        )
        commands.append(
            [
                "gcloud",
                "secrets",
                "add-iam-policy-binding",
                secret_name,
                "--project",
                project,
                "--member",
                f"serviceAccount:{service_account}",
                "--role",
                "roles/secretmanager.secretAccessor",
            ]
        )
    commands.append(
        [
            "gcloud",
            "run",
            "jobs",
            "list",
            "--project",
            project,
            "--region",
            region,
        ]
    )
    return commands


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", nargs="?", help="GCP project id; prompts if omitted.")
    parser.add_argument("--region", nargs="?", help="Cloud Run region; prompts if omitted.")
    parser.add_argument(
        "--service-account",
        nargs="?",
        help="Runtime service account email; prompts if omitted.",
    )
    parser.add_argument("--apply", action="store_true", help="Run commands after printing them.")
    args = parser.parse_args()

    project = _prompt(args.project, "GCP project id")
    region = _prompt(args.region, "Cloud Run region")
    service_account = _prompt(args.service_account, "Runtime service account email")
    commands = create_secret_commands(project=project, region=region, service_account=service_account)

    if args.apply:
        confirm = input("Apply these prod-mutating commands? Type APPLY: ").strip()
        if confirm != "APPLY":
            raise SystemExit("aborted")

    for command in commands:
        run(command, dry_run=not args.apply)


if __name__ == "__main__":
    main()
