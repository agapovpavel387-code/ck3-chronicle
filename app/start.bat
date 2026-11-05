@echo off
setlocal
cd /d "%~dp0"
set PORT=8778
echo Хроника рода: http://127.0.0.1:%PORT%/
start "" "http://127.0.0.1:%PORT%/"
python -m http.server %PORT% --bind 127.0.0.1
