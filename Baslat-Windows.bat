@echo off
REM DALSAN ISG - Windows baslatici. Bu dosyaya cift tiklayin.
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python masaustu\dalsan_launcher.py
) else (
    echo.
    echo   Python bulunamadi.
    echo   https://www.python.org/downloads/ adresinden Python 3.12 kurun.
    echo   Kurulum sirasinda "Add Python to PATH" kutusunu MUTLAKA isaretleyin.
    echo.
    pause
)
