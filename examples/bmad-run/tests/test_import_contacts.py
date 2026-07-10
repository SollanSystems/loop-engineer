"""Red-green-refactor tests the DoD and code-review gate on.

Fictional sample verification artifact for the vendored bmad-run fixture.
"""

import csv

from src.import_contacts import import_contacts, normalize_key


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["email", "phone"])
        writer.writeheader()
        writer.writerows(rows)


def test_case_variants_share_one_key():
    assert normalize_key("Ada@Example.com", "555-0100") == normalize_key(
        "ada@example.com", "555-0100"
    )


def test_blank_fields_never_dedupe():
    assert normalize_key("", "  ") is None


def test_first_seen_is_retained(tmp_path):
    src = tmp_path / "a.csv"
    _write_csv(src, [
        {"email": "ada@example.com", "phone": "555-0100"},
        {"email": "ADA@example.com", "phone": "555-0100"},
    ])
    roster, summary = import_contacts([str(src)], log_path=str(tmp_path / "d.log"))
    assert summary.kept == 1
    assert summary.skipped == 1
    assert roster[0]["email"] == "ada@example.com"


def test_dropped_rows_are_logged_with_line_numbers(tmp_path):
    src = tmp_path / "a.csv"
    log = tmp_path / "dedupe.log"
    _write_csv(src, [
        {"email": "ada@example.com", "phone": "555-0100"},
        {"email": "ADA@EXAMPLE.COM", "phone": "555-0100"},
    ])
    import_contacts([str(src)], log_path=str(log))
    assert f"{src}:3" in log.read_text(encoding="utf-8")


def test_second_import_adds_nothing(tmp_path):
    src = tmp_path / "a.csv"
    log = tmp_path / "dedupe.log"
    _write_csv(src, [{"email": "ada@example.com", "phone": "555-0100"}])
    roster, first = import_contacts([str(src)], log_path=str(log))
    seen = {normalize_key(r["email"], r["phone"]) for r in roster}
    _, second = import_contacts([str(src)], seen=seen, log_path=str(log))
    assert second.kept == 0
    assert second.skipped == 1
