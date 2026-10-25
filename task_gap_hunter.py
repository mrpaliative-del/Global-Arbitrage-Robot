#!/usr/bin/env python3
"""SolveEase Task Gap Hunter — standard-library-only discovery prototype.

Discovers public signals of recurring, poorly-served tasks. It does NOT claim
that an AI failure or a buyer's willingness to pay is proven; those are separate
signals requiring verification. No task is claimed, submitted, or paid for.
"""
from __future__ import annotations
import email.utils
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable

APP_VERSION = "0.1.0"
USER_AGENT = "SolveEase-TaskGapHunter/0.1 (+public-data research; contact: configured by operator)"
DEFAULT_DB = os.getenv("TASK_GAP_DB", "task_gap_hunter.sqlite3")

FAILURE_PATTERNS = {
    "repeated_failure": [r"keeps? (?:failing|breaking|getting .* wrong|making .* mistake)", r"still (?:have to|need to) (?:manually|check|fix)", r"fails? (?:to|when|on)", r"does(?:n't| not) work", r"unreliable", r"inconsistent", r"regression", r"false positive", r"false negative", r"manual workaround", r"workaround", r"misses? (?:the|a|an)", r"cannot reproduce", r"can't reproduce", r"not reproducible", r"flaky", r"edge case", r"broken"],
    "buyer_signal": [r"hiring", r"contract", r"paid task", r"bounty", r"reward", r"budget", r"rate of \$", r"\$\s?\d+", r"€\s?\d+", r"£\s?\d+", r"per accepted", r"pay(?:ing|ment)", r"purchase", r"looking for (?:someone|a freelancer|a contractor)", r"need (?:someone|a freelancer|a contractor)"],
    "recurrence": [r"every week", r"weekly", r"daily", r"recurring", r"repeat(?:ed|edly|able)?", r"each time", r"continually", r"ongoing", r"at scale", r"hundreds of", r"thousands of", r"batch", r"pipeline", r"monitor(?:ing)?", r"again and again"],
    "automation_fit": [r"api", r"csv", r"json", r"spreadsheet", r"structured data", r"test(?:s|ing)?", r"logs?", r"report(?:ing)?", r"reconcile", r"compare", r"validate", r"extract", r"classify", r"crawl", r"parse", r"automate", r"script"],
}

@dataclass
class Candidate:
    source: str
    source_id: str
    title: str
    url: str
    description: str = ""
    observed_at: str = ""
    published_at: str = ""
    updated_at: str = ""
    company: str = ""
    reward_text: str = ""
    task_status: str = "unknown"
    category: str = "unclassified"
    ai_failure_score: int = 0
    recurrence_score: int = 0
    buyer_signal_score: int = 0
    automation_fit_score: int = 0
    total_score: int = 0
    evidence: str = ""
    raw_json: str = "{}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    value = html.unescape(str(value))
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def get_json(url: str, timeout: int = 18, token: str = "") -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json, application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(5_000_000)
        return json.loads(data.decode("utf-8", "replace"))


def get_text(url: str, timeout: int = 18) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(3_000_000).decode("utf-8", "replace")


def score_text(title: str, description: str) -> dict[str, Any]:
    text = f"{title} {description}".lower()
    def hit_count(key: str) -> int:
        return sum(1 for pattern in FAILURE_PATTERNS[key] if re.search(pattern, text, re.I))
    fail_hits = hit_count("repeated_failure")
    buyer_hits = hit_count("buyer_signal")
    recur_hits = hit_count("recurrence")
    auto_hits = hit_count("automation_fit")
    # Signals are intentionally capped and must not be interpreted as proof.
    fail = min(100, fail_hits * 16)
    buyer = min(100, buyer_hits * 22)
    recurrence = min(100, recur_hits * 20)
    automation = min(100, auto_hits * 18)
    # Prioritize observable pain and recurring work; buyer signal stays separately visible.
    total = round(0.35 * fail + 0.25 * recurrence + 0.20 * buyer + 0.20 * automation)
    evidence = []
    for label, hits in [("failure phrases", fail_hits), ("buyer/payment phrases", buyer_hits), ("recurrence phrases", recur_hits), ("automation-fit phrases", auto_hits)]:
        if hits:
            evidence.append(f"{label}: {hits} pattern match(es)")
    return {"ai_failure_score": fail, "recurrence_score": recurrence, "buyer_signal_score": buyer, "automation_fit_score": automation, "total_score": total, "evidence": "; ".join(evidence) or "No configured signal phrases matched; inspect manually."}


