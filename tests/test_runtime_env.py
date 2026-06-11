from __future__ import annotations

import importlib


def test_obs_runtime_env_is_env_var_name(monkeypatch) -> None:
    monkeypatch.delenv("XSOURCE_RUNTIME_ENV", raising=False)
    import xsource.obs as obs

    obs = importlib.reload(obs)

    assert obs._RUNTIME_ENV == "XSOURCE_RUNTIME_ENV"


def test_signal_project_defaults_to_adc_and_accepts_override(monkeypatch) -> None:
    import xsource.signals.emit as emit

    monkeypatch.delenv("XSOURCE_GCP_PROJECT", raising=False)
    emit = importlib.reload(emit)
    assert emit._project() is None

    monkeypatch.setenv("XSOURCE_GCP_PROJECT", "example-project")
    assert emit._project() == "example-project"
