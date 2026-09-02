"""Ayarların TEK kaynağı — kök dizindeki .env dosyasını okur.

Başka hiçbir dosya os.environ'a veya .env'e bakmaz; ayar gereken her yer
buradan bir `Ayarlar` nesnesi alır (CLAUDE.md §7: sabit kodlanmış eşik,
yol, IP yasak).

Eksik veya bozuk ayar, program açılışında anlaşılır Türkçe bir `AyarHatasi`
ile durdurur — sistem yarım ayarla ÇALIŞMAZ.
"""

from __future__ import annotations

import errno
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from app.hatalar import AyarHatasi

# Bu dosya backend/app/ içinde; iki üst klasör depo köküdür. Kontrol Paneli
# uvicorn'u backend/ içinden başlattığı için yollar çalışma dizinine göre
# DEĞİL, her zaman depo köküne göre çözülür.
_VARSAYILAN_KOK = Path(__file__).resolve().parents[2]

_ANONS_SECENEKLERI = ("null", "ses_karti", "http")
_CIHAZ_SECENEKLERI = ("cpu", "cuda")
_IYILESTIRME_SECENEKLERI = ("kapali", "otomatik")


@dataclass(frozen=True)
class Ayarlar:
    kok_dizin: Path
    veri_dizini: Path
    veritabani_yolu: Path
    goruntu_klasoru: Path
    log_dosyasi: Path
    olay_saklama_gun: int
    goruntu_saklama_gun: int
    kkd_ham_veri_saklama_gun: int
    sistem_olay_saklama_gun: int
    kkd_ornek_saat_limit: int
    disk_uyari_gb: int
    cikarim_cihazi: str
    kare_ornekleme_fps: int
    tespit_guven_esigi: float
    tespit_insan_guven_esigi: float
    tespit_nms_esigi: float
    tespit_en_kucuk_kenar_px: int
    goruntu_iyilestirme: str
    anons: str
    anons_http_adresi: str
    anons_bekleme_sn: int
    model_dosyasi: Path


def ayarlari_yukle(kok_dizin: Path | None = None) -> Ayarlar:
    """.env dosyasını okur, doğrular, gereken klasörleri oluşturur.

    Her doğrulama hatası, kullanıcının olduğu gibi okuyabileceği Türkçe
    bir AyarHatasi mesajıdır.
    """
    kok = (kok_dizin or _VARSAYILAN_KOK).resolve()
    env_yolu = kok / ".env"
    if not env_yolu.exists():
        raise AyarHatasi(
            f"Ayar dosyası bulunamadı: {env_yolu}\n"
            "Çözüm: .env.example dosyasını .env adıyla kopyalayın. "
            "(Kontrol Paneli'ndeki 'İlk Kurulumu Yap' düğmesi bunu otomatik yapar.)"
        )
    degerler = {a: (d or "").strip() for a, d in dotenv_values(env_yolu).items()}

    # Not: giriş şifresi bilerek YOK (docs/07 #0). Sistem tek makinede, yalnızca
    # 127.0.0.1'e bağlı çalışır; fabrika sunucusuna çıkmadan önce geri eklenir.

    # Not: sistemin portunu Kontrol Paneli belirler (8080). Bu yüzden .env'de
    # port ayarı YOKTUR — okunmayan bir ayar ekranda yanlış bilgi gösterirdi.

    # veri/ klasörünün yeri sabittir: Kontrol Paneli günlüğü veri/loglar/sistem.log
    # dosyasından okur ve yedekleme "veri/ klasörünü kopyala" diye tarif edilir.
    veri_dizini = kok / "veri"
    veritabani_yolu = kok / _metin(degerler, "VERITABANI_YOLU", "veri/dalsan.db")
    goruntu_klasoru = kok / _metin(degerler, "GORUNTU_KLASORU", "veri/goruntuler")
    log_dosyasi = veri_dizini / "loglar" / "sistem.log"

    for klasor in (veritabani_yolu.parent, goruntu_klasoru, log_dosyasi.parent):
        _klasor_olustur(klasor)

    anons = _secenek(degerler, "ANONS", varsayilan="null", secenekler=_ANONS_SECENEKLERI)
    anons_http_adresi = degerler.get("ANONS_HTTP_ADRESI", "")
    if anons == "http":
        if not anons_http_adresi:
            raise AyarHatasi(
                ".env dosyasında ANONS=http seçilmiş ama ANONS_HTTP_ADRESI boş. "
                "Anons sunucusunun adresini yazın veya ANONS=null yapın."
            )
        # Şemasız adres (ör. '10.0.0.5/anons') urllib'de her ihlalde ValueError
        # fırlatırdı; hatayı açılışta ve anlaşılır biçimde ver.
        if not anons_http_adresi.startswith(("http://", "https://")):
            raise AyarHatasi(
                ".env dosyasında ANONS_HTTP_ADRESI http:// veya https:// ile başlamalı; "
                f"şu an '{anons_http_adresi}' yazıyor. Örnek: http://10.0.0.9:8080/anons"
            )

    return Ayarlar(
        kok_dizin=kok,
        veri_dizini=veri_dizini,
        veritabani_yolu=veritabani_yolu,
        goruntu_klasoru=goruntu_klasoru,
        log_dosyasi=log_dosyasi,
        olay_saklama_gun=_tam_sayi(degerler, "OLAY_SAKLAMA_GUN", 180, 1, 3650),
        goruntu_saklama_gun=_tam_sayi(degerler, "GORUNTU_SAKLAMA_GUN", 90, 1, 3650),
        kkd_ham_veri_saklama_gun=_tam_sayi(degerler, "KKD_HAM_VERI_SAKLAMA_GUN", 30, 1, 3650),
        sistem_olay_saklama_gun=_tam_sayi(degerler, "SISTEM_OLAY_SAKLAMA_GUN", 90, 1, 3650),
        # KKD veri toplama: kamera başına saatte en çok kaç kişi görüntüsü
        # örneklenir (docs/04 §4.3 — aynı kişinin 200 ardışık karesi değil)
        kkd_ornek_saat_limit=_tam_sayi(degerler, "KKD_ORNEK_SAAT_LIMIT", 60, 1, 3600),
        # Boş disk bu değerin altına inince sistem olayı üretilir (docs/08 R8)
        disk_uyari_gb=_tam_sayi(degerler, "DISK_UYARI_GB", 5, 1, 1000),
        cikarim_cihazi=_secenek(degerler, "CIKARIM_CIHAZI", "cpu", _CIHAZ_SECENEKLERI),
        # Yeni kameranın varsayılan örnekleme hızı (kamera formunda değiştirilebilir)
        kare_ornekleme_fps=_tam_sayi(degerler, "KARE_ORNEKLEME_FPS", 6, 1, 30),
        # Tespit eşikleri: sahaya göre ayarlanır, koda gömülmez (CLAUDE.md §7).
        # Düşük eşik = daha çok tespit + daha çok yanlış alarm. İnsan eşiği ayrı
        # tutulur: kaçırılan insan, kaçırılan araçtan daha risklidir (docs/00).
        tespit_guven_esigi=_ondalik(degerler, "TESPIT_GUVEN_ESIGI", 0.35, 0.05, 0.95),
        tespit_insan_guven_esigi=_ondalik(degerler, "TESPIT_INSAN_GUVEN_ESIGI", 0.28, 0.05, 0.95),
        tespit_nms_esigi=_ondalik(degerler, "TESPIT_NMS_ESIGI", 0.45, 0.1, 0.9),
        # Bu kenar uzunluğundan küçük kutular atılır: uzaktaki birkaç piksellik
        # gürültü insan sanılıp yanlış alarm üretmesin
        tespit_en_kucuk_kenar_px=_tam_sayi(degerler, "TESPIT_EN_KUCUK_KENAR_PX", 12, 2, 500),
        # Düşük kaliteli fabrika kamerası için yerel kontrast dengeleme (CLAHE)
        goruntu_iyilestirme=_secenek(
            degerler, "GORUNTU_IYILESTIRME", "kapali", _IYILESTIRME_SECENEKLERI
        ),
        anons=anons,
        anons_http_adresi=anons_http_adresi,
        # Anons, ekran uyarısından bağımsız ve daha seyrek çalar (docs/02 §7):
        # hoparlör aynı kamera+mesaj için bu süre dolmadan tekrar bağırmaz.
        anons_bekleme_sn=_tam_sayi(degerler, "ANONS_BEKLEME_SN", 30, 5, 3600),
        model_dosyasi=kok / _metin(degerler, "MODEL_DOSYASI", "models/yolox_tiny.onnx"),
    )


