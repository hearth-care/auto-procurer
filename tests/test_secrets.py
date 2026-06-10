from __future__ import annotations

from xsource.secrets import secret_from_env


def test_secret_from_env_reads_file_when_direct_value_missing(monkeypatch, tmp_path):
    secret_file = tmp_path / "anthropic-key"
    secret_file.write_text("sk-from-file\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY_FILE", str(secret_file))

    assert secret_from_env("ANTHROPIC_API_KEY") == "sk-from-file"
