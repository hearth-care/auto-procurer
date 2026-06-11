from dataclasses import dataclass
from datetime import date, datetime

@dataclass
class Signal:
    worker: str
    kind: str
    title: str
    detail: str
    level: str
    urgency: str
    capability_key: str | None
    focus: str | None
    dedup_key: str
    emitted_at: datetime
    due_at: date | None
    source_ref: str
    source_id: str
