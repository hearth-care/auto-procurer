"""Build and persist draft-only quote requests."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from clonway_cockpit.persona_soul import compose_system_prompt

from xsource.store.models import Request, Supplier

OUTBOX_LABEL = "xsource/outbox"
DEFAULT_PROVENANCE_DIR = Path.home() / ".claude-inbox" / "xsource" / "provenance"
_STANCE_PATH = Path(__file__).with_name("stance.md")
_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["body"],
    "properties": {
        "body": {
            "type": "string",
            "description": "Plain-text supplier quote request body.",
        }
    },
}


@dataclass(frozen=True)
class QuoteDraft:
    to: str
    subject: str
    body: str


def build_outreach_system_prompt() -> str:
    return compose_system_prompt(_STANCE_PATH.read_text())


def _draft_context(request: Request) -> tuple[str, str, str]:
    email_vars = dict(request.triage.get("email_vars", {}))
    job_summary = email_vars.get("job_summary") or request.raw_need
    town = email_vars.get("location_town") or request.constraints.get("location_town") or "the area"
    needed_by = request.constraints.get("needed_by") or "when convenient"
    return job_summary, town, needed_by


def _draft_prompt(request: Request, supplier: Supplier) -> str:
    job_summary, town, needed_by = _draft_context(request)
    return "\n".join(
        [
            build_outreach_system_prompt(),
            "",
            f"Request id: {request.id}",
            f"Supplier: {supplier.name}",
            f"Job summary: {job_summary}",
            f"Town: {town}",
            f"Needed by: {needed_by}",
            "",
            "Return only the email body. Include the request reference in the body footer.",
        ]
    )


def build_quote_request(request: Request, supplier: Supplier, gateway=None) -> QuoteDraft:
    if not supplier.email:
        raise ValueError(f"supplier {supplier.id} has no email")
    job_summary, town, needed_by = _draft_context(request)
    subject = f"Quote request: {job_summary}"
    if gateway is not None:
        result = gateway.complete_structured(
            [{"role": "user", "content": _draft_prompt(request, supplier)}],
            _DRAFT_SCHEMA,
            role="outreach",
        )
        return QuoteDraft(to=supplier.email, subject=subject, body=str(result["body"]).strip())
    body = "\n\n".join(
        [
            f"Hello {supplier.name},",
            (
                "Could you quote for this job please: "
                f"{job_summary}. It is in/near {town}, and we are looking for "
                f"availability around {needed_by}."
            ),
            "Please let me know the likely price, what is included, and your earliest availability.",
            "Kind regards,\nMilo",
            f"ref {request.id}",
        ]
    )
    return QuoteDraft(to=supplier.email, subject=subject, body=body)


def _write_provenance(
    *,
    provenance_dir: Path,
    request: Request,
    supplier: Supplier,
    draft: QuoteDraft,
    metadata: dict[str, str],
    outreach: dict[str, str],
) -> Path:
    provenance_dir.mkdir(parents=True, exist_ok=True)
    path = provenance_dir / f"{request.id}-{supplier.id}-{metadata['draft_id']}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event": "xsource_outreach_draft",
                "request_id": request.id,
                "supplier_id": supplier.id,
                "supplier_name": supplier.name,
                "to": draft.to,
                "subject": draft.subject,
                "body": draft.body,
                "draft_metadata": metadata,
                "outreach": outreach,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return path


def create_request_drafts(
    *,
    request_id: str,
    suppliers,
    requests,
    draft_client,
    now: dt.datetime,
    provenance_dir: Path = DEFAULT_PROVENANCE_DIR,
    gateway=None,
) -> dict[str, int]:
    request = requests.get(request_id)
    if request is None:
        raise KeyError(request_id)

    supplier_by_id = {supplier.id: supplier for supplier in suppliers.all()}
    drafted = 0
    skipped = 0
    for entry in request.shortlist:
        supplier = supplier_by_id.get(entry.supplier_id)
        if entry.excluded or supplier is None:
            skipped += 1
            continue
        if not supplier.email:
            entry.outreach = {"mode": "call", "status": "to_call"}
            skipped += 1
            continue
        draft = build_quote_request(request, supplier, gateway=gateway)
        metadata = draft_client.create_draft(
            to=draft.to,
            subject=draft.subject,
            body=draft.body,
            label=OUTBOX_LABEL,
        )
        outreach = {
            "mode": "email",
            "status": "draft_ready",
            "draft_id": metadata["draft_id"],
            "message_id": metadata["message_id"],
            "thread_id": metadata["thread_id"],
            "drafted_at": now.isoformat(),
            "label": OUTBOX_LABEL,
        }
        _write_provenance(
            provenance_dir=provenance_dir,
            request=request,
            supplier=supplier,
            draft=draft,
            metadata=metadata,
            outreach=outreach,
        )
        entry.outreach = outreach
        drafted += 1

    requests.upsert(request)
    return {"drafted": drafted, "skipped": skipped}
