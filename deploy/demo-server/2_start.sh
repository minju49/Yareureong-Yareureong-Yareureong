#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
test -f .env || { echo "먼저 bash 1_prepare.sh 를 실행하세요."; exit 2; }
docker compose up -d --no-build --pull never
echo "Spring/MariaDB를 시작했습니다. 초기 DB 준비를 기다린 뒤 bash 3_check.sh 로 확인하세요."
