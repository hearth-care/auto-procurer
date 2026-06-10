from xsource.research.companies_house import company_check

FIXTURE = {
    "items": [
        {
            "title": "TEIGN TREES & GROUNDS LTD",
            "company_status": "active",
            "date_of_creation": "2019-04-01",
            "company_number": "11912345",
        }
    ]
}


def fake_get(url, params, auth):
    fake_get.calls.append((url, params))
    return FIXTURE


fake_get.calls = []


def test_company_check_enriches():
    info = company_check("Teign Trees & Grounds", api_key="K", get_fn=fake_get)
    assert info == {"number": "11912345", "status": "active", "incorporated": "2019-04-01"}


def test_no_match_returns_none():
    def empty(url, params, auth):
        return {"items": []}

    assert company_check("Nobody", api_key="K", get_fn=empty) is None


def test_failure_degrades_to_none():
    def boom(url, params, auth):
        raise RuntimeError("down")

    assert company_check("X", api_key="K", get_fn=boom) is None
