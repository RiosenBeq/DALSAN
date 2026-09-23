"""Kural tipi 3 - ppe_violation: KKD ihlali (docs/03 §3, docs/04 §7).

KANITIN YOKLUĞU, İHLALİN VARLIĞI DEĞİLDİR.
`belirsiz` HİÇBİR ZAMAN olay üretmez. Yalnızca yeterli sayıda GEÇERLİ
gözlemin yeterli oranı 'yok' diyorsa, o da kişi bölgede yeterince kaldıysa,
olay üretilir. Bu kural test_belirsiz_asla_olay_uretmez ile korunur.

Karar kare bazında DEĞİL, takip (track) bazında zamansal oylamayla verilir.
Her kalem (baret, yelek) AYRI karar ve AYRI olaydır (docs/17 §5.6): yalnız
yelek eksikse yalnız PPE_NO_VEST açılır; ikisi eksikse iki olay, iki bekleme.

Bir karedeki gözlem şüpheliyse (kabindeki sürücü, üst üste iki kişi, bulanık
kırpık - docs/17 §5.3-5.4) o karede iki kalem de BELİRSİZ yazılır.
"""

from __future__ import annotations

from collections import deque

from app.rules.geometri import kutu_alani, kutu_iou, kutu_kesisimi, nokta_poligonda
from app.rules.parametreler import KkdParams
from app.rules.tipler import (
    BELIRSIZ,
    SINIF_FORKLIFT,
    SINIF_INSAN,
    SINIF_TIR,
    VAR,
    YOK,
    Ihlal,
    KkdGozlem,
    Kural,
    Tespit,
)

# details JSON'unda veritabanı şemasıyla aynı İngilizce etiketler kullanılır
# (ppe_samples.helmet_label: yes/no/unknown)
_ETIKET = {VAR: "yes", YOK: "no", BELIRSIZ: "unknown"}
_KKD_ALANLARI = {"helmet": ("baret", "baret_guven"), "vest": ("yelek", "yelek_guven")}

# Kare kenarına bu kadar yakın kutular "kesik" sayılır (require_full_bbox)
_KENAR_PAYI_PX = 2.0
# Sürücü muafiyetinde kabin sayılan araçlar (docs/17 §5.4)
_ARAC_SINIFLARI = (SINIF_FORKLIFT, SINIF_TIR)


