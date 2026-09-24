"""Tespit modelini ilk açılışta otomatik indirir (models/indir.sh ile aynı kaynak).

Model ağırlıkları depoya girmez (CLAUDE.md §7). Kullanıcı terminal komutu
çalıştırmasın diye (CLAUDE.md §8) eksik model, sistem açılırken BİR KEZ
indirilir. Yalnızca bilinen dosyalar iner (YOLOX'un resmi yayını ve bu deponun
forklift modeli yayını), ikisi de SHA-256 ile doğrulanır; başka bir ad
verilmişse indirilmez, kullanıcıya dosyayı kendisinin koyması söylenir.
"""

from __future__ import annotations

import hashlib
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from app import kaynaklar
from app.analiz.model_adi import (
    YEREL_FORKLIFT_ADI,
    gorunen_model_adi,
    hazir_modele_donus,
    yerel_forklift_tabani,
)
from app.hatalar import DalsanHata

# ADR-002: Apache-2.0 lisanslı YOLOX resmi yayınları (models/indir.sh ile aynı)
_YAYIN_ADRESI = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/"

# Forklift tanıyan modeller (egitim/forklift, docs/17 §12.3): resmi YOLOX modeli
# ile LOCO (CC0 1.0) verisinden eğitilen ek baş, tek ONNX'te. Bu deponun kendi
# yayınından (GitHub Release) iner. Yerel dosya adı sürüm taşır: yeni eğitim yeni
# ad demektir; var olan dosya yeniden indirilmediği için diskte kalan eski sürüm
# böylece yeni sürüm sanılmaz.
DALSAN_YAYINI = "https://github.com/RiosenBeq/DALSAN/releases/download/"
# Yerel dosya adı -> yayındaki yeri "<etiket>/<yayın dosyası>"
# (models/indir.sh'teki `indir <ad> <etiket>/<yayın dosyası>` satırı)
DALSAN_MODELLERI: dict[str, str] = {}
# Forklifti ayrı sınıf olarak da tanıyan model -> insanı ve aracı onunla AYNI
# tanıyan hazır model (donuk resmi model + ek baş). Kurulum listesi ve Ayarlar,
# çalışan modelin forklift karşılığını buradan bulur.
FORKLIFT_TABANI: dict[str, str] = {}

# Dosya adı → SHA-256. İndirilen dosya bu özetle karşılaştırılır; tutmazsa
# kullanılmaz (docs/17 §10.5 R17). Değerler 23.09.2026'da resmi yayından iki
# ayrı indirmeyle ölçüldü ve aynı çıktı; models/indir.sh aynı değerleri taşır
# (tests/test_model_butunlugu.py ikisini karşılaştırır). Yayın dosyası
# değişirse (yeni sürüm) özet de buradan güncellenir - sessizce kabul edilmez.
BILINEN_MODELLER: dict[str, str] = {
    "yolox_tiny.onnx": "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7",
    "yolox_s.onnx": "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063",
}


class ModelIndirmeHatasi(DalsanHata):
    """İnternet yok / adres erişilemez - sistem tespitsiz devam eder.

    Kullanıcı mesajında indirme adresi YOKTUR (bkz. `_indirme_hata_metinleri`);
    tam adres `teknik_ayrinti` üzerinden sistem.log'a gider.
    """


def indirme_adresi(ad: str) -> str:
    """Dosyanın indirileceği adres: DALSAN yayını ya da YOLOX'un resmi yayını."""
    yayindaki_yeri = DALSAN_MODELLERI.get(ad)
    return DALSAN_YAYINI + yayindaki_yeri if yayindaki_yeri else _YAYIN_ADRESI + ad


def indirilebilir_mi(model_dosyasi: Path) -> bool:
    return model_dosyasi.name in BILINEN_MODELLER


def resmi_yayinla_ayni_mi(model_dosyasi: Path) -> bool:
    """Dosya, hazır modellerden birinin resmi yayınıyla bayt bayt aynı mı (SHA-256)?

    Hazır olmayan (kendi eğitilmiş) model için karşılaştırılacak özet yoktur;
    okunamayan dosya da "aynı" sayılmaz - ikisinde de False.
    """
    beklenen = BILINEN_MODELLER.get(model_dosyasi.name)
    if beklenen is None:
        return False
    ozet = hashlib.sha256()
    try:
        with model_dosyasi.open("rb") as dosya:
            for parca in iter(lambda: dosya.read(1024 * 1024), b""):
                ozet.update(parca)
    except OSError:
        return False
    return ozet.hexdigest() == beklenen


