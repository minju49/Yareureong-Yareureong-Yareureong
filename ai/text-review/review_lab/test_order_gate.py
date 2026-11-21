"""Acceptance guard regressions. Fixtures are not measured model accuracy."""
import copy
import unittest

from order_gate import validate_order
from review import review_transcript
from run_review import CONTEXTS


def response(menu='americano', quantity=1, temp='ice', *, intent='add', needs=False, question='',
             cream=None, note='', size='regular', input_text=None):
    row = {'status': 'ok', 'parsed': {'intent': intent, 'items': [{'menu_id': menu, 'quantity': quantity,
           'temperature': temp, 'size': size, 'whipped_cream': cream, 'custom_note': note}],
           'needs_clarification': needs, 'clarification_question': question}}
    if input_text is not None: row['input_text'] = input_text
    return row


class GateTests(unittest.TestCase):
    def test_complete_known_item_is_only_field_ready(self):
        out = validate_order(response(), '아아 한 잔 주세요')
        self.assertEqual(out['status'], 'ready')
        self.assertTrue(out['can_accept_fields'])
        self.assertTrue(out['customer_final_confirmation_required'])
        self.assertFalse(out['cart_mutated'])
        self.assertFalse(out['order_committed'])

    def test_quantity_absent_never_accepts_guessed_one(self):
        row = response('mango_smoothie', 1)
        before = copy.deepcopy(row)
        out = validate_order(row, '망고스무디 주세요')
        self.assertEqual(out['status'], 'ask')
        self.assertEqual(out['question'], '몇 잔 드릴까요?')
        self.assertFalse(out['can_accept_fields'])
        self.assertFalse(out['validated_items'])
        self.assertEqual(row, before)

    def test_wrong_menu_does_not_become_the_correct_menu_silently(self):
        out = validate_order(response(), '아바라 한 잔 주세요')
        self.assertEqual(out['status'], 'menu_check')
        self.assertIn('바닐라라떼', out['question'])
        self.assertFalse(out['validated_items'])

    def test_unregistered_milkshake_does_not_become_americano(self):
        out = validate_order(response(intent='clarify', needs=True, question='어떤 메뉴인가요?'), '밀크쉐이크 주세요')
        self.assertEqual(out['status'], 'menu_check')
        self.assertFalse(out['can_accept_fields'])
        self.assertFalse(out['validated_items'])

    def test_generic_latte_has_candidates_without_guessing(self):
        out = validate_order(response(), '라떼 한 잔 주세요')
        self.assertEqual(out['status'], 'menu_check')
        self.assertEqual(set(out['candidate_menu_ids']), {'cafe_latte', 'vanilla_latte', 'strawberry_latte'})

    def test_malformed_response_cannot_be_ready(self):
        for row in ({'status': 'error'}, {'status': 'invalid_response'}, {'status': 'ok', 'parsed': []}):
            with self.subTest(row=row):
                self.assertEqual(validate_order(row, '아아 한 잔 주세요')['status'], 'unavailable')

    def test_malformed_item_list_is_held(self):
        row = response()
        row['parsed']['items'] = 'americano'
        self.assertEqual(validate_order(row, '아아 한 잔 주세요')['status'], 'hold')

    def test_explicit_temperature_disagreement_is_not_repaired(self):
        for temp in ('hot', None):
            with self.subTest(temp=temp):
                row = response(temp=temp)
                before = copy.deepcopy(row)
                out = validate_order(row, '아아 한 잔 주세요')
                self.assertEqual(out['status'], 'ask')
                self.assertEqual(row, before)
                self.assertFalse(out['validated_items'])

    def test_only_ice_catalog_completion_is_separate_from_raw_model(self):
        row = response('strawberry_latte', 2, None)
        out = validate_order(row, '딸기라떼 두 잔 주세요')
        self.assertEqual(out['status'], 'ready')
        self.assertIsNone(row['parsed']['items'][0]['temperature'])
        self.assertEqual(out['validated_items'][0]['temperature'], 'ice')
        self.assertEqual(out['catalog_completions'][0]['source'], 'catalog_ice_only')
        self.assertFalse(out['question'])

    def test_explicit_impossible_hot_ice_only_is_not_overridden(self):
        out = validate_order(response('mango_smoothie', 1, 'ice'), '따뜻한 망고스무디 한 잔 주세요')
        self.assertEqual(out['status'], 'ask')
        self.assertFalse(out['validated_items'])

    def test_uncertain_unit_requests_confirmation(self):
        out = validate_order(response('strawberry_latte', 2), '딸기라떼 두대주세요')
        self.assertEqual(out['status'], 'ask')
        self.assertEqual(out['question'], '두 잔을 말씀하신 건가요?')
        self.assertEqual(out['source_facts']['quantity'], 2)

    def test_ice_only_model_error_does_not_create_an_unnecessary_temperature_question(self):
        out = validate_order(response('strawberry_latte', 2, 'hot'), '딸기라떼 두 잔 주세요')
        self.assertEqual(out['status'], 'hold')
        self.assertFalse(out['question'])
        self.assertFalse(out['validated_items'])

    def test_pending_answer_uses_same_explicit_context(self):
        out = validate_order(response(), '한 개요', CONTEXTS['quantity'])
        self.assertEqual(out['status'], 'ready')
        review = review_transcript('한 개요', CONTEXTS['quantity'])
        row = response(input_text=review['reviewed_text'])
        b = validate_order(row, review['reviewed_text'], review['context'], evidence_text=review['lexical_text'])
        self.assertEqual(b['status'], 'ready')

    def test_unknown_short_answer_does_not_invent_a_menu(self):
        self.assertEqual(validate_order(response(), '한 개요')['status'], 'menu_check')

    def test_fuzzy_menu_requires_confirmation_before_field_acceptance(self):
        review = review_transcript('아메리카너 차갑게 한 잔 주세요')
        out = validate_order(response(), review['reviewed_text'], evidence_text=review['lexical_text'], changes=review['changes'])
        self.assertEqual(out['status'], 'menu_check')
        self.assertFalse(out['validated_items'])

    def test_compound_change_and_reset_are_held(self):
        for text in ('아아 하나 빼주고 아니 아바라 하나 추가해줘', '아메리카노 하나 빼줘', '다 취소해줘'):
            with self.subTest(text=text):
                out = validate_order(response(), text)
                self.assertEqual(out['status'], 'hold')
                self.assertFalse(out['can_accept_fields'])

    def test_custom_note_is_not_discarded_or_auto_accepted(self):
        out = validate_order(response(temp='hot', note='얼음 두 개'), '뜨아 한 잔에 얼음 두 개만')
        self.assertEqual(out['status'], 'hold')
        self.assertFalse(out['validated_items'])
        self.assertEqual(validate_order(response(note='한 개요'), '아아 한 잔 주세요')['status'], 'hold')

    def test_quantity_mismatch_and_boolean_are_rejected(self):
        for value in (2, None, True):
            with self.subTest(value=value):
                self.assertEqual(validate_order(response(quantity=value), '아아 한 잔 주세요')['status'], 'ask')

    def test_required_whip_is_checked(self):
        row = response('cafe_mocha', 1, 'hot', cream=None)
        out = validate_order(row, '따뜻한 카페모카 휘핑 빼고 한 잔 주세요')
        self.assertEqual(out['status'], 'ask')
        self.assertFalse(out['validated_items'])

    def test_empty_items_can_still_prompt_for_a_missing_quantity(self):
        row = response(needs=True, intent='clarify', question='몇 잔 드릴까요?')
        row['parsed']['items'] = []
        self.assertEqual(validate_order(row, '아아 주세요')['status'], 'ask')

    def test_complete_item_with_contradictory_question_is_not_ready(self):
        self.assertEqual(validate_order(response(question='따뜻하게 드릴까요?'), '아아 한 잔 주세요')['status'], 'ask')

    def test_request_text_mismatch_is_held(self):
        self.assertEqual(validate_order(response(input_text='다른 문장'), '아아 한 잔 주세요')['status'], 'hold')

    def test_invalid_signed_or_decimal_count_is_not_accepted(self):
        for text in ('아아 -1잔 주세요', '아아 1.5잔 주세요'):
            with self.subTest(text=text):
                self.assertEqual(validate_order(response(), text)['status'], 'hold')

    def test_negation_does_not_become_an_add(self):
        self.assertEqual(validate_order(response(), '아아 한 잔 주지 마세요')['status'], 'hold')


if __name__ == '__main__': unittest.main(verbosity=2)
