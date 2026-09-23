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
    tur: str = "sayi"  # sayi | ondalik | secim | metin | sifre
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
                    "erişim için önce docs/15-UZAKTAN-ERISIM.md belgesini okuyun — "
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
            "yonetici_sifresi_kurulu": bool(ayarlar.yonetici_sifresi),
            "sonuc_mesaji": SONUC_MESAJLARI.get(sonuc, ""),
        }
    )
    return sablonlar.TemplateResponse(istek, "komuta_ayarlar.html", baglam)


@router.post("/ayarlar/kaydet")
async def ayarlari_kaydet(istek: Request):
    """Formu doğrular, geçerse .env'e yazar. Geçmezse dosyaya DOKUNMAZ."""
    ayarlar = istek.app.state.ayarlar
    form = await istek.form()

    degisiklikler: dict[str, str] = {}
    for alan in TUM_ALANLAR:
        if alan.tur == "sifre":
            yeni = _sifre_degisikligi(form, alan.anahtar)
            if yeni is not None:
                degisiklikler[alan.anahtar] = yeni
        elif alan.anahtar in form:
            degisiklikler[alan.anahtar] = str(form[alan.anahtar]).strip()
    if not degisiklikler:
        raise DogrulamaHatasi("Kaydedilecek ayar bulunamadı. Sayfayı yenileyip tekrar deneyin.")

    # Dosyadaki mevcut değerlerin üzerine formdakiler yazılır; sistemin
    # açılışta kullandığı doğrulayıcı bu birleşik sözlüğü sınar.
    birlesik = ayarlar_modulu.env_degerlerini_oku(ayarlar.env_yolu)
    birlesik.update(degisiklikler)
    try:
        ayarlar_modulu.env_degisikliklerini_dogrula(degisiklikler)
        ayarlar_modulu.ayarlari_coz(ayarlar.kok_dizin, birlesik)
    except AyarHatasi as hata:
        raise DogrulamaHatasi(_anlasilir_hata(hata.kullanici_mesaji), hata.teknik_ayrinti) from hata

    ayarlar_modulu.env_dosyasina_yaz(ayarlar.env_yolu, degisiklikler)
    return RedirectResponse("/ayarlar?sonuc=kaydedildi", status_code=303)


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


def _gosterilecek_deger(ayarlar, alan: AyarAlani) -> str:
    """Çalışan sistemdeki değerin form kutusuna yazılacak hali.

    Şifre asla yazılmaz: sayfa kaynağında, tarayıcı önbelleğinde ya da bir
    ekran görüntüsünde görünmemeli.
    """
    if alan.tur == "sifre":
        return ""
    deger = getattr(ayarlar, alan.alan)
    if isinstance(deger, tuple):
        # ('192.168.1.50', 'isg.dalsan.local') → "192.168.1.50, isg.dalsan.local"
        return ", ".join(deger)
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
