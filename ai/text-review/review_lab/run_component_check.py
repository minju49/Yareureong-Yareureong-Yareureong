"""Repeated component checks on 24 already-used development texts.

All arms receive the same explicit context. Identical strings share one
response within a case/repetition only. Repetitions are not new samples.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import shutil
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
import uuid

from review import POLICY, review_transcript
from qwen_client import PROFILES, PROMPT, ORDER_SCHEMA, check_model, request_order
from run_batch import DATASET, load_cases, score_model, score_gate, write_json
from run_review import CONTEXTS
from order_gate import GATE_VERSION, validate_order

ARMS = ('raw', 'lexical', 'full')
GROUPS = {'A': '승인 줄임말', 'N': '메뉴 표기 정리', 'C': '짧은 문맥 답변'}
VERSION = 'bom-component-repeat-0.2'


def aggregate(records, repetitions, profile_key='home'):
    out = {'version':VERSION,'completed_case_repetitions':len(records),'planned_repetitions':repetitions,
           'distinct_development_cases':len({r['case']['id'] for r in records}),
           'new_independent_samples':False,'profile_key':profile_key,
           'school_tested':profile_key=='school' and any(row.get('status')=='ok' for record in records for row in record['arms'].values()),
           'groups':{},'arms':{}}
    for arm in ARMS:
        rows = [r['arms'][arm] for r in records]
        out['arms'][arm] = {'api_json_ok':sum(row['status']=='ok' for row in rows),
            'reference_correct':sum(row['reference_score']['correct'] is True for row in rows),
            'denominator':len(rows),'actual_model_calls':sum(row.get('model_called',False) for row in rows),
            'shared_responses':sum(row.get('shared_identical_input',False) for row in rows),
            'gate':dict(Counter(row['gate_score'] for row in rows))}
        case_sets = {}
        for record in records:
            case_sets.setdefault(record['case']['id'],[]).append(record['arms'][arm])
        complete = [rs for rs in case_sets.values() if len(rs)==repetitions]
        valid = [rs for rs in complete if all(row['status']=='ok' for row in rs)]
        out['arms'][arm]['stability'] = {'complete_cases':len(complete),'all_repetitions_valid_json':len(valid),
            'identical_parsed_json_all_repetitions':sum(len({json.dumps(row['parsed'],sort_keys=True,ensure_ascii=False) for row in rs})==1 for rs in valid),
            'reference_correct_all_repetitions':sum(all(row['reference_score']['correct'] is True for row in rs) for rs in complete)}
    for prefix,label in GROUPS.items():
        group = [r for r in records if r['case']['id'].startswith(prefix)]
        out['groups'][label] = {'distinct_cases':len({r['case']['id'] for r in group}),
            'response_observations':len(group), **{arm:sum(r['arms'][arm]['reference_score']['correct'] is True for r in group) for arm in ARMS}}
    out['actual_model_calls'] = sum(x['actual_model_calls'] for x in out['arms'].values())
    out['limitations'] = ['이미 사용한 개발 문장 24개의 반복 점검이며 독립 시험셋이 아니다.',
        '정답은 팀원의 독립 검수 전인 초안이다. 질문의 실제 의미·친절함은 별도 확인해야 한다.',
        '같은 문맥을 모든 조건에 제공한다. 문맥 유무 실험이 아니라 문맥을 문장에 명시적으로 보강하는 효과를 비교한다.',
        '온도 0에서도 반복 응답의 안정성과 정답 일치는 서로 다른 지표다.',
        '추가 확인 중 CPU 음성 작업이 병행될 수 있어 이 실행의 시간은 단독 속도 벤치마크가 아니다.']
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--profile',choices=('home','school'),default='home')
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args()
    if not 2<=args.repetitions<=5: raise ValueError('반복 횟수는 2~5회로 지정해주세요.')
    data=load_cases()
    cases=[c for c in data['cases'] if c['id'][0] in GROUPS]
    assert len(cases)==24 and all(c['expected_model'] is not None for c in cases)
    if args.validate_only:
        print('개발24문장 × '+str(args.repetitions)+'회 · 대상 '+args.profile+' · 모델 호출 없이 입력 확인 완료.')
        return 0
    if args.profile=='school':
        from run_school import configure
        configure()
    profile=copy.deepcopy(PROFILES[args.profile])
    model=check_model(profile)
    folder=args.output_root/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    (folder/'cases').mkdir(parents=True)
    (folder/'source').mkdir()
    files=('run_component_check.py','review.py','qwen_client.py','order_gate.py','menu_policy.json','run_review.py','run_batch.py','option_spacing.py','run_school.py')
    for name in files: shutil.copy2(Path(__file__).with_name(name),folder/'source'/name)
    write_json(folder/'protocol.json', {'version':VERSION,'policy_version':POLICY['version'],'gate_version':GATE_VERSION,
        'source_kind':'previously_used_constructed_text_component_repeat','distinct_cases':24,'repetitions':args.repetitions,
        'model':profile,'profile_key':args.profile,'model_info':model,'case_ids':[c['id'] for c in cases],
        'reference_answers_sent':False,'arms':{'raw':'원문','lexical':'용어·표기만 정리','full':'용어·표기 정리 + 명시적 문맥 보강'},
        'same_explicit_context_in_all_arms':True,'reference_status':data['annotation_status'],
        'dataset_sha256':hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
        'schema_sha256':hashlib.sha256(json.dumps(ORDER_SCHEMA,sort_keys=True).encode()).hexdigest(),
        'source_hashes':{name:hashlib.sha256((folder/'source'/name).read_bytes()).hexdigest() for name in files},
        'counterbalancing':'seed=20261123 shuffled per repetition; rotated arm order; equal strings share within repetition only'})
    write_json(folder/'cases.json', {'annotation_status':data['annotation_status'],'cases':cases})
    print('결과 폴더: '+str(folder),flush=True)
    rng=random.Random(20261123)
    records=[]
    failed=False
    try:
        for repetition in range(args.repetitions):
            order=list(cases);rng.shuffle(order)
            for idx,case in enumerate(order):
                reviewed=review_transcript(case['text'],CONTEXTS[case['context']])
                texts={'raw':reviewed['original_text'],'lexical':reviewed['lexical_text'],'full':reviewed['reviewed_text']}
                offset=(repetition+idx)%3
                arm_order=ARMS[offset:]+ARMS[:offset]
                by_text={}; arms={}
                print(f"반복 {repetition+1}/{args.repetitions} · {idx+1:02}/24 · {case['id']} {case['text']}",flush=True)
                for arm in arm_order:
                    text=texts[arm]
                    if text in by_text:
                        row=copy.deepcopy(by_text[text])
                        row.update(model_called=False,request_ms=None,shared_identical_input=True)
                    else:
                        row=request_order(profile,text,reviewed['context'])
                        by_text[text]=copy.deepcopy(row)
                    row['reference_score']=score_model(row,case['expected_model'])
                    row['order_decision']=validate_order(row,text,reviewed['context'],
                        evidence_text=reviewed['original_text'] if arm=='raw' else reviewed['lexical_text'],
                        changes=[] if arm=='raw' else reviewed['changes'])
                    row['gate_score']=score_gate(row,case)
                    arms[arm]=row
                    if row['status']=='error': failed=True;break
                for arm in ARMS:
                    if arm not in arms:
                        text=texts[arm]
                        row={'status':'skipped','model_called':False,'request_ms':None,'reason':'다른 조건 연결 실패로 추가 요청 생략'}
                        row['reference_score']=score_model(row,case['expected_model'])
                        row['order_decision']=validate_order(row,text,reviewed['context'])
                        row['gate_score']=score_gate(row,case)
                        arms[arm]=row
                record={'case':case,'repetition':repetition+1,'review':reviewed,'arm_order':arm_order,'arms':arms,
                        'cart_mutated':False,'new_speech_recording':False}
                records.append(record)
                write_json(folder/'cases'/f"{case['id']}-R{repetition+1}.json",record)
                write_json(folder/'summary.json',aggregate(records,args.repetitions,args.profile))
                if failed: break
            if failed: break
    except KeyboardInterrupt:
        failed=True
    summary=aggregate(records,args.repetitions,args.profile)
    summary['all_planned_completed']=len(records)==24*args.repetitions and not failed
    write_json(folder/'summary.json',summary)
    lines=['기능별 반복 비교 결과 · '+profile['model'],
           '기존 개발 문장 24개 × '+str(args.repetitions)+'회. 새로운 독립 음성 표본이 아닙니다.',
           '완료한 문장·반복 조합: '+str(len(records))+' / '+str(24*args.repetitions),
           '실제 모델 호출: '+str(summary['actual_model_calls'])+'회',
           '정답은 검수 전 개발 초안이며 질문 문구의 실제 의미는 자동 채점하지 않습니다.','']
    for group,row in summary['groups'].items():
        n=row['response_observations']
        lines.append(group+': 원문 '+str(row['raw'])+'/'+str(n)+' → 용어만 '+str(row['lexical'])+'/'+str(n)+' → 용어+문맥 '+str(row['full'])+'/'+str(n))
    text='\n'.join(lines)+'\n\n조건과 원본 요청·응답은 protocol.json과 cases 폴더에 보관합니다.\n'
    (folder/'결과요약.txt').write_text(text,encoding='utf-8-sig')
    print(text)
    print('결과: '+str(folder),flush=True)
    return 0 if summary['all_planned_completed'] else 1


if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
