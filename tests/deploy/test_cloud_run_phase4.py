from __future__ import annotations

from pathlib import Path


def test_readme_points_runtime_to_cloud_run_and_launchd_rollback() -> None:
    readme = Path("README.md").read_text()

    assert "## Runtime" in readme
    assert "Cloud Run jobs" in readme
    assert "scripts/install_launchd.py" in readme
    assert "rollback only" in readme


def test_cutover_runbook_covers_soak_single_runner_and_operator_todos() -> None:
    runbook = Path("docs/runbooks/cloud-run-cutover.md").read_text()

    assert "Deploy jobs and schedulers paused" in runbook
    assert "never run both watchers" in runbook
    assert "OPERATOR TODO" in runbook
    assert "launchctl bootout" in runbook
    assert "Rollback" in runbook


def test_launchd_installer_docstring_marks_legacy_rollback_only() -> None:
    text = Path("scripts/install_launchd.py").read_text()

    assert "legacy/rollback-only" in text
