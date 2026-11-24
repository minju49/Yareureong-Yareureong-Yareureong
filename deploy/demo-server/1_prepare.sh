#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker가 필요합니다. 학교 담당자 또는 서버 담당자가 설치한 뒤 다시 실행하세요."
  exit 2
fi
docker compose version >/dev/null || { echo "Docker Compose 플러그인을 확인해주세요."; exit 2; }
docker info --format '{{.OSType}}/{{.Architecture}}' || { echo "Docker 실행 권한과 상태를 확인해주세요."; exit 2; }
if [ ! -f .env ]; then
  command -v python3 >/dev/null || { echo "첫 설정에 Python 3가 필요합니다."; exit 2; }
  python3 - <<'PY'
from pathlib import Path
import secrets
p=Path('.env')
p.write_text('BOM_DB_PASSWORD='+secrets.token_urlsafe(24)+'\nBOM_DB_ROOT_PASSWORD='+secrets.token_urlsafe(24)+'\nBOM_SPRING_BIND=0.0.0.0\n')
p.chmod(0o600)
PY
  echo "이 시연용 DB의 새 비밀번호를 .env에 준비했습니다. 기존 친구 PC 비밀번호는 필요하지 않습니다."
fi
test -s menus_catalog.sql || { echo "menus_catalog.sql이 없습니다. ZIP 전체를 풀어주세요."; exit 2; }
test -s images.tar || { echo "images.tar가 없습니다. ZIP 전체를 풀어주세요."; exit 2; }
docker load -i images.tar
echo "준비 확인 완료. bash 2_start.sh 를 실행하세요."
