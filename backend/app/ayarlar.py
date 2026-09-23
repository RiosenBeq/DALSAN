"""Ayarların TEK kaynağı - yazılabilir kökteki .env dosyasını okur.

Başka hiçbir dosya os.environ'a veya .env'e bakmaz; ayar gereken her yer
buradan bir `Ayarlar` nesnesi alır (CLAUDE.md §7: sabit kodlanmış eşik,
yol, IP yasak).

Eksik veya bozuk ayar, program açılışında anlaşılır Türkçe bir `AyarHatasi`
ile durdurur - sistem yarım ayarla ÇALIŞMAZ.
"""

from __future__ import annotations

import errno
import ipaddress
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from app import kaynaklar
from app.hatalar import AyarHatasi

# Yolların nerede çözüldüğü: app/kaynaklar.py. Bu dosya çalışma dizinine ASLA
# güvenmez (Kontrol Paneli uvicorn'u backend/ içinden başlatır) ve paketlenmiş
# çalışmada veri klasörünün nereye taşındığını da bilmek zorunda değildir.


# IP hoparlörlerin/anons sunucularının HTTP arayüzü tek tip DEĞİLDİR: kimi
# JSON gövde bekler, kimi form alanı, kimi de yalnızca adrese bir GET ister.
# Bu üç seçenek sahada karşılaşılan neredeyse her cihazı karşılar ve yeni bir
# kütüphane gerektirmez (CLAUDE.md §3). Ayrıntı: docs/14-ANONS-SISTEMI-BAGLAMA.md
_ANONS_BICIM_SECENEKLERI = ("json", "form", "get")
_CIHAZ_SECENEKLERI = ("cpu", "cuda")
_IYILESTIRME_SECENEKLERI = ("kapali", "otomatik")
# Bekçi takılmayı görünce: yalnız uyarır ya da süreci yeniden başlatır
# (yalnız Docker `restart:` / systemd `Restart=` kurulumunda anlamlı).
_BEKCI_TEPKILERI = ("uyar", "yeniden_baslat")


