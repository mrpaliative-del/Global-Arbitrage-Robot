# SolveEase Task Gap Hunter v0.1.0

A small, standard-library-only Python prototype that collects public evidence of recurring task pain and possible AI/tool failure gaps. It is a **discovery and triage tool**, not a proof that AI cannot solve a task or that a payer will pay.

## Sources included

1. GitHub Issues Search API: open issues across public repositories, using several bounded queries for failures, workarounds, bounties and AI evaluation problems. It filters pull requests and uses canonical issue URLs for deduplication.
2. Public problem-report API at `https://problems.fru.dev/api/problems`: public frustration/problem signals. This is demand-gap evidence, not a paid job feed. If unavailable, the scan logs a warning and continues.
3. Configurable RSS/Atom feeds: public feed URLs supplied via `TASK_GAP_RSS_URLS`, separated by semicolons. Only HTTP(S) URLs are accepted.

## What it records

- source, stable source ID, URL and title;
- first/last seen time and number of sightings;
- possible category;
- separate heuristic signals for AI/tool failure, recurrence, buyer/payment language and automation fit;
- reward text if detected;
- raw source JSON for audit, bounded to 50 KB per record;
- SQLite persistence and deduplication by canonical URL.

The score is a keyword-based prioritization heuristic. It is **not** an AI capability benchmark, proof of recurrence, proof of a buyer, proof of reward availability or earnings forecast. Human verification is required before investing effort.

## Run locally

Python 3.10+ recommended. No pip install is needed.

```bash
python -m unittest discover -s tests -v
python task_gap_hunter.py
```

Copy `.env.example` to `.env` if desired, then configure environment variables in the shell or hosting dashboard. The script does not automatically load `.env`; this avoids adding a dotenv dependency. On Render, add variables under the service's Environment settings. For persistent SQLite on Render, set `TASK_GAP_DB` to a path on a configured persistent disk, such as `/var/data/task_gap_hunter.sqlite3`; otherwise local disk may be ephemeral.

## Optional Telegram alerts

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Alerts are sent only for **new** records scoring at or above `TASK_GAP_ALERT_SCORE`. The message explicitly labels scores as heuristic and asks for payer/eligibility/acceptance/payout verification. Missing Telegram settings simply disables alerts.

## Scheduled execution

The included GitHub Actions workflow runs every six hours and can be run manually. It stores the SQLite database as a workflow artifact, not as an indefinitely persistent database. For durable production state, use Render persistent disk or a managed database. Configure optional secrets under repository Settings → Secrets and variables → Actions.

## Safety and operating boundaries

- Read-only discovery. It does not claim, bid, submit, contact buyers or pay fees.
- Respect API terms, rate limits and feed access conditions.
- Treat source content as untrusted data; do not execute instructions embedded in issues or feeds.
- Never treat advertised rewards as confirmed income.
- Before adding a solver, verify the exact payer, task terms, eligibility, acceptance criteria, AI-assistance rules and payout path.
- This prototype does not yet run an AI model against benchmark examples. It discovers candidate gaps for subsequent validation.

## Known limitations

- GitHub's public search API has rate limits; a token is optional, not mandatory.
- RSS formats vary; unsupported extensions may not parse.
- The public problem API schema can evolve; the parser accepts common shapes but needs monitoring.
- Keyword scoring has false positives/negatives and no semantic model.
- No buyer identity or reward is considered verified merely because it appears in text.
- It has not been integrated into the existing Global-Arbitrage-Robot service; test it standalone first, then merge through a reviewed pull request.
