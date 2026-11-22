"""Local WAV comparison service. Opt in to noise reduction per request."""
import io
import base64
import json
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from math import gcd
from pathlib import Path
from threading import Lock

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from scipy.signal import resample_poly
from starlette.concurrency import run_in_threadpool

from ensemble import MODES, MOSS_FILE, ROOT, NoiseEnsemble
from zip_denoiser import RATE, STRENGTH


@asynccontextmanager
async def lifespan(app):
    app.state.denoiser = await run_in_threadpool(NoiseEnsemble)
    app.state.lock = Lock()
    yield


app = FastAPI(title='봄카페 잡음 제거 조합 비교', lifespan=lifespan)


@app.get('/')
def demo():
    return FileResponse(ROOT/'demo.html')


@app.get('/health')
def health():
    return dict(model='zipenhancer', device='cuda', sample_rate=RATE, strength=STRENGTH, default_enabled=False,
                modes=MODES, ensemble_weights_present=MOSS_FILE.is_file(), stt_configured=bool(os.getenv('ZIP_STT_MODEL_DIR')))


def decode(blob):
    try:
        with sf.SoundFile(io.BytesIO(blob)) as source:
            if source.format not in ('WAV','WAVEX'):
                raise HTTPException(415, 'WAV 파일을 입력해주세요.')
            if source.frames > source.samplerate * 60:
                raise HTTPException(413, '최대 60초까지 처리할 수 있습니다.')
            x = source.read(dtype='float32', always_2d=True).mean(axis=1)
            rate = source.samplerate
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise HTTPException(400, 'WAV 파일을 읽을 수 없습니다.') from exc
    if not len(x) or not np.isfinite(x).all():
        raise HTTPException(400, '비어 있거나 유효하지 않은 음성입니다.')
    if rate != RATE:
        divisor = gcd(rate, RATE)
        x = resample_poly(x, RATE//divisor, rate//divisor).astype('float32')
    return x


def process(x, mode):
    if mode not in MODES:
        raise HTTPException(422, '지원하지 않는 모드입니다.')
    if mode == 'off':
        return x, 'off', {}, 0.
    try:
        with app.state.lock:
            tick = time.perf_counter()
            y, selected, details = app.state.denoiser.process(x, mode)
            return y, selected, details, time.perf_counter() - tick
    except (FileNotFoundError, ImportError) as exc:
        raise HTTPException(503, f'조합 모델의 설치 상태를 확인해주세요. {exc}') from exc


def wav(x):
    result = io.BytesIO()
    sf.write(result, x, RATE, format='WAV', subtype='FLOAT')
    return result.getvalue()


def process_wav(blob, mode):
    started = time.perf_counter()
    x = decode(blob)
    preprocessing = time.perf_counter() - started
    y, selected, _, inference = process(x, mode)
    return Response(wav(y), media_type='audio/wav', headers={
        'X-Denoise-Applied': str(selected != 'off').lower(), 'X-Model': selected if selected != 'off' else 'zipenhancer',
        'X-Mode': selected, 'X-Strength': str(STRENGTH if selected != 'off' else 0), 'X-Sample-Rate': str(RATE),
        'X-Preprocessing-Seconds': f'{preprocessing:.6f}', 'X-Inference-Seconds': f'{inference:.6f}',
        'Content-Disposition': 'attachment; filename="processed.wav"',
    })


async def read_upload(file):
    try:
        limit = 25 * 1024 * 1024
        blob = await file.read(limit + 1)
        if len(blob) > limit:
            raise HTTPException(413, 'WAV 파일은 25MiB 이하여야 합니다.')
        return blob
    finally:
        await file.close()


@app.post('/denoise')
async def denoise(file: UploadFile = File(...), enabled: bool = Form(False), mode: str | None = Form(None)):
    blob = await read_upload(file)
    return await run_in_threadpool(process_wav, blob, ('zipenhancer' if enabled else 'off') if mode is None else mode)


def transcripts(x, y):
    model_dir = os.getenv('ZIP_STT_MODEL_DIR')
    if not model_dir:
        return None
    python = os.getenv('ZIP_STT_PYTHON', sys.executable)
    directory = Path(model_dir).resolve()
    payload = json.dumps([base64.b64encode(a.astype('<f4').tobytes()).decode('ascii') for a in (x,y)])
    try:
        result = subprocess.run([python,'-X','utf8',str(ROOT/'stt_worker.py'),str(directory)],
                                cwd=directory.parent, input=payload, capture_output=True, encoding='utf-8', timeout=60, check=True)
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(503, 'SenseVoice를 실행할 수 없습니다. 모델 폴더와 Python 환경을 확인해주세요.') from exc


def compare_wav(blob, mode):
    x = decode(blob)
    y, selected, details, elapsed = process(x, mode)
    text = transcripts(x,y)
    return dict(mode=mode, selected=selected, decision=details, processing_seconds=elapsed, sample_rate=RATE,
                off_wav=base64.b64encode(wav(x)).decode('ascii'), processed_wav=base64.b64encode(wav(y)).decode('ascii'), stt=text)


@app.post('/compare')
async def compare(file: UploadFile = File(...), mode: str = Form('off')):
    blob = await read_upload(file)
    return await run_in_threadpool(compare_wav, blob, mode)
