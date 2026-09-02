"""Mac ve Windows üretim tariflerinin ORTAK bölümü.

NEDEN AYRI BİR DOSYA — iki `.spec` dosyası aynı listeleri kopyala-yapıştır
taşısaydı zamanla ayrışırdı: birine yeni bir şablon klasörü eklenir, diğerine
unutulur ve HATA yalnızca o platformda, üstelik ancak uygulama açılmayınca
görülürdü (paketlenmiş programın çıktısı hiçbir yere gitmez). Bu yüzden
"pakete ne konacak" sorusunun cevabı TEK yerde, burada durur.

Platforma özel olan ne varsa ilgili `.spec` dosyasında kalır:

* macOS: `.app` kabuğu (BUNDLE), kamera izni metinleri, `.icns` simgesi ve
  OpenSSL çakışması düzeltmesi (`otool` yalnız macOS'ta vardır).
* Windows: `.ico` simgesi, gizli konsol penceresi ve açılış hatası kancası.

Bu dosya PyInstaller tarafından ÇALIŞTIRILMAZ; `.spec` dosyaları onu normal
bir Python modülü gibi okur.
"""

import sys
from pathlib import Path

# Kullanıcının gördüğü ürün adı. Uygulama dosyasının adı da budur.
UYGULAMA_ADI = "NextGen Detector"

# Programın giriş noktası: çift tıklanınca açılan Kontrol Paneli penceresi.
GIRIS_BETIGI = ("masaustu", "dalsan_launcher.py")


def giris_betigi(depo: Path) -> str:
    """Paketlenecek programın başlangıç dosyası (iki platformda da aynıdır)."""
    return str(depo.joinpath(*GIRIS_BETIGI))


def veri_dosyalari(depo: Path) -> list[tuple[str, str]]:
    """Pakete KOD OLMAYAN dosyalar: şablon, stil, şema, örnek ayar.

    TUZAK: PyInstaller yalnızca `import` edilen .py dosyalarını toplar;
    .html, .css, .js, .sql dosyalarını GÖRMEZ. Unutulursa uygulama açılır
    açılmaz "şablon bulunamadı" ile çöker.

    Klasör düzeni depodakiyle AYNI tutulur, çünkü app/kaynaklar.py yolları
    depo köküne göre çözer (`kaynak_yolu("backend", "sema")` gibi).
    """
    backend = depo / "backend"
    return [
        (str(backend / "app" / "web" / "templates"), "backend/app/web/templates"),
        (str(backend / "app" / "web" / "static"), "backend/app/web/static"),
        (str(backend / "sema"), "backend/sema"),
        # Paketlenmiş programda .env kullanıcı klasöründe, bu örnekten üretilir.
        (str(depo / ".env.example"), "."),
    ]


def gizli_moduller(depo: Path) -> list[str]:
    """PyInstaller'ın kodu tarayarak BULAMAYACAĞI modüller.

    TUZAK: uvicorn bazı parçalarını adıyla yükler — `http="auto"` ayarı
    aslında "uvicorn.protocols.http.auto" METNİDİR. Tarayıcı bunu bir import
    olarak göremez, modülü pakete koymaz ve sunucu hiç açılmaz.
    """
    backend = depo / "backend"
    # `app` paketi backend/ altındadır; collect_submodules onu bulabilsin.
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from PyInstaller.utils.hooks import collect_submodules

    return [
        # Sistemin kendi modülleri: bir kısmı (analiz süpervizörü, kural
        # motoru) ancak çalışma anında import edilir.
        *collect_submodules("app"),
        # uvicorn'un metinle yüklediği parçalar.
        "uvicorn.lifespan.off",
        "uvicorn.lifespan.on",
        "uvicorn.loops.asyncio",
        "uvicorn.loops.auto",
        "uvicorn.loops.uvloop",
        "uvicorn.logging",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.protocols.websockets.wsproto_impl",
        # Kontrol Paneli penceresi.
        "tkinter",
        "tkinter.font",
        "tkinter.scrolledtext",
    ]


# Pakete KONMAYACAKLAR — yalnızca geliştirme/test araçları.
#
# Görüntü işleme zinciri (numpy, opencv, onnxruntime, supervision) ve
# supervision'ın zorunlu bağımlılıkları ÇIKARILAMAZ: scipy ByteTrack'in Kalman
# filtresi için, matplotlib supervision.draw.color için ÇALIŞMA ANINDA
# yüklenir. Boyut küçültmek uğruna çıkarılırlarsa tespit ilk karede çöker.
disarida = [
    "pytest",
    "_pytest",
    "httpx",
    "IPython",
    "notebook",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "wx",
]


def yaz(mesaj: str) -> None:
    """Üretim sırasında ekrana satır düşürür.

    TUZAK (Windows): konsolun varsayılan kod sayfası cp857/cp1254'tür ve
    Türkçe harfleri olmayan bir kod sayfasında `print` UnicodeEncodeError
    verir — üretim, hiç ilgisi olmayan bir hatayla YARIDA KESİLİR. Burada
    yazılamayan harf '?' olur, üretim devam eder.
    """
    try:
        print(mesaj)
    except UnicodeEncodeError:
        print(mesaj.encode("ascii", "replace").decode("ascii"))
