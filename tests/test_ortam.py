"""Yanlış OpenCV sürümü SESSİZ kalmıyor (analiz/ortam.py).

Bu GERÇEKTEN yaşandı ve bulunması saatler aldı: bir makinede
`opencv-python 5.0.0`, requirements.txt'in sabitlediği 4.10'u gölgeledi.
Sistem açıldı, kameralar bağlandı, tespit çalıştı, tek bir hata satırı çıkmadı
- ama nesne kütüphanesi 36 sorgunun hiçbirini bulamadı. Yani "tanıttığım nesne
neden bulunmuyor" sorusunun cevabı hiçbir yerde yazmıyordu.

Burada korunan şey uyarının KENDİSİ değil, sessizliğin bir daha olmaması.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.analiz import ortam

KOK = Path(__file__).resolve().parents[1]
GEREKSINIMLER = KOK / "backend" / "requirements.txt"


def test_dogru_surumde_uyari_yok():
    """Olağan kurulumda ekranda ve günlükte hiçbir şey görünmemeli."""
    assert ortam.opencv_uyarisi("4.10.0.84") == ""
    assert ortam.opencv_uyarisi("4.12.0") == ""


@pytest.mark.parametrize("surum", ["5.0.0.93", "5.1.0", "3.4.18"])
def test_yanlis_ana_surumde_uyari_var(surum):
    uyari = ortam.opencv_uyarisi(surum)
    assert uyari, f"{surum} için uyarı üretilmedi"
    assert surum in uyari, "kullanıcı hangi sürümün kurulu olduğunu görmeli"
    # Uyarı NE YAPILACAĞINI söylemeli, yalnız sorunu değil (CLAUDE.md §8).
    assert "İlk Kurulumu Yap" in uyari


def test_uyari_sistemin_calistigini_da_soyluyor():
    """Sürüm farkı bir UYARIDIR, arıza değil.

    "Görüntü kütüphaneniz yanlış" cümlesini tek başına okuyan kullanıcı,
    güvenlik sisteminin tamamen durduğunu sanıp paniğe kapılırdı; oysa bölge
    ihlali, güvenli mesafe ve KKD kuralları çalışmaya devam eder.
    """
    uyari = ortam.opencv_uyarisi("5.0.0")
    assert "çalışır" in uyari
    assert "Nesneler" in uyari, "hangi özelliğin etkilendiği yazmalı"


@pytest.mark.parametrize("bozuk", ["", "bilinmeyen", "sürüm-yok"])
def test_surum_okunamazsa_uyari_uretilmez(bozuk):
    """ "Sürümünüz yanlış" demek, yalnızca metni okuyamadığımız için
    kullanıcıyı olmayan bir arızanın peşine düşürürdü."""
    assert ortam.opencv_uyarisi(bozuk) == ""


def test_beklenen_surum_requirements_ile_ayni():
    """İkisi birlikte değişmeli.

    requirements.txt 5.x'e çıkarılıp bu sabit 4'te kalsaydı, DOĞRU kurulumda
    her açılışta yanlış bir uyarı görünürdü - ve bir süre sonra kimse
    uyarılara bakmaz olurdu.
    """
    metin = GEREKSINIMLER.read_text(encoding="utf-8")
    eslesme = re.search(r"^opencv-python==(\d+)\.", metin, re.M)
    assert eslesme, "requirements.txt'te sabitlenmiş opencv-python satırı yok"
    assert int(eslesme.group(1)) == ortam.BEKLENEN_ANA_SURUM


def test_kurulu_surum_okunabiliyor():
    """Sürüm hiç okunamıyorsa denetimin kendisi işe yaramaz."""
    assert ortam.opencv_surumu(), "cv2 sürümü okunamadı"


# --------------------------------------------------------------- ekranda


def test_dogru_kurulumda_ana_sayfa_uyari_gostermiyor(istemci):
    sayfa = istemci.get("/").text
    assert "sürümü beklenenden farklı" not in sayfa


def test_yanlis_kurulumda_ana_sayfada_yaziyor(istemci, monkeypatch):
    """Günlüğe yazmak yetmez: kullanıcı günlüğü ancak bir şeyin bozuk
    olduğunu ZATEN bildiğinde açar."""
    from app.web import rotalar

    monkeypatch.setattr(rotalar, "_ortam_uyarisi", lambda: ortam.opencv_uyarisi("5.0.0"))
    sayfa = istemci.get("/").text
    assert "sürümü beklenenden farklı" in sayfa
    assert "İlk Kurulumu Yap" in sayfa
