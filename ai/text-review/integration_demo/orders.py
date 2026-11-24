"""Server-owned demonstration cart; touch and real Qwen share one state.

The frozen lab handles six voice menus. All 61 DB menus support touch. This
integration never promotes an unregistered voice interpretation into an order.
"""
import copy
from datetime import datetime,timezone
import re
import threading
import uuid

from review import MENUS,review_transcript,exact_mentions,quantity_info
from gate_evidence import validation_facts
from order_gate import validate_order
from qwen_client import request_order,PROMPT
from catalog import BRIDGE,db_id,lab_id,to_backend,cart_item,supported


def explicit_replacement(text):
    """Keep the final addition in an explicit remove-then-correct request."""
    parts = re.split(r'\s*[,，.]?\s*(?:아\s*[,，]\s*)?아니(?:요)?\s*[,，]?\s*', text)
    if len(parts) != 2:
        return None
    revoked, replacement = parts
    if len(exact_mentions(revoked)) != 1 or len(exact_mentions(replacement)) != 1:
        return None
    if not re.search(r'(?:빼(?:주고|고|줘요?|주세요)|취소(?:하고|해줘요?|해주세요))\s*[.!]?$', revoked):
        return None
    if not re.search(r'추가\s*(?:해\s*줘요?|해\s*주세요|할게요?)\s*[.!]?$', replacement):
        return None
    if re.search(r'말고|제외|하지\s*마|그리고|이랑|둘\s*다|모두|전부', text):
        return None
    return replacement


