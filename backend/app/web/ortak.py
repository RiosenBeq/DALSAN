"""Web katmanının ortak yardımcıları: istek başına veritabanı bağlantısı,
RTSP maskeleme, güvenli CSV, Türkçe etiket tabloları ve bölge tiplerinin
hazır kuralları."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Request

from app import veritabani, zaman
from app.hatalar import DogrulamaHatasi
from app.loglama import ADRES_KIMLIGI, ADRES_MASKESI, adres_maskele
from app.rules.olay_kodu import KAPANIS_SEBEPLERI, OLAY_KODLARI, ONEM_ADLARI
from app.rules.parametreler import params_dogrula

# Kullanıcıya görünen Türkçe adlar (kod içi değerler İngilizce kalır)
BOLGE_TIPLERI = {
    "pedestrian_path": "Yaya yolu",
    "loading_area": "Yükleme alanı",
    "truck_parking": "Tır park alanı",
    "vehicle_area": "Araç sahası",
    "ppe_required": "KKD zorunlu alan",
    "restricted": "Yasak bölge",
    "crossing": "Yaya-araç geçidi",
    "ppe_exempt": "KKD muaf alan",
}

KURAL_TIPLERI = {
    "zone_intrusion": "Bölge ihlali",
    "safe_distance": "Güvenli mesafe",
    "ppe_violation": "KKD (baret/yelek)",
    "vehicle_speed": "Araç hız sınırı",
}

# Bölgesi ZORUNLU olan kural tipleri. Güvenli mesafe ve araç hızı bölgesiz de
# çalışır (o zaman tüm kareyi kapsar); bölge ihlali ve KKD bölgesiz anlamsızdır.
BOLGE_ZORUNLU_KURALLAR = frozenset({"zone_intrusion", "ppe_violation"})

OLAY_DURUMLARI = {"new": "Yeni", "reviewed": "İncelendi", "false_alarm": "Yanlış alarm"}

# Cümle içinde küçük harfle geçen durum adı ("… · incelendi").
# Jinja'nın |lower süzgeci BURADA KULLANILAMAZ: Python "İncelendi".lower()
# çağrısında "i̇ncelendi" üretir (i + ayrı nokta), çünkü Türkçe büyük İ'nin
# küçüğü noktasız bir i değildir. Ekranda gözle görülür bir bozukluk olur.
OLAY_DURUMLARI_KUCUK = {"new": "yeni", "reviewed": "incelendi", "false_alarm": "yanlış alarm"}

SINIFLAR = {"person": "İnsan", "forklift": "Forklift", "truck": "Tır/Araç"}

# KKD parçalarının Türkçe adları. Olay özetinde ve inceleme ekranında AYNI
# kelime görünsün diye tek yerde durur.
KKD_ADLARI = {"helmet": "baret", "vest": "yelek"}


# ------------------------------------------------------------------ öğe dili


@dataclass(frozen=True)
class Oge:
    """Sistemin tanıdığı ya da denetlediği bir öğe: ekrandaki simgesi ve adı.

    İlk istekteki öğeler (insan, forklift, tır, yaya yolu, baret, yelek) her
    ekranda AYNI simge ve AYNI renkle görünsün diye tek yerde durur. Bir
    olayın hangi öğeye ait olduğu bakınca anlaşılmalı: "forklift insana
    yaklaştı" ile "baret yok" aynı kırmızı satır olarak görünmemeli.

    `anahtar` CSS sınıfıdır (`.oge-<anahtar>`, stil.css → ÖĞE DİLİ; renk
    ailesi canlı görüntüdeki kutu renkleriyle aynıdır). `simge` sprite'taki
    addır (vendor/simgeler.svg, "s-" öneksiz).
    """

    anahtar: str
    ad: str
    simge: str


OGELER: dict[str, Oge] = {
    "insan": Oge("insan", "İnsan", "insan"),
    "forklift": Oge("forklift", "Forklift", "forklift"),
    "tir": Oge("tir", "Tır / araç", "tir"),
    "baret": Oge("baret", "Baret", "kkd"),
    "yelek": Oge("yelek", "Reflektörlü yelek", "yelek"),
    "kkd": Oge("kkd", "Baret ve yelek", "kkd"),
    "yaya-yolu": Oge("yaya-yolu", "Yaya yolu", "yaya-yolu"),
    "alan": Oge("alan", "Girilmemesi gereken alan", "yasak"),
    "park": Oge("park", "Tır park yeri", "park"),
    "hiz": Oge("hiz", "Araç hızı", "hiz"),
    "kamera": Oge("kamera", "Kamera", "kamera-yok"),
    "sistem": Oge("sistem", "Sistem", "saglik"),
}

# Öğenin İHLAL olarak adı: "Forklift" bir öğedir, "araç–yaya yakınlığı" onun
# ürettiği ihlaldir. Komuta ekranındaki öğe dağılımı bu adları kullanır. Olay
# koduyla aynı şeyi anlatan ad sözlükten gelir (rules/olay_kodu.py): aynı
# ekranda akış "Araç–yaya yakınlığı", öğe kartı başka bir ad yazmasın.
OGE_IHLAL_ADLARI = {
    "forklift": OLAY_KODLARI["VEHICLE_PERSON_PROXIMITY"].ad,
    "yaya-yolu": OLAY_KODLARI["PERSON_OFF_WALKWAY"].ad,
    "baret": OLAY_KODLARI["PPE_NO_HELMET"].ad,
    "yelek": OLAY_KODLARI["PPE_NO_VEST"].ad,
    "kkd": "Baret ve yelek yok",
    "alan": OLAY_KODLARI["RESTRICTED_ENTRY"].ad,
    "park": OLAY_KODLARI["VEHICLE_OUT_OF_POSITION"].ad,
    "tir": "Tır bölgede",
    "hiz": OLAY_KODLARI["VEHICLE_OVERSPEED"].ad,
}

# Tespit sınıfı → öğe (renk anahtarı ve sayım tabloları)
SINIF_OGELERI = {"person": "insan", "forklift": "forklift", "truck": "tir"}

# Anons mesajı anahtarı → öğe (anons sayfasındaki mesaj satırları)
ANONS_OGELERI = {
    "safe_distance": "forklift",
    "pedestrian_path": "yaya-yolu",
    "vehicle_position": "park",
    "helmet": "baret",
    "vest": "yelek",
    # Şema 007 (docs/17 §8.2) — olay_ogesi() ile aynı mantık: bölgedeki araç
    # "tır", girilmemesi gereken alandaki kişi "alan".
    "vehicle_on_walkway": "tir",
    "person_in_vehicle_lane": "alan",
    "restricted_entry": "alan",
}

# Bölge tipi → simge. Renk stil.css'teki --bolge-* değişkenlerinden gelir
# (yeni bölge çizilirken kullanılan renklerle aynı).
BOLGE_SIMGELERI = {
    "pedestrian_path": "yaya-yolu",
    "loading_area": "yukleme",
    "truck_parking": "park",
    "vehicle_area": "arac-yolu",
    "ppe_required": "kkd",
    "restricted": "yasak",
    "crossing": "gecit",
    "ppe_exempt": "muaf",
}


def _liste(deger) -> list:
    """Kural kaydındaki JSON alanı: bazen çözülmüş liste, bazen ham metin."""
    if isinstance(deger, str):
        try:
            deger = json.loads(deger)
        except json.JSONDecodeError:
            return []
    return list(deger) if isinstance(deger, (list, tuple)) else []


def _sozluk(deger) -> dict:
    if isinstance(deger, str):
        try:
            deger = json.loads(deger)
        except json.JSONDecodeError:
            return {}
    return deger if isinstance(deger, dict) else {}


def olay_ogesi(olay_tipi: str, kural: dict, detaylar: dict) -> str:
    """Olayın öğesi (`OGELER` anahtarı): ekranda hangi simgeyle görüneceği.

    Olay anındaki kural kaydından çıkarılır; kural sonradan silinse ya da
    değişse de geçmiş olay aynı simgeyle görünür. Kayıt bölge TİPİNİ
    taşımaz, bu yüzden bölge ihlalinde yön ve hedeften okunur: yolun
    DIŞINDA kalan kişi yaya yolu, alanın dışında duran tır park yeri,
    alanın İÇİNDE kalan kişi girilmemesi gereken alandır (yasak bölge ile
    yükleme alanı aynı simgeyi paylaşır). Bilinmeyen durum genel bölge
    simgesine düşer; hiçbir olay simgesiz kalmaz.
    """
    if olay_tipi == "system":
        return "kamera" if str(detaylar.get("mesaj", "")).startswith("Kamera") else "sistem"
    tip = kural.get("rule_type", "")
    if tip == "ppe_violation":
        eksik = set(_liste(detaylar.get("eksik_kkd")))
        if eksik == {"helmet"}:
            return "baret"
        if eksik == {"vest"}:
            return "yelek"
        return "kkd"
    if tip == "safe_distance":
        return "forklift"
    if tip == "vehicle_speed":
        return "hiz"
    if tip == "zone_intrusion":
        hedef = _liste(kural.get("target_classes"))
        yon = _sozluk(kural.get("params")).get("mode")
        if "truck" in hedef or "forklift" in hedef:
            return "park" if yon == "outside" else "tir"
        return "yaya-yolu" if yon == "outside" else "alan"
    return "alan"


# .env'deki ANONS ayarının başlıkta gösterilen KISA adı. Uzun açıklamalar
# web/anons_web.py ANONS_ACIKLAMALARI'nda; burada yalnızca tek kelimelik ad.
ANONS_KISA_ADLARI = {"null": "kapalı", "ses_karti": "ses kartı", "http": "IP hoparlör"}


# ---------------------------------------------------------------- olay özeti
#
# Olay listesi, CSV, canlı akış (SSE) ve komuta ekranı AYNI cümleyi göstermeli.
# Özet metni iki ayrı yerde üretilirse er ya da geç birbirinden ayrılır ve
# kullanıcı aynı olayı iki farklı isimle görür; bu yüzden tek yerde durur.

OLAY_SORGUSU = (
    "SELECT e.*, c.name AS kamera_adi, c.area AS kamera_alani "
    "FROM events e LEFT JOIN cameras c ON c.id = e.camera_id"
)


def sayi_metni(deger, birim: str = "", basamak: int = 1) -> str:
    """Ölçülen değeri Türkçe yazımıyla gösterir: 1.85 → '1,85 m'.

    Türkçede ondalık ayırıcı virgüldür; aynı sayı ekranın bir yerinde nokta,
    başka yerinde virgülle görünürse kullanıcı iki farklı ölçüm sanır.
    Değer yoksa BOŞ metin döner — çağıran taraf o kutuyu hiç çizmez; boş
    kutuya "—" yazmak "ölçüldü ama sonuç çıkmadı" izlenimi verirdi.
    """
    if deger is None:
        return ""
    try:
        metin = f"{float(deger):.{basamak}f}"
    except (TypeError, ValueError):
        return ""
    if "." in metin:
        metin = metin.rstrip("0").rstrip(".")
    return f"{metin.replace('.', ',')} {birim}".strip()


# ----------------------------------------------------------- yoğunluk çubukları
#
# Komuta panosu, anons ekranı ve rapor AYNI çubukları çizer. Üç ayrı yerde
# kovalanan bir histogram, aynı olayı üç grafikte farklı saate düşürebilirdi;
# bu yüzden hesap tek yerde durur (kütüphane YOK — sade CSS genişliği).

# Renk eşiği SAYIYA değil, o listedeki EN YÜKSEK değere ORANLA verilir:
# 4 ihlalli küçük bir kurulumda da 400 ihlalli büyük bir kurulumda da "en yoğun
# alan" kırmızı görünsün. Sabit bir "20 ihlal = kırmızı" eşiği kurulumdan
# kuruluma yanlış olurdu.
YOGUN_ORANI = 0.66
ORTA_ORANI = 0.33


def yogunluk_sinifi(deger: int, en_yuksek: int) -> str:
    if en_yuksek <= 0:
        return ""
    oran = deger / en_yuksek
    if oran >= YOGUN_ORANI:
        return "yogun"
    if oran >= ORTA_ORANI:
        return "orta"
    return ""


def cubuk_yuzdesi(deger: int, en_yuksek: int) -> str:
    """Çubuk genişliği/yüksekliği — en yüksek değere oranla."""
    if en_yuksek <= 0:
        return "0%"
    return f"{round(deger / en_yuksek * 100)}%"


def saat_sutunlari(zamanlar, birim: str) -> dict:
    """UTC damga listesini 00-23 arası 24 sütuna böler (histogram).

    Kovalama SQL'de değil Python'da yapılır: veritabanındaki damgalar UTC'dir,
    SQLite'ın saat dilimi bilgisi yoktur ve sütunlar 3 saat kayardı.

    İhlal dağılımı, anons dağılımı ve rapor bu fonksiyonu kullanır: ayrı
    kovalama kodları olsaydı aynı olay iki grafikte farklı saate düşebilirdi.
    """
    kovalar = [0] * 24
    for damga in zamanlar:
        kovalar[zaman.yerel_saat(damga)] += 1

    toplam = sum(kovalar)
    en_yuksek = max(kovalar) if toplam else 0
    sutunlar = [
        {
            "etiket": f"{saat:02d}",
            "deger": adet,
            "yukseklik": cubuk_yuzdesi(adet, en_yuksek),
            "sinif": yogunluk_sinifi(adet, en_yuksek),
        }
        for saat, adet in enumerate(kovalar)
    ]
    tepe = ""
    if toplam:
        saat = kovalar.index(en_yuksek)
        tepe = f"En yoğun {saat:02d}:00 – {(saat + 1) % 24:02d}:00 · {en_yuksek} {birim}"
    return {"sutunlar": sutunlar, "toplam": toplam, "tepe": tepe}


# --------------------------------------------------------------- Türkçe ekler
#
# Sayıdan sonra gelen ek, sayının OKUNUŞUNA göre değişir: "%36'sı" ama "%69'u",
# "%7'sinde" ama "%64'ünde". Şablona sabit yazılırsa er ya da geç yanlış olur —
# ve bir kez oldu: Nesneler sayfasındaki kart "%36'i bulundu ve %7'inde" diyor,
# aynı sayfanın alt paragrafı ise doğru yazıyordu. Sayı ölçümden geldiği için
# yarın 36 değil 69 olabilir; ek de onunla değişmelidir.
#
# Ek son RAKAMA değil, okunuşun son KELİMESİNE bağlıdır: 14 "on dört"tür ve eki
# dörtten gelir ("%14'ü"), 40 "kırk"tır ve eki kırktan gelir ("%40'ı").

# okunuşun son kelimesi → (iyelik, iyelik+bulunma, ayrılma)
#   iyelik          : "%36'sı bulundu"
#   iyelik+bulunma  : "%7'sinde işaret nesnenin üstündeydi"
#   ayrılma         : "4'ten fazlası"
_SAYI_EKLERI = {
    "sıfır": ("ı", "ında", "dan"),
    "bir": ("i", "inde", "den"),
    "iki": ("si", "sinde", "den"),
    "üç": ("ü", "ünde", "ten"),
    "dört": ("ü", "ünde", "ten"),
    "beş": ("i", "inde", "ten"),
    "altı": ("sı", "sında", "dan"),
    "yedi": ("si", "sinde", "den"),
    "sekiz": ("i", "inde", "den"),
    "dokuz": ("u", "unda", "dan"),
    "on": ("u", "unda", "dan"),
    "yirmi": ("si", "sinde", "den"),
    "otuz": ("u", "unda", "dan"),
    "kırk": ("ı", "ında", "tan"),
    "elli": ("si", "sinde", "den"),
    "altmış": ("ı", "ında", "tan"),
    "yetmiş": ("i", "inde", "ten"),
    "seksen": ("i", "inde", "den"),
    "doksan": ("ı", "ında", "dan"),
    "yüz": ("ü", "ünde", "den"),
}
_BIRLER = ("sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz")
_ONLAR = ("", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan")
_HALLER = {"iyelik": 0, "bulunma": 1, "ayrilma": 2}


def sayi_okunusu(sayi: int) -> str:
    """Ekin bağlı olduğu son kelime: 14 → 'dört', 40 → 'kırk', 100 → 'yüz'.

    Yüzdeler (0-100) için yazıldı; daha büyük sayılarda son iki basamağa bakar,
    yani 1500 doğru ("yüz"), 1000 yanlış olurdu — bu fonksiyona öyle bir sayı
    gelmez ve gelirse de ek üretmek yerine yanlış ek yazmak istemeyiz.
    """
    kalan = abs(int(sayi)) % 100
    if kalan == 0:
        return "sıfır" if abs(int(sayi)) == 0 else "yüz"
    if kalan % 10:
        return _BIRLER[kalan % 10]
    return _ONLAR[kalan // 10]


def sayi_eki(sayi, hal: str = "iyelik") -> str:
    """Sayıdan sonra gelen Türkçe eki kesme işaretiyle verir: 36 → "'sı".

    Şablonda süzgeç olarak kullanılır (web/rotalar.py kaydeder):
        %{{ yuzde }}{{ yuzde|sayi_eki }} bulundu
        %{{ yuzde }}{{ yuzde|sayi_eki('bulunma') }} işaret nesnenin üstündeydi
    Sayı okunamıyorsa BOŞ döner: eksiz bir cümle, yanlış ekli bir cümleden iyidir.
    """
    try:
        okunus = sayi_okunusu(int(sayi))
    except (TypeError, ValueError):
        return ""
    return "'" + _SAYI_EKLERI[okunus][_HALLER.get(hal, 0)]


def olay_hazirla(satir) -> dict:
    """Veritabanı satırını ekrana hazır olay sözlüğüne çevirir."""
    olay = dict(satir)
    olay["yerel_zaman"] = zaman.ekranda_goster(olay["occurred_at"])
    olay["durum_adi"] = OLAY_DURUMLARI.get(olay["status"], olay["status"])
    olay["durum_kucuk"] = OLAY_DURUMLARI_KUCUK.get(olay["status"], olay["status"])
    try:
        olay["detaylar"] = json.loads(olay["details"]) if olay["details"] else {}
    except json.JSONDecodeError:
        olay["detaylar"] = {"ham": olay["details"]}
    try:
        kural = json.loads(olay["rule_snapshot"]) if olay["rule_snapshot"] else {}
    except json.JSONDecodeError:
        kural = {}
    # Kural anlık görüntüsü (olay anındaki eşikler) inceleme ekranında
    # "ölçülen değer" ile "kural eşiği" yan yana gösterilirken kullanılır.
    olay["kural_kaydi"] = kural
    olay["kural_tipi_adi"] = KURAL_TIPLERI.get(kural.get("rule_type", ""), "")
    # GÖLGE MOD (şema 002): kural çalışıp olay yazmış ama hoparlör susmuş ve
    # ekranda uyarı bandı çıkmamıştır. Kuralın BUGÜNKÜ halinden değil olay
    # anındaki anlık görüntüsünden okunur: kural sonradan canlıya alındıysa
    # geçmiş olay "anons çaldı" diye görünmemeli.
    olay["golge_mod"] = bool(kural.get("shadow_mode"))
    olay["oge"] = OGELER[olay_ogesi(olay["event_type"], kural, olay["detaylar"])]
    _kod_ve_sure(olay)
    if olay["event_type"] == "system":
        olay["ozet"] = olay["detaylar"].get("mesaj", "Sistem olayı")
    else:
        olay["ozet"] = _ihlal_ozeti(olay)
    return olay


def _kod_ve_sure(olay: dict) -> None:
    """Olay kodunun adı, önem ve süre (şema 007, docs/17 §6.1).

    007 öncesi olayda kod ve önem boştur: ekran kural tipinin adına düşer.
    `suruyor` yalnız kodlu ve bitişi olmayan olaydadır; anlık olayda (bitiş =
    başlangıç) süre metni boş kalır, çünkü "0 sn sürdü" bilgi değildir.
    """
    kod = olay.get("event_code")
    tanim = OLAY_KODLARI.get(kod) if kod else None
    olay["kod_adi"] = tanim.ad if tanim else ""
    olay["onem"] = olay.get("severity") or ""
    olay["onem_adi"] = ONEM_ADLARI.get(olay["onem"], "")
    bitis = olay.get("resolved_at")
    olay["suruyor"] = bool(kod) and bitis is None
    olay["bitis_zamani"] = zaman.ekranda_goster(bitis) if bitis else ""
    if olay["suruyor"]:
        olay["sure_metni"] = zaman.sure_metni(zaman.sure_saniye(olay["occurred_at"]))
    elif bitis and bitis != olay["occurred_at"]:
        olay["sure_metni"] = zaman.sure_metni(zaman.sure_saniye(olay["occurred_at"], bitis))
    else:
        olay["sure_metni"] = ""
    olay["kapanis_sebebi_adi"] = KAPANIS_SEBEPLERI.get(
        str(olay["detaylar"].get("kapanis_sebebi", "")), ""
    )


def _ihlal_ozeti(olay: dict) -> str:
    """ "Yasak alana giriş", "Araç–yaya yakınlığı — 1,85 m", "Baret ve yelek yok".

    Kodlu olayda başlık kodun adıdır; 007 öncesi olayda kural tipinin adı
    ("KKD (baret/yelek) — baret yok") — eski olayın yazısı değişmez.
    """
    detay = olay["detaylar"]
    ad = olay["kod_adi"] or olay["kural_tipi_adi"] or "İhlal"
    eksik = [KKD_ADLARI.get(k, k) for k in _liste(detay.get("eksik_kkd"))]
    if eksik and olay["kod_adi"]:
        # Kodun adı yalnız ağır kalemi söyler ("Baret yok"); iki kalem eksikse
        # ikisi de yazılır.
        metin = " ve ".join(eksik) + " yok"
        return metin[0].upper() + metin[1:]
    if eksik:
        return f"{ad} — {', '.join(eksik)} yok"
    if detay.get("mesafe_m") is not None:
        return f"{ad} — {sayi_metni(detay['mesafe_m'], 'm', 2)}"
    if detay.get("hiz_kmh") is not None:
        # Hız km/sa yazılır: fabrika hız levhaları da km/sa'dır. Ayarın
        # kendisi m/sn tutulur (Tespit.hiz_mps ile aynı birim).
        return f"{ad} — {sayi_metni(detay['hiz_kmh'], 'km/sa', 1)}"
    if detay.get("bolge_tipi") in BOLGE_TIPLERI:
        # Yedek kod (ZONE_INTRUSION): olayın ne olduğunu bölge tipi söyler
        return f"{ad} — {BOLGE_TIPLERI[detay['bolge_tipi']]}"
    return ad


def baglanti_al(istek: Request) -> Iterator:
    """İstek başına SQLite bağlantısı (FastAPI dependency)."""
    baglanti = veritabani.baglanti_ac(istek.app.state.ayarlar.veritabani_yolu)
    try:
        yield baglanti
    finally:
        baglanti.close()


def rtsp_maskele(url: str) -> str:
    """rtsp://kullanici:sifre@ip/... → rtsp://••••@ip/...  (docs/01 §3.6).

    Kamera adresleri için yazıldı, ama şema/protokole bakmaz: hoparlör
    bölgelerinin http adresleri de aynı desenle maskelenir. Adresin kendisi
    (ip, port, yol) görünür kalır — kullanıcı hangi cihazı yazdığını görmeli;
    gizlenen yalnızca kullanıcı adı ve şifredir. Desen günlükle ortaktır
    (loglama.ADRES_KIMLIGI).
    """
    return adres_maskele(url)


def maskeyi_coz(gonderilen: str, kayitli: str) -> str:
    """Formda maskeli gösterilen adres geri gelince kayıtlı kimliği yerine koyar.

    Düzenleme formları adresi maskeli basar (docs/17 §10.5 R18): şifre sayfa
    kaynağına, tarayıcı önbelleğine ya da ekran görüntüsüne düşmez. Kullanıcı
    •••• kısmını olduğu gibi bırakırsa kayıtlı kullanıcı adı ve şifre korunur;
    adresin geri kalanını (ip, port, yol) değiştirse de. Yeni kimlik yazarsa
    o geçerlidir.
    """
    if "••••" not in gonderilen:
        return gonderilen
    eslesme = ADRES_KIMLIGI.search(kayitli or "")
    if ADRES_MASKESI not in gonderilen or eslesme is None:
        raise DogrulamaHatasi(
            "Adresteki •••• yerine kullanıcı adını ve şifreyi yazın. "
            "Biçim: rtsp://kullanici:sifre@IP:554/yol ya da http://kullanici:sifre@IP/yol"
        )
    return gonderilen.replace(ADRES_MASKESI, f"//{eslesme.group(1)}@", 1)


def guvenli_json(veri) -> str:
    """<script> bloğuna gömülecek JSON — HTML'e özel karakterler kaçırılır.

    json.dumps `<`, `>`, `&` karakterlerini kaçırmaz; kullanıcı verisi (örn.
    bölge adı) `</script><img onerror=...>` içerirse depolanan XSS olurdu.
    Unicode kaçışları JSON içinde birebir aynı metni temsil eder.
    """
    metin = json.dumps(veri, ensure_ascii=False)
    return metin.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# CSV formül enjeksiyonu (docs/17 §10.5 R31). Excel ve LibreOffice = + - @ ile
# (ya da sekme / satır başı ile) başlayan hücreyi FORMÜL olarak okur. Kamera
# adı, bölüm, bölge adı ve inceleme notu kullanıcıdan gelir: adı
# `=HYPERLINK(...)` olan bir kamera, raporu açan kişinin bilgisayarında
# tıklanabilir bir bağlantıya ya da dış veri isteğine dönüşürdü. Böyle başlayan
# METİN hücresinin başına tek tırnak eklenir; sayı hücreleri (negatif sayı
# dahil) değişmez.
_FORMUL_BASLARI = ("=", "+", "-", "@", "\t", "\r")


def csv_hucresi(deger):
    if isinstance(deger, str) and deger.startswith(_FORMUL_BASLARI):
        return "'" + deger
    return deger


class CsvYazici:
    """Noktalı virgüllü CSV (Türkçe Excel bunu bekler); her hücre
    `csv_hucresi`'nden geçer. Dışa aktarılan her CSV bunu kullanır: kaçış tek
    yerde olmasaydı yeni bir sütun ya da yeni bir dosya onu unuturdu."""

    def __init__(self, tampon) -> None:
        self._yazici = csv.writer(tampon, delimiter=";")

    def writerow(self, satir) -> None:
        self._yazici.writerow([csv_hucresi(hucre) for hucre in satir])


# ---------------------------------------------------------------- hazır kurallar
#
# Kullanıcı bir bölge çizdiğinde "çizdim ama hiçbir şey olmuyor" durumuna
# düşmemeli: her bölge tipinin, tek tıkla kurulabilen bir karşılığı vardır.
# Eşleme ve varsayılanlar docs/03-KURAL-MOTORU.md'den alınmıştır.


@dataclass(frozen=True)
class HazirKural:
    """Bir bölge tipinin tek tıkla kurulan kural karşılığı (docs/03).

    `params` YALNIZCA şema varsayılanından FARKLI olan alanları taşır; kalan
    eşikler app/rules/parametreler.py'deki (yine docs/03 tablolarından alınmış)
    varsayılanlardan gelir. Böylece hiçbir eşik iki ayrı yerde yazılmaz.
    """

    kural_tipi: str
    hedef_siniflar: tuple[str, ...]
    params: dict
    anons_anahtari: str | None  # announcement_messages.key — yoksa yalnız ekran uyarısı
    cooldown_s: int | None  # None → VARSAYILAN_COOLDOWN_SN[kural_tipi]
    kisa_ad: str  # düğme metni: '"Ad" için {kisa_ad} ekle'
    aciklama: str  # {param} yer tutucuları çözülmüş params ile doldurulur
    # Gölge modda doğar (şema 002): olay yazılır, anons çalmaz. Sahada yanlış
    # alarm oranı ölçülmemiş yeni bir kural hoparlörü boşuna konuşturmasın;
    # operatör ölçtükten sonra Kurallar sayfasından gölgeyi kapatır.
    golge: bool = False
    # EK_HAZIR_KURALLAR'da düğmenin gönderdiği anahtar; birincil kuralda boş
    anahtar: str = ""


# docs/03: kural tipine göre varsayılan cooldown (saniye)
VARSAYILAN_COOLDOWN_SN = {
    "zone_intrusion": 120,
    "safe_distance": 90,
    "ppe_violation": 180,
    # Hız ihlali anlıktır ve sürücü uyarıyı duyunca yavaşlar; 90 sn, aynı
    # forklift için ikinci uyarının anlamlı olacağı en kısa aralıktır.
    "vehicle_speed": 90,
}

HAZIR_KURALLAR: dict[str, HazirKural] = {
    # docs/03 Ek — yolu KULLANMAYAN kişi ihlaldir (mode=outside)
    "pedestrian_path": HazirKural(
        kural_tipi="zone_intrusion",
        hedef_siniflar=("person",),
        params={"mode": "outside", "min_dwell_s": 5.0},
        anons_anahtari="pedestrian_path",
        cooldown_s=180,
        kisa_ad="yaya yolu kuralı",
        aciklama=(
            "Yaya yolunun DIŞINDA {min_dwell_s:g} saniyeden uzun kalan kişi uyarı üretir; "
            "yolun kenarına bir adım atan kişi uyarı üretmez. Hoparlörden "
            "«Lütfen yaya yolunu kullanınız.» anonsu geçilir."
        ),
    ),
    # docs/03 §1 — yasak bölgede olmak ihlaldir (mode=inside, varsayılan).
    # Şema 007'nin "restricted_entry" mesajına bağlanır (docs/17 §8.2).
    "restricted": HazirKural(
        kural_tipi="zone_intrusion",
        hedef_siniflar=("person",),
        params={"mode": "inside"},
        anons_anahtari="restricted_entry",
        cooldown_s=None,
        kisa_ad="yasak bölge kuralı",
        aciklama=(
            "Yasak bölgeye girip {min_dwell_s:g} saniyeden uzun kalan kişi uyarı üretir. "
            "Hoparlörden «Bu alana giriş yasaktır.» anonsu geçilir; metni Anons "
            "sayfasından değiştirebilirsiniz."
        ),
    ),
    # docs/03 §1 tablosu — "Yükleme alanında yaya": inside / person
    "loading_area": HazirKural(
        kural_tipi="zone_intrusion",
        hedef_siniflar=("person",),
        params={"mode": "inside"},
        anons_anahtari=None,
        cooldown_s=None,
        kisa_ad="yükleme alanı kuralı",
        aciklama=(
            "Yükleme alanının İÇİNDE {min_dwell_s:g} saniyeden uzun kalan kişi uyarı üretir "
            "— forklift ve tırın çalıştığı alanda yaya durmamalıdır."
        ),
    ),
    # docs/03 §1 tablosu — "Tır yanlış konumda": outside / truck
    "truck_parking": HazirKural(
        kural_tipi="zone_intrusion",
        hedef_siniflar=("truck",),
        params={"mode": "outside"},
        anons_anahtari="vehicle_position",
        cooldown_s=None,
        kisa_ad="tır konumlanma kuralı",
        aciklama=(
            "Tır park alanının DIŞINDA {min_dwell_s:g} saniyeden uzun duran tır uyarı üretir. "
            "Hoparlörden «Lütfen aracınızı belirlenen alana konumlandırınız.» anonsu geçilir."
        ),
    ),
    # docs/03 §2 — güvenli mesafe; bölge verilince yalnız o alandaki kişiler korunur
    "vehicle_area": HazirKural(
        kural_tipi="safe_distance",
        hedef_siniflar=("person", "forklift", "truck"),
        params={},
        anons_anahtari="safe_distance",
        cooldown_s=None,
        kisa_ad="güvenli mesafe kuralı",
        aciklama=(
            "Bu alandaki bir kişi ile HAREKET HALİNDEKİ forklift/tır arasındaki mesafe "
            "{distance_m:g} metrenin altına düşerse uyarı üretir. Hoparlörden "
            "«Lütfen iş makinelerinden güvenli mesafede durunuz.» anonsu geçilir."
        ),
    ),
    # docs/03 §3 — KKD kuralı yalnızca bu tipte bölgede çalışır
    "ppe_required": HazirKural(
        kural_tipi="ppe_violation",
        hedef_siniflar=("person",),
        params={},
        anons_anahtari=None,  # baret ve yelek mesajı ayrıdır; kullanıcı seçer
        cooldown_s=None,
        kisa_ad="KKD (baret/yelek) kuralı",
        # Gölgede doğar (docs/17 §5.7-1, S25): anons KKD kapısından sonra açılır
        golge=True,
        aciklama=(
            "Bu bölgede baret veya yelek takmayan kişi uyarı üretir. Karar tek kareye değil "
            "{window_size} gözlemlik pencereye bakılarak verilir; emin olunamayan durum ihlal "
            "sayılmaz. Baret/yelek anonsunu Kurallar sayfasından seçebilirsiniz."
        ),
    ),
}


# Bir bölge tipinin BİRİNCİL kuralına ek olarak kurulabilen kurallar (docs/17
# §6.1, §8.2). İkisi de gölge modda doğar ve şema 007'nin mesajlarına bağlanır;
# kalış süreleri docs/17 §4.5'ten. Geçitteki (crossing) yaya ya da araç ihlal
# sayılmaz (kuralın `gecit_haric` varsayılanı açık).
EK_HAZIR_KURALLAR: dict[str, tuple[HazirKural, ...]] = {
    "pedestrian_path": (
        HazirKural(
            kural_tipi="zone_intrusion",
            hedef_siniflar=("forklift", "truck"),
            params={"mode": "inside", "min_dwell_s": 1.0},
            anons_anahtari="vehicle_on_walkway",
            cooldown_s=None,
            kisa_ad="yaya yolunda araç kuralı",
            aciklama=(
                "Yaya yolunun İÇİNDE {min_dwell_s:g} saniyeden uzun kalan forklift ya da tır "
                "uyarı üretir; yaya-araç geçidindeki araç uyarı üretmez. Gölge modda "
                "kurulur: olay yazılır, hoparlör susar. Yanlış alarmları gördükten sonra "
                "Kurallar sayfasından gölge modu kapatınca «Dikkat, yaya yolunda araç var.» "
                "anonsu çalar."
            ),
            golge=True,
            anahtar="yaya_yolunda_arac",
        ),
    ),
    "vehicle_area": (
        HazirKural(
            kural_tipi="zone_intrusion",
            hedef_siniflar=("person",),
            params={"mode": "inside", "min_dwell_s": 1.5},
            anons_anahtari="person_in_vehicle_lane",
            cooldown_s=None,
            kisa_ad="araç yolunda yaya kuralı",
            aciklama=(
                "Araç sahasının İÇİNDE {min_dwell_s:g} saniyeden uzun kalan kişi uyarı "
                "üretir; o anda sahada bir araç da varsa önemi Yüksek olur. Yaya-araç "
                "geçidindeki kişi uyarı üretmez. Gölge modda kurulur: olay yazılır, "
                "hoparlör susar; gölge modu Kurallar sayfasından kapatınca «Lütfen araç "
                "yolundan çıkınız.» anonsu çalar."
            ),
            golge=True,
            anahtar="arac_yolunda_yaya",
        ),
    ),
}


def bolge_hazir_kurallari(bolge_tipi: str) -> list[HazirKural]:
    """Bölge tipinin kurulabilir bütün hazır kuralları: birincil + ekler."""
    birincil = HAZIR_KURALLAR.get(bolge_tipi)
    return ([birincil] if birincil else []) + list(EK_HAZIR_KURALLAR.get(bolge_tipi, ()))


def ayni_hazir_kural_var(baglanti, zone_id: int, hazir: HazirKural) -> bool:
    """Bölgede bu hazır kuralın AYNISI (tip, yön, hedef sınıflar) kurulu mu?

    "Bölgede herhangi bir kural var mı" sorusu yetmez: yaya yolunda "yolun
    dışındaki kişi" ile "yoldaki araç" iki ayrı kuraldır.
    """
    for satir in baglanti.execute(
        "SELECT rule_type, target_classes, params FROM rules WHERE zone_id = ?", (zone_id,)
    ):
        if satir["rule_type"] != hazir.kural_tipi:
            continue
        if hazir.kural_tipi != "zone_intrusion":
            return True
        yon = _sozluk(satir["params"]).get("mode", "inside")
        if yon == hazir.params.get("mode", "inside") and set(
            _liste(satir["target_classes"])
        ) == set(hazir.hedef_siniflar):
            return True
    return False


def hazir_kural_params(hazir: HazirKural) -> dict:
    """Hazır kuralın TAM parametre sözlüğü: farklar + şema varsayılanları."""
    return params_dogrula(hazir.kural_tipi, dict(hazir.params))


def hazir_kural_aciklamasi(hazir: HazirKural) -> str:
    """Kullanıcıya gösterilen cümle; içindeki sayılar kaydedilecek değerlerdir."""
    return hazir.aciklama.format(**hazir_kural_params(hazir))


def hazir_kural_cooldown(hazir: HazirKural) -> int:
    return hazir.cooldown_s or VARSAYILAN_COOLDOWN_SN[hazir.kural_tipi]


# /saglik "sorunlar" kodlarının komuta ekranlarındaki sistem şeridi metni
# (static/sistem_seridi.js; docs/06 §2 tablosu). Şeritte yalnız bu kodlar
# görünür ve hepsi kırmızıdır: uyarının üretilmediğini ya da kaydedilmediğini
# söylerler. ort_paket_cakismasi bilerek yok: teknik bir kurulum notudur,
# /saglik ve Kontrol Paneli söyler. Kontrol Paneli'nin kendi metinleri
# masaustu/dalsan_launcher.py'dedir (ayrı program, uygulamayı içe aktarmaz).
SAGLIK_SORUN_METINLERI: dict[str, str] = {
    "analiz_takildi": "Analiz takıldı — görüntü geliyor ama uyarı üretilmiyor",
    "analiz_olu": "Analiz durdu — uyarı üretilmiyor",
    "model_yuklenemedi": "Analiz yapılmıyor — model yüklenemedi",
    "veritabani_acilamadi": "Veritabanı okunamıyor — olaylar kaydedilemeyebilir",
    "olay_yazilamadi": "Son ihlal kaydedilemedi — anons yine de çaldı",
    "kritik_kural_pasif": "Mesafe ya da hız kuralı çalışmıyor — kalibrasyon bekleniyor",
}
