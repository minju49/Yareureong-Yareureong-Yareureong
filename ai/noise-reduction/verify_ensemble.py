"""Exercise real model combinations, selection, and paired audio responses."""
import base64
import io
import os

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from ensemble import MODES
from server import app, wav


def main():
    t = np.arange(72000) / 16000
    x = (.07*np.sin(2*np.pi*250*t) + np.random.default_rng(8).normal(0,.01,len(t))).astype('float32')
    payload = {'file': ('test.wav', wav(x))}
    outputs = {}
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        for mode in MODES:
            response = client.post('/denoise',files=payload,data={'mode':mode})
            assert response.status_code==200,response.text
            y,rate=sf.read(io.BytesIO(response.content),dtype='float32')
            assert rate==16000 and y.shape==x.shape and np.isfinite(y).all()
            assert np.array_equal(y,x)==(mode=='off')
            outputs[mode]=(y,response.headers['X-Mode'])
            print(f'{mode}: {response.headers["X-Mode"]}, {len(y)} frames',flush=True)
        for mode in ('parallel','moss_to_zip','zip_to_moss'):
            assert not np.array_equal(outputs[mode][0],outputs['zipenhancer'][0])
            assert not np.array_equal(outputs[mode][0],outputs['mossgan'][0])
        automatic,selected=outputs['auto']
        assert selected in ('zipenhancer','moss_to_zip','zip_to_moss')
        np.testing.assert_array_equal(automatic,outputs[selected][0])
        pair=client.post('/compare',files=payload,data={'mode':'parallel'})
        assert pair.status_code==200,pair.text
        data=pair.json()
        assert data['selected']=='parallel' and data['processing_seconds']>0
        a,_=sf.read(io.BytesIO(base64.b64decode(data['off_wav'])),dtype='float32')
        b,_=sf.read(io.BytesIO(base64.b64decode(data['processed_wav'])),dtype='float32')
        np.testing.assert_array_equal(a,x)
        np.testing.assert_array_equal(b,outputs['parallel'][0])
        if os.getenv('ZIP_STT_MODEL_DIR'):
            assert [type(r['text']) for r in data['stt']]==[str,str]
        assert client.post('/denoise', files=payload,data={'mode':'invalid'}).status_code==422
    print('PASS: 실제 GPU 조합 세 가지, AUTO 경로 일치, 비교 화면 API')


if __name__=='__main__':
    main()
