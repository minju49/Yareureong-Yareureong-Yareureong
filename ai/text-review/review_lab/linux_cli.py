"""Linux launch menu for the unchanged school text experiments.

Only Python's standard library is used. Offline flags never contact a server.
"""
from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
from datetime import datetime,timezone,timedelta
import argparse
import platform
import sys
import traceback
import uuid

ROOT=Path(__file__).resolve().parent.parent
LAUNCH_VERSION='bom-linux-launch-1.0'
MIN_PYTHON=(3,10)
HISTORY=ROOT/'local-inputs'/'historical-stt-cases-draft.json'


class Tee:
    def __init__(self,screen,log): self.screen,self.log=screen,log
    def write(self,text):
        self.screen.write(text);self.log.write(text);self.flush()
        return len(text)
    def flush(self): self.screen.flush();self.log.flush()


def self_check():
    if sys.version_info<MIN_PYTHON:
        raise ValueError('Python 3.10 이상이 필요합니다. 현재 '+platform.python_version())
    from run_batch import load_cases
    from review import POLICY
    required=('review.py','qwen_client.py','order_gate.py','option_spacing.py','run_school.py','run_batch.py','menu_policy.json')
    missing=[name for name in required if not (ROOT/'review_lab'/name).is_file()]
    if missing: raise ValueError('ZIP 전체 압축 해제를 확인해주세요. 빠진 파일: '+', '.join(missing))
    data=load_cases()
    print('운영체제: '+platform.system()+' / '+platform.machine())
    print('Python: '+platform.python_version()+' / '+sys.executable)
    print('문장 보정 버전: '+POLICY['version'])
    print('개발 문장: '+str(len(data['cases']))+'개')
    if HISTORY.is_file(): print('과거 STT 문장: '+str(len(load_cases(HISTORY)['cases']))+'개')
    else: print('과거43개 자료: 없음. 개인 전달용 Linux ZIP에 포함됩니다.')
    print('서버 설정 파일: '+('있음' if (ROOT/'school.local.json').is_file() else '없음 — Git 소스 사용 시 school.example.json 참고'))
    print('준비 확인 완료. 학교 서버 연결·모델 호출·마이크/STT 실행은 하지 않았습니다.')
    return 0


def _call(main,argv):
    previous=sys.argv
    try:
        sys.argv=argv
        return main()
    finally: sys.argv=previous


def dispatch(action,remaining):
    if action=='selfcheck': return self_check()
    if action=='component':
        from run_component_check import main
        return _call(main,['run_component_check.py','--profile','school','--repetitions','3',
                          '--output-root',str(ROOT/'records'/'component'),*remaining])
    from run_school import main
    if action=='batch43':
        if not HISTORY.is_file(): raise ValueError('과거43개 자료가 없습니다. 개인 전달용 리눅스 ZIP을 전체 압축 해제해주세요.')
        return _call(main,['run_school.py','batch','--cases',str(HISTORY),*remaining])
    return _call(main,['run_school.py','check' if action=='check' else 'batch',*remaining])


def run_action(action,remaining=()):
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d-%H%M%S')
    folder=ROOT/'records'/'linux-launch'
    try: folder.mkdir(parents=True,exist_ok=True)
    except OSError as exc:
        print('기록 폴더를 만들 수 없습니다. ZIP을 홈 폴더 등 쓰기 가능한 곳에 풀어주세요. '+str(exc))
        return 2
    path=folder/(stamp+'-'+uuid.uuid4().hex[:6]+'.log')
    code=2
    with path.open('w',encoding='utf-8') as handle:
        with redirect_stdout(Tee(sys.stdout,handle)),redirect_stderr(Tee(sys.stderr,handle)):
            print('봄카페 리눅스 실행 · '+LAUNCH_VERSION)
            print('현재 실행 위치: '+str(ROOT))
            try: code=dispatch(action,list(remaining))
            except KeyboardInterrupt:
                print('사용자가 중단했습니다. 중단한 요청을 성공으로 기록하지 않습니다.');code=130
            except SystemExit as exc: code=exc.code if isinstance(exc.code,int) else 2
            except Exception as exc:
                print('실행하지 못했습니다: '+str(exc))
                traceback.print_exc(file=handle)
                print('ZIP 전체 압축 해제·Python 버전·서버 연결 안내를 확인해주세요.');code=2
            print('실행 기록: '+str(path))
    return code


def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if sys.version_info<MIN_PYTHON:
        print('Python 3.10 이상이 필요합니다. python3 --version 결과를 확인해주세요.')
        return 2
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',default='menu',choices=('menu','selfcheck','check','batch56','batch43','component'))
    parser.add_argument('--self-check',action='store_true')
    parser.add_argument('--validate-only',action='store_true')
    args,remaining=parser.parse_known_args(argv)
    if args.self_check or args.validate_only:
        return run_action('selfcheck')
    if args.action!='menu': return run_action(args.action,remaining)
    actions={'1':'selfcheck','2':'check','3':'batch56','4':'batch43','5':'component'}
    while True:
        print('\n봄카페 · 리눅스 문장 재점검 실험')
        print('1. 파일·Python 준비 확인 (서버 호출 없음)')
        print('2. 학교 Qwen 연결·실제 한 문장 점검')
        print('3. 개발 56문장 원문/재점검 비교')
        print('4. 과거 STT 43문장 비교')
        print('5. 기능별 24문장 × 3회 비교')
        print('0. 종료')
        try: choice=input('번호 입력: ').strip()
        except (EOFError,KeyboardInterrupt): print('\n종료했어요.');return 0
        if choice=='0': print('종료했어요.');return 0
        if choice not in actions: print('0~5 중에서 골라주세요.');continue
        run_action(actions[choice])


if __name__=='__main__': raise SystemExit(main())
