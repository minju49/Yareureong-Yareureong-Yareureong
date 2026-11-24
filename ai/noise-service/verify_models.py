"""Use the packaged, pinned weights offline; download only when absent/bad."""
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'audio_lab'))
try:
    from model_files import verify
    from ensemble import MOSS_FILE,moss_verified
    from speaker_separation import SS_FILE,verified
    verify()
    if not moss_verified(MOSS_FILE) or not verified(SS_FILE):raise ValueError('추가 모델 파일 해시 확인 필요')
    print('동봉한 3개 잡음 처리 모델의 해시 확인 완료. 모델 다운로드는 하지 않았습니다.')
except (OSError,ValueError):
    sys.argv=['model_files.py','--ensemble','--separation']
    runpy.run_path(str(ROOT/'audio_lab'/'model_files.py'),run_name='__main__')
