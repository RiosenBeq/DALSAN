# -*- mode: python ; coding: utf-8 -*-
"""Windows uygulaması (.exe) üretim tarifi — PyInstaller.

    Üretmek için:  paketleme\\Windows-Uygulama-Uret.bat dosyasına ÇİFT TIKLAYIN.
    Elle:          .venv\\Scripts\\python.exe -m PyInstaller --noconfirm --clean ^
                       paketleme\\NextGenDetector-windows.spec

ÖNEMLİ — bu dosya YALNIZCA Windows'ta çalıştırılabilir. PyInstaller çapraz
derleme yapmaz: Mac'te Windows uygulaması üretilemez. Üretim, uygulamanın
çalışacağı Windows bilgisayarda yapılır.

Sonuç: dist\\NextGen Detector\\  klasörü. İçinde iki şey vardır:

    NextGen Detector.exe   ← kullanıcı buna çift tıklar
    _internal\\             ← programın parçaları, dokunulmaz

KLASÖR MÜ, TEK DOSYA MI — bilerek klasör (onedir) seçildi:
  * Tek dosya (onefile) her açılışta 240 MB'ı geçici klasöre AÇAR; açılış
    her seferinde yarım dakika uzar, üstelik zaten uzun olan ilk açılışa
    eklenir.
  * Virüs koruma yazılımları, kendini açan tek dosyalık programları çok daha
    sık "şüpheli" işaretler.
  * PyInstaller 6 ile klasörün görünen tek dosyası zaten .exe'dir; geri
    kalan her şey `_internal` içindedir. Kullanıcı yanlış dosyaya tıklayamaz.
Teslim ederken KLASÖRÜN TAMAMI kopyalanır (bkz. docs/13).

WINDOWS'A ÖZGÜ ÜÇ NOKTA (Mac tarifinden farkı budur):

1. `.app` KABUĞU YOKTUR. macOS'un BUNDLE adımı ve Info.plist izin metinleri
   Windows'ta karşılıksızdır; kamera izni diye bir kavram yoktur.

2. SİMGE `.ico` OLMALIDIR. Windows `.icns` okumaz. Simge, Mac simgesiyle
   AYNI çizimden üretilmiştir (bkz. aşağıdaki not).

3. KONSOL PENCERESİ GİZLİ (`console=False`) AMA HATA GÖRÜNÜR. Gizli konsolun
   bedeli ağırdır: `sys.stdout` ve `sys.stderr` yok olur, program açılırken
   çökerse kullanıcı EKRANDA HİÇBİR ŞEY GÖRMEZ. Bu yüzden bir açılış
   kancası takılıyor (paketleme/windows_acilis_kancasi.py): kayıp çıkış
   akışlarını dosyaya bağlar, yakalanmamış hatayı ayrıntısıyla
   veri/loglar/acilis-hatasi.log dosyasına yazar ve kullanıcıya Türkçe bir
   uyarı penceresi gösterip dosyanın yerini söyler.

MAC'TEKİ OPENSSL DÜZELTMESİ BURADA YOKTUR ve olmamalıdır: o sorun,
opencv'nin macOS'ta yanında getirdiği eski `libcrypto.3.dylib` dosyasının
Python'un `_ssl` modülünü ezmesinden çıkıyordu. Windows'ta opencv OpenSSL
taşımaz; düzeltmeyi taşımak, olmayan bir sorunu "çözmeye" çalışıp üretimi
durdururdu.

Simge: backend/app/web/static/logo.svg → paketleme/NextGenDetector.ico
(Mac simgesinin çizimiyle aynı; bir kez üretildi). Yeniden üretmek gerekirse
Mac'te:

    iconutil -c iconset paketleme/NextGenDetector.icns -o /tmp/ngd.iconset
    .venv/bin/python -c "from PIL import Image; \
        Image.open('/tmp/ngd.iconset/icon_512x512.png').convert('RGBA').save( \
        'paketleme/NextGenDetector.ico', sizes=[(16,16),(24,24),(32,32), \
        (48,48),(64,64),(128,128),(256,256)])"
"""

import sys
from pathlib import Path

DEPO = Path(SPECPATH).resolve().parent          # noqa: F821  (SPECPATH: PyInstaller)
BACKEND = DEPO / "backend"

# Ortak bölüm (pakete konacak dosyalar, gizli modüller, dışarıda kalanlar)
# iki tarifte de aynıdır ve TEK yerde durur — bkz. paketleme_ortak.py.
sys.path.insert(0, SPECPATH)                    # noqa: F821
import paketleme_ortak as ortak                 # noqa: E402

sys.path.pop(0)

analiz = Analysis(                                          # noqa: F821
    [ortak.giris_betigi(DEPO)],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=ortak.veri_dosyalari(DEPO),
    hiddenimports=ortak.gizli_moduller(DEPO),
    hookspath=[],
    hooksconfig={},
    # Asıl program başlamadan önce çalışır: gizli konsolun yuttuğu hataları
    # dosyaya ve kullanıcının ekranına çıkarır (3. nokta).
    runtime_hooks=[str(DEPO / "paketleme" / "windows_acilis_kancasi.py")],
    excludes=ortak.disarida,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analiz.pure)                                      # noqa: F821

exe = EXE(                                                  # noqa: F821
    pyz,
    analiz.scripts,
    [],
    exclude_binaries=True,
    name=ortak.UYGULAMA_ADI,
    icon=str(DEPO / "paketleme" / "NextGenDetector.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX sıkıştırması virüs koruma uyarılarını artırır
    console=False,      # siyah komut penceresi açılmaz (bkz. 3. nokta)
    # True olsaydı PyInstaller'ın hata penceresi hiç görünmezdi; açılış
    # kancası devre dışı kalırsa geriye kalan tek uyarı yolu budur.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(                                             # noqa: F821
    exe,
    analiz.binaries,
    analiz.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=ortak.UYGULAMA_ADI,
)
