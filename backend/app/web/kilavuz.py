"""Kılavuzlu arayüz: ekran açıklamaları ve ilk kurulum kontrol listesi.

Sistemi ilk açan kişi yazılım bilmiyor ve ekranda ne yapması gerektiğini
bilmiyor (CLAUDE.md §8). Bu modül iki şeyi üretir:

1. `EKRAN_ACIKLAMALARI` — her komuta ekranının üstünde görünen, kapatılabilir
   şeridin metni: "bu ekran ne işe yarar" + "ne yapmalısınız". İki cümleyi
   geçmez, teknik terim içermez.
2. `kurulum_durumu()` — sistemin GERÇEK veritabanı durumundan üretilen sıralı
   kontrol listesi. Hiçbir adım "tamam" görünmez; her adımın cevabı o anda
   sorgulanır. Sahte ilerleme çubuğu YOK.

Bu modül `komuta.py` içine konmadı: komuta.py altı ekranın veri hazırlığını
zaten taşıyor ve kılavuz metinleri oradan bağımsız değişir. Ters yönde bir
bağımlılık da yoktur (bu modül komuta.py'yi import etmez), böylece döngüsel
import riski yok.
"""

from __future__ import annotations

from app.analiz.model_adi import gorunen_model_adi
from app.rules.motor import KALIBRASYON_GEREKTIREN

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


def _model_adimi(supervizor, ayarlar) -> dict:
    """1. adım — tespit motoru.

    Bu adım SONRAKİ adımları engellemez (`engeller=False`): model inerken ya da
    yüklenemezken bile kamera eklemek, bölge çizmek ve kural kurmak anlamlıdır.
    Kullanıcıyı boş yere bekletmek, kurulumu tek adımda durdururdu.
    """
    ad = gorunen_model_adi(ayarlar.model_dosyasi.name)
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
        return {**ortak, "tamam": True, "hal": "", "aciklama": f"{ad} çalışıyor."}
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
        # söyler (adres, dosya yolu içermez — tests/test_model_hatasi_ekranda.py).
        hata = getattr(supervizor, "tespit_hatasi", "") or f"{ad} başlatılamadı."
        return {**ortak, "tamam": False, "hal": "sorun", "aciklama": hata}
    return {
        **ortak,
        "tamam": False,
        "hal": "calisiyor",
        "aciklama": (
            "Analiz henüz başlatılmadı. Kontrol Paneli penceresinde "
            "“Sistemi Başlat” düğmesine basın."
        ),
    }