def ozel_model_hatasi(model_dosyasi: Path) -> ModelIndirmeHatasi:
    """Hazır listede olmayan model için ORTAK açıklama (tek metin kaynağı).

    İki yerden çağrılır: indirme denendiğinde ve süpervizör indirmeyi
    atladığında. Böylece kendi modelini koyan kullanıcı hangi yoldan gelirse
    gelsin aynı, markalı açıklamayı görür - ham dosya yolunu değil.
    """
    # Ekranda dosya adı GEÇMEZ (kullanıcı yazılımcı değil); tam ad günlüğe gider.
    if yerel_forklift_tabani(model_dosyasi.name) is not None:
        # Forklift sayfasından kurulmuş model: indirilecek yeri yok, dosyası kaybolmuş
        return ModelIndirmeHatasi(
            f"{gorunen_model_adi(model_dosyasi.name)} dosyası bulunamadı: silinmiş ya da "
            "taşınmış olabilir. Forklift sayfasındaki “Modeli kur” ile yeniden kurun. "
            f"{hazir_modele_donus()}",
            f"Yerel forklift modeli yok: {model_dosyasi}",
        )
    hazir_adlar = " veya ".join(gorunen_model_adi(ad) for ad in BILINEN_MODELLER)
    return ModelIndirmeHatasi(
        f"{gorunen_model_adi(model_dosyasi.name)} kendiliğinden inemez: seçili model, "
        f"hazır modellerden ({hazir_adlar}) biri değil. Kendi eğittiğiniz bir modeli "
        "kullanıyorsanız, model dosyanızı ayar dosyasındaki MODEL_DOSYASI satırında "
        f"yazan yere koyun. {hazir_modele_donus()}",
        f"Otomatik indirme atlandı: {model_dosyasi} bilinen yayın dosyalarından "
        f"({', '.join(BILINEN_MODELLER)}) biri değil.",
    )


def modeli_indir(model_dosyasi: Path, ilerleme: Callable[[int, int], None] | None = None) -> None:
    """Modeli `.part` dosyasına indirip bitince adını değiştirir - yarım
    kalan indirme asla 'geçerli model' sanılmaz. Özeti bilinen değerle
    TUTMAYAN dosya da (bozuk, eksik ya da yolda değiştirilmiş) sanılmaz."""
    if not indirilebilir_mi(model_dosyasi):
        raise ozel_model_hatasi(model_dosyasi)
    adres = indirme_adresi(model_dosyasi.name)
    gecici = model_dosyasi.with_suffix(model_dosyasi.suffix + ".part")
    ozet = hashlib.sha256()
    try:
        model_dosyasi.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(adres, timeout=30) as yanit, gecici.open("wb") as hedef:
            toplam = int(yanit.headers.get("Content-Length") or 0)
            inen = 0
            while True:
                parca = yanit.read(1024 * 256)
                if not parca:
                    break
                hedef.write(parca)
                ozet.update(parca)
                inen += len(parca)
                if ilerleme is not None:
                    ilerleme(inen, toplam)
        if ozet.hexdigest() != BILINEN_MODELLER[model_dosyasi.name]:
            gecici.unlink(missing_ok=True)
            raise ModelIndirmeHatasi(
                f"{gorunen_model_adi(model_dosyasi.name)} indirildi ama doğrulanamadı: "
                "dosya eksik, bozuk ya da yolda değiştirilmiş. Kullanılmadı ve silindi. "
                "İnternet bağlantısını kontrol edip "
                f"{kaynaklar.baslatma_tarifi(cumle_basi=False)}. Sorun sürerse bilgi "
                "işlem birimine haber verin: "
                "şirket ağındaki bir güvenlik cihazı indirilen dosyayı değiştiriyor "
                "olabilir.",
                f"SHA-256 tutmadı: {adres} → {gecici} | beklenen "
                f"{BILINEN_MODELLER[model_dosyasi.name]} | inen {ozet.hexdigest()} "
                f"({inen} bayt)",
            )
        # Eksik inen dosya da özetten geçemez; ayrı bir boyut denetimi gerekmez.
        gecici.replace(model_dosyasi)
    except (urllib.error.URLError, TimeoutError, OSError) as hata:
        gecici.unlink(missing_ok=True)
        kullanici_mesaji, teknik_ayrinti = _indirme_hata_metinleri(adres, model_dosyasi, hata)
        raise ModelIndirmeHatasi(kullanici_mesaji, teknik_ayrinti) from hata


