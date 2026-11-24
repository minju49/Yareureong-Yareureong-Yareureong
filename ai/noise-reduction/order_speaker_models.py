"""Fetch and verify the pinned weights for the order-speaker mode."""
from hashlib import file_digest
import os
from pathlib import Path
from shutil import copyfileobj
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
MODELS = ROOT/'models'
SS_FILE = Path(os.getenv('MOSSFORMER2_SS_FILE', MODELS/'mossformer2-ss/last_best_checkpoint.pt'))
ECAPA_DIR = Path(os.getenv('ZIP_ECAPA_MODEL_DIR', MODELS/'ecapa-tdnn'))
SENSEVOICE_DIR = Path(os.getenv('ZIP_STT_MODEL_DIR', MODELS/'sensevoice-small'))
ARTIFACTS = {
    SS_FILE: ('alibabasglab/MossFormer2_SS_16K', '407cb030cd66340918ebb6c8cc63b18f8592cdbe', 'last_best_checkpoint.pt',
              '00a3a48bda492db1e829b85dd443f8f43a43039a3e90f1a24962ea9caf14a11a'),
    ECAPA_DIR/'hyperparams.yaml': ('speechbrain/spkrec-ecapa-voxceleb', '0f99f2d0ebe89ac095bcc5903c4dd8f72b367286', 'hyperparams.yaml',
                                   '6f78854fa04ba59e761437b76a2575d3aba5e5016de3e9b69f0c9a5077fb1a41'),
    ECAPA_DIR/'embedding_model.ckpt': ('speechbrain/spkrec-ecapa-voxceleb', '0f99f2d0ebe89ac095bcc5903c4dd8f72b367286', 'embedding_model.ckpt',
                                        '0575cb64845e6b9a10db9bcb74d5ac32b326b8dc90352671d345e2ee3d0126a2'),
    SENSEVOICE_DIR/'model.int8.onnx': ('csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17', '2365baeacb507f821a0c8120fcee3d484dba7a07', 'model.int8.onnx',
                                      'c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51'),
    SENSEVOICE_DIR/'tokens.txt': ('csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17', '2365baeacb507f821a0c8120fcee3d484dba7a07', 'tokens.txt',
                                 'f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc'),
}


def verified(path, expected):
    if not path.is_file():
        return False
    with path.open('rb') as file:
        return file_digest(file,'sha256').hexdigest()==expected


def require_weight(path):
    if not verified(path,ARTIFACTS[path][3]):
        raise RuntimeError(f'가중치 준비가 필요합니다. setup-order-speaker.ps1 ({path.name})')


def main():
    for path,(repo,revision,name,checksum) in ARTIFACTS.items():
        if not verified(path,checksum):
            path.parent.mkdir(parents=True,exist_ok=True)
            part = path.with_name(path.name+'.part')
            try:
                print(f'Downloading {repo}: {name}',flush=True)
                with urlopen(f'https://huggingface.co/{repo}/resolve/{revision}/{name}',timeout=90) as source, part.open('wb') as target:
                    copyfileobj(source,target)
                if not verified(part,checksum):
                    raise RuntimeError(f'Checksum mismatch: {name}')
                part.replace(path)
            finally:
                part.unlink(missing_ok=True)
        print(f'Verified {path}',flush=True)


if __name__=='__main__':
    main()
