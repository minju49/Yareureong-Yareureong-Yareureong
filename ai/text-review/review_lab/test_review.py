"""Regression checks on constructed text, not a real STT evaluation set."""
import copy
import json
import csv
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import unicodedata
from unittest.mock import patch

from review import POLICY, review_transcript, policy_check, read_quantity, quantity_info
from qwen_client import payload, PROFILES, compare, diagnose
from run_review import CONTEXTS, make_record, csv_file


class ReviewTests(unittest.TestCase):
    def test_approved_aliases(self):
        for text, expected in [('아아 한 잔 주세요', '아이스 아메리카노 한 잔 주세요'),
                               ('뜨아 한 잔 주세요', '따뜻한 아메리카노 한 잔 주세요'),
                               ('따아 한 잔 주세요', '따뜻한 아메리카노 한 잔 주세요'),
                               ('아바라 두 잔 주세요', '아이스 바닐라라떼 두 잔 주세요')]:
            with self.subTest(text=text):
                result = review_transcript(text)
                self.assertEqual(result['original_text'], text)
                self.assertEqual(result['reviewed_text'], expected)
                self.assertEqual(result['changes'][0]['kind'], 'approved_alias')

    def test_correct_six_menus_unchanged(self):
        for menu in POLICY['menus']:
            text = menu['name'] + ' 한 잔 주세요'
            with self.subTest(text=text):
                result = review_transcript(text)
                self.assertEqual(result['reviewed_text'], text)
                self.assertFalse(result['changes'])

    def test_attached_quantity_and_spacing(self):
        result = review_transcript('아아한잔주세요')
        self.assertEqual(result['reviewed_text'], '아이스 아메리카노 한잔주세요')
        self.assertEqual(policy_check(result['lexical_text'])['quantity'], 1)
        self.assertEqual(policy_check('아이스아메리카노한잔주세요')['quantity'], 1)
        self.assertEqual(policy_check('아메리카노하나주세요')['quantity'], 1)

    def test_menu_spacing(self):
        self.assertEqual(review_transcript('딸기 라떼 두 잔 주세요')['reviewed_text'], '딸기라떼 두 잔 주세요')

    def test_variant_spelling(self):
        self.assertEqual(review_transcript('카페라테 한 잔 주세요')['reviewed_text'], '카페라떼 한 잔 주세요')

    def test_narrow_one_jamo_correction(self):
        result = review_transcript('차가운 아메리카너 두 잔 주세요')
        self.assertEqual(result['reviewed_text'], '차가운 아메리카노 두 잔 주세요')
        self.assertEqual(result['changes'][0]['kind'], 'menu_typo_candidate')

    def test_weak_candidate_is_not_automatic(self):
        for text in ('딸기한테 한 잔 주세요', '카페라때 한 잔 주세요'):
            with self.subTest(text=text):
                result = review_transcript(text)
                self.assertEqual(result['reviewed_text'], text)
                self.assertTrue(result['needs_review'])
                self.assertTrue(result['candidates'])

    def test_no_fabricated_short_alias(self):
        for text in ('아라 한 잔 주세요', '아봐라 한 잔 주세요', '아아아 한 잔 주세요'):
            with self.subTest(text=text):
                result = review_transcript(text)
                self.assertEqual(result['reviewed_text'], text)
                self.assertTrue(result['needs_review'])

    def test_unsupported_flavor_not_changed_to_supported(self):
        for text in ('카라멜라떼 한 잔 주세요', '카멜라떼 한 잔 주세요', '헤이즐넛라떼 한 잔 주세요', '바나나라떼 한 잔 주세요'):
            with self.subTest(text=text):
                result = review_transcript(text)
                self.assertEqual(result['reviewed_text'], text)
                self.assertTrue(result['needs_review'])

    def test_generic_menu_preserved_and_flagged(self):
        result = review_transcript('라떼 한 잔 주세요')
        self.assertEqual(result['reviewed_text'], '라떼 한 잔 주세요')
        self.assertTrue(result['needs_review'])

    def test_correction_and_cancel_words_preserved(self):
        text = '아아 하나 빼주고 아니 아바라 하나 추가해줘'
        result = review_transcript(text)
        self.assertEqual(result['reviewed_text'], '아이스 아메리카노 하나 빼주고 아니 아이스 바닐라라떼 하나 추가해줘')
        self.assertTrue(result['protected_action'])
        self.assertEqual(policy_check(result['lexical_text'])['scope'], 'not_a_simple_single_add')

    def test_unknown_menu_typo_not_auto_changed_during_cancel(self):
        text = '아메리카너 하나 빼줘'
        result = review_transcript(text)
        self.assertEqual(result['reviewed_text'], text)
        self.assertFalse(any(c['automatic'] for c in result['candidates']))

    def test_numbers_and_temperatures_not_rewritten(self):
        for text in ('아이스 아메리카너 세 잔 주세요', '뜨거운 아메리카너 두 잔 주세요'):
            with self.subTest(text=text):
                self.assertEqual(review_transcript(text)['reviewed_text'], text.replace('아메리카너', '아메리카노'))

    def test_unicode_raw_preserved(self):
        raw = unicodedata.normalize('NFD', '아메리카노 한 잔 주세요')
        result = review_transcript(raw)
        self.assertEqual(result['original_text'], raw)
        self.assertEqual(result['reviewed_text'], '아메리카노 한 잔 주세요')
        self.assertTrue(result['unicode_normalized'])

    def test_invalid_or_excessive_input_rejected(self):
        for text in ('', '  ', None, '가' * 2001):
            with self.subTest(text=text):
                with self.assertRaises(ValueError): review_transcript(text)


