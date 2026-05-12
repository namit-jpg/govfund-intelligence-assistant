from io import StringIO

import pytest

from backend.services.tec_parser import parse_tec_file, preview_tec_file


def test_parse_tec_file_rejects_missing_required_columns():
    csv_data = StringIO("name,city\nJane Doe,Austin\n")
    with pytest.raises(ValueError) as exc:
        parse_tec_file(csv_data, "bad.csv")
    assert "mappings" in str(exc.value)


def test_parse_tec_file_preserves_bad_row_for_quality_flags():
    csv_data = StringIO(
        "transaction_date,amount,committee_name,contributor_name\n"
        "not-a-date,1200,Committee A,Jane Doe\n"
    )
    parsed = parse_tec_file(csv_data, "tec.csv")
    assert parsed.records[0]["transaction_date"] == "not-a-date"


def test_preview_tec_file_detects_mapping():
    csv_data = StringIO("transaction_date,amount,filer_name\n2024-01-01,10,Committee A\n")
    preview = preview_tec_file(csv_data, "tec.csv")
    assert preview["mapping"]["transaction_date"] == "transaction_date"
