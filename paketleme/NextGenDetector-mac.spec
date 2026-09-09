# -*- mode: python ; coding: utf-8 -*-
"""Mac uygulaması (.app) üretim tarifi — PyInstaller.

    Üretmek için:  paketleme/Mac-Uygulama-Uret.command dosyasına çift tıklayın.
    Elle:          .venv/bin/python -m PyInstaller --noconfirm --clean \
                       paketleme/NextGenDetector-mac.spec

Sonuç: dist/NextGen Detector.app  — kullanıcı buna çift tıklar, Kontrol Paneli
açılır, "Sistemi Başlat" der. Python kurmasına, pip çalıştırmasına gerek yoktur.

Windows karşılığı: paketleme/NextGenDetector-windows.spec. İki tarifin ORTAK
bölümü (pakete konacak dosyalar, gizli modüller, dışarıda kalanlar) tek yerde,
paketleme_ortak.py içindedir; burada yalnızca macOS'a özel olanlar kalır.

MACOS'A ÖZEL İKİ TUZAK VE ÇÖZÜMLERİ (buraya not düşülmezse tekrar yaşanır):

1. macOS KAMERA İZNİ SESSİZ REDDEDİLİR. Info.plist içinde
   NSCameraUsageDescription yoksa işletim sistemi kamera erişimini
   kullanıcıya HİÇ sormadan reddeder; ekranda yalnızca "görüntü yok" görünür.
   → BUNDLE(info_plist=...).

2. AYNI ADLI İKİ KÜTÜPHANE — biri diğerini eziyordu. opencv-python kendi
   OpenSSL kopyasını (libcrypto.3.dylib, sürüm 3.0) yanında getirir;
   Python'un `_ssl` modülü ise sistemdeki YENİ OpenSSL'e (3.6) bağlıdır.
   PyInstaller ikisini aynı adla görüp tekine bağladığı için `_ssl`
   yüklenemiyor, program açılır açılmaz şu hatayı veriyordu:
       Symbol not found: _X509_STORE_get1_objects
   Sonuç: sistem hiç başlamıyor, model de inemiyordu (indirme HTTPS'tir).
   → `_openssl_cakismasini_gider`: her iki kütüphane de pakete konur;
     opencv kendi kopyasını (cv2/.dylibs/…), `_ssl` kendi kopyasını kullanır.
   Bu düzeltme Windows tarifine TAŞINMAZ: orada opencv OpenSSL getirmez.

(Şablon/şema dosyalarının ve uvicorn'un metinle yüklediği modüllerin tuzağı
ortak bölümde anlatılıyor — paketleme_ortak.py.)

Simge: backend/app/web/static/logo.svg dosyasından bir kez üretilmiştir
(paketleme/NextGenDetector.icns). Yeniden üretmek gerekirse:

    qlmanage -t -s 1024 -o /tmp/ikon backend/app/web/static/logo.svg
    mkdir /tmp/ikon/NextGenDetector.iconset
    for b in 16 32 128 256 512; do
      sips -z $b $b /tmp/ikon/logo.svg.png \
        --out /tmp/ikon/NextGenDetector.iconset/icon_${b}x${b}.png
      sips -z $((b*2)) $((b*2)) /tmp/ikon/logo.svg.png \
        --out /tmp/ikon/NextGenDetector.iconset/icon_${b}x${b}@2x.png
    done
    iconutil -c icns /tmp/ikon/NextGenDetector.iconset \
        -o paketleme/NextGenDetector.icns
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

DEPO = Path(SPECPATH).resolve().parent          # noqa: F821  (SPECPATH: PyInstaller)
BACKEND = DEPO / "backend"

# Ortak bölüm — iki tarif de buradan okur, kopyala-yapıştır yoktur.
sys.path.insert(0, SPECPATH)                    # noqa: F821
import paketleme_ortak as ortak                 # noqa: E402

sys.path.pop(0)


# ---------------------------------------------------------------- OpenSSL çakışması
def _sslin_kullandigi_openssl() -> dict:
    """Python'un `_ssl` modülünün GERÇEKTEN bağlı olduğu OpenSSL dosyaları.

    Dönen sözlük: {"libcrypto.3.dylib": "/…/gerçek/yol", …}
    """
    tanim = importlib.util.find_spec("_ssl")
    if tanim is None or not tanim.origin:
        return {}
    try:
        cikti = subprocess.run(
            ["otool", "-L", tanim.origin], capture_output=True, text=True, check=False
        ).stdout
    except FileNotFoundError:
        # `otool` Xcode komut satırı araçlarıyla gelir. Yoksa ham İngilizce
        # bir traceback yerine ne yapılacağı yazılır (CLAUDE.md §8).
        raise SystemExit(
            "[paketleme] HATA: 'otool' bulunamadi.\n"
            "Bu arac Xcode komut satiri araclariyla gelir ve uygulama uretimi\n"
            "icin gereklidir. Terminal'e su satiri yazip kurulumu tamamlayin,\n"
            "sonra Mac-Uygulama-Uret.command dosyasina yeniden cift tiklayin:\n"
            "    xcode-select --install"
        ) from None
    bulunan = {}
    for satir in cikti.splitlines()[1:]:
        yol = Path(satir.strip().split(" (")[0])
        if yol.name.startswith(("libssl.", "libcrypto.")) and yol.is_absolute():
            gercek = yol.resolve()
            if gercek.is_file():
                bulunan[yol.name] = str(gercek)
    return bulunan


def _openssl_cakismasini_gider(analiz_nesnesi) -> None:
    """Kök klasördeki OpenSSL kısayolunu gerçek dosyayla değiştirir (tuzak 2).

    PyInstaller aynı adlı iki kütüphaneden birini seçer, diğerinin yerine
    kısayol (SYMLINK) koyar ve o kısayolu `datas` listesine yazar — `binaries`
    listesine DEĞİL. Burada kısayol silinip `_ssl`'in ihtiyacı olan sürüm
    gerçek dosya olarak konur; opencv'nin kendi kopyası cv2/.dylibs altında
    el değmeden kalır, yani iki tüketici de doğru sürümü kullanır.
    """
    if sys.platform != "darwin":
        # Bu tuzak macOS'a özeldir (.dylib) ve düzeltme yalnızca Mac'te
        # ÜRETİM yaparken anlamlıdır. Çıkış burada duruyor ki tarif başka bir
        # işletim sisteminde de ÇALIŞTIRILABİLSİN: testler tarifi sahte bir
        # PyInstaller ile koşturup yazım hatası / eksik değişken arıyor
        # (tests/test_mac_uygulamasi.py). Windows tarifi için bu zaten
        # yapılıyordu; Mac tarifi otool'a takıldığı için yapılamıyordu ve
        # tarifteki bir yazım hatası ancak KULLANICININ Mac'inde görülürdü.
        return
    dogru = _sslin_kullandigi_openssl()
    if not dogru:
        # Sessizce geçilirse uygulama üretilir ama AÇILMAZ: `_ssl` yüklenemez,
        # model de inemez (indirme HTTPS'tir). Üretimi burada durdurmak, hatayı
        # kullanıcının bilgisayarında keşfetmekten çok daha ucuzdur.
        raise SystemExit(
            "[paketleme] HATA: Python'un `_ssl` modulunun OpenSSL bagimliligi\n"
            "cozulemedi; opencv'nin eski OpenSSL kopyasi onu ezer ve uygulama\n"
            "acilmaz. .spec dosyasindaki 2. tuzagi okuyun."
        )
    degisen = []
    kalan_datas = []
    for hedef, kaynak, tur in analiz_nesnesi.datas:
        if tur == "SYMLINK" and hedef in dogru:
            analiz_nesnesi.binaries.append((hedef, dogru[hedef], "BINARY"))
            degisen.append(hedef)
        else:
            kalan_datas.append((hedef, kaynak, tur))
    analiz_nesnesi.datas = kalan_datas
    if not degisen:
        # Sessizce geçilirse hata GERİ GELİR ve ancak uygulama açılmayınca
        # fark edilir; üretimi burada durdurmak çok daha ucuz.
        raise SystemExit(
            "[paketleme] HATA: OpenSSL kısayolu bulunamadı. PyInstaller'ın "
            "davranışı değişmiş olabilir; .spec dosyasındaki 2. tuzağı okuyun."
        )
    ortak.yaz(f"[paketleme] OpenSSL çakışması giderildi: {', '.join(degisen)}")


analiz = Analysis(                                          # noqa: F821
    [ortak.giris_betigi(DEPO)],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=ortak.veri_dosyalari(DEPO),
    hiddenimports=ortak.gizli_moduller(DEPO),
    hookspath=[],
    hooksconfig={},
    # Açılış kancası: `.app` Finder'dan açıldığında stdout/stderr HİÇBİR YERE
    # gitmez. Kanca olmadan, açılışta çöken uygulama sessizce hiç açılmıyor
    # gibi görünür — kullanıcı "uygulamayı göremedim" der, sebep hiçbir yerde
    # yazmaz. Kanca hatayı dosyaya yazar ve macOS uyarı penceresi gösterir.
    runtime_hooks=[str(DEPO / "paketleme" / "acilis_kancasi.py")],
    excludes=ortak.disarida,
    noarchive=False,
    optimize=0,
)

_openssl_cakismasini_gider(analiz)

pyz = PYZ(analiz.pure)                                      # noqa: F821

exe = EXE(                                                  # noqa: F821
    pyz,
    analiz.scripts,
    [],
    exclude_binaries=True,
    name=ortak.UYGULAMA_ADI,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # pencereli uygulama: terminal açılmaz
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

app = BUNDLE(                                               # noqa: F821
    coll,
    name=f"{ortak.UYGULAMA_ADI}.app",
    icon=str(DEPO / "paketleme" / "NextGenDetector.icns"),
    bundle_identifier="com.nextgen.detector",
    info_plist={
        "CFBundleName": ortak.UYGULAMA_ADI,
        "CFBundleDisplayName": ortak.UYGULAMA_ADI,
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        # Bu iki anahtar olmadan macOS erişimi kullanıcıya SORMADAN reddeder.
        "NSCameraUsageDescription": (
            "Fabrikadaki kameralardan görüntü almak için kullanılır."
        ),
        "NSLocalNetworkUsageDescription": (
            "Fabrikadaki IP kameralara bağlanmak için kullanılır."
        ),
    },
)
