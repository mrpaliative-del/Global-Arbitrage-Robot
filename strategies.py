from __future__ import annotations
from dataclasses import dataclass
from typing import List
from .models import Opportunity

@dataclass
class Strategy:
    name: str
    payer: str
    deliverable: str
    conversion_action: str
    permissions: str
    expected_route: str

def generate_strategies(o: Opportunity) -> List[Strategy]:
    base_payer = o.payer or "unverified payer"
    base_deliverable = o.deliverable or "decision-ready output"
    return [
        Strategy("fixed_scope_service", base_payer, base_deliverable,
                 "send a compliant offer or application through an authorized channel",
                 o.permission_status, "service"),
        Strategy("reusable_digital_product", base_payer,
                 f"reusable template or report based on {base_deliverable}",
                 "publish a product page and accept a lawful order",
                 o.permission_status, "product"),
        Strategy("information_report", base_payer,
                 f"verified report covering {base_deliverable}",
                 "deliver a paid report or referral",
                 o.permission_status, "information"),
        Strategy("referral_matching", base_payer,
                 f"qualified introduction related to {base_deliverable}",
                 "make a permissioned introduction",
                 o.permission_status, "referral"),
        Strategy("savings_recovery", base_payer,
                 f"documented recovery or avoided-loss action for {base_deliverable}",
                 "submit a claim or recovery request where authorized",
                 o.permission_status, "recovery"),
    ]
