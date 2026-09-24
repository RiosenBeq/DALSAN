"""Kılavuzlu arayüz: ekran açıklamaları ve ilk kurulum kontrol listesi.

Sistemi ilk açan kişi yazılım bilmiyor ve ekranda ne yapması gerektiğini
bilmiyor (CLAUDE.md §8). Bu modül iki şeyi üretir:

1. `EKRAN_ACIKLAMALARI` - her komuta ekranının üstünde görünen, kapatılabilir
   şeridin metni: "bu ekran ne işe yarar" + "ne yapmalısınız". İki cümleyi
   geçmez, teknik terim içermez.
2. `kurulum_durumu()` - sistemin GERÇEK veritabanı durumundan üretilen sıralı
   kontrol listesi. Hiçbir adım "tamam" görünmez; her adımın cevabı o anda
   sorgulanır. Sahte ilerleme çubuğu YOK.

Bu modül `komuta.py` içine konmadı: komuta.py altı ekranın veri hazırlığını
zaten taşıyor ve kılavuz metinleri oradan bağımsız değişir. Ters yönde bir
bağımlılık da yoktur (bu modül komuta.py'yi import etmez), böylece döngüsel
import riski yok.
"""

from __future__ import annotations

import json

from app import kaynaklar
from app.analiz.model_adi import gorunen_model_adi
from app.analiz.model_indir import FORKLIFT_TABANI, forklift_tabanlari
from app.olaylar.kanallar import kanal_sagligi_ozeti
from app.rules.motor import KALIBRASYON_GEREKTIREN
from app.rules.tipler import SINIF_FORKLIFT, SINIF_TIR
from app.web.ortak import calisan_model

# ---------------------------------------------------------------------------
# EKRAN AÇIKLAMALARI
# ---------------------------------------------------------------------------
#
# "ne" = bu ekran ne işe yarar, "yap" = kullanıcı ne yapmalı.
# Her ikisi de EN FAZLA iki cümle: uzun metin okunmaz, okunmayan metin
# kapatılır ve bir daha açılmaz.

EKRAN_ACIKLAMALARI: dict[str, dict[str, str]] = {
    "ana": {
        "ne": (
            "Fabrikanın o anki güvenlik tablosu: bugün kaç uyarı çıktı, hangi bölümde "
            "yoğunlaştı ve hangi kamera öne çıktı."
        ),
        "yap": (
            "Günde bir kez “İncelenmeyi bekleyen” sayısına bakın; sıfırdan "
            "büyükse üstüne tıklayıp olayları sırayla işaretleyin."
        ),
    },
    "rapor": {
        "ne": (
            "Seçtiğiniz tarih aralığındaki uyarıların özeti: hangi kural, hangi kamera, "
            "hangi bölüm ve hangi saat öne çıkmış."
        ),
        "yap": (
            "Tarihleri seçip “Yazdır” düğmesine basın; açılan pencerede yazıcı yerine "
            "“PDF olarak kaydet”i seçin (Excel için “Excel’e aktar”)."
        ),
    },
    "duvar": {
        "ne": (
            "Bütün kameraları tek ekranda canlı gösterir. Kırmızı çerçeveli kutu, o "
            "kamerada henüz incelenmemiş bir uyarı olduğu anlamına gelir."
        ),
        "yap": "Bir kutuya tıklayınca o kameranın kendi sayfası açılır.",
    },
    "inceleme": {
        "ne": (
            "Sistemin ürettiği uyarıları tek tek açıp doğru mu yanlış mı olduğunu "
            "işaretlediğiniz ekran."
        ),
        "yap": (
            "Kanıt fotoğrafına bakın ve “Doğru uyarı” ya da “Yanlış "
            "alarm” düğmesine basın; ok tuşlarıyla sonraki olaya geçebilirsiniz."
        ),
    },
    "saglik": {
        "ne": (
            "Her kameranın bağlı olup olmadığını, saniyede kaç kare verdiğini (okunan) "
            "ve analizin kaçını işleyebildiğini (işlenen), kalibre edilip "
            "edilmediğini gösterir."
        ),
        "yap": (
            "Sarı veya kırmızı rozetli bir satır varsa o kameranın adını tıklayıp "
            "adresini ve bağlantısını kontrol edin."
        ),
    },
    "uyari": {
        "ne": (
            "Hangi kuralın hangi kameralarda çalıştığını ve bir ihlalde hoparlörden ne "
            "duyulacağını tek tabloda gösterir."
        ),
        "yap": (
            "Yeni kurduğunuz bir kuralı birkaç gün gölge modda tutun; uyarıların "
            "isabetli olduğuna ikna olunca “Anonsu aç” düğmesine basın."
        ),
    },
    "anons": {
        "ne": (
            "Hoparlörden çalınacak Türkçe mesajları ve uyarının hangi kanaldan (bu "
            "bilgisayarın ses çıkışı ya da IP hoparlör) duyulacağını buradan yönetirsiniz."
        ),
        "yap": (
            "Her kanalı kendi “Dene” düğmesiyle sınayın; ses gelmiyorsa kanalın ses "
            "çıkışını ya da adresini kontrol edin."
        ),
    },
    "nesneler": {
        # Kapsam sınırını ("canlı kameraları etkilemez") bu şerit TEKRARLAMAZ:
        # onu sayfanın kendi KAPATILAMAZ bandı söyler. Aynı cümleyi iki kutuda
        # üst üste yazmak, ikisini de okunmaz yapardı.
        "ne": (
            "Sistemin tanımadığı kendi nesnenizi (pano, tüp, kalıp…) fotoğrafla tanıtırsınız; "
            "sonra bir fotoğraf yükleyip o nesnenin karede olup olmadığını sordurursunuz."
        ),
        "yap": (
            "Nesnenin en az 2, tercihen 4 fotoğrafını yükleyip ad verin; kartın üstünde "
            "çıkan “kolay/zor tanınır” rozetine bakıp altındaki öneriyi uygulayın."
        ),
    },
    "ayarlar": {
        # "Yeniden başlatmadan geçerli olmaz" cümlesi bu şeritte YOKTUR:
        # onu sayfanın kendi kapatılamaz bandı söyler (komuta_ayarlar.html).
        "ne": (
            "Anons yolu, tespit hassasiyeti ve kayıtların saklanma süresi gibi "
            "sistem geneli ayarların tek yeri."
        ),
        "yap": (
            "Bir eşiği değiştirdikten sonra sistemi yeniden başlatın ve kamera "
            "sayfasındaki canlı görüntüde kutulara bakarak sonucu görün."
        ),
    },
}


