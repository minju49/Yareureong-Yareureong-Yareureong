"""Validate an explicit user review before freezing development references.

No annotation is invented, and a review after development is never called a
blind holdout. A requested correction must be resolved before freezing.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import uuid

from review import POLICY
from run_batch import DATASET, ROOT, strict_equal, write_json


def validate_review(review, dataset, dataset_sha256):
    if review.get('version') != 'bom-human-reference-review-0.1':
        raise ValueError('지원하는 검수 기록 형식이 아닙니다.')
    if review.get('dataset_sha256') != dataset_sha256 or review.get('dataset_version') != dataset['version']:
        raise ValueError('검수한 문장·정답표와 현재 파일이 다릅니다. 변경 내용을 다시 검토해주세요.')
    if review.get('policy_version') != POLICY['version']:
        raise ValueError('검수 당시와 현재의 보정 버전이 다릅니다.')
    if not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip():
        raise ValueError('검수자 코드가 없습니다.')
    if review.get('reference_state') != 'all_cases_approved_by_user':
        raise ValueError('미검토·수정 필요·판단 보류가 남아 있어 정답을 확정하지 않았습니다.')
    rows = review.get('cases')
    if not isinstance(rows, list) or len(rows) != len(dataset['cases']):
        raise ValueError('검수 문장 수가 맞지 않습니다.')
    by_id = {row.get('case_id'): row for row in rows if isinstance(row, dict)}
    if len(by_id) != len(rows) or set(by_id) != {case['id'] for case in dataset['cases']}:
        raise ValueError('검수 문장 ID에 누락·중복·추가가 있습니다.')
    for case in dataset['cases']:
        row = by_id[case['id']]
        if row.get('status') != 'approved':
            raise ValueError(case['id'] + ': 검토가 완료되지 않았습니다.')
        if row.get('text') != case['text'] or row.get('context') != case['context']:
            raise ValueError(case['id'] + ': 검수 당시 입력이나 문맥이 다릅니다.')
        if not strict_equal(row.get('proposed_reference'), case['expected_model']):
            raise ValueError(case['id'] + ': 정답 수정이 있습니다. 메모를 반영한 새 정답표를 먼저 검토해야 합니다.')
        if row.get('model_scoring_excluded') is not (case['expected_model'] is None):
            raise ValueError(case['id'] + ': 채점 제외 여부가 다릅니다.')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('review_file', type=Path)
    parser.add_argument('--dataset', type=Path, default=DATASET)
    parser.add_argument('--output-root', type=Path, default=ROOT/'records'/'references')
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    dataset = json.loads(raw)
    review_bytes = args.review_file.read_bytes()
    review = json.loads(review_bytes.decode('utf-8-sig'))
    validate_review(review, dataset, hashlib.sha256(raw).hexdigest())
    folder = args.output_root/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    (folder/'user-review.json').write_bytes(review_bytes)
    dataset['annotation_status'] = '사용자가 개발용 정답 초안을 검수함. 개발 결과를 본 뒤의 검수이며 독립 최종 시험셋이 아니다.'
    dataset['human_review'] = {'reviewer':review['reviewer'], 'review_created_at':review.get('created_at'),
        'frozen_at':datetime.now(timezone.utc).isoformat(), 'original_dataset_sha256':hashlib.sha256(raw).hexdigest(),
        'review_file_sha256':hashlib.sha256(review_bytes).hexdigest(), 'blind_independent_review':False,
        'review_phase':'post_development_before_next_run','all_cases_approved_by_user':True}
    target = folder/'reviewed-cases.json'
    write_json(target,dataset)
    print('사용자 검수 기록과 일치하는 개발용 정답표를 고정했습니다.')
    print('독립 시험셋이나 실제 음성 검증으로 표시하지 않았습니다.')
    print('정답표: '+str(target.resolve()))
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print('정답표를 고정하지 못했습니다: '+str(exc))
        raise SystemExit(2)