class PolicyTests(unittest.TestCase):
    def test_absent_quantity_does_not_default_to_one(self):
        for text in ('아아 주세요', '아바라 주세요', '망고스무디 주세요'):
            with self.subTest(text=text):
                result = policy_check(text)
                self.assertIsNone(result['quantity'])
                self.assertEqual(result['next_question'], '몇 잔 드릴까요?')

    def test_ice_only_no_temperature_question(self):
        for text in ('딸기라떼 두 잔 주세요', '망고스무디 한 잔 주세요'):
            with self.subTest(text=text):
                result = policy_check(text)
                self.assertEqual(result['temperature'], 'ice')
                self.assertFalse(result['missing_fields'])

    def test_mocha_temperature_then_whip(self):
        first = policy_check('카페모카 한 잔 주세요')
        self.assertEqual(first['missing_fields'], ['temperature', 'whipped_cream'])
        second = policy_check('아이스 카페모카 한 잔 주세요')
        self.assertEqual(second['missing_fields'], ['whipped_cream'])
        last = policy_check('따뜻한 카페모카 휘핑 빼고 한 잔 주세요')
        self.assertEqual(last['scope'], 'simple_single_add')
        self.assertEqual(last['whipped_cream'], 'none')
        self.assertFalse(last['missing_fields'])

    def test_ice_count_does_not_become_drink_quantity_or_temperature(self):
        result = policy_check(review_transcript('뜨아 한 잔에 얼음 2개만 넣어줘')['lexical_text'])
        self.assertEqual(result['quantity'], 1)
        self.assertEqual(result['temperature'], 'hot')
        self.assertEqual(read_quantity('아메리카노 두 잔 얼음 한 개만'), 2)
        self.assertEqual(read_quantity('카페모카 한 잔에 샷 두 개'), 1)

    def test_temperature_conflicts_not_silently_resolved(self):
        for text in ('따뜻한 망고스무디 한 잔 주세요', '아아 따뜻하게 한 잔 주세요', '아이스 아메리카노 따뜻하게 한 잔 주세요'):
            with self.subTest(text=text):
                result = policy_check(review_transcript(text)['lexical_text'])
                self.assertTrue(result['temperature_conflict'])
                self.assertFalse(result['simple_required_fields_complete'])

    def test_quantity_short_answers_in_explicit_context(self):
        for text, expected in [('한 개요', 1), ('하나요', 1), ('둘이요', 2), ('세 잔이요', 3)]:
            with self.subTest(text=text):
                ctx = CONTEXTS['quantity']
                review = review_transcript(text, ctx)
                self.assertIsNotNone(review['context_expansion'])
                self.assertEqual(review['context_expansion']['value'], expected)
                facts = policy_check(review['lexical_text'], ctx)
                self.assertEqual(facts['quantity'], expected)
                self.assertEqual(facts['temperature'], 'ice')

    def test_no_context_no_invented_menu(self):
        result = review_transcript('한 개요')
        self.assertEqual(result['reviewed_text'], '한 개요')
        self.assertIsNone(result['context_expansion'])

    def test_temperature_reply_keeps_quantity_and_asks_whip(self):
        result = review_transcript('차갑게', CONTEXTS['temperature'])
        facts = policy_check(result['lexical_text'], CONTEXTS['temperature'])
        self.assertEqual(facts['menu_id'], 'cafe_mocha')
        self.assertEqual(facts['quantity'], 1)
        self.assertEqual(facts['temperature'], 'ice')
        self.assertEqual(facts['missing_fields'], ['whipped_cream'])

    def test_whip_reply(self):
        for text, expected in [('빼줘', 'none'), ('많이', 'extra'), ('적게', 'light'), ('일반', 'normal')]:
            with self.subTest(text=text):
                result = review_transcript(text, CONTEXTS['whip'])
                self.assertEqual(result['context_expansion']['value'], expected)
                self.assertEqual(policy_check(result['lexical_text'], CONTEXTS['whip'])['whipped_cream'], expected)

    def test_new_menu_is_not_swallowed_as_previous_answer(self):
        result = review_transcript('아바라 두 잔 주세요', CONTEXTS['quantity'])
        self.assertIsNone(result['context_expansion'])
        self.assertIn('바닐라라떼', result['reviewed_text'])

    def test_context_not_mutated(self):
        context = copy.deepcopy(CONTEXTS['quantity'])
        before = copy.deepcopy(context)
        review_transcript('한 개요', context)
        self.assertEqual(context, before)

    def test_unconfigured_menu_or_option_is_not_a_simple_validated_order(self):
        for text in ('아메리카노 한 잔에 샷 두 개', '아메리카노 한 잔과 아이스티 한 잔'):
            with self.subTest(text=text):
                self.assertEqual(policy_check(text)['scope'], 'not_a_simple_single_add')

    def test_price_or_help_request_not_scored_as_an_add(self):
        self.assertEqual(policy_check('아메리카노 한 잔 얼마예요')['scope'], 'not_a_simple_single_add')

    def test_uncertain_unit_keeps_number_without_calling_it_missing(self):
        for text in ('딸기라떼 두대주세요', '딸기라떼두대주세요', '딸기라떼 두 대 주세요'):
            with self.subTest(text=text):
                result = review_transcript(text)
                self.assertEqual(result['reviewed_text'], text)
                facts = policy_check(result['lexical_text'])
                self.assertEqual(facts['quantity'], 2)
                self.assertEqual(facts['quantity_status'], 'unit_uncertain')
                self.assertNotIn('quantity', facts['missing_fields'])
                self.assertTrue(facts['needs_quantity_confirmation'])
                self.assertEqual(facts['next_question'], '두 잔을 말씀하신 건가요?')
                self.assertFalse(facts['simple_required_fields_complete'])

    def test_uncertain_unit_in_explicit_pending_context(self):
        facts = policy_check('두대요', CONTEXTS['quantity'])
        self.assertEqual(facts['menu_id'], 'americano')
        self.assertEqual(facts['quantity'], 2)
        self.assertEqual(facts['temperature'], 'ice')
        self.assertEqual(facts['quantity_status'], 'unit_uncertain')

    def test_true_absence_is_distinct_from_bad_unit(self):
        self.assertEqual(quantity_info('딸기라떼 주세요')['status'], 'missing')
        self.assertEqual(quantity_info('딸기라떼 두대주세요')['status'], 'unit_uncertain')
        self.assertEqual(quantity_info('딸기라떼 두 잔 주세요')['status'], 'explicit')

    def test_cup_is_an_explicit_drink_quantity(self):
        facts = policy_check('딸기라떼 두 컵 주세요')
        self.assertEqual(facts['quantity'], 2)
        self.assertEqual(facts['quantity_status'], 'explicit')

    def test_option_count_and_particle_are_not_drink_quantity(self):
        self.assertEqual(read_quantity('뜨아 한 잔 얼음은 두 개만'), 1)
        self.assertEqual(quantity_info('아메리카노 얼음 두 대만')['status'], 'missing')

    def test_ambiguous_and_out_of_range_are_not_missing(self):
        self.assertEqual(quantity_info('딸기라떼 두 잔 세 잔')['status'], 'ambiguous')
        result = policy_check('딸기라떼 10잔 주세요')
        self.assertEqual(result['quantity'], 10)
        self.assertEqual(result['quantity_status'], 'out_of_range')
        self.assertNotIn('quantity', result['missing_fields'])
        self.assertTrue(result['needs_quantity_confirmation'])


