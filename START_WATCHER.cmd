@echo off
title Sugarland Petroleum - Video Intelligence - AUTO WATCHER
cd /d "%~dp0"
REM Self-healing (item 7): if the watcher process ever crashes/exits with an error,
REM relaunch it automatically. A clean stop (Ctrl+C / quit = exit code 0) ends here.
:loop
echo(
echo [%date% %time%] Starting the auto watcher (leave this window open; PC must stay on)...
python watch_and_run.py
if errorlevel 1 (
  echo(
  echo Watcher crashed - self-healing restart in 5 seconds ^(close this window to stop^)...
  timeout /t 5 /nobreak >nul
  goto loop
)
echo(
echo Watcher stopped cleanly.
pause