@dataclass(frozen=True)
class Ayarlar:
    kok_dizin: Path
    veri_dizini: Path
    veritabani_yolu: Path
    goruntu_klasoru: Path
    nesne_klasoru: Path
    nesne_tarama_klasoru: Path
    log_dosyasi: Path
    olay_saklama_gun: int
    goruntu_saklama_gun: int
    kkd_ham_veri_saklama_gun: int
    sistem_olay_saklama_gun: int
    kkd_ornek_saat_limit: int
    disk_uyari_gb: int
    cikarim_cihazi: str
    # Tespit modelinin kullanacağı işlemci çekirdeği sayısı. 0 = otomatik
    # (ONNX Runtime kendi seçer, tüm çekirdekler). Sunucu başka işler de
    # yapıyorsa sınırlamak, sistemi makinenin tamamını yemekten alıkoyar.
    cikarim_is_parcacigi: int
    kare_ornekleme_fps: int
    fps_uyari_orani: float
    tespit_guven_esigi: float
    tespit_insan_guven_esigi: float
    tespit_nms_esigi: float
    tespit_en_kucuk_kenar_px: int
    goruntu_iyilestirme: str
    # Yönetici şifresi. BOŞ = giriş sorulmaz (tek makinede, 127.0.0.1'de
    # çalışan kurulum). Dolu = her sayfa giriş ister. Fabrika sunucusunda ya
    # da sistem ağa açıldığında DOLDURULMALIDIR - kural değiştirebilen ve
    # anons tetikleyen bir sistem LAN'da bile şifresiz durmamalı.
    yonetici_sifresi: str
    # Sunucunun DİNLEYECEĞİ adres. 127.0.0.1 = yalnız bu bilgisayar (varsayılan).
    # 0.0.0.0 = ağdaki diğer cihazlar da erişebilir (uzaktan erişimin ön koşulu).
    # Şifresiz bir sistemin ağa açılması AÇILIŞTA REDDEDİLİR - bkz. ayarlari_yukle.
    sunucu_adresi: str
    # Uyarı KANALLARI (ses çıkışı, IP hoparlör) .env'de değil, veritabanında
    # tanımlanır (speaker_zones; Komuta → Anons, docs/17 K22). Eski ANONS /
    # ANONS_SES_CIHAZI / ANONS_HTTP_ADRESI satırları ilk açılışta bir kez
    # "Tüm fabrika" kanalına aktarılır (olaylar/kanallar.py) ve sonra okunmaz.
    # Biçim bütün IP hoparlörler için ortaktır.
    anons_http_bicimi: str
    anons_bekleme_sn: int
    model_dosyasi: Path
    # KKD sınıflandırıcısı (docs/17 §5.2); dosya yoksa KKD kuralı olay üretmez
    kkd_model_dosyasi: Path
    nesne_izinli_uzantilar: tuple[str, ...]
    nesne_foto_en_buyuk_mb: int
    nesne_tarama_en_cok_dosya: int
    nesne_eslesme_esigi: float
    # --- Yüklenen test videoları (web/videolar.py) ---
    video_klasoru: Path
    video_izinli_uzantilar: tuple[str, ...]
    video_en_buyuk_mb: int
    # Ayarların yazıldığı dosya. Ayarlar sayfası (web/ayar_rotalari.py) buraya
    # yazar; yolun kendisi ekranda GÖSTERİLMEZ, yalnızca dosya işlemi için var.
    env_yolu: Path
    # Yazılabilir klasör olağandışı seçildiyse (paketlenmiş program, kayıtlar
    # eski yerde bulundu) açılışta günlüğe düşecek cümle. Olağan durumda boş.
    veri_konumu_notu: str = ""
    veri_konumu_ayrintisi: str = ""
    # Sisteme hangi ADLARLA erişilebilir (Host başlığı). Geri döngü adresleri
    # (127.x, ::1, localhost) ve sunucu_adresi her zaman izinlidir; bu liste
    # ONLARIN ÜSTÜNE eklenir. Boş = yalnız o adlar. Denetim: web/kaynak_denetimi.py
    izinli_sunucu_adlari: tuple[str, ...] = ()
    # --- Takip ve kamera bağlantısı (docs/17 K7, K8) ---
    # Kaybolan izin kaç saniye aynı kimlikle bekleneceği (ByteTrack hafızası ve
    # kuralların kayıp toleransı ikisi de bundan türer).
    takip_hafiza_sn: float = 2.0
    # Akan görüntü bu süre kesilirse kamera çevrimdışı sayılır.
    kamera_kopuk_esigi_sn: float = 10.0
    # "Tekrar çevrimiçi" olayı için gereken kesintisiz görüntü süresi.
    kamera_up_kararlilik_sn: float = 5.0
    # RTSP açılış / okuma zaman aşımları (OpenCV → FFmpeg), milisaniye.
    rtsp_acilis_zaman_asimi_ms: int = 5000
    rtsp_okuma_zaman_asimi_ms: int = 10000
    # --- Analiz sağlığı (docs/17 §3.6) ---
    # Analiz döngüsü bu kadar saniye ilerlemezse "takıldı" sayılır (bekçi).
    bekci_esigi_sn: float = 90.0
    # Takılmada ne yapılsın: uyar | yeniden_baslat (yalnız Docker/systemd'de).
    bekci_tepkisi: str = "uyar"
    # İşleme hızı hedefin altında bu kadar saniye kalırsa "analiz yavaşladı".
    analiz_yavas_sure_sn: float = 60.0
    # Bir kamerada üst üste bu kadar kare işlenemezse hattı yeniden kurulur.
    analiz_hata_esigi: int = 30
    # --- KKD anons kapısı (docs/17 §5.7, K16; S33) ---
    # Gölgedeki KKD kuralının anonsu, kalem ve model sürümü başına bu şartlar
    # sağlanmadan açılmaz (web/kkd_karnesi.py). Açık onayla zorla açılabilir;
    # onay sistem olayı olarak yazılır.
    kkd_kapi_precision: float = 0.90
    kkd_kapi_gun: int = 3
    kkd_kapi_en_az_olay: int = 30


def _yerel_adres_mi(adres: str) -> bool:
    """Adres yalnızca BU bilgisayardan mı erişilebilir?

    127.x.x.x ve ::1 yereldir; 0.0.0.0, :: ve gerçek bir IP ağa açar.
    """
    temiz = adres.strip().strip("[]").lower()
    return temiz.startswith("127.") or temiz in ("localhost", "::1")


# Host başlığında ya da ayar satırında bir sunucu adının içerebileceği
# karakterler: harf, rakam, nokta, tire, alt çizgi; IPv6 için iki nokta ve
# köşeli parantez. Boşluk, '@', '/' gibi karakterler ad değildir.
_AD_KARAKTERLERI = re.compile(r"[a-z0-9._\-:\[\]]+")


def sunucu_adi(ham: str) -> str:
    """Host başlığından, adresten ya da ayar satırından karşılaştırılacak ADI çıkarır.

    '127.0.0.1:8080' → '127.0.0.1' · '[::1]:8080' → '::1' ·
    'ISG.Dalsan.Local.' → 'isg.dalsan.local' · 'http://10.0.0.5:8080/x' → '10.0.0.5'.
    Ad olamayacak bir değer (boşluk, '@', '/' içeren; kapanmamış köşeli
    parantez; sayı olmayan port) BOŞ metin döner - çağıran taraf onu izinsiz
    sayar.
    """
    metin = ham.strip().lower()
    if "://" in metin:  # tam adres (Origin, Referer ya da ayara yapıştırılmış adres)
        try:
            metin = urlsplit(metin).netloc
        except ValueError:
            return ""
    if not metin.isascii():
        # Türkçe harfli ad ('işg.dalsan.local'): tarayıcı Host başlığına onu
        # punycode yazar ('xn--g-...'); karşılaştırma aynı biçimde yapılır.
        try:
            metin = metin.encode("idna").decode("ascii")
        except UnicodeError:
            return ""
    if not _AD_KARAKTERLERI.fullmatch(metin):
        return ""
    if metin.startswith("["):
        kapanis = metin.find("]")
        if kapanis == -1:
            return ""
        ad, kalan = metin[1:kapanis], metin[kapanis + 1 :]
        if kalan and not (kalan.startswith(":") and kalan[1:].isdigit()):
            return ""
    elif metin.count(":") == 1:
        ad, port = metin.split(":")
        if not port.isdigit():
            return ""
    else:
        ad = metin  # port yok ya da köşeli parantezsiz IPv6 ('fe80::1')
    return ad.rstrip(".")


