@echo off
rem ===========================================================================
rem  Chronicle of the House - import a new Crusader Kings III save.
rem  Asks for the save and for the game folder (the map lives there, not in the
rem  save), then builds everything the app needs.
rem ===========================================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if not %errorlevel%==0 (
    echo Python 3 is required for the importer.
    echo Install it from https://www.python.org/downloads/ and run this file again.
    echo.
    pause
    goto :done
)

echo You can drag the .ck3 file into this window and press Enter.
python tools\import_save.py %*

echo.
pause

:done
endlocal
