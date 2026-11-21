"""Auditable menu text review; stdlib only, no STT or LLM hidden inside.

Hangul NFD edit distance is adapted from the existing laptop lab's
experiment_processing.py. This implementation uses a new six-menu policy.
It ranks lexicon candidates from ONE transcript, not an ASR N-best list.
"""
from __future__ import annotations

from pathlib import Path
import copy
import json
import re
import time
import unicodedata

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / 'menu_policy.json').read_text(encoding='utf-8'))
MENUS = {m['id']: m for m in POLICY['menus']}
RUN = re.compile(r'[가-힣]+')
ACTION = re.compile(r'아니|말고|빼|취소|삭제|제거|바꾸|바꿔|변경|수정|처음부터|초기화|리셋')
UNCONFIGURED = re.compile(r'카라멜|카멜|캬라멜|바나나|말차|녹차|초코|민트|흑당|헤이즐넛|디카페인|콜드브루|카모마일|유자|레몬|자몽|오트|두유|꿀|펄|샷|시럽|아이스티|에스프레소')
PREFIXES = ('아이스', '따뜻한', '따뜻하게', '뜨거운', '차가운', '차갑게', '핫')
SUFFIXES = ('주세요', '주세', '주쇼', '주셔', '주시오', '줘', '주라', '주문',
            '하나', '한잔', '한개', '두잔', '두개', '세잔', '세개', '네잔', '네개',
            '다섯', '여섯', '일곱', '여덟', '아홉', '이랑', '랑', '하고', '와', '과',
            '은', '는', '을', '를', '만', '도', '요', '따뜻', '뜨겁', '차갑', '아이스',
            '휘핑', '샷', '시럽', '추가', '빼', '취소', '말고', '아니', '얼음')
NUMBER_WORDS = {'한': 1, '하나': 1, '두': 2, '둘': 2, '세': 3, '셋': 3, '네': 4, '넷': 4,
                '다섯': 5, '여섯': 6, '일곱': 7, '여덟': 8, '아홉': 9}
NUMBER_PATTERN = r'[0-9]+|' + '|'.join(sorted(NUMBER_WORDS, key=len, reverse=True))
UNIT_PATTERN = r'잔|개|대|명|번|통|병|컵'
QUANTITY_WITH_UNIT = re.compile(r'(?<![0-9])(?P<number>' + NUMBER_PATTERN + r')\s*(?P<unit>' + UNIT_PATTERN + r')')


def is_option_count(text, start):
    return bool(re.search(r'(?:얼음|샷|펄|시럽|휘핑|설탕|꿀)\s*(?:은|는|을|를)?\s*$', text[:start]))


def distance(a, b):
    a, b = unicodedata.normalize('NFD', a), unicodedata.normalize('NFD', b)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(row[-1] + 1, prev[j] + 1, prev[j - 1] + (x != y)))
        prev = row
    edits = prev[-1]
    return edits, 1 - edits / max(len(a), len(b), 1)


def spaced_pattern(form):
    return r'\s*'.join(map(re.escape, form))


def start_boundary(text, start, *, full=False):
    if start == 0 or not text[start - 1].isalnum():
        return True
    return any(text[:start].endswith(p) for p in PREFIXES)


def end_boundary(text, end):
    if end == len(text) or not text[end].isalpha():
        return True
    return (any(text[end:].startswith(s) for s in SUFFIXES)
            or bool(QUANTITY_WITH_UNIT.match(text, end)))


def overlap(a, b):
    return a[0] < b[1] and a[1] > b[0]


