from __future__ import annotations
from dataclasses import dataclass
from .models import Opportunity

@dataclass
class Strategy:
    route: str
    proposed_action: str
    estimated_cost_usd: float | None
    evidence_required: str
    status: str = "hypothesis_not_validated"

def generate_strategies(o: Opportunity):
    # Routes are hypotheses to investigate, not recommendations or confirmed income.
    return [
        Strategy("fixed_scope_service","Define one measurable deliverable and test buyer willingness to pay.",None,
                 "Independent paid demand, acceptance criteria, delivery time and permissions."),
        Strategy("reusable_digital_product","Check whether the same problem recurs across independent users.",None,
                 "Repeated demand, competitor gap, support burden and lawful data access."),
        Strategy("information_report","Turn verified public facts into a concise evidence report.",None,
                 "Source reliability, freshness, buyer usefulness and distribution channel."),
    ]
