"""IP hoparlör adresindeki kullanıcı adı ve şifre (docs/14 §3.4).

Eskiden urllib adresteki `kullanici:sifre@` kısmını göndermiyordu: kimlik
isteyen hoparlör hiç çalmıyordu. Port yazılmamışsa şifre port sanılıp hata
metnine giriyor, oradan son anons satırına, teslim kaydına, arşive ve
sistem.log'a düşüyordu; adres maskesi `//…@` biçimini aradığı için onu
yakalamıyordu. Analiz kapalıyken aynı adresin "Dene"si 500 dönüyordu.
Denetim 24.09.2026; operatör: "Olan problemleri de çöz".

Kimlik testleri gerçek bir yerel HTTP sunucusuyla konuşur: Basic ve Digest
uçtan uca denenir. R30 bu bilgisayarı gösteren adresi reddettiği için yalnız
o denetim bu testlerde devre dışıdır.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import http.server
import json
import logging
import threading
import urllib.error
import urllib.request

import pytest

from app.olaylar import anons

KULLANICI = "anons"
SIFRE = "p@ss-gizli"
ADRESTEKI_SIFRE = "p%40ss-gizli"  # "@" adreste yüzde kaçışıyla yazılır


class _Hoparlor(http.server.BaseHTTPRequestHandler):
    """Kimlik isteyen bir IP hoparlör: önce 401 ile ister, doğruysa 200."""

    def log_message(self, *_a) -> None:  # test çıktısını kirletmesin
        pass

    def do_POST(self) -> None:
        govde = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        yetki = self.headers.get("Authorization")
        self.server.istekler.append({"yol": self.path, "yetki": yetki, "govde": govde})
        if self.server.kimlik_dogru(self.command, yetki):
            self.send_response(200)
        else:
            self.send_response(401)
            self.send_header("WWW-Authenticate", self.server.meydan_okuma)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST


def _basic(sifre: str):
    beklenen = "Basic " + base64.b64encode(f"{KULLANICI}:{sifre}".encode()).decode()
    return 'Basic realm="hoparlor"', lambda _yontem, yetki: yetki == beklenen


def _md5(metin: str) -> str:
    return hashlib.md5(metin.encode()).hexdigest()  # noqa: S324 - Digest'in kendi tanımı


def _digest(sifre: str):
    alan, tek = "amfi", "4b1d0c3e"

    def dogru(yontem: str, yetki: str | None) -> bool:
        if not yetki or not yetki.startswith("Digest "):
            return False
        a = urllib.request.parse_keqv_list(urllib.request.parse_http_list(yetki[7:]))
        ha1 = _md5(f"{a['username']}:{alan}:{sifre}")
        ha2 = _md5(f"{yontem}:{a['uri']}")
        beklenen = _md5(f"{ha1}:{tek}:{a['nc']}:{a['cnonce']}:{a['qop']}:{ha2}")
        return a["username"] == KULLANICI and a["nonce"] == tek and a["response"] == beklenen

    return f'Digest realm="{alan}", nonce="{tek}", qop="auth", algorithm=MD5', dogru


@pytest.fixture
def hoparlor(monkeypatch):
    """Kimlik isteyen yerel hoparlör kurar; adresini döndürür."""
    monkeypatch.setattr(anons, "hoparlor_adresini_dogrula", lambda _adres: None)
    sunucular: list[http.server.ThreadingHTTPServer] = []

    def kur(sema):
        meydan_okuma, dogru = sema
        sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hoparlor)
        sunucu.istekler = []
        sunucu.meydan_okuma = meydan_okuma
        sunucu.kimlik_dogru = dogru
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        sunucular.append(sunucu)
        return sunucu

    yield kur
    for sunucu in sunucular:
        sunucu.shutdown()
        sunucu.server_close()


class _Toplayici(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.mesajlar: list[str] = []

    def emit(self, kayit: logging.LogRecord) -> None:
        self.mesajlar.append(kayit.getMessage())


@pytest.fixture
def anons_gunlugu():
    toplayici = _Toplayici()
    gunluk = logging.getLogger("dalsan.anons")
    gunluk.addHandler(toplayici)
    try:
        yield toplayici.mesajlar
    finally:
        gunluk.removeHandler(toplayici)


@pytest.mark.parametrize("bicim", ["json", "form", "get"])
def test_basic_kimlik_istenince_gonderilir(hoparlor, bicim):
    sunucu = hoparlor(_basic(SIFRE))
    port = sunucu.server_address[1]
    adres = f"http://{KULLANICI}:{ADRESTEKI_SIFRE}@127.0.0.1:{port}/anons?k={{anahtar}}"

    anons.http_gonder(adres, "helmet", "Baretinizi takınız.", bicim)

    ilk, son = sunucu.istekler[0], sunucu.istekler[-1]
    # Kimlik yalnız cihaz isteyince gider; adres satırında hiç yoktur
    assert ilk["yetki"] is None
    assert son["yetki"].startswith("Basic ")
    assert son["yol"] == "/anons?k=helmet"
    if bicim == "json":
        assert json.loads(son["govde"]) == {"key": "helmet", "text": "Baretinizi takınız."}


def test_digest_kimlik_istenince_gonderilir(hoparlor):
    sunucu = hoparlor(_digest(SIFRE))
    port = sunucu.server_address[1]

    anons.http_gonder(
        f"http://{KULLANICI}:{ADRESTEKI_SIFRE}@127.0.0.1:{port}/api/play", "vest", "Yelek", "json"
    )

    assert sunucu.istekler[-1]["yetki"].startswith("Digest ")
    assert json.loads(sunucu.istekler[-1]["govde"])["key"] == "vest"


def test_yanlis_sifre_kimlik_hatasi_der_ve_sifreyi_yazmaz(hoparlor, anons_gunlugu):
    sunucu = hoparlor(_basic("baska-sifre"))
    port = sunucu.server_address[1]
    adres = f"http://{KULLANICI}:{ADRESTEKI_SIFRE}@127.0.0.1:{port}/anons"

    with pytest.raises(anons.AnonsHatasi) as hata:
        anons.http_gonder(adres, "helmet", "Baret", "json")

    metin = str(hata.value)
    assert "reddetti (HTTP 401)" in metin and "şifre" in metin
    assert "ulaşılamadı" not in metin, "cihaz yanıt verdi; ağ sorunu gibi söylenmemeli"
    assert "p@ss" not in metin and "p%40ss" not in metin
    assert not any("p@ss" in m or "p%40ss" in m for m in anons_gunlugu)


def test_kimliksiz_adres_eskisi_gibi_dogrudan_gider(hoparlor):
    """Kimlik yazılmamışsa istek tek seferde, Authorization'sız gider."""
    sunucu = hoparlor(("", lambda _yontem, _yetki: True))
    port = sunucu.server_address[1]

    anons.http_gonder(f"http://127.0.0.1:{port}/anons", "helmet", "Baret", "json")

    assert len(sunucu.istekler) == 1 and sunucu.istekler[0]["yetki"] is None


