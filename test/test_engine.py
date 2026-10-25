import tempfile
from pathlib import Path
from solvease.models import Opportunity
from solvease.economics import screen, expected_value
from solvease.store import SQLiteLedger
from solvease.robot import ArbitrageRobot

def test_expected_value_and_threshold():
    o = Opportunity("a", "test", "x", "u", "t", success_probability=0.5, success_net_value_usd=10)
    assert expected_value(o) == 5.0
    assert screen(o).passes_threshold

def test_zero_capital_rejects_upfront_cost():
    o = Opportunity("b", "test", "x", "u", "t", success_probability=1.0, success_net_value_usd=10, remaining_cost_usd=1)
    assert not screen(o).scoreable
    assert screen(o).reason == "requires_upfront_capital_above_default"

def test_missing_inputs_unscored():
    o = Opportunity("c", "test", "x", "u", "t")
    r = screen(o)
    assert not r.scoreable
    assert r.reason == "missing_or_invalid_probability_or_value"

def test_sqlite_idempotent_upsert_and_processing():
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "ledger.sqlite3"
        ledger = SQLiteLedger(str(db))
        o = Opportunity("d", "test", "x", "u", "t", success_probability=0.5, success_net_value_usd=5)
        robot = ArbitrageRobot(ledger)
        out = robot.process([o, o])
        assert len(out) == 2
        assert ledger.counts()["discovered"] == 1
        ledger.close()
