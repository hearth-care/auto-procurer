import re
from pathlib import Path

import pytest

from xsource.workbook import contract

WORKBOOK = Path("docs/contracts/gareth-workbook-v1.md")


def parse_contract_tables(path: Path) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    heading = ""
    header: list[str] | None = None
    for line in path.read_text().splitlines():
        if re.match(r"#{2,3} ", line):
            heading = line.lstrip("#").strip()
            header = None
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None:
                header = cells
                tables[heading] = []
            elif not all(re.fullmatch(r"-+", c) for c in cells):
                tables[heading].append(dict(zip(header, cells, strict=False)))
        else:
            header = None
    return tables


def test_tab_names_match_contract():
    tabs = parse_contract_tables(WORKBOOK)["Tabs"]
    assert tuple(r["Tab name"].strip("`") for r in tabs[:3]) == contract.FIXED_TABS


@pytest.mark.parametrize(
    "heading, columns",
    [
        ("Board", contract.BOARD_COLUMNS),
        ("Job tab (standard trades)", contract.JOB_COLUMNS),
        ("Black book", contract.BLACK_BOOK_COLUMNS),
        ("Log", contract.LOG_COLUMNS),
    ],
)
def test_columns_match_contract(heading, columns):
    rows = parse_contract_tables(WORKBOOK)[heading]
    assert tuple(r["Header"] for r in rows) == columns
    assert [r["Col"] for r in rows] == [chr(ord("A") + i) for i in range(len(columns))]


def test_energy_columns_replace_prices_and_shift_by_two():
    assert contract.ENERGY_JOB_COLUMNS[9:13] == (
        "Term",
        "Unit rate",
        "Standing charge",
        "Est. yearly cost",
    )
    assert contract.ENERGY_JOB_COLUMNS[13:] == contract.JOB_COLUMNS[11:]


def test_stages_match_contract():
    text = WORKBOOK.read_text()
    assert all(f"`{s}`" in text for s in contract.FIRM_STAGES + contract.JOB_STAGES)
    assert contract.FIRM_STAGES[0] == "To call" and contract.JOB_STAGES[-1] == "Done"


def test_contract_version_matches():
    assert f"contract_version: {contract.CONTRACT_VERSION}" in WORKBOOK.read_text()
