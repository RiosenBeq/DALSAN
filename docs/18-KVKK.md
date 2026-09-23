# 18 - KVKK Uyum Kartı

> **Hukuki tavsiye değildir.** Bu sayfa docs/17 §10'un uygulanmış hâlidir: her
> yükümlülüğün üründe nerede karşılandığını gösterir. Kurul kararlarının çoğu
> yalnız arama özetleriyle doğrulanabildi (docs/16 §7); **her satır avukat
> teyidi bekler.** Veri sorumlusu müşteridir; aydınlatma metnini ve levhayı
> müşteri hazırlar (docs/00 "KVKK - atlanamaz").

Son güncelleme: 23.09.2026 (Faz 5c).

---

## 1. Uyum kartı

| Yükümlülük | Kaynak (docs/16 §7) | Üründeki karşılığı | Nerede | Avukat teyidi |
|---|---|---|---|---|
| Hukuki dayanak | KVKK m.5/2-ç (6331 m.4'ten doğan hukuki yükümlülük) ve m.5/2-f (meşru menfaat); Kurul 2022/797 | Aydınlatma metninde yazılır; açık rıza kutusu **konmaz** (2026/347) | Müşterinin aydınlatma metni | bekliyor |
| Aydınlatma | m.10'un beş unsuru; Tebliğ m.5; katmanlı yöntem (2020 duyurusu); 2023/2007 levha uygulaması | İki katman: kameralı alanlarda sarı zeminli levha (veri sorumlusu, "İSG amacıyla görüntü işlenmektedir", tam metnin yeri) + tam metin. Mevcut CCTV metni varsa yeni amaç için güncellenir (Tebliğ m.5/1-b) | Müşteri | bekliyor |
| Yüz tanıma yok | m.4 ölçülülük; 2022/797 | Yüz kırpığı, yüz gömmesi, Re-ID, iz → personel eşlemesi hiçbir tabloya yazılmaz; takip numarası oturum içi geçici kimliktir | `tests/test_kkd_toplama_kapisi.py` "saklanmayanlar" testi şemayı denetler | bekliyor |
| Ses işlenmez | 2020/212; 2023/2007; 8770 | Kamera akışından ses okunmaz; sistem anons ÇALAR ama ses kaydetmez | `analiz/kamera.py` (`cv2.VideoCapture` ses okumaz) | bekliyor |
| Amaç sınırı | 8770 (sürekli gözetim, performans/disiplin takibi meşru amaç değil) | Yalnız İSG olayları; kişi bazlı rapor ve "en çok ihlal yapan kişi" yok; uyarılar bölge ve konum bazlı | Rapor, Olaylar | bekliyor |
| İnsan onayı | m.11/1-g | Kişi aleyhine sonuç doğmadan İSG uzmanı incelemesi şartı aydınlatma metnine yazılır; ürün yalnız "inceleme" işaretleri sunar | Olay inceleme ekranı | bekliyor |
| Çalışan görüşü | 6331 m.18/1-b | Kurulum listesine "İSG kurulu / çalışan temsilcisine danışıldı" maddesi **eklenmedi**: uygulanabilirliği avukata sorulacak (docs/17 §10.1) | - | **soru** |
| Saklama | m.4/2-d, m.7; Silme Yönetmeliği (6 ayda bir periyodik imha; imha kaydı en az 3 yıl); sabit gün yok | Olay 180, fotoğraf 90, etiketsiz KKD kırpığı 30, sistem olayı 90 gün (`.env`, Ayarlar sayfası). Bakım günde bir çalışır ve her koşuda imha kaydı yazar (§4). Gün sayılarını müşteri ve avukat belirler (docs/17 S5 açık) | docs/06 §5; Ayarlar → KVKK | bekliyor |
| Olay dondurma | 8770 ("hukuki süreçte yalnız ilgili kayıt") | Olay sayfasında "Dondur": olay, kanıt fotoğrafı ve uyarı teslim kaydı süre dolsa da silinmez (§3) | Olay sayfası; `events.hold` | bekliyor |
| Erişim ve güvenlik | m.12; Kurul 2018/10; 8770 yetki matrisi | Tek yönetici şifresi (Docker'da zorunlu) + erişim izi (§2); giriş kilidi, köken ve sunucu adı denetimi, oturum sırrı (docs/17 §10.5) | Ayarlar → KVKK | bekliyor |
| Mahremiyet alanları | 2022/797; 8769 (dar açı, maskeleme) | Tuvalet, soyunma odası, duş, mescit, dinlenme ve emzirme odası görüş alanında olamaz; önce kamera açısı düzeltilir. Yazılım bunu göremez: her kamera sayfasında elle onaylanır, kamera adresi değişince onay kalkar | Kamera sayfası "Mahremiyet kontrolü"; kurulum listesi adım 9 | bekliyor |
| Rol ve sözleşme | m.12/2 müşterek sorumluluk | NextGen-müşteri veri işleyen sözleşmesi. Bulut, telemetri, yurt dışı aktarım yok; tek dış bağlantı model indirmedir (`analiz/model_indir.py`) ve kurulumdan sonra kapatılabilir | Sözleşme | bekliyor |
| Ağ bölümlendirmesi | m.12 teknik tedbir | Kameralar ayrı ağda; sunucu yalnız kamera ağına, yönetim ağına ve anons cihazlarına erişir. Belge ağ ekibiyle doldurulur | docs/06 §1.4 | bekliyor |
| KKD veri toplama | docs/00 (Rev.02) | Kapı SQLite'ta, yeniden başlatmadan ve gecikmesiz kapanır; açmak Rev.02 onayı ister; her değişiklik olay ve erişim izi bırakır | KKD sayfası | bekliyor |

## 2. Erişim izi (`access_log`)

Kişisel veriye dokunan ya da onu koruyan ayarı değiştiren her istek bir satır
bırakır: **zaman, istemci adresi, ne yapıldı, neye.** Ayarlar sayfasının en
altında "KVKK: erişim ve imha kayıtları" bölümünde okunur.

| Ne yapıldı (`action`) | Ne zaman yazılır | Neye (`target`) |
|---|---|---|
| `view_snapshot` | Kanıt fotoğrafı açıldı (olay listesi küçük resmi, olay sayfası, inceleme) | `event:<id>` |
| `view_ppe_crop` | KKD kırpığı açıldı | `sample:<id>` |
| `export_csv` | Olaylar CSV'si ya da rapor CSV'si indirildi | satır sayısı / dönem |
| `export_dataset` | KKD veri seti zip'i indirildi | örnek sayısı |
| `settings_change` | Ayarlar kaydedildi (yalnız gerçekten değişen ayarların **adları**); kamera mahremiyet onayı | `OLAY_SAKLAMA_GUN, …` / `camera:<id>` |
| `rule_change` | Kural kaydedildi, hazır kural eklendi, silindi; gölge / anons değişti | `rule:<id>` |
| `hold_change` | Olay donduruldu ya da dondurma kaldırıldı | `event:<id> hold=1/0` |
| `ppe_collection_gate` | KKD veri toplama açıldı ya da kapandı | `acik` / `kapali` |

- **Yazılmayanlar:** şifre, oturum çerezi, ayarın DEĞERİ, kamera ve hoparlör
  adresi. Bir test bunu şifreli bir kurulumda denetler (`tests/test_kvkk_izleri.py`).
- **"Kim" sınırı:** sistemde tek şifre vardır; kim olduğu, isteği yapan
  bilgisayarın adresidir. Aynı bilgisayarı kullanan iki kişi ayırt edilemez;
  araya bir vekil (proxy) girerse adres vekilin adresidir. Kişi bazlı rol ve
  kullanıcı docs/07 #5'tedir (docs/17 S5).
- **Tekrar:** aynı istemci aynı kaydı bir dakika içinde yeniden görüntülerse
  (sayfa yenileme, küçük resim) bir kez yazılır. Değişiklik ve dışa aktarım her
  seferinde yazılır.
- **Yazılamazsa:** istek yine sonuçlanır, günlüğe hata düşer. İSG uzmanının bir
  veritabanı kilidi yüzünden kanıta bakamaması daha kötü bir sonuç sayıldı.
- **Saklama:** erişim izi silinmez. Bir süre belirlenirse (S5) bakım ona göre
  genişletilir.

## 3. Olay dondurma (hukuki süreç)

1. Olay sayfasında "Hukuki süreç" bölümüne sebebi yazın (ör. iş kazası
   soruşturması, dava dosya numarası) ve **Dondur**'a basın. Sebep zorunludur.
2. Dondurulan olay listede "dondurulmuş" rozetiyle görünür. Olay, kanıt
   fotoğrafı ve uyarı teslim kaydı saklama süresi dolsa da silinmez.
3. Süreç bitince **Dondurmayı kaldır**. Saklama süresi dolmuşsa olay bir sonraki
   bakımda silinir; ekran bunu sorarak söyler.

Dondurma ve kaldırma erişim izine düşer. Yetki yönetici şifresinin sahibindedir
(docs/17 S5 varsayılanı).

## 4. İmha kaydı (`purge_log`)

Her bakım koşusu (günde bir) bir satır yazar: silinen olay, fotoğraf ve KKD
örneği sayısı, dondurulduğu için silinmeyen olay sayısı ve o günkü saklama gün
sayıları. Kişisel veri içermez. Silme Yönetmeliği imha kaydının en az 3 yıl
saklanmasını ister; bakım bu tabloyu hiç silmez.

## 5. Saklanmayanlar

Yüz kırpığı, yüz gömmesi, kişi adı ya da sicil numarası, iz → personel eşlemesi,
ses, ham video akışı. Yalnız kullanıcının yüklediği test videoları saklanır ve
bakım onlara dokunmaz. Şemada bunları taşıyabilecek bir sütun olmadığını bir
test denetler.

## 6. Yapılmayanlar

| Madde | Durum |
|---|---|
| Yüz bulanıklaştırma | Kodlanmadı: docs/17 S27 cevaplanmadı (kutu üstü yöntemi baret kanıtını siler, YuNet uzak yüzü bulamaz). |
| Roller ve kişi bazlı kullanıcı | Kodlanmadı: tek şifre (S5); docs/07 #5. |
| Olay klibi | Kodlanmadı: S5 varsayılanı "klip yok"; docs/07 #1. |
| Çalışan temsilcisine danışma maddesi | Avukat görüşü bekleniyor (§1). |

## 7. Operatöre açık sorular

- **S5:** Olay, fotoğraf ve KKD kırpığı kaç gün saklanacak? Veri sorumlusu kim?
  Dondurma yetkisi kimde? Erişim izi ne kadar saklanacak?
- **S6:** Kamera ağı ayrı bir VLAN'da mı? Görüş alanında mahremiyet beklentisi
  olan alan var mı? RTSP akışlarında ses kanalı var mı?
- **S27:** Yüz bulanıklaştırma isteniyor mu, hangi yöntemle?
- Çalışan temsilcisine danışma (6331 m.18/1-b) kurulum listesine girmeli mi?