def _metin(degerler: dict, anahtar: str, varsayilan: str) -> str:
    """Boş bırakılan anahtar da varsayılana düşer ('VERITABANI_YOLU=' gibi)."""
    return degerler.get(anahtar, "") or varsayilan


def _ondalik(degerler: dict, anahtar: str, varsayilan: float, en_az: float, en_cok: float) -> float:
    """Ondalık ayar. Virgül de kabul edilir: kullanıcı '0,35' yazabilir."""
    ham = (degerler.get(anahtar, "") or "").replace(",", ".")
    if not ham:
        return varsayilan
    try:
        sayi = float(ham)
    except ValueError:
        raise AyarHatasi(
            f".env dosyasında {anahtar} bir ondalık sayı olmalı; şu an '{ham}' yazıyor."
        ) from None
    if not en_az <= sayi <= en_cok:
        raise AyarHatasi(
            f".env dosyasında {anahtar} {en_az} ile {en_cok} arasında olmalı; şu an {sayi} yazıyor."
        )
    return sayi


def _tam_sayi(degerler: dict, anahtar: str, varsayilan: int, en_az: int, en_cok: int) -> int:
    ham = degerler.get(anahtar, "")
    if not ham:
        return varsayilan
    try:
        sayi = int(ham)
    except ValueError:
        raise AyarHatasi(
            f".env dosyasında {anahtar} bir tam sayı olmalı; şu an '{ham}' yazıyor."
        ) from None
    if not en_az <= sayi <= en_cok:
        raise AyarHatasi(
            f".env dosyasında {anahtar} {en_az} ile {en_cok} arasında olmalı; şu an {sayi} yazıyor."
        )
    return sayi


def _secenek(degerler: dict, anahtar: str, varsayilan: str, secenekler: tuple[str, ...]) -> str:
    ham = degerler.get(anahtar, "")
    if not ham:
        return varsayilan
    if ham not in secenekler:
        raise AyarHatasi(
            f".env dosyasında {anahtar} şunlardan biri olmalı: "
            f"{', '.join(secenekler)}. Şu an '{ham}' yazıyor."
        )
    return ham


def _klasor_olustur(klasor: Path) -> None:
    try:
        klasor.mkdir(parents=True, exist_ok=True)
    except OSError as hata:
        sebep = {
            errno.EACCES: "izin yok",
            errno.EROFS: "disk salt okunur",
            errno.ENOSPC: "disk dolu",
        }.get(hata.errno, hata.strerror or str(hata))
        raise AyarHatasi(f"{klasor} klasörü oluşturulamadı: {sebep}") from hata
