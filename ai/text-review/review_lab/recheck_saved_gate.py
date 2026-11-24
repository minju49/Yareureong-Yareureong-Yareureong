"""Recheck saved real Qwen responses; never call models or overwrite originals."""
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import uuid
from collections import Counter
from order_gate import GATE_VERSION,validate_order
from run_batch import score_gate,score_model,write_json

ROOT=Path(__file__).resolve().parent.parent


def replay(folder,output):
    records=[];sources=[]
    for target in sorted(Path(folder).glob('cases/*.json')):
        original=target.read_bytes();r=json.loads(original);case=r['case'];review=r['review']
        row={'id':case['id'],'text':case['text'],'branches':{}}
        for branch,b in r['responses'].items():
            if branch not in ('A_original','B_reviewed'):continue
            a=branch=='A_original';evidence=review['original_text'] if a else review['lexical_text']
            model_text=review['original_text'] if a else review['reviewed_text']
            copied=copy.deepcopy(b)
            copied['order_decision']=validate_order(copied,model_text,r['context'],evidence_text=evidence,
                changes=[] if a else review['changes'])
            copied['reference_score']=score_model(copied,case['expected_model'])
            row['branches'][branch]={'old_gate_score':b.get('gate_score'),
                'new_gate_score':score_gate(copied,case),'old_decision':b['order_decision'],
                'new_decision':copied['order_decision'],'unchanged_model_reference_score':copied['reference_score'],
                'raw_response_sha256':hashlib.sha256(b.get('raw_content','').encode()).hexdigest()}
        sources.append({'path':str(target.resolve()),'sha256':hashlib.sha256(original).hexdigest()});records.append(row)
    if not records:raise ValueError('cases/*.json이 있는 비교 결과 폴더를 선택해주세요.')
    summary={'scope':'저장된 실제 Qwen 응답의 검증 규칙만 재실행. 새 Qwen/STT/마이크 호출 없음.',
        'gate_version':GATE_VERSION,'new_model_calls':0,'cases':len(records),'model_outputs_changed':False,
        'branches':{b:{phase:dict(Counter(r['branches'][b][phase+'_gate_score'] for r in records))
                    for phase in ('old','new')} for b in ('A_original','B_reviewed')}}
    write_json(output/'검증규칙_재검사.json',{'summary':summary,'sources':sources,'records':records})
    lines=[summary['scope'],'검증 버전: '+GATE_VERSION,'문장 수: '+str(len(records))]
    for b,counts in summary['branches'].items():
        lines.append(b+': 불필요 차단 '+str(counts['old'].get('unnecessary_block',0))+' → '+str(counts['new'].get('unnecessary_block',0))+
            ' / 필드 수락 가능 '+str(counts['old'].get('accepted_correct',0))+' → '+str(counts['new'].get('accepted_correct',0))+
            ' / 검토 필요 입력의 오수락 '+str(counts['old'].get('unsafe_accept',0))+' → '+str(counts['new'].get('unsafe_accept',0)))
    lines.append('모델 자체의 정답률은 바뀌지 않습니다. 원본 실험 기록을 덮어쓰지 않았습니다.')
    (output/'검증규칙_재검사.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path)
    parser.add_argument('--output-root',type=Path,default=ROOT/'records'/'gate-recheck')
    args=parser.parse_args()
    source=args.input
    if source is None:
        choices=sorted((ROOT/'records'/'additional20').glob('*/protocol.json'))
        if not choices:raise ValueError('먼저 실행한 새 20문장 records/additional20 결과가 필요합니다.')
        source=choices[-1].parent
    output=args.output_root/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);output.mkdir(parents=True,exist_ok=False)
    replay(source,output)
    print((output/'검증규칙_재검사.txt').read_text(encoding='utf-8-sig'))
    print('별도로 저장한 결과: '+str(output))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError) as exc:print('재검사 실패: '+str(exc));raise SystemExit(2)
