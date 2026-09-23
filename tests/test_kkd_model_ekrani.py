"""KKD modelinin ekrandaki izi: KKD sayfasının model kartı ve önizlemede
kişi kutusunun rengi (docs/17 §5.10; Faz 3c).

- KKD sayfası modelin durumunu yazar: doğrulandı (sürümüyle), yüklü değil,
  yüklenemedi (sebebiyle) ya da analiz kapalı.
- Karedeki kişiler sınıflandırıcıya tek çağrıda verilir; son gözlem yalnız
  çizim için tutulur (kutu rengi kadans karelerinde titremez).
- Kutu rengi yalnız kuralın istediği kalemlere bakar.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.analiz.boru_hatti import KameraHatti
from app.analiz.kkd_siniflandirici import KkdSiniflandirici
from app.rules.parametreler import varsayilan_params
from app.rules.tipler import BELIRSIZ, VAR, YOK, Bolge, KkdGozlem, Kural, Tespit

# ------------------------------------------------------------------ KKD sayfası


@pytest.mark.parametrize(
    ("supervizor", "parca", "sinif"),
    [
        (None, "Analiz çalışmıyor", "bilinmiyor"),
        (
            SimpleNamespace(kkd=KkdSiniflandirici(None), kkd_hatasi=None),
            "Model yüklü değil: KKD kuralı olay üretmez",
            "yok",
        ),
        (
            SimpleNamespace(kkd=KkdSiniflandirici(None), kkd_hatasi="KKD modeli yüklenmedi: x"),
            "KKD modeli yüklenmedi: x",
            "hata",
        ),
        (
            SimpleNamespace(
                kkd=SimpleNamespace(
                    model_var=True, model_surumu="kkd-abc123", kart={"egitim_tarihi": "2026-10"}
                ),
                kkd_hatasi=None,
            ),
            "Model: kkd-abc123, doğrulandı",
            "hazir",
        ),
    ],
)
def test_kkd_sayfasi_model_durumunu_yazar(istemci, supervizor, parca, sinif):
    istemci.app.state.supervizor = supervizor
    try:
        metin = istemci.get("/kkd").text
    finally:
        istemci.app.state.supervizor = None
    assert parca in metin
    assert f'class="kart kkd-model {sinif}"' in metin
    if sinif == "hazir":
        assert "egitim_tarihi" in metin


# ------------------------------------------------------------------ boru hattı


class _SayanKkd:
    model_var = True

    def __init__(self, gozlem: KkdGozlem):
        self.gozlem = gozlem
        self.cagrilar: list[int] = []

    def degerlendir_toplu(self, kirpiklar):
        self.cagrilar.append(len(kirpiklar))
        return [self.gozlem] * len(kirpiklar)


def _hat(kalemler=("helmet", "vest")) -> KameraHatti:
    hat = KameraHatti(1, 6)
    kural = Kural(
        id=1,
        kamera_id=1,
        tip="ppe_violation",
        bolge_id=1,
        hedef_siniflar=["person"],
        params={**varsayilan_params("ppe_violation"), "required_ppe": list(kalemler)},
        cooldown_s=180.0,
    )
    hat.yapilandir(
        [Bolge(id=1, tip="ppe_required", poligon=[(0, 0), (1, 0), (1, 1), (0, 1)])], [kural], None
    )
    return hat


def _kisi(takip_id: int, x: float) -> Tespit:
    return Tespit(sinif="person", kutu=(x, 200.0, x + 100, 700.0), takip_id=takip_id, guven=0.9)


def test_karedeki_kisiler_tek_cagrida():
    hat = _hat()
    kkd = _SayanKkd(KkdGozlem(baret=VAR, yelek=VAR))
    kare = np.full((1000, 1000, 3), 90, dtype=np.uint8)
    kisiler = [_kisi(1, 100), _kisi(2, 400), _kisi(3, 700)]
    hat._kkd_degerlendir(kare, kisiler, (1000.0, 1000.0), kkd)
    assert kkd.cagrilar == [3]
    assert all(k.kkd_gozlemi is kkd.gozlem for k in kisiler)
    # Kadans: sonraki karede gözlem yok, çizim için son gözlem durur
    kisiler = [_kisi(1, 100), _kisi(2, 400), _kisi(3, 700)]
    hat._kkd_degerlendir(kare, kisiler, (1000.0, 1000.0), kkd)
    assert kkd.cagrilar == [3, 0]
    assert all(k.kkd_gozlemi is None for k in kisiler)
    assert set(hat._kkd_son) == {1, 2, 3}


@pytest.mark.parametrize(
    ("kalemler", "baret", "yelek", "renk"),
    [
        (("helmet", "vest"), VAR, VAR, "yesil"),
        (("helmet", "vest"), VAR, YOK, "kirmizi"),
        (("helmet", "vest"), VAR, BELIRSIZ, "gri"),
        (("helmet",), VAR, YOK, "yesil"),  # yelek istemeyen kural: yeleksiz kişi kırmızı değil
        (("helmet",), BELIRSIZ, YOK, "gri"),
    ],
)
def test_kisi_kutusu_rengi_kuralin_kalemlerine_gore(kalemler, baret, yelek, renk):
    from app.analiz import boru_hatti

    beklenen = {
        "yesil": boru_hatti._RENKLER["person"],
        "kirmizi": boru_hatti._KKD_YOK_RENGI,
        "gri": boru_hatti._KKD_BELIRSIZ_RENGI,
    }[renk]
    assert _hat(kalemler)._kkd_kutu_rengi(KkdGozlem(baret=baret, yelek=yelek)) == beklenen