def kalibrasyon_bekleyen_kurallar(baglanti) -> list[dict]:
    """Etkin olduğu halde kalibrasyon olmadığı için ÇALIŞMAYAN kurallar.

    Güvenli mesafe ve hız kuralları metre ister (rules/motor.py
    KALIBRASYON_GEREKTIREN); kalibrasyonsuz kamerada sessizce pasif kalırlar.
    Bu yalnız kural sayfasındaki rozette kalmamalı (docs/17 §6.4): kurulum
    listesi ve /saglik da söyler.
    """
    yer = ",".join("?" * len(KALIBRASYON_GEREKTIREN))
    return [
        dict(satir)
        for satir in baglanti.execute(
            "SELECT r.id, r.rule_type, c.id AS kamera_id, c.name AS kamera_adi "
            "FROM rules r JOIN cameras c ON c.id = r.camera_id "
            "LEFT JOIN camera_calibrations k ON k.camera_id = r.camera_id "
            f"WHERE r.enabled = 1 AND c.enabled = 1 AND r.rule_type IN ({yer}) "
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


def _ham_adimlar(baglanti, supervizor, ayarlar) -> list[dict]:
    """Altı adımın ham cevabı — hepsi veritabanından ve sistem durumundan."""
    kamera_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM cameras").fetchone()["n"]
    goruntu_veren = baglanti.execute(
        "SELECT COUNT(*) AS n FROM cameras WHERE enabled = 1 AND last_frame_at IS NOT NULL"
    ).fetchone()["n"]
    bolge_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM zones").fetchone()["n"]
    kural_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM rules WHERE enabled = 1").fetchone()[
        "n"
    ]
    hoparlor_sayisi = baglanti.execute(
        "SELECT COUNT(*) AS n FROM speaker_zones WHERE enabled = 1"
    ).fetchone()["n"]

    # Bağlantılar HER ZAMAN var olan bir sayfayı göstermeli: tek kamera varsa
    # doğrudan o kameranın sayfası, birden çoksa liste. "Bölge çiz" ve "Hazır
    # kural" düğmeleri kamera sayfasında yaşıyor.
    ilk_kamera = baglanti.execute("SELECT id FROM cameras ORDER BY id LIMIT 1").fetchone()
    bolgeli_kamera = baglanti.execute("SELECT camera_id FROM zones ORDER BY id LIMIT 1").fetchone()
    kamera_yolu = f"/kameralar/{ilk_kamera['id']}" if ilk_kamera else "/kameralar"
    kural_yolu = f"/kameralar/{bolgeli_kamera['camera_id']}" if bolgeli_kamera else "/kurallar/yeni"

    adimlar = [
        _model_adimi(supervizor, ayarlar),
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
                    "Kamera hazır değilse “Video Yükle” deyip elinizdeki bir video "
                    "dosyasıyla şimdiden deneyebilirsiniz."
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
                "Şifre tanımlı — sisteme girmek için şifre soruluyor."
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
            # listeyi sürekli "eksik" göstermez — kullanıcı anonssuz da,
            # şifresiz de çalışan bir sistemle baş başa kalmamalı.
            "istege_bagli": True,
            "engeller": False,
        },
        {
            "no": 6,
            "baslik": "Sesli anons kuruldu mu?",
            # Kanal tanımı veritabanındadır (speaker_zones, docs/17 K22)
            "tamam": hoparlor_sayisi > 0,
            "hal": "",
            "aciklama": (
                f"{hoparlor_sayisi} açık sesli kanal tanımlı."
                if hoparlor_sayisi
                else (
                    "Sesli kanal yok: uyarılar ekranda ve olay listesinde görünür, ama "
                    "hoparlörden ses çıkmaz. Bu bilgisayarın ses çıkışını ya da bir IP "
                    "hoparlörü kanal olarak ekleyin; sistemi anonssuz da kullanabilirsiniz."
                )
            ),
            "bag": "/komuta/anons",
            "bag_yazi": "Kanal ekle",
            "istege_bagli": True,
            "engeller": False,
        },
    ]
    bekleyenler = kalibrasyon_bekleyen_kurallar(baglanti)
    if bekleyenler:
        adimlar.append(_kalibrasyon_adimi(bekleyenler))
    # Numaraya göre sırala: şifre adımı yukarıda anonsun ÖNÜNE yazıldı ama
    # ekranda kurulum sırasına göre (…6, 7) görünmeli.
    return sorted(adimlar, key=lambda a: a["no"])


def kurulum_durumu(baglanti, supervizor, ayarlar) -> dict:
    """Sıralı kurulum kontrol listesi + sistemin hazır olup olmadığı.

    "Tamamlanan adım sonraki adımı açar": ilk tamamlanmamış ENGELLEYİCİ adımdan
    sonraki adımlar soluk görünür ve düğmeleri çizilmez. Kullanıcı her an tek
    bir sonraki hamle görür; altı düğmeden hangisine basacağını seçmek zorunda
    kalmaz. Zaten tamamlanmış bir adım, sırası geçmiş olsa da yeşil kalır —
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
        # "Hazır" YALNIZCA zorunlu adımlara bakar: anons kurulmadan da sistem
        # uyarı üretir. İsteğe bağlı bir adım yüzünden ekranda sürekli kurulum
        # listesi durmasın.
        "hazir": all(a["durum"] == "tamam" for a in zorunlu),
    }