def geri_donus_adi_mi(ad: str) -> bool:
    """Ad bu bilgisayarın kendisini mi gösteriyor? ('localhost', 127.x, ::1)

    `_yerel_adres_mi`'den farkı: adres öneki değil, GERÇEK IP ayrıştırması.
    '127.saldirgan.com' bir alan adıdır, geri döngü değildir.
    """
    if ad == "localhost":
        return True
    try:
        return ipaddress.ip_address(ad).is_loopback
    except ValueError:
        return False


def env_degerlerini_oku(env_yolu: Path) -> dict[str, str]:
    """.env dosyasını anahtar→değer sözlüğüne çevirir (değerler kırpılır)."""
    return {a: (d or "").strip() for a, d in dotenv_values(env_yolu).items()}


def ayarlari_yukle(kok_dizin: Path | None = None) -> Ayarlar:
    """.env dosyasını okur, doğrular, gereken klasörleri oluşturur.

    `kok_dizin` verilmezse yazılabilir kök app/kaynaklar.py'den sorulur:
    geliştirmede depo kökü, paketlenmiş programda kullanıcı profilindeki
    klasör. Testler kökü açıkça verir.

    Her doğrulama hatası, kullanıcının olduğu gibi okuyabileceği Türkçe
    bir AyarHatasi mesajıdır.
    """
    konum = (
        kaynaklar.VeriKonumu(kok_dizin.resolve())
        if kok_dizin is not None
        else kaynaklar.veri_konumu()
    )
    kok = konum.kok
    env_yolu = kok / ".env"
    if not env_yolu.exists() and kaynaklar.paketlenmis_mi():
        # Paketlenmiş programda kullanıcının kopyalayabileceği bir .env.example
        # YOKTUR (dosyalar paketin içindedir) ve klasör de ilk açılışta boştur.
        # Bu yüzden ayar dosyası bir kez, örnekten üretilir.
        _ornek_envden_olustur(env_yolu)
    if not env_yolu.exists() and kaynaklar.kapsayicida_mi():
        # Docker'da .env, sunucudaki ayar/ dizininden bağlanır (docker-compose.yml);
        # kökteki .env oraya işaret eden bir bağdır. Dosya yoksa kapsayıcının
        # içinde üretmek yanlış olurdu: sunucudaki yöneticinin elinde kalmalı.
        raise AyarHatasi(
            "Ayar dosyası bulunamadı: Docker kurulumunda ayarlar sunucudaki "
            "ayar/.env dosyasındadır.\n"
            "İlk kurulum:  mkdir -p ayar && cp .env.example ayar/.env\n"
            "Eski kurulumdan geliyorsanız:  mkdir -p ayar && mv .env ayar/.env\n"
            "ayar klasörünü Docker kendisi oluşturduysa (sahibi root) komutların "
            "başına sudo ekleyin. Sonra ayar/.env içinde YONETICI_SIFRESI satırını "
            "doldurup docker compose up -d ile yeniden başlatın (docs/06-OPERASYON.md)."
        )
    if not env_yolu.exists():
        raise AyarHatasi(
            f"Ayar dosyası bulunamadı: {env_yolu}\n"
            "Çözüm: .env.example dosyasını .env adıyla kopyalayın. "
            "(Kontrol Paneli'ndeki 'İlk Kurulumu Yap' düğmesi bunu otomatik yapar.)"
        )
    return ayarlari_coz(kok, env_degerlerini_oku(env_yolu), konum)


def _ornek_envden_olustur(env_yolu: Path) -> None:
    """.env yoksa programla gelen .env.example'dan BİR KEZ üretir."""
    ornek = kaynaklar.kaynak_yolu(".env.example")
    if not ornek.is_file():
        # Örnek de yoksa aşağıdaki "Ayar dosyası bulunamadı" hatası devreye girer.
        return
    _klasor_olustur(env_yolu.parent)
    try:
        shutil.copyfile(ornek, env_yolu)
    except OSError as hata:
        raise AyarHatasi(
            "Ayar dosyası oluşturulamadı: klasöre yazılamıyor.",
            f"{ornek} → {env_yolu} kopyalanamadı: {hata!r}",
        ) from hata


