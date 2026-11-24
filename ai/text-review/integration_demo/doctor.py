"""Read-only local/runtime and explicitly configured service diagnostics."""
from pathlib import Path
import json
import os
import platform
import sys
from urllib.request import build_opener,ProxyHandler

ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'review_lab'),str(ROOT/'voice_lab'),str(ROOT/'vendor')]
from server import config
from backend import MenuBackend
from qwen_client import check_model
from run_school import configure
from run_batch import write_json


def main():
    result={'root':str(ROOT),'python':sys.version,'os':platform.platform(),'cpu':platform.processor(),
        'models_present':all((ROOT/p).is_file() for p in ('models/sensevoice/model.int8.onnx','models/sensevoice/tokens.txt')),
        'stt_executed_here':False,'new_qwen_order_calls':0,'checks':{}}
    settings=config()
    for name,operation in (
        ('Spring/MariaDB',lambda:MenuBackend(settings['spring_base_url']).request('/api/menu-health')),
        ('학교 Qwen 목록',lambda:check_model(configure())),
        ('잡음 서버',lambda:json.load(build_opener(ProxyHandler({})).open(settings['noise_base_url'].rstrip('/')+'/health',timeout=8)))):
        if name=='잡음 서버' and not settings['noise_base_url']:
            result['checks'][name]={'status':'not_configured'};continue
        try:result['checks'][name]={'status':'ok','response':operation()};print(name+': 연결 확인')
        except Exception as exc:result['checks'][name]={'status':'failed','error':str(exc)};print(name+': '+str(exc))
    path=ROOT/'diagnostics'/'팀연결_환경점검.json';write_json(path,result);print('점검 기록: '+str(path))
    print('이 점검은 목록·연결 확인이며 새 마이크/STT/Qwen 주문/TTS 합성을 실행하지 않습니다.')


if __name__=='__main__':main()