def infer_category(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    categories = [
        ("software_testing", ["bug", "test", "regression", "stack trace", "exception", "github", "repository", "code", "api failure"]),
        ("technical_seo", ["seo", "indexing", "canonical", "crawler", "crawl", "search console", "redirect", "structured data"]),
        ("data_reconciliation", ["invoice", "reconcile", "reconciliation", "duplicate transaction", "ledger", "mismatched records"]),
        ("document_verification", ["ocr", "pdf", "document extraction", "scanned document", "table extraction"]),
        ("research_monitoring", ["procurement", "tender", "grant", "deadline", "monitor", "public notice", "price comparison"]),
        ("ai_evaluation", ["llm", "model evaluation", "ai agent", "hallucination", "benchmark", "grading rubric", "eval"]),
    ]
    for category, terms in categories:
        if any(term in text for term in terms):
            return category
    return "unclassified"


def make_candidate(source: str, source_id: str, title: Any, url: Any, description: Any = "", **kwargs: Any) -> Candidate:
    title_s, desc_s, url_s = clean_text(title), clean_text(description), str(url or "").strip()
    scores = score_text(title_s, desc_s)
    reward = ""
    reward_match = re.search(r"(?:\$|USD\s?)(\s?\d[\d,.]*(?:\s?[-–]\s?\$?\d[\d,.]*)?)", f"{title_s} {desc_s}", re.I)
    if reward_match:
        reward = reward_match.group(0).strip()
    raw = kwargs.pop("raw", {})
    return Candidate(source=source, source_id=str(source_id), title=title_s[:500], url=url_s,
        description=desc_s[:12000], observed_at=utc_now(), company=clean_text(kwargs.get("company", "")),
        published_at=str(kwargs.get("published_at", "") or ""), updated_at=str(kwargs.get("updated_at", "") or ""),
        reward_text=reward, task_status=str(kwargs.get("task_status", "unknown")),
        category=infer_category(title_s, desc_s), **scores, raw_json=json.dumps(raw, ensure_ascii=False)[:50000])


def github_candidates(max_pages: int = 2, per_page: int = 50, token: str = "") -> Iterable[Candidate]:
    # Several independent query patterns broaden coverage while keeping requests bounded.
    queries = [
        'is:issue is:open ("does not work" OR "doesn\'t work" OR broken OR regression)',
        'is:issue is:open ("manual workaround" OR flaky OR "false positive" OR "false negative")',
        'is:issue is:open (bounty OR reward OR "paid task" OR "good first issue")',
        'is:issue is:open ("AI agent" OR LLM OR "model evaluation") (fails OR failure OR bug OR issue)',
    ]
    seen = set()
    for query in queries:
        for page in range(1, max_pages + 1):
            params = urllib.parse.urlencode({"q": query, "per_page": min(100, max(1, per_page)), "page": page, "sort": "updated", "order": "desc"})
            url = "https://api.github.com/search/issues?" + params
            try:
                data = get_json(url, token=token)
            except Exception as exc:
                print(f"WARN github query failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                break
            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                break
            for item in items:
                if "pull_request" in item:
                    continue
                html_url = item.get("html_url", "")
                if not html_url or html_url in seen:
                    continue
                seen.add(html_url)
                repo = (item.get("repository_url", "").rstrip("/").split("/repos/")[-1])
                body = item.get("body") or ""
                yield make_candidate("github_issues", str(item.get("id", html_url)), item.get("title"), html_url,
                    body, company=repo, published_at=item.get("created_at", ""), updated_at=item.get("updated_at", ""),
                    task_status=item.get("state", "unknown"), raw=item)
            if len(items) < min(100, max(1, per_page)):
                break
            time.sleep(1.0)  # courteous pacing for public API


def problems_api_candidates(limit: int = 100, offset: int = 0) -> Iterable[Candidate]:
    """Read public frustration/problem reports. This is demand-gap evidence, not a job feed."""
    params = urllib.parse.urlencode({"limit": min(100, max(1, limit)), "offset": max(0, offset), "sort": "momentum"})
    url = "https://problems.fru.dev/api/problems?" + params
    try:
        data = get_json(url)
    except Exception as exc:
        print(f"WARN public problem API unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return
    if isinstance(data, dict):
        items = data.get("problems", data.get("items", data.get("results", [])))
    elif isinstance(data, list):
        items = data
    else:
        items = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = item.get("statement") or item.get("title") or item.get("problem") or "Untitled problem"
        evidence_parts = [item.get("evidence", ""), item.get("summary", ""), item.get("description", "")]
        posts = item.get("posts", item.get("post_count", ""))
        momentum = item.get("momentum", "")
        extra = " ".join(str(x) for x in evidence_parts if x) + f" Posts: {posts}. Momentum: {momentum}."
        links = item.get("top_links") or item.get("links") or []
        link = item.get("url") or item.get("page_url") or (links[0].get("url", "") if links and isinstance(links[0], dict) else "")
        if not link:
            link = "https://problems.fru.dev/"
        yield make_candidate("public_problem_reports", str(item.get("id", link)), title, link, extra,
            company=item.get("company", ""), published_at=item.get("first_post", ""), updated_at=item.get("last_post", ""),
            task_status="reported_problem", raw=item)


def rss_candidates(feed_urls: list[str], timeout: int = 18) -> Iterable[Candidate]:
    for feed_url in feed_urls:
        if not feed_url.startswith(("https://", "http://")):
            print(f"WARN ignored non-http RSS URL: {feed_url}", file=sys.stderr)
            continue
        try:
            xml = get_text(feed_url, timeout=timeout)
            root = ET.fromstring(xml)
        except Exception as exc:
            print(f"WARN RSS feed failed {feed_url}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        entries = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for entry in entries:
            def child_text(names: list[str]) -> str:
                for name in names:
                    node = entry.find(name)
                    if node is not None and node.text:
                        return node.text.strip()
                return ""
            title = child_text(["title", "{http://www.w3.org/2005/Atom}title"])
            description = child_text(["description", "summary", "content", "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"])
            link = child_text(["link"])
            if not link:
                atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
                if atom_link is not None:
                    link = atom_link.attrib.get("href", "")
            published = child_text(["pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"])
            if not title or not link:
                continue
            yield make_candidate("rss", hashlib.sha256((feed_url + "|" + link).encode()).hexdigest()[:20], title, link,
                description, published_at=published, raw={"feed_url": feed_url, "title": title, "description": description, "link": link, "published": published})


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS candidates (
      fingerprint TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
      title TEXT NOT NULL, url TEXT NOT NULL, description TEXT, observed_at TEXT,
      published_at TEXT, updated_at TEXT, company TEXT, reward_text TEXT, task_status TEXT,
      category TEXT, ai_failure_score INTEGER, recurrence_score INTEGER, buyer_signal_score INTEGER,
      automation_fit_score INTEGER, total_score INTEGER, evidence TEXT, raw_json TEXT,
      first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, occurrences INTEGER NOT NULL DEFAULT 1
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(total_score DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_category ON candidates(category)")
    conn.commit()
    return conn


def fingerprint(c: Candidate) -> str:
    # Prefer canonical URL, fall back to source/id.
    base = c.url.strip().rstrip("/").lower() or f"{c.source}:{c.source_id}"
    return hashlib.sha256(base.encode()).hexdigest()


def save_candidate(conn: sqlite3.Connection, c: Candidate) -> tuple[bool, bool]:
    fp = fingerprint(c)
    now = utc_now()
    existing = conn.execute("SELECT total_score, title FROM candidates WHERE fingerprint=?", (fp,)).fetchone()
    vals = asdict(c)
    if existing:
        conn.execute("""UPDATE candidates SET source=?,source_id=?,title=?,url=?,description=?,observed_at=?,published_at=?,updated_at=?,company=?,reward_text=?,task_status=?,category=?,ai_failure_score=?,recurrence_score=?,buyer_signal_score=?,automation_fit_score=?,total_score=?,evidence=?,raw_json=?,last_seen_at=?,occurrences=occurrences+1 WHERE fingerprint=?""",
            (vals["source"], vals["source_id"], vals["title"], vals["url"], vals["description"], vals["observed_at"], vals["published_at"], vals["updated_at"], vals["company"], vals["reward_text"], vals["task_status"], vals["category"], vals["ai_failure_score"], vals["recurrence_score"], vals["buyer_signal_score"], vals["automation_fit_score"], vals["total_score"], vals["evidence"], vals["raw_json"], now, fp))
        changed = (existing["total_score"] != c.total_score or existing["title"] != c.title)
        conn.commit()
        return False, changed
    conn.execute("""INSERT INTO candidates (fingerprint,source,source_id,title,url,description,observed_at,published_at,updated_at,company,reward_text,task_status,category,ai_failure_score,recurrence_score,buyer_signal_score,automation_fit_score,total_score,evidence,raw_json,first_seen_at,last_seen_at,occurrences)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
      (fp, vals["source"], vals["source_id"], vals["title"], vals["url"], vals["description"], vals["observed_at"], vals["published_at"], vals["updated_at"], vals["company"], vals["reward_text"], vals["task_status"], vals["category"], vals["ai_failure_score"], vals["recurrence_score"], vals["buyer_signal_score"], vals["automation_fit_score"], vals["total_score"], vals["evidence"], vals["raw_json"], now, now))
    conn.commit()
    return True, False


def telegram_send(message: str, token: str, chat_id: str) -> bool:
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except Exception as exc:
        print(f"WARN Telegram alert failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def format_alert(c: Candidate) -> str:
    desc = c.description[:350] + ("…" if len(c.description) > 350 else "")
    return (f"SOLVEEASE TASK GAP CANDIDATE\nScore: {c.total_score}/100 (heuristic, not proof)\n"
            f"Category: {c.category}\nSource: {c.source}\nTitle: {c.title}\n"
            f"Failure signal: {c.ai_failure_score}/100 | Recurrence: {c.recurrence_score}/100 | Buyer signal: {c.buyer_signal_score}/100 | Automation fit: {c.automation_fit_score}/100\n"
            f"Reward text: {c.reward_text or 'not detected'}\nEvidence: {c.evidence}\nDescription: {desc}\nURL: {c.url}\n"
            "Verification required: confirm active listing, exact payer, eligibility, acceptance terms and payout. No revenue claimed.")


def run() -> int:
    db_path = os.getenv("TASK_GAP_DB", DEFAULT_DB)
    conn = init_db(db_path)
    sources = []
    github_enabled = os.getenv("TASK_GAP_GITHUB_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    problems_enabled = os.getenv("TASK_GAP_PROBLEMS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    rss_urls = [u.strip() for u in os.getenv("TASK_GAP_RSS_URLS", "").split(";") if u.strip()]
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if github_enabled:
        sources.append(("github", github_candidates(max_pages=int(os.getenv("TASK_GAP_GITHUB_PAGES", "1")), per_page=int(os.getenv("TASK_GAP_GITHUB_PER_PAGE", "30")), token=token)))
    if problems_enabled:
        sources.append(("public_problem_reports", problems_api_candidates(limit=int(os.getenv("TASK_GAP_PROBLEMS_LIMIT", "60")))))
    if rss_urls:
        sources.append(("rss", rss_candidates(rss_urls)))
    threshold = int(os.getenv("TASK_GAP_ALERT_SCORE", "55"))
    tg_token, tg_chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    counts = {"seen": 0, "new": 0, "updated": 0, "alerts": 0, "errors": 0}
    print(f"SolveEase Task Gap Hunter v{APP_VERSION} | {utc_now()} | database={db_path}")
    for name, iterator in sources:
        print(f"\nSOURCE {name}")
        try:
            for c in iterator:
                counts["seen"] += 1
                is_new, changed = save_candidate(conn, c)
                counts["new"] += int(is_new)
                counts["updated"] += int((not is_new) and changed)
                print(f"[{c.total_score:02d}] {c.category:22s} {c.title[:110]} | {c.url}")
                # Alert only new candidates above threshold, not every repeated poll.
                if is_new and c.total_score >= threshold and telegram_send(format_alert(c), tg_token, tg_chat):
                    counts["alerts"] += 1
        except Exception as exc:
            counts["errors"] += 1
            print(f"ERROR source {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    conn.close()
    print("\nSUMMARY " + json.dumps(counts, sort_keys=True))
    return 0 if counts["errors"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(run())
