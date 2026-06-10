"""Live integration smoke.

Run manually:
    XSOURCE_LIVE_SMOKE=1 uv run python scripts/live_smoke.py
"""

import os
import sys

if os.environ.get("XSOURCE_LIVE_SMOKE") != "1":
    sys.exit("set XSOURCE_LIVE_SMOKE=1 to run (this hits real APIs)")

from xsource.config import Config
from xsource.research.companies_house import company_check
from xsource.research.places import search_places
from xsource.wiring import build_research_fns

cfg = Config.from_env()
print(f"home postcode: {cfg.home_postcode}")

print("Places: 'tree surgeon'")
for candidate in search_places(
    "tree surgeon",
    cfg.home_postcode or "",
    cfg.default_radius_miles,
    api_key=os.environ["GOOGLE_MAPS_API_KEY"],
)[:3]:
    print("   ", candidate.name, candidate.phone, candidate.rating)

fns = build_research_fns(cfg)
print("Yell directory search")
for candidate in fns["directory_fn"]("tree surgeon", "yell.com")[:3]:
    print("   ", candidate.name, candidate.source_url)

print("Companies House: 'Teign Trees'")
print("   ", company_check("Teign Trees", api_key=os.environ.get("COMPANIES_HOUSE_API_KEY", "")))
print("done - if a sheet test is needed, run the cockpit walk in --allow-apply instead")
