CONTRACT_VERSION: int = 1

FIXED_TABS = ("Board", "Black book", "Log")

BOARD_COLUMNS = (
    "Job",
    "Job tab",
    "Stage",
    "Firms keen",
    "Quotes in",
    "Best price",
    "Best firm",
    "Next step",
    "Waiting on",
)

JOB_COLUMNS = (
    "#",
    "Firm",
    "Contact",
    "Phone",
    "Email",
    "Website",
    "Address",
    "Miles",
    "Stage",
    "First price",
    "Latest price",
    "Last contact",
    "Calls",
    "Email thread",
    "Notes",
)

ENERGY_JOB_COLUMNS = (
    *JOB_COLUMNS[:9],
    "Term",
    "Unit rate",
    "Standing charge",
    "Est. yearly cost",
    *JOB_COLUMNS[11:],
)

BLACK_BOOK_COLUMNS = (
    "Kind of job",
    "Firm",
    "Contact",
    "Phone",
    "Email",
    "Last used",
    "Last price",
    "Contract ends",
    "Notice to give",
    "Tell them by",
    "Documents",
    "How we chose them",
    "In Xero",
)

LOG_COLUMNS = ("When", "Job", "What happened")

FIRM_STAGES = (
    "To call",
    "No answer",
    "Keen",
    "Emailed",
    "Quoted",
    "Declined",
    "Booked",
    "Not chosen",
)
JOB_STAGES = ("Searching", "Calling", "Waiting for prices", "Haggling", "Booked", "Done")

KEEN_STAGES = ("Keen", "Emailed", "Quoted", "Booked")

JOB_HAND_EDITABLE = (
    "Contact",
    "Phone",
    "Email",
    "Stage",
    "First price",
    "Latest price",
    "Notes",
)
ENERGY_JOB_HAND_EDITABLE = (
    *JOB_HAND_EDITABLE,
    "Term",
    "Unit rate",
    "Standing charge",
    "Est. yearly cost",
)
BLACK_BOOK_HAND_EDITABLE = ("Contact", "Phone", "Email", "Contract ends", "Notice to give")


def price_header(energy: bool) -> str:
    return "Est. yearly cost" if energy else "Latest price"
