
"""Small public API connectors; source errors are surfaced to the scanner."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

UA = (
    "SolveEaseOpportunityResearch/2.1 "
    "(public-data research; contact: project maintainer)"
)


def _get_json(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8", "replace"))


def _post_json(url, payload, timeout=20):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8", "replace"))


def fetch_github_issues(
    query='is:open "manual workaround"',
    per_page=10,
):
    params = urllib.parse.urlencode({
        "q": query,
        "per_page": max(1, min(int(per_page), 30)),
        "sort": "updated",
    })
    data = _get_json("https://api.github.com/search/issues?" + params)

    return [
        {
            "source": "github_issues",
            "external_id": str(x.get("id") or x.get("html_url")),
            "title": x.get("title", ""),
            "url": x.get("html_url", ""),
            "note": (x.get("body") or "")[:1000],
        }
        for x in data.get("items", [])
        if isinstance(x, dict)
    ]


def fetch_stackexchange_questions(tagged="python", pagesize=10):
    """Fetch Stack Overflow questions, retrying without the optional body filter."""
    base = "https://api.stackexchange.com/2.3/questions"
    common = {
        "site": "stackoverflow",
        "pagesize": max(1, min(int(pagesize), 30)),
        "order": "desc",
        "sort": "activity",
    }

    data = None
    errors = []

    # The body filter is optional. Try it first, then fall back to
    # the API's default question fields if the request is rejected.
    for use_body_filter in (True, False):
        params = dict(common)
        if tagged:
            params["tagged"] = str(tagged)[:200]
        if use_body_filter:
            params["filter"] = "withbody"

        url = base + "?" + urllib.parse.urlencode(params)

        try:
            candidate = _get_json(url, timeout=15)
            if not isinstance(candidate, dict):
                raise ValueError("Unexpected Stack Exchange response type.")

            # Stack Exchange can return HTTP 200 with an API-level error.
            if candidate.get("error_id"):
                message = candidate.get("error_message", "Unknown API error")
                raise RuntimeError(
                    f"Stack Exchange API error "
                    f"{candidate.get('error_id')}: {message}"
                )

            data = candidate
            break
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    if data is None:
        raise RuntimeError(
            "Stack Exchange request failed after fallback: "
            + " | ".join(errors)
        )

    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Stack Exchange returned an unsupported items field.")

    out = []
    for x in items:
        if not isinstance(x, dict):
            continue

        question_id = x.get("question_id")
        title = str(x.get("title") or "")
        link = str(x.get("link") or "")
        body = str(x.get("body") or "")

        out.append({
            "source": "stackexchange",
            "external_id": str(question_id or link or title),
            "title": title,
            "url": link,
            "note": body[:1000],
        })

    return out


def fetch_grants_gov(query="small business", rows=10):
    payload = {
        "keyword": query,
        "oppStatuses": "forecasted|posted|closed",
        "rows": max(1, min(int(rows), 30)),
    }

    data = _post_json(
        "https://api.grants.gov/v1/api/search2",
        payload,
        timeout=20,
    )

    result = data.get("data", data) if isinstance(data, dict) else {}
    items = (
        result.get("oppHits", result.get("opportunities", []))
        if isinstance(result, dict)
        else []
    )

    out = []
    for x in items:
        if not isinstance(x, dict):
            continue

        ident = (
            x.get("id")
            or x.get("opportunityId")
            or x.get("number")
        )
        out.append({
            "source": "grants_gov",
            "external_id": str(ident or x.get("title") or ""),
            "title": x.get("title") or x.get("opportunityTitle") or "",
            "url": x.get("url") or (
                f"https://www.grants.gov/search-results-detail/{ident}"
                if ident else ""
            ),
            "note": str(
                x.get("synopsis") or x.get("description") or ""
            )[:1000],
        })

    return out


def fetch_problem_reports():
    url = os.environ.get(
        "SOLVEEASE_PROBLEM_REPORTS_URL",
        "https://problems.fru.dev/api/problems",
    ).strip()

    if not url:
        return []

    data = _get_json(url, timeout=12)

    if isinstance(data, dict):
        items = data.get(
            "problems",
            data.get("items", data.get("data", [])),
        )
    else:
        items = data

    if not isinstance(items, list):
        raise ValueError(
            "Problem reports API returned an unsupported schema."
        )

    out = []
    for i, x in enumerate(items[:30]):
        if not isinstance(x, dict):
            continue

        ident = (
            x.get("id")
            or x.get("slug")
            or x.get("url")
            or str(i)
        )
        out.append({
            "source": "public_problem_reports",
            "external_id": str(ident),
            "title": str(
                x.get("title") or x.get("name") or x.get("problem") or ""
            )[:500],
            "url": str(x.get("url") or x.get("link") or ""),
            "note": str(
                x.get("description")
                or x.get("body")
                or x.get("summary")
                or ""
            )[:1000],
        })

    return [x for x in out if x["title"]]
