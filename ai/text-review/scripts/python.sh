#!/bin/sh
set -eu
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if [ -n "${BOM_PYTHON:-}" ]; then
    if ! "$BOM_PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        printf '%s\n' 'BOM_PYTHON에 지정한 실행 파일을 확인해주세요. Python 3.10 이상이 필요합니다.'
        exit 2
    fi
    exec "$BOM_PYTHON" "$@"
fi

for bom_candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python; do
    if command -v "$bom_candidate" >/dev/null 2>&1 &&
       "$bom_candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        exec "$bom_candidate" "$@"
    fi
done

printf '%s\n' 'Python 3.10 이상을 찾지 못했습니다.'
printf '%s\n' '터미널에서 python3 --version 결과를 확인해주세요.'
printf '%s\n' 'Python이 준비되면 다시 실행하세요. Qwen 모델이나 pip 패키지를 설치하는 단계는 아닙니다.'
exit 2
