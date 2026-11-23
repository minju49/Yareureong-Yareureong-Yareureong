"""Paired, sequential real calls. Never repair the model's raw answer."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit

from review import POLICY

PROFILES = {
    'home': {'name': '집 Docker Qwen 0.8B', 'base_url': 'http://127.0.0.1:18080/v1', 'model': 'Qwen/Qwen3.5-0.8B'},
    'school': {'name': '학교 Qwen 9B — 학교에서 별도 확인 필요', 'base_url': os.environ.get('BOM_SCHOOL_QWEN_BASE_URL', '').strip(), 'model': 'qwen3.5:9b-q4_K_M', 'api_style': 'ollama'},
}
TRANSPORT_VERSION = 'bom-qwen-transport-1.1'
CONTRACT_VERSION = 'qwen-order-fields-0.3-short'
ORDER_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'intent': {'type': 'string', 'enum': ['add', 'update', 'remove', 'reset', 'confirm', 'clarify', 'help']},
        'items': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'properties': {
                'menu_id': {'type': 'string', 'enum': [m['id'] for m in POLICY['menus']]},
                'quantity': {'type': ['integer', 'null'], 'minimum': 1},
                'temperature': {'type': ['string', 'null'], 'enum': ['hot', 'ice', None]},
                'size': {'type': 'string', 'enum': ['regular']},
                'whipped_cream': {'type': ['string', 'null'], 'enum': ['normal', 'extra', 'light', 'none', None]},
                'custom_note': {'type': 'string'}
            }, 'required': ['menu_id', 'quantity', 'temperature', 'size', 'whipped_cream', 'custom_note']
        }},
        'needs_clarification': {'type': 'boolean'},
        'clarification_question': {'type': 'string'}
    }, 'required': ['intent', 'items', 'needs_clarification', 'clarification_question']
}
# Development-selected shorter instruction. Korean user text/output are retained.
# Vocabulary rules are general; no per-test reference answer enters a request.
PROMPT = '''Extract the Korean customer's order into the required JSON. `menu` is a catalog, NOT the order. Include only drinks requested in `text`.
Read quantities literally: 한/하나=1, 두/둘=2, 세/셋=3. Unstated quantity is null, never 1.
Read temperature literally: 아이스/차가운/차갑게 means ice; 따뜻한/따뜻하게/뜨거운 means hot. Unstated temperature is null, except an ice-only menu uses ice.
Aliases: 아아=americano ice; 뜨아/따아=americano hot; 아바라=vanilla_latte ice.
size is regular. whipped_cream is null unless explicitly selected: 많이=extra, 적게=light, 일반=normal, 빼기=none.
For a new order, if quantity or required temperature or required whip is missing, intent=clarify, needs_clarification=true; ask ONE short Korean question, quantity before temperature before whip.
If the number uses an uncertain drink unit such as 대/명/병, retain the number and ask to confirm cups. This is a unit question, not missing quantity.
A complete new order has intent=add, needs_clarification=false, clarification_question="".
Use context only for the pending question, keeping explicitly known previous facts. Preserve correction/cancel intent. Unclear menu requires clarification.
custom_note contains only a special preparation request, otherwise "". Never copy the whole input there. Ice-piece counts are preparation notes, not drink quantity or temperature.'''
OPENER = build_opener(ProxyHandler({}))


def api_base(profile):
    base = profile['base_url'].rstrip('/')
    if profile.get('api_style') == 'ollama':
        parsed = urlsplit(base)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('학교 서버의 http/https 기본 주소를 확인해주세요.')
        path = parsed.path.rstrip('/')
        for suffix in ('/v1/models', '/api/tags', '/api/chat', '/v1', '/api'):
            if path.endswith(suffix):
                path = path[:-len(suffix)]
                break
        base = urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))
    return base


def http(profile, method, path, body=None, timeout=90):
    encoded = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    req = Request(api_base(profile) + path, data=encoded, method=method,
                  headers={'Content-Type': 'application/json'})
    with OPENER.open(req, timeout=timeout) as response:
        return json.load(response)


def check_model(profile):
    if not profile.get('base_url'):
        raise ValueError('학교 서버 주소를 BOM_SCHOOL_QWEN_BASE_URL 환경 변수에 지정해주세요.')
    native = profile.get('api_style') == 'ollama'
    raw = http(profile, 'GET', '/api/tags' if native else '/models', timeout=8)
    names = [item.get('name') or item.get('model') for item in raw.get('models', [])] if native else [item.get('id') for item in raw.get('data', [])]
    if profile['model'] not in names:
        raise ValueError('요청한 모델이 목록에 없습니다: ' + profile['model'] + ' / ' + str(names))
    return raw


def payload(profile, text, context):
    # Same prompt, menu and context on both sides. Reference answers are never sent.
    menu = [{'menu_id': m['id'], **{k: m[k] for k in ('name', 'temperatures', 'ask_whip')}} for m in POLICY['menus']]
    data = {'text': text, 'context': copy.deepcopy(context or {}), 'menu': menu}
    body = {'model': profile['model'], 'messages': [{'role': 'system', 'content': PROMPT},
            {'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}],
            'temperature': 0, 'max_tokens': 512,
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'bom_order_fields', 'strict': True, 'schema': copy.deepcopy(ORDER_SCHEMA)}}}
    if profile.get('api_style') == 'ollama':
        return {'model': profile['model'], 'messages': body['messages'], 'format': copy.deepcopy(ORDER_SCHEMA),
                'stream': False, 'think': False, 'options': {'temperature': 0, 'num_predict': 1024}}
    if profile['model'] == 'Qwen/Qwen3.5-0.8B':
        body['chat_template_kwargs'] = {'enable_thinking': False}
    return body


def request_order(profile, text, context):
    started = time.perf_counter()
    body = payload(profile, text, context)
    native = profile.get('api_style') == 'ollama'
    endpoint = '/api/chat' if native else '/chat/completions'
    row = {'model_called': True, 'model': profile['model'], 'endpoint': api_base(profile) + endpoint,
           'transport_version': TRANSPORT_VERSION,
           'input_text': text, 'request': body, 'api_ok': False, 'json_ok': False, 'status': 'error'}
    try:
        raw = http(profile, 'POST', endpoint, body)
        row['raw_response'] = raw
        if native:
            row['raw_content'] = raw.get('message', {}).get('content', '')
            row['finish_reason'] = raw.get('done_reason')
            row['returned_model'] = raw.get('model')
            row['thinking_returned'] = bool(raw.get('message', {}).get('thinking'))
            row['server_load_ms'] = raw.get('load_duration', 0) / 1e6
            row['server_total_ms'] = raw.get('total_duration', 0) / 1e6
            row['api_ok'] = bool(row['raw_content']) and raw.get('done') is True and row['finish_reason'] != 'length' and row['returned_model'] == profile['model']
            if row['returned_model'] != profile['model']:
                row['error'] = '요청한 모델과 실제 응답 모델이 다릅니다.'
        else:
            choice = raw['choices'][0]
            row['raw_content'] = choice['message'].get('content', '')
            row['finish_reason'] = choice.get('finish_reason')
            row['api_ok'] = bool(row['raw_content']) and row['finish_reason'] != 'length'
        try:
            parsed = json.loads(row['raw_content'])
            if not isinstance(parsed, dict): raise ValueError('응답이 JSON 객체가 아닙니다.')
            row['parsed'] = parsed
            row['json_ok'] = True
        except (ValueError, TypeError) as exc:
            row['parse_error'] = str(exc)
        row['status'] = 'ok' if row['api_ok'] and row['json_ok'] else 'invalid_response'
    except (OSError, ValueError, KeyError, TypeError, IndexError, URLError) as exc:
        row['error'] = str(exc)
        if isinstance(exc, HTTPError): row['error_body'] = exc.read(4000).decode('utf-8', errors='replace')
    row['request_ms'] = round((time.perf_counter()-started)*1000, 3)
    return row


def compare(profile, review):
    check_model(profile)
    first = request_order(profile, review['original_text'], review['context'])
    if review['reviewed_text'] == review['original_text']:
        second = copy.deepcopy(first)
        second['model_called'] = False
        second['request_ms'] = None
        second['reused_identical_request'] = True
        second['reuse_note'] = '원문과 보정문이 같아 동일 요청의 실제 응답을 공유. 독립 속도 비교 표본이 아님.'
    elif first['status'] == 'error':
        second = {'status': 'skipped', 'model_called': False, 'reason': '첫 요청 연결 실패로 추가 호출을 생략했습니다.'}
    else:
        second = request_order(profile, review['reviewed_text'], review['context'])
    return {'profile': copy.deepcopy(profile), 'contract_version': CONTRACT_VERSION,
            'prompt_sha256': hashlib.sha256(PROMPT.encode('utf-8')).hexdigest(),
            'schema_sha256': hashlib.sha256(json.dumps(ORDER_SCHEMA, sort_keys=True).encode('utf-8')).hexdigest(),
            'A_original': first, 'B_reviewed': second,
            'note': '항상 A 다음 B로 순차 요청. 프롬프트 캐시·시스템 부하의 순서 효과가 있어 이 값만으로 속도 우열을 판정하지 않음.'}


def diagnose(row, facts):
    """Flag inconsistencies against independent simple rules; no output rewriting."""
    if row.get('status') != 'ok': return {'status': 'unavailable', 'issues': [row.get('status', 'error')]}
    if facts.get('scope') != 'simple_single_add':
        return {'status': 'not_scored', 'issues': ['복합/불명확 요청은 자동 판정 범위 밖. 원본 응답을 직접 확인해주세요.']}
    result = row['parsed']
    issues = []
    for field in ('intent', 'items', 'needs_clarification', 'clarification_question'):
        if field not in result: issues.append('필수 응답 필드 누락: ' + field)
    if 'needs_clarification' in result and type(result['needs_clarification']) is not bool:
        issues.append('needs_clarification이 참/거짓 값이 아님')
    items = result.get('items')
    if not isinstance(items, list): return {'status': 'disagreement', 'issues': ['items가 목록이 아님']}
    matches = [v for v in items if isinstance(v, dict) and v.get('menu_id') == facts['menu_id']]
    if any(not isinstance(v, dict) or v.get('menu_id') != facts['menu_id'] for v in items): issues.append('말하지 않은 메뉴 포함')
    if len(matches) != 1: issues.append('대상 메뉴가 정확히 1개가 아님')
    missing = facts['missing_fields']
    quantity_issue = facts.get('needs_quantity_confirmation', False)
    needs_question = bool(missing or facts['temperature_conflict'] or quantity_issue)
    if needs_question:
        if result.get('needs_clarification') is not True: issues.append('필수 확인 질문 누락')
        if not str(result.get('clarification_question', '')).strip(): issues.append('질문 문장 없음')
    elif result.get('needs_clarification') is True:
        issues.append('단순 필수 정보가 있는데 다시 질문함')
    if result.get('needs_clarification') is False and str(result.get('clarification_question', '')).strip():
        issues.append('확인 불필요라고 하면서 질문 문장을 반환함')
    if quantity_issue and result.get('needs_clarification') is not True:
        issues.append('수량 단위/표현 확인을 생략함')
    expected_intent = 'clarify' if needs_question else 'add'
    if result.get('intent') != expected_intent: issues.append('단일 주문 규칙과 intent 불일치')
    if matches:
        item = matches[0]
        for field in ('quantity', 'temperature', 'whipped_cream'):
            expected = facts[field]
            actual = item.get(field)
            if field == 'quantity' and quantity_issue:
                if actual is not None and expected is not None and (type(actual) is not int or actual != expected):
                    issues.append('quantity: 원문에 나온 수량 후보와 불일치')
                continue
            if field in missing and actual is not None: issues.append(field + ': 누락 값을 임의로 채움')
            elif expected is not None and (type(actual) is not type(expected) or actual != expected): issues.append(field + ': 명시/고정된 값과 불일치')
        if item.get('size') != 'regular': issues.append('기본 사이즈 불일치')
    if result.get('intent') not in ('add', 'update', 'remove', 'reset', 'confirm', 'clarify', 'help'): issues.append('실험 계약에 없는 intent')
    return {'status': 'disagreement' if issues else 'basic_fields_agree', 'issues': issues,
            'note': '제한된 단일 추가 주문의 규칙 대조이며, 전체 의미·질문 문구·특이사항·실제 주문 성공의 판정은 아님.'}
