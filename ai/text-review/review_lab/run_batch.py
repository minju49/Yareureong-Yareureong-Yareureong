"""Frozen development-text A/B experiment, separate references, and log audit.

No microphone, ASR, TTS, DB, cart mutation, or implicit school connection.
Raw model answers are retained. Reference labels are never part of requests.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import json
import os
import platform
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from review import POLICY, review_transcript
from qwen_client import PROFILES, CONTRACT_VERSION, TRANSPORT_VERSION, ORDER_SCHEMA, PROMPT, check_model, request_order
from order_gate import GATE_VERSION, validate_order
from run_review import CONTEXTS
from case_context import resolve_context

VERSION = 'bom-review-batch-1.3'
ROOT = Path(__file__).resolve().parent.parent
DATASET = Path(__file__).with_name('batch_cases.json')
KST = timezone(timedelta(hours=9))
BRANCHES = ('A_original', 'B_reviewed')
ITEM_FIELDS = ('menu_id', 'quantity', 'temperature', 'size', 'whipped_cream', 'custom_note')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(KST).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(strict_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(strict_equal(a, b) for a, b in zip(left, right))
    return left == right


def load_cases(path=DATASET):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    cases = data['cases']
    if data.get('case_count') != len(cases) or not cases:
        raise ValueError('문장 수와 case_count를 확인해주세요.')
    ids = [c['id'] for c in cases]
    if len(set(ids)) != len(ids) or any(not ident.isalnum() for ident in ids):
        raise ValueError('문장 ID는 중복 없는 영문·숫자여야 합니다.')
    for case in cases:
        if not isinstance(case['text'], str) or not case['text'].strip():
            raise ValueError('문장과 문맥을 확인해주세요: ' + case['id'])
        resolve_context(case,CONTEXTS)
        if type(case['must_block']) is not bool:
            raise ValueError('must_block은 참/거짓이어야 합니다.')
        expected = case['expected_model']
        if expected is not None:
            if expected['intent'] not in ('add', 'clarify') or type(expected['needs_clarification']) is not bool:
                raise ValueError('개발용 정답 형식을 확인해주세요.')
            if expected['question_required'] != expected['needs_clarification']:
                raise ValueError('정답의 질문 필요 여부가 일치하지 않습니다.')
            if not isinstance(expected['items'], list) or any(set(item) != set(ITEM_FIELDS) for item in expected['items']):
                raise ValueError('개발용 정답 items를 확인해주세요.')
    return data


def score_model(row, expected):
    """Independent declared references; never call policy_check as an oracle."""
    if expected is None:
        return {'scored': False, 'correct': None, 'fields': {}, 'issues': ['정답 미확정/단일 주문 범위 밖: 모델 채점 제외']}
    fields = {name: False for name in ('intent', 'needs_clarification', 'question_presence', *ITEM_FIELDS)}
    if row.get('status') != 'ok' or not isinstance(row.get('parsed'), dict):
        return {'scored': True, 'correct': False, 'available': False, 'fields': fields,
                'issues': ['API 또는 JSON 응답 실패. 정답으로 집계하지 않음']}
    actual = row['parsed']
    fields['intent'] = strict_equal(actual.get('intent'), expected['intent'])
    fields['needs_clarification'] = strict_equal(actual.get('needs_clarification'), expected['needs_clarification'])
    question = actual.get('clarification_question')
    fields['question_presence'] = isinstance(question, str) and bool(question.strip()) == expected['question_required']
    items = actual.get('items')
    item_count_ok = isinstance(items, list) and len(items) == len(expected['items'])
    for field in ITEM_FIELDS:
        fields[field] = item_count_ok and all(isinstance(a, dict) and field in a and strict_equal(a[field], e[field])
                                             for a, e in zip(items, expected['items']))
    issues = [name for name, ok in fields.items() if not ok]
    if not item_count_ok:
        issues.append('items 개수')
    return {'scored': True, 'correct': not issues, 'available': True, 'fields': fields, 'issues': issues,
            'note': '개발용 정답 초안의 슬롯·의도·질문 유무 비교. 질문의 의미/친절함, 음성 정확도, 전체 주문 성공은 평가하지 않음.'}


def score_gate(row, case):
    gate = row['order_decision']
    if row.get('status') != 'ok' or gate['status'] == 'unavailable':
        return 'unavailable'
    if gate['can_accept_fields']:
        if case['must_block']:
            return 'unsafe_accept'
        expected = case['expected_model']
        if expected is None or not strict_equal(gate['validated_items'], expected['items']):
            return 'unsafe_accept'
        return 'accepted_correct'
    if case['must_block']:
        return 'blocked_required'
    if row['reference_score'].get('correct') is True:
        return 'unnecessary_block'
    return 'blocked_inconsistent'


def audit_logs(folder, paths):
    """Deduplicate requests, not utterance strings; no speech gold is inferred."""
    unique, invalid, conflicts, sources = {}, [], [], []
    source_rows = 0
    for path in sorted({Path(p).resolve() for p in paths}):
        raw = path.read_bytes()
        sources.append({'path': str(path), 'sha256': digest(raw)})
        with path.open(encoding='utf-8-sig', newline='') as handle:
            for number, row in enumerate(csv.DictReader(handle), 2):
                source_rows += 1
                try:
                    diagnostic = json.loads(row['diagnostics_json'])
                    state = json.loads(row['state_json'])
                    key = (row['created_at'], state['session_id'], row['input_text'])
                    if not all(isinstance(value, str) and value for value in key):
                        raise ValueError('요청 식별 정보 누락')
                    entry = {'created_at': key[0], 'session_id': key[1], 'text': key[2],
                             'input_source': diagnostic.get('input_source'),
                             'stt_text': diagnostic.get('stt', {}).get('text'), 'references': []}
                    if key not in unique:
                        unique[key] = entry
                    elif any(unique[key][field] != entry[field] for field in ('input_source', 'stt_text')):
                        conflicts.append({'path': str(path), 'line': number, 'key': key})
                    unique[key]['references'].append({'path': str(path), 'line': number})
                except (ValueError, KeyError, TypeError) as exc:
                    invalid.append({'path': str(path), 'line': number, 'error': str(exc)})
    entries = sorted(unique.values(), key=lambda value: value['created_at'])
    rows = []
    for entry in entries:
        reviewed = review_transcript(entry['text'])
        rows.append({**entry, 'review': reviewed, 'context_reconstructed': False,
                     'gold_transcript_available': False, 'model_called_here': False})
    microphone = [row for row in rows if row['input_source'] == 'microphone']
    summary = {'scope': '과거 CSV 중복 제거 및 문장 처리 감사. 현재 새 녹음/모델 호출 없음.',
               'source_files': sources, 'source_rows': source_rows, 'unique_requests': len(rows),
               'duplicates_removed': source_rows - len(rows) - len(invalid), 'invalid_rows': invalid,
               'conflicting_duplicates': conflicts, 'source_counts': dict(Counter(row['input_source'] for row in rows)),
               'microphone_requests': len(microphone), 'distinct_microphone_texts': len({row['text'] for row in microphone}),
               'changed_microphone_requests': sum(row['review']['reviewed_text'] != row['text'] for row in microphone),
               'stt_text_input_mismatches': sum(row['text'] != row['stt_text'] for row in microphone),
               'cer_calculated': False, 'qwen_calls_here': 0,
               'limitations': ['원본 녹음과 사람이 검수한 정답 전사가 이 CSV에 없어 CER/의도 복원 정확도를 계산하지 않음.',
                               '과거 출력은 개발 중 이미 본 자료. 독립 최종 시험셋이 아님.',
                               '대화 문맥을 임의 재구성하지 않음. 짧은 답변/복합 요청의 정답률로 집계하지 않음.',
                               '변경 건수는 개선 건수가 아님. 과거 학교 Qwen 결과와 현재 집 Qwen 결과를 모델 비교로 섞지 않음.']}
    write_json(folder / '과거STT기록_감사.json', {'summary': summary, 'records': rows})
    with (folder / '과거STT기록_검토.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['created_at', 'input_source', 'original_text', 'reviewed_text',
                                                  'change_types', 'needs_review', 'processing_ms', 'source_references'])
        writer.writeheader()
        for row in rows:
            reviewed = row['review']
            writer.writerow({'created_at': row['created_at'], 'input_source': row['input_source'],
                             'original_text': row['text'], 'reviewed_text': reviewed['reviewed_text'],
                             'change_types': '|'.join(sorted({e['kind'] for e in reviewed['changes']})),
                             'needs_review': reviewed['needs_review'], 'processing_ms': reviewed['processing_ms'],
                             'source_references': json.dumps(row['references'], ensure_ascii=False)})
    return summary


def schedule(case, review, changed_index):
    if review['reviewed_text'] == review['original_text']:
        return ['A_original']
    return list(BRANCHES if changed_index % 2 == 0 else reversed(BRANCHES))


def execute_case(case, profile, order):
    context = resolve_context(case,CONTEXTS)
    reviewed = review_transcript(case['text'], context)
    texts = {'A_original': reviewed['original_text'], 'B_reviewed': reviewed['reviewed_text']}
    responses = {}
    for branch in order:
        responses[branch] = request_order(profile, texts[branch], context)
        if responses[branch]['status'] == 'error':
            break
    if texts['A_original'] == texts['B_reviewed'] and 'A_original' in responses:
        responses['B_reviewed'] = copy.deepcopy(responses['A_original'])
        responses['B_reviewed'].update(model_called=False, request_ms=None, reused_identical_request=True,
                                      reuse_note='원문과 재점검문이 같아 실제 응답 1개를 공유. 두 번째 호출/0ms 속도 표본이 아님.')
    for branch in BRANCHES:
        row = responses.setdefault(branch, {'status': 'skipped', 'model_called': False, 'request_ms': None,
                                           'reason': '연결 실패로 추가 요청 생략'})
        row['reference_score'] = score_model(row, case['expected_model'])
        row['order_decision'] = validate_order(row, texts[branch], context,
            evidence_text=reviewed['original_text'] if branch == 'A_original' else reviewed['lexical_text'],
            changes=[] if branch == 'A_original' else reviewed['changes'])
        row['gate_score'] = score_gate(row, case)
    preserved = all(token in reviewed['lexical_text'] for token in case['preserve_tokens'])
    return {'case': copy.deepcopy(case), 'created_at': now(), 'review': reviewed, 'context': context,
            'request_order': order, 'responses': responses, 'protected_tokens_preserved': preserved,
            'stt_called_here': False, 'cart_mutated': False}


def outcome(record):
    a, b = (record['responses'][branch]['reference_score'] for branch in BRANCHES)
    if not a['scored'] or not b['scored']:
        return 'not_scored'
    return ('both_correct' if a['correct'] else 'improved') if b['correct'] else ('worsened' if a['correct'] else 'both_wrong')


def timing(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {'n': 0, 'mean_ms': None, 'median_ms': None, 'p95_ms': None, 'max_ms': None}
    index = max(0, (95 * len(values) + 99) // 100 - 1)
    return {'n': len(values), 'mean_ms': round(statistics.mean(values), 3),
            'median_ms': round(statistics.median(values), 3), 'p95_ms': values[index], 'max_ms': values[-1]}


def summarize(records, planned):
    scored = [r for r in records if r['case']['expected_model'] is not None]
    common_valid = [r for r in scored if all(r['responses'][branch].get('status') == 'ok' for branch in BRANCHES)]
    groups = defaultdict(list)
    for record in records:
        groups[record['case']['category']].append(record)
    branches = {}
    for branch in BRANCHES:
        rows = [r['responses'][branch] for r in records]
        branches[branch] = {
            'reference_denominator': len(scored),
            'reference_correct': sum(r['responses'][branch]['reference_score']['correct'] is True for r in scored),
            'api_json_ok': sum(r.get('status') == 'ok' for r in rows),
            'actual_model_calls': sum(r.get('model_called', False) for r in rows),
            'shared_responses': sum(r.get('reused_identical_request', False) for r in rows),
            'gate': dict(Counter(r['gate_score'] for r in rows)),
            'gate_decision_counts': dict(Counter(r['order_decision']['status'] for r in rows)),
            'catalog_completions': sum(bool(r['order_decision']['catalog_completions']) for r in rows),
            'field_correct': {field: sum(r['responses'][branch]['reference_score']['fields'].get(field, False) for r in scored)
                              for field in ('intent', 'needs_clarification', 'question_presence', *ITEM_FIELDS)},
            'request_timing': timing([r.get('request_ms') for r in rows if r.get('model_called')]),
            'gate_timing': timing([r['order_decision']['processing_ms'] for r in rows]),
        }
        core_correct, core_total, core_all, core_cases = 0, 0, 0, 0
        for record in scored:
            expected = record['case']['expected_model']
            if len(expected['items']) != 1:
                continue
            item = expected['items'][0]
            slots = ['menu_id', 'quantity', 'temperature']
            if any(m['id'] == item['menu_id'] and m['ask_whip'] for m in POLICY['menus']):
                slots.append('whipped_cream')
            result = record['responses'][branch]
            predictions = result.get('parsed', {}).get('items', [])
            shape_ok = result.get('status') == 'ok' and isinstance(predictions, list) and len(predictions) == 1 and isinstance(predictions[0], dict)
            matches = [shape_ok and slot in predictions[0] and strict_equal(predictions[0][slot], item[slot]) for slot in slots]
            core_cases += 1
            core_total += len(slots)
            core_correct += sum(matches)
            core_all += all(matches)
        branches[branch]['core_slots'] = {'correct': core_correct, 'total': core_total,
            'all_correct_cases': core_all, 'cases': core_cases,
            'definition': '골드 항목이 1개인 경우 메뉴·수량·온도, 필요한 메뉴의 휘핑을 비교. null도 명시 정보 부재로 채점. 고정 사이즈와 빈 메모는 제외. 질문 상태는 별도.'}
    earlier_calls = sum(response.get('model_called', False) for record in records
                        for attempt in record.get('previous_attempts', []) for response in attempt['responses'].values())
    return {'planned_cases': planned, 'completed_cases': len(records), 'all_cases_completed': len(records) == planned,
            'reference_may_accept_cases': sum(not r['case']['must_block'] for r in records),
            'reference_requires_review_cases': sum(r['case']['must_block'] for r in records),
            'model_reference_scored': len(scored), 'model_reference_not_scored': len(records) - len(scored),
            'common_valid_reference': {'cases': len(common_valid),
                'A_correct': sum(r['responses']['A_original']['reference_score']['correct'] is True for r in common_valid),
                'B_correct': sum(r['responses']['B_reviewed']['reference_score']['correct'] is True for r in common_valid)},
            'format_recoveries_in_improved_cases': sum(outcome(r) == 'improved' and r['responses']['A_original'].get('status') != 'ok' for r in scored),
            'outcomes': dict(Counter(outcome(r) for r in records)), 'branches': branches,
            'groups': {name: {'cases': len(group), 'scored': sum(r['case']['expected_model'] is not None for r in group),
                             'outcomes': dict(Counter(outcome(r) for r in group))} for name, group in groups.items()},
            'review_timing': timing([r['review']['processing_ms'] for r in records]),
            'protected_token_failures': [r['case']['id'] for r in records if not r['protected_tokens_preserved']],
            'surface_changed': sum(r['review']['reviewed_text'] != r['review']['original_text'] for r in records),
            'context_expanded': sum(bool(r['review']['context_expansion']) for r in records),
            'calls_in_active_results': sum(branches[b]['actual_model_calls'] for b in BRANCHES),
            'calls_in_previous_attempts': earlier_calls,
            'actual_calls': sum(branches[b]['actual_model_calls'] for b in BRANCHES) + earlier_calls}


def render_report(folder, protocol, records, audit, finished):
    summary = summarize(records, len(protocol['case_ids']))
    summary.update(version=VERSION, report_created_at=now(), run_finished=finished, model=protocol['profile']['model'],
                   annotation_status=protocol['annotation_status'], source_kind=protocol.get('source_kind','constructed_text_development'),
                   input_source_audit=protocol.get('input_source_audit'),
                   stt_called_here=False, school_tested=protocol['profile_key'] == 'school' and any(
                       row.get('status') == 'ok' for record in records for row in record['responses'].values()),
                   historical_log_audit=audit)
    write_json(folder / 'summary.json', summary)
    fields = ['id', 'category', 'input_text', 'reviewed_text', 'context', 'review_ms', 'outcome', 'tokens_preserved']
    for branch in ('A', 'B'):
        fields.extend(branch + '_' + name for name in ('called', 'request_ms', 'reference_correct', 'reference_issues', 'decision', 'gate_score', 'question'))
    with (folder / '비교결과.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            case, review = record['case'], record['review']
            row = {'id': case['id'], 'category': case['category'], 'input_text': case['text'],
                   'reviewed_text': review['reviewed_text'], 'context': case['context'], 'review_ms': review['processing_ms'],
                   'outcome': outcome(record), 'tokens_preserved': record['protected_tokens_preserved']}
            for prefix, branch in zip(('A', 'B'), BRANCHES):
                result = record['responses'][branch]
                row.update({prefix + '_called': result.get('model_called', False), prefix + '_request_ms': result.get('request_ms'),
                            prefix + '_reference_correct': result['reference_score']['correct'],
                            prefix + '_reference_issues': '|'.join(result['reference_score']['issues']),
                            prefix + '_decision': result['order_decision']['label'], prefix + '_gate_score': result['gate_score'],
                            prefix + '_question': result['order_decision']['question']})
            writer.writerow(row)
    a, b = (summary['branches'][branch] for branch in BRANCHES)
    lines = [
        '봄카페 · STT 문장 재점검 개발 점검 결과',
        '모델: ' + protocol['profile']['model'],
        '입력 자료 종류: ' + protocol.get('source_kind','constructed_text_development'),
        '이 배치 프로그램 자체는 마이크·STT·자동 대화·장바구니를 실행하지 않음.',
        '정답표: 사용자 정책을 바탕으로 작성한 초안. 팀원의 독립 검수 전이며 최종 성능이 아님.',
        '',
        f"진행: {summary['completed_cases']} / {summary['planned_cases']}개" + (' — 완료' if summary['all_cases_completed'] and finished else ' — 부분 결과'),
        f"실제 모델 호출: {summary['actual_calls']}회 / 원문과 같아 응답을 공유한 B: {b['shared_responses']}개",
        f"정상 API·JSON 응답: 원문 {a['api_json_ok']}/{len(records)} / 재점검 {b['api_json_ok']}/{len(records)}. 실패도 분모에 포함함.",
        f"이 중 재시도 전 요청 {summary['calls_in_previous_attempts']}회는 원본을 보관하고 현재 점수/시간 통계에서는 제외함.",
        f"개발 정답표 필드 일치: 원문 {a['reference_correct']}/{a['reference_denominator']} → 재점검 {b['reference_correct']}/{b['reference_denominator']}",
        f"핵심 슬롯 개별 일치: 원문 {a['core_slots']['correct']}/{a['core_slots']['total']} → 재점검 {b['core_slots']['correct']}/{b['core_slots']['total']}",
        f"핵심 슬롯 모두 일치한 단일 메뉴 문장: 원문 {a['core_slots']['all_correct_cases']}/{a['core_slots']['cases']} → 재점검 {b['core_slots']['all_correct_cases']}/{b['core_slots']['cases']}",
        '※ 핵심 슬롯은 메뉴·수량·온도와 필수 휘핑. 고정 사이즈·빈 메모는 제외한다. 위 전체 조건 일치는 의도·질문 유무까지 포함한 더 엄격한 별도 지표다.',
        f"두 경로 모두 정상 API·JSON인 {summary['common_valid_reference']['cases']}개: 원문 {summary['common_valid_reference']['A_correct']} → 재점검 {summary['common_valid_reference']['B_correct']}개 일치",
        f"전체 개선 중 원문 형식 실패 해소를 포함한 사례: {summary['format_recoveries_in_improved_cases']}개. 전부 의미 해석 개선으로 보지 않음.",
        '※ 메뉴·수량·온도·사이즈·휘핑·메모·의도·질문 유무를 모두 비교. 질문 내용의 적절성은 채점하지 않음.',
        f"개선 {summary['outcomes'].get('improved',0)} / 악화 {summary['outcomes'].get('worsened',0)} / 둘 다 일치 {summary['outcomes'].get('both_correct',0)} / 둘 다 불일치 {summary['outcomes'].get('both_wrong',0)}",
        f"메뉴/복합 의도 정답 미확정으로 모델 채점에서 뺀 문장: {summary['model_reference_not_scored']}개",
        '',
        '검증 단계 (모델 자체의 정답률과 별도)',
        f"원문 경로: 확인이 필요한 요청의 수락 {a['gate'].get('unsafe_accept',0)}건 / 올바른 모델 답변의 추가 차단 {a['gate'].get('unnecessary_block',0)}건",
        f"재점검 경로: 확인이 필요한 요청의 수락 {b['gate'].get('unsafe_accept',0)}건 / 올바른 모델 답변의 추가 차단 {b['gate'].get('unnecessary_block',0)}건",
        f"재점검 경로에서 필드가 맞아 수락 가능한 사례: {b['gate'].get('accepted_correct',0)}건. 차단된 건은 성공 주문 수가 아님.",
        f"정답 초안상 수락 가능한 완성 입력 분모: {summary['reference_may_accept_cases']}개 / 확인·별도 검토가 필요한 입력: {summary['reference_requires_review_cases']}개",
        f"정정/수량/부정 보존 검사 실패: {len(summary['protected_token_failures'])}건",
        '',
        f"재점검 처리시간: 중앙값 {summary['review_timing']['median_ms']} ms / 최대 {summary['review_timing']['max_ms']} ms",
        f"실제 Qwen 요청 중앙값: 원문 {a['request_timing']['median_ms']} ms / 재점검 {b['request_timing']['median_ms']} ms",
        '※ 첫 로딩/캐시/호출 순서/출력 길이가 달라 요청 시간만으로 우열을 판정하지 않음. 동일 문장은 두 번째 속도 표본이 없음.',
        '',
        '해석 범위',
        '- 이번 정답표와 문장은 개발용이다. 반복 실행/비슷한 표현을 독립 음성 표본으로 세지 않는다.',
        '- Only Ice 고정값 적용은 매장 정책 처리이며 모델이 직접 맞힌 것으로 집계하지 않는다.',
        '- 집 Qwen 0.8B 결과를 학교 Qwen 9B, 고령자 음성, 실제 매장 성능으로 확대하지 않는다.',
        '- 단일 추가 주문 필드 검증만 다룬다. 복합 수정 주문의 해석 성공은 별도 평가한다.',
    ]
    if audit is not None:
        lines.extend(['', '과거 실제 입력 기록 — 이번 모델 점수에 합산하지 않음',
                      f"CSV {audit['source_rows']}행 → 중복 제거 {audit['unique_requests']}요청. 마이크 {audit['microphone_requests']}요청 / 서로 다른 마이크 문장 {audit['distinct_microphone_texts']}개.",
                      f"마이크 기록의 재점검 변경 {audit['changed_microphone_requests']}건. 변경은 개선을 뜻하지 않음.",
                      '- 원본 WAV·검수된 정답이 없어 CER를 계산하지 않았다. 짧은 답변의 문맥도 임의로 붙이지 않았다.'])
    else:
        lines.extend(['', '별도의 과거 CSV 감사는 이 실행에 추가하지 않음. 입력 자료 종류는 위 source_kind를 확인.'])
    if summary['input_source_audit'] is not None:
        source = summary['input_source_audit']
        lines.extend(['', '이번 입력의 출처',
            f"기존 마이크 {source.get('microphone_requests')}요청 / 서로 다른 원문 {source.get('distinct_raw_microphone_texts')}개 / 공백·문장부호를 묶은 {source.get('whitespace_punctuation_groups')}개 입력",
            '관측된 인식 문장의 조건을 비교한 개발 점검이다. 원본 발화/의도의 복원 정확도나 음성 CER가 아니다.'])
    text = '\n'.join(lines) + '\n'
    (folder / '결과요약.txt').write_text(text, encoding='utf-8-sig')
    outcome_names = {'improved': '개선', 'worsened': '악화', 'both_correct': '둘 다 일치', 'both_wrong': '둘 다 불일치', 'not_scored': '모델 채점 제외'}
    table = []
    for record in records:
        cells = [record['case']['id'], record['case']['category'], record['case']['text'], record['review']['reviewed_text'],
                 outcome_names[outcome(record)], record['responses']['A_original']['order_decision']['label'],
                 record['responses']['B_reviewed']['order_decision']['label']]
        table.append('<tr>' + ''.join('<td>' + html.escape(str(value)) + '</td>' for value in cells) + '</tr>')
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page += '<title>봄카페 · 재점검 실험 결과</title><style>body{font:18px/1.65 "Malgun Gothic",sans-serif;max-width:1160px;margin:32px auto;padding:0 24px;color:#191919;background:white}h1{font-size:30px}pre{white-space:pre-wrap;font:inherit;background:#f4f4f4;padding:20px;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:15px}td,th{padding:12px;border:1px solid #ccc;text-align:left;vertical-align:top}th{background:#eee}.scroll{overflow:auto}</style>'
    page += '<h1>문장 재점검 · 개발 점검</h1><pre>' + html.escape(text) + '</pre><h2>문장별 결과</h2><div class="scroll"><table><thead><tr>'
    page += ''.join('<th>' + x + '</th>' for x in ['ID', '분류', '원문', '재점검문', '개발 정답표 비교', 'A 검증', 'B 검증'])
    page += '</tr></thead><tbody>' + ''.join(table) + '</tbody></table></div><p>정답표: cases.json · 조건: protocol.json · 실제 요청/원본 응답: cases 폴더 · 전체 표: 비교결과.csv</p></html>'
    (folder / '결과요약.html').write_text(page, encoding='utf-8')
    return summary


def make_protocol(dataset_path, dataset, cases, profile_key, seed, model_info):
    files = [Path(__file__), Path(__file__).with_name('review.py'), Path(__file__).with_name('qwen_client.py'),
             Path(__file__).with_name('order_gate.py'), Path(__file__).with_name('menu_policy.json'),
             Path(__file__).with_name('run_review.py'), Path(__file__).with_name('run_school.py'),
             Path(__file__).with_name('option_spacing.py'),Path(__file__).with_name('case_context.py'),
             Path(__file__).with_name('gate_evidence.py')]
    return {'version': VERSION, 'created_at': now(), 'profile_key': profile_key, 'profile': copy.deepcopy(PROFILES[profile_key]),
            'model_info': model_info, 'policy_version': POLICY['version'], 'contract_version': CONTRACT_VERSION,
            'gate_version': GATE_VERSION, 'transport_version': TRANSPORT_VERSION,
            'generation_options': {'temperature': 0, 'num_predict': 1024, 'think_requested': False, 'stream': False} if PROFILES[profile_key].get('api_style') == 'ollama' else {'temperature': 0, 'max_tokens': 512, 'enable_thinking': False},
            'seed': seed, 'case_ids': [c['id'] for c in cases],
            'dataset_sha256': digest(Path(dataset_path).read_bytes()), 'annotation_status': dataset['annotation_status'],
            'source_kind': dataset.get('source_kind','constructed_text_development'),
            'input_source_audit': dataset.get('source_audit'),
            'source_hashes': {str(p.name): digest(p.read_bytes()) for p in files},
            'prompt_sha256': digest(PROMPT.encode('utf-8')),
            'schema_sha256': digest(json.dumps(ORDER_SCHEMA, sort_keys=True).encode('utf-8')),
            'prompt': PROMPT, 'schema': ORDER_SCHEMA, 'policy_snapshot': copy.deepcopy(POLICY),
            'reference_answers_sent_to_model': False, 'temperature': 0,
            'order_policy': '고정 seed로 문장 순서를 섞고, 변경 문장의 첫 호출을 A/B 번갈아 배치. 동일 입력은 실제 응답 하나를 공유.',
            'environment': {'os': platform.platform(), 'python': platform.python_version(),
                            'logical_cpu_count': os.cpu_count(), 'processor': platform.processor()},
            'limits': ['개발용 문장과 정답 초안. 독립 평가/음성 시험/고령자 연구가 아니다.',
                       '통계적 유의성·반복 안정성·학교 9B 성능을 증명하지 않는다.',
                       '질문 문구의 의미는 검사하지 않는다. 슬롯/의도/질문 유무만 비교한다.']}


def main():
    parser = argparse.ArgumentParser(description='문장 재점검 개발용 일괄 비교. 기본값은 집 모델 실제 호출.')
    parser.add_argument('--profile', choices=PROFILES, default='home')
    parser.add_argument('--cases', type=Path, default=DATASET)
    parser.add_argument('--seed', type=int, default=20261122)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output-root', type=Path, default=ROOT / 'records' / 'batch')
    parser.add_argument('--resume', type=Path, help='같은 코드·정답표·모델의 중단된 실행 폴더')
    parser.add_argument('--logs', action='append', type=Path, help='이전 kiosk-orders CSV. 여러 번 지정 가능')
    parser.add_argument('--skip-log-audit', action='store_true')
    parser.add_argument('--validate-only', action='store_true', help='입력/정답표와 보존만 점검. 모델 호출/정답률 산출 없음')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    dataset = load_cases(args.cases)
    cases = copy.deepcopy(dataset['cases'])
    random.Random(args.seed).shuffle(cases)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError('--limit은 1 이상이어야 합니다.')
        cases = cases[:args.limit]
    if args.validate_only:
        failures = []
        for case in cases:
            review = review_transcript(case['text'], resolve_context(case,CONTEXTS))
            if not all(token in review['lexical_text'] for token in case['preserve_tokens']):
                failures.append(case['id'])
        print(f"입력 점검: {len(cases)}개 / 정답표 채점 가능 {sum(c['expected_model'] is not None for c in cases)}개")
        print('보존 검사 실패: ' + str(failures))
        print('모델을 호출하지 않았고, 성능 점수를 계산하지 않았습니다.')
        return 1 if failures else 0
    print(VERSION + ' · ' + PROFILES[args.profile]['name'], flush=True)
    print(f"입력 문장 {len(cases)}개 / {dataset.get('source_kind','constructed_text_development')}. 마이크/STT·장바구니는 실행하지 않아요.", flush=True)
    try:
        model_info = check_model(PROFILES[args.profile])
    except Exception as exc:
        print('모델에 연결하지 못했어요: ' + str(exc))
        print('집 실험: Docker Desktop과 2_모델서버실행.cmd를 확인해주세요. 학교 모델은 --profile school로 따로 선택합니다.')
        return 2
    protocol = make_protocol(args.cases, dataset, cases, args.profile, args.seed, model_info)
    if args.resume:
        folder = args.resume.resolve()
        old = json.loads((folder / 'protocol.json').read_text(encoding='utf-8'))
        for key in ('version', 'profile_key', 'profile', 'case_ids', 'dataset_sha256', 'source_hashes', 'prompt_sha256', 'schema_sha256', 'seed'):
            if old[key] != protocol[key]:
                raise ValueError('이어서 실행할 조건이 달라졌어요: ' + key + '. 새 실행으로 기록해주세요.')
        protocol = old
    else:
        folder = (args.output_root / (datetime.now(KST).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])).resolve()
        folder.mkdir(parents=True, exist_ok=False)
        write_json(folder / 'protocol.json', protocol)
        write_json(folder / 'cases.json', {**dataset, 'cases': cases, 'case_count': len(cases)})
        snapshot = folder / 'source_snapshot'
        snapshot.mkdir()
        for name in protocol['source_hashes']:
            (snapshot / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    print('결과 폴더: ' + str(folder), flush=True)
    audit = None
    if not args.skip_log_audit:
        log_paths = args.logs if args.logs is not None else list((Path.home() / 'Downloads').glob('kiosk-orders*.csv'))
        if log_paths:
            audit = audit_logs(folder, log_paths)
            print(f"기존 기록 중복 제거: {audit['source_rows']}행 → {audit['unique_requests']}요청 / 마이크 {audit['microphone_requests']}건. 이번 모델 점수에 합산하지 않아요.", flush=True)
    records, changed_index = [], 0
    interrupted, failed_connection = False, False
    try:
        for index, case in enumerate(cases, 1):
            preview = review_transcript(case['text'], resolve_context(case,CONTEXTS))
            order = schedule(case, preview, changed_index)
            if len(order) == 2:
                changed_index += 1
            target = folder / 'cases' / (case['id'] + '.json')
            previous = None
            if target.exists():
                record = json.loads(target.read_text(encoding='utf-8'))
                if any(row.get('status') in ('error', 'skipped') for row in record['responses'].values()):
                    previous = record
                else:
                    print(f"[{index:02}/{len(cases)}] {case['id']} 저장된 결과 재사용 (새 호출 없음)", flush=True)
            if not target.exists() or previous is not None:
                print(f"[{index:02}/{len(cases)}] {case['id']} {case['text']} · {'→'.join(x[0] for x in order)}", flush=True)
                record = execute_case(case, PROFILES[args.profile], order)
                if previous is not None:
                    history = previous.pop('previous_attempts', [])
                    record['previous_attempts'] = history + [previous]
                write_json(target, record)
            records.append(record)
            if any(r.get('status') == 'error' for r in record['responses'].values()):
                failed_connection = True
                print('요청 오류로 중단했어요. 완료한 결과를 보관하고 부분 보고서를 만들어요.', flush=True)
                break
    except KeyboardInterrupt:
        interrupted = True
        print('\n중단한 요청을 성공으로 기록하지 않고 완료한 문장만 저장해요.', flush=True)
    finally:
        summary = render_report(folder, protocol, records, audit, not interrupted and not failed_connection)
        print('\n' + (folder / '결과요약.txt').read_text(encoding='utf-8-sig'), flush=True)
        print('보기 쉬운 결과: ' + str(folder / '결과요약.html'), flush=True)
        print('CSV: ' + str(folder / '비교결과.csv'), flush=True)
        if not summary['all_cases_completed']:
            print('같은 조건으로 이어서 실행: 7_자동비교실험.cmd --profile ' + args.profile + ' --resume "' + str(folder) + '"', flush=True)
        (ROOT / '7_최근결과위치.txt').write_text(str(folder) + '\n', encoding='utf-8-sig')
    return 1 if interrupted or failed_connection else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('일괄 실험을 시작/저장하지 못했어요: ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
