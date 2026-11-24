#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
docker compose ps
binding=$(docker compose port spring 8080)
port=${binding##*:}
echo "실제 Spring/MariaDB 상태:"
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${port}/api/menu-health"
echo
echo "이 서버의 IP 후보:"
hostname -I
echo "Windows 연결본 담당자 설정에 http://서버IP:${port} 을 입력하세요."
echo "동일 네트워크에서 연결이 안 되면 포트 ${port} 접근과 학교 네트워크를 확인하세요."
