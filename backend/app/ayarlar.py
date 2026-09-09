"""Ayarların TEK kaynağı — yazılabilir kökteki .env dosyasını okur.

Başka hiçbir dosya os.environ'a veya .env'e bakmaz; ayar gereken her yer
buradan bir `Ayarlar` nesnesi alır (CLAUDE.md §7: sabit kodlanmış eşik,
yol, IP yasak).

Eksik veya bozuk ayar, program açılışında anlaşılır Türkçe bir `AyarHatasi`
ile durdurur — sistem yarım ayarla ÇALIŞMAZ.
"""

from __future__ import annotations

import errno
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from app import kaynaklar
from app.hatalar import AyarHatasi

# Yolların nerede çözüldüğü: app/kaynaklar.py. Bu dosya çalışma dizinine ASLA
# güvenmez (Kontrol Paneli uvicorn'u backend/ içinden başlatır) ve paketlenmiş
# çalışmada veri klasörünün nereye taşındığını da bilmek zorunda değildir.

_ANONS_SECENEKLERI = ("null", "ses_karti", "http")

# IP hoparlörlerin/anons sunucularının HTTP arayüzü tek tip DEĞİLDİR: kimi
# JSON gövde bekler, kimi form alanı, kimi de yalnızca adrese bir GET ister.
# Bu üç seçenek sahada karşılaşılan neredeyse her cihazı karşılar ve yeni bir
# kütüphane gerektirmez (CLAUDE.md §3). Ayrıntı: docs/14-ANONS-SISTEMI-BAGLAMA.md
_ANONS_BICIM_SECENEKLERI = ("json", "form", "get")
_CIHAZ_SECENEKLERI = ("cpu", "cuda")
_IYILESTIRME_SECENEKLERI = ("kapali", "otomatik")


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
    kare_ornekleme_fps: int
    fps_uyari_orani: float
    tespit_guven_esigi: float
    tespit_insan_guven_esigi: float
    tespit_nms_esigi: float
    tespit_en_kucuk_kenar_px: int
    goruntu_iyilestirme: str
    # Yönetici şifresi. BOŞ = giriş sorulmaz (tek makinede, 127.0.0.1'de
    # çalışan kurulum). Dolu = her sayfa giriş ister. Fabrika sunucusunda ya
    # da sistem ağa açıldığında DOLDURULMALIDIR — kural değiştirebilen ve
    # anons tetikleyen bir sistem LAN'da bile şifresiz durmamalı.
    yonetici_sifresi: str
    # Sunucunun DİNLEYECEĞİ adres. 127.0.0.1 = yalnız bu bilgisayar (varsayılan).
    # 0.0.0.0 = ağdaki diğer cihazlar da erişebilir (uzaktan erişimin ön koşulu).
    # Şifresiz bir sistemin ağa açılması AÇILIŞTA REDDEDİLİR — bkz. ayarlari_yukle.
    sunucu_adresi: str
    anons: str
    anons_http_adresi: str
    anons_http_bicimi: str
    anons_bekleme_sn: int
    model_dosyasi: Path
    nesne_izinli_uzantilar: tuple[str, ...]
    nesne_foto_en_buyuk_mb: int
    nesne_tarama_en_cok_dosya: int
    nesne_eslesme_esigi: float
    # Ayarların yazıldığı dosya. Ayarlar sayfası (web/ayar_rotalari.py) buraya
    # yazar; yolun kendisi ekranda GÖSTERİLMEZ, yalnızca dosya işlemi için var.
    env_yolu: Path
    # Yazılabilir klasör olağandışı seçildiyse (paketlenmiş program, kayıtlar
    # eski yerde bulundu) açılışta günlüğe düşecek cümle. Olağan durumda boş.
    veri_konumu_notu: str = ""
    veri_konumu_ayrintisi: str = ""


