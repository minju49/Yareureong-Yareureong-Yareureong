"""Local order cue and in-memory per-order speaker state."""
import re
import secrets
import sys
import time
from types import SimpleNamespace

import numpy as np
import torch

from order_speaker_models import ECAPA_DIR, SS_FILE, require_weight
from session_speaker import SessionSpeaker
from zip_denoiser import RATE

CUE = '주문할게요'
CUE_PREFIX = re.compile(r'^\s*주\s*문\s*할\s*[게께]\s*요[\s,.!?…。~]*')
PENDING_SECONDS = 45
ACTIVE_SECONDS = 300


class MossFormer:
    def __init__(self):
        from pathlib import Path
        import clearvoice
        import yaml
        from clearvoice.models.mossformer2_ss.mossformer2 import MossFormer2_SS_16K

        require_weight(SS_FILE)
        args_file = Path(clearvoice.__file__).parent/'config/inference/MossFormer2_SS_16K.yaml'
        args = SimpleNamespace(**yaml.safe_load(args_file.read_text(encoding='utf-8')))
        self.model = MossFormer2_SS_16K(args).model
        weights = torch.load(SS_FILE,map_location='cpu',weights_only=True,mmap=True)['model']
        self.model.load_state_dict({k.removeprefix('module.'):v for k,v in weights.items()},strict=True)
        self.model.cuda().eval()

    @torch.inference_mode()
    def separate(self,x):
        padded = np.pad(x,(0,(-len(x))%16+32))
        outputs = self.model(torch.from_numpy(padded).cuda()[None,:])
        pair = np.stack([wave[0,:len(x)].float().cpu().numpy() for wave in outputs])
        if pair.shape!=(2,len(x)) or not np.isfinite(pair).all():
            raise RuntimeError('화자 분리 결과가 올바르지 않습니다.')
        tracks = []
        for track in pair:
            gain = float(x@track)/max(float(track@track),1e-12)
            peak = max(float(np.max(np.abs(track))),1e-12)
            gain = np.copysign(min(abs(gain),4.,.95/peak),gain)
            tracks.append((gain*track).astype('float32'))
        return tracks


class EcapaEncoder:
    def __init__(self):
        from hyperpyyaml import load_hyperpyyaml
        from speechbrain.utils.importutils import LazyModule

        for module in list(sys.modules.values()):
            if isinstance(module,LazyModule):
                module.__dict__.setdefault('__file__',None)
        config,weights = (ECAPA_DIR/name for name in ('hyperparams.yaml','embedding_model.ckpt'))
        require_weight(config)
        require_weight(weights)
        models = load_hyperpyyaml(config.read_text(encoding='utf-8'))
        self.features = models['compute_features'].eval()
        self.norm = models['mean_var_norm'].eval()
        self.model = models['embedding_model'].eval()
        self.model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True),strict=True)

    @torch.inference_mode()
    def embedding(self,wave):
        lengths = torch.ones(1)
        features = self.features(torch.from_numpy(wave)[None,:])
        return self.model(self.norm(features,lengths),lengths).flatten()


class OrderVoice:
    """Calls are serialised by the API's model lock."""
    def __init__(self):
        self.pending = {}
        self.active = {}
        self.separator = None
        self.encoder = None

    def prune(self):
        now = time.monotonic()
        for store in (self.pending,self.active):
            for key, (expiry,_) in list(store.items()):
                if expiry<=now:
                    self.discard(key)

    def discard(self,key):
        self.pending.pop(key,None)
        current = self.active.pop(key,None)
        if current is not None:
            current[1].reset()

    def confirm(self,key):
        self.prune()
        if key in self.active:
            return True
        pending = self.pending.get(key)
        if pending is None:
            raise KeyError(key)
        if self.encoder is None:
            self.encoder = EcapaEncoder()
        tracker = SessionSpeaker(self.encoder,.40,.20)
        if not tracker.confirm(pending[1]):
            self.pending.pop(key)
            return False
        if len(self.active)>=32:
            self.discard(next(iter(self.active)))
        self.pending.pop(key)
        self.active[key] = (time.monotonic()+ACTIVE_SECONDS,tracker)
        return True

    def transcribe(self,wave,session,stt):
        self.prune()
        if session is not None and session not in self.active:
            raise KeyError(session)
        if not RATE<=len(wave)<=8*RATE or float(np.max(np.abs(wave)))<.001:
            return dict(text='',status='invalid_clip',stt_seconds=0.)
        if self.separator is None:
            self.separator = MossFormer()
        tracks = self.separator.separate(wave)
        if session is not None:
            tracker = self.active[session][1]
            index = tracker.select(tracks)
            if index is None:
                return dict(text='',status='speaker_unclear',stt_seconds=0.)
            recognized, = stt(tracks[index])
            if not recognized['text'].strip():
                return dict(text='',status='speaker_unclear',stt_seconds=recognized['seconds'])
            self.active[session] = (time.monotonic()+ACTIVE_SECONDS,tracker)
            return dict(text=recognized['text'],status='tracked',stt_seconds=recognized['seconds'])

        recognized = stt(*tracks)
        seconds = sum(item['seconds'] for item in recognized)
        hits = [i for i,item in enumerate(recognized) if CUE_PREFIX.match(item['text'])]
        if len(hits)!=1:
            return dict(text='',status='cue_missing' if not hits else 'cue_ambiguous',stt_seconds=seconds)
        index = hits[0]
        text = CUE_PREFIX.sub('',recognized[index]['text'],count=1).strip()
        if not text:
            return dict(text='',status='order_missing',stt_seconds=seconds)
        if len(self.pending)>=32:
            self.pending.pop(next(iter(self.pending)))
        key = secrets.token_urlsafe(24)
        self.pending[key] = (time.monotonic()+PENDING_SECONDS,tracks[index])
        return dict(text=text,status='confirmation_required',candidate_id=key,stt_seconds=seconds)
