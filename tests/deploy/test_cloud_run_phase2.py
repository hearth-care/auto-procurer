from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_deploy_workflow_mounts_secret_files_and_existing_env_paths() -> None:
    workflow = Path(".github/workflows/deploy-cloud-run.yml").read_text()
    config = Path("deploy/xsource-cloud-run.env.example").read_text()

    assert "XSOURCE_GMAIL_TOKEN_SECRET" in config
    assert "XSOURCE_SHEETS_TOKEN_SECRET" in config
    assert "XSOURCE_ANTHROPIC_API_KEY_SECRET" in config
    assert "/secrets/gmail/token.json=${XSOURCE_GMAIL_TOKEN_SECRET}:latest" in workflow
    assert "XSOURCE_GMAIL_TOKEN_PATH=/secrets/gmail/token.json" in workflow
    assert "ANTHROPIC_API_KEY_FILE=/secrets/anthropic/api-key" in workflow


def test_operator_provisioning_script_is_stdlib_and_prints_secret_commands() -> None:
    path = Path("scripts/provision_cloud_run.py")
    script = path.read_text()

    assert "import google" not in script
    assert "import requests" not in script
    assert "subprocess" in script
    assert "print_command" in script

    spec = importlib.util.spec_from_file_location("provision_cloud_run", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["provision_cloud_run"] = module
    spec.loader.exec_module(module)

    prompts = iter(["gmail", "sheets", "anthropic", "maps", "companies-house"])
    module._prompt = lambda *_args: next(prompts)

    commands = module.create_secret_commands(
        project="project-id",
        region="region",
        service_account="runtime@example.iam.gserviceaccount.com",
    )

    assert commands[0][:4] == ["gcloud", "secrets", "create", "gmail"]
    assert [
        "gcloud",
        "secrets",
        "add-iam-policy-binding",
        "gmail",
        "--project",
        "project-id",
        "--member",
        "serviceAccount:runtime@example.iam.gserviceaccount.com",
        "--role",
        "roles/secretmanager.secretAccessor",
    ] in commands