def ayarlari_coz(
    kok: Path, degerler: dict[str, str], konum: kaynaklar.VeriKonumu | None = None
) -> Ayarlar:
    """Anahtar→değer sözlüğünü doğrulanmış `Ayarlar` nesnesine çevirir.

    Dosyadan ayrı durur ki Ayarlar sayfası, formdaki değerleri .env'e YAZMADAN
    ÖNCE aynı doğrulamadan geçirebilsin: kaydedilen bir ayar, sistemin bir
    daha açılmamasına yol açamaz.
    """
    konum = konum or kaynaklar.VeriKonumu(kok)

    # Giriş şifresi İSTEĞE BAĞLIDIR (YONETICI_SIFRESI): boşken giriş sorulmaz
    # - tek makinede, 127.0.0.1'e bağlı çalışan kurulum. Sistem ağa açılırken
    # (SUNUCU_ADRESI) şifre ZORUNLU olur; aşağıdaki emniyet kilidi bunu
    # açılışta uygular. Ayrıntı: web/giris.py, docs/15-UZAKTAN-ERISIM.md

    # Not: sistemin portunu Kontrol Paneli belirler (8080). Bu yüzden .env'de
    # port ayarı YOKTUR - okunmayan bir ayar ekranda yanlış bilgi gösterirdi.

    # veri/ klasörünün yeri sabittir: Kontrol Paneli günlüğü veri/loglar/sistem.log
    # dosyasından okur ve yedekleme "veri/ klasörünü kopyala" diye tarif edilir.
    veri_dizini = kok / "veri"
    veritabani_yolu = kok / _metin(degerler, "VERITABANI_YOLU", "veri/dalsan.db")
    goruntu_klasoru = kok / _metin(degerler, "GORUNTU_KLASORU", "veri/goruntuler")
    # Nesne kütüphanesi fotoğrafları GÖRÜNTÜ KLASÖRÜNÜN DIŞINDA durur: görüntü
    # klasörünü bakım döngüsü saklama süresi dolunca temizler (supervizor.py
    # _eski_dosyalari_sil). Kullanıcının elle tanıttığı nesne fotoğrafı bir
    # kanıt fotoğrafı değildir, kendiliğinden silinmemelidir.
    nesne_klasoru = kok / _metin(degerler, "NESNE_KLASORU", "veri/nesneler")
    # Tarama çıktıları (işaretlenmiş sonuç görüntüleri) ayrı alt klasörde:
    # referans fotoğraflarla karışmasın, sayısı sınırlı tutulup budanabilsin.
    nesne_tarama_klasoru = nesne_klasoru / "taramalar"
    # Kullanıcının yüklediği test videoları. Görüntü klasörünün DIŞINDA durur:
    # oradaki kanıt fotoğraflarını bakım döngüsü saklama süresi dolunca siler
    # (supervizor.py _eski_dosyalari_sil). Yüklenen video bir kanıt değil,
    # kullanıcının kendi dosyasıdır - kendiliğinden silinmemelidir.
    video_klasoru = kok / _metin(degerler, "VIDEO_KLASORU", "veri/videolar")
    log_dosyasi = veri_dizini / "loglar" / "sistem.log"

    for klasor in (
        veritabani_yolu.parent,
        goruntu_klasoru,
        nesne_klasoru,
        nesne_tarama_klasoru,
        video_klasoru,
        log_dosyasi.parent,
    ):
        _klasor_olustur(klasor)

    yonetici_sifresi = degerler.get("YONETICI_SIFRESI", "").strip()
    if yonetici_sifresi and len(yonetici_sifresi) < 6:
        raise AyarHatasi(
            ".env dosyasındaki YONETICI_SIFRESI en az 6 karakter olmalı. "
            "Şifre istemiyorsanız satırı boş bırakın (giriş sorulmaz)."
        )

    # KAPSAYICI KİLİDİ (docs/17 §10.4, R13): Docker'da sunucu her zaman bütün
    # ağ arayüzlerini dinler (Dockerfile: --host 0.0.0.0); aşağıdaki
    # SUNUCU_ADRESI kilidi orada işlemez. docker-compose.yml'deki port satırı
    # "8080:8080" yapıldığı anda şifresiz sistem ağa açılırdı - bu yüzden
    # kapsayıcıda şifre, port satırından bağımsız olarak ZORUNLUDUR.
    if kaynaklar.kapsayicida_mi() and not yonetici_sifresi:
        raise AyarHatasi(
            "Sistem Docker kapsayıcısında çalışıyor ve YONETICI_SIFRESI boş. Kapsayıcı "
            "ağ arayüzlerinin hepsini dinler: port satırı değiştirildiği anda şifresiz "
            "sistem ağdaki herkese açılır (kamera silme, kural değiştirme, anons).\n\n"
            "Sunucuda ayar/.env dosyasındaki YONETICI_SIFRESI satırına en az 6 karakterli "
            "bir şifre yazın ve docker compose up -d ile yeniden başlatın."
        )

    sunucu_adresi = degerler.get("SUNUCU_ADRESI", "127.0.0.1").strip() or "127.0.0.1"
    # EMNİYET KİLİDİ: sistemi ağa açıp şifresiz bırakmak, ağdaki herkese
    # kamera silme ve anons yaptırma yetkisi vermektir. Bu, uyarıyla
    # geçiştirilecek bir durum değil - açılış DURDURULUR.
    if not _yerel_adres_mi(sunucu_adresi) and not yonetici_sifresi:
        raise AyarHatasi(
            f".env dosyasında SUNUCU_ADRESI={sunucu_adresi} yazıyor: sistem ağdaki "
            "diğer cihazlara açılacak. Ama YONETICI_SIFRESI boş - bu haliyle ağdaki "
            "herkes kamera silebilir, kural değiştirebilir ve hoparlörden anons "
            "yaptırabilir.\n\n"
            "Ya YONETICI_SIFRESI satırına bir şifre yazın (en az 6 karakter), "
            "ya da SUNUCU_ADRESI satırını 127.0.0.1 yapın. "
            "Uzaktan erişim tarifi: docs/15-UZAKTAN-ERISIM.md"
        )

    # IP hoparlör adresleri kanal satırlarındadır ve kanal formunda doğrulanır
    # (şema, GET yer tutucusu, R30: web/hoparlorler.py).
    anons_http_bicimi = _secenek(
        degerler, "ANONS_HTTP_BICIMI", varsayilan="json", secenekler=_ANONS_BICIM_SECENEKLERI
    )

    return Ayarlar(
        kok_dizin=kok,
        veri_dizini=veri_dizini,
        veritabani_yolu=veritabani_yolu,
        goruntu_klasoru=goruntu_klasoru,
        nesne_klasoru=nesne_klasoru,
        nesne_tarama_klasoru=nesne_tarama_klasoru,
        log_dosyasi=log_dosyasi,
        olay_saklama_gun=_tam_sayi(degerler, "OLAY_SAKLAMA_GUN", 180, 1, 3650),
        goruntu_saklama_gun=_tam_sayi(degerler, "GORUNTU_SAKLAMA_GUN", 90, 1, 3650),
        kkd_ham_veri_saklama_gun=_tam_sayi(degerler, "KKD_HAM_VERI_SAKLAMA_GUN", 30, 1, 3650),
        sistem_olay_saklama_gun=_tam_sayi(degerler, "SISTEM_OLAY_SAKLAMA_GUN", 90, 1, 3650),
        # KKD veri toplama: kamera başına saatte en çok kaç kişi görüntüsü
        # örneklenir (docs/04 §4.3 - aynı kişinin 200 ardışık karesi değil)
        kkd_ornek_saat_limit=_tam_sayi(degerler, "KKD_ORNEK_SAAT_LIMIT", 60, 1, 3600),
        # Boş disk bu değerin altına inince sistem olayı üretilir (docs/08 R8)
        disk_uyari_gb=_tam_sayi(degerler, "DISK_UYARI_GB", 5, 1, 1000),
        cikarim_cihazi=_secenek(degerler, "CIKARIM_CIHAZI", "cpu", _CIHAZ_SECENEKLERI),
        cikarim_is_parcacigi=_tam_sayi(degerler, "CIKARIM_IS_PARCACIGI", 0, 0, 64),
        # Yeni kameranın varsayılan örnekleme hızı (kamera formunda değiştirilebilir)
        kare_ornekleme_fps=_tam_sayi(degerler, "KARE_ORNEKLEME_FPS", 6, 1, 30),
        # Kamera sağlığı ekranı: ÖLÇÜLEN hız, ayarlanan hızın bu oranının
        # altına inerse kamera sarı gösterilir. Sabit bir "2 fps altı kötü"
        # eşiği yanlış olurdu: 6 fps'e ayarlı kamerada 3 fps yarı hız demektir,
        # 2 fps'e ayarlı kamerada ise normaldir.
        fps_uyari_orani=_ondalik(degerler, "FPS_UYARI_ORANI", 0.6, 0.1, 1.0),
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
        yonetici_sifresi=yonetici_sifresi,
        sunucu_adresi=sunucu_adresi,
        anons_http_bicimi=anons_http_bicimi,
        # Anons, ekran uyarısından bağımsız ve daha seyrek çalar (docs/02 §7):
        # hoparlör aynı kamera+mesaj için bu süre dolmadan tekrar bağırmaz.
        anons_bekleme_sn=_tam_sayi(degerler, "ANONS_BEKLEME_SN", 30, 5, 3600),
        model_dosyasi=kok / _metin(degerler, "MODEL_DOSYASI", "models/yolox_tiny.onnx"),
        kkd_model_dosyasi=kok / _metin(degerler, "KKD_MODEL_DOSYASI", "models/kkd.onnx"),
        # --- Nesne kütüphanesi sınırları -------------------------------------
        # Yükleme doğrulaması koda gömülmez (CLAUDE.md §7): hangi uzantı kabul
        # edilir, dosya en fazla kaç MB olur, bir taramada kaç dosya işlenir -
        # üçü de .env'den okunur.
        nesne_izinli_uzantilar=_uzanti_listesi(
            degerler, "NESNE_IZINLI_UZANTILAR", "jpg,jpeg,png,webp,bmp"
        ),
        nesne_foto_en_buyuk_mb=_tam_sayi(degerler, "NESNE_FOTO_EN_BUYUK_MB", 12, 1, 200),
        # Tarama, yüklenen fotoğrafı parça parça gezer; dosya sayısı arttıkça
        # bekleme uzar. Kullanıcı "sistem dondu" sanmasın diye sınırlı tutulur.
        nesne_tarama_en_cok_dosya=_tam_sayi(degerler, "NESNE_TARAMA_EN_COK_DOSYA", 6, 1, 30),
        # Bu skorun altındaki en iyi benzerlik "eşleşme yok" sayılır: sistem
        # emin olmadığı yere isim YAZMAZ (docs/12'deki üç durum ilkesiyle aynı).
        nesne_eslesme_esigi=_ondalik(degerler, "NESNE_ESLESME_ESIGI", 0.24, 0.05, 0.95),
        # --- Yüklenen test videoları -----------------------------------------
        # Hangi uzantı kabul edilir ve dosya en fazla kaç MB olur - ikisi de
        # koda gömülmez (CLAUDE.md §7). Varsayılan sınır bilerek yüksek: bir
        # vardiyanın kamera kaydı kolayca yüz MB'ı geçer, kullanıcıyı dosyayı
        # kırpmaya zorlamak "test etmek" işini baştan zorlaştırırdı.
        video_klasoru=video_klasoru,
        video_izinli_uzantilar=_uzanti_listesi(
            degerler, "VIDEO_IZINLI_UZANTILAR", "mp4,mov,avi,mkv,m4v"
        ),
        video_en_buyuk_mb=_tam_sayi(degerler, "VIDEO_EN_BUYUK_MB", 1024, 1, 20480),
        env_yolu=kok / ".env",
        veri_konumu_notu=konum.gunluk_notu,
        veri_konumu_ayrintisi=konum.gunluk_ayrintisi,
        # DNS yeniden bağlamaya karşı Host izin listesi (docs/17 §10.5 R8).
        # Uzaktan erişimde kullanılan ad buraya yazılır (docs/15).
        izinli_sunucu_adlari=_sunucu_adlari(degerler, "IZINLI_SUNUCU_ADLARI"),
        # --- Takip ve kamera bağlantısı (docs/17 K7, K8; öneriler S14, S18) ---
        # Hafıza kısa → örtülmede yeni kimlik, tekrar uyarı; uzun → izler karışır.
        takip_hafiza_sn=_ondalik(degerler, "TAKIP_HAFIZA_SN", 2.0, 0.5, 10.0),
        # En az 3 sn: saniyede tek kare veren yavaş bir akış yanlışlıkla
        # "koptu" sayılmasın.
        kamera_kopuk_esigi_sn=_ondalik(degerler, "KAMERA_KOPUK_ESIGI_SN", 10.0, 3.0, 600.0),
        kamera_up_kararlilik_sn=_ondalik(degerler, "KAMERA_UP_KARARLILIK_SN", 5.0, 0.0, 120.0),
        rtsp_acilis_zaman_asimi_ms=_tam_sayi(
            degerler, "RTSP_ACILIS_ZAMAN_ASIMI_MS", 5000, 1000, 60000
        ),
        rtsp_okuma_zaman_asimi_ms=_tam_sayi(
            degerler, "RTSP_OKUMA_ZAMAN_ASIMI_MS", 10000, 1000, 120000
        ),
        # --- Analiz sağlığı (docs/17 §3.6; öneriler docs/16 §8) ---
        # En az 20 sn: RTSP okuma zaman aşımı (10 sn) takılma sanılmasın.
        bekci_esigi_sn=_ondalik(degerler, "BEKCI_ESIGI_SN", 90.0, 20.0, 3600.0),
        bekci_tepkisi=_secenek(degerler, "BEKCI_TEPKISI", "uyar", _BEKCI_TEPKILERI),
        analiz_yavas_sure_sn=_ondalik(degerler, "ANALIZ_YAVAS_SURE_SN", 60.0, 10.0, 3600.0),
        analiz_hata_esigi=_tam_sayi(degerler, "ANALIZ_HATA_ESIGI", 30, 3, 10000),
        # --- KKD anons kapısı (docs/17 §5.7; docs/04 §8.1 hedef 0,90; S33) ---
        # Precision 0,5'in altına indirilemez: yarısı yanlış alarm olan bir
        # anons kapı değildir. En az olay 1'e kadar inebilir ama 30'un altında
        # ölçülen precision istatistikçe zayıftır (Ayarlar sayfası söyler).
        kkd_kapi_precision=_ondalik(degerler, "KKD_KAPI_PRECISION", 0.90, 0.5, 1.0),
        kkd_kapi_gun=_tam_sayi(degerler, "KKD_KAPI_GUN", 3, 1, 90),
        kkd_kapi_en_az_olay=_tam_sayi(degerler, "KKD_KAPI_EN_AZ_OLAY", 30, 1, 10000),
    )


