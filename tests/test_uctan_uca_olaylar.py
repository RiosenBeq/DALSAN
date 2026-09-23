"""Uçtan uca olay senaryoları (docs/17 §13 2e satırı, §14 ölçüm altyapısı).

Her senaryo `tests/fixtures/senaryolar/*.json` dosyasıdır: bölgeler, kurallar,
(varsa) kalibrasyon, nesnelerin zaman içindeki yolu ve BEKLENEN olaylar
(kod, önem, başlangıç, bitiş, bitiş sebebi; ± tolerans).

Test senaryodan sentetik bir mp4 yazar, kareleri çözüp gerçek boru hattından
geçirir: takip (ByteTrack) → kural motoru → olay yaşam döngüsü → süpervizörün
olay yazma yolu (veritabanı). Tespit modeli yerine senaryoyu okuyan sahte bir
dedektör kullanılır; model gerekmez, sonuç belirlenimcidir. Zaman karenin
zamanıdır (kare sırası / fps).

Sahadan gelen her yanlış alarm buraya bir senaryo olarak eklenir: aynı hata
ikinci kez gelmesin (regresyon).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytest

from app import veritabani, zaman
from app.analiz.boru_hatti import KameraHatti
from app.analiz.supervizor import AnalizSupervizoru
from app.rules.olay_durumu import ACILDI, KAPANDI
from app.rules.parametreler import params_dogrula
from app.rules.tipler import Bolge, Kalibrasyon, Kural

SENARYO_DIZINI = Path(__file__).parent / "fixtures" / "senaryolar"
SENARYOLAR = sorted(SENARYO_DIZINI.glob("*.json"))
KARE_BOYU = (320, 240)  # genişlik, yükseklik


@dataclass
class _Nesne:
    sinif: str
    yol: list[tuple[float, float, float]]  # (t, x, y): normalize ayak noktası
    boy: float  # kutu yüksekliği / kare yüksekliği
    en: float  # kutu genişliği / kare genişliği
    gorunmez: list[tuple[float, float]] = field(default_factory=list)

    def konum(self, t: float) -> tuple[float, float] | None:
        """t anındaki ayak noktası; nesne yoksa ya da örtülüyse None."""
        if t < self.yol[0][0] or t > self.yol[-1][0]:
            return None
        if any(bas <= t < son for bas, son in self.gorunmez):
            return None
        for (t0, x0, y0), (t1, x1, y1) in zip(self.yol, self.yol[1:], strict=False):
            if t0 <= t <= t1:
                oran = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                return x0 + (x1 - x0) * oran, y0 + (y1 - y0) * oran
        return self.yol[-1][1], self.yol[-1][2]

    def kutu(self, t: float) -> tuple[float, float, float, float] | None:
        konum = self.konum(t)
        if konum is None:
            return None
        genislik, yukseklik = KARE_BOYU
        x, y = konum[0] * genislik, konum[1] * yukseklik
        yari_en = self.en * genislik / 2
        return x - yari_en, y - self.boy * yukseklik, x + yari_en, y


class _SenaryoDedektoru:
    """Tespitci yerine: karenin zamanında görünen nesneleri kutu olarak verir."""

    def __init__(self, nesneler: list[_Nesne]) -> None:
        self.nesneler = nesneler
        self.zaman = 0.0

    def tespit_et(self, kare: np.ndarray):
        kutular, siniflar = [], []
        for nesne in self.nesneler:
            kutu = nesne.kutu(self.zaman)
            if kutu is not None:
                kutular.append(kutu)
                siniflar.append(nesne.sinif)
        return (
            np.array(kutular, dtype=float).reshape(-1, 4),
            np.full(len(kutular), 0.9),
            np.array(siniflar, dtype=object),
        )


class _SessizAnons:
    def golge_kaydet(self, *args, **kwargs) -> None:
        pass

    def ekran_kaydet(self, *args, **kwargs) -> None:
        pass

    def duyur(self, *args, **kwargs) -> None:
        pass

    def bolgeleri_yukle(self, satirlar) -> None:
        list(satirlar)


def _nesneler(senaryo: dict) -> list[_Nesne]:
    return [
        _Nesne(
            sinif=n["sinif"],
            yol=[tuple(nokta) for nokta in n["yol"]],
            boy=n["boy"],
            en=n["en"],
            gorunmez=[tuple(aralik) for aralik in n.get("gorunmez", [])],
        )
        for n in senaryo["nesneler"]
    ]


def _video_yaz(yol: Path, senaryo: dict, nesneler: list[_Nesne]) -> int:
    """Senaryonun görüntüsü: bölgeler çizgi, nesneler dolu kutu. Kayıt açılıp
    izlenince senaryonun ne anlattığı görülür."""
    fps = senaryo["fps"]
    genislik, yukseklik = KARE_BOYU
    yazici = cv2.VideoWriter(str(yol), cv2.VideoWriter_fourcc(*"mp4v"), fps, KARE_BOYU)
    kare_sayisi = int(senaryo["sure_s"] * fps)
    for i in range(kare_sayisi):
        kare = np.full((yukseklik, genislik, 3), 60, dtype=np.uint8)
        for bolge in senaryo["bolgeler"]:
            noktalar = np.array(
                [[x * genislik, y * yukseklik] for x, y in bolge["poligon"]], dtype=np.int32
            )
            cv2.polylines(kare, [noktalar], True, (0, 180, 255), 1)
        for nesne in nesneler:
            kutu = nesne.kutu(i / fps)
            if kutu is not None:
                x1, y1, x2, y2 = (int(v) for v in kutu)
                renk = (80, 220, 80) if nesne.sinif == "person" else (40, 90, 230)
                cv2.rectangle(kare, (x1, y1), (x2, y2), renk, -1)
        yazici.write(kare)
    yazici.release()
    return kare_sayisi


def _veritabanini_kur(baglanti, senaryo: dict) -> None:
    """Olay satırının yabancı anahtarları için kamera, bölge ve kural satırları."""
    simdi = zaman.simdi_utc()
    # Kamera KAPALI: süpervizör kendi okuma iş parçacığını açmasın; kareyi test verir
    baglanti.execute(
        "INSERT INTO cameras (id, name, area, source_type, source_url, enabled, sample_fps, "
        "created_at, updated_at) VALUES (1, 'Senaryo', '', 'file', 'senaryo.mp4', 0, ?, ?, ?)",
        (senaryo["fps"], simdi, simdi),
    )
    for bolge in senaryo["bolgeler"]:
        baglanti.execute(
            "INSERT INTO zones (id, camera_id, name, zone_type, polygon, updated_at) "
            "VALUES (?, 1, ?, ?, ?, ?)",
            (
                bolge["id"],
                f"Bölge {bolge['id']}",
                bolge["tip"],
                json.dumps(bolge["poligon"]),
                simdi,
            ),
        )
    for kural in senaryo["kurallar"]:
        baglanti.execute(
            "INSERT INTO rules (id, camera_id, rule_type, zone_id, target_classes, params, "
            "cooldown_s, enabled, updated_at) VALUES (?, 1, ?, ?, ?, ?, ?, 1, ?)",
            (
                kural["id"],
                kural["tip"],
                kural["bolge_id"],
                json.dumps(kural["hedefler"]),
                json.dumps(kural["params"]),
                kural["cooldown_s"],
                simdi,
            ),
        )
    baglanti.commit()


def _hat(senaryo: dict, takip_hafiza_sn: float) -> KameraHatti:
    hat = KameraHatti(1, senaryo["fps"], takip_hafiza_sn=takip_hafiza_sn)
    bolgeler = [
        Bolge(id=b["id"], tip=b["tip"], poligon=[tuple(n) for n in b["poligon"]])
        for b in senaryo["bolgeler"]
    ]
    kurallar = [
        Kural(
            id=k["id"],
            kamera_id=1,
            tip=k["tip"],
            bolge_id=k["bolge_id"],
            hedef_siniflar=k["hedefler"],
            params=params_dogrula(k["tip"], k["params"]),
            cooldown_s=float(k["cooldown_s"]),
        )
        for k in senaryo["kurallar"]
    ]
    kalibrasyon = (
        Kalibrasyon(homografi=senaryo["kalibrasyon"]) if senaryo.get("kalibrasyon") else None
    )
    hat.yapilandir(bolgeler, kurallar, kalibrasyon)
    return hat


def senaryoyu_oynat(
    senaryo: dict, ayarlar, dizin: Path, anons=None, hazirla=None
) -> tuple[list[dict], list[dict]]:
    """Senaryoyu oynatır: (geçişlerden olaylar, veritabanındaki olay satırları).

    `anons` verilirse (gerçek AnonsYoneticisi) uyarı hoparlör kanalına kadar
    gider; `hazirla(baglanti)` senaryo satırları yazıldıktan sonra çağrılır
    (kurala anons bağlamak, kanal eklemek).
    """
    nesneler = _nesneler(senaryo)
    video = dizin / "senaryo.mp4"
    beklenen_kare = _video_yaz(video, senaryo, nesneler)

    baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    _veritabanini_kur(baglanti, senaryo)
    if hazirla is not None:
        hazirla(baglanti)
    supervizor = AnalizSupervizoru(ayarlar)
    supervizor._anons = anons if anons is not None else _SessizAnons()
    if anons is not None:
        supervizor._anons_mesajlari = {
            s["id"]: dict(s) for s in baglanti.execute("SELECT * FROM announcement_messages")
        }
        anons.bolgeleri_yukle(baglanti.execute("SELECT * FROM speaker_zones ORDER BY id"))
    supervizor._kamera_konfig = {1: {"id": 1, "name": "Senaryo", "area": ""}}
    hat = _hat(senaryo, ayarlar.takip_hafiza_sn)
    dedektor = _SenaryoDedektoru(nesneler)

    olaylar: dict[tuple, dict] = {}
    an = [0.0]
    asil_gecisler = hat.gecisleri_al

    def kaydeden_gecisler():
        gecisler = asil_gecisler()
        for gecis in gecisler:
            if gecis.asama == ACILDI:
                olaylar[gecis.anahtar] = {
                    "kod": gecis.ihlal.kod,
                    "onem": gecis.ihlal.onem,
                    "baslangic_s": an[0],
                    "bitis_s": None,
                    "sebep": None,
                }
            elif gecis.asama == KAPANDI and gecis.anahtar in olaylar:
                olaylar[gecis.anahtar].update(bitis_s=gecis.son_aktif_s, sebep=gecis.sebep)
        return gecisler

    hat.gecisleri_al = kaydeden_gecisler
    okuyucu = cv2.VideoCapture(str(video))
    assert okuyucu.isOpened(), "sentetik mp4 açılamadı"
    kare_no = 0
    try:
        while True:
            tamam, kare = okuyucu.read()
            if not tamam:
                break
            an[0] = kare_no / senaryo["fps"]
            dedektor.zaman = an[0]
            hat.isle(kare, an[0], dedektor, supervizor.kkd)
            supervizor._gecisleri_isle(baglanti, hat, an[0])
            kare_no += 1
        assert kare_no == beklenen_kare, f"{kare_no}/{beklenen_kare} kare çözüldü"
        satirlar = [
            dict(s)
            for s in baglanti.execute(
                "SELECT event_code, severity, resolved_at FROM events "
                "WHERE event_type = 'violation' ORDER BY id"
            )
        ]
    finally:
        okuyucu.release()
        baglanti.close()
    return sorted(olaylar.values(), key=lambda o: o["baslangic_s"]), satirlar


@pytest.mark.parametrize("dosya", SENARYOLAR, ids=[d.stem for d in SENARYOLAR])
def test_senaryo(dosya: Path, test_ayarlari, tmp_path):
    senaryo = json.loads(dosya.read_text(encoding="utf-8"))
    bulunan, satirlar = senaryoyu_oynat(senaryo, test_ayarlari, tmp_path)
    beklenen = sorted(senaryo["beklenen"], key=lambda o: o["baslangic_s"])

    ozet = json.dumps(bulunan, ensure_ascii=False)
    assert len(bulunan) == len(beklenen), f"{senaryo['ad']}: olaylar {ozet}"
    for olay, bek in zip(bulunan, beklenen, strict=True):
        tolerans = bek.get("tolerans_s", 1.0)
        assert (olay["kod"], olay["onem"]) == (bek["kod"], bek["onem"]), ozet
        assert abs(olay["baslangic_s"] - bek["baslangic_s"]) <= tolerans, ozet
        if bek["bitis_s"] is None:
            assert olay["bitis_s"] is None, ozet
        else:
            assert olay["bitis_s"] is not None, f"olay bitmedi: {ozet}"
            assert abs(olay["bitis_s"] - bek["bitis_s"]) <= tolerans, ozet
        if "sebep" in bek:
            assert olay["sebep"] == bek["sebep"], ozet

    # Veritabanı: aynı olaylar, aynı kod ve önemle; biten olayın bitişi yazılı
    assert [(s["event_code"], s["severity"]) for s in satirlar] == [
        (b["kod"], b["onem"]) for b in beklenen
    ]
    assert [s["resolved_at"] is not None for s in satirlar] == [
        b["bitis_s"] is not None for b in beklenen
    ]


class _KayitliCalici:
    """Çalıcı süreci yerine: komutu kaydeder ve hemen başarıyla biter."""

    komutlar: list[list[str]] = []

    def __init__(self, komut, **_):
        _KayitliCalici.komutlar.append(list(komut))
        self.returncode = 0

    def communicate(self, timeout=None):
        return b"", b""


BT_HOPARLOR = "bluez_output.AA_BB_CC_DD_EE_FF.1"


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows'ta çalıcı süreci yok (winsound); sunucu Linux"
)
def test_forklift_yakinliginda_bagli_hoparlor_calar(test_ayarlari, tmp_path, monkeypatch):
    """Operatör isteği (23.09.2026): risk anında bağlı hoparlörden uyarı.

    Uçtan uca: forklift yayanın 2,4 m yanından geçer → güvenli mesafe kuralı
    (hazır kuralın anonsuyla) → olay satırı → GERÇEK AnonsYoneticisi →
    "Tüm fabrika" ses çıkışı kanalı (Bluetooth hoparlör) → çalıcı o hoparlörün
    adıyla başlar ve teslim kaydı olaya bağlı "ok" olur. Mesaja ses dosyası
    bağlanmamıştır (ilk kurulumdaki gibi): hoparlör susmaz, uyarı tonu çalar.
    Gerçek ses çalınmaz; çalıcı komutu kaydedilir.
    """
    from app.olaylar import anons as anons_modulu

    _KayitliCalici.komutlar = []
    monkeypatch.setattr(
        anons_modulu.shutil, "which", lambda ad: "/usr/bin/paplay" if ad == "paplay" else None
    )
    monkeypatch.setattr(anons_modulu.subprocess, "Popen", _KayitliCalici)

    def hazirla(baglanti):
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "UPDATE rules SET announcement_id = "
            "(SELECT id FROM announcement_messages WHERE key = 'safe_distance')"
        )
        baglanti.execute(
            "INSERT INTO speaker_zones (name, area, address, kind, device, enabled, "
            "created_at, updated_at) VALUES ('Tüm fabrika', '', '', 'ses_karti', ?, 1, ?, ?)",
            (BT_HOPARLOR, simdi, simdi),
        )
        baglanti.commit()

    senaryo = json.loads((SENARYO_DIZINI / "arac_yaya_yakinligi.json").read_text("utf-8"))
    yonetici = anons_modulu.AnonsYoneticisi(test_ayarlari)
    try:
        bulunan, _ = senaryoyu_oynat(senaryo, test_ayarlari, tmp_path, yonetici, hazirla)
        assert yonetici.bosalt()
    finally:
        yonetici.kapat(2.0)

    assert [o["kod"] for o in bulunan] == ["VEHICLE_PERSON_PROXIMITY"]
    # Tek olay, tek anons: çalıcı Bluetooth hoparlörün adıyla başladı
    assert len(_KayitliCalici.komutlar) == 1, _KayitliCalici.komutlar
    komut = _KayitliCalici.komutlar[0]
    assert komut[:2] == ["/usr/bin/paplay", f"--device={BT_HOPARLOR}"]
    assert komut[-1].endswith("nextgen-uyari-tonu.wav")

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        teslimler = [
            dict(s)
            for s in baglanti.execute(
                "SELECT d.*, e.event_code AS olay_kodu FROM alert_deliveries d "
                "JOIN events e ON e.id = d.event_id ORDER BY d.id"
            )
        ]
    finally:
        baglanti.close()
    # Ekran kanalı da yazılır (izleme penceresi yok: no_listener); garanti sayılmaz
    assert [(t["channel"], t["result"]) for t in teslimler] == [
        ("ekran", "no_listener"),
        ("ses_karti", "ok"),
    ], teslimler
    teslim = teslimler[1]
    assert teslim["stage"] == "acildi"
    assert teslim["olay_kodu"] == "VEHICLE_PERSON_PROXIMITY"
    assert "uyarı tonu" in teslim["detail"]


def test_her_senaryo_belgeli():
    """Senaryo dosyası ne anlattığını söylemeli: sahadan gelen hatanın kaydıdır."""
    assert SENARYOLAR, "senaryo yok"
    for dosya in SENARYOLAR:
        senaryo = json.loads(dosya.read_text(encoding="utf-8"))
        assert senaryo.get("ad") and senaryo.get("aciklama"), dosya.name
        assert "beklenen" in senaryo, dosya.name
