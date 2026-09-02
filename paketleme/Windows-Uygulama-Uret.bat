@echo off
REM ============================================================================
REM  NextGen Detector - Windows uygulamasi (.exe) uretir.
REM  Bu dosyaya CIFT TIKLAYIN. Baska hicbir sey yapmaniza gerek yoktur.
REM
REM  Sonuc : dist\NextGen Detector\NextGen Detector.exe
REM  Sure  : ilk seferde 5-15 dakika (paketler indirilir).
REM
REM  BU DOSYADAKI METINLER BILEREK TURKCE HARF ICERMEZ.
REM  Windows konsolunun kod sayfasi (cp857 / cp1254) her Turkce harfi
REM  tasimaz; tasimadigi bir harf yuzunden satirlar okunamaz hale gelir.
REM  Ayrica dosyanin saf ASCII olmasi, asagidaki "chcp 65001" satirinin
REM  betigi bozmasini onler. tests/test_paketleme.py bunu korur.
REM ============================================================================
setlocal enabledelayedexpansion

cd /d "%~dp0.."
if errorlevel 1 goto :klasor_hatasi
set "DEPO=%CD%"

echo.
echo ==============================================================
echo   NextGen Detector - Windows uygulamasi uretiliyor
echo ==============================================================
echo.

REM --------------------------------------------------------------------------
REM  ADIM 1 - Klasor yolu cok derin mi?
REM
REM  Windows'ta bir dosya yolu 260 karakteri gecemez. Uretim sirasinda bu
REM  klasorun altinda uzun adlar olusur (dist\NextGen Detector\_internal\...);
REM  klasor zaten derindeyse uretim "dosya bulunamadi" gibi, sebebi hic
REM  anlasilmayan bir hatayla kirilir.
REM --------------------------------------------------------------------------
set "SAYILAN=%DEPO%"
set /a UZUNLUK=0
:yol_say
if not defined SAYILAN goto :yol_sayildi
set "SAYILAN=!SAYILAN:~1!"
set /a UZUNLUK+=1
goto :yol_say
:yol_sayildi

echo   [1/6] Klasor yolu denetleniyor (%UZUNLUK% karakter)...
if %UZUNLUK% GTR 80 (
    echo.
    echo   [UYARI] Bu klasorun yolu cok uzun. Uretim yarida kirilabilir.
    echo.
    echo           Onerilen cozum: proje klasorunun TAMAMINI C:\NextGen
    echo           altina tasiyin, sonra bu dosyaya oradan cift tiklayin.
    echo.
    echo   Yine de denemek icin bir tusa basin, vazgecmek icin pencereyi
    echo   kapatin.
    pause
)

REM --------------------------------------------------------------------------
REM  ADIM 2 - Python bulunuyor mu?
REM
REM  DIKKAT: "where python" Windows 10/11'de HER ZAMAN basarili olur. Python
REM  kurulu olmasa bile Microsoft Store takma adi (sifir baytlik python.exe)
REM  PATH'tedir; calistirilinca Magaza penceresi acilir ve hicbir sey
REM  uretilmez. Bu yuzden once py.exe launcher denenir ("Add to PATH"
REM  isaretlenmese de kurulur) ve adayin gercekten Python oldugu
REM  "import sys" ile DOGRULANIR. Ayni cozum Baslat-Windows.bat'ta da var.
REM --------------------------------------------------------------------------
set "PY="
py -3 -c "import sys" >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
    goto :python_bulundu
)
python -c "import sys" >nul 2>nul
if %errorlevel%==0 (
    set "PY=python"
    goto :python_bulundu
)
goto :python_yok
:python_bulundu

REM --------------------------------------------------------------------------
REM  ADIM 2 (devam) - Python surumu yeterli mi? (3.11 ve ustu)
REM  Tirnak icindeki ">" isareti yonlendirme sayilmaz, oldugu gibi gecer.
REM --------------------------------------------------------------------------
echo   [2/6] Python surumu denetleniyor...
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :surum_eski

REM --------------------------------------------------------------------------
REM  ADIM 3 - Yalitilmis Python ortami
REM --------------------------------------------------------------------------
if not exist "%DEPO%\.venv\Scripts\python.exe" (
    echo   [3/6] Yalitilmis Python ortami kuruluyor...
    %PY% -m venv "%DEPO%\.venv"
    if errorlevel 1 goto :ortam_hatasi
) else (
    echo   [3/6] Yalitilmis Python ortami zaten var.
)
set "VPY=%DEPO%\.venv\Scripts\python.exe"
if not exist "%VPY%" goto :ortam_hatasi

REM Ortam DOSYA olarak duruyor ama CALISIYOR mu? Bilgisayardaki Python
REM guncellenince ya da kaldirilinca .venv icindeki python calismaz hale
REM gelir, dosya ise yerinde durur. Bakilmazsa asagidaki pip adimi
REM "internet yok" gibi, sebebi hic ilgisiz bir hatayla kirilirdi.
"%VPY%" -c "pass" >nul 2>nul
if errorlevel 1 goto :ortam_bozuk

REM --------------------------------------------------------------------------
REM  ADIM 4 - Paketler (sistemin kendisi + paketleme araci)
REM --------------------------------------------------------------------------
echo   [4/6] Gerekli paketler kuruluyor - en uzun adim bu, bekleyin...
"%VPY%" -m pip install --upgrade pip --progress-bar off
if errorlevel 1 goto :paket_hatasi
"%VPY%" -m pip install -r "%DEPO%\backend\requirements.txt" --progress-bar off
if errorlevel 1 goto :paket_hatasi
"%VPY%" -m pip install -r "%DEPO%\paketleme\requirements-paketleme.txt" --progress-bar off
if errorlevel 1 goto :paket_hatasi

