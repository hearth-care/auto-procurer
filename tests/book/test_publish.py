from xsource.book.publish import build_directory_values
from xsource.store.models import Supplier


def test_directory_values():
    rows = build_directory_values(
        [
            Supplier(
                id="s-1",
                name="A",
                categories=["heating"],
                phone="+447700900123",
                preferred=True,
                last_used="2026-01-05",
                price_history=[
                    {
                        "date": "2026-01-05",
                        "job": "boiler service",
                        "amount": 180,
                        "outcome": "used",
                    }
                ],
            ),
            Supplier(id="s-2", name="B"),
        ]
    )
    assert rows[0] == [
        "Name",
        "Categories",
        "Phone",
        "Email",
        "Preferred",
        "Last used",
        "Last price",
        "Notes",
    ]
    assert rows[1] == [
        "A",
        "heating",
        "+447700900123",
        "—",
        "yes",
        "2026-01-05",
        "£180 (boiler service)",
        "—",
    ]
    assert rows[2] == ["B", "—", "—", "—", "", "—", "—", "—"]
