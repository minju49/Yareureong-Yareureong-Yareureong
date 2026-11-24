import copy
import unittest
from case_context import resolve_context
from run_review import CONTEXTS
from run_batch import execute_case
from qwen_client import PROFILES
from unittest.mock import patch


class CaseContextTests(unittest.TestCase):
    def case(self):
        return {'id':'D01','context':'custom','context_data':{'menu_id':'vanilla_latte','quantity':None,
            'temperature':'ice','awaiting':'quantity','previous_question':'몇 잔 드릴까요?','previous_user_text':'아바라 주세요'}}
    def test_new_menu_context_is_copied_without_answer_injection(self):
        case=self.case();out=resolve_context(case,CONTEXTS)
        self.assertEqual(out['menu_id'],'vanilla_latte');self.assertIsNone(out['quantity'])
        out['quantity']=2;self.assertIsNone(case['context_data']['quantity'])
    def test_unknown_keys_and_prefilled_pending_answer_are_rejected(self):
        for patch_value in ({'expected_model':{}},{'quantity':2},{'quantity':True},{'menu_id':'unknown'}):
            case=self.case();case['context_data'].update(patch_value)
            with self.assertRaises(ValueError):resolve_context(case,CONTEXTS)
    def test_existing_named_contexts_are_unchanged(self):
        for key,value in CONTEXTS.items():self.assertEqual(resolve_context({'context':key},CONTEXTS),value)
    def test_custom_data_cannot_silently_override_named_context(self):
        with self.assertRaises(ValueError):resolve_context({'context':'quantity','context_data':{}},CONTEXTS)
    def test_new_context_reaches_both_arms_with_same_known_facts(self):
        case=self.case();case.update(text='두 잔이요',expected_model=None,must_block=False,preserve_tokens=['두'])
        rows=[]
        def call(profile,text,context):
            rows.append((text,copy.deepcopy(context)))
            return {'status':'error','model_called':True,'request_ms':1,'error':'controlled fixture'}
        with patch('run_batch.request_order',side_effect=call):
            execute_case(case,PROFILES['home'],['A_original'])
        self.assertEqual(rows[0][1]['menu_id'],'vanilla_latte');self.assertIsNone(rows[0][1]['quantity'])


if __name__=='__main__':unittest.main()
