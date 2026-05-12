from backend.services.source_config import get_source_config


def test_source_config_defaults(monkeypatch):
    monkeypatch.delenv("FEC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = get_source_config()

    assert config["fec"]["mode"] == "api"
    assert config["fec"]["enabled"] is False
    assert config["texas"]["mode"] == "file_import"
    assert config["texas"]["enabled"] is True
    assert config["ai"]["enabled"] is False


def test_source_config_respects_secret_presence(monkeypatch):
    monkeypatch.setenv("FEC_API_KEY", "configured")
    monkeypatch.setenv("OPENAI_API_KEY", "configured")

    config = get_source_config()

    assert config["fec"]["mode"] == "api"
    assert config["fec"]["enabled"] is True
    assert config["fec"]["supports_live_refresh"] is True
    assert config["ai"]["enabled"] is True