# ---------------------------------------------------------------------------
# İLK KURULUM KONTROL LİSTESİ
# ---------------------------------------------------------------------------

# Adımın ekrandaki rozeti: (metin, rozet rengi)
DURUM_ROZETLERI = {
    "tamam": ("tamam", "yesil"),
    "sira": ("sıradaki adım", "gri"),
    "calisiyor": ("hazırlanıyor", "sari"),
    "sorun": ("sorun var", "kirmizi"),
    "beklemede": ("sırası gelmedi", "gri"),
}


def _kural_arac_siniflari(baglanti):
    """Etkin her kural ve araç sınıfları: (satır, sınıflar).

    Güvenli mesafede araç listesi `object_classes`, bölge ve hız kuralında
    kuralın hedef sınıflarıdır.
    """
    # Kapalı kameranın kuralı hiç yüklenmez (supervizor yalnız açık kameraları
    # okur), kapalı bölgenin kuralını kural motoru değerlendirmez (R21): onların
    # sessizliği modelden değildir, kalibrasyon adımı gibi sayılmaz.
    for satir in baglanti.execute(
        "SELECT r.id, r.rule_type, r.target_classes, r.params, c.name AS kamera_adi, "
        "z.zone_type, z.name AS bolge_adi FROM rules r JOIN cameras c ON c.id = r.camera_id "
        "LEFT JOIN zones z ON z.id = r.zone_id "
        "WHERE r.enabled = 1 AND c.enabled = 1 AND (r.zone_id IS NULL OR z.enabled = 1) "
        "ORDER BY c.name, r.id"
    ):
        try:
            if satir["rule_type"] == "safe_distance":
                siniflar = json.loads(satir["params"] or "{}").get("object_classes", [])
            else:
                siniflar = json.loads(satir["target_classes"] or "[]")
        except (ValueError, TypeError, AttributeError):
            continue  # bozuk satırı kural motoru zaten yüklemez ve günlüğe yazar
        yield satir, siniflar


def forklifti_gormeyen_kurallar(baglanti) -> list[dict]:
    """Araç için kurulmuş ama "Forklift"i seçmemiş etkin kurallar.

    Hazır modelde forklift çoğu zaman "tır" görünür; yalnız "Tır/Araç" seçili
    bir kural bu yüzden forklifte de tepki veriyordu. Forklift ayrı sınıf olunca
    (egitim/forklift, docs/17 §12.3) aynı kural forklifti GÖRMEZ. Tır park alanının
    bölge kuralı ("tır konumlanma") bilerek yalnız tır içindir; aynı alandaki hız
    ya da güvenli mesafe kuralı ise forklifti de görmelidir, sayılır.
    """
    return [
        dict(satir)
        for satir, siniflar in _kural_arac_siniflari(baglanti)
        if SINIF_TIR in siniflar
        and SINIF_FORKLIFT not in siniflar
        and not (satir["zone_type"] == "truck_parking" and satir["rule_type"] == "zone_intrusion")
    ]