def exact_mentions(text):
    found = []
    specs = []
    for m in MENUS.values():
        specs.extend((form, m['id'], None, m['name'], 'menu_spelling') for form in m['forms'])
    specs.extend((a['form'], a['menu_id'], a['temperature'], a['expanded'], 'approved_alias') for a in POLICY['aliases'])
    for form, menu_id, temp, replacement, kind in sorted(specs, key=lambda v: -len(v[0])):
        pattern = re.escape(form) if kind == 'approved_alias' else spaced_pattern(form)
        for match in re.finditer(pattern, text):
            if not start_boundary(text, match.start()) or not end_boundary(text, match.end()):
                continue
            if any(overlap(match.span(), (f['start'], f['end'])) for f in found):
                continue
            found.append({'start': match.start(), 'end': match.end(), 'from': match.group(),
                          'to': replacement, 'menu_id': menu_id, 'temperature': temp, 'kind': kind})
    return sorted(found, key=lambda f: f['start'])


def rank_candidates(fragment):
    ranked = []
    for m in MENUS.values():
        edits, score = min((distance(fragment, form) for form in m['forms']), key=lambda v: (v[0], -v[1]))
        ranked.append({'menu_id': m['id'], 'text': m['name'], 'edits': edits, 'similarity': round(score, 6)})
    return sorted(ranked, key=lambda v: (-v['similarity'], v['menu_id']))


def quantity_info(text, *, short_answer=False):
    """Keep source numbers even when their unit is uncertain. No text rewriting."""
    text = unicodedata.normalize('NFC', text).strip()
    evidence = []
    menu_ends = {m['end'] for m in exact_mentions(text)}
    for m in QUANTITY_WITH_UNIT.finditer(text):
        if m.start() and text[m.start()-1].isalpha() and m.start() not in menu_ends: continue
        if is_option_count(text, m.start()): continue
        if m.end() < len(text) and text[m.end()].isalpha() and not text[m.end():].startswith(SUFFIXES + ('이요', '이에요', '로', '중', '에')): continue
        token, unit = m.group('number'), m.group('unit')
        evidence.append({'from': m.group(), 'value': int(token) if token.isdigit() else NUMBER_WORDS[token],
                         'unit': unit, 'accepted_unit': unit in ('잔', '개', '컵'), 'start': m.start(), 'end': m.end()})
    for m in re.finditer(r'하나|둘|셋|넷', text):
        if m.start() and text[m.start()-1].isalpha() and m.start() not in menu_ends: continue
        if is_option_count(text, m.start()): continue
        if any(overlap(m.span(), (e['start'], e['end'])) for e in evidence): continue
        if (m.end() == len(text) or not text[m.end()].isalnum()
            or text[m.end():].startswith(('만', '요', '이요', '주세요', '주쇼', '줘', '추가'))):
            evidence.append({'from': m.group(), 'value': NUMBER_WORDS[m.group()], 'unit': None,
                             'accepted_unit': True, 'start': m.start(), 'end': m.end()})
    # 하나/둘 are standalone cardinal answers; 한/두 without units are not.
    if short_answer:
        m = re.fullmatch(r'\s*([0-9]+|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉)(?:만)?(?:이요|요)?[.!?]?\s*', text)
        if m:
            token = m.group(1)
            if not evidence:
                evidence.append({'from': m.group(), 'value': int(token) if token.isdigit() else NUMBER_WORDS[token],
                                 'unit': None, 'accepted_unit': True, 'start': m.start(), 'end': m.end()})
    values = list(dict.fromkeys(e['value'] for e in evidence))
    value = values[0] if len(values) == 1 else None
    if not values: status = 'missing'
    elif len(values) > 1: status = 'ambiguous'
    elif not POLICY['quantity_min'] <= value <= POLICY['quantity_max']: status = 'out_of_range'
    elif any(not e['accepted_unit'] for e in evidence): status = 'unit_uncertain'
    else: status = 'explicit'
    return {'value': value, 'status': status, 'evidence': evidence, 'values': values}


def read_quantity(text, *, short_answer=False):
    info = quantity_info(text, short_answer=short_answer)
    return info['value'] if info['status'] == 'explicit' else None


