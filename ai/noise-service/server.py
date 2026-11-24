"""Apply the team's pinned denoisers to 16 kHz PCM WAV requests."""
from pathlib import Path
import argparse
import base64
import io
import json
import sys
import threading
import time
import traceback
import wave
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'audio_lab'))
ENGINE=None
LOCK=threading.Lock()
GPU_MODES=('off','zipenhancer','mossgan','mossformer2_zip','auto')
CPU_MODES=('off','zipenhancer')
DEVICE='cuda'


def health():
    import importlib.util
    result={'status':'running','modes':CPU_MODES if DEVICE=='cpu' else GPU_MODES,
        'device':DEVICE,'default':'off','engine_loaded':ENGINE is not None,
        'pytorch_installed':importlib.util.find_spec('torch') is not None,
        'zip_weights_present':(ROOT/'audio_lab/models/zipenhancer/pytorch_model.bin').is_file(),
        'mossgan_weights_present':(ROOT/'audio_lab/models/mossformer-gan/last_best_checkpoint.pt').is_file(),
        'separation_weights_present':(ROOT/'audio_lab/models/mossformer2-ss/last_best_checkpoint.pt').is_file()}
    if result['pytorch_installed']:
        import torch
        result.update(torch_version=torch.__version__,cuda_available=torch.cuda.is_available())
    return result


def process(body):
    global ENGINE
    encoded=body.get('wav_b64','')
    if not isinstance(encoded,str) or len(encoded)>1400000:raise ValueError('30초 이내 WAV가 필요합니다.')
    data=base64.b64decode(encoded,validate=True);mode=body.get('mode','off')
    if mode not in (CPU_MODES if DEVICE=='cpu' else GPU_MODES):
        raise ValueError('이 잡음 서버의 지원 모드를 확인해주세요. CPU 서버는 ZipEnhancer를 실행합니다.')
    with wave.open(io.BytesIO(data),'rb') as f:
        if (f.getnchannels(),f.getframerate(),f.getsampwidth())!=(1,16000,2):raise ValueError('16kHz 모노 PCM16 WAV가 필요합니다.')
        frames=f.getnframes()
        if not 3200<=frames<=480000:raise ValueError('0.2~30초의 WAV가 필요합니다.')
        pcm=f.readframes(frames)
        if len(pcm)!=frames*2:raise ValueError('WAV 끝부분이 누락됐습니다.')
    if mode=='off':return {'status':'ok','wav_b64':encoded,'metadata':{'requested':'off','selected':'off','applied':False,'processing_ms':0}}
    with LOCK:
        import numpy as np
        cold=ENGINE is None;start=time.perf_counter()
        if cold:
            if DEVICE=='cpu':
                import torch
                from zip_denoiser import ZipDenoiser
                torch.set_num_threads(2)
                ENGINE=ZipDenoiser(device='cpu')
            else:
                from ensemble import NoiseEnsemble
                ENGINE=NoiseEnsemble()
        load_ms=(time.perf_counter()-start)*1000 if cold else 0
        x=np.frombuffer(pcm,dtype='<i2').astype('float32')/32768.
        tick=time.perf_counter()
        if DEVICE=='cpu':
            y,selected,details=ENGINE.process(x),'zipenhancer',{}
        else:
            y,selected,details=ENGINE.process(x,mode)
        elapsed=(time.perf_counter()-tick)*1000
        if y.shape!=x.shape or not np.isfinite(y).all():raise ValueError('처리 후 음성 길이·값이 올바르지 않습니다.')
        pcm=np.clip(np.rint(y*32768),-32768,32767).astype('<i2').tobytes();target=io.BytesIO()
        with wave.open(target,'wb') as f:f.setparams((1,2,16000,frames,'NONE','not compressed'));f.writeframes(pcm)
        return {'status':'ok','wav_b64':base64.b64encode(target.getvalue()).decode(),
            'metadata':{'requested':mode,'selected':selected,'applied':selected!='off','processing_ms':round(elapsed,3),
                'engine_init_ms':round(load_ms,3),'timing_note':'첫 경로 요청의 처리 시간에는 그 경로의 지연 로딩이 포함될 수 있습니다.',
                'device':DEVICE,'decision':details,'sample_rate_hz':16000,'frames':frames}}


class Handler(BaseHTTPRequestHandler):
    def send(self,status,body):
        raw=json.dumps(body,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path!='/health':return self.send(404,{'error':'not found'})
        try:return self.send(200,health())
        except Exception as exc:return self.send(500,{'status':'failed','error':str(exc)})
    def do_POST(self):
        if self.path!='/api/process':return self.send(404,{'error':'not found'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<1500000:raise ValueError('요청 크기를 확인해주세요.')
            return self.send(200,process(json.loads(self.rfile.read(size))))
        except Exception as exc:
            print(traceback.format_exc(),flush=True);return self.send(503,{'status':'failed','error':str(exc),'silent_fallback_used':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='0.0.0.0');parser.add_argument('--port',type=int,default=8058)
    parser.add_argument('--device',choices=('cpu','cuda'),default='cuda');args=parser.parse_args()
    DEVICE=args.device
    print(f'봄카페 잡음 처리 서버 · {DEVICE} · {args.host}:{args.port}',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
