@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.lock.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\setup.py
if errorlevel 1 goto failed
if not exist ".tools\godot\Godot_v4.7.2-stable_win64.exe" (
    ".venv\Scripts\python.exe" scripts\setup_godot.py
    if errorlevel 1 goto failed
)
echo Kurulum tamamlandi. ShadowMMA.cmd ile kaynak secin.
pause
exit /b 0
:failed
echo Kurulum tamamlanamadi. Python 3.12 x64 ve internet baglantisini kontrol edin.
pause
exit /b 1
