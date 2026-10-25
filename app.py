"""Small standard-library web wrapper for the SolveEase research prototype.

This is a dashboard and manual trigger, not a continuous worker or a trading
system. Public-source records are unverified leads, not verified opportunities.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# IMPORTANT: The actual package directory is named "solveease".
from solveease.models import Opportunity, utc_now_iso
from solveease.robot import ArbitrageRobot
from solveease.sources import (
    fetch_github_issues,
    fetch_stackexchange_questions,
    fetch_grants_gov,
)
from solveease.store import SQLiteLedger


APP_VERSION = "1.2.0"

DB_PATH = os.environ.get(
    "SOLVEEASE_DB_PATH",
    "solveease_ledger.sqlite3",
).strip() or "solveease_ledger.sqlite3"

RUN_TOKEN = os.environ.get("SOLVEEASE_RUN_TOKEN", "").strip()

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "10000"))

MAX_REQUEST_BODY_BYTES = 1024
SOURCE_TIMEOUT_NOTE = (
    "A source may be unavailable or rate-limited. Check the run report."
)

RUN_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()

STATE = {
    "app_version": APP_VERSION,
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "summary": "No research run has been started.",
    "sources": [],
    "records_saved": 0,
    "financially_unscored": 0,
    "errors": [],
}


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolveEase · Global Opportunity Research</title>
<style>
:root {
  color-scheme: dark;
  --bg: #10151d;
  --panel: #1a2330;
  --text: #eef3f8;
  --muted: #a8b5c5;
  --line: #344255;
  --accent: #7dd3fc;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 system-ui, -apple-system, sans-serif;
}
main {
  max-width: 900px;
  margin: auto;
  padding: 22px 16px 48px;
}
h1 { font-size: 1.55rem; margin: .2rem 0; }
h2 { font-size: 1.15rem; }
p { color: var(--muted); }
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px;
  margin: 16px 0;
}
button {
  background: var(--accent);
  color: #082032;
  font-weight: 700;
  border: 0;
  border-radius: 10px;
  padding: 12px 16px;
  font-size: 1rem;
  cursor: pointer;
}
button:disabled { opacity: .55; cursor: wait; }
.pill {
  display: inline-block;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px 9px;
  color: var(--muted);
  font-size: .82rem;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #0b1017;
  padding: 12px;
  border-radius: 9px;
  color: #dce8f4;
}
input {
  width: 100%;
  padding: 11px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: #0b1017;
  color: var(--text);
}
.warning {
  border-left: 3px solid #fbbf24;
  padding-left: 12px;
}
a { color: var(--accent); }
</style>
</head>
<body>
<main>
  <p class="pill">SOLVEEASE · GLOBAL OPPORTUNITY RESEARCH</p>
  <h1>Public opportunity research dashboard</h1>
  <p>
    Collect a small sample of public issue, question and grant records.
    These records are leads, not verified buyers, arbitrage profits or
    guaranteed income.
  </p>

  <section class="panel">
    <h2>Research run</h2>
    <p id="status">Loading status…</p>

    <label for="token">
      Run token (if configured in Render):
    </label>
    <p>
      <input
        id="token"
        type="password"
        autocomplete="current-password"
        placeholder="Paste SOLVEEASE_RUN_TOKEN"
      >
    </p>

    <button id="run">Run public-source research</button>
    <p id="message" aria-live="polite"></p>
  </section>

  <section class="panel">
    <h2>Latest run report</h2>
    <pre id="report">Loading…</pre>
  </section>

  <section class="panel warning">
    <strong>Evidence boundary</strong>
    <p>
      This prototype does not execute trades, spend money, verify payments,
      or prove commercial demand. Leads without verified success probability
      and net value remain financially unscored. A free Render service may
      sleep, and its local database may not survive replacement or
      redeployment.
    </p>
  </section>

<script>
const statusEl = document.getElementById("status");
const reportEl = document.getElementById("report");
const messageEl = document.getElementById("message");
const runButton = document.getElementById("run");

async function refresh() {
  try {
    const response = await fetch("/api/status", {
      cache: "no-store"
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Status request failed");
    }

    statusEl.textContent =
      `Status: ${data.status} · Saved records: ${data.records_saved}` +
      ` · Last finished: ${data.finished_at || "never"}`;

    reportEl.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    statusEl.textContent = "Could not load status: " + error.message;
    reportEl.textContent = "Status is currently unavailable.";
  }
}

runButton.addEventListener("click", async () => {
  runButton.disabled = true;
  messageEl.textContent =
    "Research running. This may take some time.";

  try {
    const token = document.getElementById("token").value.trim();
    const headers = {};

    if (token) {
      headers["X-SolveEase-Token"] = token;
    }

    const response = await fetch("/api/run", {
      method: "POST",
      headers,
      cache: "no-store"
    });

    const data = await response.json();

    messageEl.textContent =
      data.message || data.error || `HTTP ${response.status}`;

    await refresh();
  } catch (error) {
    messageEl.textContent = "Request failed: " + error.message;
  } finally {
    runButton.disabled = false;
  }
});

refresh();
</script>
</main>
</body>
</html>'''


def now_iso() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def json_bytes(data: dict) -> bytes:
    """Serialize JSON consistently."""
    return json.dumps(
        data,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def update_state(**changes) -> None:
    """Apply state changes safely across request threads."""
    with STATE_LOCK:
        STATE.update(changes)


def get_state() -> dict:
    """Return a snapshot of the current state."""
    with STATE_LOCK:
        return dict(STATE)


def run_research() -> dict:
    """Collect public leads and pass them through the research ledger."""

    if not RUN_LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "message": "A research run is already in progress.",
        }

    started = now_iso()

    update_state(
        status="running",
        started_at=started,
        finished_at=None,
        summary="Collecting public records.",
        sources=[],
        records_saved=0,
        financially_unscored=0,
        errors=[],
    )

    source_calls = [
        (
            "GitHub Issues",
            lambda: fetch_github_issues(
                query="is:open",
                per_page=5,
            ),
        ),
        (
            "Stack Exchange",
            lambda: fetch_stackexchange_questions(
                tagged="python",
                pagesize=5,
            ),
        ),
        (
            "Grants.gov",
            lambda: fetch_grants_gov(
                query="small business",
                rows=5,
            ),
        ),
    ]

    records = []
    source_summary = []
    errors = []

    try:
        # Collect each source independently so one failure does not
        # prevent attempts against the remaining sources.
        for label, fetch in source_calls:
            try:
                found = fetch()
                found = list(found or [])
                records.extend(found)

                source_summary.append({
                    "source": label,
                    "status": "ok",
                    "records_returned": len(found),
                })

            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"

                errors.append({
                    "source": label,
                    "error": message[:500],
                })

                source_summary.append({
                    "source": label,
                    "status": "error",
                    "records_returned": 0,
                    "error": message[:300],
                })

        # Convert source records to the existing internal model.
        opportunities = []

        for record in records:
            external_id = getattr(record, "external_id", None)
            title = getattr(record, "title", None)

            if not external_id or not title:
                continue

            source = str(getattr(record, "source", "unknown"))
            note = getattr(record, "note", None)
            url = getattr(record, "url", None)

            opportunities.append(
                Opportunity(
                    opportunity_id=f"{source}:{external_id}",
                    source=source,
                    title=str(title)[:500],
                    url=str(url or ""),
                    discovered_at=utc_now_iso(),
                    payer=None,
                    deliverable="Requires manual validation",
                    permission_status="unknown",
                    eligibility=None,
                    resource_requirements=None,
                    success_probability=None,
                    success_net_value_usd=None,
                    failure_loss_usd=0.0,
                    remaining_cost_usd=0.0,
                    evidence_status="public_lead_unverified",
                    state="discovered",
                    notes=(
                        str(note)[:2000]
                        if note
                        else (
                            "Public listing only. Buyer demand, permission "
                            "and monetization remain unverified."
                        )
                    ),
                )
            )

        saved = 0
        unscored = 0

        ledger = SQLiteLedger(DB_PATH)

        try:
            robot = ArbitrageRobot(
                ledger,
                threshold_usd=2.0,
                starting_capital_usd=0.0,
            )

            results = robot.process(opportunities) or []
            saved = len(results)

            # Retain the existing screening field expected by this
            # prototype; fail visibly if the result schema is different.
            for item in results:
                screening = item.get("screening", {})
                if not screening.get("scoreable", False):
                    unscored += 1

        finally:
            ledger.close()

        finished = now_iso()

        status = (
            "complete_with_source_errors"
            if errors
            else "complete"
        )

        note = (
            "Public leads were collected and screened. No buyer demand, "
            "profit, payment, or arbitrage outcome is verified."
        )

        report = {
            "app_version": APP_VERSION,
            "status": status,
            "started_at": started,
            "finished_at": finished,
            "sources": source_summary,
            "records_saved": saved,
            "financially_unscored": unscored,
            "errors": errors,
            "note": note,
        }

        update_state(
            status=status,
            started_at=started,
            finished_at=finished,
            summary=note,
            sources=source_summary,
            records_saved=saved,
            financially_unscored=unscored,
            errors=errors,
        )

        return {
            "ok": True,
            "message": (
                f"Run finished. Saved {saved} records; "
                f"{unscored} remain financially unscored."
            ),
            "report": report,
        }

    except Exception as exc:
        finished = now_iso()
        message = f"{type(exc).__name__}: {exc}"

        update_state(
            status="error",
            finished_at=finished,
            summary="Research run failed.",
            errors=[{"error": message[:500]}],
        )

        print(
            f"[SolveEase] Research error: {message}",
            flush=True,
        )

        return {
            "ok": False,
            "message": f"Research run failed: {message[:300]}",
        }

    finally:
        RUN_LOCK.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "SolveEaseResearch/1.2"

    def _send(
        self,
        status_code: int,
        body: bytes,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The client may close its connection before the response
            # has finished. This should not crash the service.
            pass

    def _send_json(self, status_code: int, data: dict) -> None:
        self._send(status_code, json_bytes(data))

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._send(
                200,
                HTML.encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return

        if path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "solveease",
                    "version": APP_VERSION,
                },
            )
            return

        if path == "/api/status":
            state = get_state()
            state["database_path"] = DB_PATH
            state["run_token_configured"] = bool(RUN_TOKEN)
            self._send_json(200, state)
            return

        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path != "/api/run":
            self._send_json(404, {"error": "not_found"})
            return

        # Do not allow an unprotected public endpoint to start source
        # collection. Configure this variable in Render's environment.
        if not RUN_TOKEN:
            self._send_json(
                503,
                {
                    "error": "run_token_not_configured",
                    "message": (
                        "Set SOLVEEASE_RUN_TOKEN in the Render "
                        "environment before starting a research run."
                    ),
                },
            )
            return

        supplied = self.headers.get("X-SolveEase-Token", "")

        if not hmac.compare_digest(supplied, RUN_TOKEN):
            self._send_json(
                401,
                {
                    "error": "unauthorized",
                    "message": "The run token is missing or incorrect.",
                },
            )
            return

        # This endpoint currently needs no request body. Reject large
        # bodies instead of accepting arbitrary data.
        content_length = self.headers.get("Content-Length", "0")

        try:
            body_size = int(content_length)
        except (TypeError, ValueError):
            self._send_json(
                400,
                {"error": "invalid_content_length"},
            )
            return

        if body_size < 0 or body_size > MAX_REQUEST_BODY_BYTES:
            self._send_json(
                413,
                {"error": "request_body_too_large"},
            )
            return

        result = run_research()
        status_code = 200 if result.get("ok") else 409
        self._send_json(status_code, result)

    def log_message(self, fmt: str, *args) -> None:
        print("[SolveEase] " + (fmt % args), flush=True)


def main() -> None:
    """Start the HTTP server and select a writable SQLite location."""
    global DB_PATH

    configured_path = DB_PATH

    try:
        database = Path(configured_path)
        database.parent.mkdir(parents=True, exist_ok=True)

        # Verify that the database directory is writable.
        probe = database.parent / ".solveease_write_test"
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)

    except OSError as exc:
        print(
            f"[SolveEase] Database path {configured_path!r} is not "
            f"writable: {exc}. Falling back to a local database.",
            flush=True,
        )

        DB_PATH = "solveease_ledger.sqlite3"

        try:
            Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        except OSError as fallback_exc:
            raise RuntimeError(
                f"Cannot prepare fallback database path {DB_PATH!r}: "
                f"{fallback_exc}"
            ) from fallback_exc

    server = ThreadingHTTPServer((HOST, PORT), Handler)

    print(
        f"SolveEase dashboard v{APP_VERSION} listening on {HOST}:{PORT}",
        flush=True,
    )
    print(f"[SolveEase] SQLite database path: {DB_PATH}", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[SolveEase] Shutdown requested.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