class PairingTests(unittest.TestCase):
    def test_both_branches_share_prompt_catalog_and_context(self):
        a = payload(PROFILES['home'], '아아 한 잔 주세요', CONTEXTS['quantity'])
        b = payload(PROFILES['home'], '아이스 아메리카노 한 잔 주세요', CONTEXTS['quantity'])
        self.assertEqual(a['messages'][0], b['messages'][0])
        ad, bd = json.loads(a['messages'][1]['content']), json.loads(b['messages'][1]['content'])
        self.assertEqual(ad['context'], bd['context'])
        self.assertEqual(ad['menu'], bd['menu'])
        self.assertNotIn('expected', ad)
        self.assertEqual(len(ad['menu']), 6)
        self.assertEqual(a['response_format'], b['response_format'])
        self.assertEqual(a['response_format']['type'], 'json_schema')

    @patch('qwen_client.check_model')
    @patch('qwen_client.request_order')
    def test_identical_text_reuses_one_real_response_explicitly(self, request, check):
        request.return_value = {'status': 'ok', 'model_called': True, 'request_ms': 42, 'raw_content': '{}'}
        result = compare(PROFILES['home'], review_transcript('딸기라떼 두 잔 주세요'))
        self.assertEqual(request.call_count, 1)
        self.assertFalse(result['B_reviewed']['model_called'])
        self.assertIsNone(result['B_reviewed']['request_ms'])
        self.assertTrue(result['B_reviewed']['reused_identical_request'])

    @patch('qwen_client.check_model')
    @patch('qwen_client.request_order')
    def test_different_text_calls_both(self, request, check):
        request.return_value = {'status': 'ok', 'model_called': True}
        result = compare(PROFILES['home'], review_transcript('아아 한 잔 주세요'))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[1], '아아 한 잔 주세요')
        self.assertEqual(request.call_args_list[1].args[1], '아이스 아메리카노 한 잔 주세요')

    @patch('qwen_client.check_model')
    @patch('qwen_client.request_order')
    def test_network_failure_skips_second_call(self, request, check):
        request.return_value = {'status': 'error', 'model_called': True}
        result = compare(PROFILES['home'], review_transcript('아아 한 잔 주세요'))
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result['B_reviewed']['status'], 'skipped')

    def test_diagnosis_does_not_repair_model_response(self):
        row = {'status': 'ok', 'parsed': {'intent': 'add', 'items': [{'menu_id': 'americano', 'quantity': 1,
               'temperature': 'ice', 'size': 'regular'}], 'needs_clarification': False, 'clarification_question': ''}}
        before = copy.deepcopy(row)
        diagnosis = diagnose(row, policy_check('아아 주세요'))
        self.assertEqual(diagnosis['status'], 'disagreement')
        self.assertEqual(row, before)

    def test_absent_clarification_field_is_not_reported_as_a_repeated_question(self):
        row = {'status': 'ok', 'parsed': {'intent': 'add', 'items': [{'menu_id': 'americano',
               'quantity': 1, 'temperature': 'ice', 'size': 'regular'}]}}
        check = diagnose(row, policy_check('아아 한 잔 주세요'))
        self.assertIn('필수 응답 필드 누락: needs_clarification', check['issues'])
        self.assertNotIn('단순 필수 정보가 있는데 다시 질문함', check['issues'])

    def test_complete_simple_order_agrees_but_conflicting_intent_does_not(self):
        row = {'status': 'ok', 'parsed': {'intent': 'add', 'items': [{'menu_id': 'americano',
               'quantity': 1, 'temperature': 'ice', 'size': 'regular'}], 'needs_clarification': False,
               'clarification_question': ''}}
        self.assertEqual(diagnose(row, policy_check('아아 한 잔 주세요'))['status'], 'basic_fields_agree')
        row['parsed']['intent'] = 'clarify'
        self.assertEqual(diagnose(row, policy_check('아아 한 잔 주세요'))['status'], 'disagreement')

    def test_uncertain_unit_requires_question_but_number_two_is_not_invented(self):
        row = {'status': 'ok', 'parsed': {'intent': 'add', 'items': [{'menu_id': 'strawberry_latte',
               'quantity': 2, 'temperature': 'ice', 'size': 'regular'}], 'needs_clarification': False,
               'clarification_question': ''}}
        facts = policy_check('딸기라떼 두대주세요')
        check = diagnose(row, facts)
        self.assertIn('수량 단위/표현 확인을 생략함', check['issues'])
        self.assertNotIn('quantity: 누락 값을 임의로 채움', check['issues'])
        row['parsed'].update(intent='clarify', needs_clarification=True, clarification_question='두 잔을 말씀하신 건가요?')
        self.assertEqual(diagnose(row, facts)['status'], 'basic_fields_agree')

    def test_question_conflicts_with_false_clarification_flag(self):
        row = {'status': 'ok', 'parsed': {'intent': 'add', 'items': [{'menu_id': 'americano',
               'quantity': 1, 'temperature': 'ice', 'size': 'regular'}], 'needs_clarification': False,
               'clarification_question': '따뜻하게 드릴까요?'}}
        self.assertIn('확인 불필요라고 하면서 질문 문장을 반환함', diagnose(row, policy_check('아아 한 잔 주세요'))['issues'])


