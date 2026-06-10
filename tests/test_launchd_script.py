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
    jobs = script.jobs("/Users/olliepage/Developer/Auto-Procurer")
    labels = {job.label for job in jobs}

    assert labels == {
        "care.clonway.xsource.watcher",
        "care.clonway.xsource.sync",
        "care.clonway.xsource.signals",
    }
    sync_job = next(job for job in jobs if job.label == "care.clonway.xsource.sync")
    assert sync_job.argv[-2:] == ["request", "sync-all"]


def test_launchd_script_is_stdlib_only():
    text = Path("scripts/install_launchd.py").read_text()

    assert "google" not in text
    assert "requests" not in text
    assert "subprocess" in text
