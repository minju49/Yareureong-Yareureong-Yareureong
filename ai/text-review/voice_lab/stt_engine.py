"""Selected local CPU ASR; no browser recognition and no model downloads."""
from __future__ import annotations
import hashlib
import io
import math
import os
from pathlib import Path
import threading
import time
import wave

MODEL_SHA256='c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51'
CHECKPOINT='csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17@2365baeacb507f821a0c8120fcee3d484dba7a07'


def pcm_wave(data):
    if not isinstance(data,bytes) or len(data)>1_000_000:
        raise ValueError('처리용 WAV는 30초 이내의 16kHz 모노 PCM16이어야 합니다.')
    try:
        with wave.open(io.BytesIO(data),'rb') as audio:
            rate,channels,width,frames=audio.getframerate(),audio.getnchannels(),audio.getsampwidth(),audio.getnframes()
            if (rate,channels,width,audio.getcomptype())!=(16000,1,2,'NONE'):
                raise ValueError('처리용 WAV가 16kHz·모노·PCM16이 아닙니다. 화면에서 파일을 다시 선택해주세요.')
            if not 3200<=frames<=480000:raise ValueError('실제로 저장된 음성은 0.2~30초여야 합니다.')
            pcm=audio.readframes(frames)
            if len(pcm)!=frames*2:raise ValueError('WAV 끝부분이 누락되었습니다. 다시 녹음해주세요.')
    except (wave.Error,EOFError) as exc:
        raise ValueError('정상적인 PCM WAV를 읽지 못했습니다: '+str(exc)) from exc
    return pcm,frames/16000


class SenseVoice:
    def __init__(self,root,threads=2):
        self.root=Path(root).resolve();self.threads=threads;self.recognizer=None
        self.error=None;self.load_ms=None;self.last_success=None;self.lock=threading.Lock()
        self.model=self.root/'models'/'sensevoice'/'model.int8.onnx'
        self.tokens=self.model.with_name('tokens.txt')

    def status(self):
        return {'model_id':'iic/SenseVoiceSmall','checkpoint':CHECKPOINT,
            'implementation':'sherpa-onnx 1.12.40 / embedded ONNX Runtime CPU',
            'precision':'int8','device':'cpu','threads':self.threads,'sample_rate_hz':16000,
            'language':'ko','use_itn':False,'files_present':self.model.is_file() and self.tokens.is_file(),
            'loaded':self.recognizer is not None,'actual_recognition_verified':self.last_success is not None,
            'initial_load_ms':self.load_ms,'error':self.error,'last_success':self.last_success}

    def load(self):
        if self.recognizer is not None:return
        started=time.perf_counter()
        try:
            if not self.model.is_file() or not self.tokens.is_file():
                raise ValueError('동봉한 models/sensevoice 폴더의 모델·토큰 파일이 없습니다. ZIP 전체를 압축 해제해주세요.')
            with self.model.open('rb') as handle:actual=hashlib.file_digest(handle,'sha256').hexdigest()
            if actual!=MODEL_SHA256:raise ValueError('동봉 모델의 해시가 다릅니다. 전송·압축 해제 상태를 확인해주세요.')
            import numpy
            import sherpa_onnx
            # Native model loader receives paths relative to the current project,
            # including when the Windows parent folder has Korean or spaces.
            self.recognizer=sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=os.path.relpath(self.model),tokens=os.path.relpath(self.tokens),
                language='ko',use_itn=False,num_threads=self.threads,sample_rate=16000,provider='cpu')
            self.load_ms=round((time.perf_counter()-started)*1000,3)
            self.error=None
        except Exception as exc:
            self.error=str(exc)
            raise RuntimeError('SenseVoice를 실행하지 못했습니다. '+str(exc)+
                ' DLL/애플리케이션 제어 정책 오류라면 학교 담당자에게 해당 오류와 진단기록을 보여주세요.') from exc

    def recognize(self,data):
        pcm,duration=pcm_wave(data)
        with self.lock:
            wall=time.perf_counter();cold=self.recognizer is None;self.load()
            import numpy as np
            samples=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768.0
            started=time.perf_counter();stream=self.recognizer.create_stream()
            stream.accept_waveform(16000,samples);self.recognizer.decode_stream(stream)
            text=stream.result.text.strip()
            inference_ms=round((time.perf_counter()-started)*1000,3)
            rms=float(np.sqrt(np.mean(samples.astype(np.float64)**2)))
            result={'text':text,'duration_s':duration,'inference_ms':inference_ms,
                'load_ms':self.load_ms if cold else 0,'cold_start':cold,
                'total_ms':round((time.perf_counter()-wall)*1000,3),
                'rms_dbfs':round(20*math.log10(rms),2) if rms else None,
                'peak':float(np.max(np.abs(samples))),'zero_samples':int(np.count_nonzero(samples==0)),
                'model_id':'iic/SenseVoiceSmall','checkpoint':CHECKPOINT,'model_sha256':MODEL_SHA256,
                'precision':'int8','device':'cpu','language':'ko','use_itn':False,'sample_rate_hz':16000}
            self.last_success={'text':text,'duration_s':duration,'synthetic_smoke':False}
            return result
