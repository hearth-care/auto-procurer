"""Ingest xbook AP acknowledgement records for invoice handoff."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xsource.store.models import InvoiceTransitionError

_SUPPORTED_CONTRACT_VERSION = 1


def read_ack_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def ingest_ack_records(invoices, records: list[dict[str, Any]]) -> dict[str, int]:
    report = {"acknowledged": 0, "rejected": 0, "skipped": 0}
    for record in records:
        if int(record.get("contract_version") or 0) != _SUPPORTED_CONTRACT_VERSION:
            report["skipped"] += 1
            continue
        invoice = invoices.get(str(record.get("invoice_id") or ""))
        if invoice is None:
            report["skipped"] += 1
            continue
        disposition = str(record.get("disposition") or "")
        timestamp = str(record.get("timestamp") or "")
        try:
            # A received ack proves the signal reached the consumer; advance captured→emitted.
            if invoice.status == "captured":
                invoice.transition_to("emitted", at=timestamp)
            if disposition == "accepted":
                invoice.transition_to("acknowledged", at=timestamp)
                report["acknowledged"] += 1
            elif disposition.startswith("rejected:"):
                invoice.transition_to("rejected", at=timestamp)
                invoice.handoff["rejection_reason"] = disposition.split(":", 1)[1]
                report["rejected"] += 1
            else:
                report["skipped"] += 1
                continue
        except InvoiceTransitionError:
            report["skipped"] += 1
            continue
        invoice.handoff["ack_ref"] = str(record.get("consumer_run_id") or "")
        invoice.handoff["contract_version"] = _SUPPORTED_CONTRACT_VERSION
        invoices.upsert(invoice)
    return report
