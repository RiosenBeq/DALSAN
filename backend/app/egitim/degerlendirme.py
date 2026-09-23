"""KKD modelinin değerlendirmesi: veri seti + model → tek HTML rapor (docs/17 §5.9, docs/09 #7).

Depo kökünden:

    PYTHONPATH=backend .venv/bin/python -m app.egitim.degerlendirme dalsan-kkd-veri-seti.zip
    (seçenekler: --model models/kkd.onnx · --kume test · --min-guven 0.7 · --cikti rapor.html)

NE ÖLÇER: KKD sayfasından indirilen veri setinin TEST günlerindeki (varsayılan)
etiketli kırpıklarda modelin tahmini. Kalem başına var / yok / görünmüyor
karışıklık tablosu, "yok" için precision ve recall, belirsiz oranı, en kötü 50
hatanın görüntü ızgarası ve kamera / gün / zor örnek kırılımı. Operatör sayı
okumak yerine bakarak karar verir.

NE ÖLÇMEZ: sahadaki OLAY precision'ını. Sahada karar tek kareden değil zamansal
oylamadan çıkar (docs/04 §7.1); onu gölge karnesi ölçer (web/kkd_karnesi.py).

Model sahadaki yoldan yüklenir (`KkdSiniflandirici`): SHA256SUMS özeti ve ONNX
sözleşmesi denetlenir, tahmin aynı ön işlemeden geçer. Düşük güven, KKD
kuralındaki gibi belirsiz sayılır (`min_confidence`, rules/kkd.py).

Veri seti manifest'le doğrulanır: kullanılan her dosyanın sha256'sı manifest'teki
özetle aynı olmalı. Rapor tek dosyadır; görüntüler içine gömülür, dış bağlantı yok.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import io
import json
import sys
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app import kaynaklar, zaman
from app.egitim.veri_seti import KUMELER, MANIFEST_SURUMU, ZOR_ORNEKLER
from app.rules.parametreler import KkdParams
from app.rules.tipler import BELIRSIZ, VAR, YOK

KALEMLER = (("baret", "Baret"), ("yelek", "Yelek"))  # etiketler.csv sütunu, ekran adı
ETIKETLER = ("yes", "no", "unknown")
ETIKET_ADLARI = {"yes": "var", "no": "yok", "unknown": "görünmüyor"}
TAHMIN_ADLARI = {"yes": "var", "no": "yok", "unknown": "belirsiz"}
_SINIF_ETIKETI = {VAR: "yes", YOK: "no", BELIRSIZ: "unknown"}

# Hata türleri, en kötüden: yanlış "yok" sahada yanlış alarm demektir (docs/00:
# yanlış alarm kaçırılan ihlalden kötüdür); sonra kaçan ve belirsiz kalan "yok".
HATA_TURLERI = {
    "yanlis_yok": "Yanlış “yok” (yanlış alarm kaynağı)",
    "kacan_yok": "Kaçan “yok”",
    "belirsiz_yok": "“Yok” belirsiz kaldı",
}
EN_KOTU_ADET = 50
_TOPLU = 32  # sınıflandırıcıya tek çağrıda verilen kırpık


class DegerlendirmeHatasi(Exception):
    """Kullanıcıya olduğu gibi gösterilen Türkçe hata (dosya yok, özet tutmuyor…)."""


@dataclass(frozen=True)
class Kayit:
    """etiketler.csv'nin bir satırı (veri_seti.disa_aktar)."""

    dosya: str
    kume: str
    ornek_id: int
    kamera_id: str  # boş: kamerası silinmiş
    gun: str
    baret: str
    yelek: str
    zor: str  # boş: zor örnek değil


@dataclass(frozen=True)
class Tahmin:
    """Güven eşiği uygulanmış tahmin: yes | no | unknown ve modelin olasılığı."""

    baret: str
    yelek: str
    baret_guven: float
    yelek_guven: float


