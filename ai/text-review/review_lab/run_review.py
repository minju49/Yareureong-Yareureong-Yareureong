"""User-visible CLI: input -> audit -> optional real paired Qwen calls."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import copy
import csv
import json
import sys
import uuid

from review import POLICY, review_transcript, policy_check
from qwen_client import PROFILES, compare, diagnose
from order_gate import validate_order, GATE_VERSION

if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'): sys.stdin.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parent.parent
CONTEXTS = {
    'none': {},
    'quantity': {'menu_id': 'americano', 'quantity': None, 'temperature': 'ice', 'awaiting': 'quantity',
                 'previous_question': '몇 잔 드릴까요?', 'previous_user_text': '아아 주세요'},
    'temperature': {'menu_id': 'cafe_mocha', 'quantity': 1, 'temperature': None, 'awaiting': 'temperature',
                    'previous_question': '따뜻하게 드릴까요, 차갑게 드릴까요?', 'previous_user_text': '카페모카 한 잔 주세요'},
    'whip': {'menu_id': 'cafe_mocha', 'quantity': 1, 'temperature': 'ice', 'awaiting': 'whipped_cream',
             'previous_question': '휘핑은 어떻게 해드릴까요?', 'previous_user_text': '아이스 카페모카 한 잔 주세요'},
}
CONTEXT_NAMES = {'none': '없음 — 새 문장', 'quantity': '아아의 수량을 묻는 중',
                 'temperature': '카페모카 1잔의 온도를 묻는 중', 'whip': '아이스 카페모카 1잔의 휘핑을 묻는 중'}


def csv_file(folder):
    # A new policy adds columns without corrupting the user's previous CSV.
    return folder / ('review-records-' + POLICY['version'].removeprefix('bom-text-review-') + '.csv')


def display_review(review, facts):
    print('\n원문  : ' + review['original_text'])
    print('재점검: ' + review['reviewed_text'])
    for change in review['changes']:
        print('  - ' + change['from'] + ' → ' + change['to'] + ' / ' + change['reason'])
    for proposal in review['candidates']:
        if not proposal['automatic']:
            print('  - 자동 변경 보류: ' + proposal['from'] + ' / 후보 ' + proposal['to']
                  + ' / 자모 유사도 ' + str(proposal['similarity']))
    if review['context_expansion']:
        print('  - 직전 질문에 대한 짧은 답변을 이전에 확인된 사실과 연결했어요.')
    if not review['changes'] and not review['context_expansion']:
        print('  - 문자 저장 방식만 NFC로 통일했어요.' if review['unicode_normalized'] else '  - 문장을 바꾸지 않았어요.')
    for note in review['notes']: print('  - ' + note)
    print('재점검 처리시간: ' + str(review['processing_ms']) + ' ms (Qwen 시간 제외)')
    if facts['scope'] == 'simple_single_add':
        print('규칙 참고: ' + (facts['next_question'] or '단순 필수 정보가 채워져 있어요.'))
        if facts.get('quantity_status') == 'unit_uncertain':
            print('  수량 후보는 ' + str(facts['quantity']) + '예요. 수량 누락이 아니라 단위 표현 확인 대상이에요.')
        elif facts.get('quantity_status') == 'ambiguous':
            print('  수량 표현이 여러 개라 하나로 확정하지 않았어요.')
        elif facts.get('quantity_status') == 'out_of_range':
            print('  수량 표현은 있지만 이 실험의 1~9잔 범위를 벗어났어요.')
    else:
        print('규칙 참고: ' + facts['note'])
    print('위 규칙 참고와 아래 Qwen 실제 응답은 별도로 기록해요.')


def display_comparison(result, facts, review):
    for key, label in [('A_original', 'A. 원문을 보낸 Qwen'), ('B_reviewed', 'B. 재점검문을 보낸 Qwen')]:
        row = result[key]
        print('\n' + label)
        if row.get('reused_identical_request'):
            print('  원문과 같아 A의 실제 응답을 공유했어요. 추가 호출·별도 속도 측정은 없어요.')
        if row.get('raw_content'): print(row['raw_content'])
        else: print('  ' + row.get('error', row.get('reason', '응답을 확인하지 못했어요.')))
        if row.get('request_ms') is not None: print('  요청 전체 시간: ' + str(row['request_ms']) + ' ms')
        check = diagnose(row, facts)
        row['rule_diagnosis'] = check
        if check['status'] == 'basic_fields_agree':
            print('  단순 필드 대조: 불일치 없음. 전체 의미의 정답 판정은 아니에요.')
        else:
            print('  단순 필드 대조: ' + ' / '.join(check['issues']))
        is_reviewed = key == 'B_reviewed'
        model_text = review['reviewed_text'] if is_reviewed else review['original_text']
        evidence = review['lexical_text'] if is_reviewed else review['original_text']
        decision = validate_order(row, model_text, review['context'], evidence_text=evidence,
                                  changes=review['changes'] if is_reviewed else [])
        row['order_decision'] = decision
        print('  [검증 후 판정] ' + decision['label'])
        if decision['question']: print('  안내: ' + decision['question'])
        for reason in decision['reasons']: print('    - ' + reason)
        if decision['catalog_completions']:
            print('    - 누락된 고정 옵션을 메뉴 정책으로 별도 적용했어요. Qwen 원본은 그대로예요.')
        if decision['can_accept_fields']:
            print('    - 필드 검증 범위에서 다음 단계로 진행 가능. 최종 고객 확인은 별도예요.')
        print('  실제 장바구니 변경: 없음')


def save_record(record, folder):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (record['case_id'] + '.json')
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    csv_path = csv_file(folder)
    new_file = not csv_path.exists()
    comparison = record.get('qwen', {})
    a, b = comparison.get('A_original', {}), comparison.get('B_reviewed', {})
    review = record['review']
    row = {'case_id': record['case_id'], 'created_at': record['created_at'],
           'version': POLICY['version'] + '+' + comparison.get('contract_version', 'review-only'),
           'input_kind': record['input_kind'], 'context_name': record['context_name'],
           'original_text': review['original_text'], 'reviewed_text': review['reviewed_text'],
           'change_types': '|'.join(sorted(set(v['kind'] for v in review['changes']))),
           'context_expanded': bool(review['context_expansion']), 'needs_review': review['needs_review'],
           'quantity_status': record['policy_reference'].get('quantity_status', 'not_scored'),
           'quantity_candidate': record['policy_reference'].get('quantity'),
           'quantity_confirmation': record['policy_reference'].get('needs_quantity_confirmation', False),
           'review_ms': review['processing_ms'], 'model': comparison.get('profile', {}).get('model', ''),
           'A_called': a.get('model_called', False), 'B_called': b.get('model_called', False),
           'A_ms': a.get('request_ms'), 'B_ms': b.get('request_ms'),
           'A_status': a.get('status', 'not_requested'), 'B_status': b.get('status', 'not_requested'),
           'A_rule_diagnosis': a.get('rule_diagnosis', {}).get('status', ''),
           'B_rule_diagnosis': b.get('rule_diagnosis', {}).get('status', ''),
           'A_decision': a.get('order_decision', {}).get('status', 'not_run'),
           'B_decision': b.get('order_decision', {}).get('status', 'not_run'),
           'A_question': a.get('order_decision', {}).get('question', ''),
           'B_question': b.get('order_decision', {}).get('question', ''),
           'A_can_accept_fields': a.get('order_decision', {}).get('can_accept_fields', False),
           'B_can_accept_fields': b.get('order_decision', {}).get('can_accept_fields', False),
           'json_file': target.name}
    with csv_path.open('a', encoding='utf-8-sig' if new_file else 'utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        if new_file: writer.writeheader()
        writer.writerow(row)
    return target


def make_record(text, context_name, profile_key, output_dir, use_qwen=None, input_kind='typed_or_pasted_text'):
    context = copy.deepcopy(CONTEXTS[context_name])
    review = review_transcript(text, context)
    facts = policy_check(review['lexical_text'], context)
    record = {'case_id': datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + uuid.uuid4().hex[:6],
              'created_at': datetime.now(timezone.utc).isoformat(), 'input_kind': input_kind,
              'stt_called_here': False, 'context_name': context_name, 'review': review, 'policy_reference': facts,
              'policy_snapshot': copy.deepcopy(POLICY), 'order_gate_version': GATE_VERSION,
              'scope': '텍스트 입력 재점검 실험. 마이크/STT·장바구니·TTS는 이 프로그램에서 실행하지 않음.'}
    display_review(review, facts)
    if use_qwen is None:
        print('\n비교 대상: ' + PROFILES[profile_key]['name'])
        use_qwen = input('Qwen 실제 응답도 비교할까요? [y/N]: ').strip().lower() in ('y', 'yes', '예')
    exit_ok = True
    try:
        if use_qwen:
            print('실제 요청 중이에요. A 원문 다음 B 재점검문을 같은 설정·문맥으로 보내요.', flush=True)
            record['qwen'] = compare(PROFILES[profile_key], review)
            display_comparison(record['qwen'], facts, review)
            exit_ok = all(record['qwen'][key].get('status') == 'ok' for key in ('A_original', 'B_reviewed'))
        else:
            record['qwen'] = {'status': 'not_requested'}
            print('이번에는 텍스트 재점검만 기록했어요. Qwen은 호출하지 않았어요.')
    except KeyboardInterrupt:
        record['qwen'] = {'status': 'cancelled', 'note': '사용자가 중단. 성공으로 기록하지 않음.'}
        raise
    except Exception as exc:
        record['qwen'] = {'status': 'error', 'error': str(exc)}
        print('Qwen 비교 실패: ' + str(exc))
        exit_ok = False
    finally:
        target = save_record(record, output_dir)
        print('\n기록: ' + str(target))
        print('CSV : ' + str(csv_file(output_dir)))
    return exit_ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text')
    parser.add_argument('--context', choices=list(CONTEXTS), default='none')
    parser.add_argument('--profile', choices=list(PROFILES), default='home')
    parser.add_argument('--qwen', action='store_true', help='실제 Qwen 호출. 미지정 단일 실행은 재점검만 수행.')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'records' / 'review')
    parser.add_argument('--input-kind', default='typed_or_pasted_text')
    args = parser.parse_args()
    from qwen_client import CONTRACT_VERSION
    print('봄카페 문장 재점검 ' + POLICY['version'] + ' / ' + CONTRACT_VERSION)
    print('6개 메뉴 / 수량 생략 시 확인 / Only Ice 온도 질문 생략 / 카페모카 휘핑 확인')
    print('텍스트를 입력하거나 STT 결과를 붙여넣는 실험이에요. 여기서는 마이크·STT를 실행하지 않아요.')
    print('집 Qwen 0.8B 결과와 학교 9B 성능 평가는 구분해서 기록해요.\n')
    print('Qwen 원본과 검증 후 판정을 나란히 표시해요. 확정 가능도 실험용 필드 판정이며 실제 주문은 생성하지 않아요.\n')
    if args.text is not None:
        ok = make_record(args.text, args.context, args.profile, args.output_dir, args.qwen, args.input_kind)
        raise SystemExit(0 if ok else 1)
    context_name, profile_key = args.context, args.profile
    print('명령: /예시 /문맥 /모델 /종료. 빈 줄도 종료예요.')
    while True:
        print('\n현재 문맥: ' + CONTEXT_NAMES[context_name] + ' / 모델: ' + PROFILES[profile_key]['name'])
        text = input('확인할 문장: ').strip()
        if not text or text == '/종료': break
        if text == '/예시':
            print('아아 한 잔 주세요 / 아메리카너 한 잔 주세요 / 딸기한테 한 잔 주세요 / 망고스무디 주세요')
            print('직접 만든 동작 확인 예시이며 실제 녹음 데이터나 성능 평가셋은 아니에요.')
            continue
        if text == '/문맥':
            print('0 없음 / 1 아아 수량 질문 / 2 카페모카 온도 질문 / 3 카페모카 휘핑 질문')
            choice = input('번호: ').strip()
            context_name = {'0': 'none', '1': 'quantity', '2': 'temperature', '3': 'whip'}.get(choice, context_name)
            print('정해둔 이전 질문 상황을 선택했어요. 자동 대화·장바구니 갱신 기능은 아니에요.')
            continue
        if text == '/모델':
            print('1 집 Docker 0.8B / 2 학교 9B (학교에서만 선택해 실제 연결 확인)')
            profile_key = {'1': 'home', '2': 'school'}.get(input('번호: ').strip(), profile_key)
            continue
        try:
            make_record(text, context_name, profile_key, args.output_dir, None, args.input_kind)
        except ValueError as exc:
            print(str(exc))


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\n실험을 종료했어요.')
