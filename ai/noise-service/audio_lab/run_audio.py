"""Run the added waveform stage before the existing school text experiment."""
import argparse
import base64
import json
from math import gcd
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from ensemble import SERVICE_MODES, NoiseEnsemble
from zip_denoiser import RATE

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_MODES = ('off','zipenhancer','mossgan','mossformer2_zip')


def input_wave(path):
    with sf.SoundFile(path) as source:
        if source.format not in ('WAV','WAVEX') or not 0 < source.frames <= 30*source.samplerate:
            raise ValueError('30초 이내의 비어 있지 않은 WAV 파일을 골라주세요.')
        audio = source.read(dtype='float32',always_2d=True).mean(axis=1)
        rate = source.samplerate
    if rate != RATE:
        div = gcd(rate,RATE)
        audio = resample_poly(audio,RATE//div,rate//div).astype('float32')
    if not np.isfinite(audio).all():
        raise ValueError('음성 파일에 비정상 샘플이 있습니다.')
    return audio


def transcribe(waves):
    model = Path(os.getenv('BOM_STT_MODEL_DIR', HERE/'models/sensevoice')).resolve()
    if not all((model/name).is_file() for name in ('model.int8.onnx','tokens.txt')):
        raise FileNotFoundError('SenseVoice 파일이 없습니다. 5_SetupAudio.cmd를 실행해주세요.')
    python = os.getenv('BOM_STT_PYTHON',sys.executable)
    payload = json.dumps([base64.b64encode(w.astype('<f4').tobytes()).decode('ascii') for w in waves])
    result = subprocess.run([python,'-X','utf8',str(HERE/'stt_worker.py'),str(model)],cwd=model.parent,
                            input=payload,capture_output=True,encoding='utf-8',timeout=120)
    if result.returncode:
        raise RuntimeError('SenseVoice 실행 실패\n'+result.stderr[-2000:])
    replies = json.loads(result.stdout)
    if len(replies)!=len(waves):
        raise RuntimeError('SenseVoice 응답 개수가 맞지 않습니다.')
    return replies


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input',type=Path,nargs='?')
    parser.add_argument('--mode',action='append',choices=SERVICE_MODES)
    parser.add_argument('--school',action='store_true')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'records/audio')
    args=parser.parse_args()
    sample = next(ROOT.glob('추가_집실험기록/synthetic/*/wav/A01-base.wav'),None)
    path = args.input or sample
    if path is None or not path.is_file():
        parser.error('WAV 파일을 지정해주세요.')
    modes = list(dict.fromkeys(args.mode or (('zipenhancer',) if args.school else DEFAULT_MODES)))
    x = input_wave(path)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='audio-',dir=args.output_dir))
    status = dict(sample_rate=RATE,frames=len(x),input=path.name,provided_sample=args.input is None,results=[])
    summary = output/'summary.json'
    sys.path.insert(0,str(ROOT/'review_lab'))
    from review import review_transcript
    try:
        engine=NoiseEnsemble() if any(m!='off' for m in modes) else None
        waves=[]
        for mode in modes:
            start=time.perf_counter()
            y, selected, decision=engine.process(x,mode) if mode!='off' else (x,'off',{})
            if y.shape!=x.shape or not np.isfinite(y).all():
                raise ValueError(f'{mode} 출력 파형이 올바르지 않습니다.')
            elapsed=time.perf_counter()-start
            sf.write(output/(mode+'.wav'),y,RATE,subtype='FLOAT')
            waves.append(y)
            status['results'].append(dict(mode=mode,selected=selected,decision=decision,
                                          processing_seconds=elapsed,file=mode+'.wav'))
        for record,reply in zip(status['results'],transcribe(waves)):
            record['stt']=reply
            record['review']=review_transcript(reply['text'],{})
            print(f'[{record["mode"]}] {record["selected"]} | {reply["text"]}',flush=True)
        status['local_status']='ok'
        if args.school:
            from run_school import configure
            from run_review import make_record
            configure()
            for record in status['results']:
                text=record['stt']['text'].strip()
                record['school_ok']=bool(text) and make_record(text,'none','school',output/record['mode'],
                                                               use_qwen=True,input_kind='audio_after_denoise')
            return 0 if all(item['school_ok'] for item in status['results']) else 1
        return 0
    except Exception as exc:
        status['error']=str(exc)
        print(str(exc),file=sys.stderr)
        return 1
    finally:
        summary.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'결과 폴더 {output}',flush=True)


if __name__=='__main__':
    raise SystemExit(main())
