"""Şema 007 çevresi (docs/17 §4.3, §4.5, R19): yeni bölge tipleri ve anons damgası."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import veritabani, zaman
from app.analiz.supervizor import AnalizSupervizoru
from app.rules.tipler import BOLGE_TIPI_KODLARI, ISTISNA_BOLGE_TIPLERI
from app.uygulama import uygulama_olustur
from app.web.ortak import BOLGE_SIMGELERI, BOLGE_TIPLERI


def test_bolge_tipi_kodlarinin_tek_kaynagi_rules_katmani():
    """Veritabanında CHECK yok (007); rules/ app.web'i import edemediği için
    kodlar tipler.py'de, Türkçe adlar ortak.py'de. İkisi ayrışırsa bir tip
    ya çizilemez ya da kural katmanında bilinmez."""
    assert set(BOLGE_TIPLERI) == set(BOLGE_TIPI_KODLARI)
    assert set(BOLGE_SIMGELERI) == set(BOLGE_TIPI_KODLARI)
    assert {"crossing", "ppe_exempt"} == ISTISNA_BOLGE_TIPLERI


def _kamera(baglanti) -> int:
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, source_type, source_url, created_at, updated_at) "
        "VALUES (1, 'Rampa', 'rtsp', 'rtsp://x', ?, ?)",
        (simdi, simdi),
    )
    return 1


def test_yeni_bolge_tipleri_arayuzden_cizilebilir(istemci, test_ayarlari):
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "Rampa", "source_type": "rtsp", "source_url": "rtsp://10.0.0.5/1"},
        follow_redirects=False,
    )
    kamera = int(yanit.headers["location"].rsplit("/", 1)[1])
    for tip in ("crossing", "ppe_exempt"):
        istemci.post(
            f"/kameralar/{kamera}/bolgeler",
            data={"name": tip, "zone_type": tip, "polygon": "[[0.1,0.1],[0.9,0.1],[0.9,0.9]]"},
            follow_redirects=False,
        )
    sayfa = istemci.get(f"/kameralar/{kamera}").text
    assert "Yaya-araç geçidi" in sayfa and "KKD muaf alan" in sayfa
    # Uydurma tip hâlâ reddedilir (süzgeç artık kodda)
    yanit = istemci.post(
        f"/kameralar/{kamera}/bolgeler",
        data={"name": "x", "zone_type": "uydurma", "polygon": "[[0.1,0.1],[0.9,0.1],[0.9,0.9]]"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400


def test_supervizor_bilinmeyen_bolge_tipini_atlar(test_ayarlari):
    """CHECK'in yerini tutan ikinci ağ: elle yazılmış tip kurala girmez."""
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        kamera = _kamera(baglanti)
        for tip in ("restricted", "bilinmeyen_tip"):
            baglanti.execute(
                "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
                "VALUES (?, ?, ?, '[[0,0],[1,0],[1,1]]', ?)",
                (kamera, tip, tip, zaman.simdi_utc()),
            )
        baglanti.commit()
        bolgeler = AnalizSupervizoru(test_ayarlari)._bolgeleri_yukle(baglanti, kamera)
    finally:
        baglanti.close()
    assert [b.tip for b in bolgeler] == ["restricted"]


def test_anons_metni_degisince_calisan_sisteme_iner(test_ayarlari):
    """AUDIT R19: mesaj kaydı damgaya girmiyordu; yeni metin ancak yeniden
    başlatınca çalınıyordu."""
    with TestClient(uygulama_olustur(test_ayarlari, analiz=False)) as istemci:
        baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
        try:
            supervizor = AnalizSupervizoru(test_ayarlari)
            supervizor._konfigurasyonu_yenile(baglanti)
            ilk_damga = supervizor._konfig_damgasi
            istemci.post(
                "/anons/1/kaydet",
                data={"text": "Yeni metin.", "audio_file": "", "enabled": "1"},
                follow_redirects=False,
            )
            assert baglanti.execute(
                "SELECT updated_at FROM announcement_messages WHERE id = 1"
            ).fetchone()[0]
            supervizor._konfigurasyonu_yenile(baglanti)
        finally:
            baglanti.close()
    assert supervizor._konfig_damgasi != ilk_damga
    assert supervizor._anons_mesajlari[1]["text"] == "Yeni metin."
