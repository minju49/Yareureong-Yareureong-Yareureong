"""Small constructed-text integration smoke checks; never called an ASR study."""
from pathlib import Path
from datetime import datetime
import json
import os
import subprocess
import sys
import uuid

from run_review import make_record

ROOT = Path(__file__).resolve().parent.parent
QA = ROOT / 'records' / 'review-verification' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])


def main():
    QA.mkdir(parents=True, exist_ok=True)
    command = 'call "' + str(ROOT / '6_문장재점검실험.cmd') + '" --output-dir "' + str(QA / '한글 경로 CLI') + '" --input-kind scripted_cli_smoke'
    # cmd.exe interprets its /c remainder itself; list2cmdline would leave \" in it.
    command_line = '"' + os.environ.get('COMSPEC', r'C:\Windows\System32\cmd.exe') + '" /d /c ' + command
    completed = subprocess.run(command_line,
        input='아아 주세요\nn\n/문맥\n1\n한 개요\nn\n/종료\n\n',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', timeout=30)
    (QA / 'interactive-cli.log').write_text(completed.stdout, encoding='utf-8')
    records = sorted((QA / '한글 경로 CLI').glob('*.json'))
    rows = [json.loads(p.read_text(encoding='utf-8')) for p in records]
    cli_ok = (completed.returncode == 0 and len(rows) == 2 and
              all(row['qwen']['status'] == 'not_requested' for row in rows) and
              rows[0]['review']['reviewed_text'] == '아이스 아메리카노 주세요' and
              rows[1]['review']['context_expansion']['value'] == 1)
    summary = {'scope': 'constructed text and actual local Qwen smoke only; no microphone/STT or school 9B validation',
               'cli_exit_code': completed.returncode, 'cli_unicode_and_context_ok': cli_ok,
               'live_cases': []}
    if not cli_ok:
        print(completed.stdout)
        raise RuntimeError('대화형 실행 파일 점검 실패. interactive-cli.log를 확인하세요.')
    print('실행 파일 / 한글 출력 / 문맥 선택 / Qwen 미호출 선택 확인 완료.', flush=True)
    cases = [('아아 한 잔 주세요', 'none'), ('아메리카너 한 잔 주세요', 'none'),
             ('딸기라떼 두 잔 주세요', 'none'), ('망고스무디 주세요', 'none'),
             ('한 개요', 'quantity'), ('차갑게', 'temperature')]
    for text, context in cases:
        ok = make_record(text, context, 'home', QA / 'actual-qwen', True, 'constructed_text_smoke')
        summary['live_cases'].append({'text': text, 'context': context, 'api_and_json_ok': ok})
    (QA / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n검증 요약: ' + str(QA / 'summary.json'))
    if not all(row['api_and_json_ok'] for row in summary['live_cases']):
        raise SystemExit(1)


if __name__ == '__main__': main()
