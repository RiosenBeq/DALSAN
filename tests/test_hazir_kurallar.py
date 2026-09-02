"""Her bölge tipi için tek tıkla kural: "çizdim ama hiçbir şey olmuyor" bitiyor.

Neden bu testler var:

Bölge çizmek tek başına hiçbir uyarı üretmez; bölgenin bir KURALA bağlanması
gerekir. Eskiden kamera sayfasındaki tek kısayol yaya yolu içindi; diğer beş
bölge tipinde kullanıcı bölgeyi çiziyor, hiçbir şey olmuyor, kural kurmak için
ayrı bir sayfaya gidip form dolduruyordu. Yazılım bilmeyen bir kullanıcı için
"yaya geçidini/yasak alanı tanıtmak" tam burada kırılıyordu.

Artık altı bölge tipinin altısında da hazır kural var. Eşleme docs/03'ten
gelir; eşikler app/rules/parametreler.py'deki şema varsayılanlarından (yine
docs/03 tabloları) okunur — hiçbir eşik iki ayrı yerde yazılmaz. Bu testler
hem eşlemeyi hem de "eşik tek kaynaktan gelir" kuralını korur.
"""

from __future__ import annotations

import json

import pytest

from app import veritabani
from app.rules.parametreler import BolgeIhlaliParams, KkdParams, MesafeParams, params_dogrula
from app.web.ortak import (
    BOLGE_TIPLERI,
    HAZIR_KURALLAR,
    VARSAYILAN_COOLDOWN_SN,
    hazir_kural_aciklamasi,
    hazir_kural_cooldown,
    hazir_kural_params,
)

# docs/03-KURAL-MOTORU.md'deki eşleme:
#   bölge tipi -> (kural tipi, hedef sınıflar, mode, anons anahtarı)
DOKUMAN_ESLEMESI = {
    "pedestrian_path": ("zone_intrusion", ["person"], "outside", "pedestrian_path"),
    "restricted": ("zone_intrusion", ["person"], "inside", None),
    "loading_area": ("zone_intrusion", ["person"], "inside", None),
    "truck_parking": ("zone_intrusion", ["truck"], "outside", "vehicle_position"),
    "vehicle_area": ("safe_distance", ["person", "forklift", "truck"], None, "safe_distance"),
    "ppe_required": ("ppe_violation", ["person"], None, None),
}


def _kamera_ekle(istemci, test_ayarlari) -> int:
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "K1", "source_type": "file", "source_url": str(video), "sample_fps": "6"},
        follow_redirects=False,
    )
    return int(yanit.headers["location"].rsplit("/", 1)[1])


def _bolge_ekle(istemci, test_ayarlari, kamera_id: int, tip: str, ad: str) -> int:
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": ad,
            "zone_type": tip,
            "polygon": "[[0.25,0.25],[0.75,0.25],[0.75,0.75],[0.25,0.75]]",
        },
        follow_redirects=False,
    )
    return _sorgu(test_ayarlari, "SELECT MAX(id) AS m FROM zones")["m"]


def _sorgu(test_ayarlari, sorgu: str, parametreler: tuple = ()):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute(sorgu, parametreler).fetchone()
        return dict(satir) if satir is not None else None
    finally:
        baglanti.close()


# ---- 1. tablo: her bölge tipinin karşılığı var ve docs/03 ile aynı ----


def test_her_bolge_tipinin_hazir_kurali_var():
    """Altı bölge tipinin altısı da bir kurala bağlanabilmeli; biri eksik
    kalırsa o tipi çizen kullanıcı yine 'hiçbir şey olmuyor' der."""
    assert set(HAZIR_KURALLAR) == set(BOLGE_TIPLERI)


@pytest.mark.parametrize("tip", sorted(DOKUMAN_ESLEMESI))
def test_esleme_dokumanla_ayni(tip):
    kural_tipi, hedefler, mode, anons = DOKUMAN_ESLEMESI[tip]
    hazir = HAZIR_KURALLAR[tip]
    assert hazir.kural_tipi == kural_tipi
    assert list(hazir.hedef_siniflar) == hedefler
    assert hazir.anons_anahtari == anons
    if mode is not None:
        assert hazir_kural_params(hazir)["mode"] == mode


