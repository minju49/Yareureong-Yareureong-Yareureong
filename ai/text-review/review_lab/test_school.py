"""School transport fixtures only. No real school model is called by tests."""
import copy
import json
import unittest
from unittest.mock import patch

import qwen_client as client
import run_school
from review import review_transcript, policy_check
from run_review import CONTEXTS


class SchoolTransportTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'base_url':'http://example.invalid/ollama/v1','model':'qwen3.5:9b-q4_K_M','api_style':'ollama'}
        self.parsed = {'intent':'add','items':[], 'needs_clarification':False,'clarification_question':''}
        self.reply = {'model':self.profile['model'],'done':True,'done_reason':'stop',
                      'message':{'content':json.dumps(self.parsed)},'load_duration':1000000,'total_duration':2000000}

    def test_known_url_suffixes_normalize_to_one_native_base(self):
        for suffix in ['', '/', '/v1', '/api', '/api/tags', '/api/chat', '/v1/models']:
            self.assertEqual(client.api_base({**self.profile,'base_url':'http://example.invalid/ollama'+suffix}),
                             'http://example.invalid/ollama')

    def test_invalid_urls_do_not_become_requests(self):
        for url in ['file:///tmp/a','https://host/api?secret=x','http://user:pass@host/api']:
            with self.assertRaises(ValueError):
                client.api_base({**self.profile,'base_url':url})

    def test_native_model_list_uses_tags_and_exact_model(self):
        with patch.object(client,'http',return_value={'models':[{'name':self.profile['model']}]}) as http:
            client.check_model(self.profile)
        self.assertEqual(http.call_args.args[2], '/api/tags')
        with patch.object(client,'http',return_value={'models':[{'name':'some-other-model'}]}):
            with self.assertRaises(ValueError): client.check_model(self.profile)

    def test_native_payload_keeps_prompt_and_context_without_reference(self):
        context={'menu_id':'americano','awaiting':'quantity'}
        body=client.payload(self.profile,'두 잔',context)
        self.assertFalse(body['think'])
        self.assertFalse(body['stream'])
        self.assertEqual(body['format'],client.ORDER_SCHEMA)
        self.assertEqual(body['options'],{'temperature':0,'num_predict':1024})
        data=json.loads(body['messages'][1]['content'])
        self.assertEqual(set(data),{'text','context','menu'})
        self.assertEqual(data['context'],context)
        self.assertEqual(body['messages'][0]['content'],client.PROMPT)

    def test_native_json_and_raw_are_recorded_separately(self):
        before=copy.deepcopy(self.reply)
        with patch.object(client,'http',return_value=self.reply) as http:
            row=client.request_order(self.profile,'아아 한 잔',{})
        self.assertEqual(http.call_args.args[2],'/api/chat')
        self.assertEqual(row['endpoint'],'http://example.invalid/ollama/api/chat')
        self.assertEqual(row['status'],'ok')
        self.assertEqual(row['parsed'],self.parsed)
        self.assertEqual(row['raw_response'],before)
        self.assertEqual(row['server_load_ms'],1)

    def test_truncation_cannot_count_as_success_even_when_json_is_valid(self):
        self.reply['done_reason']='length'
        with patch.object(client,'http',return_value=self.reply):
            row=client.request_order(self.profile,'아아 한 잔',{})
        self.assertTrue(row['json_ok'])
        self.assertEqual(row['status'],'invalid_response')

    def test_unfinished_wrong_model_or_bad_json_cannot_count_as_success(self):
        for change in [{'done':False},{'model':'other'},{'message':{'content':'{"unfinished"'}}]:
            with patch.object(client,'http',return_value={**self.reply,**change}):
                row=client.request_order(self.profile,'아아 한 잔',{})
            self.assertNotEqual(row['status'],'ok')

    def test_server_rejecting_options_is_not_silently_retried(self):
        with patch.object(client,'http',side_effect=OSError('server rejected think parameter')) as http:
            row=client.request_order(self.profile,'아아 한 잔',{})
        self.assertEqual(http.call_count,1)
        self.assertEqual(row['status'],'error')
        self.assertIn('think',row['error'])

    def test_home_generation_contract_is_unchanged(self):
        body=client.payload(client.PROFILES['home'],'아아 한 잔',{})
        self.assertEqual(body['max_tokens'],512)
        self.assertEqual(body['temperature'],0)
        self.assertIn('response_format',body)
        self.assertNotIn('format',body)

    def test_normal_whip_suffix_only_uses_explicit_previous_question(self):
        for text in ['일반으로','보통으로요','기본으로 해주세요']:
            result=review_transcript(text,CONTEXTS['whip'])
            self.assertEqual(result['context_expansion']['value'],'normal')
            facts=policy_check(text,CONTEXTS['whip'])
            self.assertTrue(facts['simple_required_fields_complete'])
            self.assertEqual(facts['whipped_cream'],'normal')
            self.assertIsNone(review_transcript(text)['context_expansion'])
        for text in ['일반 말고 많이','일반으로 말고 빼줘']:
            self.assertIsNone(review_transcript(text,CONTEXTS['whip'])['context_expansion'])

    def test_cup_quantity_reply_preserves_known_menu_and_temperature(self):
        result=review_transcript('세 컵이요',CONTEXTS['quantity'])
        self.assertEqual(result['context_expansion']['value'],3)
        facts=policy_check('세 컵이요',CONTEXTS['quantity'])
        self.assertEqual((facts['menu_id'],facts['quantity'],facts['temperature']),('americano',3,'ice'))
        self.assertTrue(facts['simple_required_fields_complete'])

    def test_offline_self_check_never_configures_or_contacts_school(self):
        import contextlib,io
        with patch.object(run_school.sys,'argv',['run_school.py','check','--self-check']), \
             patch.object(run_school,'configure',side_effect=AssertionError('must not configure')), \
             patch.object(run_school,'preflight',side_effect=AssertionError('must not connect')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_school.main(),0)


if __name__=='__main__':
    unittest.main()
