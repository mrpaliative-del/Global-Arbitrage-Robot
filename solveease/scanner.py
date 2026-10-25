from __future__ import annotations

import hashlib
import json
import os
import traceback
from pathlib import Path

from . import sources
from .economics import screen
from .models import Opportunity, utc_now_iso
from .store import SQLiteLedger


def stable_id(source: str, record: dict) -> str:
    identity = (
        record.get("external_id")
        or record.get("url")
        or record.get("title")
        or repr(sorted(record.items()))
    )
    raw = f"{source}|{identity}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def discover():
    jobs = [
        ("github_issues", sources.fetch_github_issues),
        ("stackexchange", sources.fetch_stackexchange_questions),
        ("grants_gov", sources.fetch_grants_gov),
        ("problem_reports", sources.fetch_problem_reports),
    ]

    records = []
    source_status = {}

    for name, fetcher in jobs:
        try:
            result = fetcher()
            if not isinstance(result, list):
                raise TypeError(
                    f"{name} returned {type(result).__name__}, expected list"
                )

            valid = [
                item for item in result
                if isinstance(item, dict) and item.get("title")
            ]
            records.extend(valid)
            source_status[name] = {
                "status": "ok",
                "records": len(valid),
            }

        except Exception as exc:
            source_status[name] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "records": 0,
            }

    return records, source_status


def run_scan():
    db_path = (
        os.environ.get("SOLVEEASE_DB_PATH")
        or os.environ.get("TASK_GAP_DB")
        or "solveease_ledger.sqlite3"
    )

    ledger = SQLiteLedger(db_path)
    records, source_status = discover()

    seen = set()
    saved = 0
    screened = 0
    errors = []

    try:
        for record in records:
            try:
                source = str(record.get("source") or "unknown")
                title = str(record.get("title") or "").strip()
                url = str(record.get("url") or "").strip()

                if not title or not url:
                    continue

                oid = stable_id(source, record)
                if oid in seen:
                    continue
                seen.add(oid)

                opportunity = Opportunity(
                    opportunity_id=oid,
                    source=source,
                    title=title[:1000],
                    url=url,
                    discovered_at=utc_now_iso(),
                    permission_status="public_read_only",
                    evidence_status="public_lead_unverified",
                    state="discovered",
                    notes=str(record.get("note") or "")[:4000],
                )

                # Public listings alone do not establish buyer demand,
                # success probability, profit, or permission to reuse data.
                ledger.upsert_opportunity(opportunity)
                saved += 1

                result = screen(opportunity)
                ledger.add_screening(result)
                screened += 1

            except Exception as exc:
                errors.append(
                    f"{type(exc).__name__}: {exc}"
                )

        report = {
            "status": "complete",
            "generated_at": utc_now_iso(),
            "database": str(Path(db_path).resolve()),
            "sources": source_status,
            "records_received": len(records),
            "unique_records_processed": len(seen),
            "opportunities_saved": saved,
            "screenings_saved": screened,
            "opportunity_counts_by_state": ledger.counts(),
            "errors": errors[:30],
            "interpretation": (
                "Public leads are unverified. An unscored lead is not "
                "a validated business opportunity or proof of profit."
            ),
        }

        print(json.dumps(report, indent=2), flush=True)

        if not any(s["status"] == "ok" for s in source_status.values()):
            raise RuntimeError("All discovery sources failed.")

        return report

    finally:
        ledger.close()


if __name__ == "__main__":
    run_scan()