def test_esikler_semadan_gelir_koda_gomulmez():
    """Hazır kural yalnızca docs/03'te AÇIKÇA farklı olan alanları taşır;
    kalan eşikler şema varsayılanından gelir. Eşik iki yerde yazılırsa biri
    değişip diğeri unutulur."""
    # Yaya yolu: docs/03 Ek'te bilerek farklı (kenara bir adım atan uyarı üretmesin)
    yaya = hazir_kural_params(HAZIR_KURALLAR["pedestrian_path"])
    assert yaya["min_dwell_s"] == 5.0
    assert hazir_kural_cooldown(HAZIR_KURALLAR["pedestrian_path"]) == 180

    # Diğer bölge kuralları şema varsayılanını kullanır
    varsayilan_dwell = BolgeIhlaliParams().min_dwell_s
    for tip in ("restricted", "loading_area", "truck_parking"):
        assert hazir_kural_params(HAZIR_KURALLAR[tip])["min_dwell_s"] == varsayilan_dwell
        assert hazir_kural_cooldown(HAZIR_KURALLAR[tip]) == VARSAYILAN_COOLDOWN_SN["zone_intrusion"]

    mesafe = hazir_kural_params(HAZIR_KURALLAR["vehicle_area"])
    assert mesafe == MesafeParams().model_dump()
    assert hazir_kural_cooldown(HAZIR_KURALLAR["vehicle_area"]) == 90

    kkd = hazir_kural_params(HAZIR_KURALLAR["ppe_required"])
    assert kkd == KkdParams().model_dump()
    assert hazir_kural_cooldown(HAZIR_KURALLAR["ppe_required"]) == 180


def test_aciklamalardaki_sayilar_kaydedilecek_degerlerdir():
    """Ekranda yazan sayı ile kurulan kuralın değeri aynı olmalı; yoksa
    kullanıcı 5 saniye okuyup 2 saniyelik kural kurar."""
    metin = hazir_kural_aciklamasi(HAZIR_KURALLAR["pedestrian_path"])
    assert "5 saniyeden" in metin
    assert "3 metrenin" in hazir_kural_aciklamasi(HAZIR_KURALLAR["vehicle_area"])
    for tip in HAZIR_KURALLAR:
        assert "{" not in hazir_kural_aciklamasi(HAZIR_KURALLAR[tip]), "çözülmemiş yer tutucu"


# ---- 2. uç nokta: her tip için gerçekten kural kuruyor ----


@pytest.mark.parametrize("tip", sorted(DOKUMAN_ESLEMESI))
def test_tek_tikla_kural_kurulur(istemci, test_ayarlari, tip):
    kural_tipi, hedefler, mode, anons_anahtari = DOKUMAN_ESLEMESI[tip]
    kamera_id = _kamera_ekle(istemci, test_ayarlari)
    bolge_id = _bolge_ekle(istemci, test_ayarlari, kamera_id, tip, f"Alan {tip}")

    yanit = istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    assert yanit.status_code == 303, yanit.text
    assert yanit.headers["location"] == f"/kameralar/{kamera_id}"

    kural = _sorgu(test_ayarlari, "SELECT * FROM rules WHERE zone_id = ?", (bolge_id,))
    assert kural is not None, f"{tip} için kural kurulmadı"
    assert kural["rule_type"] == kural_tipi
    assert kural["camera_id"] == kamera_id
    assert json.loads(kural["target_classes"]) == hedefler
    assert kural["enabled"] == 1, "hazır kural kurulur kurulmaz çalışmalı"
    assert kural["cooldown_s"] == hazir_kural_cooldown(HAZIR_KURALLAR[tip])
    # Parametreler şemadan geçmiş olmalı: motor bunları yüklerken doğruluyor
    params = json.loads(kural["params"])
    assert params == params_dogrula(kural_tipi, params)
    if mode is not None:
        assert params["mode"] == mode

    if anons_anahtari is None:
        assert kural["announcement_id"] is None
    else:
        anons = _sorgu(
            test_ayarlari,
            "SELECT id FROM announcement_messages WHERE key = ?",
            (anons_anahtari,),
        )
        assert kural["announcement_id"] == anons["id"]


@pytest.mark.parametrize("tip", sorted(DOKUMAN_ESLEMESI))
def test_kisayol_dugmesi_gorunur_ve_kural_kurulunca_kaybolur(istemci, test_ayarlari, tip):
    kamera_id = _kamera_ekle(istemci, test_ayarlari)
    bolge_id = _bolge_ekle(istemci, test_ayarlari, kamera_id, tip, "Deneme alanı")

    detay = istemci.get(f"/kameralar/{kamera_id}").text
    dugme = f'"Deneme alanı" için {HAZIR_KURALLAR[tip].kisa_ad} ekle'
    assert dugme in detay, f"{tip} için hazır kural düğmesi yok"
    assert hazir_kural_aciklamasi(HAZIR_KURALLAR[tip])[:40] in detay, "ne yapacağı yazmıyor"

    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert dugme not in detay, "kural kurulduktan sonra düğme durmamalı"


