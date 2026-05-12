from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.db import init_database
from backend.routers import health, ingestion, watchlists, transactions, analytics, ai, exports

app=FastAPI(title='GovFund Intelligence Assistant')
init_database()
app.include_router(health.router)
app.include_router(ingestion.router)
app.include_router(watchlists.router)
app.include_router(transactions.router)
app.include_router(analytics.router)
app.include_router(ai.router)
app.include_router(exports.router)

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.exists():
    app.mount("/app", StaticFiles(directory=_WEB_DIR, html=True), name="web_app")


@app.get("/")
def app_root():
    return RedirectResponse(url="/app/")
