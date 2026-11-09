@echo off
rem One entry point: checks, facts, documents, archive, archive self-check.
rem   make.cmd              - full run with tests
rem   make.cmd --skip-tests - without npm test (draft)
setlocal
cd /d "%~dp0"
python -X utf8 tools\release.py %*
if errorlevel 1 (
  echo.
  echo BUILD FAILED - the archive must not be published.
  exit /b 1
)
echo.
echo BUILD OK. Archive and manifest are in dist.
