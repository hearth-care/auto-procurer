"""The Sheet contract."""

from __future__ import annotations

from xsource.research.candidates import Candidate

COLUMNS = [
    "#",
    "Provider",
    "Source",
    "Rating",
    "Phone",
    "Email",
    "Indicative",
    "Status",
    "Asked",
    "Reply",
    "Quote £",
    "Chosen",
    "Updated",
    "Notes",
]
STATUS_VALUES = ["To call", "Draft ready", "Asked", "Replied", "Quoted", "Chosen", "No"]

_SOURCE_LABEL = {
    "book": "black book",
    "places": "Google",
    "yell": "Yell",
    "checkatrade": "Checkatrade",
    "web": "Web",
    "companies_house": "Comp. House",
}


def _rating_cell(candidate: Candidate) -> str:
    if candidate.rating is None:
        return "—"
    if candidate.rating_scale == 10:
        return f"{candidate.rating:g} ({candidate.review_count or 0})"
    return f"★{candidate.rating:g} ({candidate.review_count or 0})"


def _hyperlink(url: str | None, label: str) -> str:
    if not url:
        return label
    return f'=HYPERLINK("{url}", "{label}")'


def build_values(
    request_id: str,
    job_line: str,
    indicative: dict | None,
    rows: list[Candidate],
    indicatives: list[list[int] | None],
    now_label: str,
) -> list[list[str]]:
    grid: list[list[str]] = [list(COLUMNS)]
    for idx, (candidate, indicative_range) in enumerate(zip(rows, indicatives, strict=True), start=1):
        grid.append(
            [
                str(idx),
                candidate.name,
                _hyperlink(candidate.source_url, _SOURCE_LABEL.get(candidate.source, candidate.source)),
                _rating_cell(candidate),
                candidate.phone or "—",
                candidate.email or "—",
                f"£{indicative_range[0]}–{indicative_range[1]}" if indicative_range else "—",
                "To call",
                "",
                "",
                "",
                "",
                now_label,
                "",
            ]
        )
    ind_line = (
        f" · indicative £{indicative['low']}–£{indicative['high']} ({indicative['sources']} sources)"
        if indicative
        else ""
    )
    grid.append([f"Job: {job_line}{ind_line} · request {request_id}"] + [""] * (len(COLUMNS) - 1))
    return grid
