"""R30 (SSRF): IP hoparlör adresi bu bilgisayarı ya da bağlantı-yerel ağı gösteremez.

Hoparlör formu, "Bu hoparlörü dene" ve her anons gönderimi aynı denetimden
geçer (docs/17 §10.5, F4a). Özel ağ adresleri serbesttir: hoparlörler oradadır.
"""

from __future__ import annotations

import socket
import urllib.request

import pytest

from app.olaylar import anons
from app.olaylar.anons import AnonsHatasi, hoparlor_adresini_dogrula


@pytest.mark.parametrize(
    "adres",
    [
        "http://127.0.0.1:8080/anons",
        "http://127.8.9.10/anons",  # 127/8'in tamamı
        "http://localhost/anons",
        "http://anons.localhost/anons",
        "http://[::1]:8080/anons",
        "http://[::ffff:127.0.0.1]/anons",  # IPv4 eşlenik IPv6
        "http://0.0.0.0/anons",
        "http://169.254.169.254/latest/meta-data",  # bulut üst veri servisi
        "http://[fe80::1]/anons",
        "http://kul:sifre@127.0.0.1/anons",
    ],
)
def test_bu_bilgisayar_ve_baglanti_yerel_reddedilir(adres):
    with pytest.raises(AnonsHatasi, match="bu bilgisayarı ya da bağlantı-yerel") as hata:
        hoparlor_adresini_dogrula(adres)
    assert "sifre" not in str(hata.value)  # adres maskeli yazılır (R18)


@pytest.mark.parametrize(
    "adres",
    [
        "http://10.0.0.9:8080/anons",
        "http://192.168.1.50/anons?k={anahtar}",
        "https://172.16.4.2/api",
        "http://[fd00::5]/anons",  # IPv6 özel ağ
    ],
)
def test_fabrika_agi_kabul_edilir(adres):
    hoparlor_adresini_dogrula(adres)


def test_ad_cozulur_ve_yerel_sonuc_reddedilir(monkeypatch):
    """'2130706433' ya da DNS'te 127.0.0.1'e çıkan bir ad da yakalanır."""
    cozum = {
        "anons.fabrika": "10.0.0.9",
        "hileli.ornek": "127.0.0.1",
        "2130706433": "127.0.0.1",  # glibc ondalık yazımı böyle çözer
    }

    def sahte_getaddrinfo(sunucu, port, *a, **k):
        if sunucu not in cozum:
            raise socket.gaierror("çözülemedi")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (cozum[sunucu], port))]

    monkeypatch.setattr(socket, "getaddrinfo", sahte_getaddrinfo)
    hoparlor_adresini_dogrula("http://anons.fabrika/anons")
    for adres in ("http://hileli.ornek/anons", "http://2130706433/anons"):
        with pytest.raises(AnonsHatasi):
            hoparlor_adresini_dogrula(adres)
    # Çözülemeyen ad burada reddedilmez: gönderimde "ulaşılamadı" denir
    hoparlor_adresini_dogrula("http://yok.ornek/anons")


def test_gonderim_de_denetler_ve_aga_cikmaz(monkeypatch):
    cagrildi = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: cagrildi.append(a))
    with pytest.raises(AnonsHatasi, match="bu bilgisayarı"):
        anons.http_gonder("http://127.0.0.1:9000/anons", "helmet", "Baret", "json")
    assert cagrildi == [], "reddedilen adrese istek hiç gitmemeli"


def test_formdan_yerel_adres_kaydedilmez(istemci, test_ayarlari):
    from app import veritabani

    yanit = istemci.post(
        "/hoparlorler/kaydet",
        data={"name": "Hileli", "area": "", "address": "http://127.0.0.1:2375/", "enabled": "1"},
    )
    assert yanit.status_code == 400
    assert "bu bilgisayarı" in yanit.json()["hata"]
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        assert baglanti.execute("SELECT COUNT(*) FROM speaker_zones").fetchone()[0] == 0
    finally:
        baglanti.close()
