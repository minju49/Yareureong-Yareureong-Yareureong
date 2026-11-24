import copy
import sys
from pathlib import Path
import unittest
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'integration_demo'),str(ROOT/'review_lab')]
from orders import OrderSession


def item(menu='americano',q=1,temp='ice',cream=None):
    return {'menu_id':menu,'quantity':q,'temperature':temp,'size':'regular','whipped_cream':cream,'custom_note':''}


class BackendFixture:
    def quote(self,items):
        prices={'americano':1800,'vanilla_latte':3300,'cafe_latte':2900,'strawberry_fruit_latte':3800,'mango_smoothie':3800,'cafe_mocha':3500}
        if any(type(x['quantity']) is not int or not 1<=x['quantity']<=9 for x in items):raise ValueError('invalid quantity fixture')
        lines=[{**x,'name':x['menu_id'],'unit_price':prices[x['menu_id']],'subtotal':prices[x['menu_id']]*x['quantity']} for x in items]
        return {'items':lines,'total':sum(x['subtotal'] for x in lines)}
    def confirm(self,items,place,key):return {'order_id':'FIXTURE','total':self.quote(items)['total'],'payment_simulated':True}


def model(items,intent='add',needs=False,question=''):
    def run(profile,text,context):
        return {'model_called':True,'status':'ok','input_text':text,'raw_content':'CONTROLLED FIXTURE',
            'parsed':{'intent':intent,'items':copy.deepcopy(items),'needs_clarification':needs,'clarification_question':question}}
    return run


class SessionTests(unittest.TestCase):
    def new(self,request):return OrderSession(BackendFixture(),{},[],model_request=request)
    def apply(self,s,text=None,**kw):
        return s.apply({'request_id':uuid.uuid4().hex,'revision':s.revision,**({'text':text} if text is not None else {}),**kw},source='text' if text is not None else 'touch')
    def test_touch_and_voice_use_one_cart_and_backend_prices(self):
        s=self.new(model([item('cafe_latte',1,'hot')]))
        self.apply(s,action='add',item=item());state=self.apply(s,'따뜻한 카페라떼 한 잔 주세요')
        self.assertEqual(state['total'],4700);self.assertEqual(len(state['cart']),2)
    def test_both_approved_aliases_add_atomically(self):
        s=self.new(model([item(q=2),item('vanilla_latte')]))
        state=self.apply(s,'아아 두 잔이랑 아바라 한 잔 주세요')
        self.assertEqual(state['total'],6900);self.assertEqual(len(state['cart']),2)
    def test_complete_two_drinks_keep_temperature_prefixes_in_evidence(self):
        s=self.new(model([item(q=2),item('cafe_latte',1,'hot')]))
        state=self.apply(s,'아이스 아메리카노 두 잔이랑 따뜻한 카페라떼 한 잔 주세요')
        self.assertEqual(state['total'],6500)
    def test_unknown_extra_clause_is_not_partially_committed(self):
        s=self.new(model([item(q=2),item('vanilla_latte')]))
        self.assertFalse(self.apply(s,'아아 두 잔이랑 아바라 한 잔 그리고 레몬차요')['cart'])
    def test_pending_is_separate_and_polite_answer_completes_it(self):
        s=self.new(model([item('cafe_latte',1,None)],intent='clarify',needs=True,question='온도요?'))
        first=self.apply(s,'카페라떼 한 잔 주세요');self.assertFalse(first['cart']);self.assertEqual(first['pending']['awaiting'],'temperature')
        s.call_model=model([item('cafe_latte',1,'ice')]);state=self.apply(s,'아이스로 해주세요')
        self.assertIsNone(state['pending']);self.assertEqual(state['total'],2900)
    def test_backend_error_preserves_cart_and_pending(self):
        s=self.new(model([item()]));self.apply(s,action='add',item=item())
        before=copy.deepcopy(s.cart)
        with self.assertRaises(ValueError):self.apply(s,action='add',item=item(q=9))
        self.assertEqual(s.cart,before)
    def test_repeated_http_id_does_not_duplicate_an_order(self):
        s=self.new(model([item()]));body={'request_id':uuid.uuid4().hex,'revision':0,'action':'add','item':item()}
        first=s.apply(body);second=s.apply(body)
        self.assertEqual(first,second);self.assertEqual(s.cart[0]['quantity'],1)
    def test_wrong_removal_model_does_not_delete_cart(self):
        s=self.new(model([item('vanilla_latte')],intent='remove'))
        self.apply(s,action='add',item=item(q=2));state=self.apply(s,'아메리카노 하나 빼줘')
        self.assertEqual(state['cart'][0]['quantity'],2)
    def test_recognized_removal_deducts_only_requested_count(self):
        s=self.new(model([item()],intent='remove'))
        self.apply(s,action='add',item=item(q=2));state=self.apply(s,'아아 하나 빼줘')
        self.assertEqual(state['cart'][0]['quantity'],1)
    def test_explicit_correction_keeps_the_original_drink(self):
        s=self.new(model([item('vanilla_latte')]))
        self.apply(s,action='add',item=item())
        state=self.apply(s,'아아 하나 빼주고 아니 아바라 하나 추가해줘')
        self.assertEqual(state['total'],5100)
        self.assertEqual([x['menu_id'] for x in state['cart']],['americano','vanilla_latte'])
        self.assertEqual(state['diagnostics']['explicit_correction']['effective_request'],'아바라 하나 추가해줘')
    def test_ambiguous_correction_does_not_change_cart(self):
        s=self.new(model([item('vanilla_latte')]))
        self.apply(s,action='add',item=item())
        state=self.apply(s,'아아 하나 빼주고 아니 아바라 하나')
        self.assertEqual(state['total'],1800)
        self.assertNotIn('explicit_correction',state['diagnostics'])
    def test_touch_answer_completes_question_without_another_model_call(self):
        s=self.new(model([item('cafe_latte',1,None)],intent='clarify',needs=True,question='온도요?'))
        self.apply(s,'카페라떼 한 잔 주세요')
        def forbidden(*args):raise AssertionError('Touch selection must not depend on Qwen')
        s.call_model=forbidden;state=self.apply(s,action='answer',value='차갑게')
        self.assertEqual(state['total'],2900);self.assertIsNone(state['pending'])
        self.assertFalse(state['diagnostics']['model_called'])


if __name__=='__main__':unittest.main()
