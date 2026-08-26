# 03 — Kural Motoru

Üç kural tipi tüm senaryoları karşılar. Dördüncüsü eklenmeden önce mevcut üçüyle
çözülüp çözülemediği sorgulanır.

| Tip | Teklifteki senaryolar |
|---|---|
| `zone_intrusion` | 5 (yaya yolu), 6 (sevkiyat/yükleme alanı), 7 (tır konumlanma) |
| `safe_distance` | 8 (güvenli mesafe) |
| `ppe_violation` | **Yeni kapsam** — baret / yelek |

Ortak çıktı: `Violation(rule_id, camera_id, track_ids, measured_value, zone_id, evidence)`.
Ortak filtre: cooldown. Ortak ilke: **kare değil, track bazlı karar.**

---

## 1. `zone_intrusion` — Bölge ihlali

**Soru:** Tanımlı sınıftan bir nesne, tanımlı bölgede, tanımlı süreden uzun kaldı mı?

| Parametre | Varsayılan | Anlam |
|---|---|---|
| `zone_id` | zorunlu | Hangi bölge |
| `target_classes` | zorunlu | `["person"]`, `["forklift","truck"]` vb. |
| `mode` | `inside` | `inside` = bölgede olmak ihlal · `outside` = bölge dışında olmak ihlal |
| `min_dwell_s` | 2.0 | Bölgede minimum kalış |
| `cooldown_s` | 120 | Track başına tekrar bastırma |

**`mode` neden var:** "Yaya yolunu kullan" kuralı aslında "yaya yolu **dışında** insan"
kuralıdır. Tek parametreyle üç senaryo çözülür:

| Senaryo | zone_type | target | mode |
|---|---|---|---|
| Yaya yolu kullanımı | pedestrian_path | person | outside |
| Yükleme alanında yaya | loading_area | person | inside |
| Tır yanlış konumda | truck_parking | truck | outside |

**Karar noktası:** bbox alt-orta noktası (zemin teması) poligonun içinde mi.

---

## 2. `safe_distance` — Güvenli mesafe

**Soru:** İnsan ile forklift/tır arasındaki gerçek dünya mesafesi eşiğin altına düştü mü?

| Parametre | Varsayılan | Anlam |
|---|---|---|
| `subject_classes` | `["person"]` | Korunan taraf |
| `object_classes` | `["forklift","truck"]` | Riskli taraf |
| `distance_m` | 3.0 | Eşik (metre) |
| `min_frames` | 5 | Ardışık kaç değerlendirmede eşik altında olmalı |
| `require_moving_vehicle` | true | Araç duruyorsa uyarı üretme |
| `min_speed_mps` | 0.3 | "Hareket halinde" eşiği |
| `zone_id` | nullable | Boşsa tüm kare |
| `cooldown_s` | 90 | Track çifti başına |

**Kalibrasyon zorunluluğu:** Kamera kalibre edilmemişse bu kural **çalışmaz** —
sessizce yaklaşık bir sonuç üretmez, açıkça pasif kalır ve arayüzde "kalibrasyon
bekleniyor" olarak görünür. Kalibre edilmemiş piksel mesafesi perspektifle
kat kat değişir; üretilen sayı yanıltıcı olur.

**`require_moving_vehicle` neden var:** Park halindeki tırın yanında duran şoför,
mesafe kuralını sürekli ihlal eder ama gerçek risk yoktur. Bu tek parametre,
sevkiyat alanındaki yanlış alarmların büyük kısmını keser.

**Hesap:** Her iki nesnenin ayak noktası homografi ile zemin düzlemine yansıtılır,
öklid mesafesi metre cinsinden hesaplanır.

---

## 3. `ppe_violation` — KKD ihlali

**Soru:** KKD zorunlu bölgede, yeterince görünür bir kişi, gerekli KKD'yi
yeterince tutarlı biçimde takmıyor mu?

> Tam gerekçe, veri toplama ve eğitim için: `04-KKD-BARET-YELEK.md`

| Parametre | Varsayılan | Anlam |
|---|---|---|
| `zone_id` | **zorunlu** | KKD kuralı bölgesiz tanımlanamaz |
| `required_ppe` | `["helmet","vest"]` | Alt küme seçilebilir |
| `min_person_height_px` | 120 (baret) / 80 (yelek) | Altında değerlendirme yok |
| `min_confidence` | 0.70 | Kalibre edilmiş güven eşiği |
| `window_size` | 15 | Kayan pencere (değerlendirme sayısı) |
| `min_valid_observations` | 8 | Penceredeki `unknown` olmayan minimum gözlem |
| `violation_ratio` | 0.75 | Geçerli gözlemlerin bu oranı `no` demeli |
| `min_dwell_s` | 3.0 | Bölgede minimum kalış |
| `require_full_bbox` | true | Kare kenarında kesik kutu değerlendirilmez |
| `cooldown_s` | 180 | Track başına |

### Üç durumlu karar — motorun en önemli kuralı

```
yes     → uyumlu, olay yok
no      → ihlal adayı, zamansal oylamaya girer
unknown → HİÇBİR ZAMAN olay üretmez
```

`unknown` üretilen durumlar: kişi çok küçük · kare kenarında kesik · başka nesneyle
ağır örtüşme · model güveni eşik altı · baş/gövde görünmüyor.

**Kanıtın yokluğu ihlalin varlığı değildir.** Bu cümle `rules/ppe.py` başına yorum
olarak yazılır ve testle korunur (`test_unknown_never_produces_event`).

### Olay kaydına yazılan kanıt

`events.details` içine:

```json
{
  "ppe": {
    "required": ["helmet"],
    "helmet": {"decision": "no", "valid_obs": 11, "negative_obs": 9, "mean_conf": 0.83},
    "vest": {"decision": "yes"},
    "person_height_px": 168,
    "model_version": "ppe-v3",
    "dwell_s": 5.2
  }
}
```

`model_version` olmadan "model iyileşti mi" sorusu cevaplanamaz. Zorunludur.

---

## 4. Cooldown — ortak filtre

Anahtar: `(rule_id, camera_id, track_id)` — mesafe kuralında `(rule_id, camera_id, track_id_pair)`.

Track kaybolup yeni ID ile döndüğünde cooldown sıfırlanır. Bu bilinen bir sınırdır:
aynı kişi yeni track ID alırsa tekrar uyarı üretebilir. Track kalıcılığını artırmak
(ByteTrack `track_buffer` parametresi) bunu azaltır; tamamen çözmek yeniden kimliklendirme
(re-ID) gerektirir → Phase 2.

**Anons cooldown'u ayrıdır ve daha uzundur.** Ekranda 3 olay görünmesi sorun değil;
hoparlörün 3 kez bağırması sorundur.

---

## 5. Yeni kural tipi ekleme prosedürü

1. `rules/` içine saf fonksiyon: `evaluate_<tip>(detections, zones, calibration, params) -> list[Violation]`
2. `schemas/rules.py` içine `params` Pydantic modeli
3. `rules/registry.py` içine kayıt
4. `tests/rules/test_<tip>.py` — en az: pozitif durum, negatif durum, sınır durum, `unknown`/eksik veri durumu, cooldown
5. Frontend'e parametre formu

Başka hiçbir dosyaya dokunulmaz. Bu şablon bozuluyorsa mimari sınır ihlal ediliyor demektir.
