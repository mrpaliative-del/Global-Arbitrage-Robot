from __future__ import annotations
import argparse
from .models import Opportunity, utc_now_iso
from .store import SQLiteLedger
from .robot import ArbitrageRobot

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="solveease_ledger.sqlite3")
    p.add_argument("--title", default="Demo opportunity")
    p.add_argument("--value", type=float, default=10.0)
    p.add_argument("--probability", type=float, default=0.5)
    args = p.parse_args()
    ledger = SQLiteLedger(args.db)
    try:
        o = Opportunity("demo-1", "manual", args.title, "https://example.com", utc_now_iso(),
                        payer="unverified", deliverable="demo output",
                        success_probability=args.probability, success_net_value_usd=args.value)
        result = ArbitrageRobot(ledger).process([o])
        print(result[0]["screening"])
    finally:
        ledger.close()

if __name__ == "__main__":
    main()
