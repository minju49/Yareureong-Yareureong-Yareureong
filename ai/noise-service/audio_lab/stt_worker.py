"""Optional two-channel comparison using the same SenseVoiceSmall settings."""
import base64
import json
import sys
import time
from pathlib import Path

import numpy as np
from sherpa_onnx import OfflineRecognizer


def main():
    directory = Path(sys.argv[1]).name
    model = OfflineRecognizer.from_sense_voice(
        model=f'{directory}/model.int8.onnx', tokens=f'{directory}/tokens.txt',
        language='ko', use_itn=False, num_threads=4, sample_rate=16000, provider='cpu',
    )
    outputs = []
    for encoded in json.load(sys.stdin):
        samples = np.frombuffer(base64.b64decode(encoded), dtype='<f4')
        start = time.perf_counter()
        stream = model.create_stream()
        stream.accept_waveform(16000, samples)
        model.decode_stream(stream)
        outputs.append(dict(text=stream.result.text.strip(), seconds=time.perf_counter()-start))
    print(json.dumps(outputs, ensure_ascii=True))


if __name__ == '__main__':
    main()
