"""School-only preparation and explicit calls; --self-check never uses network."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
import platform
import sys
import webbrowser
from review import POLICY

from qwen_client import PROFILES, api_base, check_model, request_order, payload
from run_batch import ROOT, load_cases, main as batch_main, score_model, write_json


def configure():
    profile = dict(PROFILES['school'])
    config_path = ROOT / 'school.local.json'
    if not profile['base_url'] and config_path.is_file():
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        profile['base_url'] = str(config.get('base_url', '')).strip()
    if not profile['base_url']:
        raise ValueError('school.local.json의 base_url 또는 BOM_SCHOOL_QWEN_BASE_URL에 교수님이 주신 주소를 지정해주세요.')
    profile['base_url'] = api_base(profile)
    PROFILES['school'] = profile
    return profile


def preflight(profile):
    folder = ROOT / 'records' / 'school-check'
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d-%H%M%S-%f')
    target = folder / (stamp + '.json')
    record = {'scope': '학교 모델 목록·실제 1건 호출 점검. 전체 성능 평가/배치 점수에 합산하지 않음.',
              'profile': profile, 'school_connection_verified': False, 'warmup_excluded_from_batch': True}
    try:
        print('[1/2] 학교 모델 목록을 확인합니다.', flush=True)
        record['models'] = check_model(profile)
        print('[2/2] 아이스 아메리카노 1잔 문장을 실제 요청합니다. 첫 로딩은 기다려주세요.', flush=True)
        row = request_order(profile, '아이스 아메리카노 한 잔 주세요', {})
        record['response'] = row
        reference = {'intent':'add','items':[{'menu_id':'americano','quantity':1,'temperature':'ice',
            'size':'regular','whipped_cream':None,'custom_note':''}], 'needs_clarification':False,'question_required':False}
        record['smoke_fields'] = score_model(row, reference)
        record['school_connection_verified'] = row['status'] == 'ok'
        if row.get('raw_content'):
            print('실제 답변: ' + row['raw_content'], flush=True)
        if not record['school_connection_verified']:
            print('실제 호출 또는 JSON 확인에 실패했습니다: ' + row.get('error', row.get('parse_error', row['status'])), flush=True)
        else:
            print('학교 모델 실제 응답·JSON 확인 완료.', flush=True)
            print('점검 1문장 필드 일치: ' + str(record['smoke_fields']['correct']) + '. 전체 정확도가 아닙니다.', flush=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        record['error'] = str(exc)
        print('연결 점검 실패: ' + str(exc), flush=True)
    finally:
        write_json(target, record)
        print('진단 기록: ' + str(target), flush=True)
    return record['school_connection_verified']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check','batch'])
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args, remaining = parser.parse_known_args()
    print('봄카페 학교 Qwen 실험 준비 1.1', flush=True)
    print('문장 보정 버전: ' + POLICY['version'], flush=True)
    print('현재 실행 위치: ' + str(ROOT), flush=True)
    if args.self_check:
        data = load_cases()
        print('Python: ' + platform.python_version() + ' / ' + platform.architecture()[0])
        print('실행 환경 위치: ' + sys.prefix)
        print('고정 개발용 문장: ' + str(len(data['cases'])) + '개 / 정답 초안의 팀원 검수 필요')
        print('준비 확인 완료. 학교 연결·모델 호출·마이크/STT 실행은 하지 않았습니다.')
        return 0
    profile = configure()
    print('대상 모델: ' + profile['model'], flush=True)
    print('대상 주소: ' + profile['base_url'], flush=True)
    if not preflight(profile):
        print('모델명·주소·학교 네트워크·서버 상태를 확인해주세요. 연결 실패를 성공 결과로 채우지 않았습니다.')
        return 2
    if args.action == 'check':
        return 0
    print('점검 요청은 제외하고, 같은 학교 모델로 원문/재점검문을 비교합니다.', flush=True)
    original_argv = sys.argv
    try:
        sys.argv = [str(Path(__file__).with_name('run_batch.py')), '--profile', 'school', '--skip-log-audit', *remaining]
        code = batch_main()
    finally:
        sys.argv = original_argv
    location = ROOT / '7_최근결과위치.txt'
    if location.is_file():
        report = Path(location.read_text(encoding='utf-8-sig').strip()) / '결과요약.html'
        if report.is_file() and report.resolve().is_relative_to((ROOT/'records').resolve()) and not args.no_browser:
            webbrowser.open(report.resolve().as_uri())
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('실험을 시작하지 못했습니다: ' + str(exc), flush=True)
        raise SystemExit(2)