def forklifte_bagli_kurallar(baglanti) -> list[dict]:
    """Araç olarak yalnız "Forklift"i seçmiş etkin kurallar.

    Forkliftsiz modelde (hazır model ya da forklift modelinden geri dönülmüş
    kurulum) forklift sınıfı hiç üretilmez: bu kurallar forklift için HİÇ uyarı
    vermez (kural insanı da izliyorsa insan uyarısı sürer).
    """
    return [
        dict(satir)
        for satir, siniflar in _kural_arac_siniflari(baglanti)
        if SINIF_FORKLIFT in siniflar and SINIF_TIR not in siniflar
    ]


def forklift_karsiliklari(model_dosyasi: str, tabanlar: dict[str, str] | None = None) -> list[str]:
    """Çalışan modelin forklift karşılıkları: insanı ve aracı onunla aynı tanıyan,
    forklifti ayrıca tanıyan modeller (dosya adları), kayıt sırasıyla: yeni sürüm
    sona eklenir, en yenisi sondadır. `tabanlar` verilmezse yalnız kayıtlı yayın
    modelleri; verilirse Forklift sayfasından kurulan yerel modeller de
    (model_indir.forklift_tabanlari)."""
    tabanlar = FORKLIFT_TABANI if tabanlar is None else tabanlar
    return [ad for ad, taban in tabanlar.items() if taban == model_dosyasi]


def _en_yeni_forklift_modelleri(tabanlar: dict[str, str]) -> dict[str, str]:
    """Her hazır model için en yeni forklift karşılığı: {taban: forklift modeli}."""
    en_yeni: dict[str, str] = {}
    for ad, taban in tabanlar.items():
        en_yeni[taban] = ad  # sonraki kayıt öncekinin yerini alır
    return en_yeni


def _forklift_tabanlari(ayarlar) -> dict[str, str]:
    """Kayıtlı yayın modelleri ve bu kurulumda yerelde kurulanlar (en yenisi sonda)."""
    return forklift_tabanlari(ayarlar.kok_dizin / "models")


def _forklift_notu(supervizor, model_dosyasi: str, tabanlar: dict[str, str]) -> str:
    """Forklift ayrı sınıf mı (docs/17 §4.2, §12.3; docs/08 R1)?

    Hazır model (COCO) forklifti tanımaz; çoğu zaman "tır" (araç) görür ve
    "Tır/Araç" seçili kurallar onu araç olarak işler, hiç göremediği de olur.
    Forklift sınıflı bir model yüklenince (sınıf listesi dosyanın içinde) not
    değişir. Uyumsuz kurallar ayrı, kırmızı bir adımdır (`_forklift_kural_adimi`):
    kurulum bitince bu not gizlenir, o adım gizlenmez.

    Önerilen model, çalışan modelin forklift karşılığıdır (insanı ve aracı
    onunla AYNI tanır). Karşılığı yoksa başka tabanlı forklift modeli
    önerilirken insanı ve aracı hangi modelle tanıyacağı söylenir: İsabetli
    kullanan bir tesis, bilmeden daha zayıf bir insan tanımasına geçmesin.
    """
    if getattr(getattr(supervizor, "tespitci", None), "forklift_taniyor", False):
        return "Forklift ayrı sınıf olarak tanınıyor."
    not_ = (
        "Forklift ayrı bir sınıf değil: bu model forklifti çoğu zaman araç (tır) "
        "olarak görür ve “Tır/Araç” seçili kurallar onu araç olarak işler, ama hiç "
        "görmediği de olur."
    )
    karsiliklar = forklift_karsiliklari(model_dosyasi, tabanlar)
    if karsiliklar:
        return not_ + (
            f" Forklifti ayrıca tanıyan “{gorunen_model_adi(karsiliklar[-1])}” modeline "
            "Ayarlar'daki “Tanıma modeli” listesinden geçebilirsiniz; insanı ve aracı "
            "bu modelle aynı tanır."
        )
    if tabanlar:
        secenekler = _ve_ile(
            [
                f"“{gorunen_model_adi(ad)}” (insanı ve aracı “{gorunen_model_adi(taban)}” "
                "modeliyle tanır)"
                for taban, ad in sorted(_en_yeni_forklift_modelleri(tabanlar).items())
            ]
        )
        return not_ + (
            " Forklifti ayrıca tanıyan model Ayarlar'daki “Tanıma modeli” listesinde "
            f"var: {secenekler}. Geçmeden önce insanı hangi modelle tanıyacağına bakın."
        )
    return not_ + (
        " Forkliftin kendisini tanıması için eğitilmiş model gerekir; destek ekibinden isteyin."
    )


