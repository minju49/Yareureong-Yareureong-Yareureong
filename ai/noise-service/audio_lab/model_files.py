"""Download and check the exact ZipEnhancer checkpoint used in the experiment."""
import os
from hashlib import file_digest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_DIR = Path(os.environ.get('ZIPENHANCER_MODEL_DIR', ROOT / 'models' / 'zipenhancer'))
REPO = 'iic/speech_zipenhancer_ans_multiloss_16k_base'
# ModelScope exposes only the master branch for this model. The files are
# pinned by content hashes to the validated revision below.
ARTIFACT_REVISION = 'bed374bb53e4a5ffc62093676bab408a56b0db48'
FILES = {
    'configuration.json': '877861f930f597b479887685556b33724a9c1c87e4a135207253f9bdc8e717a7',
    'pytorch_model.bin': 'b18896915e27a821585584221d0c0820f35e12145315ae3f1e73ccd5a68d195f',
}


def verify():
    for name, expected in FILES.items():
        path = MODEL_DIR / name
        if not path.is_file():
            raise FileNotFoundError(f'{path} 파일이 없습니다. python model_files.py를 실행하세요.')
        with path.open('rb') as file:
            if file_digest(file, 'sha256').hexdigest() != expected:
                raise ValueError(f'{name}의 SHA-256이 실험 체크포인트와 일치하지 않습니다.')


if __name__ == '__main__':
    import argparse
    from modelscope.hub.file_download import model_file_download

    parser = argparse.ArgumentParser()
    parser.add_argument('--ensemble', action='store_true')
    parser.add_argument('--separation', action='store_true')
    args = parser.parse_args()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        model_file_download(REPO, name, revision='master', local_dir=str(MODEL_DIR))
    verify()
    print(f'SHA-256 검증 완료 ({ARTIFACT_REVISION}): {MODEL_DIR}')
    if args.ensemble:
        from shutil import copyfileobj
        from urllib.request import urlopen
        from ensemble import MOSS_FILE, MOSS_URL, moss_verified

        if not moss_verified(MOSS_FILE):
            MOSS_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = MOSS_FILE.with_suffix('.part')
            try:
                with urlopen(MOSS_URL, timeout=90) as source, temporary.open('wb') as output:
                    copyfileobj(source, output)
                if not moss_verified(temporary):
                    raise ValueError('MossFormerGAN SHA-256 불일치')
                temporary.replace(MOSS_FILE)
            finally:
                temporary.unlink(missing_ok=True)
        print(f'MossFormerGAN SHA-256 검증 완료: {MOSS_FILE}')

    if args.separation:
        from shutil import copyfileobj
        from urllib.request import urlopen
        from speaker_separation import SS_FILE, SS_URL, verified

        if not verified(SS_FILE):
            SS_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = SS_FILE.with_suffix('.part')
            try:
                with urlopen(SS_URL, timeout=90) as source, temporary.open('wb') as output:
                    copyfileobj(source,output)
                if not verified(temporary):
                    raise ValueError('MossFormer2 SS SHA-256 불일치')
                temporary.replace(SS_FILE)
            finally:
                temporary.unlink(missing_ok=True)
        print(f'MossFormer2 SS SHA-256 검증 완료: {SS_FILE}')