REM --------------------------------------------------------------------------
REM  ADIM 5 ve 6 - Uretim ve temizlik
REM --------------------------------------------------------------------------
if exist "%DEPO%\build" rmdir /s /q "%DEPO%\build"
if exist "%DEPO%\dist" rmdir /s /q "%DEPO%\dist"

REM Uretim ciktisindaki Turkce harfler bozulmasin: konsolu ve Python'u ayni
REM kodlamaya (UTF-8) getir. Bu satir bilerek EN SONA birakildi; kod sayfasi
REM degistikten sonra bazi komutlarin ciktisi okunamaz olabiliyor.
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo   [5/6] Uygulama uretiliyor - ekran arada sessiz kalabilir, bekleyin...
"%VPY%" -m PyInstaller --noconfirm --clean "%DEPO%\paketleme\NextGenDetector-windows.spec"
if errorlevel 1 goto :uretim_hatasi

set "URUN=%DEPO%\dist\NextGen Detector\NextGen Detector.exe"
if not exist "%URUN%" goto :urun_yok

echo   [6/6] Gecici klasorler siliniyor...
if exist "%DEPO%\build" rmdir /s /q "%DEPO%\build"
"%VPY%" -c "import pathlib; t=sum(f.stat().st_size for f in pathlib.Path('dist').rglob('*') if f.is_file()); print(f'         Boyut: {t/1048576:.0f} MB')"

echo.
echo ==============================================================
echo   TAMAM - uygulama hazir.
echo ==============================================================
echo.
echo   Klasor: dist\NextGen Detector
echo   Icindeki "NextGen Detector.exe" dosyasina cift tiklayin.
echo.
echo   BASKA BILGISAYARA VERIRKEN: klasorun TAMAMINI kopyalayin,
echo   yalniz .exe dosyasini degil.
echo.
echo   Ilk acilista Windows "bilinmeyen yayinci" uyarisi verebilir:
echo   once "Daha fazla bilgi", sonra "Yine de calistir" dugmesine basin.
echo.
explorer "%DEPO%\dist"
goto :son


REM ==========================================================================
REM  Hata cikislari - hepsi :son_hata'ya gider, pencere KAPANMAZ.
REM ==========================================================================

:klasor_hatasi
echo.
echo   [HATA] Proje klasorune girilemedi.
echo   Bu dosya, proje klasorundeki "paketleme" klasorunun icinde durmali.
goto :son_hata

:python_yok
echo.
echo   [HATA] Python bulunamadi.
echo.
echo   https://www.python.org/downloads/ adresinden Python 3.12 kurun.
echo   Kurulum ekranindaki "Add Python to PATH" kutusunu MUTLAKA isaretleyin,
echo   sonra bu dosyaya yeniden cift tiklayin.
echo.
echo   NOT: Microsoft Store'da gorunen "Python" ise yaramaz; yukaridaki
echo   adresten kurun.
goto :son_hata

:surum_eski
echo.
echo   [HATA] Bu bilgisayardaki Python surumu cok eski (3.11 veya ustu gerekli).
echo.
echo   https://www.python.org/downloads/ adresinden Python 3.12 kurun,
echo   sonra bu dosyaya yeniden cift tiklayin.
goto :son_hata

:ortam_hatasi
echo.
echo   [HATA] Yalitilmis Python ortami kurulamadi.
echo.
echo   En sik sebep: klasore yazma izni yok. Proje klasorunu Masaustu'ne
echo   ya da C:\NextGen altina tasiyip tekrar deneyin.
goto :son_hata

:ortam_bozuk
echo.
echo   [HATA] Yalitilmis Python ortami bozulmus.
echo.
echo   En sik sebep: bilgisayardaki Python guncellendi ya da kaldirildi.
echo   Cozum: proje klasorundeki ".venv" klasorunu SILIN ve bu dosyaya
echo   yeniden cift tiklayin. Kayitlariniza hicbir sey olmaz.
goto :son_hata

:paket_hatasi
echo.
echo   [HATA] Gerekli paketler kurulamadi.
echo.
echo   En sik sebep: internet baglantisi yok ya da sirket guvenlik duvari
echo   indirmeyi engelliyor. Baglantiyi kontrol edip tekrar deneyin.
goto :son_hata

:uretim_hatasi
echo.
echo   [HATA] Uretim tamamlanamadi.
echo.
echo   Virus koruma yazilimi uretim sirasinda dosyalari kilitlemis olabilir.
echo   Windows Guvenligi ^> Virus ve tehdit korumasi ^> Ayarlari yonet
echo   bolumunden bu proje klasorunu "haric tutulan klasor" olarak ekleyip
echo   tekrar deneyin.
goto :son_hata

:urun_yok
echo.
echo   [HATA] Uretim bitti ama uygulama dosyasi ortada yok.
echo.
echo   Bu neredeyse her zaman Windows Defender'in yeni uretilen .exe
echo   dosyasini karantinaya almasindan olur.
echo.
echo   Cozum: Windows Guvenligi ^> Virus ve tehdit korumasi ^> Koruma
echo   gecmisi bolumunu acin, "NextGen Detector" satirini bulun ve
echo   "Cihazda izin ver" secin. Sonra bu dosyaya yeniden cift tiklayin.
goto :son_hata


:son_hata
echo.
echo   Bu pencere kendiliginden KAPANMAYACAK. Yukaridaki son satirlari
echo   kopyalayip destek icin gonderebilirsiniz.
echo.
pause
exit /b 1

:son
echo.
pause
exit /b 0