def _model_adimi(supervizor, ayarlar, baglanti=None) -> dict:
    """1. adım - tespit motoru.

    Bu adım SONRAKİ adımları engellemez (`engeller=False`): model inerken ya da
    yüklenemezken bile kamera eklemek, bölge çizmek ve kural kurmak anlamlıdır.
    Kullanıcıyı boş yere bekletmek, kurulumu tek adımda durdururdu.
    """
    calisan = calisan_model(supervizor, ayarlar)
    ad = gorunen_model_adi(calisan.name)
    ortak = {
        "no": 1,
        "baslik": "Tespit motoru hazır mı?",
        "bag": "/",
        "bag_yazi": "Sistem durumunu aç",
        "istege_bagli": False,
        "engeller": False,
    }
    durum = getattr(supervizor, "model_durumu", None) if supervizor is not None else None

    if durum == "hazir":
        # Seçili forklift modeli kullanılamadıysa "forklift modeline geçin" önerisi
        # anlamsızdır (zaten seçili): sebep ve yedek söylenir
        notu = getattr(supervizor, "model_uyarisi", "") or _forklift_notu(
            supervizor, calisan.name, _forklift_tabanlari(ayarlar)
        )
        aciklama = f"{ad} çalışıyor. {notu}"
        return {**ortak, "tamam": True, "hal": "", "aciklama": aciklama}
    if durum in ("indiriliyor", "yukleniyor"):
        return {
            **ortak,
            "tamam": False,
            "hal": "calisiyor",
            "aciklama": (
                f"{ad} hazırlanıyor. İlk açılışta bir kez indirilir (internet gerekir); "
                "birkaç dakika sürebilir. Bu sırada kamera eklemeye devam edebilirsiniz."
            ),
        }
    if durum == "hata":
        # Süpervizörün ürettiği metin zaten sade Türkçedir ve ne yapılacağını
        # söyler (adres, dosya yolu içermez - tests/test_model_hatasi_ekranda.py).
        hata = getattr(supervizor, "tespit_hatasi", "") or f"{ad} başlatılamadı."
        return {**ortak, "tamam": False, "hal": "sorun", "aciklama": hata}
    return {
        **ortak,
        "tamam": False,
        "hal": "calisiyor",
        "aciklama": (f"Analiz henüz başlatılmadı. {kaynaklar.baslatma_tarifi(yeniden=False)}."),
    }


def kalibrasyon_bekleyen_kurallar(baglanti) -> list[dict]:
    """Etkin olduğu halde kalibrasyon olmadığı için ÇALIŞMAYAN kurallar.

    Güvenli mesafe ve hız kuralları metre ister (rules/motor.py
    KALIBRASYON_GEREKTIREN); kalibrasyonsuz kamerada sessizce pasif kalırlar.
    Bu yalnız kural sayfasındaki rozette kalmamalı (docs/17 §6.4): kurulum
    listesi ve /saglik da söyler. Kapalı bölgenin kuralı kalibrasyonla da
    çalışmaz (R21), sayılmaz.
    """
    yer = ",".join("?" * len(KALIBRASYON_GEREKTIREN))
    return [
        dict(satir)
        for satir in baglanti.execute(
            "SELECT r.id, r.rule_type, c.id AS kamera_id, c.name AS kamera_adi "
            "FROM rules r JOIN cameras c ON c.id = r.camera_id "
            "LEFT JOIN camera_calibrations k ON k.camera_id = r.camera_id "
            "LEFT JOIN zones z ON z.id = r.zone_id "
            f"WHERE r.enabled = 1 AND c.enabled = 1 AND r.rule_type IN ({yer}) "
            "AND (r.zone_id IS NULL OR z.enabled = 1) "
            "AND k.camera_id IS NULL ORDER BY c.name, r.id",
            tuple(sorted(KALIBRASYON_GEREKTIREN)),
        )
    ]


def _ve_ile(ogeler: list[str]) -> str:
    """Türkçe sayım: "A", "A ve B", "A, B ve C"."""
    return " ve ".join(filter(None, [", ".join(ogeler[:-1]), ogeler[-1]]))


