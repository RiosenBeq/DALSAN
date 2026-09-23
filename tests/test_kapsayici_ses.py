"""Container'da ses yolu (docs/17 §7.6 yol A, S29; Faz 4e).

İmaj bu depoda derlenmez; burada yalnız dosyaların durağan denetimi yapılır:
imajda ses istemcisi var, ses yolu ayrı bir compose dosyasıyla isteğe bağlı
açılır ve hiçbir compose dosyası geniş yetki vermez (docs/16 §4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

# Ses için gerekmeyen, verilmesi yasak yetkiler (docs/17 §7.6, docs/16 §4).
# /run/dbus yalnız Bluetooth yeniden bağlanma bekçisi yazılırsa bağlanırdı (S9).
YASAKLAR = ("privileged", "network_mode", "cap_add", "NET_ADMIN", "NET_RAW", "/run/dbus")


def _etkin_satirlar(dosya: str) -> str:
    """Yorum satırları atılmış metin: yorumdaki tarif denetlenmez."""
    metin = (KOK / dosya).read_text(encoding="utf-8")
    return "\n".join(s for s in metin.splitlines() if not s.lstrip().startswith("#"))


def test_imajda_ses_istemcisi_var_bluez_yok():
    dockerfile = _etkin_satirlar("Dockerfile")
    assert "pulseaudio-utils" in dockerfile, "paplay/pactl olmadan ses çıkışı kanalı çalamaz"
    assert "bluez" not in dockerfile, "bekçi yazılmadı; Bluetooth istemcisi gerekmez"


@pytest.mark.parametrize("dosya", ["docker-compose.yml", "docker-compose.ses.yml"])
def test_compose_genis_yetki_vermez(dosya):
    metin = _etkin_satirlar(dosya)
    for yasak in YASAKLAR:
        assert yasak not in metin, f"{dosya}: {yasak}"
    assert "/dev/snd" not in metin, "ALSA Bluetooth'u görmez; imajda ALSA çalıcısı yok"


def test_ses_yolu_soket_ve_kullanici_numarasiyla_acilir():
    metin = _etkin_satirlar("docker-compose.ses.yml")
    assert 'PULSE_SERVER: "unix:/run/dalsan-ses/native"' in metin
    assert "target: /run/dalsan-ses/native" in metin
    assert 'user: "${DALSAN_UID:-1000}:${DALSAN_GID:-1000}"' in metin
    # Soket yoksa Docker onun yerine boş klasör açmasın (sessiz arıza olurdu)
    assert "create_host_path: false" in metin


def test_ses_klasoru_acilista_olusur(tmp_path, monkeypatch):
    """WAV'lar veri/sesler/'de durur: Docker'da bağlı klasördedir, yedeğe girer."""
    from app.ayarlar import ayarlari_coz

    monkeypatch.delenv("DALSAN_KAPSAYICI", raising=False)
    ayarlari_coz(tmp_path, {})
    assert (tmp_path / "veri" / "sesler").is_dir()


def test_ana_compose_ses_yolunu_zorla_acmaz():
    """Ses sunucusu olmayan sunucuda container yine açılabilmeli: ses yolu
    isteğe bağlıdır ve ana dosyada yalnız tarifi durur."""
    ana = _etkin_satirlar("docker-compose.yml")
    assert "PULSE_SERVER" not in ana and "user:" not in ana
    assert "docker-compose.ses.yml" in (KOK / "docker-compose.yml").read_text(encoding="utf-8")
