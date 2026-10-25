from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SCANNER = ROOT / os.environ.get("TASK_GAP_SCRIPT", "run_scan.py")

TOKEN = os.environ.get("SOLVEEASE_RUN_TOKEN", "").strip()
PORT = int(os.environ.get("PORT", "10000"))
HOST = "0.0.0.0"

LOCK = threading.Lock()
STATE_LOCK = threading.Lock()

STATE = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "last_output": "",
    "error": None,
}


def now():
    return datetime.now(timezone.utc).isoformat()


def state_copy():
    with STATE_LOCK:
        return dict(STATE)


def run_scanner():
    if not LOCK.acquire(blocking=False):
        return False

    started = now()

    with STATE_LOCK:
        STATE.update({
            "status": "running",
            "started_at": started,
            "finished_at": None,
            "exit_code": None,
            "last_output": "",
            "error": None,
        })

    try:
        if not SCANNER.is_file():
            raise FileNotFoundError(
                f"Scanner not found: {SCANNER}. "
                "Check the deployed commit, branch, root directory "
                "and TASK_GAP_SCRIPT setting."
            )

        env = os.environ.copy()

        # Pass the persistent database path through to the scanner.
        if not env.get("TASK_GAP_DB"):
            env["TASK_GAP_DB"] = str(
                Path("/var/data/task_gap_hunter.sqlite3")
            )

        result = subprocess.run(
            [sys.executable, str(SCANNER)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

        output = (result.stdout or "")
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr

        with STATE_LOCK:
            STATE.update({
                "status": (
                    "complete" if result.returncode == 0
                    else "failed"
                ),
                "finished_at": now(),
                "exit_code": result.returncode,
                "last_output": output[-16000:],
                "error": (
                    None if result.returncode == 0
                    else f"Scanner exited with code {result.returncode}"
                ),
            })

    except Exception as exc:
        with STATE_LOCK:
            STATE.update({
                "status": "failed",
                "finished_at": now(),
                "error": f"{type(exc).__name__}: {exc}",
                "last_output": "",
            })

    finally:
        LOCK.release()

    return True


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SolveEase Task Gap Hunter</title>
<style>
body{font:16px/1.5 system-ui,sans-serif;max-width:900px;
margin:24px auto;padding:0 16px;background:#10151d;color:#edf3fa}
section{background:#1a2330;padding:18px;border-radius:12px;
margin:16px 0;border:1px solid #344255}
input,button{font:inherit;padding:11px;border-radius:8px;margin:5px 0}
input{width:95%;background:#0b1017;color:white;border:1px solid #526176}
button{background:#7dd3fc;border:0;font-weight:bold}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:500px;
overflow:auto;background:#0b1017;padding:12px;border-radius:8px}
small{color:#b7c5d5}
</style>
</head>
<body>
<h1>SolveEase · Task Gap Hunter</h1>
<p><small>Public opportunity discovery and evidence validation.
A collected record is not proof of AI failure or buyer demand.</small></p>
<section>
<h2>Run discovery</h2>
<p>Enter the run token configured in Render.</p>
<input id="token" type="password" autocomplete="current-password"
placeholder="SOLVEEASE_RUN_TOKEN">
<br><button id="run">Run scanner</button>
<p id="message">Loading status…</p>
</section>
<section>
<h2>Latest scan</h2>
<pre id="report">Loading…</pre>
</section>
<script>
async function refresh(){
 try{
  const r=await fetch('/api/status',{cache:'no-store'});
  const d=await r.json();
  document.getElementById('message').textContent =
    'Status: '+d.status+(d.error?' — '+d.error:'');
  document.getElementById('report').textContent=JSON.stringify(d,null,2);
 }catch(e){
  document.getElementById('message').textContent='Status unavailable: '+e;
 }
}
document.getElementById('run').onclick=async()=>{
 const b=document.getElementById('run');
 const msg=document.getElementById('message');
 b.disabled=true;
 try{
  const token=document.getElementById('token').value;
  const r=await fetch('/api/run',{
   method:'POST',
   headers: token?{'X-SolveEase-Token':token}:{}
  });
  const d=await r.json();
  msg.textContent=d.message||d.error||('HTTP '+r.status);
  await refresh();
 }catch(e){msg.textContent='Request failed: '+e}
 finally{b.disabled=false}
};
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, data, content_type="application/json"):
        body = data if isinstance(data, bytes) else data.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type + (
            "; charset=utf-8" if "charset=" not in content_type else ""
        ))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html", "/health"):
            self.send_response(200)
        else:
            self.send_response(404)

        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            return self.respond(200, PAGE, "text/html; charset=utf-8")

        if path == "/health":
            return self.respond(200, json.dumps({
                "ok": True,
                "service": "solveease-task-gap-hunter",
                "scanner_file_present": SCANNER.is_file(),
            }))

        if path == "/api/status":
            return self.respond(200, json.dumps({
                **state_copy(),
                "scanner_path": str(SCANNER),
                "scanner_file_present": SCANNER.is_file(),
            }))

        return self.respond(404, json.dumps({"error": "not_found"}))

    def do_POST(self):
        if urlparse(self.path).path != "/api/run":
            return self.respond(404, json.dumps({"error": "not_found"}))

        # Fail closed if no secret is configured.
        if not TOKEN:
            return self.respond(503, json.dumps({
                "error": "run_disabled",
                "message": "Configure SOLVEEASE_RUN_TOKEN in Render."
            }))

        supplied = self.headers.get("X-SolveEase-Token", "")
        if not hmac.compare_digest(supplied, TOKEN):
            return self.respond(401, json.dumps({
                "error": "unauthorized",
                "message": "Invalid run token."
            }))

        if not SCANNER.is_file():
            return self.respond(503, json.dumps({
                "error": "scanner_missing",
                "message": f"Scanner file not found: {SCANNER}"
            }))

        if LOCK.locked():
            return self.respond(409, json.dumps({
                "error": "already_running",
                "message": "A scan is already running."
            }))

        threading.Thread(target=run_scanner, daemon=True).start()
        return self.respond(202, json.dumps({
            "ok": True,
            "message": "Scan started. Refresh status to follow progress."
        }))

    def log_message(self, fmt, *args):
        print("[SolveEase] " + (fmt % args), flush=True)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(
        f"SolveEase dashboard listening on {HOST}:{PORT}; "
        f"scanner={SCANNER}; exists={SCANNER.is_file()}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
