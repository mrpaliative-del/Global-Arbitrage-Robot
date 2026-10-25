from __future__ import annotations
import json, sqlite3
from pathlib import Path
from .models import Opportunity, ScreeningResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities(
 opportunity_id TEXT PRIMARY KEY, source TEXT NOT NULL, payload_json TEXT NOT NULL,
 state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS screenings(
 id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL,
 payload_json TEXT NOT NULL, screened_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_screenings_opp ON screenings(opportunity_id);
"""

class SQLiteLedger:
    def __init__(self, path="solveease_ledger.sqlite3"):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(str(self.path),timeout=20)
        self.conn.row_factory=sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=20000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        # Backward-compatible schema upgrade from v1.
        cols={r["name"] for r in self.conn.execute("PRAGMA table_info(opportunities)")}
        if "updated_at" not in cols:
            self.conn.execute("ALTER TABLE opportunities ADD COLUMN updated_at TEXT")
            self.conn.execute("UPDATE opportunities SET updated_at=created_at WHERE updated_at IS NULL")
        self.conn.commit()
    def close(self): self.conn.close()
    def upsert_opportunity(self,o:Opportunity):
        payload=json.dumps(o.to_dict(),sort_keys=True,ensure_ascii=False)
        self.conn.execute("""INSERT INTO opportunities(opportunity_id,source,payload_json,state,created_at,updated_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(opportunity_id) DO UPDATE SET source=excluded.source,
        payload_json=excluded.payload_json,state=excluded.state,updated_at=excluded.updated_at""",
        (o.opportunity_id,o.source,payload,o.state,o.discovered_at,o.discovered_at))
        self.conn.commit()
    def add_screening(self,r:ScreeningResult):
        self.conn.execute("INSERT INTO screenings(opportunity_id,payload_json,screened_at) VALUES(?,?,?)",
            (r.opportunity_id,json.dumps(r.to_dict(),sort_keys=True),r.screened_at))
        self.conn.commit()
    def counts(self):
        return {r[0]:r[1] for r in self.conn.execute("SELECT state,COUNT(*) FROM opportunities GROUP BY state")}
    def latest_opportunities(self,limit=100):
        rows=self.conn.execute("SELECT payload_json FROM opportunities ORDER BY updated_at DESC LIMIT ?",(max(1,min(int(limit),500)),))
        return [json.loads(r[0]) for r in rows]
