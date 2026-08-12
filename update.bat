@echo off
REM ============================================================
REM  Wiki Archive - Update the container (double-click)
REM  Rebuilds the image and restarts with the new code.
REM ============================================================
cd /d "%~dp0"

echo.
echo === Updating the Wiki Archive container ===
echo.

docker compose up -d --build
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE%==0 (
    echo Done. Interface: http://localhost:8080
) else (
    echo FAILED ^(code %EXITCODE%^) - see messages above.
)

echo.
pause