def forklift_yedegi(model_dosyasi: Path) -> Path | None:
    """Forklift modeli kullanılamazsa geçilecek model.

    Forklift modeli, insanı ve aracı tabanındaki hazır modelle AYNI tanır: bu
    deponun yayınından inen modelin tabanı FORKLIFT_TABANI'dadır, Forklift
    sayfasından kurulan yerel modelinki adındadır (model_adi.YEREL_FORKLIFT_ADI).
    İnmez ya da açılmazsa (internetsiz saha, bozuk ya da silinmiş dosya)
    süpervizör o hazır modelle çalışır: insan ve araç tespiti durmaz, yalnız
    forklift ayrı sınıf olarak tanınmaz (operatör, 24.09.2026: "Olan
    problemleri de çöz"). Hazır model aynı klasörde durur; forklift modeli
    değilse None.
    """
    if model_dosyasi.name in DALSAN_MODELLERI:
        taban = FORKLIFT_TABANI.get(model_dosyasi.name)
    else:
        taban = yerel_forklift_tabani(model_dosyasi.name)
    return model_dosyasi.with_name(taban) if taban else None


def yerel_forklift_modelleri(modeller_klasoru: Path) -> dict[str, str]:
    """Bu kurulumda Forklift sayfasından kurulmuş modeller: {dosya adı: taban}.

    Kurulma sırasıyla (dosya zamanı; eşitse ad): en yenisi sondadır, kurulum
    listesi ve Ayarlar onu en yeni sayar (FORKLIFT_TABANI'nın sırasıyla aynı kural).
    """
    if not modeller_klasoru.is_dir():
        return {}
    bulunan = []
    for yol in modeller_klasoru.iterdir():
        if not YEREL_FORKLIFT_ADI.fullmatch(yol.name) or not yol.is_file():
            continue
        try:
            zaman = yol.stat().st_mtime
        except OSError:
            continue
        bulunan.append((zaman, yol.name))
    return {ad: yerel_forklift_tabani(ad) or "" for _, ad in sorted(bulunan)}


def forklift_tabanlari(modeller_klasoru: Path) -> dict[str, str]:
    """Bütün forklift modelleri ve tabanları: kayıtlı yayın modelleri, sonra bu
    kurulumda yerelde kurulanlar (en yenisi sonda)."""
    return {**FORKLIFT_TABANI, **yerel_forklift_modelleri(modeller_klasoru)}


def _saat_hatasi_mi(hata: Exception) -> bool:
    """Sertifika doğrulaması SAAT yüzünden mi başarısız oldu?

    OpenSSL bu iki durumu ayrı metinlerle bildirir: sertifika henüz
    başlamamış ("is not yet valid") ya da süresi geçmiş ("has expired").
    İkisi de bilgisayarın saatinin gerçek zamandan sapmasıyla oluşur - yeni
    kurulan, CMOS pili bitmiş ya da saat dilimi hiç ayarlanmamış makinelerde
    sık görülür. Metne bakılır çünkü `verify_code` sayıları OpenSSL sürümüne
    göre değişebilir; bu iki ifade değişmez.
    """
    metin = str(hata).lower()
    return (
        "not yet valid" in metin
        or "has expired" in metin
        or "is expired" in metin
        or "system clock" in metin
    )


