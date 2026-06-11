from xsource.config import Config


def test_defaults(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("XSOURCE_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("XSOURCE_HOME_POSTCODE", "TQ12 4QQ")
    cfg = Config.from_env()
    assert cfg.home_postcode == "TQ12 4QQ"
    assert cfg.default_radius_miles == 15
    assert cfg.shortlist_n == 5
    assert cfg.max_places_calls == 10
    assert cfg.max_web_searches == 8
    assert cfg.monthly_budget_gbp == 10.0
    assert cfg.chase_after_days == 3


def test_overrides(monkeypatch):
    monkeypatch.setenv("XSOURCE_HOME_POSTCODE", "EX1 1AA")
    monkeypatch.setenv("XSOURCE_DEFAULT_RADIUS_MILES", "25")
    monkeypatch.setenv("XSOURCE_SHORTLIST_N", "7")
    cfg = Config.from_env()
    assert (cfg.home_postcode, cfg.default_radius_miles, cfg.shortlist_n) == ("EX1 1AA", 25, 7)


def test_missing_postcode_is_none(monkeypatch):
    monkeypatch.delenv("XSOURCE_HOME_POSTCODE", raising=False)
    assert Config.from_env().home_postcode is None


def test_model_chain_defaults_to_sonnet(monkeypatch):
    monkeypatch.delenv("XSOURCE_MODEL_CHAIN", raising=False)
    monkeypatch.delenv("XSOURCE_RESEARCH_MODEL", raising=False)
    cfg = Config.from_env()
    assert cfg.model_chain == ["claude-sonnet-4-6"]


def test_model_chain_from_env(monkeypatch):
    monkeypatch.setenv("XSOURCE_MODEL_CHAIN", "claude-opus-4-8, claude-sonnet-4-6")
    cfg = Config.from_env()
    assert cfg.model_chain == ["claude-opus-4-8", "claude-sonnet-4-6"]


def test_model_chain_from_research_model_fallback(monkeypatch):
    monkeypatch.delenv("XSOURCE_MODEL_CHAIN", raising=False)
    monkeypatch.setenv("XSOURCE_RESEARCH_MODEL", "claude-haiku-4-5-20251001")
    cfg = Config.from_env()
    assert cfg.model_chain == ["claude-haiku-4-5-20251001"]


def test_fleet_state_config_comes_from_env(monkeypatch):
    monkeypatch.setenv("XSOURCE_FLEET_BUCKET", "bucket-name")
    monkeypatch.setenv("XSOURCE_STATE_PREFIX", "state/example")

    cfg = Config.from_env()

    assert cfg.fleet_bucket == "bucket-name"
    assert cfg.state_prefix == "state/example"
