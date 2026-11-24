import copy
import unittest
from gate_evidence import pending_answer
from order_gate import validate_order
from test_order_gate import response
from case_context import resolve_context
from run_batch import load_cases
from run_review import CONTEXTS
from pathlib import Path


class PendingEvidenceTests(unittest.TestCase):
    def context(self,field='quantity',menu='cafe_latte',q=None,temp='hot'):
        return {'menu_id':menu,'quantity':q,'temperature':temp,'awaiting':field,
            'previous_question':'확인 질문','previous_user_text':'앞서 말한 주문'}
    def test_known_complete_model_answers_are_no_longer_rejected_for_polite_suffixes(self):
        data=load_cases(Path(__file__).with_name('additional20_cases.json'))
        for ident in ('D03','D04','D05','D07','D11'):
            case=next(c for c in data['cases'] if c['id']==ident);item=case['expected_model']['items'][0]
            row=response(item['menu_id'],item['quantity'],item['temperature'],cream=item['whipped_cream'],input_text=case['text'])
            before=copy.deepcopy(row);ctx=resolve_context(case,CONTEXTS);ctx_before=copy.deepcopy(ctx)
            self.assertEqual(validate_order(row,case['text'],ctx)['status'],'ready',ident)
            self.assertEqual(row,before);self.assertEqual(ctx,ctx_before)
    def test_other_menus_and_suffixes_use_explicit_facts_only(self):
        for text,n in (('셋으로 부탁해요',3),('두 컵으로 해주세요',2),('하나를 주세요',1)):
            ctx=self.context(menu='vanilla_latte',temp='ice')
            out=validate_order(response('vanilla_latte',n),text,ctx)
            self.assertEqual(out['status'],'ready',text)
    def test_missing_context_and_assent_do_not_invent_a_menu_or_quantity(self):
        for text in ('하나로 주세요','아이스로 해주세요','많이 올려주세요'):
            self.assertIsNone(pending_answer(text,{}))
            self.assertFalse(validate_order(response(),text)['can_accept_fields'])
        self.assertIsNone(pending_answer('네',self.context()))
    def test_negation_correction_multiple_values_and_unknown_options_are_not_short_answers(self):
        examples=['두 잔 말고 한 잔으로 해주세요','두 잔이랑 한 잔 주세요','하나로 주세요 샷 추가',
            '하나 주지 마세요','하나는 필요 없어요','-1잔 주세요','1.5잔 주세요','열 잔 주세요','두 병으로 주세요']
        for text in examples:
            self.assertIsNone(pending_answer(text,self.context()),text)
            self.assertFalse(validate_order(response('cafe_latte',1,'hot'),text,self.context())['can_accept_fields'],text)
    def test_wrong_model_fields_are_still_blocked(self):
        ctx=self.context()
        for row in (response('cafe_latte',2,'hot'),response('americano',1,'hot'),response('cafe_latte',1,'ice')):
            self.assertFalse(validate_order(row,'하나로 주세요',ctx)['can_accept_fields'])
    def test_whip_reply_cannot_swallow_a_request_for_other_options(self):
        ctx=self.context('whipped_cream','cafe_mocha',1,'ice')
        for text in ('설탕 많이 올려주세요','샷 빼주세요','휘핑 안 빼주세요','조금만 올려줘요 그리고 샷도요'):
            self.assertIsNone(pending_answer(text,ctx),text)
            self.assertFalse(validate_order(response('cafe_mocha',1,'ice',cream='extra'),text,ctx)['can_accept_fields'],text)
    def test_invalid_or_prefilled_context_cannot_supply_evidence(self):
        for patch in ({'quantity':True},{'quantity':2},{'menu_id':'unknown'}):
            ctx=self.context();ctx.update(patch)
            self.assertIsNone(pending_answer('하나로 주세요',ctx))


if __name__=='__main__':unittest.main()