def _kalibrasyon_adimi(bekleyenler: list[dict]) -> dict:
    """Kalibrasyon bekleyen kritik kural varsa kırmızı madde (docs/17 §6.4).

    Yalnız böyle bir kural varken listede görünür. Zorunlu sayılır: güvenli
    mesafe kuralı kurulmuş ama çalışmıyorsa sistem "hazır" değildir.
    """
    kameralar = sorted({b["kamera_adi"] for b in bekleyenler})
    adlar = {"safe_distance": "güvenli mesafe", "vehicle_speed": "hız"}
    turler = _ve_ile(sorted({adlar.get(b["rule_type"], b["rule_type"]) for b in bekleyenler}))
    tek_kamera = len(kameralar) == 1
    return {
        "no": 8,
        "baslik": "Mesafe ve hız kuralları çalışıyor mu?",
        "tamam": False,
        "hal": "sorun",
        "aciklama": (
            f"Kalibrasyon bekleniyor: {_ve_ile(kameralar)} "
            f"{'kamerasındaki' if tek_kamera else 'kameralarındaki'} {turler} "
            f"{'kuralı' if len(bekleyenler) == 1 else 'kuralları'}, "
            f"{'kamera' if tek_kamera else 'kameralar'} kalibre edilmeden ÇALIŞMAZ ve "
            "uyarı üretmez. Kamera sayfasında “Gelişmiş araçlar”a basıp “Mesafe "
            "kalibrasyonu” bölümünde zeminde ölçülü dört nokta işaretleyin."
        ),
        "bag": f"/kameralar/{bekleyenler[0]['kamera_id']}",
        "bag_yazi": "Kamerayı aç",
        "istege_bagli": False,
        "engeller": False,
    }


def _forklift_kural_adimi(
    kurallar: list[dict], forklift_taniyor: bool, forklift_modeli_var: bool
) -> dict:
    """Çalışan modelle uyuşmayan araç kuralı varsa kırmızı madde (docs/17 §12.3-5).

    Forklift sınıflı modelde yalnız "Tır/Araç" seçili kural forklifti GÖRMEZ;
    forkliftsiz modelde yalnız "Forklift" seçili kural HİÇ uyarı vermez. İkisi
    de sessizce susan bir güvenlik kuralıdır: kalibrasyon adımı gibi zorunlu
    sayılır, kurulum bitmiş olsa da listeyi yeniden açar ("Sistem hazır."
    rozeti gizleyemez).
    """
    turler = {
        "zone_intrusion": "bölge kuralı",
        "safe_distance": "güvenli mesafe kuralı",
        "vehicle_speed": "hız kuralı",
    }
    # Aynı kamera, bölge ve türdeki kurallar tek tanımda sayılır; ilk üç tanım
    # yazılır, kalanlar sayıyla: "A, B, C ve 2 kural daha".
    sayilar: dict[str, int] = {}
    for k in kurallar:
        tanim = (
            f"{k['kamera_adi']} kamerasındaki "
            + (f"“{k['bolge_adi']}” " if k.get("bolge_adi") else "")
            + turler.get(k["rule_type"], "kural")
        )
        sayilar[tanim] = sayilar.get(tanim, 0) + 1
    ilk_uc = list(sayilar.items())[:3]
    ogeler = [tanim if sayi == 1 else f"{tanim} ({sayi} kural)" for tanim, sayi in ilk_uc]
    kalan = len(kurallar) - sum(sayi for _, sayi in ilk_uc)
    liste = _ve_ile(ogeler + ([f"{kalan} kural daha"] if kalan else []))
    if forklift_taniyor:
        aciklama = (
            "Forklift ayrı sınıf olarak tanınıyor, ama şu kurallar araç olarak yalnız "
            f"“Tır/Araç”ı izliyor ve forklifti GÖRMEZ: {liste}. Kuralı açıp “Forklift”i "
            "de işaretleyin (tır park alanının bölge kuralı bilerek yalnız tır içindir)."
        )
    else:
        aciklama = (
            "Çalışan tanıma modeli forklifti ayrı sınıf olarak tanımıyor, ama şu kurallar "
            "araç olarak yalnız “Forklift”i izliyor ve forklift için HİÇ uyarı vermez "
            f"(kural insanı da izliyorsa insan uyarısı sürer): {liste}. Kuralı açıp "
            "“Tır/Araç”ı da işaretleyin"
            + (
                " ya da Ayarlar'daki “Tanıma modeli” listesinden forklifti tanıyan modeli seçin."
                if forklift_modeli_var
                else "."
            )
        )
    return {
        "no": 10,
        "baslik": "Araç kuralları tanıma modeline uyuyor mu?",
        "tamam": False,
        "hal": "sorun",
        "aciklama": aciklama,
        "bag": "/kurallar",
        "bag_yazi": "Kuralları aç",
        "istege_bagli": False,
        "engeller": False,
    }


