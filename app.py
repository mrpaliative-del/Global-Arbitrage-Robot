"""Small standard-library web wrapper for the SolveEase research prototype.

This is a dashboard/trigger, not a continuous worker and not a trading system.
Public-source records are saved as unverified leads without invented financial scores.
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from solvease.models import Opportunity, utc_now_iso
from solvease.robot import ArbitrageRobot
from solvease.sources import fetch_github_issues, fetch_stackexchange_questions, fetch_grants_gov
from solvease.store import SQLiteLedger

DB_PATH = os.environ.get("SOLVEEASE_DB_PATH", "solveease_ledger.sqlite3")
RUN_TOKEN = os.environ.get("SOLVEEASE_RUN_TOKEN", "").strip()
RUN_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
STATE = {"status": "idle", "started_at": None, "finished_at": None, "summary": "No research run has been started.", "sources": [], "records_saved": 0, "errors": []}

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolveEase · Global Opportunity Research</title>
<style>
:root{color-scheme:dark;--bg:#10151d;--panel:#1a2330;--text:#eef3f8;--muted:#a8b5c5;--line:#344255;--accent:#7dd3fc}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:900px;margin:auto;padding:22px 16px 48px}h1{font-size:1.55rem;margin:.2rem 0}p{color:var(--muted)}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin:16px 0}
button{background:var(--accent);color:#082032;font-weight:700;border:0;border-radius:10px;padding:12px 16px;font-size:1rem;cursor:pointer}button:disabled{opacity:.55;cursor:wait}.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:3px 9px;color:var(--muted);font-size:.82rem}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1017;padding:12px;border-radius:9px;color:#dce8f4}a{color:var(--accent)}.warning{border-left:3px solid #fbbf24;padding-left:12px}
</style></head><body><main>
<p class="pill">SOLVEEASE · GLOBAL OPPORTUNITY RESEARCH</p><h1>Public opportunity research dashboard</h1>
<p>Collects a small sample of public issue, question and grant records. Records are leads—not verified buyers, arbitrage profits, or guaranteed income.</p>
<section class="panel"><h2>Research run</h2><p id="status">Loading status…</p><label for="token">Run token (if configured in Render):</label><p><input id="token" type="password" autocomplete="current-password" placeholder="Paste SOLVEEASE_RUN_TOKEN" style="width:100%;padding:11px;border-radius:8px;border:1px solid var(--line);background:#0b1017;color:var(--text)"></p><button id="run">Run public-source research</button><p id="message" aria-live="polite"></p></section>
<section class="panel"><h2>Latest run report</h2><pre id="report">Loading…</pre></section>
<section class="panel warning"><strong>Evidence boundary</strong><p>This prototype does not execute trades, spend money, verify payment, or prove commercial demand. Records with no verified success probability and net value remain financially unscored. The free Render service may sleep, and its local database may not survive replacement/redeployment.</p></section>
<script>
async function refresh(){try{const r=await fetch('/api/status');const d=await r.json();document.getElementById('status').textContent=`Status: ${d.status} · Saved records: ${d.records_saved} · Last finished: ${d.finished_at||'never'}`;document.getElementById('report').textContent=JSON.stringify(d,null,2)}catch(e){document.getElementById('status').textContent='Could not load status: '+e}}
const b=document.getElementById('run');b.addEventListener('click',async()=>{b.disabled=true;document.getElementById('message').textContent='Research running. This can take up to about a minute.';try{const token=document.getElementById('token').value;const r=await fetch('/api/run',{method:'POST',headers:token?{'X-SolveEase-Token':token}:{}});const d=await r.json();document.getElementById('message').textContent=d.message||d.error||('HTTP '+r.status);await refresh()}catch(e){document.getElementById('message').textContent='Request failed: '+e}finally{b.disabled=false}});refresh();
</script></main></body></html>'''


def run_research() -> dict:
    if not RUN_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "A research run is already in progress."}
    started = datetime.now(timezone.utc).isoformat()
    with STATE_LOCK:
        STATE.update(status="running", started_at=started, finished_at=None, summary="Collecting public records.", sources=[], records_saved=0, errors=[])
    source_calls = [
        ("GitHub Issues", lambda: fetch_github_issues(query="is:open", per_page=5)),
        ("Stack Exchange", lambda: fetch_stackexchange_questions(tagged="python", pagesize=5)),
        ("Grants.gov", lambda: fetch_grants_gov(query="small business", rows=5)),
    ]
    records, source_summary, errors = [], [], []
    try:
        for label, call in source_calls:
            try:
                found = call()
                records.extend(found)
                source_summary.append({"source": label, "status": "ok", "records_returned": len(found)})
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                errors.append({"source": label, "error": msg[:500]})
                source_summary.append({"source": label, "status": "error", "records_returned": 0, "error": msg[:300]})
        saved = 0
        ledger = SQLiteLedger(DB_PATH)
        try:
            robot = ArbitrageRobot(ledger, threshold_usd=2.0, starting_capital_usd=0.0)
            opportunities = []
            for record in records:
                if not record.external_id or not record.title:
                    continue
                opportunities.append(Opportunity(
                    opportunity_id=f"{record.source}:{record.external_id}", source=record.source,
                    title=record.title[:500], url=record.url or "", discovered_at=utc_now_iso(),
                    payer=None, deliverable="Requires manual validation", permission_status="unknown",
                    eligibility=None, resource_requirements=None, success_probability=None,
                    success_net_value_usd=None, failure_loss_usd=0.0, remaining_cost_usd=0.0,
                    evidence_status="public_lead_unverified", state="discovered",
                    notes=record.note or "Public listing only; buyer demand and monetization are unverified."))
            results = robot.process(opportunities)
            saved = len(results)
            unscored = sum(1 for item in results if not item["screening"]["scoreable"])
        finally:
            ledger.close()
        finished = datetime.now(timezone.utc).isoformat()
        report = {"status": "complete", "started_at": started, "finished_at": finished,
                  "sources": source_summary, "records_saved": saved, "financially_unscored": unscored,
                  "errors": errors,
                  "note": "Public leads were collected and screened. No buyer demand, profit, payment, or arbitrage outcome is verified."}
        with STATE_LOCK:
            STATE.update(status="complete" if not errors else "complete_with_source_errors", started_at=started,
                         finished_at=finished, summary=report["note"], sources=source_summary,
                         records_saved=saved, financially_unscored=unscored, errors=errors)
        return {"ok": True, "message": f"Run finished. Saved {saved} public lead records; {unscored} remain financially unscored.", "report": report}
    except Exception as exc:
        with STATE_LOCK:
            STATE.update(status="error", finished_at=datetime.now(timezone.utc).isoformat(), errors=[{"error": f"{type(exc).__name__}: {exc}"[:500]}])
        return {"ok": False, "message": f"Research run failed: {type(exc).__name__}: {exc}"}
    finally:
        RUN_LOCK.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "SolveEaseResearch/1.1"

    def _send(self, code: int, body: bytes, content_type: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, HTML.encode(), "text/html; charset=utf-8")
        if path == "/health":
            return self._send(200, b'{"ok":true,"service":"solveease"}')
        if path == "/api/status":
            with STATE_LOCK:
                state = dict(STATE)
            state["database_path"] = DB_PATH
            return self._send(200, json.dumps(state).encode())
        return self._send(404, b'{"error":"not_found"}')

    def do_POST(self):
        if urlparse(self.path).path != "/api/run":
            return self._send(404, b'{"error":"not_found"}')
        if RUN_TOKEN:
            supplied = self.headers.get("X-SolveEase-Token", "")
            if not hmac.compare_digest(supplied, RUN_TOKEN):
                return self._send(401, b'{"error":"unauthorized","message":"Configure an authorized request token."}')
        result = run_research()
        return self._send(200 if result.get("ok") else 409, json.dumps(result).encode())

    def log_message(self, fmt, *args):
        print("[SolveEase] " + (fmt % args), flush=True)


def main():
    port = int(os.environ.get("PORT", "10000"))
    host = os.environ.get("HOST", "0.0.0.0")
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"SolveEase web research dashboard listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
