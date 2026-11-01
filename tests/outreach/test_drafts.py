from __future__ import annotations

import datetime as dt

from xsource.outreach.drafts import (
    build_outreach_system_prompt,
    build_quote_request,
    create_request_drafts,
)
from xsource.store.models import Request, ShortlistEntry, Supplier


class _Store:
    def __init__(self, records):
        self.records = {record.id: record for record in records}
        self.upserted = []

    def all(self):
        return list(self.records.values())

    def get(self, rec_id):
        return self.records.get(rec_id)

    def upsert(self, rec):
        self.records[rec.id] = rec
        self.upserted.append(rec)


class _DraftClient:
    def __init__(self):
        self.calls = []

    def create_draft(self, *, to, subject, body, label):
        self.calls.append({"to": to, "subject": subject, "body": body, "label": label})
        n = len(self.calls)
        return {"draft_id": f"d-{n}", "message_id": f"m-{n}", "thread_id": f"t-{n}"}


class _Gateway:
    def __init__(self):
        self.calls = []

    def complete_structured(self, messages, schema, role="research"):
        self.calls.append({"messages": messages, "schema": schema, "role": role})
        return {"body": "Model-written supplier note.\n\nref r-0042"}


def test_build_quote_request_uses_reference_in_body_not_subject():
    supplier = Supplier(id="s-1", name="Westcountry Tree Care", email="info@example.com")
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+01:00",
        raw_need="Fallen tree needs cutting and chipping",
        triage={"email_vars": {"job_summary": "fallen tree", "location_town": "Newton Abbot"}},
        constraints={"needed_by": "Friday"},
    )

    draft = build_quote_request(request, supplier)

    assert "r-0042" not in draft.subject
    assert "ref r-0042" in draft.body
    assert "Newton Abbot" in draft.body
    assert "Friday" in draft.body
    assert draft.to == "info@example.com"


def test_build_quote_request_can_use_procurement_gateway():
    supplier = Supplier(id="s-1", name="Westcountry Tree Care", email="info@example.com")
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+01:00",
        raw_need="Fallen tree needs cutting and chipping",
        triage={"email_vars": {"job_summary": "fallen tree", "location_town": "Newton Abbot"}},
        constraints={"needed_by": "Friday"},
    )
    gateway = _Gateway()

    draft = build_quote_request(request, supplier, gateway=gateway)

    assert draft.body == "Model-written supplier note.\n\nref r-0042"
    assert gateway.calls[0]["role"] == "outreach"
    prompt_text = gateway.calls[0]["messages"][0]["content"]
    assert "Never fabricate numbers" in prompt_text
    assert "Newton Abbot" in prompt_text
    assert "Westcountry Tree Care" in prompt_text


def test_create_request_drafts_persists_thread_ids_without_asked_at():
    suppliers = _Store(
        [
            Supplier(id="s-1", name="Email Co", email="quotes@example.com"),
            Supplier(id="s-2", name="Phone Co", phone="+441626000001"),
            Supplier(id="s-3", name="Excluded Co", email="no@example.com"),
        ]
    )
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+01:00",
        raw_need="Tree chipping",
        triage={"email_vars": {"job_summary": "tree chipping", "location_town": "Newton Abbot"}},
        shortlist=[
            ShortlistEntry(supplier_id="s-1", rank=1),
            ShortlistEntry(supplier_id="s-2", rank=2),
            ShortlistEntry(supplier_id="s-3", rank=3, excluded=True),
        ],
    )
    requests = _Store([request])
    client = _DraftClient()

    report = create_request_drafts(
        request_id="r-0042",
        suppliers=suppliers,
        requests=requests,
        draft_client=client,
        now=dt.datetime(2026, 6, 10, 16, 2, tzinfo=dt.UTC),
        gateway=_Gateway(),
    )

    assert report == {"drafted": 1, "skipped": 2}
    assert client.calls[0]["label"] == "xsource/outbox"
    saved = requests.get("r-0042")
    assert saved.shortlist[0].outreach == {
        "mode": "email",
        "status": "draft_ready",
        "draft_id": "d-1",
        "message_id": "m-1",
        "thread_id": "t-1",
        "drafted_at": "2026-06-10T16:02:00+00:00",
        "label": "xsource/outbox",
    }
    assert "asked_at" not in saved.shortlist[0].outreach
    assert saved.shortlist[1].outreach == {"mode": "call", "status": "to_call"}
    assert saved.shortlist[2].outreach == {}


