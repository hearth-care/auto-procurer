from dataclasses import dataclass

@dataclass
class Pill:
    label: str
    status: str
    detail: str
    level: str

@dataclass
class NeedsItem:
    title: str
    detail: str
    level: str
    capability_key: str

@dataclass
class CockpitState:
    tenant_name: str
    app_label: str
    date_label: str
    time_label: str
    pills: tuple[Pill, ...]
    needs: tuple[NeedsItem, ...]
    shelves: dict[str, str]
    toolkit_label: str
