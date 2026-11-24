#!/bin/sh
set -eu
bom_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$bom_root"
exec sh "$bom_root/scripts/python.sh" "$bom_root/review_lab/linux_cli.py" "$@"
