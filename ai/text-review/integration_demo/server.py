"""Serve the team's kiosk with actual speech, Qwen and Spring/MariaDB calls."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime,timezone
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler
import uuid
import webbrowser

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path[:0]=[str(HERE),str(ROOT/'vendor'),str(ROOT/'review_lab'),str(ROOT/'voice_lab')]
from backend import MenuBackend
from orders import OrderSession
from catalog import supported
from stt_engine import SenseVoice,pcm_wave
from run_school import configure
from run_batch import write_json
from order_gate import GATE_VERSION

VERSION='bom-team-integration-0.1'
STATIC=HERE/'static'


def config():
    path=ROOT/'integration.local.json'
    value=json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    value.setdefault('spring_base_url','http://127.0.0.1:8080')
    value.setdefault('noise_base_url','')
    return value


class App:
    def __init__(self,settings=None,model_request=None):
        self.settings=settings or config();self.backend=MenuBackend(self.settings['spring_base_url'])
        self.engine=SenseVoice(ROOT);self.profile=configure();self.sessions={};self.catalog=[]
        self.catalog_error=None;self.lock=threading.Lock();self.audio_lock=threading.Lock()
        self.records=ROOT/'records'/'integration';self.records.mkdir(parents=True,exist_ok=True)
        self.model_request=model_request
        prompt_file=STATIC/'prompts'/'manifest.json'
        self.prompts=json.loads(prompt_file.read_text(encoding='utf-8')) if prompt_file.is_file() else {}
    def load_catalog(self):
        try:self.catalog=self.backend.catalog();self.catalog_error=None;return self.catalog
        except Exception as exc:self.catalog_error=str(exc);raise
    def info(self):
        return {'version':VERSION,'root':str(ROOT),'gate_version':GATE_VERSION,'stt':self.engine.status(),
            'spring_base_url':self.settings['spring_base_url'],'catalog_loaded':bool(self.catalog),'catalog_error':self.catalog_error,
            'catalog_count':len(self.catalog),'voice_supported':supported(self.catalog),'catalog':self.catalog,
            'qwen':{'base_url':self.profile['base_url'],'model':self.profile['model'],'actual_call_verified':any(s.last and
                s.last.get('model_called') is True and s.last.get('qwen',{}).get('status')=='ok' and
                s.last.get('qwen',{}).get('returned_model')==self.profile['model'] for s in self.sessions.values())},
            'noise':{'base_url':self.settings['noise_base_url'],'default':'off','available_configured':bool(self.settings['noise_base_url'])},
            'scope':'61 touch menus from live Spring/MariaDB; 6 voice menus; server-owned cart; demo receipt stored in MariaDB; no actual payment',
            'tts':{'ready':bool(self.prompts),'method':'MeloTTS Korean 사전 생성 고정 안내 재생',
                'dynamic_synthesis_on_client':False,'prompt_count':len(self.prompts),
                'note':'실제 MeloTTS로 생성한 고정 문구만 재생. 생성 기록 보존. 이 PC에서 새 문장을 합성하는 기능은 아님.'}}
    def enrich(self,state):
        value=self.prompts.get(state.get('message',''))
        state['guide_audio']=({'audio_url':'/prompts/'+value['filename'],**value,'generated_now':False} if value else None)
        return state
    def session(self,ident):
        if ident not in self.sessions:raise ValueError('주문 세션이 없습니다. 화면을 새로고침해주세요.')
        return self.sessions[ident]
    def new_session(self):
        catalog=self.load_catalog()
        kwargs={'model_request':self.model_request} if self.model_request else {}
        item=OrderSession(self.backend,self.profile,catalog,**kwargs)
        with self.lock:self.sessions[item.id]=item
        return self.enrich(item.state())
    def noise(self,audio,mode):
        if mode=='off':return audio,{'requested':'off','selected':'off','applied':False,'processing_ms':0}
        if mode not in ('zipenhancer','mossgan','mossformer2_zip','auto'):raise ValueError('잡음 제거 모드를 확인해주세요.')
        if not self.settings['noise_base_url']:raise ValueError('잡음 제거 서버 주소가 없습니다. 담당자 설정에서 연결해주세요.')
        body=json.dumps({'wav_b64':base64.b64encode(audio).decode(),'mode':mode}).encode()
        req=Request(self.settings['noise_base_url'].rstrip('/')+'/api/process',data=body,headers={'Content-Type':'application/json'})
        from urllib.error import HTTPError
        try:
            with build_opener(ProxyHandler({})).open(req,timeout=90) as response:value=json.load(response)
        except HTTPError as exc:
            try:detail=json.load(exc).get('error',str(exc))
            except ValueError:detail=str(exc)
            raise ValueError('잡음 제거 실행 실패: '+detail) from exc
        if value.get('status')!='ok':raise ValueError('잡음 제거 실행 실패: '+str(value.get('error','상태 확인 필요')))
        processed=base64.b64decode(value['wav_b64'],validate=True)
        _,before=pcm_wave(audio);_,after=pcm_wave(processed)
        if abs(before-after)>1/16000:raise ValueError('잡음 제거 후 길이가 달라 인식을 중단했습니다.')
        return processed,value['metadata']
    def speech(self,body):
        if not self.audio_lock.acquire(blocking=False):raise ValueError('앞선 음성 처리가 끝난 뒤 말씀해주세요.')
        folder=self.records/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);folder.mkdir()
        record={'status':'started','version':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),
            'capture_metadata':body.get('capture_metadata',{}),'model_called':False,'cart_changed':False}
        started=time.perf_counter()
        try:
            input_source='wav' if body.get('input_source')=='wav' else 'microphone'
            encoded=body.get('wav_b64','')
            if not isinstance(encoded,str) or len(encoded)>1400000:raise ValueError('30초 이내의 음성을 입력해주세요.')
            audio=base64.b64decode(encoded,validate=True);pcm_wave(audio);(folder/'input_16k.wav').write_bytes(audio)
            if body.get('original_b64'):
                original=base64.b64decode(body['original_b64'],validate=True)
                if len(original)>8000000:raise ValueError('원본 음성이 너무 큽니다.')
                (folder/'source.wav').write_bytes(original)
            processed,metadata=self.noise(audio,body.get('noise_mode','off'))
            (folder/'stt_input.wav').write_bytes(processed);record['noise']=metadata
            stt=self.engine.recognize(processed);record['stt']=stt
            if not stt['text']:raise ValueError('음성 인식 결과가 비어 있습니다. 다시 말씀해주세요.')
            session=self.session(body.get('session_id'));before=copy_json(session.state())
            state=session.apply({**body,'text':stt['text']},source='text')
            if state.get('diagnostics'):
                state['diagnostics'].update(input_source=input_source,stt=stt,noise=metadata)
            record.update(status='completed',input_source=input_source,state_before=before,state_after=state,
                model_called=bool(state.get('diagnostics',{}).get('model_called')),cart_changed=before['cart']!=state['cart'])
            return self.enrich({**state,'speech':{'stt':stt,'noise':metadata,'record_dir':str(folder)}})
        except Exception as exc:record.update(status='failed',error=str(exc),traceback=traceback.format_exc());raise
        finally:
            try:record['wall_ms']=round((time.perf_counter()-started)*1000,3);write_json(folder/'result.json',record)
            finally:self.audio_lock.release()


def copy_json(value):return json.loads(json.dumps(value,ensure_ascii=False))


class Handler(BaseHTTPRequestHandler):
    def send(self,status,data,mime='application/json; charset=utf-8'):
        if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False).encode()
        elif isinstance(data,str):data=data.encode()
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        path=urlsplit(self.path).path
        try:
            if path=='/api/integration/info':return self.send(200,self.server.app.info())
            if path=='/api/integration/catalog':return self.send(200,self.server.app.load_catalog())
            if path.startswith('/prompts/'):
                name=path[len('/prompts/'):]
                allowed={v['filename'] for v in self.server.app.prompts.values()}
                if name not in allowed:return self.send(404,{'error':'없는 안내 음성입니다.'})
                return self.send(200,(STATIC/'prompts'/name).read_bytes(),'audio/wav')
            files={'/':'index.html','/adapter.js':'adapter.js','/capture.js':'capture.js','/recorder-worklet.js':'recorder-worklet.js'}
            if path not in files:return self.send(404,{'error':'없는 주소입니다.'})
            p=STATIC/files[path];return self.send(200,p.read_bytes(),('text/html' if p.suffix=='.html' else 'text/javascript')+'; charset=utf-8')
        except Exception as exc:return self.send(503,{'error':str(exc)})
    def do_POST(self):
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''):return self.send(403,{'error':'현재 주문 화면에서 실행해주세요.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=13000000:raise ValueError('요청 크기를 확인해주세요.')
            if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('JSON 요청이 필요합니다.')
            body=json.loads(self.rfile.read(size));app=self.server.app;path=urlsplit(self.path).path
            if path=='/api/integration/session':return self.send(200,app.new_session())
            if path=='/api/integration/speech':return self.send(200,app.speech(body))
            if path=='/api/integration/settings':
                value={k:str(body.get(k,'')).strip() for k in ('spring_base_url','noise_base_url')}
                backend=MenuBackend(value['spring_base_url']);catalog=backend.catalog()
                if value['noise_base_url']:
                    p=urlsplit(value['noise_base_url'])
                    if p.scheme not in ('http','https') or not p.netloc:raise ValueError('잡음 처리 서버 주소를 확인해주세요.')
                write_json(ROOT/'integration.local.json',value)
                app.settings=value;app.backend=backend;app.catalog=catalog
                return self.send(200,{'saved':True,'menu_count':len(catalog),'restart_session_required':True})
            if path in ('/api/integration/action','/api/integration/text'):
                session=app.session(body.get('session_id'))
                state=session.apply(body,source='text' if path.endswith('/text') else 'touch')
                write_json(app.records/('text-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.json'),state)
                return self.send(200,app.enrich(state))
            return self.send(404,{'error':'없는 작업입니다.'})
        except Exception as exc:
            print(traceback.format_exc(),flush=True);return self.send(400,{'error':str(exc)})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8012);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    os.chdir(ROOT)
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.app=App()
    print(VERSION+' / '+str(ROOT));url=f'http://127.0.0.1:{args.port}/';print(url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