class OrderSession:
    def __init__(self,backend,profile,catalog,model_request=request_order):
        self.backend=backend;self.profile=copy.deepcopy(profile);self.catalog=catalog;self.call_model=model_request
        self.profile['system_prompt']=PROMPT+'''\nFor this integrated demo, items contains ONLY the requested change, never a copy of current_order.
Add: return requested new items. Remove: intent=remove; give the explicit target and quantity; quantity=null means cancel the whole named drink when no count is said.
Reset: intent=reset for cancelling the whole cart. Confirm: intent=confirm for proceeding with the existing cart.
current_order in context is read-only background. Never add its items again. A pending question uses only its known previous facts and the current reply.'''
        self.id=uuid.uuid4().hex;self.revision=0;self.cart=[];self.pending=None
        self.message='주문하실 메뉴를 말씀해 주세요.';self.place='';self.phase='order';self.receipt=None
        self.last=None;self.lock=threading.Lock();self.completed={}
    def state(self):
        return {'session_id':self.id,'revision':self.revision,'cart':copy.deepcopy(self.cart),
            'total':sum(x['subtotal'] for x in self.cart),'pending':copy.deepcopy(self.pending),
            'message':self.message,'phase':self.phase,'place':self.place,'receipt':copy.deepcopy(self.receipt),
            'diagnostics':copy.deepcopy(self.last),'price_source':'Spring → MariaDB menus_catalog'}
    def _replace(self,items):
        # Quote the entire candidate cart BEFORE committing it. A backend error
        # preserves the previous cart and the pending request.
        merged=[]
        for raw in items:
            item=cart_item(raw);key=(item['menu_id'],item['temperature'],item['size'])
            existing=next((v for v in merged if (v['menu_id'],v['temperature'],v['size'])==key),None)
            if existing:
                if existing['whipped_cream']!=item['whipped_cream']:raise ValueError('같은 음료의 휘핑 선택을 확인해주세요.')
                existing['quantity']+=item['quantity']
            else:merged.append(item)
        checked=self.backend.quote(merged)
        self.cart=checked['items'];self.pending=None;self.phase='order'
    def add(self,items):
        proposal=[cart_item(x) for x in self.cart]
        for item in items:
            x=to_backend(item)
            current=next((v for v in proposal if (v['menu_id'],v['temperature'],v['size'])==(x['menu_id'],x['temperature'],x['size'])),None)
            if current:
                if current['whipped_cream']!=x['whipped_cream']:raise ValueError('같은 음료의 휘핑 선택이 달라요. 기존 음료의 옵션을 바꿔주세요.')
                current['quantity']+=x['quantity']
            else:proposal.append(x)
        self._replace(proposal);self.message='장바구니에 담았어요.'
    def _context(self):
        p=self.pending
        if not p or p.get('kind')!='add':return {}
        return {'menu_id':p['menu_id'],'quantity':p['quantity'],'temperature':p['temperature'],
            'awaiting':p['awaiting'],'previous_question':p['question'],'previous_user_text':p['source_text']}
    def _ask(self,facts,source):
        missing=facts.get('missing_fields',[])
        if not missing:
            self.message=facts.get('next_question') or '선택 내용을 다시 확인해주세요.';return
        field=missing[0];choices={
            'quantity':[{'label':str(q)+'잔','value':str(q)+'잔'} for q in (1,2,3,4,5)],
            'temperature':[{'label':'따뜻하게','value':'따뜻하게'},{'label':'차갑게','value':'차갑게'}],
            'whipped_cream':[{'label':'일반','value':'일반'},{'label':'많이','value':'많이'},
                {'label':'적게','value':'적게'},{'label':'빼기','value':'빼기'}]}[field]
        self.pending={'kind':'add','menu_id':facts['menu_id'],'quantity':facts['quantity'],
            'temperature':facts['temperature'],'whipped_cream':facts.get('whipped_cream'),'awaiting':field,'question':facts['next_question'],
            'choices':choices,'source_text':source}
        self.message=facts['next_question']
    def _remove(self,index,quantity):
        if type(index) is not int or not 0<=index<len(self.cart):raise ValueError('삭제할 주문을 다시 선택해주세요.')
        if type(quantity) is not int or quantity<1 or quantity>self.cart[index]['quantity']:raise ValueError('삭제 수량을 확인해주세요.')
        proposed=[cart_item(x) for x in self.cart];proposed[index]['quantity']-=quantity
        if not proposed[index]['quantity']:proposed.pop(index)
        self._replace(proposed);self.message='장바구니를 수정했어요.'
    def text(self,raw):
        if not isinstance(raw,str) or not raw.strip() or len(raw)>1000:raise ValueError('주문 문장을 입력해주세요.')
        original=raw
        replacement=explicit_replacement(raw)
        if replacement is not None:
            raw=replacement
        context=self._context();mentions=exact_mentions(raw)
        # Explicit new menu text is never combined with an unrelated old pending
        # answer. An unfinished request is separate from the committed cart.
        if mentions:context={}
        review=review_transcript(raw,context)
        model_context={**context,'current_order':[{**cart_item(x),'menu_id':lab_id(x['menu_id'])} for x in self.cart]}
        row=self.call_model(self.profile,review['reviewed_text'],model_context)
        self.last={'input_text':original,'input_source':'text','review':review,'qwen':row,
            'model_called':row.get('model_called',True),'integration_scope':'six_voice_menus; 61 touch menus; real Spring quote'}
        if replacement is not None:
            self.last['explicit_correction']={'original':original,'effective_request':raw,
                'reason':'명시적으로 고쳐 말한 마지막 추가 요청을 검증합니다.'}
        if row.get('status')!='ok':
            self.message='학교 Qwen 응답을 확인하지 못했어요. 연결 상태를 확인해주세요.';return
        parsed=row.get('parsed',{});ids=list(dict.fromkeys(m['menu_id'] for m in mentions))
        if re.fullmatch(r'\s*(?:다\s*취소(?:해줘|해주세요)?|전체\s*취소|처음부터\s*다시(?:\s*할래)?)[.!?]?\s*',raw) and parsed.get('intent')=='reset':
            self.cart=[];self.pending=None;self.message='주문을 모두 비웠어요.';return
        if re.search(r'이대로|주문\s*(?:확정|할게|완료)',raw) and parsed.get('intent')=='confirm':
            if self.pending:self.message='먼저 진행 중인 선택을 마쳐주세요.'
            elif self.cart:self.phase='review';self.message='주문 내용과 합계를 확인해주세요.'
            else:self.message='먼저 메뉴를 담아주세요.'
            return
        if re.search(r'빼|취소|삭제',raw) and parsed.get('intent')=='remove':
            if len(ids)!=1 or re.search(r'아니|말고|추가|그리고|이랑',raw):
                self.message='어떤 음료를 바꿀지 화면에서 선택해주세요.';return
            detail=quantity_info(raw);q=detail['value']
            target_id=ids[0];temps={m['temperature'] for m in mentions if m.get('temperature')}
            model_items=parsed.get('items',[])
            if (len(model_items)!=1 or model_items[0].get('menu_id')!=target_id
                or model_items[0].get('quantity')!=q or (temps and model_items[0].get('temperature') not in temps)):
                self.message='삭제할 메뉴와 수량을 다시 확인해주세요.';return
            candidates=[i for i,x in enumerate(self.cart) if x['menu_id']==db_id(target_id) and (not temps or x['temperature'] in temps)]
            if len(candidates)!=1:self.message='삭제할 음료를 주문 내역에서 선택해주세요.';return
            index=candidates[0]
            if detail['status'] not in ('explicit','missing'):self.message='삭제할 수량을 다시 말씀해 주세요.';return
            q=q if q is not None else self.cart[index]['quantity']
            self._remove(index,q);return
        if len(ids)>1:
            # Check every explicit menu clause against its own model item. An
            # ambiguous correction is held rather than partially applied.
            if parsed.get('intent')!='add' or re.search(r'아니|말고|취소|빼|바꿔|변경',raw):
                self.message='복잡한 변경은 한 메뉴씩 말씀해 주세요.';return
            clauses=re.split(r'\s*(?:이랑|랑|하고|그리고|(?<=[잔개컵])(?:와|과))\s*',raw)
            if len(clauses)!=len(ids) or len(parsed.get('items',[]))!=len(ids):
                self.message='메뉴를 한 가지씩 다시 말씀해 주세요.';return
            confirmed=[];checks=[]
            for segment in clauses:
                segment_mentions=exact_mentions(segment)
                clause_ids=set(m['menu_id'] for m in segment_mentions)
                if len(clause_ids)!=1:break
                candidates=[x for x in parsed['items'] if x.get('menu_id') in clause_ids]
                if len(candidates)!=1:break
                sub=copy.deepcopy(row);sub['parsed']={**parsed,'items':candidates}
                gate=validate_order(sub,review['reviewed_text'],evidence_text=segment,changes=review['changes'])
                gate['projection_note']='전체 Qwen 응답의 해당 메뉴 항목을 원문 절과 대조. 새 모델 호출이나 원본 응답 수정 없음.'
                checks.append(gate)
                if not gate['can_accept_fields']:break
                confirmed.extend(gate['validated_items'])
            self.last['multi_item_validation']=checks
            if len(confirmed)==len(ids):self.add(confirmed)
            else:self.message='각 음료의 메뉴·수량·온도를 한 가지씩 말씀해 주세요.'
            return
        gate=validate_order(row,review['reviewed_text'],context,evidence_text=review['lexical_text'],changes=review['changes'])
        self.last['validation']=gate
        facts=gate['source_facts']
        if gate['can_accept_fields']:self.add(gate['validated_items'])
        elif facts.get('scope')=='simple_single_add' and facts.get('missing_fields') and not facts.get('temperature_conflict'):
            self._ask(facts,raw)
        else:self.message=gate['question'] or '주문 내용을 다시 확인해주세요. 메뉴를 한 가지씩 말씀해 주세요.'
    def touch(self,body):
        action=body.get('action')
        if action=='add':
            item=body.get('item',{});self.add([item]);return
        if action=='edit':
            index=body.get('index');item=body.get('item')
            if type(index) is not int or not 0<=index<len(self.cart):raise ValueError('수정할 음료를 다시 선택해주세요.')
            proposal=[cart_item(x) for x in self.cart];proposal[index]=cart_item(item);self._replace(proposal);self.message='옵션을 변경했어요.';return
        if action=='quantity':
            index=body.get('index');delta=body.get('delta')
            if type(index) is not int or not 0<=index<len(self.cart) or delta not in (-1,1):raise ValueError('수량 변경을 확인해주세요.')
            proposal=[cart_item(x) for x in self.cart];proposal[index]['quantity']+=delta
            if proposal[index]['quantity']==0:proposal.pop(index)
            self._replace(proposal);self.message='수량을 바꿨어요.';return
        if action=='remove':self._remove(body.get('index'),body.get('quantity',1));return
        if action=='cancel_pending':self.pending=None;self.message='진행 중인 선택을 취소했어요.';return
        if action=='reset':self.cart=[];self.pending=None;self.phase='order';self.receipt=None;self.message='새 주문을 시작해요.';return
        if action=='place':
            if body.get('place') not in ('dine_in','takeaway'):raise ValueError('매장 또는 포장을 선택해주세요.')
            self.place=body['place'];return
        if action=='answer':
            if not self.pending:raise ValueError('진행 중인 질문이 없습니다.')
            value=body.get('value','');p=copy.deepcopy(self.pending)
            if value not in [x['value'] for x in p['choices']]:raise ValueError('화면에 있는 선택지를 눌러주세요.')
            field=p['awaiting']
            if field=='quantity':p['quantity']=int(value.removesuffix('잔'))
            elif field=='temperature':p['temperature']={'따뜻하게':'hot','차갑게':'ice'}[value]
            else:p['whipped_cream']={'일반':'normal','많이':'extra','적게':'light','빼기':'none'}[value]
            missing=[]
            if p['quantity'] is None:missing.append('quantity')
            if p['temperature'] is None:missing.append('temperature')
            if MENUS[p['menu_id']]['ask_whip'] and p.get('whipped_cream') is None:missing.append('whipped_cream')
            self.last={'input_source':'touch','model_called':False,'applied_source':'explicit_option_selection','selected_field':field,'selected_value':value}
            if missing:
                questions={'quantity':'몇 잔 드릴까요?','temperature':'따뜻하게 드릴까요, 차갑게 드릴까요?','whipped_cream':'휘핑은 어떻게 해드릴까요?'}
                self._ask({**p,'missing_fields':missing,'next_question':questions[missing[0]]},p['source_text'])
            else:self.add([{'menu_id':p['menu_id'],'quantity':p['quantity'],'temperature':p['temperature'],'size':'regular',
                'whipped_cream':p.get('whipped_cream'),'custom_note':''}])
            return
        if action=='confirm':
            if self.pending:raise ValueError('진행 중인 선택을 먼저 마쳐주세요.')
            if not self.cart:raise ValueError('먼저 메뉴를 담아주세요.')
            receipt=self.backend.confirm([cart_item(x) for x in self.cart],self.place,body['request_id'])
            self.receipt=receipt;self.phase='complete';self.message='시연 주문을 저장했어요. 실제 결제는 진행되지 않습니다.';return
        raise ValueError('지원하지 않는 주문 조작입니다.')
    def apply(self,body,source='touch'):
        key=body.get('request_id');revision=body.get('revision')
        if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',key):raise ValueError('요청 번호가 올바르지 않습니다.')
        with self.lock:
            if key in self.completed:return copy.deepcopy(self.completed[key])
            if type(revision) is not int or revision!=self.revision:raise ValueError('주문 화면이 바뀌었어요. 새로고침한 후 다시 시도해주세요.')
            if self.phase=='complete' and body.get('action')!='reset':raise ValueError('완료된 주문입니다. 새 주문을 시작해주세요.')
            before=(copy.deepcopy(self.cart),copy.deepcopy(self.pending),self.phase,self.receipt,self.place)
            try:
                if source=='text':self.text(body.get('text',''))
                else:self.touch(body)
                self.revision+=1;state=self.state();self.completed[key]=copy.deepcopy(state);return state
            except Exception:
                self.cart,self.pending,self.phase,self.receipt,self.place=before;raise