@dataclass(frozen=True)
class Oran:
    pay: int
    payda: int

    def metin(self, yuzde: bool = False) -> str:
        """AŞAĞI yuvarlanır: 0,899 "0,90" görünmesin. Payda yoksa ölçülemedi."""
        if not self.payda:
            return "ölçülemedi"
        binde = self.pay * 100 // self.payda
        return f"%{binde}" if yuzde else f"{binde // 100},{binde % 100:02d}"


# ------------------------------------------------------------------ saf hesap


def tahmin_etiketi(sinif: str, guven: float, min_guven: float) -> str:
    """Kuralın kararıyla aynı (rules/kkd.py): görünmüyor ya da güven eşiğin
    altındaysa belirsiz."""
    if sinif == BELIRSIZ or guven < min_guven:
        return "unknown"
    return _SINIF_ETIKETI[sinif]


def karisiklik(ciftler: Iterable[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """(etiket, tahmin) çiftlerinden 3×3 tablo: tablo[etiket][tahmin]."""
    tablo = {etiket: dict.fromkeys(ETIKETLER, 0) for etiket in ETIKETLER}
    for etiket, tahmin in ciftler:
        tablo[etiket][tahmin] += 1
    return tablo


def olcumler(tablo: dict[str, dict[str, int]]) -> dict[str, Oran]:
    """Precision ve recall ("yok" için) ve tahminlerin belirsiz oranı.

    Precision'ın paydası "yok" TAHMİNLERİDİR: etiketi "görünmüyor" olan bir
    kırpığa "yok" demek de yanlış alarmdır. Recall'un paydası "yok" ETİKETLERİDİR;
    belirsiz kalan "yok" da kaçmış sayılır (sahada olay üretmez).
    """
    return {
        "precision": Oran(tablo["no"]["no"], sum(tablo[e]["no"] for e in ETIKETLER)),
        "recall": Oran(tablo["no"]["no"], sum(tablo["no"].values())),
        "belirsiz": Oran(
            sum(tablo[e]["unknown"] for e in ETIKETLER),
            sum(sum(satir.values()) for satir in tablo.values()),
        ),
    }


def hata_turu(etiket: str, tahmin: str) -> str | None:
    if tahmin == "no" and etiket != "no":
        return "yanlis_yok"
    if etiket == "no" and tahmin == "yes":
        return "kacan_yok"
    if etiket == "no" and tahmin == "unknown":
        return "belirsiz_yok"
    return None  # doğru ya da zararsız ayrılık (ör. görünmüyor → var)


def en_kotuler(
    kayitlar: Sequence[Kayit], tahminler: Sequence[Tahmin], adet: int = EN_KOTU_ADET
) -> list[dict]:
    """Hatalar, en kötüden: önce tür (yanlış yok > kaçan > belirsiz), sonra
    modelin yanılırken ne kadar emin olduğu."""
    hatalar = []
    for kayit, tahmin in zip(kayitlar, tahminler, strict=True):
        for alan, ad in KALEMLER:
            tur = hata_turu(getattr(kayit, alan), getattr(tahmin, alan))
            if tur:
                hatalar.append(
                    {
                        "kayit": kayit,
                        "kalem": ad,
                        "etiket": getattr(kayit, alan),
                        "tahmin": getattr(tahmin, alan),
                        "guven": getattr(tahmin, f"{alan}_guven"),
                        "tur": tur,
                    }
                )
    sira = list(HATA_TURLERI)
    hatalar.sort(key=lambda h: (sira.index(h["tur"]), -h["guven"], h["kayit"].ornek_id))
    return hatalar[:adet]


def kirilim(
    kayitlar: Sequence[Kayit], tahminler: Sequence[Tahmin], anahtar: Callable[[Kayit], str]
) -> list[dict]:
    """Grup başına örnek sayısı; kalem başına yanlış "yok", kaçan "yok"
    (belirsiz kalanlar dahil) ve belirsiz oranı. Gruplar ada göre sıralı."""
    gruplar: dict[str, list[tuple[Kayit, Tahmin]]] = defaultdict(list)
    for kayit, tahmin in zip(kayitlar, tahminler, strict=True):
        gruplar[anahtar(kayit)].append((kayit, tahmin))
    satirlar = []
    for ad in sorted(gruplar):
        uyeler = gruplar[ad]
        satir = {"ad": ad, "adet": len(uyeler), "kalemler": {}}
        for alan, _ in KALEMLER:
            turler = [hata_turu(getattr(k, alan), getattr(t, alan)) for k, t in uyeler]
            satir["kalemler"][alan] = {
                "yanlis_yok": turler.count("yanlis_yok"),
                "kacan_yok": turler.count("kacan_yok") + turler.count("belirsiz_yok"),
                "belirsiz": Oran(
                    sum(1 for _, t in uyeler if getattr(t, alan) == "unknown"), len(uyeler)
                ),
            }
        satirlar.append(satir)
    return satirlar


def degerlendir(kayitlar: Sequence[Kayit], tahminler: Sequence[Tahmin]) -> dict:
    """Raporun bütün sayıları. Sahte tahminlerle de çağrılabilir (testler)."""
    kalemler = {}
    for alan, ad in KALEMLER:
        tablo = karisiklik(
            (getattr(k, alan), getattr(t, alan)) for k, t in zip(kayitlar, tahminler, strict=True)
        )
        kalemler[alan] = {"ad": ad, "tablo": tablo, "olcum": olcumler(tablo)}
    return {
        "adet": len(kayitlar),
        "kalemler": kalemler,
        "en_kotuler": en_kotuler(kayitlar, tahminler),
        "hata_sayilari": {
            tur: sum(
                1
                for k, t in zip(kayitlar, tahminler, strict=True)
                for alan, _ in KALEMLER
                if hata_turu(getattr(k, alan), getattr(t, alan)) == tur
            )
            for tur in HATA_TURLERI
        },
        "kirilimlar": [
            ("Kameraya göre", kirilim(kayitlar, tahminler, _kamera_adi)),
            ("Güne göre", kirilim(kayitlar, tahminler, lambda k: k.gun)),
            ("Zor örneğe göre", kirilim(kayitlar, tahminler, _zor_adi)),
        ],
    }


def _kamera_adi(kayit: Kayit) -> str:
    # Veri setinde kamera ADI yoktur (KVKK, veri_seti.py); numara yeter
    return f"Kamera {kayit.kamera_id}" if kayit.kamera_id else "Kamerası silinmiş"


def _zor_adi(kayit: Kayit) -> str:
    return ZOR_ORNEKLER.get(kayit.zor, kayit.zor) if kayit.zor else "Zor örnek değil"


# ------------------------------------------------------------------ veri seti


class VeriSeti:
    """Dışa aktarılmış zip. Okunan her dosya manifest'teki sha256 ile denetlenir."""

    def __init__(self, yol: Path, kume: str) -> None:
        try:
            self._arsiv = zipfile.ZipFile(yol)
        except FileNotFoundError:
            raise DegerlendirmeHatasi(f"Veri seti bulunamadı: {yol}") from None
        except zipfile.BadZipFile:
            raise DegerlendirmeHatasi(f"Veri seti zip değil ya da bozuk: {yol}") from None
        try:
            self._yukle(kume)
        except BaseException:
            self.kapat()
            raise

    def _yukle(self, kume: str) -> None:
        self.manifest = {}
        try:
            self.manifest = json.loads(self._oku("manifest.json", dogrula=False))
        except json.JSONDecodeError:
            raise DegerlendirmeHatasi("Veri setinin manifest.json dosyası okunamadı.") from None
        if self.manifest.get("surum") != MANIFEST_SURUMU:
            raise DegerlendirmeHatasi(
                f"Veri setinin manifest sürümü {self.manifest.get('surum')!r}; bu program "
                f"{MANIFEST_SURUMU}. sürümü okur. Veri setini KKD sayfasından yeniden indirin."
            )
        metin = self._oku("etiketler.csv").decode("utf-8")
        try:
            tum = [
                Kayit(
                    dosya=satir["dosya"],
                    kume=satir["kume"],
                    ornek_id=int(satir["ornek_id"]),
                    kamera_id=satir["kamera_id"],
                    gun=satir["gun"],
                    baret=satir["baret"],
                    yelek=satir["yelek"],
                    zor=satir["zor_ornek"],
                )
                for satir in csv.DictReader(io.StringIO(metin))
            ]
        except (KeyError, ValueError):
            raise DegerlendirmeHatasi(
                "etiketler.csv beklenen sütunları taşımıyor. Veri setini KKD sayfasından "
                "yeniden indirin."
            ) from None
        tanimsiz = {k.baret for k in tum} | {k.yelek for k in tum}
        if tanimsiz - set(ETIKETLER):
            raise DegerlendirmeHatasi(
                f"etiketler.csv'de tanınmayan etiket: {sorted(tanimsiz - set(ETIKETLER))}"
            )
        self.kume = kume
        self.kayitlar = tum if kume == "tum" else [k for k in tum if k.kume == kume]

    def _oku(self, ad: str, dogrula: bool = True) -> bytes:
        try:
            veri = self._arsiv.read(ad)
        except KeyError:
            raise DegerlendirmeHatasi(f"Veri setinde {ad} yok.") from None
        if dogrula:
            beklenen = self.manifest.get("dosyalar", {}).get(ad)
            if beklenen is None or hashlib.sha256(veri).hexdigest() != beklenen:
                raise DegerlendirmeHatasi(
                    f"Veri seti bozuk: {ad} manifest'teki sha256 özetiyle aynı değil. "
                    "Veri setini KKD sayfasından yeniden indirin."
                )
        return veri

    def goruntu(self, kayit: Kayit) -> bytes:
        return self._oku(kayit.dosya)

    def kapat(self) -> None:
        self._arsiv.close()

    def __enter__(self) -> VeriSeti:
        return self

    def __exit__(self, *_) -> None:
        self.kapat()


def tahmin_et(siniflandirici, veri_seti: VeriSeti, min_guven: float) -> list[Tahmin]:
    """Kırpıklar sahadaki yoldan değerlendirilir (degerlendir_toplu); güven
    eşiği kuraldaki gibi uygulanır. Görüntüler parça parça okunur."""
    import cv2

    from app.analiz.kkd_siniflandirici import CROP_BOYUT

    tahminler: list[Tahmin] = []
    kayitlar = veri_seti.kayitlar
    for bas in range(0, len(kayitlar), _TOPLU):
        kirpiklar = []
        for kayit in kayitlar[bas : bas + _TOPLU]:
            kirpik = cv2.imdecode(
                np.frombuffer(veri_seti.goruntu(kayit), np.uint8), cv2.IMREAD_COLOR
            )
            if kirpik is None:
                raise DegerlendirmeHatasi(f"Kırpık görüntü olarak açılamadı: {kayit.dosya}")
            if kirpik.shape[:2] != (CROP_BOYUT[1], CROP_BOYUT[0]):
                kirpik = cv2.resize(kirpik, CROP_BOYUT, interpolation=cv2.INTER_LINEAR)
            kirpiklar.append(kirpik)
        for gozlem in siniflandirici.degerlendir_toplu(kirpiklar):
            tahminler.append(
                Tahmin(
                    baret=tahmin_etiketi(gozlem.baret, gozlem.baret_guven, min_guven),
                    yelek=tahmin_etiketi(gozlem.yelek, gozlem.yelek_guven, min_guven),
                    baret_guven=gozlem.baret_guven,
                    yelek_guven=gozlem.yelek_guven,
                )
            )
    return tahminler


# ------------------------------------------------------------------ HTML


_STIL = """
:root { --metin:#15171c; --metin-2:#454b58; --metin-3:#5f6675; --cizgi:#d9dee8;
  --basari:#166534; --basari-z:#dcfce7; --tehlike:#b91c1c; --tehlike-z:#fee2e2;
  --uyari:#92400e; --uyari-z:#fef3c7; --gri-z:#eef1f6; --vurgu:#1d4ed8; }
* { box-sizing: border-box; }
body { margin: 0; background: #f6f7fa; color: var(--metin);
  font: 14px/1.5 "Inter", "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif; }
main { max-width: 1120px; margin: 0 auto; padding: 28px 20px 48px; display: grid; gap: 22px;
  grid-template-columns: minmax(0, 1fr); }
h1 { margin: 0; font-size: 22px; letter-spacing: -0.02em; }
h2 { margin: 0 0 12px; font-size: 17px; }
h3 { margin: 0 0 8px; font-size: 14px; color: var(--metin-2); }
p { margin: 0 0 8px; }
.kunye { color: var(--metin-3); font-size: 12.5px; }
.kart { background: #fff; border: 1px solid var(--cizgi); border-radius: 12px; padding: 18px 20px; }
.uyari { background: var(--uyari-z); color: var(--uyari); border-color: #fcd34d; font-weight: 600; }
.not { color: var(--metin-2); font-size: 12.5px; }
.kalemler { display: grid; gap: 22px;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); }
.sayilar { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px;
  margin-bottom: 14px; }
.sayi { background: var(--gri-z); border-radius: 10px; padding: 10px 12px; }
.sayi span { display: block; font-size: 11.5px; color: var(--metin-3); }
.sayi b { font-size: 22px; font-variant-numeric: tabular-nums; }
.sayi small { display: block; color: var(--metin-3); font-size: 11.5px; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--cizgi); text-align: right; }
th.sol, td.sol { text-align: left; }  /* yalnız ilk sütun: rowspan'lı başlık kaymasın */
th { color: var(--metin-3); font-weight: 600; font-size: 12px; }
td.dogru { background: var(--basari-z); color: var(--basari); font-weight: 700; }
td.yanlis-yok { background: var(--tehlike-z); color: var(--tehlike); font-weight: 700; }
td.kacan { background: var(--uyari-z); color: var(--uyari); font-weight: 700; }
td.belirsiz { color: var(--metin-3); }
.izgara { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(148px, 1fr)); }
.hata { background: #fff; border: 1px solid var(--cizgi); border-radius: 10px; padding: 8px;
  display: grid; gap: 4px; font-size: 12px; break-inside: avoid; }
.hata img { width: 100%; aspect-ratio: 1 / 2; object-fit: contain; background: var(--gri-z);
  border-radius: 6px; }
.hata .tur { font-weight: 700; }
.hata.yanlis_yok .tur { color: var(--tehlike); }
.hata.kacan_yok .tur, .hata.belirsiz_yok .tur { color: var(--uyari); }
.hata small { color: var(--metin-3); }
.kirilimlar { display: grid; gap: 22px; grid-template-columns: minmax(0, 1fr); }
.tablo-kaydir { overflow-x: auto; }
@media print { body { background: #fff; } .kart { break-inside: avoid; } }
"""


def _e(deger) -> str:
    return html.escape(str(deger))


def _ondalik(deger: float) -> str:
    return f"{deger:.2f}".replace(".", ",")


def _sayi_karti(baslik: str, oran: Oran, bos: str, yuzde: bool = False) -> str:
    alt = f"{oran.pay} / {oran.payda}" if oran.payda else bos
    return (
        f'<div class="sayi"><span>{_e(baslik)}</span><b>{_e(oran.metin(yuzde))}</b>'
        f"<small>{_e(alt)}</small></div>"
    )


def _hucre_sinifi(etiket: str, tahmin: str, adet: int) -> str:
    """Hücre rengi; sıfır hücre boyanmaz, göz yalnız gerçekten olana gitsin."""
    if not adet:
        return ""
    if etiket == tahmin:
        return "dogru"
    tur = hata_turu(etiket, tahmin)
    if tur == "yanlis_yok":
        return "yanlis-yok"
    if tur in ("kacan_yok", "belirsiz_yok"):
        return "kacan"
    return "belirsiz" if tahmin == "unknown" else ""


def _kalem_bolumu(kalem: dict) -> str:
    olcum = kalem["olcum"]
    satirlar = []
    for etiket in ETIKETLER:
        hucreler = "".join(
            f'<td class="{_hucre_sinifi(etiket, tahmin, adet)}">{adet}</td>'
            for tahmin, adet in kalem["tablo"][etiket].items()
        )
        toplam = sum(kalem["tablo"][etiket].values())
        satirlar.append(
            f"<tr><td class='sol'>{_e(ETIKET_ADLARI[etiket])}</td>{hucreler}<td>{toplam}</td></tr>"
        )
    basliklar = "".join(f"<th>{_e(TAHMIN_ADLARI[t])}</th>" for t in ETIKETLER)
    return (
        f'<section class="kart"><h2>{_e(kalem["ad"])}</h2><div class="sayilar">'
        + _sayi_karti("“Yok” precision", olcum["precision"], "model hiç “yok” demedi")
        + _sayi_karti("“Yok” recall", olcum["recall"], "“yok” etiketli örnek yok")
        + _sayi_karti("Belirsiz", olcum["belirsiz"], "örnek yok", yuzde=True)
        + "</div><h3>Karışıklık tablosu (satır: etiket, sütun: tahmin)</h3>"
        f"<div class='tablo-kaydir'><table><tr><th class='sol'>Etiket \\ Tahmin</th>{basliklar}"
        "<th>Toplam</th></tr>" + "".join(satirlar) + "</table></div></section>"
    )


def _hata_karti(hata: dict, goruntu: bytes) -> str:
    kayit: Kayit = hata["kayit"]
    veri = base64.b64encode(goruntu).decode("ascii")
    zor = f" · {_e(_zor_adi(kayit))}" if kayit.zor else ""
    return (
        f'<figure class="hata {hata["tur"]}" style="margin:0">'
        f'<img src="data:image/jpeg;base64,{veri}" alt="örnek {kayit.ornek_id}">'
        f'<span class="tur">{_e(hata["kalem"])}: {_e(ETIKET_ADLARI[hata["etiket"]])} → '
        f"{_e(TAHMIN_ADLARI[hata['tahmin']])}</span>"
        f"<span>modelin güveni {_e(_ondalik(hata['guven']))}</span>"
        f"<small>örnek {kayit.ornek_id} · {_e(_kamera_adi(kayit))} · {_e(kayit.gun)}{zor}</small>"
        "</figure>"
    )


def _kirilim_tablosu(baslik: str, satirlar: list[dict]) -> str:
    ust = "".join(f'<th colspan="3" style="text-align:center">{_e(ad)}</th>' for _, ad in KALEMLER)
    alt = "<th>yanlış “yok”</th><th>kaçan “yok”</th><th>belirsiz</th>" * len(KALEMLER)
    govde = []
    for satir in satirlar:
        hucreler = "".join(
            f"<td>{s['yanlis_yok']}</td><td>{s['kacan_yok']}</td>"
            f"<td>{_e(s['belirsiz'].metin(yuzde=True))}</td>"
            for s in (satir["kalemler"][alan] for alan, _ in KALEMLER)
        )
        govde.append(
            f"<tr><td class='sol'>{_e(satir['ad'])}</td><td>{satir['adet']}</td>{hucreler}</tr>"
        )
    return (
        f'<div><h3>{_e(baslik)}</h3><div class="tablo-kaydir"><table>'
        f'<tr><th rowspan="2" class="sol"></th><th rowspan="2">örnek</th>{ust}</tr><tr>{alt}</tr>'
        + "".join(govde)
        + "</table></div></div>"
    )


def html_raporu(
    sonuc: dict,
    *,
    model_surumu: str,
    model_karti: dict,
    manifest: dict,
    kume: str,
    min_guven: float,
    goruntu_oku: Callable[[Kayit], bytes],
) -> str:
    """Tek, kendi içinde yeterli HTML: stil ve görüntüler gömülü."""
    kume_adi = {"train": "eğitim", "val": "doğrulama", "test": "test", "tum": "tüm"}[kume]
    olusturma = manifest.get("olusturma_utc")
    veri_seti_tarihi = zaman.ekranda_goster(olusturma) if olusturma else "—"
    gunler = sorted({s["ad"] for s in dict(sonuc["kirilimlar"])["Güne göre"]})
    donem = f"{gunler[0]} – {gunler[-1]}" if gunler else "—"
    uyarilar = list(manifest.get("uyarilar") or [])
    if kume != "test":
        uyarilar.append(
            f"Bu rapor {kume_adi} kümesinden. Modelin başarısını yalnız görmediği TEST günleri "
            "söyler; eğitim günlerindeki sayı ezberi ölçer (docs/04 §5.4)."
        )
    kart_satirlari = "".join(
        f"<tr><td class='sol'>{_e(anahtar)}</td><td class='sol'>{_e(deger)}</td></tr>"
        for anahtar, deger in model_karti.items()
    )
    hata_sayilari = " · ".join(
        f"{_e(ad)}: <b>{sonuc['hata_sayilari'][tur]}</b>" for tur, ad in HATA_TURLERI.items()
    )
    kartlar = "".join(_hata_karti(h, goruntu_oku(h["kayit"])) for h in sonuc["en_kotuler"])
    parcalar = [
        "<!doctype html><html lang='tr'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>KKD model değerlendirmesi — {_e(model_surumu)}</title>",
        f"<style>{_STIL}</style></head><body><main>",
        "<header class='kart'>",
        f"<h1>KKD model değerlendirmesi — {_e(model_surumu)}</h1>",
        f"<p class='kunye'>Veri seti: {_e(kume_adi)} kümesi, <b>{sonuc['adet']}</b> etiketli "
        f"kırpık, {len(gunler)} gün ({_e(donem)}) · veri seti {_e(veri_seti_tarihi)} · "
        f"güven eşiği {_e(_ondalik(min_guven))} "
        "(altı belirsiz sayılır, KKD kuralındaki gibi) · rapor "
        f"{_e(zaman.ekranda_goster(zaman.simdi_utc()))}</p>",
        "<p class='not'>Bu rapor tek tek kırpıkları ölçer. Sahadaki olay precision'ı zamansal "
        "oylamadan sonra gölge karnesinde ölçülür (KKD sayfası; docs/17 §5.7). Metrikler "
        "yalnız sahadan toplanan veriyle ölçülür; bu dosyadaki sayı başka yere taşınmaz.</p>",
        "</header>",
    ]
    parcalar += [f"<p class='kart uyari'>{_e(u)}</p>" for u in uyarilar]
    parcalar.append("<div class='kalemler'>")
    parcalar += [_kalem_bolumu(k) for k in sonuc["kalemler"].values()]
    parcalar.append("</div>")
    parcalar.append(
        f"<section class='kart'><h2>En kötü {len(sonuc['en_kotuler'])} hata</h2>"
        f"<p class='not'>{hata_sayilari}. Sıra: önce yanlış “yok” (sahada yanlış alarm "
        "demektir), sonra kaçan ve belirsiz kalan “yok”; her türün içinde modelin en emin "
        "olduğu hata önce.</p>"
        + (f"<div class='izgara'>{kartlar}</div>" if kartlar else "<p>Hata yok.</p>")
        + "</section>"
    )
    parcalar.append(
        "<section class='kart kirilimlar'><div><h2>Kırılımlar</h2><p class='not'>Kaçan “yok” "
        "sayısına belirsiz kalan “yok” da girer: sahada ikisi de olay üretmez.</p></div>"
    )
    parcalar += [_kirilim_tablosu(b, s) for b, s in sonuc["kirilimlar"]]
    parcalar.append("</section>")
    if kart_satirlari:
        parcalar.append(
            f"<section class='kart'><h2>Model kartı</h2><table>{kart_satirlari}</table></section>"
        )
    parcalar.append(
        "<p class='kunye'>DALSAN İSG · app/egitim/degerlendirme.py · docs/17 §5.9</p>"
        "</main></body></html>"
    )
    return "".join(parcalar)


# ------------------------------------------------------------------ komut


def degerlendir_zip(
    zip_yolu: Path,
    model_yolu: Path,
    *,
    kume: str = "test",
    min_guven: float | None = None,
    cikti: Path | None = None,
    oturum_kur: Callable | None = None,
) -> tuple[Path, dict, str]:
    """Veri setini ve modeli okur, raporu yazar: (rapor yolu, sonuç, model sürümü).

    Önce veri seti doğrulanır (yol, zip, manifest, küme boş mu): en sık yapılan
    hata yanlış dosyayı vermektir ve modeli açmadan söylenebilir.
    """
    from app.analiz.kkd_siniflandirici import KkdSiniflandirici

    esik = KkdParams().min_confidence if min_guven is None else min_guven
    if not 0 <= esik <= 1:
        raise DegerlendirmeHatasi(f"Güven eşiği 0 ile 1 arasında olmalı: {esik}")
    with VeriSeti(zip_yolu, kume) as veri_seti:
        if not veri_seti.kayitlar:
            raise DegerlendirmeHatasi(
                f"Veri setinin {kume} kümesinde örnek yok. Test günleri için en az üç ayrı "
                "günün etiketli örneği gerekir (docs/04 §5.4)."
            )
        ek = {} if oturum_kur is None else {"oturum_kur": oturum_kur}
        siniflandirici = KkdSiniflandirici(model_yolu, **ek)  # özet, sözleşme: ModelHatasi
        if not siniflandirici.model_var:
            raise DegerlendirmeHatasi(f"KKD modeli bulunamadı: {model_yolu}")
        tahminler = tahmin_et(siniflandirici, veri_seti, esik)
        sonuc = degerlendir(veri_seti.kayitlar, tahminler)
        metin = html_raporu(
            sonuc,
            model_surumu=siniflandirici.model_surumu,
            model_karti=siniflandirici.kart,
            manifest=veri_seti.manifest,
            kume=kume,
            min_guven=esik,
            goruntu_oku=veri_seti.goruntu,
        )
    hedef = cikti or zip_yolu.with_name(
        f"kkd-degerlendirme-{siniflandirici.model_surumu}-{kume}.html"
    )
    hedef.write_text(metin, encoding="utf-8")
    return hedef, sonuc, siniflandirici.model_surumu


def main(argv: list[str] | None = None) -> int:
    from app.analiz.tespit import ModelHatasi

    ayristirici = argparse.ArgumentParser(
        prog="python -m app.egitim.degerlendirme",
        description="KKD modelini veri setinin test günlerinde değerlendirir ve tek HTML "
        "rapor yazar (docs/17 §5.9).",
    )
    ayristirici.add_argument("veri_seti", type=Path, help="KKD sayfasından indirilen .zip")
    ayristirici.add_argument(
        "--model",
        type=Path,
        # Uygulamanın modeli aradığı yer (ayarlar.py: yazılabilir kök / models)
        default=kaynaklar.veri_konumu().kok / "models" / "kkd.onnx",
        help="değerlendirilecek model; özeti aynı klasördeki SHA256SUMS'ta olmalı",
    )
    ayristirici.add_argument("--kume", choices=(*KUMELER, "tum"), default="test")
    ayristirici.add_argument(
        "--min-guven",
        type=float,
        default=None,
        help="bu olasılığın altı belirsiz sayılır (varsayılan: KKD kuralınınki, 0.7)",
    )
    ayristirici.add_argument("--cikti", type=Path, default=None, help="rapor dosyası (.html)")
    secenek = ayristirici.parse_args(argv)
    try:
        hedef, sonuc, surum = degerlendir_zip(
            secenek.veri_seti,
            secenek.model,
            kume=secenek.kume,
            min_guven=secenek.min_guven,
            cikti=secenek.cikti,
        )
    except DegerlendirmeHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 2
    except ModelHatasi as hata:
        print(f"HATA: {hata.kullanici_mesaji}\n  {hata.teknik_ayrinti}", file=sys.stderr)
        return 2
    print(f"Rapor yazıldı: {hedef}")
    print(f"Model {surum} · {secenek.kume} kümesi · {sonuc['adet']} kırpık")
    for kalem in sonuc["kalemler"].values():
        olcum = kalem["olcum"]
        print(
            f"  {kalem['ad']}: “yok” precision {olcum['precision'].metin()}, "
            f"recall {olcum['recall'].metin()}, belirsiz {olcum['belirsiz'].metin(yuzde=True)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
