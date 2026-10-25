from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

@dataclass
class Opportunity:
    opportunity_id: str
    source: str
    title: str
    url: str
    discovered_at: str
    payer: Optional[str] = None
    beneficiary: Optional[str] = None
    deliverable: Optional[str] = None
    permission_status: str = "unknown"
    eligibility: Optional[str] = None
    resource_requirements: Optional[str] = None
    success_probability: Optional[float] = None
    success_net_value_usd: Optional[float] = None
    failure_loss_usd: float = 0.0
    remaining_cost_usd: float = 0.0
    evidence_status: str = "lead"
    state: str = "discovered"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ScreeningResult:
    opportunity_id: str
    scoreable: bool
    expected_value_usd: Optional[float]
    passes_threshold: bool
    reason: str
    screened_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
