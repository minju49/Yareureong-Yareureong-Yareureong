"""Independent scoring, experimental design, and audit regressions, not voice data."""
import contextlib
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_batch as batch
from qwen_client import payload, PROFILES
from review import review_transcript
from run_review import CONTEXTS


def response(expected, text=''):
    parsed = copy.deepcopy(expected)
    needed = parsed.pop('question_required')
    parsed['clarification_question'] = '몇 잔 드릴까요?' if needed else ''
    return {'status': 'ok', 'parsed': parsed, 'raw_content': json.dumps(parsed, ensure_ascii=False),
            'model_called': True, 'request_ms': 12.5, 'input_text': text}


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = batch.load_cases()
        cls.cases = {case['id']: case for case in cls.dataset['cases']}

    def test_dataset_scope_and_denominators(self):
        self.assertEqual(len(self.cases), 56)
        self.assertEqual(sum(c['expected_model'] is not None for c in self.cases.values()), 44)
        self.assertTrue(all(c['source_kind'] == 'constructed_text_development' for c in self.cases.values()))

    def test_correct_reference(self):
        expected = self.cases['N01']['expected_model']
        self.assertTrue(batch.score_model(response(expected), expected)['correct'])

    def test_literal_boolean_is_not_quantity_one(self):
        expected = self.cases['N01']['expected_model']
        row = response(expected)
        row['parsed']['items'][0]['quantity'] = True
        self.assertFalse(batch.score_model(row, expected)['correct'])

    def test_guessed_missing_quantity_is_wrong(self):
        expected = self.cases['F06']['expected_model']
        row = response(expected)
        row['parsed']['items'][0]['quantity'] = 1
        self.assertFalse(batch.score_model(row, expected)['fields']['quantity'])

    def test_extra_menu_fails(self):
        expected = self.cases['N01']['expected_model']
        row = response(expected)
        row['parsed']['items'].append(copy.deepcopy(row['parsed']['items'][0]))
        self.assertFalse(batch.score_model(row, expected)['correct'])

    def test_unknown_menu_should_not_invent_item(self):
        expected = self.cases['M01']['expected_model']
        row = response(expected)
        self.assertTrue(batch.score_model(row, expected)['correct'])
        row['parsed']['items'] = copy.deepcopy(self.cases['N01']['expected_model']['items'])
        self.assertFalse(batch.score_model(row, expected)['correct'])

    def test_required_question_presence_and_empty_answer(self):
        expected = self.cases['F01']['expected_model']
        row = response(expected)
        row['parsed']['clarification_question'] = ''
        self.assertFalse(batch.score_model(row, expected)['fields']['question_presence'])
        expected2 = self.cases['N01']['expected_model']
        row2 = response(expected2)
        row2['parsed']['clarification_question'] = '정말요?'
        self.assertFalse(batch.score_model(row2, expected2)['correct'])

    def test_error_not_marked_correct(self):
        score = batch.score_model({'status': 'error'}, self.cases['N01']['expected_model'])
        self.assertTrue(score['scored'])
        self.assertFalse(score['correct'])
        self.assertFalse(score['available'])

    def test_ambiguous_cases_are_not_silently_correct(self):
        score = batch.score_model(response(self.cases['N01']['expected_model']), None)
        self.assertFalse(score['scored'])
        self.assertIsNone(score['correct'])

    def test_references_are_independent_of_policy_parser(self):
        expected = self.cases['N01']['expected_model']
        with patch('review.policy_check', side_effect=AssertionError('circular oracle')):
            self.assertTrue(batch.score_model(response(expected), expected)['correct'])

    def test_a_b_order_balances_only_changed_inputs(self):
        changed = review_transcript('아아 한 잔 주세요')
        unchanged = review_transcript('망고스무디 두 잔 주세요')
        self.assertEqual(batch.schedule({}, changed, 0), list(batch.BRANCHES))
        self.assertEqual(batch.schedule({}, changed, 1), list(reversed(batch.BRANCHES)))
        self.assertEqual(batch.schedule({}, unchanged, 8), ['A_original'])

    def test_payload_never_includes_reference_answers(self):
        case = self.cases['A01']
        for text in [case['text'], review_transcript(case['text'])['reviewed_text']]:
            body = payload(PROFILES['home'], text, CONTEXTS[case['context']])
            data = json.loads(body['messages'][1]['content'])
            self.assertEqual(set(data), {'text', 'menu', 'context'})
            self.assertNotIn('expected_model', json.dumps(body))
            self.assertNotIn('must_block', json.dumps(body))

    def test_unchanged_uses_one_real_call_no_zero_ms(self):
        case = self.cases['Q03']
        expected = case['expected_model']
        with patch.object(batch, 'request_order', side_effect=lambda p,t,c: response(expected,t)) as request:
            record = batch.execute_case(case, PROFILES['home'], ['A_original'])
        self.assertEqual(request.call_count, 1)
        self.assertFalse(record['responses']['B_reviewed']['model_called'])
        self.assertIsNone(record['responses']['B_reviewed']['request_ms'])
        self.assertEqual(batch.summarize([record], 1)['actual_calls'], 1)

    def test_raw_answer_preserved_catalog_completion_separate(self):
        case = self.cases['Q03']
        row = response(case['expected_model'], case['text'])
        row['parsed']['items'][0]['temperature'] = None
        row['raw_content'] = json.dumps(row['parsed'])
        original = copy.deepcopy(row)
        with patch.object(batch, 'request_order', return_value=row):
            record = batch.execute_case(case, PROFILES['home'], ['A_original'])
        actual = record['responses']['A_original']
        self.assertIsNone(actual['parsed']['items'][0]['temperature'])
        self.assertEqual(actual['raw_content'], original['raw_content'])
        self.assertFalse(actual['reference_score']['correct'])
        self.assertEqual(actual['order_decision']['validated_items'][0]['temperature'], 'ice')
        self.assertEqual(actual['gate_score'], 'accepted_correct')

    def test_unsafe_accept_is_detected_separately(self):
        case = self.cases['F06']
        row = {'status': 'ok', 'reference_score': {'correct': False},
               'order_decision': {'status': 'ready', 'can_accept_fields': True, 'validated_items': []}}
        self.assertEqual(batch.score_gate(row, case), 'unsafe_accept')

    def test_error_not_counted_as_successful_block(self):
        row = {'status': 'error', 'order_decision': {'status': 'unavailable', 'can_accept_fields': False}}
        self.assertEqual(batch.score_gate(row, self.cases['F06']), 'unavailable')

    def test_retry_call_count_not_hidden(self):
        case = self.cases['Q03']
        with patch.object(batch, 'request_order', side_effect=lambda p,t,c: response(case['expected_model'],t)):
            record = batch.execute_case(case, PROFILES['home'], ['A_original'])
        old = copy.deepcopy(record)
        record['previous_attempts'] = [old]
        result = batch.summarize([record], 1)
        self.assertEqual(result['actual_calls'], 2)
        self.assertEqual(result['calls_in_previous_attempts'], 1)

    def test_format_recovery_is_not_reported_as_two_valid_json_comparison(self):
        case = self.cases['Q03']
        with patch.object(batch, 'request_order', side_effect=lambda p,t,c: response(case['expected_model'],t)):
            record = batch.execute_case(case, PROFILES['home'], ['A_original'])
        first = record['responses']['A_original']
        first['status'] = 'invalid_response'
        first['reference_score'] = batch.score_model(first, case['expected_model'])
        summary = batch.summarize([record], 1)
        self.assertEqual(summary['outcomes']['improved'], 1)
        self.assertEqual(summary['format_recoveries_in_improved_cases'], 1)
        self.assertEqual(summary['common_valid_reference']['cases'], 0)

    def test_log_dedup_uses_request_identity_not_text_only(self):
        with tempfile.TemporaryDirectory(prefix='봄카페 검증 ') as tmp:
            folder = Path(tmp)
            source = folder / '기록.csv'
            common = {'input_text': '아아 한 잔 주세요', 'state_json': json.dumps({'session_id':'s1'}),
                      'diagnostics_json': json.dumps({'input_source':'microphone','stt':{'text':'아아 한 잔 주세요'}})}
            with source.open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=['created_at', *common])
                writer.writeheader()
                for stamp in ['t1', 't1', 't2']:
                    writer.writerow({'created_at':stamp, **common})
            summary = batch.audit_logs(folder, [source])
            self.assertEqual(summary['source_rows'], 3)
            self.assertEqual(summary['unique_requests'], 2)
            self.assertEqual(summary['distinct_microphone_texts'], 1)
            self.assertFalse(summary['cer_calculated'])
            self.assertEqual(summary['qwen_calls_here'], 0)

    def test_html_escapes_input_and_report_has_no_false_stt_claim(self):
        case = copy.deepcopy(self.cases['Q03'])
        with patch.object(batch, 'request_order', side_effect=lambda p,t,c: response(case['expected_model'],t)):
            record = batch.execute_case(case, PROFILES['home'], ['A_original'])
        record['case']['text'] = '<img src=x onerror=alert(1)>'
        with tempfile.TemporaryDirectory(prefix='보고서 검증 ') as tmp:
            folder = Path(tmp)
            summary = batch.render_report(folder, {'case_ids':[case['id']], 'profile':PROFILES['home'],
                'profile_key':'home','annotation_status':'draft'}, [record], None, True)
            page = (folder / '결과요약.html').read_text(encoding='utf-8')
            self.assertNotIn('<img src=x', page)
            self.assertIn('&lt;img', page)
            self.assertFalse(summary['stt_called_here'])
            self.assertFalse(summary['school_tested'])

    def test_validate_only_never_connects_model(self):
        with patch.object(sys_module := batch.sys, 'argv', ['run_batch.py','--validate-only']), \
             patch.object(batch, 'check_model', side_effect=AssertionError('must not connect')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(batch.main(), 0)


if __name__ == '__main__':
    unittest.main()
