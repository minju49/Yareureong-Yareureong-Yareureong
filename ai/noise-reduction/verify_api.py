"""Smoke test the real packaged API and checkpoint without dataset audio."""
import io

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from server import app


def main():
    t = np.arange(80003) / 16000
    x = (.07*np.sin(2*np.pi*250*t)+np.random.default_rng(8).normal(0,.01,len(t))).astype('float32')
    payload = io.BytesIO()
    sf.write(payload, x, 16000, format='WAV', subtype='FLOAT')
    with TestClient(app) as client:
        assert client.get('/health').json()['default_enabled'] is False
        for state in (None, 'false', 'true'):
            response = client.post('/denoise', files={'file': ('test.wav', payload.getvalue())},
                                   data={} if state is None else {'enabled':state})
            assert response.status_code==200, response.text
            audio,rate=sf.read(io.BytesIO(response.content),dtype='float32')
            assert rate==16000 and audio.shape==x.shape and np.isfinite(audio).all()
            enabled=state=='true'
            assert response.headers['X-Denoise-Applied']==str(enabled).lower()
            assert np.array_equal(audio,x) is (not enabled)
        invalid = client.post('/denoise',files={'file':('invalid.wav',b'invalid')})
        assert invalid.status_code==400
    print('PASS: 기본 OFF, 명시적 OFF/ON, 4초 초과 파형 길이, 잘못된 WAV')


if __name__ == '__main__':
    main()
