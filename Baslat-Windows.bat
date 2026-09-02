@echo off
REM DALSAN ISG - Windows baslatici. Bu dosyaya cift tiklayin.
cd /d "%~dp0"

REM DIKKAT: "where python" Windows 10/11'de HER ZAMAN basarili olur.
REM Python kurulu olmasa bile Microsoft Store takma adi (sifir baytlik
REM python.exe) PATH'tedir; calistirilinca Magaza acilir ve pencere kapanir.
REM Bu yuzden once py.exe launcher denenir (Add to PATH isaretlenmese de
REM kurulur) ve adayin gercekten Python oldugu dogrulanir.

py -3 -c "import sys" >nul 2>nul
if %errorlevel%==0 (
    py -3 masaustu\dalsan_launcher.py
    if errorlevel 1 pause
    goto :eof
)

python -c "import sys" >nul 2>nul
if %errorlevel%==0 (
    python masaustu\dalsan_launcher.py
    if errorlevel 1 pause
    goto :eof
)

echo.
echo   Python bulunamadi.
echo   https://www.python.org/downloads/ adresinden Python 3.12 kurun.
echo   Kurulum sirasinda "Add Python to PATH" kutusunu MUTLAKA isaretleyin.
echo.
pause
