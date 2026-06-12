"""End-to-end tests for the trigger parse → walk → store pipeline (S10)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from xsource.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _Store:
    def __init__(self, records=None):
        self._records: dict = {}
        for rec in records or []:
            self._records[rec.id] = rec
        self.upserted: list = []
        self._counter = 0

    def all(self):
        return list(self._records.values())

    def get(self, rec_id):
        return self._records.get(rec_id)

    def upsert(self, rec):
        self._records[rec.id] = rec
        self.upserted.append(rec)

    def next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter:04d}"

    @property
    def offline(self):
        return False


class _FakeTriage:
    category = "tree surgery"
    search_terms = ["tree chipping"]
    also_try = []
    email_vars = {"job_summary": "tree chipping", "location_town": "Newton Abbot"}

    def to_dict(self):
        return {
            "category": self.category,
            "search_terms": self.search_terms,
            "also_try": self.also_try,
            "email_vars": self.email_vars,
        }


class _FakeResearchResult:
    def __init__(self):
        from xsource.research.candidates import Candidate
        from xsource.research.pipeline import ResearchResult

        self.shortlist = [
            Candidate(
                name="Newton Tree Services",
                source="places",
                phone="+441626000001",
                email="info@newtontree.example",
                website=None,
                address="1 High St, Newton Abbot",
                postcode="TQ12 1AB",
                source_url=None,
                rating=4.5,
                review_count=12,
                rating_scale=5,
                extra={},
            )
        ]
        self._result = ResearchResult(shortlist=self.shortlist, indicative=None, stages={})


# ---------------------------------------------------------------------------
# Walk step-chain tests
# ---------------------------------------------------------------------------


def test_trigger_walk_email_payload_creates_request(monkeypatch, tmp_path):
    """email payload → parse → triage → research → apply → Request in store."""
    import datetime as dt

    from clonway_cockpit.registry import WizardContext
    from clonway_cockpit.walk import StepResult
    from rich.console import Console

    from xsource.cli.cockpit import (
        _research_step,
        _triage_step,
        _trigger_step,
    )

    fake_res = _FakeResearchResult()

    monkeypatch.setattr("xsource.cli.cockpit.run_triage", lambda *a, **k: _FakeTriage())
    monkeypatch.setattr("xsource.cli.cockpit.run_research", lambda **k: fake_res._result)
    monkeypatch.setattr(
        "xsource.cli.cockpit.build_stores", lambda cfg: (_Store(), _Store(), _Store())
    )
    monkeypatch.setattr(
        "xsource.cli.cockpit.build_research_fns",
        lambda cfg: {
            "places_fn": lambda *a, **k: [],
            "directory_fn": lambda *a, **k: [],
            "price_fn": lambda *a, **k: None,
            "ch_fn": lambda *a, **k: None,
        },
    )

    # Patch apply step: intercept sheet creation + stores
    suppliers_store = _Store()
    requests_store = _Store()

    def fake_build_stores(cfg):
        return suppliers_store, requests_store, _Store()

    monkeypatch.setattr("xsource.cli.cockpit.build_stores", fake_build_stores)

    captured_sheet_calls = []

    def fake_review_apply_step(ctx, bag):
        from xsource.walks.request_new import apply_request

        def create_sheet(title, values):
            captured_sheet_calls.append({"title": title, "values": values})
            return ("sheet-id-1", "https://sheets.example/1")

        req = apply_request(
            raw_need=bag["raw_need"],
            triage_dict=bag["triage"],
            constraints=bag["constraints"],
            result=bag["result"],
            suppliers=suppliers_store,
            requests=requests_store,
            create_sheet_fn=create_sheet,
            now=dt.datetime(2026, 6, 11, 10, 0),
        )
        return StepResult(ok=True, data={"summary": f"Created {req.id}."})

    payload = {
        "source": "email",
        "subject": "Need tree work",
        "body": "Please find someone for tree chipping near Newton Abbot by Friday.",
    }
    payload_json = json.dumps(payload)

    inputs = iter([payload_json, ""])  # payload JSON, then Enter to keep need

    ctx = WizardContext(
        state={},
        client=None,
        console=Console(quiet=True),
        input_fn=lambda *a, **k: next(inputs),
        confirm_fn=lambda _p: True,
        read_key=lambda: "\r",
        focus=None,
    )

    bag: dict = {}

    # Step 1: trigger
    r1 = _trigger_step(ctx, bag)
    assert r1.ok, r1.message
    bag.update(r1.data or {})
    assert bag["raw_need"] == "Please find someone for tree chipping near Newton Abbot by Friday."
    assert bag["constraints"]["source"] == "email"

    # Step 2: triage (mocked)
    r2 = _triage_step(ctx, bag)
    assert r2.ok
    bag.update(r2.data or {})

    # Step 3: research (mocked)
    r3 = _research_step(ctx, bag)
    assert r3.ok
    bag.update(r3.data or {})

    # Step 4: apply via our fake (bypasses real Google auth)
    r4 = fake_review_apply_step(ctx, bag)
    assert r4.ok

    # Assertions
    assert len(requests_store.upserted) == 1
    request = requests_store.upserted[0]
    assert request.raw_need == "Please find someone for tree chipping near Newton Abbot by Friday."
    assert request.constraints["source"] == "email"
    assert len(request.shortlist) == 1
    assert len(captured_sheet_calls) == 1


def test_trigger_walk_non_procurement_payload_rejected():
    """chat payload with no procurement hints → step returns ok=False, no store writes."""
    from clonway_cockpit.registry import WizardContext
    from rich.console import Console

    from xsource.cli.cockpit import _trigger_step

    payload_json = json.dumps({"source": "chat", "body": "Thanks, all sorted."})
    ctx = WizardContext(
        state={},
        client=None,
        console=Console(quiet=True),
        input_fn=lambda *a, **k: payload_json,
        confirm_fn=lambda _p: False,
        read_key=lambda: "\x1b",
        focus=None,
    )
    result = _trigger_step(ctx, {})
    assert not result.ok
    assert "not a procurement trigger" in result.message.lower()


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


def test_trigger_cli_procurement_payload_exits_zero(tmp_path):
    payload = {
        "source": "email",
        "subject": "Need a supplier",
        "body": "Please find someone for tree chipping.",
    }
    p = tmp_path / "payload.json"
    p.write_text(json.dumps(payload))

    result = runner.invoke(app, ["request", "trigger", "--file", str(p)])

    assert result.exit_code == 0
    assert "source: email" in result.stdout
    assert "need:" in result.stdout


def test_trigger_cli_non_procurement_payload_exits_one(tmp_path):
    payload = {"source": "chat", "body": "Thanks, all sorted."}
    p = tmp_path / "payload.json"
    p.write_text(json.dumps(payload))

    result = runner.invoke(app, ["request", "trigger", "--file", str(p)])

    assert result.exit_code == 1


def test_trigger_cli_invalid_json_exits_one(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not-json")

    result = runner.invoke(app, ["request", "trigger", "--file", str(p)])

    assert result.exit_code == 1