# ---------------------------------------------------------------- .env yazımı
#
# Ayarlar sayfası (web/ayar_rotalari.py) kullanıcının değiştirdiği anahtarları
# buradan yazar. Kullanıcı .env'i elle düzenleyemeyeceği için (paketlenmiş
# programda dosya kullanıcı profilindedir) dosyanın AÇIKLAMA SATIRLARI çok
# değerlidir: dosya baştan yazılmaz, yalnızca ilgili satırın değeri değişir.

# "KARE_ORNEKLEME_FPS = 6   # açıklama" biçimindeki bir satırı parçalara ayırır.
# Yorum satırları ('#' ile başlayanlar) bilerek eşleşmez.
_ENV_SATIRI = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$")
# Değerin ardındaki açıklama: python-dotenv de boşluk + '#' gördüğü yerden
# sonrasını yorum sayar, yani burada korunan şey okunan şeyle aynıdır.
_SATIR_SONU_YORUMU = re.compile(r"\s+#.*$")

# SATIR ENJEKSİYONU (docs/AUDIT.md R14): "hdmi\nYONETICI_SIFRESI=" gibi bir
# değer dosyaya YENİ BİR SATIR ekler - şifreyi silen ya da sistemi ağa açan
# bir satır. Açılış doğrulayıcısı bunu göremez: formdaki değeri tek bir değer
# olarak okur, satır ancak dosyaya yazıldıktan sonra doğar. Bu yüzden yazmadan
# ÖNCE reddedilir. Yalnız \n ve \r değil: C0/C1 kontrol karakterleri ve
# Unicode satır/paragraf ayırıcıları da (str.splitlines() onları da satır sonu
# sayar, yani bir sonraki kayıtta aynı enjeksiyon doğardı).
_KONTROL_KARAKTERI = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_ANAHTAR_BICIMI = re.compile(r"[A-Z][A-Z0-9_]*")


