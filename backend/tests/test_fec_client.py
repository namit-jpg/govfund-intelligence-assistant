import pytest

from backend.services.fec_client import (
    FECValidationError,
    build_fec_request_params,
    redact_query,
    sanitize_fec_error,
    validate_fec_query,
)


def test_build_fec_request_params_formats_filters_without_key():
    params = build_fec_request_params(
        {
            "min_date": "2025-01-01",
            "max_date": "2026-12-31",
            "contributor_state": "TX",
            "contributor_employer": "ACME",
            "cycle": "2026",
        }
    )

    assert params["two_year_transaction_period"] == ["2026"]
    assert params["min_date"] == "01/01/2025"
    assert params["max_date"] == "12/31/2026"
    assert params["contributor_state"] == "TX"
    assert params["contributor_employer"] == "ACME"
    assert "api_key" not in params


def test_redact_query_hides_api_key():
    redacted = redact_query(build_fec_request_params({"per_page": 10}, api_key="secret"))

    assert redacted["api_key"] == "[REDACTED]"


def test_validate_fec_query_rejects_broad_query_without_cycle():
    with pytest.raises(FECValidationError):
        validate_fec_query({"contributor_state": "TX", "per_page": 100})


def test_validate_fec_query_allows_single_cycle():
    validate_fec_query({"contributor_state": "TX", "two_year_transaction_period": "2024"})


def test_sanitize_fec_error_removes_api_key(monkeypatch):
    monkeypatch.setenv("FEC_API_KEY", "secret-key")
    message = sanitize_fec_error("400 for url https://x.test/?api_key=secret-key&per_page=1")
    assert "secret-key" not in message
    assert "api_key=" not in message
