"""Track a confirmed speaker in memory for one kiosk order session."""
import numpy as np


class SessionSpeaker:
    def __init__(self, encoder, minimum_similarity, minimum_margin):
        self.encoder = encoder
        self.minimum_similarity = minimum_similarity
        self.minimum_margin = minimum_margin
        self._reference = None

    def _vector(self, wave):
        wave = np.asarray(wave,dtype=np.float32)
        if wave.ndim!=1 or len(wave)<16000 or not np.isfinite(wave).all():
            return None
        frames = wave[:len(wave)//320*320].reshape(-1,320)
        energy = np.sqrt(np.mean(frames**2,axis=1))
        audible = np.flatnonzero(energy >= max(.003,float(energy.max())*.08))
        if len(audible)<30:
            return None
        begin,end = max(0,int(audible[0])-5)*320,min(len(wave),(int(audible[-1])+6)*320)
        feature = self.encoder.embedding(wave[begin:end]).cpu().numpy()
        norm = float(np.linalg.norm(feature))
        return feature/norm if norm>0 and np.isfinite(norm) else None

    def confirm(self, wave):
        if self._reference is not None:
            raise RuntimeError('Reset the order session before changing its speaker')
        reference = self._vector(wave)
        if reference is None:
            return False
        self._reference = reference
        return True

    def reset(self):
        self._reference = None

    def scores(self, tracks):
        if self._reference is None:
            return (None,None)
        if len(tracks)!=2:
            raise ValueError('Expected two separated tracks')
        vectors = [self._vector(track) for track in tracks]
        return tuple(float(np.clip(vector@self._reference,-1,1)) if vector is not None else None for vector in vectors)

    @staticmethod
    def choose(scores, minimum_similarity, minimum_margin):
        usable = sorted(((score,index) for index,score in enumerate(scores) if score is not None),reverse=True)
        if not usable or usable[0][0]<minimum_similarity:
            return None
        if len(usable)>1 and usable[0][0]-usable[1][0]<=minimum_margin:
            return None
        return usable[0][1]

    def select(self, tracks):
        return self.choose(self.scores(tracks),self.minimum_similarity,self.minimum_margin)
