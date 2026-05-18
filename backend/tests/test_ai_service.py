import os


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
