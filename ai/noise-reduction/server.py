"""Local WAV comparison service. Opt in to noise reduction per request."""
import io
import time
from contextlib import asynccontextmanager
from math import gcd
from threading import Lock

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from scipy.signal import resample_poly
from starlette.concurrency import run_in_threadpool

from zip_denoiser import RATE, STRENGTH, ZipDenoiser


@asynccontextmanager
async def lifespan(app):
    app.state.denoiser = await run_in_threadpool(ZipDenoiser)
    app.state.lock = Lock()
    yield


app = FastAPI(title='ZipEnhancer 잡음 제거 비교', lifespan=lifespan)


@app.get('/health')
def health():
    return dict(model='zipenhancer', device='cuda', sample_rate=RATE, strength=STRENGTH, default_enabled=False)


def process_wav(blob, enabled):
    started = time.perf_counter()
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
    preprocessing = time.perf_counter() - started
    inference = 0.
    if enabled:
        with app.state.lock:
            tick = time.perf_counter()
            x = app.state.denoiser.process(x)
            inference = time.perf_counter() - tick
    result = io.BytesIO()
    sf.write(result, x, RATE, format='WAV', subtype='FLOAT')
    return Response(result.getvalue(), media_type='audio/wav', headers={
        'X-Denoise-Applied': str(enabled).lower(), 'X-Model': 'zipenhancer',
        'X-Strength': str(STRENGTH if enabled else 0), 'X-Sample-Rate': str(RATE),
        'X-Preprocessing-Seconds': f'{preprocessing:.6f}', 'X-Inference-Seconds': f'{inference:.6f}',
        'Content-Disposition': 'attachment; filename="processed.wav"',
    })


@app.post('/denoise')
async def denoise(file: UploadFile = File(...), enabled: bool = Form(False)):
    try:
        limit = 25 * 1024 * 1024
        blob = await file.read(limit + 1)
        if len(blob) > limit:
            raise HTTPException(413, 'WAV 파일은 25MiB 이하여야 합니다.')
        return await run_in_threadpool(process_wav, blob, enabled)
    finally:
        await file.close()
