@echo off
setlocal
rem Radar control - start, stop, status, log. See RADAR.md.
rem Kept ASCII-only on purpose: cmd reads a .cmd file in the console codepage, and a stray
rem em dash in a comment was enough to make it try to execute part of the line.

set "ROOT=%~dp0"
set "PY=%ROOT%backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if "%~1"=="" goto usage
if /I "%~1"=="help" goto usage
if /I "%~1"=="log" goto showlog

pushd "%ROOT%backend"
"%PY%" -m algent_backend.cli newsroom radar %*
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%

:showlog
powershell -NoProfile -Command "Get-Content -Wait -Tail 40 '%ROOT%backend\runs_data\radar_daemon.log'"
exit /b 0

:usage
echo Usage: radar [start^|stop^|status^|log]
echo.
echo   start    begin posting in the background (close this window freely)
echo   stop     stop it, and verify nothing is left running
echo   status   what is queued, what is running, when the next post goes
echo   log      follow the log
exit /b 1
