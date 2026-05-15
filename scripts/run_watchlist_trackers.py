from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.db import SessionLocal, init_database
    from backend.services.tracker_service import run_due_watchlists

    init_database()
    db = SessionLocal()
    try:
        results = run_due_watchlists(db)
        print(f"watchlist_tracker_runs={len(results)}")
        for result in results:
            print(
                "watchlist_run "
                f"id={result.get('id')} "
                f"watchlist_id={result.get('watchlist_id')} "
                f"status={result.get('status')} "
                f"matched={result.get('matched_count')} "
                f"raw={result.get('raw_records_fetched')} "
                f"inserted={result.get('inserted_count')} "
                f"duplicates={result.get('duplicate_count')}"
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
