"""Directory web-search and supplier-website contact seam."""

from __future__ import annotations

import logging
import re
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


CONTACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "email": {"type": ["string", "null"]},
        "page_url": {"type": ["string", "null"]},
        "source_quote": {"type": "string"},
    },
    "required": ["email", "page_url", "source_quote"],
}

_CONTACT_INSTRUCTION = (
    "Open the business's own website and find the email address it gives for enquiries. "
    "Try the home page, then a contact page if there is one. Report the address exactly as "
    "written, the page it was on, and the sentence it appears in. If no email address is "
    "shown, report null; never guess one from the domain."
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


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

    def _report(
        self, model: str, system: str, tool: dict, prompt: str, schema: dict
    ) -> dict | None:
        resp = self.client.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            tools=cast(
                Any,
                [
                    tool,
                    {
                        "name": "report",
                        "description": "Report what you found.",
                        "input_schema": schema,
                    },
                ],
            ),
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            block_any = cast(Any, block)
            if (
                getattr(block_any, "type", None) == "tool_use"
                and getattr(block_any, "name", None) == "report"
            ):
                return cast(dict, block_any.input)
        return None

    def _extract_with_model(self, model: str, query: str, schema: dict) -> dict:
        out = self._report(
            model,
            _EXTRACT_INSTRUCTION,
            {"type": "web_search_20260209", "name": "web_search", "max_uses": 3},
            f"Query: {query}\nWhen done searching, call report.",
            schema,
        )
        if out is None:
            log.warning("websearch returned no report tool call for %r", query)
            return {"candidates": []}
        return out

    def _contact_with_model(self, model: str, name: str, website: str) -> dict:
        out = self._report(
            model,
            _CONTACT_INSTRUCTION,
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3},
            f"Business: {name}\nWebsite: https://{website}/\nWhen done, call report.",
            CONTACT_SCHEMA,
        )
        return out or {"email": None, "page_url": None, "source_quote": ""}

    def find_contact(self, name: str, website: str) -> dict:
        return self._with_fallback(
            "contact", lambda model: self._contact_with_model(model, name, website)
        )

    def extract(self, query: str, schema: dict) -> dict:
        return self._with_fallback(
            "websearch", lambda model: self._extract_with_model(model, query, schema)
        )

    def _with_fallback(self, role: str, call) -> dict:
        from xsource.obs import event as obs_event

        for i, model in enumerate(self.model_chain):
            try:
                return call(model)
            except Exception as exc:
                if not _is_retriable_error(exc) or i == len(self.model_chain) - 1:
                    raise
                log.warning(
                    "websearch model %r unavailable (%s), falling back to %r",
                    model,
                    exc,
                    self.model_chain[i + 1],
                )
                obs_event(
                    "gateway.model_fallback",
                    severity="warn",
                    role=role,
                    failed_model=model,
                    next_model=self.model_chain[i + 1],
                    error=str(exc),
                )
        raise RuntimeError(f"{role} model chain exhausted")


def find_website_email(name: str, website: str, searcher) -> str | None:
    """The supplier's enquiry email, only if the quoted page text really contains it."""
    try:
        raw = searcher.find_contact(name, website)
    except Exception as exc:
        log.warning("contact lookup failed for %r: %s", website, exc)
        return None
    email = (raw.get("email") or "").strip()
    if not _EMAIL.fullmatch(email) or email.lower() not in raw.get("source_quote", "").lower():
        return None
    return email


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
