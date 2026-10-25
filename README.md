# SolveEase Global Arbitrage Robot v1.0.0

A conservative, zero-capital-default research robot for converting publicly visible opportunity gaps into testable value-to-money routes.

## What is included

- Value-to-money engine with route generation:
  - fixed-scope service
  - reusable digital product
  - information report
  - referral/matching
  - savings recovery
- Public-source connectors:
  - GitHub Issues API
  - Stack Exchange API
  - Grants.gov search endpoint
  - Open Contracting landing-page reachability check
- Deterministic financial screening:
  - default starting capital: US$0
  - expected-net threshold: US$2
  - missing or invalid inputs remain unscored
- SQLite ledger with WAL mode and idempotent opportunity upserts
- Optional Telegram helper, disabled unless credentials are supplied
- Automated tests
- CLI demo

## Important evidence boundaries

This package does **not** claim:
- that every connector is live in every environment;
- that any source record proves buyer demand;
- that commercial conversion is validated;
- that any revenue has been earned;
- that a route is legal or eligible without separate verification.

The OCP connector only checks a public landing page. It is not a tender feed.

## Financial screening formula

`EV = P(success) * success_net_value - P(failure) * failure_loss - remaining_cost`

The success value must already be net of success-dependent costs. Remaining costs are deducted once. If probability or value is missing/invalid, the opportunity is not scored.

## Run locally

Python 3.10+ recommended.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
# .venv\Scripts\activate

pip install -r requirements.txt
pytest -q
python -m solvease --title "Example" --value 10 --probability 0.5
```

## Deployment options

### Render / Railway / any Python host
1. Upload the repository to GitHub.
2. Set the start command to:
   `python -m solvease --db /var/data/solveease_ledger.sqlite3`
3. Add environment variables from `.env.example`.
4. Use a persistent disk if ledger persistence across restarts is required.
5. Keep Telegram variables empty unless notifications are intentionally enabled.

### Scheduled scan
Use a scheduler or cron to run the CLI or a wrapper that fetches sources and passes normalized `Opportunity` records into `ArbitrageRobot`.

## Security and operating rules

- Never commit `.env` or credentials.
- Do not bypass access controls, paywalls, rate limits, or source terms.
- Treat all source records as leads until buyer, eligibility, permissions, deliverable, and payment evidence are independently checked.
- Do not report realized revenue without payment/settlement evidence.

## License

Use only where permitted by source terms and applicable law.