def env_degisikliklerini_dogrula(degisiklikler: dict[str, str]) -> None:
    """Dosyaya yazılacak her anahtar ve değer tek satırlık, düz metin mi?"""
    for anahtar, deger in degisiklikler.items():
        if not _ANAHTAR_BICIMI.fullmatch(anahtar):
            raise AyarHatasi(f"Geçersiz ayar adı: {anahtar!r}. Kaydedilmedi.")
        if _KONTROL_KARAKTERI.search(deger):
            raise AyarHatasi(
                f".env dosyasında {anahtar} değeri satır sonu ya da görünmeyen bir "
                "kontrol karakteri içeremez. Değeri tek satır olarak yeniden yazın."
            )


def env_guncelle(metin: str, degisiklikler: dict[str, str]) -> str:
    """Ayar dosyasının metnini, açıklama satırlarına dokunmadan günceller.

    Var olan anahtarın yalnızca değeri değişir; dosyada olmayan anahtarlar
    sona eklenir. Satır enjeksiyonu taşıyan değişiklik reddedilir
    (`env_degisikliklerini_dogrula`) - her yazma yolu buradan geçer.
    """
    env_degisikliklerini_dogrula(degisiklikler)
    kalan = dict(degisiklikler)
    satirlar = metin.splitlines()
    for sira, satir in enumerate(satirlar):
        eslesme = _ENV_SATIRI.match(satir)
        if not eslesme:
            continue
        onek, anahtar, esittir, ham_deger = eslesme.groups()
        if anahtar not in kalan:
            continue
        satirlar[sira] = (
            f"{onek}{anahtar}{esittir}{_env_degeri(kalan.pop(anahtar))}{_yorum(ham_deger)}"
        )

    if kalan:
        if satirlar and satirlar[-1].strip():
            satirlar.append("")
        satirlar.append("# Ayarlar sayfasından eklendi")
        satirlar.extend(f"{anahtar}={_env_degeri(deger)}" for anahtar, deger in kalan.items())
    return "\n".join(satirlar) + "\n"


