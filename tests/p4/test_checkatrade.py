from __future__ import annotations

from xsource.p4.checkatrade import CheckatradeLead, CheckatradeLeadClient


def test_checkatrade_client_builds_signed_request_without_posting():
    client = CheckatradeLeadClient(partner_id="partner-1", secret="secret")
    lead = CheckatradeLead(
        request_id="r-0042",
        category="tree surgery",
        postcode="TQ12 4QQ",
        description="Tree chipping",
        contact_name="Milo",
        contact_email="milo@example.com",
    )

    req = client.build_request(lead)

    assert req.method == "POST"
    assert req.path == "/jobs"
    assert req.body["external_ref"] == "r-0042"
    assert req.headers["X-Partner-Id"] == "partner-1"
    assert req.headers["X-Signature"]


def test_checkatrade_lead_rejects_missing_contact():
    lead = CheckatradeLead(
        request_id="r-0042",
        category="tree surgery",
        postcode="TQ12 4QQ",
        description="Tree chipping",
        contact_name="",
        contact_email="",
    )

    assert lead.validate() == ["contact_name missing", "contact_email missing"]
