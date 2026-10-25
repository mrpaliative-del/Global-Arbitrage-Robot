import unittest
from task_gap_hunter import Candidate, clean_text, fingerprint, infer_category, make_candidate, score_text

class TaskGapHunterTests(unittest.TestCase):
    def test_html_cleanup(self):
        self.assertEqual(clean_text('<p>AI keeps failing</p>'), 'AI keeps failing')

    def test_failure_signal_scores(self):
        scores = score_text('Regression: AI keeps failing', 'Still have to manually check results; repeated workaround.')
        self.assertGreater(scores['ai_failure_score'], 0)
        self.assertGreater(scores['recurrence_score'], 0)

    def test_buyer_signal_is_separate(self):
        a = score_text('Broken feature', 'This keeps failing and needs a workaround.')
        b = score_text('Paid contract: $200 per accepted task', 'Create regression tests and verify the fix.')
        self.assertEqual(a['buyer_signal_score'], 0)
        self.assertGreater(b['buyer_signal_score'], 0)

    def test_category(self):
        self.assertEqual(infer_category('Regression test for API', 'test failure'), 'software_testing')
        self.assertEqual(infer_category('Invoice mismatch', 'reconcile duplicate transactions'), 'data_reconciliation')

    def test_candidate_and_fingerprint(self):
        c = make_candidate('test', '1', 'Broken API test', 'https://example.com/issue/1', 'Flaky regression test', raw={})
        self.assertEqual(len(fingerprint(c)), 64)
        self.assertEqual(c.source, 'test')
        self.assertGreaterEqual(c.total_score, 0)

if __name__ == '__main__':
    unittest.main()
