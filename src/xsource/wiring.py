"""Build real collaborators from Config and env secrets."""

from __future__ import annotations

import datetime as dt
import os
from functools import partial
from pathlib import Path

from xsource.budget import Budget
from xsource.config import Config
from xsource.research import places, pricesweep, websearch
from xsource.research.companies_house import company_check
from xsource.secrets import secret_from_env
from xsource.store.models import Request, Supplier
from xsource.store.remote import SyncedStore, make_blob

_BUCKET = "clonway-orchestrator-eu-west2"


def build_stores(cfg: Config) -> tuple[SyncedStore, SyncedStore]:
    base = Path(cfg.state_dir)
    suppliers = SyncedStore(
        base, "suppliers.jsonl", Supplier, make_blob(_BUCKET, "state/xsource/suppliers.jsonl")
    )
    requests_ = SyncedStore(
        base, "requests.jsonl", Request, make_blob(_BUCKET, "state/xsource/requests.jsonl")
    )
    return suppliers, requests_


def build_budget(cfg: Config, today: dt.date) -> Budget:
    return Budget(Path(cfg.state_dir), cfg.monthly_budget_gbp, today.strftime("%Y-%m"))


def build_research_fns(cfg: Config):
    maps_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    ch_key = os.environ.get("COMPANIES_HOUSE_API_KEY", "")
    searcher = websearch.AnthropicSearcher(
        api_key=secret_from_env("ANTHROPIC_API_KEY"),
        model=cfg.model_chain[0],
        model_chain=cfg.model_chain,
    )
    return {
        "places_fn": partial(_places, cfg, maps_key),
        "directory_fn": lambda term, site: websearch.search_directory(
            term, cfg.home_postcode or "", site, searcher=searcher
        ),
        "price_fn": lambda term: pricesweep.sweep_prices(term, "Devon", searcher=searcher),
        "ch_fn": lambda name: company_check(name, api_key=ch_key) if ch_key else None,
    }


def _places(cfg: Config, key: str, term: str):
    return places.search_places(
        term, cfg.home_postcode or "", cfg.default_radius_miles, api_key=key
    )
