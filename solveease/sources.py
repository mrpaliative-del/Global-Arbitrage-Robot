"""Small public API connectors; network errors are surfaced to the caller."""
from __future__ import annotations
import json, os, urllib.parse, urllib.request, xml.etree.ElementTree as ET

UA="SolveEaseOpportunityResearch/2.0 (public-data research; contact: project maintainer)"
def _get_json(url, timeout=15):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        if response.status != 200: raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8","replace"))

def fetch_github_issues(query='is:open "manual workaround"',per_page=10):
    q=urllib.parse.urlencode({"q":query,"per_page":max(1,min(int(per_page),30)),"sort":"updated"})
    data=_get_json("https://api.github.com/search/issues?"+q)
    return [{"source":"github_issues","external_id":str(x.get("id") or x.get("html_url")),
        "title":x.get("title",""),"url":x.get("html_url",""),
        "note":(x.get("body") or "")[:1000]} for x in data.get("items",[])]

def fetch_stackexchange_questions(tagged="python",pagesize=10):
    q=urllib.parse.urlencode({"site":"stackoverflow","tagged":tagged,"pagesize":max(1,min(int(pagesize),30)),
                              "order":"desc","sort":"activity","filter":"withbody"})
    data=_get_json("https://api.stackexchange.com/2.3/questions?"+q)
    return [{"source":"stackexchange","external_id":str(x.get("question_id")),
        "title":x.get("title",""),"url":x.get("link",""),
        "note":(x.get("body") or "")[:1000]} for x in data.get("items",[])]

def fetch_grants_gov(query="small business",rows=10):
    # Grants.gov public search endpoint; API schema changes are reported, not hidden.
    payload=json.dumps({"keyword":query,"oppStatuses":"forecasted|posted|closed","rows":max(1,min(int(rows),30))}).encode()
    req=urllib.request.Request("https://api.grants.gov/v1/api/search2",data=payload,
        headers={"User-Agent":UA,"Content-Type":"application/json","Accept":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=20) as response:
        data=json.loads(response.read().decode("utf-8","replace"))
    result=data.get("data",data)
    items=result.get("oppHits",result.get("opportunities",[])) if isinstance(result,dict) else []
    out=[]
    for x in items:
        ident=x.get("id") or x.get("opportunityId") or x.get("number")
        out.append({"source":"grants_gov","external_id":str(ident or x.get("title")),
          "title":x.get("title") or x.get("opportunityTitle") or "",
          "url":x.get("url") or (f"https://www.grants.gov/search-results-detail/{ident}" if ident else ""),
          "note":str(x.get("synopsis") or x.get("description") or "")[:1000]})
    return out

def fetch_problem_reports():
    url=os.environ.get("SOLVEEASE_PROBLEM_REPORTS_URL","https://problems.fru.dev/api/problems").strip()
    if not url: return []
    data=_get_json(url,timeout=12)
    if isinstance(data,dict):
        items=data.get("problems",data.get("items",data.get("data",[])))
    else: items=data
    if not isinstance(items,list): raise ValueError("Problem reports API returned an unsupported schema.")
    out=[]
    for i,x in enumerate(items[:30]):
        if not isinstance(x,dict): continue
        ident=x.get("id") or x.get("slug") or x.get("url") or str(i)
        out.append({"source":"public_problem_reports","external_id":str(ident),
          "title":str(x.get("title") or x.get("name") or x.get("problem") or "")[:500],
          "url":str(x.get("url") or x.get("link") or ""),
          "note":str(x.get("description") or x.get("body") or x.get("summary") or "")[:1000]})
    return [x for x in out if x["title"]]
