@echo off
REM Radar control — the switch you can reach without an agent.
REM
REM   radar start    begin posting (runs in the background; close this window freely)
REM   radar stop     stop it, and verify nothing is left running
REM   radar status   what is queued, what is running, when the next post goes
REM   radar log      follow the log
REM
REM Deliberately a plain batch file at the repo root: when the point is "turn it off NOW",
REM it must not depend on remembering a module path, activating a venv, or having an agent
REM available to ask.

setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if /I "%~1"=="log" (
  powershell -NoProfile -Command "Get-Content -Wait -Tail 40 '%ROOT%backend\runs_data\radar_daemon.log'"
  exit /b 0
)

if "%~1"=="" (
  echo Usage: radar [start^|stop^|status^|log]
  exit /b 1
)

pushd "%ROOT%backend"
"%PY%" -m algent_backend.cli newsroom radar %*
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
