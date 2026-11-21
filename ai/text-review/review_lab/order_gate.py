"""Post-Qwen decisions for a bounded experiment. No cart writes or model calls.

The model's raw response is never rewritten. Only a missing catalog-fixed
ICE temperature/regular size can be completed in a separate validated item.
Spelling guesses, custom preparation and compound changes require review.
"""
from __future__ import annotations

import copy
import re
import time

from review import MENUS, POLICY, exact_mentions, policy_check

GATE_VERSION = 'bom-order-gate-0.1'
LABELS = {'ready': '확정 가능(필드 수준)', 'ask': '되묻기', 'menu_check': '메뉴 확인',
          'hold': '판정 보류', 'unavailable': '응답 확인 불가'}


def menu_label(menu_id, temp=None):
    prefix = {'ice': '차가운 ', 'hot': '따뜻한 '}.get(temp, '')
    return prefix + MENUS[menu_id]['name']


def validate_order(row, model_text, context=None, *, evidence_text=None, changes=None):
    """Use each branch's own text and the same independently selected context.

    Context expansion only restates known facts. Its underlying lexical text
    is used as evidence, not the model's interpretation or a reference answer.
    """
    started = time.perf_counter()
    source = model_text if evidence_text is None else evidence_text
    context = copy.deepcopy(context or {})
    facts = policy_check(source, context)
    ids = list(dict.fromkeys(m['menu_id'] for m in exact_mentions(source)))
    if not ids and facts.get('scope') == 'simple_single_add': ids = [facts['menu_id']]

    def finish(status, question='', reasons=(), *, validated=None, completions=None, candidates=None):
        return {'version': GATE_VERSION, 'status': status, 'label': LABELS[status],
                'can_accept_fields': status == 'ready', 'question': question,
                'reasons': list(reasons), 'validated_items': copy.deepcopy(validated or []),
                'catalog_completions': copy.deepcopy(completions or []),
                'candidate_menu_ids': list(candidates or []), 'evidence_text': source,
                'model_input_text': model_text, 'source_facts': copy.deepcopy(facts),
                'cart_mutated': False, 'order_committed': False,
                'customer_final_confirmation_required': True,
                'processing_ms': round((time.perf_counter()-started)*1000, 3),
                'note': '단일 추가 주문의 실험용 필드 판정. 실제 장바구니·가격·결제·최종 주문 확정은 수행하지 않습니다.'}

    if row.get('status') != 'ok' or not isinstance(row.get('parsed'), dict):
        return finish('unavailable', reasons=['정상적인 모델 JSON 응답을 확인하지 못해 확정하지 않음'])
    if row.get('input_text', model_text) != model_text:
        return finish('hold', reasons=['실제 요청 기록과 검증할 문장이 달라 확정하지 않음'])
    parsed = row['parsed']
    items = parsed.get('items')
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        return finish('hold', reasons=['items 형식이 올바르지 않음'])
    if any(item.get('menu_id') not in MENUS for item in items):
        return finish('menu_check', '메뉴 이름을 다시 확인해주세요.', ['모델이 등록되지 않은 메뉴 ID를 반환함'])
    if re.search(r'(?:[-−]\s*\d+|\d+\s*[.,]\s*\d+)\s*(?:잔|개|컵|대)', source):
        return finish('hold', reasons=['음수·분수 또는 수량 표기 형식을 확인해야 함'])
    if re.search(r'주지\s*마|제외|필요\s*없|싫|마셨어|먹었', source):
        return finish('hold', reasons=['부정·제외 또는 과거 발화는 단순 추가 주문으로 확정하지 않음'])

    # Do not treat an explicitly non-order utterance as an unknown drink.
    if re.search(r'처음부터|전체\s*취소|다\s*취소|초기화|주문\s*(?:확정|끝)|이대로|어떻게|추천|가격|얼마|도와', source):
        return finish('hold', reasons=['추가 주문 이외의 의도는 이 실험의 확정 판정 범위 밖'])
    if len(ids) > 1:
        return finish('hold', reasons=['여러 메뉴 또는 복합 정정 요청은 별도 검토 필요'], candidates=ids)
    if not ids:
        if re.search(r'라떼|라테', source):
            choices = [m['id'] for m in MENUS.values() if m['name'].endswith('라떼')]
            return finish('menu_check', '어떤 라떼를 드릴까요?', ['입력에서 메뉴 종류를 특정하지 못함'], candidates=choices)
        return finish('menu_check', '메뉴를 확인하지 못했어요. 화면에서 골라주세요.',
                      ['입력에서 등록 메뉴를 확인하지 못함', '모델이 제시한 다른 메뉴를 대신 확정하지 않음'])
    menu_id = ids[0]
    menu = MENUS[menu_id]
    if facts.get('scope') != 'simple_single_add':
        return finish('hold', reasons=['취소·수정·미확정 옵션 등은 단일 추가 주문 검증 범위 밖'], candidates=ids)
    if any(c.get('kind') == 'menu_typo_candidate' for c in changes or []):
        return finish('menu_check', menu['name'] + '를 말씀하신 건가요?',
                      ['실험적 오타 보정으로 선택한 메뉴는 사용자 확인 필요'], candidates=ids)
    if any(item.get('menu_id') != menu_id for item in items):
        return finish('menu_check', menu['name'] + '를 말씀하신 건가요?',
                      ['입력의 메뉴와 모델이 반환한 메뉴가 다름'], candidates=ids)

    # Required questions come from source evidence and catalog, not guessed values.
    if facts['temperature_conflict']:
        question = ('이 음료는 차갑게만 제공해요. 차갑게 드릴까요?' if menu['temperatures'] == ['ice']
                    else '따뜻한 것과 차가운 것 중 어느 쪽인가요?')
        return finish('ask', question, ['요청한 온도와 제공 조건 또는 발화의 온도 표현이 충돌함'], candidates=ids)
    if facts.get('needs_quantity_confirmation'):
        return finish('ask', facts['next_question'], ['수량 표현은 있으나 단위·범위 또는 값 확인 필요'], candidates=ids)
    if facts['missing_fields']:
        field = facts['missing_fields'][0]
        return finish('ask', facts['next_question'], ['입력에서 필수 정보가 빠짐: ' + field,
                      '모델이 임의로 채운 값으로 확정하지 않음'], candidates=ids)

    if len(items) != 1:
        return finish('menu_check', menu['name'] + '를 말씀하신 건가요?', ['대상 메뉴 항목이 정확히 하나가 아님'], candidates=ids)
    for field in ('intent', 'needs_clarification', 'clarification_question'):
        if field not in parsed:
            return finish('hold', reasons=['모델 응답 필수 항목 누락: ' + field])
    if type(parsed['needs_clarification']) is not bool or not isinstance(parsed['clarification_question'], str):
        return finish('hold', reasons=['모델의 확인 상태/질문 자료형이 올바르지 않음'])

    item = items[0]
    q = item.get('quantity')
    if type(q) is not int or q != facts['quantity']:
        return finish('ask', str(facts['quantity']) + '잔을 말씀하신 건가요?',
                      ['모델 수량이 원문의 명시 수량과 다르거나 누락됨'], candidates=ids)
    completions = []
    candidate = copy.deepcopy(item)
    temp = item.get('temperature')
    if temp is None and menu['temperatures'] == ['ice']:
        candidate['temperature'] = 'ice'
        completions.append({'field': 'temperature', 'from': None, 'to': 'ice', 'source': 'catalog_ice_only'})
    elif temp != facts['temperature']:
        if menu['temperatures'] == ['ice']:
            return finish('hold', reasons=['차갑게만 제공하는 메뉴에 모델이 불가능한 온도를 지정함. 사용자에게 온도 선택을 다시 묻지 않음'], candidates=ids)
        return finish('ask', ('차가운 음료를 말씀하신 건가요?' if facts['temperature'] == 'ice'
                             else '따뜻한 음료를 말씀하신 건가요?'),
                      ['모델 온도가 원문과 다르거나 누락됨'], candidates=ids)
    if item.get('size') is None:
        candidate['size'] = POLICY['size']
        completions.append({'field': 'size', 'from': None, 'to': POLICY['size'], 'source': 'catalog_single_size'})
    elif item['size'] != POLICY['size']:
        return finish('hold', reasons=['이 실험에서 제공하지 않는 사이즈'], candidates=ids)
    cream = item.get('whipped_cream')
    if menu['ask_whip'] and cream != facts['whipped_cream']:
        return finish('ask', '휘핑 선택을 다시 확인해주세요.', ['모델 휘핑이 명시한 선택과 다르거나 누락됨'], candidates=ids)
    if not menu['ask_whip'] and (cream not in (None, 'none') or facts['whipped_cream'] not in (None, 'none')):
        return finish('hold', reasons=['이 메뉴의 휘핑 추가 정책은 등록되어 있지 않음'], candidates=ids)
    if re.search(r'얼음\s*(?:많이|적게|[0-9]+|한|두|세)|연하게|진하게|설탕', source) or item.get('custom_note'):
        return finish('hold', reasons=['특이 제조 요청 또는 별도 메모는 수작업 확인 대상'], candidates=ids)
    if item.get('custom_note') is None:
        return finish('hold', reasons=['custom_note 응답 형식이 올바르지 않음'], candidates=ids)
    if parsed['intent'] != 'add' or parsed['needs_clarification'] or parsed['clarification_question'].strip():
        return finish('ask', menu_label(menu_id, facts['temperature']) + ' ' + str(q) + '잔이 맞나요?',
                      ['필수 정보는 있으나 모델의 의도·확인 상태·질문이 충돌함'], candidates=ids)
    return finish('ready', reasons=['단일 추가 주문의 메뉴·명시 수량·온도·필수 옵션이 검증 기준을 충족함'],
                  validated=[candidate], completions=completions, candidates=ids)
