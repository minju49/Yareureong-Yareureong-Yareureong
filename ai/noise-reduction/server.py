"""Local WAV comparison service. Opt in to noise reduction per request."""
import io
import base64
import asyncio
import json
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager, suppress
from math import gcd
from pathlib import Path
from threading import Lock

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from scipy.signal import resample_poly
from starlette.concurrency import run_in_threadpool

from ensemble import MODES, MOSS_FILE, ROOT, NoiseEnsemble
from order_speaker import CUE, OrderVoice
from order_speaker_models import ECAPA_DIR, SS_FILE
from zip_denoiser import RATE, STRENGTH


@asynccontextmanager
async def lifespan(app):
    app.state.denoiser = await run_in_threadpool(NoiseEnsemble)
    app.state.lock = Lock()
    app.state.order_voice = OrderVoice()
    cleanup = asyncio.create_task(expire_order_sessions())
    try:
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup


def prune_order_sessions():
    with app.state.lock:
        app.state.order_voice.prune()


async def expire_order_sessions():
    while True:
        await asyncio.sleep(10)
        await run_in_threadpool(prune_order_sessions)


app = FastAPI(title='봄카페 잡음 제거 조합 비교', lifespan=lifespan)
SITE_ROOT = ROOT.parent.parent
app.mount('/kiosk/assets', StaticFiles(directory=SITE_ROOT/'assets'), name='kiosk-assets')


@app.get('/kiosk', include_in_schema=False)
def kiosk_redirect():
    return RedirectResponse('/kiosk/')


@app.get('/kiosk/', include_in_schema=False)
def kiosk():
    return FileResponse(SITE_ROOT/'index.html')



@app.get('/')
def demo():
    return FileResponse(ROOT/'demo.html')


@app.get('/health')
def health():
    return dict(model='zipenhancer', device='cuda', sample_rate=RATE, strength=STRENGTH, default_enabled=False,
                modes=MODES, ensemble_weights_present=MOSS_FILE.is_file(), stt_configured=bool(os.getenv('ZIP_STT_MODEL_DIR')),
                order_speaker_configured=bool(os.getenv('ZIP_STT_MODEL_DIR')) and SS_FILE.is_file() and
                all((ECAPA_DIR/name).is_file() for name in ('hyperparams.yaml','embedding_model.ckpt')), order_cue=CUE)


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


def transcripts(*waves):
    model_dir = os.getenv('ZIP_STT_MODEL_DIR')
    if not model_dir:
        return None
    python = os.getenv('ZIP_STT_PYTHON', sys.executable)
    directory = Path(model_dir).resolve()
    payload = json.dumps([base64.b64encode(a.astype('<f4').tobytes()).decode('ascii') for a in waves])
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


def recognize_speech(blob, mode, session=None):
    if not os.getenv('ZIP_STT_MODEL_DIR'):
        raise HTTPException(503, '음성 인식 모델 폴더를 지정한 뒤 서버를 다시 실행해주세요.')
    x = decode(blob)
    if mode=='order_speaker':
        return recognize_order_speaker(x,session)
    y, selected, details, elapsed = process(x, mode)
    # Only the waveform selected by the kiosk setting is sent to SenseVoice.
    recognition, = transcripts(y)
    return dict(mode=mode, selected=selected, decision=details, processing_seconds=elapsed,
                text=recognition['text'], stt_seconds=recognition['seconds'])


def recognize_order_speaker(x, session):
    try:
        with app.state.lock:
            started = time.perf_counter()
            result = app.state.order_voice.transcribe(x,session,transcripts)
            elapsed = time.perf_counter()-started
    except KeyError as error:
        raise HTTPException(409,'음성 주문 세션이 끝났어요. “주문할게요”로 다시 시작해 주세요.') from error
    except (ImportError,RuntimeError,OSError) as error:
        raise HTTPException(503,'화자 추적 모델을 준비하거나 실행할 수 없어요. 설치 안내를 확인해 주세요.') from error
    return dict(result,selected='order_speaker',processing_seconds=elapsed)


@app.post('/kiosk/api/speech')
async def speech(file: UploadFile = File(...), mode: str = Form('off'), session: str | None = Form(None,max_length=64)):
    blob = await read_upload(file)
    return await run_in_threadpool(recognize_speech, blob, mode, session)


class OrderVoiceToken(BaseModel):
    token: str = Field(min_length=1,max_length=64)


@app.post('/kiosk/api/order-voice/confirm')
def confirm_order_voice(body: OrderVoiceToken):
    try:
        with app.state.lock:
            ready = app.state.order_voice.confirm(body.token)
    except KeyError as error:
        raise HTTPException(409,'확인 시간이 끝났어요. 첫 주문을 다시 말해 주세요.') from error
    except (ImportError,RuntimeError,OSError) as error:
        raise HTTPException(503,'화자 추적 모델을 실행할 수 없어요. 설치 안내를 확인해 주세요.') from error
    if not ready:
        raise HTTPException(422,'목소리를 비교하기에 첫 음성이 짧거나 작아요. 다시 말해 주세요.')
    return {'session':body.token}


@app.post('/kiosk/api/order-voice/end',status_code=204)
def end_order_voice(body: OrderVoiceToken):
    with app.state.lock:
        app.state.order_voice.discard(body.token)
    return Response(status_code=204)
