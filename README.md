# SolveEase Global Opportunity Research Robot — corrected bundle

Python 3.11+, standard library only. Research dashboard, public-source lead collection, SQLite persistence and deterministic evidence-aware screening. This is **not** an automatic trading bot and does not guarantee income.

## Render deployment

1. Back up the current GitHub repository first.
2. Upload/merge these files into the repository root; do not put them in a nested folder.
3. In Render, confirm the service is connected to the intended repository, branch (`main` unless you intentionally use another), and latest commit.
4. Build command: `python -m compileall -q .`
5. Start command: `python app.py`
6. Health check path: `/health`.
7. If using the included `render.yaml` Blueprint, review the service and persistent disk settings before applying. If configuring the existing service manually, set `SOLVEEASE_RUN_TOKEN` to a long random secret and `SOLVEEASE_DB_PATH` to a writable path. Only configure `/var/data` if a persistent disk is actually mounted there.
8. After deploy, open `/health`, then `/` and enter the run token to trigger a scan.

## Why the earlier deployment failed

The log `python: can't open file .../app.py` means the specific commit Render built did not contain `app.py` at its project root. The current public `main` branch may have moved since that log. Confirm Render's deployed commit and branch; do not assume the runtime is building the latest GitHub state.

## Sources

- GitHub Issues Search API
- Stack Exchange API
- Grants.gov public search endpoint
- Configurable public problem-report endpoint

External APIs may rate-limit, change their schemas or be temporarily unavailable. Each source's error is reported separately. Collected records are unverified leads. The app never infers buyer willingness to pay from a public issue.

## Evidence and financial screening

Expected value is `p(success) × net success value − p(failure) × failure loss − remaining cost`. Missing/invalid probability or net value means **unscored**, not zero risk or profit. This calculator is only a screen; values must be evidenced independently. No source record proves a buyer, legal eligibility, profit, or revenue.

## Tests

Run:

```bash
python -m unittest discover -s tests -v
```

No API keys or paid APIs are required for tests. The HTTP test uses a local port and a temporary database.

## Security

- Never commit `.env`, tokens or personal credentials.
- The scan endpoint fails closed unless `SOLVEEASE_RUN_TOKEN` is set.
- No automatic purchasing, trades, or paid task execution.
- A Render Free Web Service may sleep. Persistent disk availability and pricing depend on the service plan; check the dashboard before enabling paid resources.
