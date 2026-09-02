"""Analiz süpervizörü — FastAPI içinde çalışan TEK arka plan iş parçacığı.

Görevleri:
- Aktif kameraların okuma iş parçacıklarını başlatır/durdurur
- 5 sn'de bir konfigürasyon değişikliğine bakar (MAX(updated_at)) ve
  RESTART'SIZ uygular (docs/02 §5)
- Her kamerayı kendi örnekleme hızında işler (tespit → takip → kural → olay)
- Kamera çevrimiçi/çevrimdışı geçişlerini DB'ye ve olay listesine yazar
- İhlalde anonsu tetikler, KKD bölgelerinden veri örnekler
- Günde bir kez saklama süresi (retention) temizliği ve disk kontrolü yapar

Bir kameranın hatası yalnızca o kamerayı atlatır; döngü asla ölmez —
7x24 çalışmanın gereği. Hatalar loglanır, sessizce yutulmaz.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from app import veritabani, zaman
from app.analiz.boru_hatti import KameraHatti
from app.analiz.kamera import DURUM_BAGLANIYOR, DURUM_OFFLINE, DURUM_ONLINE, KameraKaynagi
from app.analiz.kkd_siniflandirici import KkdSiniflandirici, kisi_kirp
from app.analiz.model_adi import gorunen_model_adi
from app.analiz.model_indir import (
    ModelIndirmeHatasi,
    indirilebilir_mi,
    modeli_indir,
    ozel_model_hatasi,
)
from app.analiz.tespit import ModelHatasi, Tespitci
from app.ayarlar import Ayarlar
from app.loglama import log_al
from app.olaylar.anons import AnonsYoneticisi
from app.olaylar.yazici import ihlal_yaz, sistem_olayi_yaz
from app.rules.parametreler import KuralParametreHatasi, params_dogrula
from app.rules.tipler import SINIF_INSAN, Bolge, Kalibrasyon, Kural

_KONFIG_KONTROL_SN = 5.0
_DURUM_YAZMA_SN = 5.0
_BAKIM_ARALIGI_SN = 24 * 3600.0


class AnalizSupervizoru:
    def __init__(self, ayarlar: Ayarlar) -> None:
        self.ayarlar = ayarlar
        self._log = log_al("supervizor")
        self._dur = threading.Event()
        self._is_parcacigi = threading.Thread(target=self._dongu, name="analiz", daemon=True)

        self._kaynaklar: dict[int, KameraKaynagi] = {}
        self._hatlar: dict[int, KameraHatti] = {}
        self._kamera_konfig: dict[int, dict] = {}
        self._anons_mesajlari: dict[int, dict] = {}
        self._son_durumlar: dict[int, str] = {}
        self._son_islenen_kare: dict[int, float] = {}
        self._siradaki_ornek: dict[int, float] = {}
        self._son_kkd_ornek: dict[int, float] = {}

        self._son_konfig_kontrol = 0.0
        self._son_durum_yazma = 0.0
        # Bakım zamanlayıcısı _dongu() başında tohumlanır. 0.0 bırakılırsa koşul
        # `time.monotonic() >= 86400` olur; monotonic MAKİNENİN AÇIK KALMA
        # SÜRESİDİR, uygulamanınki değil. Her vardiya sonunda kapatılan bir
        # bilgisayarda 86400'e hiç ulaşılmaz → saklama süresi temizliği ve disk
        # uyarısı HİÇ çalışmaz, disk sessizce dolardı.
        self._son_bakim = 0.0
        self._konfig_damgasi: str = ""
        # Kamera başına canlı sayım: {kamera_id: {"person": 2, "truck": 1}}
        self._canli_sayim: dict[int, dict[str, int]] = {}

        self.tespitci: Tespitci | None = None
        self.tespit_hatasi: str | None = None
        # CIKARIM_CIHAZI=cuda istenip CPU'ya düşüldüyse Türkçe uyarı (ana sayfa)
        self.cihaz_uyarisi: str = ""
        # yukleniyor | indiriliyor | hazir | hata — ana sayfa bunu gösterir
        self.model_durumu: str = "yukleniyor"
        self.kkd = KkdSiniflandirici(None)  # model 9. adımda eğitilecek
        self._anons = AnonsYoneticisi(ayarlar)

    # ---- yaşam döngüsü ----

    def baslat(self) -> None:
        self._is_parcacigi.start()

    def durdur(self) -> None:
        self._dur.set()
        self._is_parcacigi.join(timeout=10)
        for kaynak in self._kaynaklar.values():
            kaynak.durdur()

    # ---- web'in kullandığı arayüz ----

    def canli_sayim(self, kamera_id: int) -> dict[str, int]:
        """Kameranın o anda gördüğü nesne sayıları (takip bazlı, kare değil)."""
        return dict(self._canli_sayim.get(kamera_id, {}))

    def toplam_canli_sayim(self) -> dict[str, int]:
        """Tüm kameraların toplamı — ana sayfadaki özet."""
        toplam: dict[str, int] = {}
        for sayim in self._canli_sayim.values():
            for sinif, adet in sayim.items():
                toplam[sinif] = toplam.get(sinif, 0) + adet
        return toplam

    def kamera_durumu(self, kamera_id: int) -> dict:
        """Kamera sayfasının 2 sn'de bir sorduğu canlı durum: online /
        connecting / offline + kullanıcının anlayacağı Türkçe açıklama."""
        kaynak = self._kaynaklar.get(kamera_id)
        if kaynak is None:
            return {
                "durum": DURUM_BAGLANIYOR,
                "mesaj": "Kamera birkaç saniye içinde başlatılacak…",
            }
        durum = kaynak.durum()
        son_hata = kaynak.son_hata
        if durum == DURUM_ONLINE:
            fps = round(kaynak.olculen_fps, 1)
            mesaj = "Görüntü akıyor" + (f" — ölçülen {fps:g} fps" if fps else "")
        elif durum == DURUM_BAGLANIYOR:
            mesaj = "Bağlanılıyor… (ilk bağlantı 30 sn sürebilir)"
            if son_hata:
                mesaj += f" Son deneme başarısız: {son_hata}"
        else:
            mesaj = "Bağlantı yok."
            if son_hata:
                mesaj += f" {son_hata}"
            mesaj += " Sistem otomatik olarak yeniden denemeye devam ediyor."
        return {
            "durum": durum,
            "mesaj": mesaj,
            "son_deneme": zaman.ekranda_goster(kaynak.son_deneme_utc)
            if kaynak.son_deneme_utc
            else "",
            "sayim": self.canli_sayim(kamera_id),
            "kalite": self._kalite(kamera_id),
        }

    def _kalite(self, kamera_id: int) -> dict:
        hat = self._hatlar.get(kamera_id)
        return hat.kalite() if hat is not None else {"sorun": "yok", "mesaj": ""}

    def onizleme_jpeg(self, kamera_id: int, bolgeler_dahil: bool = True) -> bytes | None:
        """İşlenmiş (kutulu) son kare; yoksa ham son kare.

        bolgeler_dahil=False → bölgeler görüntüye çizilmez. Bölge çizim sayfası
        bölgeleri kendi tuvaline çizdiği için oraya bu sürüm gider.
        """
        hat = self._hatlar.get(kamera_id)
        if hat is not None:
            jpeg = hat.son_islenmis_jpeg(bolgeler_dahil)
            if jpeg is not None:
                return jpeg
        kaynak = self._kaynaklar.get(kamera_id)
        if kaynak is None:
            return None
        kare, _ = kaynak.son_kare()
        if kare is None:
            return None
        import cv2

        tamam, jpeg = cv2.imencode(".jpg", kare, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return jpeg.tobytes() if tamam else None

    # ---- ana döngü ----

    def _dongu(self) -> None:
        try:
            baglanti = veritabani.baglanti_ac(self.ayarlar.veritabani_yolu)
        except Exception as hata:  # noqa: BLE001 — iş parçacığı SESSİZCE ölmesin
            self.model_durumu = "hata"
            # Ekranda sade Türkçe; özgün hata metni yalnızca günlüğe yazılır.
            self.tespit_hatasi = (
                "Analiz başlatılamadı. Kontrol Paneli'nde Durdur'a, sonra Sistemi Başlat'a "
                "basın. Sorun sürerse program klasöründeki veri/loglar/sistem.log dosyasını "
                "destek ekibine iletin."
            )
            self._log.error(f"Analiz başlatılamadı: {hata}", exc_info=hata)
            return
        try:
            self._tespitciyi_kur(baglanti)
        except Exception as hata:  # noqa: BLE001 — model kurulamadı diye kameralar durmaz
            self.tespitci = None
            self.model_durumu = "hata"
            # Ekranda ürün adı + yapılabilir adım; ham hata metni günlüğe gider.
            self.tespit_hatasi = (
                f"{gorunen_model_adi(self.ayarlar.model_dosyasi.name)} başlatılamadı. "
                "Kontrol Paneli'nde Durdur'a, sonra Sistemi Başlat'a basın. Sorun sürerse "
                "program klasöründeki veri/loglar/sistem.log dosyasını destek ekibine iletin."
            )
            self._log.error(f"Tespit modeli kurulamadı: {hata}", exc_info=hata)
        # Bakım açılıştan hemen sonra bir kez, sonra her 24 saatlik UYGULAMA
        # çalışma süresinde bir çalışsın (makinenin uptime'ından bağımsız).
        self._son_bakim = time.monotonic() - _BAKIM_ARALIGI_SN
        self._log.info("Analiz süpervizörü başladı.")
        try:
            while not self._dur.is_set():
                simdi = time.monotonic()
                try:
                    if simdi - self._son_konfig_kontrol >= _KONFIG_KONTROL_SN:
                        self._son_konfig_kontrol = simdi
                        self._konfigurasyonu_yenile(baglanti)
                    self._kameralari_isle(baglanti, simdi)
                    if simdi - self._son_durum_yazma >= _DURUM_YAZMA_SN:
                        self._son_durum_yazma = simdi
                        self._durumlari_yaz(baglanti)
                    if simdi - self._son_bakim >= _BAKIM_ARALIGI_SN:
                        self._son_bakim = simdi
                        self._bakimi_baslat()
                except Exception as hata:  # noqa: BLE001 — 7x24 döngüsü ölmemeli;
                    # hata tam ayrıntıyla loglanır, bir sonraki turda devam edilir
                    self._log.error(f"Analiz döngüsünde hata: {hata}", exc_info=hata)
                self._dur.wait(0.05)
        finally:
            baglanti.close()
            self._log.info("Analiz süpervizörü durdu.")

    def _tespitciyi_kur(self, baglanti) -> None:
        try:
            self._modeli_hazirla()
            self.tespitci = Tespitci(
                self.ayarlar.model_dosyasi,
                self.ayarlar.cikarim_cihazi,
                guven_esigi=self.ayarlar.tespit_guven_esigi,
                insan_guven_esigi=self.ayarlar.tespit_insan_guven_esigi,
                nms_esigi=self.ayarlar.tespit_nms_esigi,
                en_kucuk_kenar_px=self.ayarlar.tespit_en_kucuk_kenar_px,
            )
            self.tespit_hatasi = None
            self.model_durumu = "hazir"
            if self.tespitci.cihaz_uyarisi:
                # GPU istenip CPU'ya düşülmüşse kullanıcı bunu bilmeli
                self.cihaz_uyarisi = self.tespitci.cihaz_uyarisi
                sistem_olayi_yaz(baglanti, self.tespitci.cihaz_uyarisi)
        except (ModelHatasi, ModelIndirmeHatasi) as hata:
            # Model yokken sistem ÇÖKMEZ: kameralar izlenir, tespit yapılmaz.
            # Durum ana sayfada ve olay listesinde görünür.
            self.tespitci = None
            self.tespit_hatasi = hata.kullanici_mesaji
            self.model_durumu = "hata"
            # Ekranda sade mesaj, günlükte tam ayrıntı (indirme adresi, özgün hata)
            self._log.error(hata.teknik_ayrinti, exc_info=hata)
            sistem_olayi_yaz(baglanti, f"Tespit modeli yüklenemedi: {hata.kullanici_mesaji}")

    def _modeli_hazirla(self) -> None:
        """Model dosyası yoksa ve bilinen bir YOLOX modeliyse bir kez indirir.
        Kullanıcı terminalde betik çalıştırmak zorunda kalmaz (CLAUDE.md §8)."""
        dosya = self.ayarlar.model_dosyasi
        if dosya.exists():
            return
        if not indirilebilir_mi(dosya):
            # Kendi modelini koyan kullanıcı "dosya bulunamadı" yerine NE YAPACAĞINI
            # söyleyen markalı açıklamayı görsün; metin tek yerde durur.
            raise ozel_model_hatasi(dosya)
        self.model_durumu = "indiriliyor"
        self._log.info(
            f"Tespit modeli bulunamadı, indiriliyor (bir kez, ~20-35 MB): {dosya.name} …"
        )
        son_yuzde = -1

        def ilerleme(inen: int, toplam: int) -> None:
            nonlocal son_yuzde
            if toplam <= 0:
                return
            yuzde = inen * 100 // toplam
            if yuzde // 25 != son_yuzde // 25:  # her %25'te bir satır, günlük şişmesin
                son_yuzde = yuzde
                self._log.info(f"Model indiriliyor: %{yuzde}")

        modeli_indir(dosya, ilerleme)
        self._log.info(f"Tespit modeli indirildi: {dosya}")

    # ---- konfigürasyon ----

    def _konfigurasyonu_yenile(self, baglanti) -> None:
        damga_satiri = baglanti.execute(
            "SELECT (SELECT COALESCE(MAX(updated_at), '') FROM cameras) || '|' || "
            "(SELECT COALESCE(MAX(updated_at), '') FROM zones) || '|' || "
            "(SELECT COALESCE(MAX(updated_at), '') FROM rules) || '|' || "
            "(SELECT COALESCE(MAX(calibrated_at), '') FROM camera_calibrations) || '|' || "
            "(SELECT COALESCE(COUNT(*), 0) FROM cameras) || '|' || "
            "(SELECT COALESCE(COUNT(*), 0) FROM zones) || '|' || "
            "(SELECT COALESCE(COUNT(*), 0) FROM rules) AS damga"
        ).fetchone()
        damga = damga_satiri["damga"]
        if damga == self._konfig_damgasi:
            return
        self._log.info("Konfigürasyon değişti — yeniden yükleniyor (restart yok).")

        kameralar = self._atanmis_kameralar(baglanti)
        self._anons_mesajlari = {
            satir["id"]: dict(satir)
            for satir in baglanti.execute("SELECT * FROM announcement_messages")
        }

        aktif_idler = set()
        for kamera in kameralar:
            kid = kamera["id"]
            aktif_idler.add(kid)
            self._kamera_konfig[kid] = kamera

            mevcut = self._kaynaklar.get(kid)
            adres_degisti = mevcut is not None and mevcut.kaynak_url != kamera["source_url"]
            if adres_degisti:
                mevcut.durdur()
                mevcut = None
                del self._kaynaklar[kid]
                # Adres değiştiyse ESKİ kameranın son karesi ve takip durumu
                # yeni kameraya ait değildir: hat da sıfırlanmalı, yoksa
                # önizlemede eski görüntü ve yanlış takip id'leri sürerdi.
                self._hatlar.pop(kid, None)
                self._son_islenen_kare.pop(kid, None)
                self._canli_sayim.pop(kid, None)
            if mevcut is None:
                kaynak = KameraKaynagi(
                    kid, kamera["name"], kamera["source_type"], kamera["source_url"]
                )
                kaynak.baslat()
                self._kaynaklar[kid] = kaynak
                self._siradaki_ornek[kid] = 0.0
                self._son_durumlar.pop(kid, None)

            hat = self._hatlar.get(kid)
            # Örnekleme hızı değiştiyse takipçinin kare hızı da değişmeli
            if hat is not None and hat.fps != int(kamera["sample_fps"]):
                hat = None
                self._hatlar.pop(kid, None)
            if hat is None:
                hat = KameraHatti(
                    kid,
                    int(kamera["sample_fps"]),
                    iyilestir=self.ayarlar.goruntu_iyilestirme == "otomatik",
                )
                self._hatlar[kid] = hat
            hat.yapilandir(
                self._bolgeleri_yukle(baglanti, kid),
                self._kurallari_yukle(baglanti, kid),
                self._kalibrasyonu_yukle(baglanti, kid),
            )

        # Silinen/pasifleşen kameraların iş parçacıkları durdurulur; pasif
        # kamera listede 'çevrimiçi' görünmeye devam etmesin diye durumu sıfırlanır
        for kid in list(self._kaynaklar):
            if kid not in aktif_idler:
                self._kaynaklar.pop(kid).durdur()
                self._hatlar.pop(kid, None)
                self._kamera_konfig.pop(kid, None)
                self._son_durumlar.pop(kid, None)
                self._canli_sayim.pop(kid, None)
                baglanti.execute(
                    "UPDATE cameras SET status = ?, measured_fps = NULL WHERE id = ?",
                    (DURUM_OFFLINE, kid),
                )
        baglanti.commit()
        # Damga ancak yenileme BAŞARIYLA bittikten sonra yazılır: ortada bir
        # hata olursa bir sonraki turda aynı değişiklik tekrar denenir, sessizce
        # yutulmaz.
        self._konfig_damgasi = damga

    def _atanmis_kameralar(self, baglanti) -> list[dict]:
        """Bu analizörün ilgilendiği kameralar (ADR-008): bugün 'tüm aktifler'.

        Fabrika geneline çıkarken bölümlendirme YALNIZCA bu fonksiyonu değiştirir.
        """
        return [
            dict(satir) for satir in baglanti.execute("SELECT * FROM cameras WHERE enabled = 1")
        ]

    def _bolgeleri_yukle(self, baglanti, kamera_id: int) -> list[Bolge]:
        bolgeler = []
        for satir in baglanti.execute("SELECT * FROM zones WHERE camera_id = ?", (kamera_id,)):
            try:
                poligon = [tuple(nokta) for nokta in json.loads(satir["polygon"])]
            except (json.JSONDecodeError, TypeError) as hata:
                self._log.error(f"Bölge poligonu bozuk (id {satir['id']}): {hata}")
                continue
            bolgeler.append(
                Bolge(
                    id=satir["id"],
                    tip=satir["zone_type"],
                    poligon=poligon,
                    aktif=bool(satir["enabled"]),
                )
            )
        return bolgeler

    def _kurallari_yukle(self, baglanti, kamera_id: int) -> list[Kural]:
        kurallar = []
        for satir in baglanti.execute(
            "SELECT * FROM rules WHERE camera_id = ? AND enabled = 1", (kamera_id,)
        ):
            try:
                params = params_dogrula(satir["rule_type"], json.loads(satir["params"]))
                hedefler = json.loads(satir["target_classes"])
            except (KuralParametreHatasi, json.JSONDecodeError) as hata:
                self._log.error(f"Kural {satir['id']} yüklenemedi, atlandı: {hata}")
                continue
            kurallar.append(
                Kural(
                    id=satir["id"],
                    kamera_id=kamera_id,
                    tip=satir["rule_type"],
                    bolge_id=satir["zone_id"],
                    hedef_siniflar=hedefler,
                    params=params,
                    cooldown_s=float(satir["cooldown_s"]),
                    anons_id=satir["announcement_id"],
                    siddet=satir["severity"],
                )
            )
        return kurallar

    def _kalibrasyonu_yukle(self, baglanti, kamera_id: int) -> Kalibrasyon | None:
        satir = baglanti.execute(
            "SELECT homography FROM camera_calibrations WHERE camera_id = ?", (kamera_id,)
        ).fetchone()
        if satir is None:
            return None
        try:
            return Kalibrasyon(homografi=json.loads(satir["homography"]))
        except (json.JSONDecodeError, TypeError) as hata:
            self._log.error(f"Kalibrasyon bozuk (kamera {kamera_id}): {hata}")
            return None

    # ---- kare işleme ----

    def _kameralari_isle(self, baglanti, simdi: float) -> None:
        for kid, kaynak in list(self._kaynaklar.items()):
            konfig = self._kamera_konfig.get(kid)
            if konfig is None:
                continue
            fps = max(float(konfig["sample_fps"]), 0.1)
            if simdi < self._siradaki_ornek.get(kid, 0.0):
                continue
            self._siradaki_ornek[kid] = simdi + 1.0 / fps

            kare, kare_zamani = kaynak.son_kare()
            if kare is None or kare_zamani <= self._son_islenen_kare.get(kid, 0.0):
                continue  # yeni kare yok — aynı kareyi iki kez işleme
            self._son_islenen_kare[kid] = kare_zamani

            hat = self._hatlar[kid]
            try:
                tespitler, ihlaller = hat.isle(kare, simdi, self.tespitci, self.kkd)
            except Exception as hata:  # noqa: BLE001 — kamera izolasyonu:
                # bir kameranın işleme hatası diğerlerini durdurmamalı
                self._log.error(f"Kare işlenemedi (kamera {kid}): {hata}", exc_info=hata)
                continue

            # Canlı sayım: takip edilen nesneler (kare başına ham tespit değil)
            sayim: dict[str, int] = {}
            for tespit in tespitler:
                sayim[tespit.sinif] = sayim.get(tespit.sinif, 0) + 1
            self._canli_sayim[kid] = sayim

            for ihlal in ihlaller:
                self._ihlali_kaydet(baglanti, hat, ihlal, simdi)
            self._kkd_ornekle(baglanti, kid, kare, tespitler, hat, simdi)

    def _ihlali_kaydet(self, baglanti, hat: KameraHatti, ihlal, simdi: float) -> None:
        kural_kaydi = self._kural_kaydi(baglanti, ihlal.kural_id)
        olay_id = ihlal_yaz(baglanti, self.ayarlar, ihlal, kural_kaydi, hat.son_islenmis_jpeg())
        self._log.info(
            f"İhlal kaydedildi (olay {olay_id}, kamera {ihlal.kamera_id}, kural {ihlal.kural_id})"
        )
        anons_id = kural_kaydi.get("announcement_id")
        if anons_id:
            self._anons.duyur(ihlal.kamera_id, simdi, self._anons_mesajlari.get(anons_id))

    def _kural_kaydi(self, baglanti, kural_id: int) -> dict:
        satir = baglanti.execute("SELECT * FROM rules WHERE id = ?", (kural_id,)).fetchone()
        if satir is None:
            return {"id": kural_id}
        kayit = dict(satir)
        for alan in ("params", "target_classes"):
            try:
                kayit[alan] = json.loads(kayit[alan])
            except (json.JSONDecodeError, TypeError):
                pass  # ham metin kalsın — olay kaydı yine de anlamlı
        return kayit

    def _kkd_ornekle(
        self, baglanti, kamera_id: int, kare, tespitler, hat: KameraHatti, simdi: float
    ) -> None:
        """KKD bölgesindeki kişilerden saatlik limitle veri örnekler (docs/04 §4.3)."""
        en_az_aralik = 3600.0 / self.ayarlar.kkd_ornek_saat_limit
        if simdi - self._son_kkd_ornek.get(kamera_id, 0.0) < en_az_aralik:
            return
        boyut = (float(kare.shape[1]), float(kare.shape[0]))
        for tespit in tespitler:
            if tespit.sinif != SINIF_INSAN or not hat.kkd_bolgesinde_mi(tespit, boyut):
                continue
            kirpik = kisi_kirp(kare, tespit.kutu)
            if kirpik is None:
                continue
            self._son_kkd_ornek[kamera_id] = simdi
            self._kkd_ornek_kaydet(baglanti, kamera_id, kirpik)
            break  # bu turda tek örnek yeter

    def _kkd_ornek_kaydet(self, baglanti, kamera_id: int, kirpik) -> None:
        import cv2

        simdi_utc = zaman.simdi_utc()
        goreli = str(
            Path("kkd-ornekler")
            / simdi_utc[:7]
            / f"{simdi_utc.replace(':', '-').replace('+', 'Z')}-k{kamera_id}.jpg"
        )
        tam_yol = self.ayarlar.goruntu_klasoru / goreli
        try:
            tam_yol.parent.mkdir(parents=True, exist_ok=True)
            # cv2.imwrite YERİNE imencode + write_bytes: imwrite yolu işletim
            # sisteminin ANSI kod sayfasıyla kodlar ve Türkçe karakter içeren
            # bir yolda (C:\Users\Gökhan\...) hata FIRLATMADAN False döner.
            # Sonuç: veritabanında var görünen ama diskte olmayan örnekler.
            tamam, tampon = cv2.imencode(".jpg", kirpik)
            if not tamam:
                self._log.error(f"KKD örneği kodlanamadı: {tam_yol}")
                return
            tam_yol.write_bytes(tampon.tobytes())
        except (OSError, cv2.error) as hata:
            self._log.error(f"KKD örneği yazılamadı ({tam_yol}): {hata}")
            return
        # Kamera bu arada silinmiş olabilir (konfig penceresi) — FK hatası yerine
        # örnek kamerasız kaydedilir; eğitim verisi yine de değerlidir.
        kamera_var = baglanti.execute("SELECT 1 FROM cameras WHERE id = ?", (kamera_id,)).fetchone()
        baglanti.execute(
            "INSERT INTO ppe_samples (camera_id, captured_at, crop_path, source) "
            "VALUES (?, ?, ?, 'auto')",
            (kamera_id if kamera_var else None, simdi_utc, goreli),
        )
        baglanti.commit()

    # ---- durum yazımı ----

    def _durumlari_yaz(self, baglanti) -> None:
        """Üç durum: connecting (ilk 60 sn, olay yok) / online / offline.

        Olay yalnızca GERÇEK geçişlerde üretilir: 'çevrimdışı' ilk bağlantı
        süresi dolunca ya da akan görüntü kesilince; 'tekrar çevrimiçi' yalnız
        çevrimdışından dönüşte. Yeni eklenen ya da yeniden başlatılan sistemde
        henüz bağlanmakta olan kamera olay üretmez.
        """
        for kid, kaynak in self._kaynaklar.items():
            durum = kaynak.durum()
            onceki = self._son_durumlar.get(kid)
            if durum != onceki:
                self._son_durumlar[kid] = durum
                ad = self._kamera_konfig.get(kid, {}).get("name", kid)
                if durum == DURUM_OFFLINE:
                    sebep = f" — {kaynak.son_hata}" if kaynak.son_hata else ""
                    self._log.warning(f"Kamera çevrimdışı: {ad}{sebep}")
                    sistem_olayi_yaz(
                        baglanti,
                        f"Kamera çevrimdışı: {ad}{sebep}",
                        kamera_id=kid,
                    )
                elif durum == DURUM_ONLINE and onceki == DURUM_OFFLINE:
                    self._log.info(f"Kamera tekrar çevrimiçi: {ad}")
                    sistem_olayi_yaz(baglanti, f"Kamera tekrar çevrimiçi: {ad}", kamera_id=kid)
            if durum == DURUM_ONLINE:
                baglanti.execute(
                    "UPDATE cameras SET status = ?, last_frame_at = ?, measured_fps = ? "
                    "WHERE id = ?",
                    (durum, zaman.simdi_utc(), round(kaynak.olculen_fps, 1), kid),
                )
            else:
                # last_frame_at KORUNUR: "en son ne zaman görüntü geldi" bilgisi
                # kamera koptuğunda en çok ihtiyaç duyulan bilgidir; silinmez.
                baglanti.execute(
                    "UPDATE cameras SET status = ?, measured_fps = NULL WHERE id = ?",
                    (durum, kid),
                )
        baglanti.commit()

    # ---- bakım (retention + disk) ----

    def _bakimi_baslat(self) -> None:
        """Bakımı KENDİ iş parçacığında çalıştırır: binlerce dosya silmek
        dakikalar sürebilir; kare işleme bu sürede durmamalı."""
        if getattr(self, "_bakim_calisiyor", False):
            return
        self._bakim_calisiyor = True

        def _calistir() -> None:
            # Bağlantı açılışı da try İÇİNDE: açılış hatası (bozuk DB, izin)
            # yakalanmazsa bayrak True'da takılı kalır ve bakım restart'a
            # kadar sessizce devre dışı kalırdı.
            bakim_baglantisi = None
            try:
                bakim_baglantisi = veritabani.baglanti_ac(self.ayarlar.veritabani_yolu)
                self._bakim_yap(bakim_baglantisi)
            except Exception as hata:  # noqa: BLE001 — bakım hatası sistemi durdurmaz
                self._log.error(f"Bakım hatası: {hata}", exc_info=hata)
            finally:
                if bakim_baglantisi is not None:
                    bakim_baglantisi.close()
                self._bakim_calisiyor = False

        threading.Thread(target=_calistir, name="bakim", daemon=True).start()

    def _bakim_yap(self, baglanti) -> None:
        a = self.ayarlar
        sinir = zaman.gun_once_utc(a.olay_saklama_gun)
        silinen_olay = baglanti.execute(
            "DELETE FROM events WHERE event_type = 'violation' AND occurred_at < ?",
            (sinir,),
        ).rowcount
        silinen_sistem = baglanti.execute(
            "DELETE FROM events WHERE event_type = 'system' AND occurred_at < ?",
            (zaman.gun_once_utc(a.sistem_olay_saklama_gun),),
        ).rowcount
        baglanti.commit()

        silinen_foto = self._eski_dosyalari_sil(a.goruntu_klasoru, a.goruntu_saklama_gun)
        # Dosya silindiği halde events.snapshot_path dolu kalırsa olay ekranında
        # kırık resim görünür; kaydı da temizle (olayın kendisi korunur).
        baglanti.execute(
            "UPDATE events SET snapshot_path = NULL "
            "WHERE snapshot_path IS NOT NULL AND occurred_at < ?",
            (zaman.gun_once_utc(a.goruntu_saklama_gun),),
        )
        baglanti.commit()
        silinen_kkd = self._kkd_hamlarini_sil(baglanti)

        import shutil as _shutil

        bos_gb = _shutil.disk_usage(a.veri_dizini).free / (1024**3)
        self._log.info(
            f"Bakım: {silinen_olay} olay, {silinen_sistem} sistem olayı, "
            f"{silinen_foto} fotoğraf, {silinen_kkd} KKD örneği silindi; "
            f"boş disk {bos_gb:.1f} GB"
        )
        if bos_gb < a.disk_uyari_gb:
            sistem_olayi_yaz(
                baglanti,
                f"Disk azalıyor: {bos_gb:.1f} GB kaldı (uyarı eşiği {a.disk_uyari_gb} GB). "
                "Saklama sürelerini kısaltmayı veya disk açmayı değerlendirin.",
            )

    def _eski_dosyalari_sil(self, klasor: Path, gun: int) -> int:
        """Eski OLAY fotoğraflarını siler.

        kkd-ornekler/ alt ağacına DOKUNMAZ: etiketli örnekler eğitim veri
        setidir ve asla silinmez; etiketsizlerin süresi _kkd_hamlarini_sil
        tarafından ayrı (daha kısa) politika ile yönetilir (docs/06 §5).
        """
        sinir = time.time() - gun * 86400
        kkd_klasoru = klasor / "kkd-ornekler"
        sayi = 0
        for dosya in klasor.rglob("*.jpg"):
            if dosya.is_relative_to(kkd_klasoru):
                continue
            try:
                if dosya.stat().st_mtime < sinir:
                    dosya.unlink()
                    sayi += 1
            except OSError:
                # Windows'ta başka bir işlemin (Defender, yedekleme, dizin
                # oluşturucu) açık tuttuğu dosya PermissionError verir.
                # Yalnızca FileNotFoundError yakalamak, TEK kilitli dosya
                # yüzünden o günkü bakımın tamamını iptal ediyordu.
                continue
        return sayi

    def _kkd_hamlarini_sil(self, baglanti) -> int:
        """Etiketlenmemiş KKD örnekleri süre dolunca dosyasıyla birlikte silinir.
        Etiketlenenler veri setidir; retention onlara dokunmaz (docs/06 §5)."""
        sinir = zaman.gun_once_utc(self.ayarlar.kkd_ham_veri_saklama_gun)
        satirlar = baglanti.execute(
            "SELECT id, crop_path FROM ppe_samples WHERE labeled_at IS NULL AND captured_at < ?",
            (sinir,),
        ).fetchall()
        for satir in satirlar:
            dosya = self.ayarlar.goruntu_klasoru / satir["crop_path"]
            try:
                dosya.unlink(missing_ok=True)
            except OSError as hata:
                self._log.error(f"KKD örneği silinemedi ({dosya}): {hata}")
        baglanti.execute(
            "DELETE FROM ppe_samples WHERE labeled_at IS NULL AND captured_at < ?",
            (sinir,),
        )
        baglanti.commit()
        return len(satirlar)
