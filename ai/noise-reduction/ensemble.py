"""Combine validated pretrained checkpoints and apply an input-only policy."""

import json
from hashlib import file_digest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from zip_denoiser import RATE, STRENGTH, ZipDenoiser, enhance_in_windows

ROOT = Path(__file__).resolve().parent
MOSS_FILE = ROOT / 'models/mossformer-gan/last_best_checkpoint.pt'
MOSS_URL = ('https://huggingface.co/alibabasglab/MossFormerGAN_SE_16K/resolve/'
            'dcb1b20e1e44d435090072ab9b223c792ea1f624/last_best_checkpoint.pt')
MOSS_HASH = '04bf00db575389e1ea8b1fcca48d9efcf073e50ad170e6dd5230df3bac98be27'
STEP = 1 - np.sqrt(.75)
MODES = ('off', 'zipenhancer', 'mossgan', 'parallel', 'moss_to_zip', 'zip_to_moss', 'auto')


def moss_verified(path):
    if not path.is_file():
        return False
    with path.open('rb') as file:
        return file_digest(file, 'sha256').hexdigest() == MOSS_HASH


def blend(original, estimate, amount):
    return ((1 - amount)*original + amount*estimate).astype('float32')


class MossDenoiser:
    def __init__(self):
        import clearvoice
        import yaml
        from clearvoice.models.mossformer_gan_se.generator import MossFormerGAN_SE_16K
        from clearvoice.utils.decode import decode_one_audio_mossformergan_se_16k

        if not moss_verified(MOSS_FILE):
            raise ValueError('MossFormerGAN 파일을 model_files.py --ensemble로 준비해주세요.')
        config = Path(clearvoice.__file__).parent/'config/inference/MossFormerGAN_SE_16K.yaml'
        self.args = SimpleNamespace(**yaml.safe_load(config.read_text(encoding='utf-8')))
        self.model = MossFormerGAN_SE_16K(self.args).model
        weights = torch.load(MOSS_FILE, map_location='cpu', weights_only=True)
        weights = weights.get('model', weights)
        self.model.load_state_dict({key.removeprefix('module.'): value for key,value in weights.items()}, strict=True)
        self.model.cuda().eval()
        self.decode = decode_one_audio_mossformergan_se_16k

    @torch.inference_mode()
    def _window(self, x):
        if not np.any(x):
            return np.zeros_like(x)
        padded = np.pad(x, (0, (-len(x)) % 100 + 400))
        return np.asarray(self.decode(self.model,'cuda',padded[None,:],self.args)[:len(x)], dtype='float32')

    def enhance(self, x):
        return enhance_in_windows(x, self._window)


def auto_route(x):
    if not np.any(x):
        return 'off', {'reason':'digital_silence'}
    if not 2*RATE <= len(x) <= 8*RATE:
        return 'zipenhancer', {'reason':'outside_evaluated_duration'}
    frames = x[:len(x)//512*512].reshape(-1,512).astype('float64')
    lo,hi = np.quantile(np.mean(frames**2,axis=1), [.2,.8])
    ratio = float(np.float32((lo+1e-12)/(hi+1e-12)))
    node = json.loads((ROOT/'auto-policy.json').read_text(encoding='utf-8'))['tree']
    while 'mode' not in node:
        if node['feature'] != 1:
            raise ValueError('지원하지 않는 자동 선택 특징입니다.')
        node = node['left' if ratio <= node['threshold'] else 'right']
    return node['mode'], {'reason':'experimental_energy_ratio', 'energy_ratio':ratio}


class NoiseEnsemble:
    def __init__(self):
        self.zip = ZipDenoiser()
        self.moss = None

    def process(self, x, mode):
        selected, info = auto_route(x) if mode == 'auto' else (mode, {})
        if selected == 'off':
            return x, selected, info
        if selected == 'zipenhancer':
            return self.zip.process(x), selected, info
        if not MOSS_FILE.is_file():
            raise FileNotFoundError('조합 모델 파일을 먼저 준비해주세요. python model_files.py --ensemble')
        # Match the CUDA math policy used for the offline two-model comparison.
        previous = torch.backends.cuda.matmul.allow_tf32, torch.backends.cudnn.allow_tf32, torch.backends.cudnn.benchmark
        torch.backends.cuda.matmul.allow_tf32 = torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = False
        try:
            if self.moss is None:
                self.moss = MossDenoiser()
            if selected == 'mossgan':
                y = blend(x, self.moss.enhance(x), STRENGTH)
            elif selected == 'parallel':
                y = .75*x + .125*self.moss.enhance(x) + .125*self.zip.enhance(x)
            elif selected in ('moss_to_zip','zip_to_moss'):
                first,second = (self.moss,self.zip) if selected=='moss_to_zip' else (self.zip,self.moss)
                intermediate = blend(x,first.enhance(x),STEP)
                y = blend(intermediate,second.enhance(intermediate),STEP)
            else:
                raise ValueError('지원하지 않는 처리 모드입니다.')
        finally:
            (torch.backends.cuda.matmul.allow_tf32, torch.backends.cudnn.allow_tf32,
             torch.backends.cudnn.benchmark) = previous
        if y.shape != x.shape or not np.isfinite(y).all():
            raise RuntimeError('조합 결과의 형식이 올바르지 않습니다.')
        return y.astype('float32'), selected, info
