#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
docker compose --profile noise stop
echo "서버를 멈췄습니다. 메뉴와 시연 주문 DB는 보존했습니다."
