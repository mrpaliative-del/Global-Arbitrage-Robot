"""SolveEase public-opportunity research dashboard. Standard-library only."""
from __future__ import annotations
import hmac, json, os, threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from solveease.models import Opportunity, utc_now_iso
from solveease.robot import ArbitrageRobot
from solveease.sources import fetch_github_issues, fetch_stackexchange_questions, fetch_grants_gov, fetch_problem_reports
from solveease.store import SQLiteLedger

DB_PATH = os.environ.get("SOLVEEASE_DB_PATH", "/var/data/solveease_ledger.sqlite3")
RUN_TOKEN = os.environ.get("SOLVEEASE_RUN_TOKEN", "").strip()
RUN_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
STATE = {"status":"idle","started_at":None,"finished_at":None,"records_saved":0,
         "financially_unscored":0,"sources":[],"errors":[],"summary":"No scan run yet."}
HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SolveEase · Opportunity Research</title>
<style>
:root{color-scheme:dark;--bg:#10151d;--panel:#1a2330;--text:#eef3f8;--muted:#a8b5c5;--line:#344255;--accent:#7dd3fc}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,sans-serif}
main{max-width:980px;margin:auto;padding:22px 16px 48px}h1{font-size:1.55rem}.muted{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin:16px 0}
button{background:var(--accent);color:#082032;font-weight:700;border:0;border-radius:10px;padding:12px 16px;font-size:1rem}
button:disabled{opacity:.5}input{width:100%;padding:11px;border-radius:8px;border:1px solid var(--line);background:#0b1017;color:var(--text)}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1017;padding:12px;border-radius:9px}
.statgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px}.stat{border:1px solid var(--line);border-radius:10px;padding:12px}
a{color:var(--accent)}.warning{border-left:3px solid #fbbf24;padding-left:12px}
</style></head><body><main><p class="muted">SOLVEEASE · GLOBAL OPPORTUNITY RESEARCH</p>
<h1>Opportunity discovery & validation dashboard</h1>
<p class="muted">Public records are leads—not verified buyers, AI failures, profits, or guaranteed income.</p>
<section class="panel"><h2>Run a scan</h2><p id="status">Loading…</p>
<label for="token">Run token (only if configured on Render)</label><p><input id="token" type="password" autocomplete="current-password" placeholder="SOLVEEASE_RUN_TOKEN"></p>
<button id="run">Run public-source scan</button><p id="message" aria-live="polite"></p></section>
<section class="panel"><h2>Current status</h2><div class="statgrid" id="stats"></div><pre id="report">Loading…</pre></section>
<section class="panel warning"><b>Evidence rules</b><p class="muted">A listing does not prove that a buyer will pay. The app does not execute trades, make purchases, call paid AI APIs, or report revenue without settlement evidence. Financial screening remains unscored when probability and net value are missing.</p></section>
<script>
async function refresh(){try{let r=await fetch('/api/status',{cache:'no-store'}),d=await r.json();
document.getElementById('status').textContent='Status: '+d.status+' · Last finished: '+(d.finished_at||'never');
document.getElementById('stats').innerHTML=[['Saved leads',d.records_saved||0],['Unscored',d.financially_unscored||0],['Source errors',(d.errors||[]).length]].map(x=>'<div class="stat"><div class="muted">'+x[0]+'</div><b>'+x[1]+'</b></div>').join('');
document.getElementById('report').textContent=JSON.stringify(d,null,2)}catch(e){document.getElementById('status').textContent='Status unavailable: '+e}}
let b=document.getElementById('run');b.onclick=async()=>{b.disabled=true;let m=document.getElementById('message');m.textContent='Scanning public sources…';
try{let t=document.getElementById('token').value;let r=await fetch('/api/run',{method:'POST',headers:t?{'X-SolveEase-Token':t}:{}});let d=await r.json();m.textContent=d.message||d.error||('HTTP '+r.status);await refresh()}catch(e){m.textContent='Request failed: '+e}finally{b.disabled=false}};
refresh();setInterval(refresh,15000);
</script></main></body></html>"""

def _state_copy():
    with STATE_LOCK:
        return dict(STATE)

def run_research():
    if not RUN_LOCK.acquire(blocking=False):
        return {"ok":False,"message":"A scan is already running."}
    started = utc_now_iso()
    with STATE_LOCK:
        STATE.update(status="running", started_at=started, finished_at=None, records_saved=0,
                     financially_unscored=0, sources=[], errors=[], summary="Collecting public records.")
    calls = [
        ("GitHub Issues", lambda: fetch_github_issues(query='is:open "manual workaround"', per_page=10)),
        ("Stack Exchange", lambda: fetch_stackexchange_questions(tagged="python", pagesize=10)),
        ("Grants.gov", lambda: fetch_grants_gov(query="small business", rows=10)),
        ("Public problem reports", fetch_problem_reports),
    ]
    all_records, source_report, errors = [], [], []
    try:
        for name, fn in calls:
            try:
                found = fn()
                all_records.extend(found)
                source_report.append({"source":name,"status":"ok","records_returned":len(found)})
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"[:400]
                errors.append({"source":name,"error":message})
                source_report.append({"source":name,"status":"error","records_returned":0,"error":message})
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        ledger = SQLiteLedger(DB_PATH)
        try:
            robot = ArbitrageRobot(ledger, threshold_usd=2.0, starting_capital_usd=0.0)
            opportunities = []
            for r in all_records:
                if not r.get("external_id") or not r.get("title"):
                    continue
                opportunities.append(Opportunity(
                    opportunity_id=f"{r['source']}:{r['external_id']}", source=r["source"],
                    title=str(r["title"])[:500], url=str(r.get("url") or ""),
                    discovered_at=utc_now_iso(), payer=None,
                    deliverable="Requires independent manual validation",
                    permission_status="unknown", eligibility=None, resource_requirements=None,
                    success_probability=None, success_net_value_usd=None,
                    failure_loss_usd=0.0, remaining_cost_usd=0.0,
                    evidence_status="public_lead_unverified", state="discovered",
                    notes=str(r.get("note") or "Public record only; no buyer or monetization evidence verified.")[:1200]))
            results = robot.process(opportunities)
            saved = len(results)
            unscored = sum(1 for x in results if not x["screening"]["scoreable"])
            counts = ledger.counts()
        finally:
            ledger.close()
        finished = utc_now_iso()
        with STATE_LOCK:
            STATE.update(status="complete_with_source_errors" if errors else "complete",
                         finished_at=finished, records_saved=saved, financially_unscored=unscored,
                         sources=source_report, errors=errors, ledger_counts=counts,
                         summary="Scan completed. Records are unverified leads; no revenue or buyer demand is verified.")
        return {"ok":True,"message":f"Scan complete: {saved} lead records processed; {unscored} financially unscored.",
                "sources":source_report,"errors":errors}
    except Exception as exc:
        message=f"{type(exc).__name__}: {exc}"[:500]
        with STATE_LOCK:
            STATE.update(status="error",finished_at=utc_now_iso(),errors=errors+[{"error":message}],summary=message)
        return {"ok":False,"message":"Scan failed: "+message}
    finally:
        RUN_LOCK.release()

class Handler(BaseHTTPRequestHandler):
    server_version = "SolveEaseResearch/2.0"
    def _send(self, code, body, content_type="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        path=urlparse(self.path).path
        if path in ("/","/index.html"): return self._send(200,HTML,"text/html; charset=utf-8")
        if path=="/health": return self._send(200,json.dumps({"ok":True,"service":"solveease","version":"2.0"}))
        if path=="/api/status": return self._send(200,json.dumps({**_state_copy(),"database_path":DB_PATH}))
        return self._send(404,{"error":"not_found"})
    def do_POST(self):
        if urlparse(self.path).path!="/api/run": return self._send(404,{"error":"not_found"})
        # Fail closed on a public deployment: never expose a public scan trigger without a token.
        if not RUN_TOKEN:
            return self._send(503,{"error":"run_disabled","message":"Set SOLVEEASE_RUN_TOKEN in the Render environment to enable scan triggers."})
        supplied=self.headers.get("X-SolveEase-Token","")
        if not hmac.compare_digest(supplied,RUN_TOKEN):
            return self._send(401,{"error":"unauthorized","message":"The run token is missing or invalid."})
        result=run_research()
        return self._send(200 if result.get("ok") else 409,result)
    def log_message(self, fmt, *args):
        print("[SolveEase] "+(fmt % args),flush=True)

def main():
    port=int(os.environ.get("PORT","10000"))
    host=os.environ.get("HOST","0.0.0.0")
    Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer((host,port),Handler)
    print(f"SolveEase dashboard v2.0 listening on {host}:{port}; DB={DB_PATH}",flush=True)
    server.serve_forever()

if __name__=="__main__":
    main()