def temperature_flags(text):
    hot = bool(re.search(r'따뜻|뜨겁|뜨거|(?:^|\s)핫', text))
    ice = bool(re.search(r'아이스|차갑|차가운', text))
    return hot, ice


def temperature(text):
    hot, ice = temperature_flags(text)
    # An ice-count custom note in a HOT drink is not an ICE temperature.
    return ('hot' if hot else 'ice') if hot != ice else None


def whip(text, *, short_answer=False):
    if not short_answer and '휘핑' not in text:
        return None
    if re.search(r'빼|없이|안\s*넣|넣지\s*마', text): return 'none'
    if re.search(r'많이|듬뿍', text): return 'extra'
    if re.search(r'적게|조금', text): return 'light'
    if re.search(r'일반|보통|기본|그대로', text): return 'normal'
    return None


def expand_context(text, context):
    """Explicit prior facts only. Both Qwen branches receive the same context."""
    if not context or context.get('menu_id') not in MENUS or exact_mentions(text):
        return None
    field = context.get('awaiting')
    compact = re.sub(r'\s+', '', text)
    if field == 'quantity':
        valid = bool(re.fullmatch(r'(?:[1-9]|한|하나|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉)(?:잔|개)?(?:만)?(?:이요|요)?[.!?]?', compact))
        value = read_quantity(text, short_answer=True) if valid else None
    elif field == 'temperature':
        valid = bool(re.fullmatch(r'(?:차갑게|차가운걸로|아이스|따뜻하게|따뜻한걸로|뜨겁게|뜨거운걸로|핫)(?:요|해주세요|해줘)?[.!?]?', compact))
        value = temperature(text) if valid else None
    elif field == 'whipped_cream':
        valid = bool(re.fullmatch(r'(?:휘핑)?(?:빼줘|빼주세요|빼기|없이|많이|듬뿍|적게|조금|일반|보통|기본|그대로)(?:요|해주세요|해줘)?[.!?]?', compact))
        value = whip(text, short_answer=True) if valid else None
    else:
        value = None
    if value is None:
        return None
    facts = [MENUS[context['menu_id']]['name']]
    if context.get('quantity') is not None: facts.append(str(context['quantity']) + '잔')
    if context.get('temperature'): facts.append('따뜻하게' if context['temperature'] == 'hot' else '차갑게')
    label = {'quantity': '수량', 'temperature': '온도', 'whipped_cream': '휘핑'}[field]
    return {'text': '확인 중인 ' + ', '.join(facts) + '의 ' + label + ' 답변: ' + text,
            'field': field, 'value': value, 'reason': '사용자가 선택한 이전 질문 문맥을 명시적으로 보강. 새로운 수량·온도를 추정하지 않음.'}


