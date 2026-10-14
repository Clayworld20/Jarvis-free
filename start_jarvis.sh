#!/usr/bin/env sh
# JARVIS-free launcher for Linux / macOS (best effort; Windows is the primary target).
set -e
cd "$(dirname "$0")"
VENV=".venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "[setup] creating virtual environment"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip >/dev/null
  "$VENV/bin/pip" install -r requirements.txt
fi
if [ ! -d resources/models/vosk-model-small-en-us-0.15 ] || [ ! -d resources/models/vosk-model-small-ru-0.22 ]; then
  "$VENV/bin/python" tools/download_models.py
fi
exec "$VENV/bin/python" -m jarvis "$@"
