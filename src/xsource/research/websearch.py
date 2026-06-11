"""Directory web-search seam."""

from __future__ import annotations

import logging
from typing import Any, cast

from xsource.research.candidates import Candidate
from xsource.research.validate import validate_directory_candidate

log = logging.getLogger("xsource.research")

DIRECTORY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": ["string", "null"]},
                    "email": {"type": ["string", "null"]},
                    "profile_url": {"type": "string"},
                    "rating": {"type": ["number", "null"]},
                    "review_count": {"type": ["integer", "null"]},
                    "town": {"type": ["string", "null"]},
                    "categories": {"type": "array", "items": {"type": "string"}},
                    "source_quote": {"type": "string"},
                },
                "required": ["name", "profile_url", "source_quote"],
            },
        }
    },
    "required": ["candidates"],
}

_EXTRACT_INSTRUCTION = (
    "Search the web with the given query and read the listing pages it surfaces on the "
    "target directory site. Report ONLY what the listings actually show."
)


def _is_retriable_error(exc: Exception) -> bool:
    return type(exc).__name__ in {"InternalServerError", "OverloadedError", "APIStatusError"}


class AnthropicSearcher:
    def __init__(self, api_key: str, model: str, model_chain: list[str] | None = None):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_chain: list[str] = model_chain if model_chain else [model]

    @property
    def model(self) -> str:
        return self.model_chain[0]

    def _extract_with_model(self, model: str, query: str, schema: dict) -> dict:
        resp = self.client.messages.create(
            model=model,
            max_tokens=2000,
            system=_EXTRACT_INSTRUCTION,
            tools=[
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
                {
                    "name": "report",
                    "description": "Report extracted directory candidates.",
                    "input_schema": schema,
                },
            ],
            tool_choice={"type": "auto"},
            messages=[
                {"role": "user", "content": f"Query: {query}\nWhen done searching, call report."}
            ],
        )
        for block in resp.content:
            block_any = cast(Any, block)
            if (
                getattr(block_any, "type", None) == "tool_use"
                and getattr(block_any, "name", None) == "report"
            ):
                return cast(dict, block_any.input)
        log.warning("websearch returned no report tool call for %r", query)
        return {"candidates": []}

    def extract(self, query: str, schema: dict) -> dict:
        for i, model in enumerate(self.model_chain):
            try:
                return self._extract_with_model(model, query, schema)
            except Exception as exc:
                if not _is_retriable_error(exc) or i == len(self.model_chain) - 1:
                    raise
                log.warning(
                    "websearch model %r unavailable (%s), falling back to %r",
                    model,
                    exc,
                    self.model_chain[i + 1],
                )
        return {"candidates": []}


def search_directory(trade_term: str, town: str, site: str, searcher) -> list[Candidate]:
    query = f"site:{site} {trade_term} {town}"
    try:
        raw = searcher.extract(query, DIRECTORY_SCHEMA)
    except Exception as exc:
        log.warning("directory search failed for %r: %s", query, exc)
        return []
    out = []
    for candidate in raw.get("candidates", []):
        parsed = validate_directory_candidate(candidate, site=site)
        if parsed is not None:
            out.append(parsed)
    return out