@pytest.fixture
def ag_yok(monkeypatch):
    """Fabrika ağındaki kapalı hoparlör: urllib'in gerçek yolu yürür, yalnız
    bağlantı anında reddedilir; ağa çıkılmaz. Bağlanılmak istenen sunucu
    kaydedilir."""
    hedefler: list[tuple[str, int]] = []

    def reddet(baglanti):
        hedefler.append((baglanti.host, baglanti.port))
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(http.client.HTTPConnection, "connect", reddet)
    return hedefler


def test_portsuz_adreste_sifre_hicbir_yere_sizmaz(ag_yok, anons_gunlugu):
    """Eski hata: port yoksa urllib şifreyi port sanıyordu
    ("nonnumeric port: 'sifre@10.0.0.9'") ve bu metin maskeden geçiyordu."""
    with pytest.raises(anons.AnonsHatasi) as hata:
        anons.http_gonder("http://kul:anons-sifresi@10.0.0.9/anons", "helmet", "Baret", "json")

    assert ag_yok == [("10.0.0.9", 80)]
    assert "ulaşılamadı" in str(hata.value)
    assert "anons-sifresi" not in str(hata.value)
    assert not any("anons-sifresi" in m for m in anons_gunlugu)


def test_bozuk_yanit_da_anons_hatasidir(monkeypatch):
    """Yanıtsız kapanan bağlantı (HTTPException) eskiden AnonsHatasi'ne
    dönmüyor, "beklenmeyen hata" olarak yukarı kaçıyordu."""

    def kopar(*_a, **_k):
        raise http.client.RemoteDisconnected("Remote end closed connection without response")

    monkeypatch.setattr(urllib.request, "urlopen", kopar)
    with pytest.raises(anons.AnonsHatasi, match="ulaşılamadı"):
        anons.http_gonder("http://10.0.0.9/anons", "helmet", "Baret", "json")


def test_analiz_kapaliyken_dene_500_donmez(istemci, ag_yok):
    istemci.post(
        "/hoparlorler/kaydet",
        data={
            "name": "Rampa",
            "area": "",
            "address": "http://kul:dene-sifresi@10.0.0.9/anons",
            "enabled": "1",
            "description": "",
        },
        follow_redirects=False,
    )
    yanit = istemci.post("/hoparlorler/1/dene")

    assert yanit.status_code == 400
    hata = yanit.json()["hata"]
    assert "ulaşılamadı" in hata and "dene-sifresi" not in hata