class KkdDegerlendirici:
    def __init__(self, kural: Kural) -> None:
        self.kural = kural
        self.params = KkdParams(**kural.params)
        # takip_id -> {"giris": zaman, "pencereler": {kkd: deque[(durum, guven)]}}
        self._durumlar: dict[int, dict] = {}
        self._aktif: set[tuple] = set()
        self._belirsiz: set[tuple] = set()

    def aktif_anahtarlar(self) -> set[tuple]:
        """Son değerlendirmede oyu hâlâ "yok" olan (kişi, kalem)lar (olay_durumu)."""
        return self._aktif

    def belirsiz_anahtarlar(self) -> set[tuple]:
        """Oyu BELİRSİZ olan (kişi, kalem)lar: o kalemin açık olayı `belirsiz`
        sebebiyle kapanır. Belirsiz kanıtla "ihlal sürüyor" denmez (docs/17 §5.6)."""
        return self._belirsiz

    def degerlendir(self, baglam) -> list[Ihlal]:
        self._aktif, self._belirsiz = set(), set()
        bolge = baglam.bolgeler.get(self.kural.bolge_id)
        if bolge is None or not bolge.aktif:
            return []  # KKD kuralı bölgesiz ÇALIŞMAZ (docs/03 §3: zone_id zorunlu)

        ihlaller: list[Ihlal] = []
        gorulenler: set[int] = set()
        # KKD muaf alanlar (kabin, ofis köşesi) zorunlu alandan oyulur
        # (docs/17 §5.5): içindeki kişi değerlendirilmez, bölge dışında sayılır.
        muaflar = [b.poligon for b in baglam.bolgeler.values() if b.tip == "ppe_exempt" and b.aktif]

        for tespit in baglam.tespitler:
            if tespit.sinif != SINIF_INSAN:
                continue
            ayak = tespit.ayak_noktasi()
            ayak_norm = (ayak[0] / baglam.kare_boyutu[0], ayak[1] / baglam.kare_boyutu[1])
            icinde = nokta_poligonda(ayak_norm, bolge.poligon) and not any(
                nokta_poligonda(ayak_norm, m) for m in muaflar
            )
            if not icinde:
                # Bölgeden çıkan kişinin kalış süresi sıfırlanır; gözlem
                # penceresi durur ama silinmez (kayan pencere)
                durum = self._durumlar.get(tespit.takip_id)
                if durum:
                    durum.pop("giris", None)
                continue

            gorulenler.add(tespit.takip_id)
            durum = self._durumlar.setdefault(
                tespit.takip_id,
                {"pencereler": {k: deque(maxlen=self.params.window_size) for k in _KKD_ALANLARI}},
            )
            durum.setdefault("giris", baglam.zaman_s)
            durum["son_boy_px"] = tespit.kutu[3] - tespit.kutu[1]
            if tespit.kkd_gozlemi is not None:
                durum["model_surumu"] = getattr(tespit.kkd_gozlemi, "model_surumu", "") or ""

            self._gozlem_ekle(tespit, durum, baglam)

            kalis = baglam.zaman_s - durum["giris"]
            if kalis < self.params.min_dwell_s:
                continue
            ihlaller.extend(self._karar_ver(tespit, durum, kalis, baglam))

        # Uzun süredir görülmeyen takipler temizlenir (bellek)
        for takip_id in list(self._durumlar):
            if takip_id not in gorulenler:
                durum = self._durumlar[takip_id]
                durum["kayip"] = durum.get("kayip", 0) + 1
                if durum["kayip"] > 10 * self.params.window_size:
                    del self._durumlar[takip_id]
            else:
                self._durumlar[takip_id].pop("kayip", None)
        return ihlaller

    def _gozlem_ekle(self, tespit: Tespit, durum: dict, baglam) -> None:
        """DEĞERLENDİRME olan kareyi pencereye ekler. Şüphe = belirsiz.

        Pencere 'son N değerlendirmenin' penceresidir, son N karenin DEĞİL
        (docs/04 §7.1): sınıflandırıcı 5 karede bir çalışır; gözlem üretilmeyen
        ara kareler pencereye YAZILMAZ. Aksi halde pencere belirsizle dolar ve
        kural hiçbir zaman yeterli geçerli gözleme ulaşamazdı.
        """
        if tespit.kkd_gozlemi is None:
            return  # bu karede değerlendirme yapılmadı (kadans/model yok)
        if self._gozlem_supheli_mi(tespit, tespit.kkd_gozlemi, baglam):
            for kkd in self.params.required_ppe:
                durum["pencereler"][kkd].append((BELIRSIZ, 0.0))
            return

        boy_px = tespit.kutu[3] - tespit.kutu[1]
        kesik = self._kesik_mi(tespit, baglam.kare_boyutu)

        for kkd in self.params.required_ppe:
            alan, guven_alani = _KKD_ALANLARI[kkd]
            # Baret, kişi boyunun ~1/8'i; yelek gövdenin ~1/3'ü. Bu yüzden
            # eşikler ayrıdır: baret 120 px isterken yelek 80 px'te güvenilir
            # (docs/04 §3 tablosu).
            boy_esigi = (
                self.params.min_person_height_px
                if kkd == "helmet"
                else self.params.min_vest_height_px
            )
            if boy_px < boy_esigi or (self.params.require_full_bbox and kesik):
                durum["pencereler"][kkd].append((BELIRSIZ, 0.0))
                continue
            deger = getattr(tespit.kkd_gozlemi, alan)
            guven = getattr(tespit.kkd_gozlemi, guven_alani)
            if deger != BELIRSIZ and guven < self.params.min_confidence:
                deger = BELIRSIZ  # düşük güven → karar YOK, belirsiz
            durum["pencereler"][kkd].append((deger, guven))

    def _gozlem_supheli_mi(self, tespit: Tespit, gozlem: KkdGozlem, baglam) -> bool:
        """Bu karenin gözlemi karar için güvenilmez mi (docs/17 §5.3-5.4)?

        Üç kaynak, üçü de saf geometri ya da ölçülmüş sayı:
        - bulanık kırpık: netlik `min_netlik`'in altında (None = kapalı);
        - kabindeki sürücü (`surucu_muaf`): ayak noktası bir araç kutusunda ya
          da kişi kutusunun `surucu_ortusme_orani`'ı araçla örtüşüyor;
        - üst üste iki kişi: IoU `max_kisi_ortusmesi`'ni aşıyor (None = kapalı).
        """
        p = self.params
        if p.min_netlik is not None and gozlem.netlik is not None and gozlem.netlik < p.min_netlik:
            return True
        digerleri = [t for t in baglam.tespitler if t is not tespit]
        araclar = [t for t in digerleri if t.sinif in _ARAC_SINIFLARI]
        if p.surucu_muaf and any(self._arac_icinde_mi(tespit, arac) for arac in araclar):
            return True
        return p.max_kisi_ortusmesi is not None and any(
            kutu_iou(tespit.kutu, kisi.kutu) > p.max_kisi_ortusmesi
            for kisi in digerleri
            if kisi.sinif == SINIF_INSAN
        )

    def _arac_icinde_mi(self, kisi: Tespit, arac: Tespit) -> bool:
        x1, y1, x2, y2 = arac.kutu
        ayak_x, ayak_y = kisi.ayak_noktasi()
        if x1 <= ayak_x <= x2 and y1 <= ayak_y <= y2:
            return True
        alan = kutu_alani(kisi.kutu)
        return alan > 0 and kutu_kesisimi(kisi.kutu, arac.kutu) / alan >= (
            self.params.surucu_ortusme_orani
        )

    def _karar_ver(self, tespit: Tespit, durum: dict, kalis: float, baglam) -> list[Ihlal]:
        kararlar: dict[str, dict] = {}

        for kkd in self.params.required_ppe:
            pencere = durum["pencereler"][kkd]
            gecerli = [(d, g) for d, g in pencere if d != BELIRSIZ]
            yok_sayisi = sum(1 for d, _ in gecerli if d == YOK)

            if len(gecerli) < self.params.min_valid_observations:
                karar = BELIRSIZ  # yeterli kanıt yok → olay YOK
            elif yok_sayisi / len(gecerli) >= self.params.violation_ratio:
                karar = YOK
            else:
                karar = VAR

            ort_guven = sum(g for _, g in gecerli) / len(gecerli) if gecerli else 0.0
            kararlar[kkd] = {
                "decision": _ETIKET[karar],
                "valid_obs": len(gecerli),
                "negative_obs": yok_sayisi,
                "mean_conf": round(ort_guven, 2),
            }

        # Kalem başına anahtar, olay ve bekleme: baret ve yelek ayrı olaydır
        # (docs/17 §5.6). Olay ayrıntısı iki kalemin kararını da taşır.
        ihlaller: list[Ihlal] = []
        for kkd, karar in kararlar.items():
            anahtar = (self.kural.id, self.kural.kamera_id, tespit.takip_id, kkd)
            if karar["decision"] == _ETIKET[BELIRSIZ]:
                self._belirsiz.add(anahtar)
                continue
            if karar["decision"] != _ETIKET[YOK]:
                continue
            self._aktif.add(anahtar)
            if not baglam.cooldown.izinli_mi(anahtar, baglam.zaman_s, self.kural.cooldown_s):
                continue
            ihlaller.append(
                Ihlal(
                    kural_id=self.kural.id,
                    kamera_id=self.kural.kamera_id,
                    takip_idler=[tespit.takip_id],
                    bolge_id=self.kural.bolge_id,
                    olculen=round(kalis, 1),
                    detaylar={
                        "ppe": {
                            "required": list(self.params.required_ppe),
                            **kararlar,
                            "person_height_px": int(durum.get("son_boy_px", 0)),
                            # model_version olmadan "model iyileşti mi" sorusu
                            # cevaplanamaz - zorunludur (docs/03 §3)
                            "model_version": durum.get("model_surumu", ""),
                            "dwell_s": round(kalis, 1),
                        },
                        "eksik_kkd": [kkd],
                    },
                    kalem=kkd,
                )
            )
        return ihlaller

    def _kesik_mi(self, tespit: Tespit, kare_boyutu: tuple[float, float]) -> bool:
        x1, y1, x2, y2 = tespit.kutu
        genislik, yukseklik = kare_boyutu
        return (
            x1 <= _KENAR_PAYI_PX
            or y1 <= _KENAR_PAYI_PX
            or x2 >= genislik - _KENAR_PAYI_PX
            or y2 >= yukseklik - _KENAR_PAYI_PX
        )
