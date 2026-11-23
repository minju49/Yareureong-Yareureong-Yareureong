"""Revalidate saved Qwen answers without contacting a model or rewriting a run."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
import uuid

from order_gate import GATE_VERSION, validate_order
from run_batch import BRANCHES, score_gate, write_json


def replay_record(record):
    rows = {}
    review = record['review']
    for branch in BRANCHES:
        saved = record['responses'][branch]
        text = review['original_text'] if branch == 'A_original' else review['reviewed_text']
        decision = validate_order(saved, text, record['context'],
            evidence_text=review['original_text'] if branch == 'A_original' else review['lexical_text'],
            changes=[] if branch == 'A_original' else review['changes'])
        temporary = {**saved, 'order_decision': decision}
        rows[branch] = {
            'previous_decision': copy.deepcopy(saved['order_decision']),
            'previous_gate_score': saved['gate_score'],
            'replayed_decision': decision,
            'replayed_gate_score': score_gate(temporary, record['case']),
            'raw_content_sha256': hashlib.sha256(saved.get('raw_content', '').encode('utf-8')).hexdigest(),
            'model_called_here': False,
        }
    return {'id': record['case']['id'], 'text': record['case']['text'],
            'reviewed_text': review['reviewed_text'], 'context': copy.deepcopy(record['context']),
            'responses': rows, 'new_model_calls': 0, 'cart_mutated': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args(argv)
    run = args.run.resolve()
    paths = sorted((run / 'cases').glob('*.json'))
    if not paths or not (run / 'protocol.json').is_file():
        raise ValueError('원본 배치 실험의 protocol.json과 cases 폴더를 확인해주세요.')
    out = args.output_root.resolve() / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    out.mkdir(parents=True)
    (out / 'source').mkdir()
    for name in ('order_gate.py', 'review.py', 'menu_policy.json', 'replay_gate.py', 'run_batch.py', 'option_spacing.py'):
        shutil.copy2(Path(__file__).with_name(name), out / 'source' / name)
    records = []
    for path in paths:
        raw = path.read_bytes()
        record = replay_record(json.loads(raw))
        record['source_file'] = str(path)
        record['source_file_sha256'] = hashlib.sha256(raw).hexdigest()
        if path.read_bytes() != raw:
            raise RuntimeError('재검증 중 원본 파일이 변경되어 중단합니다.')
        records.append(record)
    summary = {'new_gate_version': GATE_VERSION, 'source_run': str(run), 'case_count': len(records),
               'new_model_calls': 0, 'raw_model_answers_rewritten': False,
               'source_files_unchanged': True, 'cart_mutated': False,
               'scope': '이미 본 개발 기록의 검증기 회귀 점검. 새 Qwen 실험/독립 시험셋이 아님.',
               'branches': {}}
    lines = ['저장된 Qwen 응답의 검증기 재점검', f'문장 {len(records)}개 / 새 모델 호출 0회',
             '원본 응답·원본 실험 결과는 변경하지 않았습니다.', '']
    for branch in BRANCHES:
        pairs = [record['responses'][branch] for record in records]
        previous = Counter(row['previous_gate_score'] for row in pairs)
        current = Counter(row['replayed_gate_score'] for row in pairs)
        transitions = [record['id'] for record in records
                       if record['responses'][branch]['previous_gate_score'] != record['responses'][branch]['replayed_gate_score']]
        summary['branches'][branch] = {'previous_gate_versions': sorted({r['previous_decision']['version'] for r in pairs}),
                                      'previous': dict(previous), 'replayed': dict(current), 'changed_cases': transitions}
        lines.extend([branch, f"  확인이 필요한 요청 수락: {previous['unsafe_accept']} → {current['unsafe_accept']}건",
                      f"  올바른 모델 응답 추가 차단: {previous['unnecessary_block']} → {current['unnecessary_block']}건",
                      f"  올바른 필드 수락: {previous['accepted_correct']} → {current['accepted_correct']}건",
                      '  판정 변화: ' + (', '.join(transitions) or '없음'), ''])
    write_json(out / 'replay.json', {'summary': summary, 'records': records})
    (out / '재점검요약.txt').write_text('\n'.join(lines) + '\n발견한 오류를 고친 개발 자료 재점검이며 새 환경의 무오류를 보장하지 않습니다.\n', encoding='utf-8-sig')
    print((out / '재점검요약.txt').read_text(encoding='utf-8-sig'))
    print('결과: ' + str(out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