def _anons_adimi(kanal_sayisi: int, tek_bluetooth: bool, bluetooth_disi: int) -> dict:
    """6. adım - sesli uyarı kanalı.

    Zorunludur (docs/17 K21, Ç39): gölgede olmayan her uyarı en az bir sesli ya
    da uzak kanala ulaşmalı; ekran bu garantiye sayılmaz. Kanal yoksa ya da ses
    yalnız Bluetooth hoparlöre dayanıyorsa (GÖREV §7, S32) kırmızıdır. Sonraki
    adımları engellemez: kanal, kamera kurulumundan bağımsız eklenebilir.
    """
    ortak = {
        "no": 6,
        "baslik": "Sesli anons kuruldu mu?",
        "bag": "/komuta/anons",
        "istege_bagli": False,
        "engeller": False,
    }
    if not kanal_sayisi:
        return {
            **ortak,
            "tamam": False,
            "hal": "sorun",
            "bag_yazi": "Kanal ekle",
            "aciklama": (
                "Sesli kanal yok: uyarılar ekranda ve olay listesinde görünür, ama "
                "hoparlörden ses çıkmaz ve her uyarı “hiçbir hoparlöre ulaşmadı” diye "
                "kaydedilir. Bu bilgisayarın ses çıkışını (kablolu amfi ya da Bluetooth "
                "hoparlör) ya da bir IP hoparlörü kanal olarak ekleyin."
            ),
        }
    if tek_bluetooth:
        neden = (
            "Bluetooth dışındaki sesli kanallar şu an bağlı değil; uyarı yalnız Bluetooth "
            "hoparlörden duyuluyor. Anons sayfasında kopan kanala bakın."
            if bluetooth_disi
            else (
                "Sesli uyarı yalnız Bluetooth hoparlöre dayanıyor: hoparlör kapanır ya da "
                "menzilden çıkarsa uyarı hiçbir yerde duyulmaz. Bluetooth tek uyarı kanalı "
                "olamaz; kablolu bir ses çıkışı ya da bir IP hoparlör ekleyin."
            )
        )
        return {
            **ortak,
            "tamam": False,
            "hal": "sorun",
            "bag_yazi": "Kanalları aç",
            "aciklama": neden,
        }
    return {
        **ortak,
        "tamam": True,
        "hal": "",
        "bag_yazi": "Kanal ekle",
        "aciklama": f"{kanal_sayisi} açık sesli kanal tanımlı.",
    }


def _mahremiyet_adimi(baglanti) -> dict:
    """9. adım - görüş alanında mahremiyet alanı yok (docs/17 §10.1, Kurul 2022/797).

    Yazılım bunu göremez: her açık kameranın görüntüsüne bakılıp kamera
    sayfasında onaylanır. Zorunludur ama sonraki adımları engellemez; kırmızı
    değildir (bir arıza değil, yapılmamış bir kontroldür).
    """
    kameralar = baglanti.execute(
        "SELECT id, privacy_checked_at FROM cameras WHERE enabled = 1 ORDER BY id"
    ).fetchall()
    eksik = [k for k in kameralar if not k["privacy_checked_at"]]
    ortak = {
        "no": 9,
        "baslik": "Kamera görüş alanlarında mahremiyet alanı yok mu?",
        "hal": "",
        "istege_bagli": False,
        "engeller": False,
    }
    if kameralar and not eksik:
        return {
            **ortak,
            "tamam": True,
            "aciklama": f"{len(kameralar)} kameranın görüş alanı kontrol edildi.",
            "bag": "/kameralar",
            "bag_yazi": "Kameraları aç",
        }
    return {
        **ortak,
        "tamam": False,
        "aciklama": (
            f"{len(kameralar) - len(eksik)} / {len(kameralar)} kamera kontrol edildi. "
            "Görüş alanında tuvalet, soyunma odası, duş, mescit, dinlenme ya da emzirme "
            "odası olamaz (KVKK). Kamera sayfasındaki “Mahremiyet kontrolü” bölümünde "
            "görüntüye bakıp onaylayın."
        ),
        "bag": f"/kameralar/{eksik[0]['id']}#mahremiyet" if eksik else "/kameralar",
        "bag_yazi": "Kamerayı aç" if eksik else "Kameraları aç",
    }


