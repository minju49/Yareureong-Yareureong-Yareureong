import copy
import unittest

from replay_gate import replay_record
from test_order_gate import response


class GateReplayTests(unittest.TestCase):
    def test_observed_partial_order_rejection_preserves_model_and_old_run(self):
        from review import review_transcript
        source = '아아 하나랑 아봐라 하나 주세요'
        review = review_transcript(source)
        answers = {}
        for branch in ('A_original', 'B_reviewed'):
            row = response(input_text=review['original_text'] if branch == 'A_original' else review['reviewed_text'])
            row.update(raw_content='saved real-answer fixture', model_called=True,
                       order_decision={'version': 'bom-order-gate-0.1', 'status': 'ready'},
                       gate_score='unsafe_accept', reference_score={'correct': None})
            answers[branch] = row
        record = {'case': {'id': 'H016', 'text': source, 'must_block': True, 'expected_model': None},
                  'review': review, 'responses': answers, 'context': {}}
        before = copy.deepcopy(record)
        replay = replay_record(record)
        self.assertEqual(record, before)
        self.assertEqual(replay['new_model_calls'], 0)
        for row in replay['responses'].values():
            self.assertFalse(row['model_called_here'])
            self.assertEqual(row['previous_gate_score'], 'unsafe_accept')
            self.assertEqual(row['replayed_gate_score'], 'blocked_required')


if __name__ == '__main__':
    unittest.main()
