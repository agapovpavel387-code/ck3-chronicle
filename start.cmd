@echo off
rem ===========================================================================
rem  Chronicle of the House - one click launcher (Windows)
rem  Serves app/ locally and opens the browser. Node or Python is enough.
rem ===========================================================================
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if %errorlevel%==0 (
    echo Starting with Node.js...
    node tools\serve.js --open
    goto :done
)

where python >nul 2>nul
if %errorlevel%==0 (
    echo Starting with Python...
    start "" "http://127.0.0.1:8778/"
    python -m http.server 8778 --bind 127.0.0.1 --directory app
    goto :done
)

echo.
echo Neither Node.js nor Python was found on this computer.
echo Install either one and run this file again:
echo   Node.js  - https://nodejs.org/    (recommended)
echo   Python   - https://www.python.org/downloads/
echo.
echo You can also open app\index.html directly in a browser.
echo.
pause

:done
endlocal
