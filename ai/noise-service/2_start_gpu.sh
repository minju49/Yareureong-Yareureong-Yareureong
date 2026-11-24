#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
exec .venv/bin/python -u server.py --host 0.0.0.0 --port 8058
