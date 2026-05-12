import os


def test_openai_client_constructs_with_pinned_httpx(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from openai import OpenAI

    client = OpenAI()
    assert client is not None
