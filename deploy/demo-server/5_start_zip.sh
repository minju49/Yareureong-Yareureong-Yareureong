#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
test -f .env || { echo "먼저 bash 1_prepare.sh 를 실행하세요."; exit 2; }
test -s noise-zip-cpu.tar || { echo "동봉한 noise-zip-cpu.tar를 같은 폴더에 두세요."; exit 2; }
docker load -i noise-zip-cpu.tar
docker compose --profile noise up -d --no-build --pull never noise
binding=$(docker compose --profile noise port noise 8058)
port=${binding##*:}
curl --fail --silent --show-error --retry 6 --retry-connrefused --retry-delay 2 --max-time 15 "http://127.0.0.1:${port}/health"
echo
echo "Windows의 잡음 서버 주소에 http://서버IP:${port} 을 입력한 뒤 ZipEnhancer를 선택하세요."
