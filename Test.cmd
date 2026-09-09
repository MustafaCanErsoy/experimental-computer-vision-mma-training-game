@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 (
    pause
    exit /b 1
)
pause
