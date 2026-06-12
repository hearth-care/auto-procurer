"""Follow-up drafting for supplier replies."""

from __future__ import annotations

import datetime as dt

from xsource.outreach.drafts import OUTBOX_LABEL
from xsource.store.models import Request, Supplier


def build_followup_draft(
    request: Request,
    supplier: Supplier,
    *,
    operator_name: str = "Milo",
) -> dict[str, str]:
    if not supplier.email:
        raise ValueError(f"supplier {supplier.id} has no email")
    entry = next((item for item in request.shortlist if item.supplier_id == supplier.id), None)
    if entry is None:
        raise KeyError(supplier.id)
    summary = entry.reply.get("summary") or "your reply"
    body = "\n\n".join(
        [
            f"Hello {supplier.name},",
            f"Thanks for getting back to us about {request.raw_need}. I saw: {summary}",
            "Could you let me know the next useful detail so we can decide how to proceed?",
            f"Kind regards,\n{operator_name}",
            f"ref {request.id}",
        ]
    )
    return {
        "to": supplier.email,
        "subject": f"Re: {request.raw_need}",
        "body": body,
        "label": OUTBOX_LABEL,
    }


def create_followup_draft(
    request: Request,
    supplier: Supplier,
    *,
    draft_client,
    now: dt.datetime,
    operator_name: str = "Milo",
) -> dict[str, str]:
    draft = build_followup_draft(request, supplier, operator_name=operator_name)
    entry = next((item for item in request.shortlist if item.supplier_id == supplier.id), None)
    metadata = draft_client.create_draft(
        to=draft["to"],
        subject=draft["subject"],
        body=draft["body"],
        label=draft["label"],
    )
    if entry is None:
        raise KeyError(supplier.id)
    entry.outreach["followup_status"] = "draft_ready"
    entry.outreach["followup_draft_id"] = metadata["draft_id"]
    entry.outreach["followup_drafted_at"] = now.isoformat()
    return metadata
