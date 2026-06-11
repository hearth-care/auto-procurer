from xsource.budget import Budget


def test_budget_accumulates_within_month(tmp_path):
    budget = Budget(state_dir=tmp_path, monthly_cap_gbp=10.0, month="2026-06")
    assert budget.spent() == 0.0 and budget.level() == "ok"
    budget.record(0.11)
    budget.record(7.50)
    assert Budget(tmp_path, 10.0, "2026-06").spent() == 7.61
    assert Budget(tmp_path, 10.0, "2026-06").level() == "warn"


def test_budget_blocks_at_cap(tmp_path):
    budget = Budget(tmp_path, 10.0, "2026-06")
    budget.record(10.0)
    assert budget.level() == "blocked" and budget.allow_new_run() is False


def test_new_month_resets(tmp_path):
    Budget(tmp_path, 10.0, "2026-06").record(9.0)
    assert Budget(tmp_path, 10.0, "2026-07").spent() == 0.0


class _Blob:
    def __init__(self, body: bytes):
        self.body = body
        self.uploads = []

    def exists(self):
        return True

    def download_as_bytes(self):
        return self.body

    def upload_from_filename(self, filename):
        with open(filename, "rb") as handle:
            self.body = handle.read()
        self.uploads.append(self.body)


def test_budget_can_sync_ledger_blob(tmp_path):
    blob = _Blob(b'{"spent_gbp": 2.0}')
    budget = Budget(tmp_path, 10.0, "2026-06", blob=blob)

    budget.record(1.5)

    assert budget.spent() == 3.5
    assert blob.uploads == [b'{"spent_gbp": 3.5}']
