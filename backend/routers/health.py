from fastapi import APIRouter
import requests
import os

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/health/fec-data")
def fec_data_test():
    key = os.getenv("FEC_API_KEY", "")
    if not key:
        return {"status": "not_configured", "message": "FEC_API_KEY is not configured."}
    try:
        r = requests.get(
            "https://api.open.fec.gov/v1/schedules/schedule_a/",
            params={
                "api_key": key,
                "per_page": 3,
                "sort": "-contribution_receipt_date",
                "contributor_employer": "Fluor",
                "two_year_transaction_period": 2024,
            },
            timeout=30,
        )
        if not r.ok:
            return {"status": r.status_code, "record_count": 0, "message": "OpenFEC health probe failed."}
        return {
            "status": r.status_code,
            "latency_ms": r.elapsed.total_seconds() * 1000,
            "record_count": len(r.json().get("results", [])),
        }
    except Exception as e:
        return {"status": "error", "message": type(e).__name__}
