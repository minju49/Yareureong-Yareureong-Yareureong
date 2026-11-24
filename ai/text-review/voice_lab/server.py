"""Local real-ASR comparison laboratory. No cart/TTS or implicit Qwen calls."""
from __future__ import annotations
import argparse
import base64
import copy
import csv
from datetime import datetime,timezone,timedelta
import hashlib
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import io
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
import traceback
import unicodedata
from urllib.parse import urlsplit
import uuid
import webbrowser

ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT/'vendor'),str(ROOT/'review_lab')]
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
from stt_engine import SenseVoice,pcm_wave
from review import POLICY,review_transcript
from run_batch import load_cases,execute_case,schedule,write_json,score_model
from run_review import CONTEXTS
from case_context import resolve_context
from qwen_client import PROFILES,CONTRACT_VERSION,TRANSPORT_VERSION,ORDER_SCHEMA,PROMPT,check_model
from run_school import configure,preflight
from order_gate import GATE_VERSION

VERSION='bom-voice-review-1.1'
KST=timezone(timedelta(hours=9))
DATASET=ROOT/'review_lab'/'additional20_cases.json'
STATIC=Path(__file__).with_name('static')


def cer(reference,hypothesis):
    def normalize(s):return ''.join(c for c in unicodedata.normalize('NFC',s) if not c.isspace() and not unicodedata.category(c).startswith('P'))
    a,b=normalize(reference),normalize(hypothesis)
    if not a:return None
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        row=[i]
        for j,y in enumerate(b,1):row.append(min(row[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
        prev=row
    return {'rate':prev[-1]/len(a),'edits':prev[-1],'reference_chars':len(a),
        'normalization':'NFC; remove whitespace and Unicode punctuation; human-entered reference only'}


def decode64(value,limit):
    if not isinstance(value,str) or len(value)>limit*4//3+8:raise ValueError('음성 데이터 크기를 확인해주세요.')
    try:result=base64.b64decode(value,validate=True)
    except (ValueError,TypeError) as exc:raise ValueError('음성 데이터가 올바르지 않습니다.') from exc
    if len(result)>limit:raise ValueError('음성 데이터가 너무 큽니다.')
    return result


class Experiment:
    def __init__(self,root=ROOT,profile=None):
        self.root=Path(root).resolve();self.engine=SenseVoice(self.root)
        self.data=load_cases(DATASET);self.profile=copy.deepcopy(profile) if profile is not None else configure()
        self.lock=threading.Lock();self.busy=False;self.check=None
        self.records=self.root/'records'/'voice';self.records.mkdir(parents=True,exist_ok=True)

    def status(self):
        return {'version':VERSION,'root':str(self.root),'python':sys.version,'os':platform.platform(),
            'cpu':platform.processor(),'logical_cpu_count':os.cpu_count(),'memory_note':'STT는 CPU 2스레드. 실제 PC 사양은 작업 관리자에서도 확인하세요.',
            'stt':self.engine.status(),'busy':self.busy,
            'qwen':{'model':self.profile['model'],'base_url':self.profile['base_url'],'last_connection_check':self.check},
            'policy_version':POLICY['version'],'contract_version':CONTRACT_VERSION,'gate_version':GATE_VERSION,
            'noise_reduction':'별도 모델 미적용. 녹음 시 요청한 브라우저 필터와 실제 설정은 개별 기록에 저장.',
            'stt_method':'녹음을 마친 뒤 최종 문장을 인식. 스트리밍·임시 자막 없음.',
            'scope':'실제 STT→문장 재점검→선택 시 학교 Qwen A/B→필드 검증. 장바구니·TTS·DB·결제 없음.',
            'records_root':str(self.records),'cases':self.data['cases'],
            'dataset_sha256':hashlib.sha256(DATASET.read_bytes()).hexdigest()}

    def run(self,body):
        if not self.lock.acquire(blocking=False):raise ValueError('앞선 처리가 진행 중입니다. 끝난 뒤 실행해주세요.')
        self.busy=True
        folder=self.records/(datetime.now(KST).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
        folder.mkdir()
        result={'version':VERSION,'created_at':datetime.now(KST).isoformat(),'status':'started',
            'cart_mutated':False,'tts_called':False,'experiment_dir':str(folder),
            'reference_sent_to_model':False,'input_source':body.get('input_source','unknown'),
            'capture_metadata':body.get('capture_metadata',{}),'annotation_status':'미검수 실제 음성 점검'}
        started=time.perf_counter()
        try:
            if type(body.get('use_qwen',False)) is not bool:raise ValueError('Qwen 실행 선택을 확인해주세요.')
            audio=decode64(body.get('wav_b64'),1_000_000);pcm_wave(audio)
            (folder/'input_16k.wav').write_bytes(audio)
            source=decode64(body.get('original_b64'),8_000_000)
            if source[:4]!=b'RIFF' or source[8:12]!=b'WAVE':raise ValueError('원본 WAV를 확인해주세요.')
            (folder/'source.wav').write_bytes(source)
            result['source_sha256']=hashlib.sha256(source).hexdigest();result['input_sha256']=hashlib.sha256(audio).hexdigest()
            case_id=body.get('case_id','')
            chosen=next((c for c in self.data['cases'] if c['id']==case_id),None)
            if case_id and chosen is None:raise ValueError('문장 번호가 올바르지 않습니다.')
            context=resolve_context(chosen,CONTEXTS) if chosen else {}
            result['context']=context;result['selected_case']=copy.deepcopy(chosen)
            reference=body.get('reference_text','')
            if not isinstance(reference,str) or len(reference)>2000:raise ValueError('검수한 정답 전사는 2,000자 이내여야 합니다.')
            confirmed=body.get('reference_confirmed',False)
            if type(confirmed) is not bool:raise ValueError('정답 검수 선택을 확인해주세요.')
            if confirmed and (not chosen or not reference.strip()):raise ValueError('정답 대조를 하려면 문장 번호를 고르고 실제 녹음을 듣고 작성한 전사가 필요합니다.')
            result['reference_text']=reference;result['reference_confirmed_by_user']=confirmed
            result['stt']=self.engine.recognize(audio)
            result['stt_cer']=cer(reference,result['stt']['text']) if reference.strip() else None
            if not result['stt']['text']:raise ValueError('인식 문장이 비어 있어 Qwen을 호출하지 않았습니다. 원본을 재생해 목소리를 확인해주세요.')
            text=result['stt']['text'];review=review_transcript(text,context);result['review']=review
            result['qwen_requested']=body.get('use_qwen',False)
            if body.get('use_qwen',False):
                case=copy.deepcopy(chosen) if chosen else {'id':'MIC','category':'자유 음성','context':'none','preserve_tokens':[]}
                case['text']=text
                if not confirmed:case.update(expected_model=None,must_block=False,preserve_tokens=[])
                order=schedule(case,review,int(folder.name[-1],16)%2)
                # Same reviewed text/context as the text comparison; references are
                # only used AFTER requests. They never enter Qwen messages.
                record=execute_case(case,self.profile,order)
                for branch,row in record['responses'].items():
                    if not confirmed:
                        row['reference_score']={'scored':False,'correct':None,'fields':{},'issues':['실제 발화의 정답 미검수. 정답률에 합산하지 않음']}
                        row['gate_score']='not_scored'
                result['comparison']=record
                result['annotation_status']='사용자가 녹음을 듣고 문장별 정답과 의미 일치를 확인함. 개발 점검.' if confirmed else '실제 발화 정답 미검수. 실행 결과만 기록. 정답률 제외.'
                result['profile']=copy.deepcopy(self.profile)
                result['status']='completed' if all(r.get('status')=='ok' for r in record['responses'].values()) else 'qwen_failed'
            else:
                result.update(status='completed',comparison=None,annotation_status='실제 STT·재점검만 실행. Qwen 미호출.')
            result['protocol']={'policy_version':POLICY['version'],'transport_version':TRANSPORT_VERSION,'gate_version':GATE_VERSION,
                'contract_version':CONTRACT_VERSION,'dataset_sha256':hashlib.sha256(DATASET.read_bytes()).hexdigest(),
                'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
                'schema_sha256':hashlib.sha256(json.dumps(ORDER_SCHEMA,sort_keys=True).encode()).hexdigest(),
                'prompt':PROMPT,'schema':ORDER_SCHEMA,'context_is_explicitly_selected':True,
                'reference_answers_sent':False,'no_automatic_conversation_state':True,
                'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    [Path(__file__),Path(__file__).with_name('stt_engine.py'),*[ROOT/'review_lab'/n for n in
                    ('review.py','qwen_client.py','order_gate.py','run_batch.py','case_context.py','gate_evidence.py','option_spacing.py','menu_policy.json')]]}}
            return result
        except Exception as exc:
            result.update(status='failed',error=str(exc),traceback=traceback.format_exc())
            return result
        finally:
            try:
                result['experiment_wall_ms']=round((time.perf_counter()-started)*1000,3)
                write_json(folder/'result.json',result)
                (self.root/'마지막음성결과위치.txt').write_text(str(folder),encoding='utf-8-sig')
            finally:self.busy=False;self.lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version='BomVoiceReview/1.0'
    def log_message(self,fmt,*args):print(fmt%args,flush=True)
    def send(self,status,data,mime='application/json; charset=utf-8'):
        if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False).encode('utf-8')
        elif isinstance(data,str):data=data.encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/status':return self.send(200,self.server.experiment.status())
        if path=='/api/records.csv':
            output=io.StringIO();writer=csv.writer(output);writer.writerow(['folder','status','case_id','source','stt','reviewed','stt_ms','review_ms','A_status','A_field_match','A_decision','A_question','B_status','B_field_match','B_decision','B_question','reference_confirmed'])
            for target in sorted(self.server.experiment.records.glob('*/result.json')):
                r=json.loads(target.read_text(encoding='utf-8'));cmp=r.get('comparison') or {};responses=cmp.get('responses',{})
                row=[str(target.parent),r['status'],(r.get('selected_case') or {}).get('id',''),r.get('input_source'),r.get('stt',{}).get('text'),r.get('review',{}).get('reviewed_text'),r.get('stt',{}).get('inference_ms'),r.get('review',{}).get('processing_ms')]
                for key in ('A_original','B_reviewed'):
                    b=responses.get(key,{});d=b.get('order_decision',{});row.extend([b.get('status'),b.get('reference_score',{}).get('correct'),d.get('label'),d.get('question')])
                writer.writerow(row+[r.get('reference_confirmed_by_user',False)])
            return self.send(200,('\ufeff'+output.getvalue()).encode('utf-8'),'text/csv; charset=utf-8')
        allowed={'/':'index.html','/app.js':'app.js','/recorder-worklet.js':'recorder-worklet.js','/style.css':'style.css'}
        if path not in allowed:return self.send(404,{'error':'없는 주소입니다.'})
        target=STATIC/allowed[path];mime={'.html':'text/html','.js':'text/javascript','.css':'text/css'}[target.suffix]
        return self.send(200,target.read_bytes(),mime+'; charset=utf-8')
    def do_POST(self):
        # Only same-local-page JSON actions; do not enable permissive CORS.
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''):return self.send(403,{'error':'현재 로컬 화면에서 실행해주세요.'})
        path=urlsplit(self.path).path
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=13_000_000:raise ValueError('요청 크기를 확인해주세요.')
            if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('JSON 요청이 필요합니다.')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('요청 형식이 올바르지 않습니다.')
            exp=self.server.experiment
            if path=='/api/run':return self.send(200,exp.run(body))
            if path=='/api/check-stt':
                if not exp.lock.acquire(blocking=False):raise ValueError('앞선 처리가 끝난 뒤 점검해주세요.')
                exp.busy=True
                try:
                    r=exp.engine.recognize((exp.root/'samples'/'synthetic_smoke.wav').read_bytes())
                    exp.engine.last_success['synthetic_smoke']=True
                    passed=('아메리카노' in r['text'] and ('아이스' in r['text'] or '차가' in r['text']))
                    result={'status':'completed' if passed else 'failed','synthetic_smoke':True,'stt':r,
                        'note':'동봉 합성 음성의 실제 인식 점검. 사람의 마이크·주문 정확도 평가는 아님.'}
                    write_json(exp.root/'diagnostics'/'last-stt-smoke.json',result)
                    return self.send(200,result)
                finally:exp.busy=False;exp.lock.release()
            if path=='/api/check-qwen':
                if not exp.lock.acquire(blocking=False):raise ValueError('앞선 처리가 끝난 뒤 점검해주세요.')
                exp.busy=True
                try:
                    ok=preflight(exp.profile);exp.check={'checked_at':datetime.now(KST).isoformat(),'api_json_ok':ok,'note':'실제 점검 1건. 전체 주문 정확도 아님.'}
                    return self.send(200,exp.check)
                finally:exp.busy=False;exp.lock.release()
            return self.send(404,{'error':'없는 작업입니다.'})
        except Exception as exc:
            print(traceback.format_exc(),flush=True);return self.send(400,{'error':str(exc)})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8010)
    parser.add_argument('--no-browser',action='store_true');parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args();os.chdir(ROOT)
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    print(VERSION+' / '+str(ROOT),flush=True)
    experiment=Experiment()
    if args.check_only:
        result=experiment.engine.recognize((ROOT/'samples'/'synthetic_smoke.wav').read_bytes())
        result['synthetic_smoke']=True
        experiment.engine.last_success['synthetic_smoke']=True
        passed='아메리카노' in result['text'] and ('아이스' in result['text'] or '차가' in result['text'])
        write_json(ROOT/'diagnostics'/'stt-check.json',{'passed':passed,'stt':result,'status':experiment.status()})
        print('[실제 SenseVoice] '+result['text'],flush=True)
        print('STT 실행 '+('확인 완료' if passed else '결과 확인 필요')+' / 합성 점검 음성이며 사람의 주문 정확도 평가가 아닙니다.',flush=True)
        print('Qwen·마이크는 아직 실행하지 않았습니다.',flush=True)
        return 0 if passed else 2
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.experiment=experiment
    url=f'http://127.0.0.1:{args.port}/'
    print('마이크 시험 화면: '+url+' / 종료: Ctrl+C',flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        target=ROOT/'diagnostics'/'startup-error.txt';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(traceback.format_exc(),encoding='utf-8');print(str(exc)+'\n진단 기록: '+str(target),flush=True)
        raise SystemExit(2)
