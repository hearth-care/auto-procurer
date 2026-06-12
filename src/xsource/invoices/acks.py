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
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            records.append(
                {
                    "_malformed": "json",
                    "line": line_number,
                    "error": exc.msg,
                }
            )
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            records.append({"_malformed": "json", "line": line_number})
    return records


def _is_supported_version(raw: Any) -> bool:
    """Parse a contract_version defensively; unknown/malformed versions are ignored."""
    try:
        return int(raw) == _SUPPORTED_CONTRACT_VERSION
    except (TypeError, ValueError):
        return False


def ingest_ack_records(invoices, records: list[dict[str, Any]]) -> dict[str, int]:
    report = {"acknowledged": 0, "rejected": 0, "skipped": 0}
    for record in records:
        if not _is_supported_version(record.get("contract_version")):
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