class RecordingTests(unittest.TestCase):
    def test_existing_old_csv_is_preserved_and_new_unit_classification_saved(self):
        with tempfile.TemporaryDirectory(prefix='bom-review-test-') as temporary:
            folder = Path(temporary)
            old = folder / 'review-records.csv'
            old.write_text('old experiment data\n', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                make_record('딸기라떼 두대주세요', 'none', 'home', folder, False, 'regression_fixture')
            self.assertEqual(old.read_text(encoding='utf-8'), 'old experiment data\n')
            with csv_file(folder).open(encoding='utf-8-sig', newline='') as handle:
                row = list(csv.DictReader(handle))[0]
            self.assertEqual(row['quantity_status'], 'unit_uncertain')
            self.assertEqual(row['quantity_candidate'], '2')
            self.assertEqual(row['A_status'], 'not_requested')

    def test_csv_appends_rows_without_a_second_header(self):
        with tempfile.TemporaryDirectory(prefix='bom-review-test-') as temporary:
            folder = Path(temporary)
            with contextlib.redirect_stdout(io.StringIO()):
                make_record('망고스무디 주세요', 'none', 'home', folder, False, 'regression_fixture')
                make_record('딸기라떼 두 잔 주세요', 'none', 'home', folder, False, 'regression_fixture')
            with csv_file(folder).open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual([r['quantity_status'] for r in rows], ['missing', 'explicit'])


if __name__ == '__main__': unittest.main(verbosity=2)
