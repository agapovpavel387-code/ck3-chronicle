#!/usr/bin/env sh
# Chronicle of the House - launcher for macOS and Linux.
# Serves app/ locally and opens the browser. Node or Python is enough.

set -e
cd "$(dirname "$0")"
URL="http://127.0.0.1:8778/"

if command -v node >/dev/null 2>&1; then
  echo "Starting with Node.js..."
  exec node tools/serve.js --open
fi

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Neither Node.js nor Python was found."
  echo "Install one of them and run this script again:"
  echo "  Node.js - https://nodejs.org/  (recommended)"
  echo "  Python  - https://www.python.org/downloads/"
  exit 1
fi

echo "Starting with Python..."
if command -v open >/dev/null 2>&1; then open "$URL"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"; fi
exec "$PY" -m http.server 8778 --bind 127.0.0.1 --directory app
