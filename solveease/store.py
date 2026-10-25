from __future__ import annotations
import json, sqlite3
from pathlib import Path
from typing import Iterable, List
from .models import Opportunity, ScreeningResult

SCHEMA = '''
CREATE TABLE IF NOT EXISTS opportunities (
  opportunity_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS screenings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  screened_at TEXT NOT NULL
);
'''

class SQLiteLedger:
    def __init__(self, path: str = "solveease_ledger.sqlite3"):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def upsert_opportunity(self, o: Opportunity):
        self.conn.execute(
            "INSERT INTO opportunities(opportunity_id, source, payload_json, state, created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(opportunity_id) DO UPDATE SET payload_json=excluded.payload_json, state=excluded.state",
            (o.opportunity_id, o.source, json.dumps(o.to_dict(), sort_keys=True), o.state, o.discovered_at),
        )
        self.conn.commit()

    def add_screening(self, r: ScreeningResult):
        self.conn.execute(
            "INSERT INTO screenings(opportunity_id, payload_json, screened_at) VALUES(?,?,?)",
            (r.opportunity_id, json.dumps(r.to_dict(), sort_keys=True), r.screened_at),
        )
        self.conn.commit()

    def counts(self):
        cur = self.conn.execute("SELECT state, COUNT(*) FROM opportunities GROUP BY state")
        return dict(cur.fetchall())
