#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -z "${APP_PYTHON_BIN:-}" ]; then
  if [ -x .venv/bin/python ]; then APP_PYTHON_BIN=.venv/bin/python
  else APP_PYTHON_BIN=python3
  fi
fi
exec "$APP_PYTHON_BIN" -m app.server