def test_kurulan_kural_kurallar_sayfasindan_duzenlenebilir(istemci, test_ayarlari):
    """Hazır kural sıradan bir kuraldır: değerleri beğenilmezse elle değişir."""
    kamera_id = _kamera_ekle(istemci, test_ayarlari)
    bolge_id = _bolge_ekle(istemci, test_ayarlari, kamera_id, "restricted", "Trafo odası")
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)

    kural_id = _sorgu(test_ayarlari, "SELECT id FROM rules")["id"]
    liste = istemci.get("/kurallar").text
    assert "Trafo odası" in liste
    assert "Bölge ihlali" in liste
    assert istemci.get(f"/kurallar/{kural_id}/duzenle").status_code == 200


def test_ayni_bolgeye_ikinci_hazir_kural_kurulmaz(istemci, test_ayarlari):
    kamera_id = _kamera_ekle(istemci, test_ayarlari)
    bolge_id = _bolge_ekle(istemci, test_ayarlari, kamera_id, "restricted", "Trafo")
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    yanit = istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    assert yanit.status_code == 400
    assert "zaten bir kural var" in yanit.json()["hata"]
    assert _sorgu(test_ayarlari, "SELECT COUNT(*) AS n FROM rules")["n"] == 1


def test_olmayan_bolgeye_hazir_kural_kurulmaz(istemci, test_ayarlari):
    _kamera_ekle(istemci, test_ayarlari)
    yanit = istemci.post("/kurallar/hazir", data={"zone_id": "999"}, follow_redirects=False)
    assert yanit.status_code == 400
    assert "Bölge bulunamadı" in yanit.json()["hata"]


def test_mesafe_kisayolu_kalibrasyon_uyarisi_gosterir(istemci, test_ayarlari):
    """Güvenli mesafe kuralı kalibrasyonsuz ÇALIŞMAZ (docs/03 §2). Kullanıcı
    bunu kuralı kurmadan önce ekranda görmeli, yoksa 'kurdum ama çalışmıyor'."""
    kamera_id = _kamera_ekle(istemci, test_ayarlari)
    _bolge_ekle(istemci, test_ayarlari, kamera_id, "vehicle_area", "Forklift sahası")

    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "henüz kalibre edilmedi" in detay

    istemci.post(
        f"/kameralar/{kamera_id}/kalibrasyon",
        data={
            "image_points": "[[0,0],[1,0],[1,1],[0,1]]",
            "world_points": "[[0,0],[10,0],[10,10],[0,10]]",
        },
        follow_redirects=False,
    )
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "henüz kalibre edilmedi" not in detay


def test_kkd_kisayolu_kkd_bolgesine_baglanir(istemci, test_ayarlari):
    """KKD kuralı bölgesiz çalışmaz ve yalnızca 'KKD zorunlu alan' tipinde
    çalışır (docs/03 §3) — kısayol bu kuralı bozmamalı."""
    kamera_id = _kamera_ekle(istemci, test_ayarlari)
    bolge_id = _bolge_ekle(istemci, test_ayarlari, kamera_id, "ppe_required", "Kaynakhane")
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)

    kural = _sorgu(test_ayarlari, "SELECT * FROM rules")
    assert kural["rule_type"] == "ppe_violation"
    assert kural["zone_id"] == bolge_id
    bolge = _sorgu(test_ayarlari, "SELECT zone_type FROM zones WHERE id = ?", (bolge_id,))
    assert bolge["zone_type"] == "ppe_required"


# ---- 3. kurulan kural gerçekten uyarı üretiyor mu ----


def test_yasak_bolge_kisayolu_gercekten_uyari_uretir():
    """Kural motoru tarafı: kısayolun kurduğu değerlerle, yasak bölgede
    kalan kişi süre dolunca uyarı üretmeli. Bölge dışındaki kişi üretmemeli."""
    import sys

    sys.path.insert(0, "tests/rules")
    from yardimci import KARE, ORTA_BOLGE, kural, tespit

    from app.rules.motor import KuralMotoru
    from app.rules.tipler import Bolge

    hazir = HAZIR_KURALLAR["restricted"]
    yasak = Bolge(id=1, tip="restricted", poligon=list(ORTA_BOLGE))
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [
            kural(
                hazir.kural_tipi,
                hedefler=list(hazir.hedef_siniflar),
                params=hazir_kural_params(hazir),
                cooldown_s=hazir_kural_cooldown(hazir),
            )
        ]
    )

    def calistir(zaman_s, tespitler):
        return motor.degerlendir(zaman_s, KARE, tespitler, [yasak], None)

    disarda = [tespit(ayak=(0.05, 0.05), takip_id=1)]
    assert calistir(0.0, disarda) == []
    assert calistir(10.0, disarda) == []

    icerde = [tespit(ayak=(0.5, 0.5), takip_id=2)]
    assert calistir(20.0, icerde) == [], "kalış süresi dolmadan uyarı olmamalı"
    ihlaller = calistir(23.0, icerde)
    assert len(ihlaller) == 1
    assert ihlaller[0].detaylar["mode"] == "inside"
    assert ihlaller[0].takip_idler == [2]
