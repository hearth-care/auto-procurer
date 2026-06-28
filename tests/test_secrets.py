from __future__ import annotations

from xsource.secrets import secret_from_env


def test_secret_from_env_reads_file_when_direct_value_missing(monkeypatch, tmp_path):
    secret_file = tmp_path / "anthropic-key"
    secret_file.write_text("sk-from-file\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY_FILE", str(secret_file))

    assert secret_from_env("ANTHROPIC_API_KEY") == "sk-from-file"


def test_secret_from_env_supports_maps_and_companies_house_file_secrets(monkeypatch, tmp_path):
    maps = tmp_path / "maps-key"
    ch = tmp_path / "companies-house-key"
    maps.write_text("maps-from-file\n")
    ch.write_text("ch-from-file\n")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY_FILE", str(maps))
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY_FILE", str(ch))

    assert secret_from_env("GOOGLE_MAPS_API_KEY") == "maps-from-file"
    assert secret_from_env("COMPANIES_HOUSE_API_KEY") == "ch-from-file"
