
from __future__ import annotations

import json
import os
from pathlib import Path

from solveease.store import SQLiteLedger


def main():
    db_path = (
        os.environ.get("SOLVEEASE_DB_PATH")
        or os.environ.get("TASK_GAP_DB")
        or "solveease_ledger.sqlite3"
    )

    ledger = SQLiteLedger(db_path)

    try:
        leads = ledger.latest_opportunities(limit=500)

        result = {
            "status": "exported",
            "database": str(Path(db_path).resolve()),
            "total_exported": len(leads),
            "leads": leads,
        }

        output = Path("solveease_leads_export.json")
        output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(json.dumps({
            "status": "success",
            "total_exported": len(leads),
            "output_file": str(output),
            "database": result["database"],
        }, indent=2))

    finally:
        ledger.close()


if __name__ == "__main__":
    main()
