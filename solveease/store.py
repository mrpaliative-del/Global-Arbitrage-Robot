
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .models import Opportunity, ScreeningResult


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities(
    opportunity_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS screenings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    screened_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_screenings_opp
ON screenings(opportunity_id);
"""


class SQLiteLedger:
    backend = "sqlite"

    def __init__(self, path="solveease_ledger.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=20)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=20000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SQLITE_SCHEMA)

        cols = {
            row["name"]
            for row in self.conn.execute(
                "PRAGMA table_info(opportunities)"
            )
        }
        if "updated_at" not in cols:
            self.conn.execute(
                "ALTER TABLE opportunities ADD COLUMN updated_at TEXT"
            )
            self.conn.execute(
                "UPDATE opportunities SET updated_at=created_at "
                "WHERE updated_at IS NULL"
            )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def upsert_opportunity(self, opportunity: Opportunity):
        payload = json.dumps(
            opportunity.to_dict(),
            sort_keys=True,
            ensure_ascii=False,
        )
        self.conn.execute(
            """
            INSERT INTO opportunities
                (opportunity_id, source, payload_json, state,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(opportunity_id) DO UPDATE SET
                source=excluded.source,
                payload_json=excluded.payload_json,
                state=excluded.state,
                updated_at=excluded.updated_at
            """,
            (
                opportunity.opportunity_id,
                opportunity.source,
                payload,
                opportunity.state,
                opportunity.discovered_at,
                opportunity.discovered_at,
            ),
        )
        self.conn.commit()

    def add_screening(self, result: ScreeningResult):
        self.conn.execute(
            """
            INSERT INTO screenings
                (opportunity_id, payload_json, screened_at)
            VALUES (?, ?, ?)
            """,
            (
                result.opportunity_id,
                json.dumps(result.to_dict(), sort_keys=True),
                result.screened_at,
            ),
        )
        self.conn.commit()

    def counts(self):
        return {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT state, COUNT(*) FROM opportunities GROUP BY state"
            )
        }

    def latest_opportunities(self, limit=100):
        limit = max(1, min(int(limit), 500))
        rows = self.conn.execute(
            """
            SELECT payload_json FROM opportunities
            ORDER BY updated_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [json.loads(row[0]) for row in rows]


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities(
    opportunity_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS screenings(
    id BIGSERIAL PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    screened_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_screenings_opp
ON screenings(opportunity_id);
"""


class PostgresLedger:
    backend = "postgres"

    def __init__(self, database_url: str):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL driver missing. Add "
                "'psycopg[binary]>=3.2,<4' to requirements.txt "
                "and redeploy."
            ) from exc

        self.conn = psycopg.connect(
            database_url,
            connect_timeout=15,
            sslmode="require",
        )
        try:
            with self.conn.cursor() as cur:
                cur.execute(POSTGRES_SCHEMA)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def upsert_opportunity(self, opportunity: Opportunity):
        payload = json.dumps(
            opportunity.to_dict(),
            sort_keys=True,
            ensure_ascii=False,
        )
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO opportunities
                        (opportunity_id, source, payload_json, state,
                         created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(opportunity_id) DO UPDATE SET
                        source=EXCLUDED.source,
                        payload_json=EXCLUDED.payload_json,
                        state=EXCLUDED.state,
                        updated_at=EXCLUDED.updated_at
                    """,
                    (
                        opportunity.opportunity_id,
                        opportunity.source,
                        payload,
                        opportunity.state,
                        opportunity.discovered_at,
                        opportunity.discovered_at,
                    ),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def add_screening(self, result: ScreeningResult):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO screenings
                        (opportunity_id, payload_json, screened_at)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        result.opportunity_id,
                        json.dumps(result.to_dict(), sort_keys=True),
                        result.screened_at,
                    ),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def counts(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT state, COUNT(*) FROM opportunities GROUP BY state"
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def latest_opportunities(self, limit=100):
        limit = max(1, min(int(limit), 500))
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload_json FROM opportunities
                ORDER BY updated_at DESC LIMIT %s
                """,
                (limit,),
            )
            return [json.loads(row[0]) for row in cur.fetchall()]


def create_ledger():
    database_url = os.environ.get("DATABASE_URL", "").strip()

    if database_url:
        if not database_url.startswith(
            ("postgres://", "postgresql://")
        ):
            raise RuntimeError(
                "DATABASE_URL must be a PostgreSQL connection URL."
            )
        return PostgresLedger(database_url)

    db_path = (
        os.environ.get("SOLVEEASE_DB_PATH")
        or os.environ.get("TASK_GAP_DB")
        or "solveease_ledger.sqlite3"
    )
    return SQLiteLedger(db_path)
