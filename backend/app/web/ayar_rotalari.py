"""Ayarlar sayfası: `.env` dosyasını ekrandan düzenleme.

NEDEN VAR: bugüne kadar eşikler, anons adresi ve saklama süreleri yalnızca
`.env` dosyası elle açılıp değiştirilerek ayarlanabiliyordu. Kullanıcı yazılım
bilmiyor; paketlenmiş programda o dosya kullanıcı profilinde, gözle
bulunamayacak bir klasörde duruyor. Bu sayfa olmadan sahada bir eşik
değiştirmek imkânsız olurdu.

İKİ GÜVENCE:

1. **Kaydetmeden önce doğrulama.** Form değerleri, sistemin açılışta
   kullandığı AYNI doğrulayıcıdan (`ayarlar.ayarlari_coz`) geçirilir. Geçmezse
   dosyaya hiçbir şey yazılmaz. Kaydedilen bir ayar yüzünden sistem bir daha
   açılamaz duruma DÜŞEMEZ.
2. **Açıklamalar korunur.** Dosya baştan yazılmaz; yalnızca ilgili satırın
   değeri değişir (`ayarlar.env_guncelle`).

Değişiklikler yeniden başlatınca geçerli olur: `Ayarlar` nesnesi açılışta bir
kez okunur ve çalışırken değiştirilmez. Bu sayfanın en üstünde de aynı cümle
yazar — "kaydettim ama hiçbir şey değişmedi" sorusu doğmasın diye.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ayarlar as ayarlar_modulu
from app.hatalar import AyarHatasi, DogrulamaHatasi
from app.web.komuta import kabuk_baglami
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()


@dataclass(frozen=True)
class AyarAlani:
    """Ekrandaki tek bir ayar kutusu.

    `anahtar` .env'deki ad, `alan` ise `Ayarlar` nesnesindeki karşılığıdır:
    ekranda gösterilen değer dosyadan değil ÇALIŞAN SİSTEMDEN okunur, böylece
    .env'de hiç yazmayan bir ayarın yerinde varsayılanı görünür.
    """

    anahtar: str
    alan: str
    etiket: str
    aciklama: str
    tur: str = "sayi"  # sayi | ondalik | secim | metin
    en_az: str = ""
    en_cok: str = ""
    adim: str = "1"
    ipucu: str = ""
    secenekler: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AyarGrubu:
    baslik: str
    aciklama: str
    alanlar: tuple[AyarAlani, ...] = field(default_factory=tuple)


# Sınırlar (en_az/en_cok) ayarlar.py'deki doğrulayıcıyla AYNI olmalıdır:
# tarayıcı bunları kutunun içinde gösterir, asıl kararı yine ayarlar.py verir.
AYAR_GRUPLARI: tuple[AyarGrubu, ...] = (
    AyarGrubu(
        baslik="Anons (hoparlör)",
        aciklama=(
            "İhlalde sesin nereden çıkacağını belirler. Mesajların metnini ve "
            "hangi bölümde hangi hoparlörün konuşacağını Anons sistemi sayfasından "
            "ayarlarsınız."
        ),
        alanlar=(
            AyarAlani(
                anahtar="ANONS",
                alan="anons",
                etiket="Anons yolu",
                tur="secim",
                secenekler=(
                    ("null", "Kapalı — yalnızca ekran uyarısı"),
                    ("ses_karti", "Bu bilgisayarın ses kartı"),
                    ("http", "IP hoparlör / anons sunucusu"),
                ),
                aciklama=(
                    "“Kapalı” seçiliyken hoparlörden hiç ses çıkmaz; ihlal yine "
                    "ekranda görünür ve kaydedilir."
                ),
            ),
            AyarAlani(
                anahtar="ANONS_HTTP_ADRESI",
                alan="anons_http_adresi",
                etiket="IP hoparlör adresi",
                tur="metin",
                ipucu="http://10.0.0.9:8080/anons",
                aciklama=(
                    "Yalnızca “IP hoparlör” seçiliyken kullanılır ve http:// veya "
                    "https:// ile başlamalıdır. Bölüm bazlı hoparlörler Anons "
                    "sistemi sayfasından tanımlanır; burası onların hiçbirine "
                    "uymayan ihlaller için kullanılan adrestir."
                ),
            ),
            AyarAlani(
                anahtar="ANONS_HTTP_BICIMI",
                alan="anons_http_bicimi",
                etiket="IP hoparlörün beklediği biçim",
                tur="secim",
                secenekler=(
                    ("json", "JSON gövde — anons sunucusu / yazılım geçidi"),
                    ("form", "Form alanı — gömülü web arayüzlü amfi, röle kartı"),
                    ("get", "Yalnızca adres çağrılır — “çağır ve çal” hoparlörler"),
                ),
                aciklama=(
                    "IP hoparlörler isteği aynı biçimde beklemez; cihazınızın "
                    "belgesinde yazan biçimi seçin. “Yalnızca adres” seçilirse "
                    "adreste {anahtar} yer tutucusu bulunmalıdır — örnek: "
                    "http://10.0.0.9/play?file={anahtar} · Hangi cihaz için "
                    "hangisi: docs/14-ANONS-SISTEMI-BAGLAMA.md"
                ),
            ),
            AyarAlani(
                anahtar="ANONS_BEKLEME_SN",
                alan="anons_bekleme_sn",
                etiket="Hoparlörün susma süresi (saniye)",
                en_az="5",
                en_cok="3600",
                aciklama=(
                    "Aynı kamera ve aynı mesaj için hoparlör bu süre dolmadan "
                    "tekrar bağırmaz. Kısaltırsanız uyarı sıklaşır, uzatırsanız "
                    "sahadaki gürültü azalır."
                ),
            ),
        ),
    ),
    AyarGrubu(
        baslik="Tespit hassasiyeti",
        aciklama=(
            "Düşük eşik = daha çok tespit ama daha çok YANLIŞ ALARM. Bir değeri "
            "değiştirdikten sonra sistemi yeniden başlatın ve kamera sayfasındaki "
            "canlı görüntüde kutulara bakın."
        ),
        alanlar=(
            AyarAlani(
                anahtar="TESPIT_INSAN_GUVEN_ESIGI",
                alan="tespit_insan_guven_esigi",
                etiket="İnsan için güven eşiği",
                tur="ondalik",
                en_az="0.05",
                en_cok="0.95",
                adim="0.01",
                aciklama=(
                    "İnsan eşiği bilerek daha düşüktür: kaçırılan bir insan, "
                    "kaçırılan bir araçtan daha risklidir. Kişiler görünmüyorsa "
                    "azaltın (örnek 0.22), gölge/direk insan sanılıyorsa artırın."
                ),
            ),
            AyarAlani(
                anahtar="TESPIT_GUVEN_ESIGI",
                alan="tespit_guven_esigi",
                etiket="Forklift ve tır için güven eşiği",
                tur="ondalik",
                en_az="0.05",
                en_cok="0.95",
                adim="0.01",
                aciklama="Araçlar görünmüyorsa azaltın, boşluğa kutu çiziliyorsa artırın.",
            ),
            AyarAlani(
                anahtar="TESPIT_NMS_ESIGI",
                alan="tespit_nms_esigi",
                etiket="Üst üste binen kutuların birleştirilmesi",
                tur="ondalik",
                en_az="0.1",
                en_cok="0.9",
                adim="0.05",
                aciklama=(
                    "Kalabalıkta iki kişi tek kutuda birleşiyorsa artırın "
                    "(0.5 – 0.6 deneyin); aynı kişiye iki kutu çiziliyorsa azaltın."
                ),
            ),
            AyarAlani(
                anahtar="TESPIT_EN_KUCUK_KENAR_PX",
                alan="tespit_en_kucuk_kenar_px",
                etiket="En küçük kutu kenarı (piksel)",
                en_az="2",
                en_cok="500",
                aciklama=(
                    "Bundan küçük kutular atılır. Uzaktaki birkaç piksellik gürültü "
                    "insan sanılıp yanlış alarm üretmesin diye vardır; uzak "
                    "kişileri kaçırıyorsanız azaltın."
                ),
            ),
            AyarAlani(
                anahtar="GORUNTU_IYILESTIRME",
                alan="goruntu_iyilestirme",
                etiket="Görüntü iyileştirme",
                tur="secim",
                secenekler=(
                    ("kapali", "Kapalı"),
                    ("otomatik", "Otomatik (karanlık/sisli görüntü için)"),
                ),
                aciklama=(
                    "Karanlık, sisli veya düşük kontrastlı kameralarda yerel "
                    "kontrast dengeleme uygular; renkleri bozmaz ama işlemciyi "
                    "biraz daha yorar."
                ),
            ),
            AyarAlani(
                anahtar="CIKARIM_CIHAZI",
                alan="cikarim_cihazi",
                etiket="Tespitin çalıştığı donanım",
                tur="secim",
                secenekler=(("cpu", "İşlemci (CPU)"), ("cuda", "Ekran kartı (NVIDIA)")),
                aciklama=(
                    "Ekran kartı yalnızca uygun bir NVIDIA kartı ve sürücüsü olan "
                    "sunucuda seçilmelidir. Kart bulunamazsa sistem işlemciye "
                    "geri döner ve bunu günlüğe yazar."
                ),
            ),
        ),
    ),
    AyarGrubu(
        baslik="Nesne arama (Nesneler sayfası)",
        aciklama=(
            "Yalnızca Nesneler sayfasında, sizin yüklediğiniz fotoğraflarda yapılan "
            "aramayı etkiler. Canlı kameralara, kurallara ve olay kayıtlarına DOKUNMAZ."
        ),
        alanlar=(
            AyarAlani(
                anahtar="NESNE_ESLESME_ESIGI",
                alan="nesne_eslesme_esigi",
                etiket="Nesne arama titizliği",
                tur="ondalik",
                en_az="0.05",
                en_cok="0.95",
                adim="0.01",
                aciklama=(
                    "Sistemin bir yere nesne adı yazmak için aradığı benzerlik. "
                    "Ölçümle bulunan değer 0.24'tür: 264 sorguluk ölçümde hiç yanlış "
                    "isim yazmadan en çok nesnenin bulunduğu nokta. Yükseltmek yanlış "
                    "isimden korumaz (0.24 ve üstündeki her kademede yanlış isim zaten "
                    "sıfır), yalnızca daha az nesne buldurur — 0.36'da hiçbir nesne "
                    "bulunmaz. Düşürmek ise tehlikelidir: 0.22'de sistem yanlış isim "
                    "yazmaya başlar. Bilerek değiştirmiyorsanız 0.24'te bırakın."
                ),
            ),
        ),
    ),
    AyarGrubu(
        baslik="Saklama süreleri ve disk",
        aciklama=(
            "Kayıtların ne kadar süre tutulacağı. KVKK politikanızla uyumlu "
            "olmalıdır: süre dolan kayıtlar bakım döngüsünde SİLİNİR, geri gelmez."
        ),
        alanlar=(
            AyarAlani(
                anahtar="OLAY_SAKLAMA_GUN",
                alan="olay_saklama_gun",
                etiket="İhlal kayıtları (gün)",
                en_az="1",
                en_cok="3650",
                aciklama="Olay listesindeki satırların saklanma süresi.",
            ),
            AyarAlani(
                anahtar="GORUNTU_SAKLAMA_GUN",
                alan="goruntu_saklama_gun",
                etiket="Kanıt fotoğrafları (gün)",
                en_az="1",
                en_cok="3650",
                aciklama=(
                    "Fotoğraflar diskte en çok yer kaplayan kayıttır. Olay "
                    "kaydından kısa tutulursa satır kalır, fotoğrafı kalmaz."
                ),
            ),
            AyarAlani(
                anahtar="KKD_HAM_VERI_SAKLAMA_GUN",
                alan="kkd_ham_veri_saklama_gun",
                etiket="KKD eğitim örnekleri (gün)",
                en_az="1",
                en_cok="3650",
                aciklama="Baret/yelek modelini eğitmek için toplanan kişi görüntüleri.",
            ),
            AyarAlani(
                anahtar="SISTEM_OLAY_SAKLAMA_GUN",
                alan="sistem_olay_saklama_gun",
                etiket="Sistem olayları (gün)",
                en_az="1",
                en_cok="3650",
                aciklama="Kamera koptu, disk azaldı gibi teknik kayıtlar.",
            ),
            AyarAlani(
                anahtar="DISK_UYARI_GB",
                alan="disk_uyari_gb",
                etiket="Disk uyarı sınırı (GB)",
                en_az="1",
                en_cok="1000",
                aciklama="Boş disk bu değerin altına inince olay listesine uyarı düşer.",
            ),
        ),
    ),
)

TUM_ALANLAR: tuple[AyarAlani, ...] = tuple(alan for grup in AYAR_GRUPLARI for alan in grup.alanlar)

# Kaydedildikten sonra gösterilen tek satırlık geri bildirim. Ham yol değil
# anahtar alınır (anons_web.py DONUS_YOLLARI ile aynı desen).
SONUC_MESAJLARI = {
    "kaydedildi": (
        "Ayarlar kaydedildi. Geçerli olması için Kontrol Paneli'nde Durdur'a, "
        "sonra Sistemi Başlat'a basın."
    ),
}


@router.get("/ayarlar", response_class=HTMLResponse)
def ayarlar_sayfasi(istek: Request, sonuc: str = "", baglanti=Depends(baglanti_al)):
    ayarlar = istek.app.state.ayarlar
    baglam = kabuk_baglami(istek, baglanti, "ayarlar")
    baglam.update(
        {
            "gruplar": AYAR_GRUPLARI,
            "degerler": {alan.anahtar: _gosterilecek_deger(ayarlar, alan) for alan in TUM_ALANLAR},
            "sonuc_mesaji": SONUC_MESAJLARI.get(sonuc, ""),
        }
    )
    return sablonlar.TemplateResponse(istek, "komuta_ayarlar.html", baglam)


@router.post("/ayarlar/kaydet")
async def ayarlari_kaydet(istek: Request):
    """Formu doğrular, geçerse .env'e yazar. Geçmezse dosyaya DOKUNMAZ."""
    ayarlar = istek.app.state.ayarlar
    form = await istek.form()

    degisiklikler = {
        alan.anahtar: str(form[alan.anahtar]).strip()
        for alan in TUM_ALANLAR
        if alan.anahtar in form
    }
    if not degisiklikler:
        raise DogrulamaHatasi("Kaydedilecek ayar bulunamadı. Sayfayı yenileyip tekrar deneyin.")

    # Dosyadaki mevcut değerlerin üzerine formdakiler yazılır; sistemin
    # açılışta kullandığı doğrulayıcı bu birleşik sözlüğü sınar.
    birlesik = ayarlar_modulu.env_degerlerini_oku(ayarlar.env_yolu)
    birlesik.update(degisiklikler)
    try:
        ayarlar_modulu.ayarlari_coz(ayarlar.kok_dizin, birlesik)
    except AyarHatasi as hata:
        raise DogrulamaHatasi(_anlasilir_hata(hata.kullanici_mesaji), hata.teknik_ayrinti) from hata

    ayarlar_modulu.env_dosyasina_yaz(ayarlar.env_yolu, degisiklikler)
    return RedirectResponse("/ayarlar?sonuc=kaydedildi", status_code=303)


