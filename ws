#!/bin/sh
# workstead CLI. Same as: python3 tools/ws/ws.py "$@"
here=$(cd "$(dirname "$0")" && pwd)
exec "${PYTHON:-python3}" "$here/tools/ws/ws.py" "$@"
