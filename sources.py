from __future__ import annotations
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

@dataclass
class SourceRecord:
    source: str
    external_id: str
    title: str
    url: str
    raw: Dict[str, Any]
    verified_live: bool = False
    note: str = ""

def _get_json(url: str, timeout: int = 15) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "SolveEase-Arbitrage-Robot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_github_issues(query: str = "is:open", per_page: int = 5) -> List[SourceRecord]:
    params = urllib.parse.urlencode({"q": query, "per_page": per_page})
    url = f"https://api.github.com/search/issues?{params}"
    data = _get_json(url)
    out = []
    for item in data.get("items", []):
        out.append(SourceRecord("github_issues", str(item.get("id")), item.get("title", ""),
                                 item.get("html_url", ""), item,
                                 verified_live=True, note="Public issue data; buyer demand is not proven."))
    return out

def fetch_stackexchange_questions(tagged: str = "python", pagesize: int = 5) -> List[SourceRecord]:
    params = urllib.parse.urlencode({"site": "stackoverflow", "tagged": tagged, "pagesize": pagesize, "order": "desc", "sort": "activity"})
    url = f"https://api.stackexchange.com/2.3/questions?{params}"
    data = _get_json(url)
    out = []
    for item in data.get("items", []):
        out.append(SourceRecord("stackexchange", str(item.get("question_id")), item.get("title", ""),
                                 item.get("link", ""), item,
                                 verified_live=True, note="Public question data; commercial conversion is not proven."))
    return out

def fetch_grants_gov(query: str = "small business", rows: int = 5) -> List[SourceRecord]:
    # Connector is intentionally conservative: schema may change and may require live validation.
    url = "https://api.grants.gov/v1/api/search2"
    payload = json.dumps({"keyword": query, "rows": rows}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "SolveEase-Arbitrage-Robot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    items = data.get("data", {}).get("hits", []) if isinstance(data, dict) else []
    return [SourceRecord("grants_gov", str(x.get("id", x.get("opportunityNumber", ""))),
                         x.get("title", x.get("opportunityTitle", "")),
                         x.get("url", x.get("opportunityURL", "")), x,
                         verified_live=True, note="Public grant listing; eligibility and monetization require separate validation.")
            for x in items]

def fetch_ocp_registry_page() -> SourceRecord:
    # This is not a procurement-feed connector. It only verifies reachability of the registry landing page.
    url = "https://www.open-contracting.org/data-standard/"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SolveEase-Arbitrage-Robot/1.0"}), timeout=15) as r:
        body = r.read(500)
    return SourceRecord("ocp_registry_page", "data-standard", "Open Contracting Data Standard", url,
                        {"preview_bytes": body.decode("utf-8", errors="replace")},
                        verified_live=True,
                        note="Registry/standard landing page only; not a tender feed.")