def _ham_adimlar(baglanti, supervizor, ayarlar) -> list[dict]:
    """Altı adımın ham cevabı - hepsi veritabanından ve sistem durumundan."""
    kamera_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM cameras").fetchone()["n"]
    goruntu_veren = baglanti.execute(
        "SELECT COUNT(*) AS n FROM cameras WHERE enabled = 1 AND last_frame_at IS NOT NULL"
    ).fetchone()["n"]
    bolge_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM zones").fetchone()["n"]
    kural_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM rules WHERE enabled = 1").fetchone()[
        "n"
    ]
    # Sesli kanal: tanım veritabanındadır (speaker_zones, docs/17 K22). Kanal
    # yoksa ya da ses yalnız Bluetooth'a dayanıyorsa adım kırmızıdır (Ç38, Ç39)
    kanal = kanal_sagligi_ozeti(baglanti, canli=supervizor is not None)
    hoparlor_sayisi = len(kanal["kanallar"])
    tek_bluetooth = "tek_kanal_bluetooth" in kanal["sorunlar"]

    # Bağlantılar HER ZAMAN var olan bir sayfayı göstermeli: tek kamera varsa
    # doğrudan o kameranın sayfası, birden çoksa liste. "Bölge çiz" ve "Hazır
    # kural" düğmeleri kamera sayfasında yaşıyor.
    ilk_kamera = baglanti.execute("SELECT id FROM cameras ORDER BY id LIMIT 1").fetchone()
    bolgeli_kamera = baglanti.execute("SELECT camera_id FROM zones ORDER BY id LIMIT 1").fetchone()
    kamera_yolu = f"/kameralar/{ilk_kamera['id']}" if ilk_kamera else "/kameralar"
    kural_yolu = f"/kameralar/{bolgeli_kamera['camera_id']}" if bolgeli_kamera else "/kurallar/yeni"

    adimlar = [
        _model_adimi(supervizor, ayarlar, baglanti),
        {
            "no": 2,
            "baslik": "En az bir kamera eklendi mi?",
            "tamam": kamera_sayisi > 0,
            "hal": "",
            "aciklama": (
                f"{kamera_sayisi} kamera tanımlı."
                if kamera_sayisi
                else (
                    "Henüz kamera eklenmedi. Fabrika kamerası için RTSP adresi gerekir. "
                    "Kamera hazır değilse Kameralar sayfasındaki “Video ile Test” ile "
                    "elinizdeki bir video dosyasıyla şimdiden deneyebilirsiniz."
                )
            ),
            # Bağlantı "Kamera ekle" KALIR: RTSP adresi elinde olan kullanıcı
            # asıl adımını burada bulmalı. Video yükleme, aynı sayfadan tek
            # tıkla ulaşılan bir alternatiftir ve yukarıdaki açıklamada geçer.
            "bag": "/kameralar/yeni",
            "bag_yazi": "Kamera ekle",
            "istege_bagli": False,
            "engeller": True,
        },
        {
            "no": 3,
            "baslik": "Kamera görüntü veriyor mu?",
            "tamam": goruntu_veren > 0,
            "hal": "",
            "aciklama": (
                f"{goruntu_veren} kameradan görüntü geliyor."
                if goruntu_veren
                else (
                    "Hiçbir kameradan henüz kare gelmedi. Kameranın sayfasını açıp "
                    "görüntünün gelip gelmediğine bakın; gelmiyorsa sayfadaki hata "
                    "cümlesi nedeni söyler."
                )
            ),
            "bag": kamera_yolu if kamera_sayisi == 1 else "/komuta/saglik",
            "bag_yazi": "Kamerayı aç" if kamera_sayisi == 1 else "Kamera sağlığını aç",
            "istege_bagli": False,
            "engeller": True,
        },
        {
            "no": 4,
            "baslik": "En az bir bölge çizildi mi?",
            "tamam": bolge_sayisi > 0,
            "hal": "",
            "aciklama": (
                f"{bolge_sayisi} bölge çizildi."
                if bolge_sayisi
                else (
                    "Kurallar bölge üstünde çalışır: yaya yolu, yükleme alanı, yasak "
                    "bölge gibi alanları kameranın görüntüsü üzerine çizersiniz."
                )
            ),
            "bag": f"{kamera_yolu}#bolge-formu",
            "bag_yazi": "Bölge çiz",
            "istege_bagli": False,
            "engeller": True,
        },
        {
            "no": 5,
            "baslik": "En az bir kural kuruldu mu?",
            "tamam": kural_sayisi > 0,
            "hal": "",
            "aciklama": (
                f"{kural_sayisi} kural açık."
                if kural_sayisi
                else (
                    "Çizilen bölge tek başına uyarı üretmez. Kamera sayfasındaki "
                    "“Hazır kurallar” bölümü, bölge tipine uyan kuralı tek "
                    "düğmeyle kurar."
                )
            ),
            "bag": kural_yolu,
            "bag_yazi": "Hazır kural ekle",
            "istege_bagli": False,
            "engeller": True,
        },
        {
            "no": 7,
            "baslik": "Giriş şifresi kondu mu?",
            "tamam": bool(ayarlar.yonetici_sifresi),
            "hal": "",
            "aciklama": (
                "Şifre tanımlı - sisteme girmek için şifre soruluyor."
                if ayarlar.yonetici_sifresi
                else (
                    "Şifre yok: sistemi açabilen herkes kamera silebilir, kural "
                    "değiştirebilir ve hoparlörden anons yaptırabilir. Sistem yalnızca "
                    "BU bilgisayardan açılıyorsa sorun değil. Fabrika sunucusuna "
                    "taşırken ya da ağa açarken mutlaka bir şifre koyun."
                )
            ),
            "bag": "/ayarlar",
            "bag_yazi": "Şifre koy",
            # Engellemez: şifresiz sistem çalışır. Ama isteğe bağlı olduğu için
            # listeyi sürekli "eksik" göstermez - kullanıcı şifresiz çalışan bir
            # sistemle baş başa kalmamalı.
            "istege_bagli": True,
            "engeller": False,
        },
        _anons_adimi(hoparlor_sayisi, tek_bluetooth, kanal["bluetooth_disi"]),
        _mahremiyet_adimi(baglanti),
    ]
    bekleyenler = kalibrasyon_bekleyen_kurallar(baglanti)
    if bekleyenler:
        adimlar.append(_kalibrasyon_adimi(bekleyenler))
    # Sınıf listesi ancak model yüklenince bilinir: model hazır değilken
    # (iniyor, hata) kuralların modele uyup uymadığı söylenemez.
    if getattr(supervizor, "model_durumu", None) == "hazir":
        forklift_taniyor = bool(
            getattr(getattr(supervizor, "tespitci", None), "forklift_taniyor", False)
        )
        uyumsuz = (
            forklifti_gormeyen_kurallar(baglanti)
            if forklift_taniyor
            else forklifte_bagli_kurallar(baglanti)
        )
        if uyumsuz:
            adimlar.append(
                _forklift_kural_adimi(uyumsuz, forklift_taniyor, bool(_forklift_tabanlari(ayarlar)))
            )
    # Numaraya göre sırala: şifre adımı yukarıda anonsun ÖNÜNE yazıldı ama
    # ekranda kurulum sırasına göre (…6, 7) görünmeli.
    return sorted(adimlar, key=lambda a: a["no"])


