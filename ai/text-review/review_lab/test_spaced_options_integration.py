import unittest
from review import review_transcript,policy_check
from order_gate import validate_order
from run_review import CONTEXTS
from test_order_gate import response


class SpacedOptionsIntegrationTests(unittest.TestCase):
    def test_observed_temperature_short_answer_keeps_known_context(self):
        raw='차갑 게'
        result=review_transcript(raw,CONTEXTS['temperature'])
        self.assertEqual(result['original_text'],raw)
        self.assertFalse(result['unicode_normalized'])
        self.assertEqual(result['lexical_text'],'차갑게')
        self.assertEqual(result['context_expansion']['value'],'ice')
        facts=policy_check(result['lexical_text'],result['context'])
        self.assertEqual(facts['temperature'],'ice')
        self.assertEqual(facts['quantity'],1)
        self.assertEqual(facts['missing_fields'],['whipped_cream'])

    def test_observed_mocha_temperature_whip_splits_are_verifiable(self):
        raw='따 뜻한 카페 모카 한 잔 휘 핑 빼 고 주세요'
        result=review_transcript(raw)
        facts=policy_check(result['lexical_text'])
        self.assertEqual((facts['temperature'],facts['whipped_cream'],facts['quantity']),('hot','none',1))
        row=response('cafe_mocha',1,'hot',cream='none',input_text=result['reviewed_text'])
        gate=validate_order(row,result['reviewed_text'],evidence_text=result['lexical_text'],changes=result['changes'])
        self.assertEqual(gate['status'],'ready')

    def test_spacing_stage_preserves_correction_and_disables_fuzzy_replacement(self):
        raw='아메리카너 하나 말 고 아바라 하나 주세요'
        result=review_transcript(raw)
        self.assertTrue(result['protected_action'])
        self.assertIn('말고',result['lexical_text'])
        self.assertIn('아메리카너',result['lexical_text'])
        self.assertFalse(any(c['automatic'] for c in result['candidates']))
        self.assertEqual(policy_check(result['lexical_text'])['scope'],'not_a_simple_single_add')

    def test_lost_alias_is_not_fabricated(self):
        raw='아 한 잔 주세요'
        result=review_transcript(raw)
        self.assertEqual(result['reviewed_text'],raw)
        self.assertFalse(validate_order(response(input_text=raw),raw)['can_accept_fields'])


if __name__=='__main__': unittest.main()
