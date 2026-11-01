# Task 2 report
Implemented schema v2 fields on Request/ShortlistEntry/Supplier, `_upgrade_v1` (entry stages and prices only; job stage "Done" if closed else "Calling" per ruling), `LogEntry`, `build_log_store` (log.jsonl). Upgrade runs when schema_version missing/<2; v2 records are untouched.
TDD: RED = ImportError for LogEntry on tests/store/test_models.py; GREEN = full suite 417 passed.
Verification: pytest -q, ruff check, ruff format --check, mypy all clean.
Files: src/xsource/store/models.py, src/xsource/wiring.py, tests/store/test_models.py.
Notes: closed without chosen supplier maps entries by reply/outreach and job to Done. Stage strings are plain (no contract import).
