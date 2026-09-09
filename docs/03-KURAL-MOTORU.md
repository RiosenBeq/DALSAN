# 03 — Kural Motoru

Dört kural tipi tüm senaryoları karşılar. Beşincisi eklenmeden önce mevcut
dördüyle çözülüp çözülemediği sorgulanır.

| Tip | Teklifteki senaryolar |
|---|---|
| `zone_intrusion` | 5 (yaya yolu), 6 (sevkiyat/yükleme alanı), 7 (tır konumlanma) |
| `safe_distance` | 8 (güvenli mesafe) |
| `ppe_violation` | **Yeni kapsam** — baret / yelek |
| `vehicle_speed` | **Yeni kapsam** — fabrika içi hız sınırı (docs/07 #15'ten geldi) |

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

## 4. `vehicle_speed` — Araç hız sınırı

**Soru:** Forklift (ya da tır) fabrika içindeki hız sınırını aştı mı?

| Parametre | Varsayılan | Anlam |
|---|---|---|
| `target_classes` | `["forklift","truck"]` | Hız sınırına tabi araçlar |
| `speed_limit_mps` | 2.5 | Eşik (m/sn). 2,5 m/sn ≈ 9 km/sa |
| `window_size` | 5 | Kaç ölçümün **ortancasına** bakılır |
| `zone_id` | nullable | Boşsa tüm kare |
| `cooldown_s` | 90 | Track başına |

**Neden ayrı bir kural:** güvenli mesafe kuralı hızı yalnızca "araç hareket
halinde mi" sorusuna cevap vermek için kullanır. Yanında kimse olmadan hızlı
giden bir forklift, mesafe kuralına **görünmez**; oysa fabrika içi kazalarda hız
tek başına bir risktir.

**Kalibrasyon zorunluluğu** §2'dekiyle aynıdır ve aynı sebeptendir: hız, ayak
noktasının **zemindeki** yer değişiminden ölçülür. Kalibre edilmemiş kamerada
kural pasif kalır ve arayüzde "kalibrasyon bekleniyor" görünür.

**Neden ortanca, neden ortalama değil:** kare başına hız ölçümü gürültülüdür —
tespit kutusunun bir karelik oynaması ayak noktasını santimetrelerce kaydırır ve
0,2 saniyelik aralığa bölününce metre/saniyelik bir sıçrama gibi görünür. Beş
ölçümün dördü 0,5 m/sn, biri 20 m/sn ise **ortalama** 4,4 m/sn çıkar ve duran
forklift hız cezası yer; **ortanca** 0,5 m/sn kalır. Ekrana ve olay kaydına
yazılan sayı da bu ortancadır: kullanıcı sıçrama değerini değil aracın gerçek
hızını görür.

**Birim:** ayar `m/sn` tutulur (`Tespit.hiz_mps` ile aynı olsun diye), ekranda ve
olay kaydında `km/sa` karşılığı da yazılır — fabrika hız levhaları km/sa'dır.

**Hazır kural yok, bilerek:** bu kural en çok bölgesiz (tüm kare) anlamlıdır ve
"araç sahası" bölgesinin hazır kuralı zaten güvenli mesafedir. Kurallar
sayfasından tek formla kurulur.

---

## 5. Cooldown — ortak filtre

Anahtar: `(rule_id, camera_id, track_id)` — mesafe kuralında `(rule_id, camera_id, track_id_pair)`.

Track kaybolup yeni ID ile döndüğünde cooldown sıfırlanır. Bu bilinen bir sınırdır:
aynı kişi yeni track ID alırsa tekrar uyarı üretebilir. Track kalıcılığını artırmak
(ByteTrack `track_buffer` parametresi) bunu azaltır; tamamen çözmek yeniden kimliklendirme
(re-ID) gerektirir → Phase 2.

**Anons cooldown'u ayrıdır ve daha uzundur.** Ekranda 3 olay görünmesi sorun değil;
hoparlörün 3 kez bağırması sorundur.

---

## 5.1 Sayım, kural DEĞİLDİR

`rules/sayim.py` bu dosyadaki dört kural tipinin yanında durur ama onlardan
**ayrıdır**: ihlal üretmez, cooldown'a girmez, anons tetiklemez, olay yazmaz.
Yalnızca "bölgede kaç var" ve "kaç tanesi girdi" sorularını cevaplar.

Neden ayrı: bir sayı yanlışsa kimse yanlış uyarı almaz. Kural mantığıyla aynı
dosyaya konsaydı, sayım için yapılan her ayar ihlal kararını da riske atardı.

Sayım kural gerektirmez: bölge çizilen her kamerada kendiliğinden çalışır.
Ayrıntı ve üç sayının anlamı `02-MIMARI.md` §8'de.

## 6. Yeni kural tipi ekleme prosedürü

1. `backend/app/rules/<tip>.py` — saf değerlendirici sınıfı (`degerlendir(baglam) -> list[Ihlal]`)
2. `backend/app/rules/parametreler.py` — `params` Pydantic modeli + `PARAM_SEMALARI` kaydı
3. `backend/app/rules/motor.py` — `DEGERLENDIRICILER` kaydı
4. `tests/rules/test_<tip>.py` — en az: pozitif durum, negatif durum, sınır durum, eksik/ölçülemeyen veri durumu, cooldown
5. Arayüz: `web/ortak.py` (`KURAL_TIPLERI`, `VARSAYILAN_COOLDOWN_SN`), `web/kurallar.py`
   (`_formdan_params`), `templates/kural_form.html` (alan kümesi)

Başka hiçbir dosyaya dokunulmaz. Bu şablon bozuluyorsa mimari sınır ihlal ediliyor demektir.

**Şema kısıtı da işin parçasıdır.** `rules.rule_type` bir CHECK kısıtıyla
kapalıdır; yeni tip için ayrı bir göç betiği gerekir. SQLite'ta CHECK
değiştirmek tabloyu yeniden kurmaktır ve bu, yabancı anahtar zorlaması AÇIKKEN
tüm olay geçmişinin kural bağlantısını **sessizce siler** (ölçülerek
doğrulandı). Doğru yol `backend/sema/005_arac_hizi_kurali.sql` dosyasında
örneklenmiştir: betiğin başına `-- DALSAN-SEMA: YABANCI-ANAHTAR-KAPALI` işaret
satırı konur; `app/veritabani.py` bunu görüp anahtarı işlem dışında kapatır,
sonra geri açar ve `PRAGMA foreign_key_check` ile bağlantıların sağlam kaldığını
doğrular.

---

## Ek — Yaya yolu (yürüyüş yolu) kuralı

Fabrikadaki çizili yürüyüş yolu, `zone_intrusion` kuralının **`mode=outside`**
biçimiyle karşılanır: yaya yolu bölgesinin **dışında** kalan kişi ihlal üretir.
Ayrı bir kural tipi eklenmedi — mevcut tip bu davranışı zaten kapsıyor
(CLAUDE.md §3: en az parça).

Arayüzde tek tıkla kurulur (kamera sayfası → "… için yaya yolu kuralı ekle").
Kurduğu değerler:

| Alan | Değer | Neden |
|---|---|---|
| `rule_type` | `zone_intrusion` | mevcut tip yeter |
| `zone_type` | `pedestrian_path` | başka tipte bölgeye kurulamaz |
| `target_classes` | `["person"]` | yol kuralı yalnızca insan içindir |
| `mode` | `outside` | yolu KULLANMAYAN kişi ihlaldir |
| `min_dwell_s` | 5,0 | yolun kenarına bir adım atan kişi uyarı üretmemeli |
| `cooldown_s` | 180 | aynı kişi için üç dakikada bir uyarı yeter |
| `announcement_id` | `pedestrian_path` | "Lütfen yaya yolunu kullanınız." |

**Karar noktası** diğer bölge kurallarıyla aynıdır: kutunun **alt-orta noktası**
(zemin teması). Bölge, üzerine basılan zemin alanı olarak çizilmelidir.

**Bilinen sınır:** kural, karede görünen HER kişiyi değerlendirir. Kameranın
görüş alanına yol dışında kalan çalışma istasyonları da giriyorsa, o alanlar
sürekli ihlal üretir. Böyle bir sahnede yolu değil, **yasak alanı** çizip
`mode=inside` kullanmak daha doğrudur.
