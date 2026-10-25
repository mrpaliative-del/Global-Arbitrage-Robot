from __future__ import annotations
from typing import Iterable, List, Dict, Any
from .economics import screen
from .models import Opportunity
from .strategies import generate_strategies
from .store import SQLiteLedger

class ArbitrageRobot:
    def __init__(self, ledger: SQLiteLedger, threshold_usd: float = 2.0, starting_capital_usd: float = 0.0):
        self.ledger = ledger
        self.threshold_usd = threshold_usd
        self.starting_capital_usd = starting_capital_usd

    def process(self, opportunities: Iterable[Opportunity]) -> List[Dict[str, Any]]:
        results = []
        for o in opportunities:
            self.ledger.upsert_opportunity(o)
            sr = screen(o, self.threshold_usd, self.starting_capital_usd)
            self.ledger.add_screening(sr)
            results.append({"opportunity": o.to_dict(), "screening": sr.to_dict(),
                            "strategies": [s.__dict__ for s in generate_strategies(o)]})
        return results
