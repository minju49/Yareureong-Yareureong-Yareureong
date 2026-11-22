"""ZipEnhancer 16 kHz with the framing and blend verified in the kiosk study."""
import json

import numpy as np
import torch

from model_files import MODEL_DIR, verify

RATE = 16000
STRENGTH = .25


class ZipDenoiser:
    def __init__(self):
        from modelscope.models.audio.ans.zipenhancer import ZipenhancerDecorator, mag_pha_istft, mag_pha_stft

        verify()
        if not torch.cuda.is_available():
            raise RuntimeError('이 평가용 모델은 NVIDIA CUDA 환경이 필요합니다.')
        config = json.loads((MODEL_DIR / 'configuration.json').read_text(encoding='utf-8'))
        self.model = ZipenhancerDecorator(str(MODEL_DIR), **config['model']).cuda().eval()
        self.stft, self.istft = mag_pha_stft, mag_pha_istft

    @torch.inference_mode()
    def _window(self, x):
        if not np.any(x):
            return np.zeros_like(x)
        wave = torch.from_numpy(x).cuda()[None, :]
        scale = torch.sqrt(len(x) / torch.sum(wave ** 2))
        wave = torch.nn.functional.pad(wave * scale, (0, 400))
        mag, phase, _ = self.stft(wave, 400, 100, 400, compress_factor=.3, center=True)
        amp, phase, *_ = self.model.model(mag, phase)
        y = self.istft(amp, phase, 400, 100, 400, compress_factor=.3, center=True) / scale
        return y.squeeze(0).float().cpu().numpy()[:len(x)]

    def process(self, x):
        window, hop = 4 * RATE, 3 * RATE
        if len(x) <= window:
            y = self._window(x)
        else:
            weights = np.ones(window, np.float64)
            overlap = window - hop
            ramp = np.linspace(0, 1, overlap + 2)[1:-1]
            weights[:overlap], weights[-overlap:] = ramp, ramp[::-1]
            summed = np.zeros(len(x), np.float64)
            total = np.zeros(len(x), np.float64)
            for start in range(0, len(x), hop):
                count = min(window, len(x) - start)
                clip = np.pad(x[start:start+count], (0, window - count))
                region = slice(start, start+count)
                summed[region] += self._window(clip)[:count] * weights[:count]
                total[region] += weights[:count]
            y = (summed / total).astype('float32')
        if y.shape != x.shape or not np.isfinite(y).all():
            raise RuntimeError('모델 출력 길이 또는 샘플 값이 올바르지 않습니다.')
        return ((1 - STRENGTH) * x + STRENGTH * y).astype('float32')
