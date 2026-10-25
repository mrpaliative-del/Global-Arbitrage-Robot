from __future__ import annotations
import math
from .models import Opportunity, ScreeningResult, utc_now_iso

def screen(o: Opportunity, threshold_usd: float = 2.0, starting_capital_usd: float = 0.0) -> ScreeningResult:
    p, value = o.success_probability, o.success_net_value_usd
    reason = ""
    if p is None or value is None:
        reason = "Unscored: success probability and net success value must be independently evidenced."
        return ScreeningResult(o.opportunity_id, False, None, False, reason, utc_now_iso())
    if not isinstance(p, (int,float)) or not math.isfinite(p) or not 0 <= p <= 1:
        reason = "Unscored: success probability must be finite and between 0 and 1."
        return ScreeningResult(o.opportunity_id, False, None, False, reason, utc_now_iso())
    numeric = (value, o.failure_loss_usd, o.remaining_cost_usd, starting_capital_usd, threshold_usd)
    if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in numeric):
        return ScreeningResult(o.opportunity_id, False, None, False, "Unscored: invalid financial input.", utc_now_iso())
    if min(value, o.failure_loss_usd, o.remaining_cost_usd, starting_capital_usd, threshold_usd) < 0:
        return ScreeningResult(o.opportunity_id, False, None, False, "Unscored: financial inputs cannot be negative.", utc_now_iso())
    if o.remaining_cost_usd > starting_capital_usd:
        return ScreeningResult(o.opportunity_id, False, None, False, "Unscored: required cost exceeds available capital.", utc_now_iso())
    ev = p * value - (1-p) * o.failure_loss_usd - o.remaining_cost_usd
    passed = ev >= threshold_usd
    return ScreeningResult(o.opportunity_id, True, round(ev, 6), passed,
        "Passes configured expected-value screen; not a guarantee of profit." if passed else "Does not meet expected-value threshold.", utc_now_iso())