def _gosterilecek_deger(ayarlar, alan: AyarAlani) -> str:
    """Çalışan sistemdeki değerin form kutusuna yazılacak hali."""
    deger = getattr(ayarlar, alan.alan)
    if isinstance(deger, float):
        # 0.35 → "0.35", 0.6 → "0.6"  (sayı kutusu noktalı yazım bekler)
        return f"{deger:g}"
    return str(deger)


def _anlasilir_hata(mesaj: str) -> str:
    """Açılış hatasını form diline çevirir: '.env dosyasında X' → '“Etiket”'.

    Kullanıcı bir dosya değil, bir form dolduruyor; ekranda dosya adı ve
    büyük harfli anahtar görmesi kafa karıştırır.
    """
    metin = mesaj.replace(".env dosyasında ", "")
    # UZUN anahtar önce: "ANONS" kısa adı, "ANONS_HTTP_ADRESI"nin içinde de
    # geçer. Kısa olan önce değiştirilirse uzun anahtar ortasından bölünür ve
    # ekranda "“Anons yolu”_HTTP_ADRESI" gibi bir metin çıkardı.
    for alan in sorted(TUM_ALANLAR, key=lambda a: len(a.anahtar), reverse=True):
        metin = metin.replace(alan.anahtar, f"“{alan.etiket}”")
    return "Ayarlar kaydedilmedi. " + metin