def test_create_request_drafts_writes_provenance(tmp_path):
    suppliers = _Store([Supplier(id="s-1", name="Email Co", email="quotes@example.com")])
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+01:00",
        raw_need="Tree chipping",
        triage={"email_vars": {"job_summary": "tree chipping", "location_town": "Newton Abbot"}},
        shortlist=[ShortlistEntry(supplier_id="s-1", rank=1)],
    )
    requests = _Store([request])

    create_request_drafts(
        request_id="r-0042",
        suppliers=suppliers,
        requests=requests,
        draft_client=_DraftClient(),
        now=dt.datetime(2026, 6, 10, 16, 2, tzinfo=dt.UTC),
        provenance_dir=tmp_path,
        gateway=_Gateway(),
    )

    path = tmp_path / "r-0042-s-1-d-1.json"
    assert path.exists()
    text = path.read_text()
    assert "tree chipping" in text
    assert "draft_ready" in text
    assert "thread_id" in text


def test_procurement_stance_is_composed_with_shared_constitution():
    prompt = build_outreach_system_prompt()

    assert "Never fabricate numbers" in prompt
    assert "casual, friendly, British" in prompt
    assert "never the full address" in prompt


def test_model_subject_is_used_unless_it_is_long_or_carries_the_reference():
    supplier = Supplier(id="s-1", name="Sparks", email="info@example.com")
    request = Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+01:00",
        raw_need="EICR for the whole building",
        triage={"category": "Electrician", "email_vars": {"job_summary": "x" * 200}},
    )

    class Gateway:
        def __init__(self, subject):
            self.subject = subject

        def complete_structured(self, messages, schema, role="research"):
            return {"subject": self.subject, "body": "Hi there\n\nref r-0042"}

    assert build_quote_request(request, supplier, Gateway("EICR quote?")).subject == "EICR quote?"
    for bad in ("EICR quote r-0042", "y" * 81, ""):
        subject = build_quote_request(request, supplier, Gateway(bad)).subject
        assert subject == "Quote please: Electrician"


def _request(town="Newton Abbot"):
    email_vars = {"job_summary": "fallen tree"}
    if town:
        email_vars["location_town"] = town
    return Request(
        id="r-0042",
        created_at="2026-06-10T15:58:00+01:00",
        raw_need="Fallen tree needs cutting and chipping",
        triage={"email_vars": email_vars},
        constraints={"needed_by": "Friday"},
    )


def _supplier():
    return Supplier(id="s-1", name="Westcountry Tree Care", email="info@example.com")


def test_drafts_are_signed_with_the_configured_name(monkeypatch):
    monkeypatch.delenv("XSOURCE_OPERATOR_DISPLAY_NAME", raising=False)
    body = build_quote_request(_request(), _supplier()).body
    assert "Cheers,\nGareth" in body and "Milo" not in body


def test_sign_off_follows_the_env_override(monkeypatch):
    monkeypatch.setenv("XSOURCE_OPERATOR_DISPLAY_NAME", "Jane")
    assert "Cheers,\nJane" in build_quote_request(_request(), _supplier()).body


def test_prompt_names_the_configured_operator(monkeypatch):
    monkeypatch.delenv("XSOURCE_OPERATOR_DISPLAY_NAME", raising=False)
    gateway = _Gateway()
    build_quote_request(_request(), _supplier(), gateway=gateway)
    prompt = gateway.calls[0]["messages"][0]["content"]
    assert "Operator first name: Gareth" in prompt and "Milo" not in prompt


def test_no_town_never_says_near_the_area(monkeypatch):
    monkeypatch.delenv("XSOURCE_HOME_TOWN", raising=False)
    body = build_quote_request(_request(town=None), _supplier()).body
    assert "near the area" not in body and "We're a local care home" in body


def test_empty_home_town_counts_as_unset(monkeypatch):
    monkeypatch.setenv("XSOURCE_HOME_TOWN", "")
    body = build_quote_request(_request(town=None), _supplier()).body
    assert "We're a local care home" in body


def test_home_town_is_used_when_triage_has_none(monkeypatch):
    monkeypatch.setenv("XSOURCE_HOME_TOWN", "Exampleton")
    assert "near Exampleton" in build_quote_request(_request(town=None), _supplier()).body


def test_triage_town_beats_home_town(monkeypatch):
    monkeypatch.setenv("XSOURCE_HOME_TOWN", "Exampleton")
    body = build_quote_request(_request(town="Newton Abbot"), _supplier()).body
    assert "near Newton Abbot" in body and "Exampleton" not in body
