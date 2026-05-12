from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp.name}"
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["FEC_API_KEY"] = ""

    from backend import models  # noqa: F401
    from backend.db import SessionLocal, init_database
    from backend.services.ai_service import generate_brief
    from backend.services.export_service import build_excel_export
    from backend.services.fec_client import build_fec_request_params
    from backend.services.normalizer import tag_transaction_topics
    from backend.services.repository import insert_records, serialize_model
    from backend.services.tec_parser import parse_tec_file, preview_tec_file

    init_database()
    db = SessionLocal()
    try:
        params = build_fec_request_params(
            {"contributor_employer": "ACME", "per_page": 100, "max_records": 250},
            api_key=None,
        )
        assert "api_key" not in params
        assert params["contributor_employer"] == "ACME"

        record = {
            "source_record_id": "SMOKE-FEC-1",
            "transaction_id": "T1",
            "transaction_type": "INDIVIDUAL_CONTRIBUTION",
            "transaction_date": "2024-01-15",
            "amount": 100.0,
            "contributor_name": "Jane Public",
            "contributor_employer": "Acme Construction LLC",
            "recipient_name": "Friends of Infrastructure",
            "committee_name": "Friends of Infrastructure",
            "description": "Infrastructure committee receipt",
            "_raw_payload": {"sub_id": "SMOKE-FEC-1"},
        }
        first = insert_records(db, "FEC", [record])
        second = insert_records(db, "FEC", [record])
        assert first["inserted_count"] == 1
        assert second["duplicate_count"] == 1

        tags = tag_transaction_topics({"recipient_name": "Citizens for Roads and Water"})
        assert {"Roads", "Water"} & {item["tag"] for item in tags}

        fixture = Path("tests/fixtures/tec_tiny.csv").read_bytes()
        preview = preview_tec_file(io.BytesIO(fixture), "tec_tiny.csv")
        assert preview["mapping"]["transaction_date"]
        parsed = parse_tec_file(io.BytesIO(fixture), "tec_tiny.csv")
        assert parsed.records and parsed.records[0]["source_system"] == "TEC"

        ai = generate_brief(db, "Summarize the records", {}, "custom_question")
        assert ai["mode"] == "disabled"
        assert "Mock" not in ai.get("message", "")

        rows = [serialize_model(row) for row in db.query(models.NormalizedTransaction).all()]
        workbook = build_excel_export(
            {"total_records": len(rows)},
            [],
            [],
            [],
            rows,
            audit_logs=[],
            data_quality_flags=[],
            raw_records=[],
        )
        assert workbook.getbuffer().nbytes > 1000
    finally:
        db.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    print("smoke_test: ok")


if __name__ == "__main__":
    main()
