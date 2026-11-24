"""Evidence for post-model validation, independent of model predictions.

The pre-Qwen reviewer and prompt remain frozen. This parser only recognizes a
whole short reply to an explicitly pending question, with polite suffixes.
It never obtains a missing value or a menu from the model's answer.
"""
import re
import unicodedata
from case_context import resolve_context
from review import MENUS,NUMBER_WORDS,POLICY,exact_mentions,policy_check

ENDING=r'(?:이요|이에요|예요|요|주세요|부탁해요|부탁드려요|해주세요|해줘요|해줘|줘요|줘|할게요|하겠습니다)?[.!?]?'
PARTICLE=r'(?:만)?(?:으로|로|을|를)?'
NUMBER='|'.join(sorted(NUMBER_WORDS,key=len,reverse=True))


def pending_answer(text,context):
    if not context or exact_mentions(text):return None
    try:known=resolve_context({'context':'custom','context_data':context},{})
    except (ValueError,TypeError,KeyError):return None
    compact=re.sub(r'\s+','',unicodedata.normalize('NFC',text))
    field=known['awaiting'];value=None
    if field=='quantity':
        m=re.fullmatch(r'(?P<number>[0-9]+|'+NUMBER+r')(?P<unit>잔|개|컵)?'+PARTICLE+ENDING,compact)
        if m:
            token=m['number']
            # 한/두/세/네 are attributive forms; bare 네 can be assent.
            if token in ('한','두','세','네') and not m['unit']:return None
            value=int(token) if token.isdigit() else NUMBER_WORDS[token]
            if not POLICY['quantity_min']<=value<=POLICY['quantity_max']:return None
    elif field=='temperature':
        m=re.fullmatch(r'(?P<value>차갑게|차가운|아이스|따뜻하게|따뜻한|뜨거운|뜨겁게|핫)(?:것|거|걸)?'+PARTICLE+ENDING,compact)
        if m:value='ice' if m['value'] in ('차갑게','차가운','아이스') else 'hot'
    elif field=='whipped_cream':
        m=re.fullmatch(r'(?:휘핑(?:은|는|을)?)?(?P<value>빼기|빼|없이|많이|듬뿍|적게|조금|일반|보통|기본|그대로)'+PARTICLE+r'(?:올려|넣어)?'+ENDING,compact)
        if m:
            value={'빼기':'none','빼':'none','없이':'none','많이':'extra','듬뿍':'extra','적게':'light',
                '조금':'light','일반':'normal','보통':'normal','기본':'normal','그대로':'normal'}[m['value']]
    if value is None:return None
    return {'field':field,'value':value,'context':known,'source_text':text,
            'source':'whole_pending_reply_with_polite_suffix','model_result_used':False}


def validation_facts(text,context):
    original=policy_check(text,context)
    if original.get('scope')=='simple_single_add':return original
    answer=pending_answer(text,context)
    if answer is None:return original
    known=answer['context'];field=answer['field'];menu=MENUS[known['menu_id']]
    q=answer['value'] if field=='quantity' else known['quantity']
    temp=answer['value'] if field=='temperature' else known['temperature']
    if temp is None and len(menu['temperatures'])==1:temp=menu['temperatures'][0]
    cream=answer['value'] if field=='whipped_cream' else None
    missing=[]
    if q is None:missing.append('quantity')
    if temp is None:missing.append('temperature')
    if menu['ask_whip'] and cream is None:missing.append('whipped_cream')
    conflict=temp is not None and temp not in menu['temperatures']
    questions={'quantity':'몇 잔 드릴까요?','temperature':'따뜻하게 드릴까요, 차갑게 드릴까요?',
               'whipped_cream':'휘핑은 어떻게 해드릴까요?'}
    return {'scope':'simple_single_add','menu_id':menu['id'],'quantity':q,'temperature':temp,
        'quantity_status':'explicit' if field=='quantity' else 'from_context',
        'quantity_evidence':[{'from':text,'value':q,'unit':'pending_drink_count','accepted_unit':True}]
            if field=='quantity' else [],'quantity_values':[q] if q is not None else [],
        'needs_quantity_confirmation':False,'whipped_cream':cream,'missing_fields':missing,
        'temperature_conflict':conflict,'next_question':questions[missing[0]] if missing else '',
        'simple_required_fields_complete':not missing and not conflict,
        'pending_answer_evidence':answer,
        'note':'검증 전용 문맥 답변 분석. 직전 확정 사실과 현재 명시 답변만 사용. Qwen 입력·원본 응답 변경 없음.'}