def _indirme_hata_metinleri(adres: str, model_dosyasi: Path, hata: Exception) -> tuple[str, str]:
    """(ekrana çıkan sade mesaj, günlüğe yazılan tam ayrıntı) döndürür.

    İndirme adresi EKRANA ÇIKMAZ: kullanıcı yazılımcı değil, uzun bir GitHub
    adresi ana sayfada ne yapacağını söylemez, yalnızca korkutur. Tam adres,
    hedef dosya ve özgün hata metni veri/loglar/sistem.log'a yazılır - destek
    akışı oradan kopyalandığı için hiçbir bilgi kaybolmaz.

    Sebebe göre DOĞRU çözümü söyler - "internetinizi kontrol edin" her zaman
    doğru teşhis değildir.
    """
    ad = gorunen_model_adi(model_dosyasi.name)
    sebep = getattr(hata, "reason", hata)
    sertifika_hatasi = isinstance(sebep, ssl.SSLCertVerificationError) or (
        "CERTIFICATE_VERIFY_FAILED" in str(hata)
    )
    if sertifika_hatasi and _saat_hatasi_mi(hata):
        # Bu, sertifika DEPOSU sorunu DEĞİLDİR: sertifika sağlamdır, bilgisayarın
        # saati onun geçerlilik aralığının dışındadır. Buraya "Install
        # Certificates.command'a çift tıklayın" yazmak kullanıcıyı saatlerce
        # yanlış yerde uğraştırır - üstelik o dosya Windows'ta hiç yoktur.
        # Doğru çözüm tek satırdır: saati düzelt.
        kullanici_mesaji = (
            f"{ad} indirilemedi: bu bilgisayarın tarih/saat ayarı yanlış olduğu için "
            "güvenlik sertifikası geçersiz görünüyor. Çözüm: bilgisayarın tarih, saat ve "
            "saat dilimi ayarını açıp 'otomatik ayarla' seçeneğini işaretleyin (Windows: "
            "Ayarlar → Saat ve dil → Tarih ve saat; Mac: Sistem Ayarları → Genel → Tarih "
            f"ve Saat). Ardından {kaynaklar.baslatma_tarifi(cumle_basi=False)}."
        )
    elif sertifika_hatasi:
        # "Install Certificates.command" yalnız python.org kurulumunda vardır:
        # Windows ve Mac uygulamasının Python'u paketin, Docker'ınki kapsayıcının
        # içindedir; tarif yalnız Başlat betikleriyle kurulan sistemde verilir.
        python_org = (
            "Mac'te python.org'dan kurulan Python'da bu sık görülür. Çözüm: "
            "Uygulamalar → Python 3.x klasöründeki 'Install Certificates.command' "
            "dosyasına çift tıklayın, ardından Kontrol Paneli'nde Durdur'a, sonra "
            "Sistemi Başlat'a basın. "
            if kaynaklar.kurulum_turu() == "kaynak"
            else ""
        )
        kullanici_mesaji = (
            f"{ad} indirilemedi: güvenlik sertifikaları doğrulanamadı. {python_org}"
            "Şirket ağındaysanız internet trafiğini denetleyen bir güvenlik duvarı "
            "bu hatayı verir; bu durumda bilgi işlem biriminden yardım isteyin."
        )
    elif isinstance(hata, urllib.error.HTTPError) and hata.code in (404, 410):
        # Sunucu cevap verdi: internet çalışıyor, dosya yayın yerinde yok
        # (yayın kaldırılmış ya da taşınmış). "İnterneti kontrol edin" burada
        # yanlış yere yollar; başka modele geçmek sistemi hemen çalıştırır.
        kullanici_mesaji = (
            f"{ad} indirilemedi: model dosyası yayın yerinde bulunamadı (internet "
            "bağlantısı çalışıyor). Ayarlar'daki “Tanıma modeli” listesinden başka bir "
            f"model seçip kaydedin, {kaynaklar.baslatma_tarifi(cumle_basi=False)} ve "
            "destek ekibine haber verin."
        )
    else:
        kullanici_mesaji = (
            f"{ad} indirilemedi. İnternet bağlantısını kontrol edip "
            f"{kaynaklar.baslatma_tarifi(cumle_basi=False)}."
        )
    teknik_ayrinti = (
        f"{kullanici_mesaji} | indirme adresi: {adres} | hedef dosya: {model_dosyasi} "
        f"| özgün hata: {hata!r}"
    )
    return kullanici_mesaji, teknik_ayrinti