def _yorum(ham_deger: str) -> str:
    """Satırın sonundaki açıklamayı ('ANONS=null   # kapalı') olduğu gibi verir.

    TIRNAKLI değerde açıklama ARANMAZ: `A="adres # not"` satırında ' # not'
    değerin parçasıdır, açıklama değildir. Aranırsa değerin yarısı açıklama
    sanılıp bir sonraki kayıtta satırın sonuna yapıştırılırdı.
    """
    if ham_deger.lstrip()[:1] in ('"', "'"):
        return ""
    eslesme = _SATIR_SONU_YORUMU.search(ham_deger)
    return eslesme.group(0) if eslesme else ""


def _env_degeri(deger: str) -> str:
    """Boşluk ya da '#' içeren değeri tırnağa alır; yoksa olduğu gibi yazar.

    Tırnaksız bir değerde ' #' dizisi, dosyayı OKUYAN taraf için açıklama
    başlangıcıdır: değerin geri kalanı sessizce kaybolurdu.
    """
    temiz = deger.strip()
    if not temiz or not any(karakter in temiz for karakter in " \t#\"'"):
        return temiz
    return '"' + temiz.replace("\\", "\\\\").replace('"', '\\"') + '"'


def env_dosyasina_yaz(env_yolu: Path, degisiklikler: dict[str, str]) -> None:
    """Değişiklikleri ayar dosyasına yazar.

    Önce yanına geçici bir dosya yazılır, sonra tek adımda yerine geçer:
    yazma yarıda kalsa bile (disk dolu, elektrik kesildi) ESKİ ayar dosyası
    bozulmadan kalır ve sistem bir daha açılamaz duruma düşmez. Yarım kalan
    geçici dosya bilerek silinmez - bir sonraki kayıtta üzerine yazılır ve
    varlığı destek için ipucudur.
    """
    # .env bir sembolik bağ olabilir (Docker: /uygulama/.env → ayar/.env, bağlı
    # dizin; docs/17 §10.5 R27). Geçici dosya HEDEFİN yanında açılır: bağın
    # yanında açılsaydı replace() bağın KENDİSİNİ düz dosyayla değiştirirdi -
    # ayar kapsayıcının içinde kalır, sunucudaki dosya değişmez ve kapsayıcı
    # yenilenince kaybolurdu. Hedefle aynı dizinde olmak, yerine koymanın tek
    # adımda (atomik) kalmasının da şartıdır.
    hedef = env_yolu.resolve()
    try:
        eski_metin = hedef.read_text(encoding="utf-8") if hedef.is_file() else ""
    except OSError as hata:
        raise AyarHatasi(
            "Ayar dosyası okunamadı; kaydedilemedi.",
            f"{hedef} okunamadı: {hata!r}",
        ) from hata

    gecici = hedef.with_name(hedef.name + ".yeni")
    try:
        gecici.write_text(env_guncelle(eski_metin, degisiklikler), encoding="utf-8")
        gecici.replace(hedef)
    except OSError as hata:
        raise AyarHatasi(
            "Ayarlar kaydedilemedi: klasöre yazılamıyor. Diskte yer olduğundan "
            "ve programın kapalı olmadığından emin olun.",
            f"{gecici} → {hedef} yazılamadı: {hata!r}",
        ) from hata


