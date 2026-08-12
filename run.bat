@echo off
REM ============================================================
REM  Wiki Archive - Native launch (double-click)
REM  Creates/activates a venv, installs dependencies, starts the
REM  server and opens the browser. Docker remains an option via
REM  update.bat (docker compose).
REM ============================================================
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

set VENV_DIR=.venv
set PYTHON=python

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3.12 -c "" >nul 2>nul && set PYTHON=py -3.12
    if not "%PYTHON%"=="py -3.12" (
        py -3.11 -c "" >nul 2>nul && set PYTHON=py -3.11
    )
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON% -m venv %VENV_DIR%
    if errorlevel 1 (
        echo FAILED to create venv - is Python 3.11/3.12 installed?
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"

echo Installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo FAILED to install dependencies.
    pause
    exit /b 1
)

echo.
echo === Wiki Archive - starting ===
echo Interface: http://127.0.0.1:8080
echo (Ctrl+C in this window to stop the server)
echo.
echo If PDF export fails: the GTK3 runtime is required on Windows.
echo https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
echo Markdown/text exports work without GTK3.
echo.

start "" http://127.0.0.1:8080
python server.py

pause
