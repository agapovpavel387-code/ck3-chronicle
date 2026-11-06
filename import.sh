#!/usr/bin/env sh
# Chronicle of the House - import a new Crusader Kings III save.
# Asks for the save and for the game folder (the map lives there, not in the save).

set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3 is required for the importer."
  echo "Install it from https://www.python.org/downloads/ and run this script again."
  exit 1
fi

exec "$PY" tools/import_save.py "$@"