def _uzanti_listesi(degerler: dict, anahtar: str, varsayilan: str) -> tuple[str, ...]:
    """'jpg, PNG' → ('.jpg', '.png'). Nokta ve büyük/küçük harf farkı hoş görülür."""
    ham = degerler.get(anahtar, "") or varsayilan
    uzantilar = tuple(
        "." + parca.strip().lstrip(".").lower() for parca in ham.split(",") if parca.strip()
    )
    if not uzantilar:
        raise AyarHatasi(
            f".env dosyasında {anahtar} boş olamaz; en az bir dosya uzantısı yazın "
            f"(örnek: {varsayilan})."
        )
    return uzantilar


def _sunucu_adlari(degerler: dict, anahtar: str) -> tuple[str, ...]:
    """'192.168.1.50, ISG.dalsan.local:8080' → ('192.168.1.50', 'isg.dalsan.local').

    Port ve 'http://' hoş görülür (kullanıcı tarayıcıdaki adresi yapıştırabilir);
    ad olmayan değer açılışı durdurur - sessizce atlanırsa kullanıcı neden
    hâlâ "izin verilmeyen adres" gördüğünü anlayamazdı.
    """
    adlar = []
    for parca in (degerler.get(anahtar, "") or "").replace(";", ",").split(","):
        parca = parca.strip()
        if not parca:
            continue
        ad = sunucu_adi(parca)
        if not ad or ad == "null":
            raise AyarHatasi(
                f".env dosyasında {anahtar} içinde sunucu adı olmayan bir değer var: "
                f"'{parca}'. Adları virgülle ayırın; joker (*) kabul edilmez. "
                "Örnek: 192.168.1.50, isg.dalsan.local"
            )
        if ad not in adlar:
            adlar.append(ad)
    return tuple(adlar)


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
        # Ekranda yalnızca klasör adı ve sade sebep; tam yol günlüğe gider.
        raise AyarHatasi(
            f"'{klasor.name}' klasörü oluşturulamadı: {sebep}.",
            f"{klasor} klasörü oluşturulamadı: {hata!r}",
        ) from hata
