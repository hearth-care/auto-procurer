from __future__ import annotations

from pathlib import Path


def test_container_files_define_uv_entrypoint() -> None:
    dockerfile = Path("Dockerfile").read_text()
    dockerignore = Path(".dockerignore").read_text().splitlines()

    assert "apt-get install -y --no-install-recommends git" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert 'CMD ["xsource", "--help"]' in dockerfile
    assert ".venv" in dockerignore
    assert ".claude" in dockerignore


def test_deploy_workflow_creates_paused_jobs_and_schedulers_from_config_keys() -> None:
    workflow = Path(".github/workflows/deploy-cloud-run.yml").read_text()
    config = Path("deploy/xsource-cloud-run.env.example").read_text()

    assert "google-github-actions/auth" in workflow
    assert 'gcloud run jobs deploy "${job_name}"' in workflow
    assert "gcloud scheduler jobs pause ${scheduler_name}" in workflow
    assert "XSOURCE_CLOUD_RUN_PROJECT" in config
    assert "XSOURCE_WATCHER_JOB_NAME" in config
    assert "XSOURCE_RUNTIME_SERVICE_ACCOUNT" in config


def test_deploy_artifacts_do_not_commit_concrete_fleet_identifiers() -> None:
    checked = [
        Path(".github/workflows/deploy-cloud-run.yml"),
        Path("deploy/xsource-cloud-run.env.example"),
    ]
    text = "\n".join(path.read_text() for path in checked)

    assert "clonway-orchestrator-eu-west2" not in text
    assert "@clonway" not in text
