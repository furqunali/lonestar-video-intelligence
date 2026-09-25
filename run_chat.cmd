@echo off
REM One-click launch of the Sugarland Petroleum chat-support portal.
REM Opens the widget in the browser and starts the offline server.
cd /d "%~dp0"
echo Starting chat support at http://127.0.0.1:8770 ...
start "" http://127.0.0.1:8770
python -m avip.chat.server 127.0.0.1 8770
pause
