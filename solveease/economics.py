from __future__ import annotations
from dataclasses import replace
from typing import Optional
from .models import Opportunity, ScreeningResult, utc_now_iso

DEFAULT_THRESHOLD_USD = 2.0
DEFAULT_STARTING_CAPITAL_USD = 0.0

def expected_value(opportunity: Opportunity) -> Optional[float]:
    p = opportunity.success_probability
    v = opportunity.success_net_value_usd
    if p is None or v is None:
        return None
    if not (0.0 <= p <= 1.0):
        return None
    return (p * v) - ((1.0 - p) * opportunity.failure_loss_usd) - opportunity.remaining_cost_usd

def screen(opportunity: Opportunity, threshold_usd: float = DEFAULT_THRESHOLD_USD,
           starting_capital_usd: float = DEFAULT_STARTING_CAPITAL_USD) -> ScreeningResult:
    now = utc_now_iso()
    if starting_capital_usd < 0:
        return ScreeningResult(opportunity.opportunity_id, False, None, False,
                               "invalid_negative_starting_capital", now)
    if opportunity.remaining_cost_usd > starting_capital_usd:
        return ScreeningResult(opportunity.opportunity_id, False, None, False,
                               "requires_upfront_capital_above_default", now)
    ev = expected_value(opportunity)
    if ev is None:
        return ScreeningResult(opportunity.opportunity_id, False, None, False,
                               "missing_or_invalid_probability_or_value", now)
    return ScreeningResult(opportunity.opportunity_id, True, ev, ev >= threshold_usd,
                           "passes" if ev >= threshold_usd else "below_threshold", now)