def _yerel_adres_mi(adres: str) -> bool:
    """Adres yalnızca BU bilgisayardan mı erişilebilir?

    127.x.x.x ve ::1 yereldir; 0.0.0.0, :: ve gerçek bir IP ağa açar.
    """
    temiz = adres.strip().strip("[]").lower()
    return temiz.startswith("127.") or temiz in ("localhost", "::1")


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

    # Not: giriş şifresi bilerek YOK (docs/07 #0). Sistem tek makinede, yalnızca
    # 127.0.0.1'e bağlı çalışır; fabrika sunucusuna çıkmadan önce geri eklenir.

    # Not: sistemin portunu Kontrol Paneli belirler (8080). Bu yüzden .env'de
    # port ayarı YOKTUR — okunmayan bir ayar ekranda yanlış bilgi gösterirdi.

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
    log_dosyasi = veri_dizini / "loglar" / "sistem.log"

    for klasor in (
        veritabani_yolu.parent,
        goruntu_klasoru,
        nesne_klasoru,
        nesne_tarama_klasoru,
        log_dosyasi.parent,
    ):
        _klasor_olustur(klasor)

    yonetici_sifresi = degerler.get("YONETICI_SIFRESI", "").strip()
    if yonetici_sifresi and len(yonetici_sifresi) < 6:
        raise AyarHatasi(
            ".env dosyasındaki YONETICI_SIFRESI en az 6 karakter olmalı. "
            "Şifre istemiyorsanız satırı boş bırakın (giriş sorulmaz)."
        )

    sunucu_adresi = degerler.get("SUNUCU_ADRESI", "127.0.0.1").strip() or "127.0.0.1"
    # EMNİYET KİLİDİ: sistemi ağa açıp şifresiz bırakmak, ağdaki herkese
    # kamera silme ve anons yaptırma yetkisi vermektir. Bu, uyarıyla
    # geçiştirilecek bir durum değil — açılış DURDURULUR.
    if not _yerel_adres_mi(sunucu_adresi) and not yonetici_sifresi:
        raise AyarHatasi(
            f".env dosyasında SUNUCU_ADRESI={sunucu_adresi} yazıyor: sistem ağdaki "
            "diğer cihazlara açılacak. Ama YONETICI_SIFRESI boş — bu haliyle ağdaki "
            "herkes kamera silebilir, kural değiştirebilir ve hoparlörden anons "
            "yaptırabilir.\n\n"
            "Ya YONETICI_SIFRESI satırına bir şifre yazın (en az 6 karakter), "
            "ya da SUNUCU_ADRESI satırını 127.0.0.1 yapın. "
            "Uzaktan erişim tarifi: docs/15-UZAKTAN-ERISIM.md"
        )

    anons = _secenek(degerler, "ANONS", varsayilan="null", secenekler=_ANONS_SECENEKLERI)
    anons_http_adresi = degerler.get("ANONS_HTTP_ADRESI", "")
    anons_http_bicimi = _secenek(
        degerler, "ANONS_HTTP_BICIMI", varsayilan="json", secenekler=_ANONS_BICIM_SECENEKLERI
    )
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
        # GET biçiminde mesaj GÖVDEDE gönderilemez; adresin hangi mesajın
        # çalınacağını taşıması gerekir. Yer tutucusuz bir adres, her ihlalde
        # AYNI sesi çalardı ve kullanıcı bunu ancak sahada fark ederdi.
        if anons_http_bicimi == "get" and not any(
            yer in anons_http_adresi for yer in ("{anahtar}", "{metin}")
        ):
            raise AyarHatasi(
                ".env dosyasında ANONS_HTTP_BICIMI=get seçilmiş ama ANONS_HTTP_ADRESI "
                "hangi mesajın çalınacağını taşımıyor. Adrese {anahtar} yer tutucusunu "
                "ekleyin. Örnek: http://10.0.0.9/play?file={anahtar}. "
                "Ayrıntı: docs/14-ANONS-SISTEMI-BAGLAMA.md"
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
        # örneklenir (docs/04 §4.3 — aynı kişinin 200 ardışık karesi değil)
        kkd_ornek_saat_limit=_tam_sayi(degerler, "KKD_ORNEK_SAAT_LIMIT", 60, 1, 3600),
        # Boş disk bu değerin altına inince sistem olayı üretilir (docs/08 R8)
        disk_uyari_gb=_tam_sayi(degerler, "DISK_UYARI_GB", 5, 1, 1000),
        cikarim_cihazi=_secenek(degerler, "CIKARIM_CIHAZI", "cpu", _CIHAZ_SECENEKLERI),
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
        anons=anons,
        anons_http_adresi=anons_http_adresi,
        anons_http_bicimi=anons_http_bicimi,
        # Anons, ekran uyarısından bağımsız ve daha seyrek çalar (docs/02 §7):
        # hoparlör aynı kamera+mesaj için bu süre dolmadan tekrar bağırmaz.
        anons_bekleme_sn=_tam_sayi(degerler, "ANONS_BEKLEME_SN", 30, 5, 3600),
        model_dosyasi=kok / _metin(degerler, "MODEL_DOSYASI", "models/yolox_tiny.onnx"),
        # --- Nesne kütüphanesi sınırları -------------------------------------
        # Yükleme doğrulaması koda gömülmez (CLAUDE.md §7): hangi uzantı kabul
        # edilir, dosya en fazla kaç MB olur, bir taramada kaç dosya işlenir —
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
        env_yolu=kok / ".env",
        veri_konumu_notu=konum.gunluk_notu,
        veri_konumu_ayrintisi=konum.gunluk_ayrintisi,
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


def env_guncelle(metin: str, degisiklikler: dict[str, str]) -> str:
    """Ayar dosyasının metnini, açıklama satırlarına dokunmadan günceller.

    Var olan anahtarın yalnızca değeri değişir; dosyada olmayan anahtarlar
    sona eklenir.
    """
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
    geçici dosya bilerek silinmez — bir sonraki kayıtta üzerine yazılır ve
    varlığı destek için ipucudur.
    """
    try:
        eski_metin = env_yolu.read_text(encoding="utf-8") if env_yolu.is_file() else ""
    except OSError as hata:
        raise AyarHatasi(
            "Ayar dosyası okunamadı; kaydedilemedi.",
            f"{env_yolu} okunamadı: {hata!r}",
        ) from hata

    gecici = env_yolu.with_name(env_yolu.name + ".yeni")
    try:
        gecici.write_text(env_guncelle(eski_metin, degisiklikler), encoding="utf-8")
        gecici.replace(env_yolu)
    except OSError as hata:
        raise AyarHatasi(
            "Ayarlar kaydedilemedi: klasöre yazılamıyor. Diskte yer olduğundan "
            "ve programın kapalı olmadığından emin olun.",
            f"{gecici} → {env_yolu} yazılamadı: {hata!r}",
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