def review_transcript(text, context=None):
    started = time.perf_counter()
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('비어 있지 않은 2,000자 이내 문장을 입력해주세요.')
    raw = text
    text = unicodedata.normalize('NFC', text)
    mentions = exact_mentions(text)
    protected_action = bool(ACTION.search(text))
    has_unconfigured = bool(UNCONFIGURED.search(text))
    edits = []
    for f in mentions:
        if f['from'] != f['to']:
            edits.append({**f, 'reason': '승인된 줄임말 풀어쓰기' if f['kind'] == 'approved_alias' else '메뉴 표기·띄어쓰기 통일'})
    proposals = []
    cfg = POLICY['review']
    for chunk in RUN.finditer(text):
        for start in range(chunk.start(), chunk.end()):
            if not start_boundary(text, start): continue
            for length in range(cfg['minimum_syllables'], 8):
                end = start + length
                if end > chunk.end() or not end_boundary(text, end): continue
                if any(overlap((start, end), (f['start'], f['end'])) for f in mentions): continue
                fragment = text[start:end]
                ranked = rank_candidates(fragment)
                best = ranked[0]
                if best['similarity'] < cfg['candidate_floor']: continue
                margin = best['similarity'] - ranked[1]['similarity']
                auto = (best['similarity'] >= cfg['minimum_similarity'] and margin >= cfg['minimum_margin']
                        and best['edits'] <= cfg['maximum_jamo_edits'] and not protected_action and not has_unconfigured)
                proposals.append({'start': start, 'end': end, 'from': fragment, 'to': best['text'],
                                  'menu_id': best['menu_id'], 'similarity': best['similarity'],
                                  'margin': round(margin, 6), 'automatic': auto, 'ranked': ranked[:3]})
    proposals.sort(key=lambda p: (-p['similarity'], -(p['end']-p['start']), p['start']))
    selected = []
    for p in proposals:
        if not any(overlap((p['start'], p['end']), (q['start'], q['end'])) for q in selected):
            selected.append(p)
            if p['automatic']:
                edits.append({**p, 'kind': 'menu_typo_candidate', 'reason': '자모 편집 1회 이내·유사도/후보 차이 기준 통과. 실험용 보정이며 정답 보장은 아님.'})
    output = text
    for e in sorted(edits, key=lambda e: e['start'], reverse=True):
        tail = output[e['end']:]
        replacement = e['to']
        if tail and tail[0].isalpha() and not tail.startswith(('은', '는', '을', '를', '이랑', '랑', '와', '과', '만', '도', '요')):
            replacement += ' '
        output = output[:e['start']] + replacement + output[e['end']:]
    lexical_text = output
    context_change = expand_context(output, context)
    if context_change:
        output = context_change['text']
    unknown_alias = bool(re.search(r'(?<![가-힣])(?:아라|아봐라|아아아)(?=\s|하나|한잔|주세요|$)', text))
    generic_menu = not mentions and bool(re.search(r'라떼|라테|스무디|커피', text)) and not any(p['automatic'] for p in selected)
    notes = []
    if protected_action: notes.append('정정·취소 표현은 보존. 이 문장의 메뉴 오타 자동 보정은 중지.')
    if has_unconfigured: notes.append('사전에 없는 메뉴/미확정 추가 옵션 표현 포함. 판매 가능·가격을 추정하지 않음.')
    if unknown_alias: notes.append('미등록 짧은 표현. 임의 별칭 해석 금지.')
    if generic_menu: notes.append('메뉴 종류를 특정할 수 없어 종류 확인이 필요함.')
    return {'version': POLICY['version'], 'original_text': raw, 'unicode_normalized': raw != text,
            'lexical_text': lexical_text, 'reviewed_text': output,
            'context': copy.deepcopy(context or {}), 'changes': sorted(edits, key=lambda e: e['start']),
            'candidates': sorted(selected, key=lambda p: p['start']), 'context_expansion': context_change,
            'needs_review': unknown_alias or generic_menu or has_unconfigured or any(not p['automatic'] for p in selected),
            'protected_action': protected_action, 'notes': notes,
            'similarity_note': '자모 편집 유사도. STT 모델의 신뢰도나 확률이 아니며 ASR N-best 재순위화도 아님.',
            'processing_ms': round((time.perf_counter() - started) * 1000, 3)}


