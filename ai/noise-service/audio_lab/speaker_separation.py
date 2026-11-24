"""Extract an onset-consistent speech source before optional residual denoising."""
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from zip_denoiser import RATE

ROOT = Path(__file__).resolve().parent
SS_FILE = Path(os.getenv('MOSSFORMER2_SS_FILE', ROOT/'models/mossformer2-ss/last_best_checkpoint.pt'))
SS_URL = ('https://huggingface.co/alibabasglab/MossFormer2_SS_16K/resolve/'
          '407cb030cd66340918ebb6c8cc63b18f8592cdbe/last_best_checkpoint.pt')
SS_HASH = '00a3a48bda492db1e829b85dd443f8f43a43039a3e90f1a24962ea9caf14a11a'
NEW_MODES = ('mossformer2_ss', 'mossformer2_zip', 'mossformer2_moss', 'mossformer2_zip_moss')
SS_MIX = .5


def verified(path):
    from hashlib import file_digest
    if not path.is_file():
        return False
    with path.open('rb') as file:
        return file_digest(file,'sha256').hexdigest() == SS_HASH


class SpeechSeparator:
    def __init__(self):
        import clearvoice
        import yaml
        from clearvoice.models.mossformer2_ss.mossformer2 import MossFormer2_SS_16K

        if not verified(SS_FILE):
            raise FileNotFoundError('MossFormer2 체크포인트를 model_files.py --separation 으로 준비해주세요.')
        config = Path(clearvoice.__file__).parent/'config/inference/MossFormer2_SS_16K.yaml'
        args = SimpleNamespace(**yaml.safe_load(config.read_text(encoding='utf-8')))
        with torch.device('cpu'):
            self.model = MossFormer2_SS_16K(args).model
        data = torch.load(SS_FILE,map_location='cpu',weights_only=True,mmap=True)['model']
        self.model.load_state_dict({k.removeprefix('module.'):v for k,v in data.items()},strict=True)
        self.model.cuda().eval()

    @torch.inference_mode()
    def separate(self,x):
        padded = np.pad(x,(0,(-len(x))%16+32))
        outputs = self.model(torch.from_numpy(padded).cuda()[None,:])
        pair = np.stack([wave[0,:len(x)].float().cpu().numpy() for wave in outputs])
        if pair.shape != (2,len(x)) or not np.isfinite(pair).all():
            raise RuntimeError('화자 분리 출력이 올바르지 않습니다.')
        return pair


def choose_source(x, candidates):
    # The first energetic portion is an input cue, not a verified speaker ID.
    frame = RATE//50
    energy = np.mean(x[:len(x)//frame*frame].reshape(-1,frame)**2,axis=1)
    active = np.flatnonzero(energy >= max(float(energy.max())*.08,1e-8))
    if not active.size:
        return None, {'reason':'no_clear_onset'}
    anchor = slice(int(active[0])*frame,min(int(active[0])*frame+int(.8*RATE),len(x)))
    cue = x[anchor].astype('float64')
    channels = candidates[:,anchor].astype('float64')
    inner = channels @ cue
    channel_norm = np.linalg.norm(channels,axis=1)
    score = np.abs(inner)/np.maximum(channel_norm*np.linalg.norm(cue),1e-12)
    idx = int(np.argmax(score))
    margin = float(score[idx]-score[1-idx])
    info = dict(anchor_scores=score.tolist(),anchor_margin=margin)
    if score[idx] < .65 or margin < .15:
        return None, dict(info,reason='ambiguous_onset')
    opposite = np.linalg.norm(candidates[1-idx])/max(float(np.linalg.norm(x)),1e-12)
    if opposite < .12:
        return None, dict(info,reason='weak_second_output')
    gain = inner[idx]/max(float(channel_norm[idx]**2),1e-12)
    gain = np.copysign(np.clip(abs(gain),.5,2.),gain)
    return (candidates[idx]*gain).astype('float32'),dict(info,reason='onset_consistent_output',source_index=idx)
