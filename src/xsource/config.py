"""xsource runtime config.

All knobs are XSOURCE_* env vars. No secrets live here, only names.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Config:
    home_postcode: str | None
    default_radius_miles: int
    shortlist_n: int
    max_places_calls: int
    max_web_searches: int
    monthly_budget_gbp: float
    chase_after_days: int
    poll_seconds: int
    drive_folder_id: str | None
    staff_share_group: str | None
    state_dir: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            home_postcode=os.environ.get("XSOURCE_HOME_POSTCODE") or None,
            default_radius_miles=_int("XSOURCE_DEFAULT_RADIUS_MILES", 15),
            shortlist_n=_int("XSOURCE_SHORTLIST_N", 5),
            max_places_calls=_int("XSOURCE_MAX_PLACES_CALLS", 10),
            max_web_searches=_int("XSOURCE_MAX_WEB_SEARCHES", 8),
            monthly_budget_gbp=float(os.environ.get("XSOURCE_MONTHLY_BUDGET_GBP", "10")),
            chase_after_days=_int("XSOURCE_CHASE_AFTER_DAYS", 3),
            poll_seconds=_int("XSOURCE_POLL_SECONDS", 60),
            drive_folder_id=os.environ.get("XSOURCE_DRIVE_FOLDER_ID") or None,
            staff_share_group=os.environ.get("XSOURCE_STAFF_SHARE_GROUP") or None,
            state_dir=os.environ.get(
                "XSOURCE_STATE_DIR", os.path.expanduser("~/.claude-inbox/xsource/state")
            ),
        )
