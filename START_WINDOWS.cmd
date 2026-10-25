@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0..\.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if defined PYTHON_EXE (
  "%PYTHON_EXE%" server.py %*
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 server.py %*
  ) else (
    python server.py %*
  )
)
if errorlevel 1 (
  echo.
  echo Start failed. To use the offline demo, open OPEN_DEMO.html.
  echo For real KiCad checks, pass --kicad-cli "FULL_PATH_TO_KICAD_CLI".
  pause
)
endlocal
