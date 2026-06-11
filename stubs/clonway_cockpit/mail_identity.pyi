from dataclasses import dataclass

@dataclass(frozen=True)
class MailIdentity:
    address: str
    display_name: str = ""
    source: str = ""

def format_from_header(identity: MailIdentity) -> str: ...
