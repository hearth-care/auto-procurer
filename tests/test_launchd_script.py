from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script():
    path = Path("scripts/install_launchd.py")
    spec = importlib.util.spec_from_file_location("install_launchd", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_launchd_script_declares_required_jobs():
    script = _load_script()
    jobs = script.jobs("/Users/olliepage/Developer/Auto-Procurer", uv_path="/opt/homebrew/bin/uv")
    labels = {job.label for job in jobs}

    assert labels == {
        "care.clonway.xsource.watcher",
        "care.clonway.xsource.sync",
        "care.clonway.xsource.signals",
    }
    assert all(job.argv[0] == "/opt/homebrew/bin/uv" for job in jobs)
    sync_job = next(job for job in jobs if job.label == "care.clonway.xsource.sync")
    assert sync_job.argv[-2:] == ["request", "sync-all"]


def test_launchd_jobs_include_environment_variables():
    script = _load_script()
    env = {
        "XSOURCE_STATE_DIR": "/Users/olliepage/.claude-inbox/xsource/state",
        "XSOURCE_GMAIL_TOKEN_PATH": "/Users/olliepage/.claude-inbox/milo/gmail-token.json",
    }

    job = script.jobs(
        "/Users/olliepage/Developer/Auto-Procurer",
        uv_path="/opt/homebrew/bin/uv",
        environment=env,
    )[0]

    assert job.plist()["EnvironmentVariables"] == env


def test_env_file_parser_reads_simple_key_value_pairs(tmp_path):
    script = _load_script()
    env_file = tmp_path / "xsource.env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "XSOURCE_STATE_DIR=/Users/olliepage/.claude-inbox/xsource/state",
                "XSOURCE_OWN_EMAILS='milo.garth@clonwaycare.co.uk'",
                "",
            ]
        )
    )

    assert script.read_env_file(env_file) == {
        "XSOURCE_STATE_DIR": "/Users/olliepage/.claude-inbox/xsource/state",
        "XSOURCE_OWN_EMAILS": "milo.garth@clonwaycare.co.uk",
    }


def test_env_file_parser_rejects_direct_secret_values(tmp_path):
    script = _load_script()
    env_file = tmp_path / "xsource.env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-secret\n")

    try:
        script.read_env_file(env_file)
    except ValueError as exc:
        assert "ANTHROPIC_API_KEY_FILE" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_filter_jobs_selects_named_jobs_only():
    script = _load_script()
    jobs = script.jobs("/Users/olliepage/Developer/Auto-Procurer", uv_path="/opt/homebrew/bin/uv")

    selected = script.filter_jobs(jobs, ["signals"])

    assert [job.label for job in selected] == ["care.clonway.xsource.signals"]


def test_filter_jobs_rejects_unknown_name():
    script = _load_script()
    jobs = script.jobs("/Users/olliepage/Developer/Auto-Procurer", uv_path="/opt/homebrew/bin/uv")

    try:
        script.filter_jobs(jobs, ["bogus"])
    except ValueError as exc:
        assert "unknown job" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_launchd_script_is_stdlib_only():
    text = Path("scripts/install_launchd.py").read_text()

    assert "google" not in text
    assert "requests" not in text
    assert "subprocess" in text
