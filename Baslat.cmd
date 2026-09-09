@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Once Kurulum.cmd calistirin.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m shadowmma %*
if errorlevel 1 pause
