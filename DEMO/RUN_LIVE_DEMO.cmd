@echo off
title Sugarland Petroleum - AI Video Intelligence - LIVE DEMO
cd /d "%~dp0"
echo.
echo   Starting the live detection demo...
echo   (this runs on THIS PC only - no internet needed)
echo.
python demo_live.py
if errorlevel 1 (
  echo.
  echo   Could not start Python. Opening the pre-rendered evidence clip instead.
  start "" "..\Mesa_Valero_Register1_ANNOTATED_evidence.mp4"
  pause
)
