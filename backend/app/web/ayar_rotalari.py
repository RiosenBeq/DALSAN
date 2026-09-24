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
yazar - "kaydettim ama hiçbir şey değişmedi" sorusu doğmasın diye.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ayarlar as ayarlar_modulu
from app.analiz.model_adi import OZEL_MODEL_ADI, gorunen_model_adi
from app.analiz.model_indir import BILINEN_MODELLER, FORKLIFT_TABANI
from app.hatalar import AyarHatasi, DogrulamaHatasi
from app.olaylar import uyari_arsivi
from app.web import erisim_izi
from app.web.erisim_izi import erisim_yaz
from app.web.komuta import kabuk_baglami
from app.web.ortak import baglanti_al, maskeyi_coz, rtsp_maskele
from app.web.rotalar import sablonlar

router = APIRouter()


# Tanıma modeli seçimi: hazır modeller models/ klasöründe, dosya adıyla durur
# (analiz/model_indir.BILINEN_MODELLER). Ekranda dosya adı değil ürün adı yazar.
MODEL_SECENEKLERI: tuple[tuple[str, str], ...] = tuple(
    (f"models/{ad}", gorunen_model_adi(ad)) for ad in BILINEN_MODELLER
)
# Listede olmayan (kendi eğitilmiş) model kurulu: seçim kutusu onu "özel model"
# diye gösterir ve bu değer gelirse MODEL_DOSYASI'na DOKUNULMAZ. Yoksa başka
# bir ayarı kaydeden kullanıcının özel modeli sessizce hazır modelle değişirdi.
OZEL_MODEL_SECIMI = "ozel"


def model_aciklamasi(forklift_modeli_var: bool) -> str:
    """ "Tanıma modeli" kutusunun açıklaması. Forklift modeli kayıtlıysa, ona
    geçenin "Tır/Araç" kurallarında ne yapması gerektiğini de söyler: bu modelde
    forklift artık tır sayılmaz ve yalnız "Tır/Araç" seçili kural onu görmez."""
    forklift = (
        "Adında “Forklift” geçen model forklifti ayrı sınıf olarak da tanır; insanı ve "
        "aracı adındaki hazır modelle aynı tanır, işlemciyi biraz daha yorar. O modelde "
        "forklift artık “Tır/Araç” sayılmaz: yalnız “Tır/Araç” seçili kurallarda "
        "“Forklift”i de işaretleyin (tır park alanının bölge kuralı bilerek yalnız "
        "tırdır). Kurulum listesi bu kuralları söyler. "
        if forklift_modeli_var
        else ""
    )
    return (
        "“İsabetli” daha isabetlidir ama daha yavaştır, işlemciyi daha çok yorar. "
        f"{forklift}Seçilen model ilk açılışta bir kez iner (internet gerekir)."
    )


@dataclass(frozen=True)
class AyarAlani:
    """Ekrandaki tek bir ayar kutusu.

    `anahtar` .env'deki ad, `alan` ise `Ayarlar` nesnesindeki karşılığıdır:
    ekranda gösterilen değer .env'den açılıştaki çözücüyle okunur, böylece
    .env'de hiç yazmayan bir ayarın yerinde varsayılanı görünür
    (bkz. `_kayitli_ayarlar`).
    """

    anahtar: str
    alan: str
    etiket: str
    aciklama: str
    tur: str = "sayi"  # sayi | ondalik | secim | metin | sifre
    en_az: str = ""
    en_cok: str = ""
    adim: str = "1"
    ipucu: str = ""
    secenekler: tuple[tuple[str, str], ...] = ()
    # Adresteki kullanıcı adı/şifre kutuya •••• ile yazılır; •••• olduğu gibi
    # gelirse kayıtlı kimlik korunur (R18, web/ortak.maskeyi_coz)
    maskeli: bool = False


@dataclass(frozen=True)
class AyarGrubu:
    baslik: str
    aciklama: str
    alanlar: tuple[AyarAlani, ...] = field(default_factory=tuple)


