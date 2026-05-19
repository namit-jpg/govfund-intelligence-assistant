import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base


def test_openai_client_constructs_with_pinned_httpx(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from openai import OpenAI

    client = OpenAI()
    assert client is not None


def test_chat_completion_options_omit_temperature_for_gpt5_models():
    from backend.services.ai_service import _chat_completion_options

    options = _chat_completion_options("gpt-5-mini", [{"role": "user", "content": "hi"}])

    assert options["model"] == "gpt-5-mini"
    assert "temperature" not in options


def test_chat_completion_options_keep_temperature_for_legacy_models():
    from backend.services.ai_service import _chat_completion_options

    options = _chat_completion_options("gpt-4o-mini", [{"role": "user", "content": "hi"}])

    assert options["temperature"] == 0.05


def test_sparse_question_facts_use_public_context_mode_without_no_data_note():
    from backend.services.ai_service import BRIEF_SECTIONS, build_question_facts

    engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        facts = build_question_facts(db, "What are the top engineering companies connected to Tom Ramsey in 2026?")
    finally:
        db.close()

    assert facts["analysis_mode"] == "public_context_first_when_local_records_are_sparse"
    assert "coverage_note" not in facts
    assert "suggested_next_data_pull" not in facts
    assert "Coverage Limitations" not in BRIEF_SECTIONS
