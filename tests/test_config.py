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
