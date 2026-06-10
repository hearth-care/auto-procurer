"""Spec global AC: Gmail send endpoints must not exist in xsource."""

import pathlib
import re

FORBIDDEN = re.compile(
    r"(drafts\(\)\.send|messages\(\)\.send|users\(\)\.messages\(\)\.send|\.send_message\()"
)


def test_no_gmail_send_call_sites():
    offenders = []
    for path in pathlib.Path("src/xsource").rglob("*.py"):
        if FORBIDDEN.search(path.read_text()):
            offenders.append(str(path))
    assert offenders == []