def kurulum_durumu(baglanti, supervizor, ayarlar) -> dict:
    """Sıralı kurulum kontrol listesi + sistemin hazır olup olmadığı.

    "Tamamlanan adım sonraki adımı açar": ilk tamamlanmamış ENGELLEYİCİ adımdan
    sonraki adımlar soluk görünür ve düğmeleri çizilmez. Kullanıcı her an tek
    bir sonraki hamle görür; altı düğmeden hangisine basacağını seçmek zorunda
    kalmaz. Zaten tamamlanmış bir adım, sırası geçmiş olsa da yeşil kalır -
    doğru olanı göstermek, listeyi düzgün göstermekten önemlidir.
    """
    ham = _ham_adimlar(baglanti, supervizor, ayarlar)
    sirasi_geldi = True
    adimlar = []
    for h in ham:
        if h["tamam"]:
            durum = "tamam"
        elif not sirasi_geldi:
            durum = "beklemede"
        else:
            durum = h["hal"] or "sira"
        if not h["tamam"] and h["engeller"]:
            sirasi_geldi = False
        rozet, rozet_rengi = DURUM_ROZETLERI[durum]
        adimlar.append(
            {
                "no": h["no"],
                "baslik": h["baslik"],
                "aciklama": h["aciklama"],
                "durum": durum,
                "rozet": rozet,
                "rozet_rengi": rozet_rengi,
                "bag": h["bag"],
                "bag_yazi": h["bag_yazi"],
                "istege_bagli": h["istege_bagli"],
            }
        )

    zorunlu = [a for a, h in zip(adimlar, ham, strict=True) if not h["istege_bagli"]]
    return {
        "adimlar": adimlar,
        "toplam": len(zorunlu),
        "tamamlanan": sum(1 for a in zorunlu if a["durum"] == "tamam"),
        # "Hazır" YALNIZCA zorunlu adımlara bakar. Sesli kanal zorunludur
        # (docs/17 K21): kanalsız uyarı ekranda kalır, hoparlörden duyulmaz.
        # İsteğe bağlı bir adım (şifre) yüzünden ekranda sürekli kurulum
        # listesi durmasın.
        "hazir": all(a["durum"] == "tamam" for a in zorunlu),
    }
