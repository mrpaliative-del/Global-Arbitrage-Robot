import tempfile, unittest
from pathlib import Path
from solveease.models import Opportunity
from solveease.economics import screen
from solveease.store import SQLiteLedger
from solveease.strategies import generate_strategies

def opp(**kwargs):
    base=dict(opportunity_id="demo:1",source="demo",title="Demo",url="https://example.com",
      discovered_at="2026-01-01T00:00:00+00:00",success_probability=None,success_net_value_usd=None)
    base.update(kwargs); return Opportunity(**base)

class CoreTests(unittest.TestCase):
    def test_missing_evidence_is_unscored(self):
        result=screen(opp())
        self.assertFalse(result.scoreable)
        self.assertIsNone(result.expected_value_usd)
    def test_expected_value_formula(self):
        result=screen(opp(success_probability=.8,success_net_value_usd=10,failure_loss_usd=2,remaining_cost_usd=1),2,5)
        self.assertTrue(result.scoreable)
        self.assertAlmostEqual(result.expected_value_usd,6.2)
        self.assertTrue(result.passes_threshold)
    def test_invalid_probability_is_unscored(self):
        self.assertFalse(screen(opp(success_probability=1.5,success_net_value_usd=10)).scoreable)
    def test_dedup_upsert_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            db=SQLiteLedger(str(Path(d)/"ledger.sqlite3"))
            try:
                db.upsert_opportunity(opp())
                db.upsert_opportunity(opp(title="Updated"))
                self.assertEqual(db.counts(),{"discovered":1})
                self.assertEqual(db.latest_opportunities()[0]["title"],"Updated")
            finally: db.close()
    def test_routes_are_explicit_hypotheses(self):
        routes=generate_strategies(opp())
        self.assertGreaterEqual(len(routes),1)
        self.assertTrue(all(x.status=="hypothesis_not_validated" for x in routes))

if __name__=="__main__": unittest.main()