# Sınırlar (en_az/en_cok) ayarlar.py'deki doğrulayıcıyla AYNI olmalıdır:
# tarayıcı bunları kutunun içinde gösterir, asıl kararı yine ayarlar.py verir.
AYAR_GRUPLARI: tuple[AyarGrubu, ...] = (
    AyarGrubu(
        baslik="Güvenlik",
        aciklama=(
            "Sistem bugün yalnızca bu bilgisayardan açılıyorsa şifre gerekmez. "
            "Fabrika sunucusuna taşırken ya da sistemi ağa açarken şifre koyun: "
            "sisteme girebilen herkes kamera silebilir, kural değiştirebilir ve "
            "hoparlörden anons yaptırabilir."
        ),
        alanlar=(
            AyarAlani(
                anahtar="SUNUCU_ADRESI",
                alan="sunucu_adresi",
                tur="secim",
                etiket="Sisteme nereden erişilebilsin?",
                secenekler=(
                    ("127.0.0.1", "Yalnız bu bilgisayar (varsayılan)"),
                    ("0.0.0.0", "Ağdaki diğer cihazlar da (telefon, başka bilgisayar)"),
                ),
                aciklama=(
                    "“Ağdaki diğer cihazlar” seçilirse ŞİFRE ZORUNLUDUR; şifre boşken "
                    "sistem açılmayı reddeder. Fabrika dışından (evden, telefondan) "
                    "erişim için önce docs/15-UZAKTAN-ERISIM.md belgesini okuyun - "
                    "sistemi doğrudan internete açmak önerilmez."
                ),
            ),
            AyarAlani(
                anahtar="IZINLI_SUNUCU_ADLARI",
                alan="izinli_sunucu_adlari",
                tur="metin",
                etiket="İzinli sunucu adları",
                ipucu="örn. 192.168.1.50, isg.dalsan.local",
                aciklama=(
                    "Sisteme başka bir cihazdan hangi adresle giriliyorsa o ad buraya "
                    "yazılır; birden fazlaysa virgülle ayırın. Bu bilgisayarın kendisi "
                    "(127.0.0.1) her zaman izinlidir. Yazılmamış bir adla gelen istek "
                    "“Bu adrese izin verilmiyor” sayfasına düşer: başka bir internet "
                    "sitesinin kendi adını bu bilgisayara yönlendirip sisteme ulaşmasını "
                    "bu liste durdurur."
                ),
            ),
            AyarAlani(
                anahtar="YONETICI_SIFRESI",
                alan="yonetici_sifresi",
                etiket="Yönetici şifresi",
                tur="sifre",
                aciklama=(
                    "Kurulu şifre bu sayfada hiçbir zaman gösterilmez. Değiştirmek için "
                    "yeni şifreyi yazın; kutuyu boş bırakırsanız mevcut şifre aynen "
                    "kalır. Şifre en az 6 karakter olmalıdır. Değişiklik sistemi yeniden "
                    "başlattıktan sonra geçerli olur ve açık oturumların hepsi düşer."
                ),
            ),
        ),
    ),
    AyarGrubu(
        baslik="Anons (hoparlör)",
        aciklama=(
            "Sesin hangi kanaldan çıkacağı (bu bilgisayarın ses çıkışı, Bluetooth "
            "hoparlör, IP hoparlör) burada değil, Anons sistemi ekranındaki kanal "
            "listesinde tanımlanır. Buradaki iki ayar bütün kanallar için ortaktır."
        ),
        alanlar=(
            AyarAlani(
                anahtar="ANONS_HTTP_BICIMI",
                alan="anons_http_bicimi",
                etiket="IP hoparlörün beklediği biçim",
                tur="secim",
                secenekler=(
                    ("json", "JSON gövde - anons sunucusu / yazılım geçidi"),
                    ("form", "Form alanı - gömülü web arayüzlü amfi, röle kartı"),
                    ("get", "Yalnızca adres çağrılır - “çağır ve çal” hoparlörler"),
                ),
                aciklama=(
                    "IP hoparlörler isteği aynı biçimde beklemez; cihazınızın "
                    "belgesinde yazan biçimi seçin. “Yalnızca adres” seçilirse "
                    "kanalın adresinde {anahtar} yer tutucusu bulunmalıdır; örnek: "
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
            AyarAlani(
                anahtar="ANONS_SAGLIK_ARALIGI_SN",
                alan="anons_saglik_araligi_sn",
                etiket="Kanal yoklama aralığı (saniye)",
                en_az="2",
                en_cok="300",
                aciklama=(
                    "Her kanal bu aralıkla yoklanır: ses çıkışı listede mi, IP "
                    "hoparlörün adresine bağlanılabiliyor mu. Öneri: 10."
                ),
            ),
            AyarAlani(
                anahtar="ANONS_KOPUK_ESIGI_SN",
                alan="anons_kopuk_esigi_sn",
                etiket="Kanal kopukluk eşiği (saniye)",
                en_az="5",
                en_cok="3600",
                aciklama=(
                    "Bu süre boyunca kesintisiz bağlı görünmeyen kanal için "
                    "Olaylar'a “Ses kanalı koptu” yazılır. Kısa aksaklık olay "
                    "üretmez. Öneri: 30."
                ),
            ),
            AyarAlani(
                anahtar="ULASMAYAN_UYARI_ARALIGI_SN",
                alan="ulasmayan_uyari_araligi_sn",
                etiket="“Uyarı ulaşamadı” olay aralığı (saniye)",
                en_az="30",
                en_cok="86400",
                aciklama=(
                    "Uyarı hiçbir sesli kanala ulaşamazsa olay yazılır; aynı "
                    "kamera için en çok bu aralıkla bir kez, aradakiler sayılıp "
                    "olaya eklenir. Öneri: 300."
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
                anahtar="MODEL_DOSYASI",
                alan="model_dosyasi",
                etiket="Tanıma modeli",
                tur="secim",
                secenekler=MODEL_SECENEKLERI,
                aciklama=model_aciklamasi(bool(FORKLIFT_TABANI)),
            ),
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
                    "(0.5 - 0.6 deneyin); aynı kişiye iki kutu çiziliyorsa azaltın."
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
        baslik="Takip ve kamera bağlantısı",
        aciklama=(
            "Görüntüden bir an kaybolan kişinin aynı kişi sayılması ve kopan bir "
            "kameranın ne kadar sürede fark edilmesi."
        ),
        alanlar=(
            AyarAlani(
                anahtar="TAKIP_HAFIZA_SN",
                alan="takip_hafiza_sn",
                etiket="Takip hafızası (sn)",
                tur="ondalik",
                en_az="0.5",
                en_cok="10",
                adim="0.5",
                aciklama=(
                    "Bir kolonun ya da forkliftin arkasından geçen kişi bu kadar saniye "
                    "aynı kişi sayılır. Kısa tutulursa kişi 'yeni biri' sayılır ve uyarı "
                    "tekrarlar; çok uzun tutulursa yan yana yürüyenlerin kimlikleri karışabilir."
                ),
            ),
            AyarAlani(
                anahtar="KAMERA_KOPUK_ESIGI_SN",
                alan="kamera_kopuk_esigi_sn",
                etiket="Kamera kopukluk süresi (sn)",
                tur="ondalik",
                en_az="3",
                en_cok="600",
                adim="1",
                aciklama=(
                    "Görüntü bu kadar saniye kesilirse kamera “çevrimdışı” görünür ve "
                    "Olaylar'a yazılır. Yeni eklenen kameraya ilk bağlantı için ayrıca "
                    "60 sn tanınır."
                ),
            ),
        ),
    ),
    AyarGrubu(
        baslik="Analiz sağlığı",
        aciklama=(
            "Analizin takılması ya da yavaşlaması sessiz kalmasın: bu eşikler aşılınca "
            "Olaylar'a sistem olayı düşer ve komuta ekranlarında şerit çıkar."
        ),
        alanlar=(
            AyarAlani(
                anahtar="BEKCI_ESIGI_SN",
                alan="bekci_esigi_sn",
                etiket="Takılma süresi (sn)",
                tur="ondalik",
                en_az="20",
                en_cok="3600",
                adim="5",
                aciklama=(
                    "Görüntü gelirken analiz bu kadar saniye ilerlemezse “Analiz takıldı” "
                    "olayı yazılır; o sürede hiçbir uyarı üretilmiyordur."
                ),
            ),
            AyarAlani(
                anahtar="BEKCI_TEPKISI",
                alan="bekci_tepkisi",
                etiket="Takılınca ne yapılsın",
                tur="secim",
                secenekler=(
                    ("uyar", "Yalnız uyar"),
                    ("yeniden_baslat", "Programı yeniden başlat (Docker / systemd)"),
                ),
                aciklama=(
                    "Yeniden başlatma yalnız sunucu kurulumunda anlamlıdır: program kendini "
                    "kapatır, Docker ya da systemd yeniden açar. Masaüstü programı Kontrol "
                    "Paneli'yle birlikte kapanmasın diye her zaman yalnız uyarır."
                ),
            ),
            AyarAlani(
                anahtar="ANALIZ_YAVAS_SURE_SN",
                alan="analiz_yavas_sure_sn",
                etiket="Yavaşlama süresi (sn)",
                tur="ondalik",
                en_az="10",
                en_cok="3600",
                adim="5",
                aciklama=(
                    "Bir kameranın işlenen görüntü hızı hedefin altında (FPS uyarı oranı) "
                    "bu kadar saniye kalırsa “Analiz yavaşladı” olayı yazılır."
                ),
            ),
            AyarAlani(
                anahtar="ANALIZ_HATA_ESIGI",
                alan="analiz_hata_esigi",
                etiket="Üst üste işleme hatası",
                en_az="3",
                en_cok="10000",
                aciklama=(
                    "Bir kamerada bu kadar görüntü üst üste işlenemezse o kameranın işleme "
                    "hattı yeniden kurulur ve “Analiz yavaşladı” olayı yazılır."
                ),
            ),
        ),
    ),
    AyarGrubu(
        baslik="KKD anons kapısı",
        aciklama=(
            "KKD kuralı gölge modda doğar: olay yazılır, hoparlör susar. Olaylar "
            "“İncelendi” ya da “Yanlış alarm” diye işaretlendikçe KKD sayfasındaki "
            "karne dolar. Anons, baret ve yelek için ayrı ayrı ve yüklü model "
            "sürümü için şu dört şart sağlanınca açılır: precision eşiği, en az gün, "
            "en az incelenmiş olay ve incelenmemiş olay kalmaması. Yeni model sürümü "
            "sayacı sıfırdan başlatır."
        ),
        alanlar=(
            AyarAlani(
                anahtar="KKD_KAPI_PRECISION",
                alan="kkd_kapi_precision",
                etiket="En düşük precision",
                tur="ondalik",
                en_az="0.5",
                en_cok="1",
                adim="0.01",
                aciklama=(
                    "İncelenen olayların kaçta kaçı gerçek ihlal olmalı. 0.90: her 10 "
                    "uyarıdan en az 9'u gerçek (docs/04 §8.1). Düşürmek, çalışanı "
                    "boşuna uyaran bir anonsu açmak demektir. Öneri: 0.90."
                ),
            ),
            AyarAlani(
                anahtar="KKD_KAPI_GUN",
                alan="kkd_kapi_gun",
                etiket="Gölge modda en az gün",
                en_az="1",
                en_cok="90",
                aciklama=(
                    "O kalem ve model sürümünün ilk olayından bu yana geçmesi gereken "
                    "süre. Tek bir vardiyanın ışığı ve işi bütün sahayı temsil etmez. "
                    "Öneri: 3."
                ),
            ),
            AyarAlani(
                anahtar="KKD_KAPI_EN_AZ_OLAY",
                alan="kkd_kapi_en_az_olay",
                etiket="En az incelenmiş olay",
                en_az="1",
                en_cok="10000",
                aciklama=(
                    "Tek doğru olayla precision %100 çıkar ama hiçbir şey söylemez. "
                    "Hiç yanlış alarm yokken bile 30 olayla söylenebilecek en iyi şey "
                    "“hata oranı %95 güvenle en çok %10”dur; 30'un altında ölçülen "
                    "precision güvenilmez. Öneri: 30."
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
                    "sıfır), yalnızca daha az nesne buldurur - 0.36'da hiçbir nesne "
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
                anahtar="UYARI_KAYDI_ARSIV_GUN",
                alan="uyari_kaydi_arsiv_gun",
                etiket="Uyarı kayıtları arşivi (gün)",
                en_az="0",
                en_cok="365",
                aciklama=(
                    "Hangi uyarının hangi hoparlörden çaldığının kaydı bu kadar günde bir "
                    "masaüstündeki “NextGen Detector uyarı kayıtları” klasörüne CSV olarak "
                    "kaydedilir ve dosya doğrulanınca sistemden silinir. Dosya "
                    "yazılamazsa hiçbir kayıt silinmez. 0 = kapalı."
                ),
            ),
            AyarAlani(
                anahtar="UYARI_KAYDI_ARSIV_KLASORU",
                alan="uyari_kaydi_arsiv_klasoru",
                tur="metin",
                etiket="Uyarı kayıtları arşiv klasörü",
                ipucu="boş = masaüstü",
                aciklama=(
                    "Boş bırakılırsa masaüstü kullanılır; masaüstü olmayan sunucuda ve "
                    "Docker'da veri/arsiv/uyari-kayitlari. Başka bir klasör (örneğin bir "
                    "ağ sürücüsü) yazılabilir."
                ),
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
# Sayfa sonradan açıldığında: kaydedilmiş ama henüz geçerli olmayan ayar var
BEKLEYEN_MESAJI = (
    "Kaydedilen ayarların bir kısmı henüz geçerli değil: sistem hâlâ eski değerlerle "
    "çalışıyor. Geçerli olması için Kontrol Paneli'nde Durdur'a, sonra Sistemi "
    "Başlat'a basın."
)


@router.get("/ayarlar", response_class=HTMLResponse)
def ayarlar_sayfasi(istek: Request, sonuc: str = "", baglanti=Depends(baglanti_al)):
    ayarlar = istek.app.state.ayarlar
    kayitli = _kayitli_ayarlar(ayarlar)
    baglam = kabuk_baglami(istek, baglanti, "ayarlar")
    baglam.update(
        {
            "gruplar": AYAR_GRUPLARI,
            "degerler": {alan.anahtar: _gosterilecek_deger(kayitli, alan) for alan in TUM_ALANLAR},
            "secenekler": {
                alan.anahtar: _secenekler(kayitli, alan)
                for alan in TUM_ALANLAR
                if alan.tur == "secim"
            },
            "yonetici_sifresi_kurulu": bool(kayitli.yonetici_sifresi),
            "sonuc_mesaji": SONUC_MESAJLARI.get(sonuc, "")
            or (BEKLEYEN_MESAJI if _bekleyen_degisiklik_var(ayarlar, kayitli) else ""),
            # KVKK: erişim izi ve imha kaydı (docs/17 §10, §11 "Ayarlar → KVKK")
            "kvkk": erisim_izi.kayitlar(baglanti),
            "uyari_arsivi": {
                "gun": ayarlar.uyari_kaydi_arsiv_gun,
                "klasor": uyari_arsivi.klasor_metni(ayarlar),
            },
        }
    )
    return sablonlar.TemplateResponse(istek, "komuta_ayarlar.html", baglam)


@router.post("/ayarlar/kaydet")
async def ayarlari_kaydet(istek: Request, baglanti=Depends(baglanti_al)):
    """Formu doğrular, geçerse .env'e yazar. Geçmezse dosyaya DOKUNMAZ."""
    ayarlar = istek.app.state.ayarlar
    kayitli = _kayitli_ayarlar(ayarlar)
    form = await istek.form()

    degisiklikler: dict[str, str] = {}
    for alan in TUM_ALANLAR:
        if alan.tur == "sifre":
            yeni = _sifre_degisikligi(form, alan.anahtar)
            if yeni is not None:
                degisiklikler[alan.anahtar] = yeni
        elif alan.anahtar in form:
            deger = str(form[alan.anahtar]).strip()
            if alan.anahtar == "MODEL_DOSYASI":
                if deger == OZEL_MODEL_SECIMI:
                    continue  # kurulu özel model olduğu gibi kalır
                if deger not in dict(MODEL_SECENEKLERI):
                    raise DogrulamaHatasi(
                        "Tanıma modeli listedeki modellerden biri olmalı. Sayfayı "
                        "yenileyip yeniden seçin.",
                        f"Geçersiz MODEL_DOSYASI seçimi: {deger!r}",
                    )
            if alan.maskeli:
                # Kutudaki maske, kutuya yazılan (kayıtlı) değerden çözülür
                deger = maskeyi_coz(deger, str(getattr(kayitli, alan.alan)))
            degisiklikler[alan.anahtar] = deger
    if not degisiklikler:
        raise DogrulamaHatasi("Kaydedilecek ayar bulunamadı. Sayfayı yenileyip tekrar deneyin.")

    # Dosyadaki mevcut değerlerin üzerine formdakiler yazılır; sistemin
    # açılışta kullandığı doğrulayıcı bu birleşik sözlüğü sınar.
    birlesik = ayarlar_modulu.env_degerlerini_oku(ayarlar.env_yolu)
    # Erişim izine değişen ayarın yalnız ADI yazılır; değer (şifre, adres) asla
    degisen = _degisen_anahtarlar(kayitli, birlesik, degisiklikler)
    birlesik.update(degisiklikler)
    try:
        ayarlar_modulu.env_degisikliklerini_dogrula(degisiklikler)
        ayarlar_modulu.ayarlari_coz(ayarlar.kok_dizin, birlesik)
    except AyarHatasi as hata:
        raise DogrulamaHatasi(_anlasilir_hata(hata.kullanici_mesaji), hata.teknik_ayrinti) from hata

    ayarlar_modulu.env_dosyasina_yaz(ayarlar.env_yolu, degisiklikler)
    if degisen:
        erisim_yaz(baglanti, istek, "settings_change", ", ".join(degisen))
    return RedirectResponse("/ayarlar?sonuc=kaydedildi", status_code=303)


def _degisen_anahtarlar(ayarlar, dosyadaki: dict, degisiklikler: dict) -> list[str]:
    """Gerçekten değişen ayarların adları (erişim izi için; değerler yazılmaz).

    Önceki değer dosyadaki değerdir; dosyada yoksa sayfanın gösterdiği
    (varsayılan) değer. Form bütün alanları gönderir: yalnız dosyaya bakılsaydı
    hiç dokunulmamış varsayılanlar da "değişti" görünürdü. Şifre alanı yalnız
    kutuya yazılınca ya da "kaldır" işaretlenince gelir: her gelişi değişikliktir.
    """
    alanlar = {alan.anahtar: alan for alan in TUM_ALANLAR}
    degisen = []
    for anahtar, yeni in degisiklikler.items():
        alan = alanlar[anahtar]
        if alan.tur == "sifre":
            degisen.append(anahtar)
            continue
        if anahtar in dosyadaki:
            onceki = dosyadaki[anahtar]
        elif alan.maskeli:
            onceki = str(getattr(ayarlar, alan.alan))
        else:
            onceki = _gosterilecek_deger(ayarlar, alan)
        if onceki != yeni:
            degisen.append(anahtar)
    return sorted(degisen)


# Şifreyi kaldırmak için ayrı onay kutusu: şifre kutusu artık boş gelir ve
# "boş" = "değiştirme" demektir, yani kaldırma isteği başka yoldan gelmeli.
SIFRE_KALDIR_EKI = "_KALDIR"


def _sifre_degisikligi(form, anahtar: str) -> str | None:
    """Şifre alanının dosyaya yazılacak yeni değeri; değişiklik yoksa None.

    Boş kutu şifreyi DEĞİŞTİRMEZ: kutu kurulu şifreyi bilerek göstermez
    (docs/AUDIT.md R9), dolayısıyla başka bir ayarı kaydeden kullanıcının
    şifresi sessizce silinmemeli. Kaldırmak için "Şifreyi kaldır" işaretlenir;
    sistem ağa açıksa bunu açılış doğrulayıcısı zaten reddeder.
    """
    if form.get(anahtar + SIFRE_KALDIR_EKI):
        return ""
    yeni = str(form.get(anahtar, "")).strip()
    return yeni or None


def _kayitli_ayarlar(ayarlar):
    """Ayar dosyasında KAYITLI değerler; sayfa bunları gösterir.

    Kaydedilen ayar ancak yeniden başlatınca geçerli olur. Sayfa çalışan
    sistemin değerlerini gösterseydi, yeniden başlatmadan yapılan ikinci kayıt
    formdaki eski (çalışan) değerleri dosyaya geri yazar, ilk kaydı sessizce
    silerdi (Tanıma modeli seçimi de). Açılıştaki çözücü kullanılır: .env'de
    yazmayan ayarın yerinde yine varsayılanı görünür. Dosya yoksa ya da elle
    bozulmuşsa çalışan sistemin değerleri gösterilir.
    """
    if not ayarlar.env_yolu.is_file():
        return ayarlar
    try:
        return ayarlar_modulu.ayarlari_coz(
            ayarlar.kok_dizin, ayarlar_modulu.env_degerlerini_oku(ayarlar.env_yolu)
        )
    except (AyarHatasi, OSError, ValueError):
        return ayarlar


def _bekleyen_degisiklik_var(ayarlar, kayitli) -> bool:
    """Kaydedilmiş ama sistem yeniden başlatılmadığı için geçerli olmayan ayar var mı?"""
    return any(getattr(kayitli, alan.alan) != getattr(ayarlar, alan.alan) for alan in TUM_ALANLAR)


def _gosterilecek_deger(ayarlar, alan: AyarAlani) -> str:
    """Ayar nesnesindeki değerin form kutusuna yazılacak hali.

    Şifre asla yazılmaz: sayfa kaynağında, tarayıcı önbelleğinde ya da bir
    ekran görüntüsünde görünmemeli.
    """
    if alan.tur == "sifre":
        return ""
    if alan.anahtar == "MODEL_DOSYASI":
        return _model_secimi(ayarlar)
    deger = getattr(ayarlar, alan.alan)
    if alan.maskeli:
        return rtsp_maskele(str(deger))
    if isinstance(deger, tuple):
        # ('192.168.1.50', 'isg.dalsan.local') → "192.168.1.50, isg.dalsan.local"
        return ", ".join(deger)
    if isinstance(deger, float):
        # 0.35 → "0.35", 0.6 → "0.6"  (sayı kutusu noktalı yazım bekler)
        return f"{deger:g}"
    return str(deger)


def _model_secimi(ayarlar) -> str:
    """Kurulu modelin seçim kutusundaki değeri; hazır listede yoksa "özel".

    Tam yol ekrana (sayfa kaynağına da) yazılmaz: kullanıcı yazılımcı değil
    ve program klasörünün yeri ekranda gösterilmez.
    """
    for deger, _ad in MODEL_SECENEKLERI:
        if ayarlar.model_dosyasi == ayarlar.kok_dizin / deger:
            return deger
    return OZEL_MODEL_SECIMI


def _secenekler(ayarlar, alan: AyarAlani) -> tuple[tuple[str, str], ...]:
    """Seçim kutusunun seçenekleri; özel model kuruluysa o da listelenir."""
    if alan.anahtar == "MODEL_DOSYASI" and _model_secimi(ayarlar) == OZEL_MODEL_SECIMI:
        return ((OZEL_MODEL_SECIMI, f"{OZEL_MODEL_ADI} - değiştirilmez"), *alan.secenekler)
    return alan.secenekler


def _anlasilir_hata(mesaj: str) -> str:
    """Açılış hatasını form diline çevirir: '.env dosyasında X' → '“Etiket”'.

    Kullanıcı bir dosya değil, bir form dolduruyor; ekranda dosya adı ve
    büyük harfli anahtar görmesi kafa karıştırır.
    """
    metin = mesaj.replace(".env dosyasında ", "")
    # UZUN anahtar önce: bir anahtar başka bir anahtarın içinde geçebilir
    # (eskiden "ANONS" ile "ANONS_HTTP_ADRESI"). Kısa olan önce değiştirilirse
    # uzun anahtar ortasından bölünür ve ekranda "“Etiket”_HTTP_ADRESI" gibi
    # bir metin çıkardı.
    for alan in sorted(TUM_ALANLAR, key=lambda a: len(a.anahtar), reverse=True):
        metin = metin.replace(alan.anahtar, f"“{alan.etiket}”")
    return "Ayarlar kaydedilmedi. " + metin
