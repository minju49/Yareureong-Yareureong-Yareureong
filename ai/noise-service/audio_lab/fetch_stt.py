"""Fetch exact SenseVoice artifacts with content verification."""
from hashlib import file_digest
from pathlib import Path
from shutil import copyfileobj
from urllib.request import urlopen

MODEL = Path(__file__).resolve().parent/'models/sensevoice'
BASE = ('https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/'
        '2365baeacb507f821a0c8120fcee3d484dba7a07/')
FILES = {
    'model.int8.onnx':'c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51',
    'tokens.txt':'f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc',
}


def digest(path):
    if path.is_file():
        with path.open('rb') as file:
            return file_digest(file,'sha256').hexdigest()
    return None


MODEL.mkdir(parents=True,exist_ok=True)
for name,expected in FILES.items():
    path = MODEL/name
    if digest(path)==expected:
        continue
    pending = path.with_suffix('.part')
    try:
        with urlopen(BASE+name,timeout=90) as src,pending.open('wb') as dst:
            copyfileobj(src,dst)
        if digest(pending)!=expected:
            raise ValueError(f'SenseVoice checksum mismatch: {name}')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
print('SenseVoice checkpoint and tokens verified.')