def policy_check(text, context=None):
    """Conservative diagnostic for ONE simple item. Never updates a cart."""
    context = context or {}
    mentions = exact_mentions(unicodedata.normalize('NFC', text))
    ids = list(dict.fromkeys(f['menu_id'] for f in mentions))
    context_answer = expand_context(text, context)
    short_unit_reply = (context.get('awaiting') == 'quantity' and context.get('menu_id') in MENUS and
        bool(re.fullmatch(r'\s*(?:' + NUMBER_PATTERN + r')\s*(?:' + UNIT_PATTERN + r')(?:만)?(?:이요|요|주세요)?[.!?]?\s*', text)))
    uses_context = bool(context_answer or short_unit_reply)
    if not ids and uses_context: ids = [context['menu_id']]
    action_text = re.sub(r'휘핑\s*(?:은|을|는)?\s*(?:빼(?:주세요|고|줘|기)?|없이|안\s*넣(?:고|어)?|넣지\s*마)', '', text)
    if (len(ids) != 1 or UNCONFIGURED.search(text) or re.search(r'가격|얼마|추천|설명|어떻게', text)
        or ACTION.search(action_text) and not (context_answer and context.get('awaiting') == 'whipped_cream')):
        return {'scope': 'not_a_simple_single_add', 'note': '복수 메뉴·수정/취소·메뉴 불명확 문장은 이 간이 진단의 자동 판정 범위 밖입니다.'}
    menu = MENUS[ids[0]]
    quantity_detail = quantity_info(text, short_answer=bool(context.get('awaiting') == 'quantity'))
    quantity = quantity_detail['value']
    if context_answer:
        quantity = context.get('quantity')
        if context_answer['field'] == 'quantity':
            quantity = context_answer['value']
        elif quantity is not None:
            quantity_detail = {'value': quantity, 'status': 'from_context', 'evidence': [], 'values': [quantity]}
    quantity_issue = quantity_detail['status'] in ('unit_uncertain', 'ambiguous', 'out_of_range')
    temp_values = set(f['temperature'] for f in mentions if f['temperature'])
    has_hot, has_ice = temperature_flags(text)
    if has_hot: temp_values.add('hot')
    if has_ice: temp_values.add('ice')
    if uses_context and context.get('temperature'): temp_values.add(context['temperature'])
    if context_answer and context_answer['field'] == 'temperature': temp_values.add(context_answer['value'])
    temp = next(iter(temp_values)) if len(temp_values) == 1 else None
    conflict = len(temp_values) > 1 or temp is not None and temp not in menu['temperatures']
    if temp is None and len(menu['temperatures']) == 1 and not temp_values: temp = menu['temperatures'][0]
    cream = whip(text)
    if context_answer and context_answer['field'] == 'whipped_cream': cream = context_answer['value']
    missing = []
    if quantity_detail['status'] == 'missing': missing.append('quantity')
    if temp is None: missing.append('temperature')
    if menu['ask_whip'] and cream is None: missing.append('whipped_cream')
    question = {'quantity': '몇 잔 드릴까요?', 'temperature': '따뜻하게 드릴까요, 차갑게 드릴까요?',
                'whipped_cream': '휘핑은 어떻게 해드릴까요?'}[missing[0]] if missing else ''
    if quantity_detail['status'] == 'unit_uncertain':
        label = {1: '한', 2: '두', 3: '세', 4: '네', 5: '다섯', 6: '여섯', 7: '일곱', 8: '여덟', 9: '아홉'}[quantity]
        question = label + ' 잔을 말씀하신 건가요?'
    elif quantity_detail['status'] == 'ambiguous': question = '수량이 여러 개로 들렸어요. 몇 잔인지 확인해주세요.'
    elif quantity_detail['status'] == 'out_of_range': question = '이 실험의 수량 범위는 1~9잔이에요. 수량을 확인해주세요.'
    if conflict: question = '이 메뉴의 제공 온도와 요청이 맞지 않아요. 온도를 확인해주세요.'
    return {'scope': 'simple_single_add', 'menu_id': menu['id'], 'quantity': quantity, 'temperature': temp,
            'quantity_status': quantity_detail['status'], 'quantity_evidence': quantity_detail['evidence'],
            'quantity_values': quantity_detail['values'], 'needs_quantity_confirmation': quantity_issue,
            'whipped_cream': cream, 'missing_fields': missing, 'temperature_conflict': conflict,
            'next_question': question, 'simple_required_fields_complete': not missing and not conflict and not quantity_issue,
            'note': '별도 규칙 참고값입니다. Qwen의 답변을 이 값으로 덮어쓰거나 장바구니에 반영하지 않습니다.'}
