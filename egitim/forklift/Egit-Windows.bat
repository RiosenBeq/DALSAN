@echo off
REM NextGen Detector - forklift modelini fabrikanin kendi verisiyle egitir.
REM
REM Kullanim: programin Forklift sayfasindan indirdiginiz veri paketini (zip)
REM bu dosyanin ustune surukleyip birakin. Egitim uzun surer (bir gun kadar);
REM pencere kapanir ya da bilgisayar yeniden baslarsa ayni zip'i yeniden
REM birakin: biten adimlar atlanir, egitim kaldigi yerden surer.
REM Istege bagli ikinci arguman: calisma klasoru (varsayilan C:\NextGen-Forklift;
REM yolda Turkce karakter olmamali).
REM
REM Fabrika kareleri kisisel veridir (KVKK): yalniz bu bilgisayarda islenir,
REM hicbir yere yuklenmez. Ayrinti: egitim\forklift\YEREL-EGITIM.md
setlocal
set "PAKET=%~1"
set "CALISMA=%~2"
if "%CALISMA%"=="" set "CALISMA=C:\NextGen-Forklift"

if "%PAKET%"=="" (
    echo.
    echo   Veri paketi verilmedi.
    echo   Programin Forklift sayfasindan indirdiginiz zip dosyasini
    echo   bu dosyanin ustune surukleyip birakin.
    echo.
    pause
    exit /b 2
)

REM Python 3.12. "where python" kullanilmaz: Windows 10/11'de Python kurulu
REM olmasa bile basarilidir, Microsoft Store takma adi PATH'tedir
REM (Baslat-Windows.bat ile ayni tuzak).
py -3.12 -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo.
    echo   Python 3.12 bulunamadi.
    echo   https://www.python.org/downloads/ adresinden Python 3.12 kurun.
    echo.
    pause
    exit /b 2
)

set "ORTAM=%CALISMA%\ortam"
set "PY=%ORTAM%\Scripts\python.exe"
if not exist "%PY%" (
    echo Egitim ortami kuruluyor: %ORTAM%
    py -3.12 -m venv "%ORTAM%"
    if errorlevel 1 goto :kurulum_hatasi
)

REM Paketler her seferinde denetlenir; kuruluysa birkac saniye surer. Ilk
REM seferde yaklasik 1 GB iner.
echo Egitim paketleri denetleniyor, ilk seferde birkac dakika surer...
"%PY%" -m pip install --disable-pip-version-check -q torch==2.14.0 torchvision==0.29.0
if errorlevel 1 goto :kurulum_hatasi
"%PY%" -m pip install --disable-pip-version-check -q -r "%~dp0gereksinimler-yerel.txt"
if errorlevel 1 goto :kurulum_hatasi

"%PY%" "%~dp0yerel.py" --saha "%PAKET%" --calisma "%CALISMA%"
set "KOD=%errorlevel%"
echo.
if "%KOD%"=="0" (
    echo   Bitti. Sonuc: %CALISMA%\SONUC.txt
) else (
    echo   Durdu, cikis kodu %KOD%. Ayrinti yukarida ve %CALISMA%\gunluk.txt icinde.
    echo   Kod 1 ise ayni zip ile yeniden calistirin: kaldigi yerden surer.
)
echo.
pause
exit /b %KOD%

:kurulum_hatasi
echo.
echo   Egitim paketleri kurulamadi. Internet baglantisini denetleyip yeniden deneyin.
echo.
pause
exit /b 1
