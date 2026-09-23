# 16 - Dış Kaynak Doğrulama (Faz 1 girdisi)

**Tarih:** 2026-09-22 · **Depo durumu:** `4a36997` · **Girdi olduğu iş:** Faz 1 tasarımı (`docs/17-V2-TASARIM.md`) · **Dayandığı metin:** [`GOREV-TANIMI-V2.md`](GOREV-TANIMI-V2.md) §4.2-§4.11 ve EK A

## Bu belge ne için yazıldı

`GOREV-TANIMI-V2.md` DALSAN deposu okunmadan yazıldı. Dış dünya hakkında pek çok iddia içeriyor: veri seti lisansları, kütüphane sürümleri, Bluetooth ve TTS davranışı, ONNX Runtime paketleri, KVKK yükümlülükleri. Faz 1 tasarımı bu iddialara yaslanmadan önce her birini kaynağından kontrol ettik. Bu belge o kontrolün ham sonucudur. Karar vermez, karar için kanıt sunar.

Yöntem iki geçişten oluştu:

1. **Araştırma geçişi.** Her konu için bir bilgi kartı çıkarıldı: iddia, kaynak URL ve sayfadan kısa alıntı.
2. **Şüpheci geçiş.** Kartta "doğrulandı" denen her iddia ayrı bir ajan tarafından yeniden açıldı ve çürütülmeye çalışıldı. İki geçiş çeliştiğinde **ikinci geçişin kararı esas alındı.**

> **Uyarı 1: avukat teyidi gerekir.** KVKK, veri seti lisansı, CC / GPL / CPML yorumları ve "ticari kullanıma uygun" hükümleri **hukuki tavsiye değildir.** Müşteriye sunmadan, veri indirmeden ya da ticari teslimata başlamadan önce bir avukat bu belgedeki ilgili maddeleri kendi kaynağından okumalıdır. KVKK bölümündeki Kurul kararlarının çoğu yalnız arama özetleriyle doğrulanabildi (aşağıya bakın).
>
> **Uyarı 2: sürümler tarihlidir.** Bütün sürüm numaraları, tarihler ve "güncel", "en son" ifadeleri **2026-09-22** itibarıyladır. Örneğin supervision 0.30.5 bu belgenin yazıldığı gün PyPI'ye yüklendi. Kurulumdan önce ilgili PyPI sayfasına yeniden bakın.
>
> **Uyarı 3: erişim kısıtı.** Bu ortamdan şu alan adlarına erişilemedi: universe.roboflow.com, docs.roboflow.com, discuss.roboflow.com, kaggle.com, huggingface.co, data.mendeley.com, arxiv.org, creativecommons.org, kvkk.gov.tr, mevzuat.gov.tr, resmigazete.gov.tr, gnu.org, freedesktop.org, docs.docker.com, docs.opencv.org, supervision.roboflow.com, elinux.org, images.cv, makeml.app, pexels.com, apple.com, learn.microsoft.com, cocodataset.org, objects365.org. Erişilebilenler: raw.githubusercontent.com, storage.googleapis.com, pypi.org ve GitHub depolarının `git clone`'u. Birincil sayfa kapalı olduğunda resmi deponun kaynak dosyası kullanıldı. Örnekler: Creative Commons metinleri için CC'nin `cc-legal-tools-data` deposu, systemd için man XML'leri, Docker için BuildKit `reference.md`, KVKK metni için bağımsız konsolide kopyalar.

### Durum etiketleri

| Etiket | Anlamı |
|---|---|
| **DOĞRULANDI** | Birincil kaynakta ya da resmi kaynağın birebir kopyasında (GitHub/PyPI) okundu; alıntı sayfada var. |
| **DOĞRULANDI (özet)** | Birincil sayfa açılamadı ama birden çok bağımsız arama özeti ve ikincil kaynak tutarlı. Karar vermeden önce birincil metin okunmalı. Çoğu KVKK Kurul kararı bu durumda. |
| **DOĞRULANDI (yerel)** | DALSAN deposunda dosya ve satır okunarak ya da bu oturumdaki bir deneyle (pip kurulumu, ölçüm) doğrulandı. |
| **ÇÜRÜTÜLDÜ** | İddia yanlış ya da bayat. **Doğrusu** aynı satırda yazılı. |
| **DOĞRULANMADI** | Kaynak bulunamadı ya da açılamadı. Her bölümün sonunda ayrı listede durur. Tasarımda **olgu olarak kullanılmaz.** |

### En önemli on bulgu

1. **KKD verisi:** §4.7'deki üç adayın üçü de ticari kurulumda kullanılamaz: SH17 (CC BY-NC-SA 4.0, üstüne "yalnız eğitim/araştırma" kaydı), CHV (lisans yok), Pictor-PPE (lisans yok). Bu oturumda baret **ve** yelek içeren, lisansı birincil kaynaktan doğrulanmış ve ticari kullanıma açık bir set **bulunamadı.** Roboflow, Mendeley ve Kaggle adayları "koşullu" kalıyor: lisans satırı tarayıcıdan okunup kaydedilmeden indirilmemeli.
2. **Forklift verisi:** LOCO (TUM) **CC0 1.0** lisanslı; forklift, pallet truck (transpalet) ve palet sınıflarını içeriyor. Lisansı en temiz açık kaynak bu, ama §4.7'de yok. `loader` sınıfı için hiçbir açık kaynakta etiket yok.
3. **TTS:** `piper-tts` artık **GPL-3.0-or-later**. Tek Türkçe Piper sesi olan `tr_TR-dfki-medium`'un verisi CC BY-NC-SA ve ses, ticari sentezi dışlayan lessac tabanından ince ayarlanmış, yani **ticari kullanılamaz.** DALSAN dinamik metni zaten tarayıcı TTS'i ve HTTP anons cihazıyla karşılıyor.
4. **Bluetooth:** BlueZ ses taşımaz; A2DP için PipeWire ya da PulseAudio şart. `bleak` A2DP yapamaz. `bluetoothctl` etkileşimsiz modda `-a` bayrağını yok sayar, `-t` verilince çıkış kodu hep 0'dır. Konteynerde `--privileged` gereksizdir.
5. **ONNX Runtime:** `onnxruntime-gpu` ayrı bir pakettir. CPU paketiyle aynı ortama kurulursa CUDA sessizce kaybolur. 1.27 ve sonrası CUDA 13 ister. 1.19.2'den 1.30.0'a geçiş iki açıdan anlamlı: gömülü `onnx` sürümü (CVE-2026-14647) ve bu makinede ölçülen yaklaşık %25 CPU hızı.
6. **supervision:** `sv.ByteTrack` 0.28'de deprecated oldu, 0.31'de kaldırılıyor; 0.25.1'de kalınmalı. `docs/03`'teki `track_buffer` parametre adı yanlış, doğrusu `lost_track_buffer`. Ayrıca DALSAN'da kayıp iz ömrü yalnız **1 saniye.**
7. **KVKK:** "Yüz tanıma yapılmaz" kararı doğru. Ama dayanağı 2026/921 değildir, çünkü o karar yalnız mesai takibini kapsar. Dayanak m.4 ölçülülük ilkesi ve Kurul'un 2022/797 kararıdır. Kamera kaydı için sabit bir saklama süresi yoktur; ilke "mümkün olan en kısa süre ve otomatik imha"dır.
8. **Bekçi (watchdog):** Docker "unhealthy" durumdaki container'ı yeniden başlatmaz. Belgedeki systemd birimi bugün hiç başlamıyor (`app.main:uygulama`). "Takılınca süreçten çık" deseni Docker ve systemd'de işe yarar, ama paketlenmiş masaüstü uygulamasında Kontrol Paneli'ni de öldürür.
9. **Metrik:** Prometheus metin biçimi elle üretilebilir. Prometheus 3 `Content-Type` başlığını zorunlu tutar. `prometheus_client` paketine gerek yok.
10. **OpenCV:** FFmpeg arka ucunda `read()` varsayılan olarak **30 saniyeye kadar** bloklayabilir. `CAP_PROP_BUFFERSIZE` bu arka uçta hiçbir şey yapmaz. Zaman aşımı yalnız açılışta, parametreyle verilebilir.

---

## 1. KKD (baret/yelek) açık veri setleri ve lisansları

### Özet

§4.7'nin önerdiği üç KKD seti de ticari fabrika kurulumunda kullanılamaz. SH17 NC-SA lisanslı ve yazarı ayrıca "yalnız eğitim/araştırma" kaydı koymuş. CHV ile Pictor-PPE'nin hiç lisansı yok. Diğer adayların durumu da benzer:

- **SHWD:** MIT lisanslı, ama negatif örneklerinin bir kısmı yalnız araştırmaya açık SCUT-HEAD'den geliyor.
- **GDUT-HWD:** Deposu Apache-2.0, ama depo dışında tutulan verinin bu lisansa girdiği yazılmamış.
- **SFCHD:** Lisanssız. Oysa fabrika ortamına en yakın set bu.
- **Ultralytics Construction-PPE:** AGPL-3.0; ADR-002'ye aykırı.

Ticari kullanıma açık görünen (CC BY 4.0 / CC0 / Public Domain) Roboflow, Mendeley ve Kaggle setlerinin lisans satırları bu ortamdan birincil kaynaktan okunamadı. Şüpheci geçiş bunların bir kısmında sayıların bayat, bir kısmında lisansın hiç görünmediğini buldu. Creative Commons lisans metinleri CC'nin kendi deposundan doğrulandı.

### Olgular

| Olgu | Durum | Kaynak |
|---|---|---|
| SH17, CC BY-NC-SA 4.0 ile yayımlanmış. Depoda ayrı LICENSE dosyası yok (master dalında `LICENSE*` 404 veriyor); lisans yalnız README'de beyan ediliyor. | DOĞRULANDI | [SH17 README (master)](https://raw.githubusercontent.com/ahmadmughees/SH17dataset/master/README.md): "The SH17 dataset is released under CC BY-NC-SA 4.0 license." |
| SH17 yazarı NC'nin üstüne bir amaç sınırlaması da koymuş: eğitim, araştırma ve analiz dışında kullanılamaz. Kaggle meta alanına bakmaya gerek kalmıyor. | DOĞRULANDI | [SH17 README](https://raw.githubusercontent.com/ahmadmughees/SH17dataset/master/README.md): "intended for educational, research, and analysis purposes only." |
| SH17'de 8.099 görüntü, 75.994 örnek ve 17 sınıf var; `Helmet` ile `Safety-vest` bunların arasında. Yazarlar Ahmad ve Rahimi (JSSR, doi 10.1016/j.jnlssr.2024.09.002; arXiv 2407.04590). | DOĞRULANDI | [SH17 README](https://raw.githubusercontent.com/ahmadmughees/SH17dataset/master/README.md): "8,099 annotated images … 75,994 object instances" |
| SH17 görüntüleri Pexels'ten URL listesiyle indiriliyor. Pexels'in serbest lisansı, SH17'nin seçim ve etiket eserinin NC-SA olduğu gerçeğini değiştirmez. | DOĞRULANDI | [SH17 README](https://raw.githubusercontent.com/ahmadmughees/SH17dataset/master/README.md): "downloaded via list of URLs from the source using download_from_pexels.py script." |
| CC BY-NC-SA 4.0 ticari kullanımı yasaklar ve türevlerin aynı lisansla dağıtılmasını şart koşar. NC tanımı ("commercial advantage or monetary compensation") DALSAN'ın ticari teslimatını kapsar. | DOĞRULANDI | [CC deed, CC'nin deposu](https://raw.githubusercontent.com/creativecommons/cc-legal-tools-data/main/docs/licenses/by-nc-sa/4.0/deed.en.html): "You may not use the material for commercial purposes." |
| CC BY 4.0 ticari kullanıma izin verir; şartları atıf yapmak ve yapılan değişikliği belirtmektir. Deed, kişilik ve mahremiyet haklarının kullanımı ayrıca sınırlayabileceği uyarısını da taşır. | DOĞRULANDI | [CC BY 4.0 deed](https://raw.githubusercontent.com/creativecommons/cc-legal-tools-data/main/docs/licenses/by/4.0/deed.en.html): "for any purpose, even commercially." |
| CC0 1.0 ticari kullanım dahil her kullanımı izinsiz serbest bırakır. Görüntüdeki kişilerin kişilik ve mahremiyet hakları bundan etkilenmez; yani KVKK açısından "Public Domain" etiketi rıza kanıtı sayılmaz. | DOĞRULANDI | [CC0 deed](https://raw.githubusercontent.com/creativecommons/cc-legal-tools-data/main/docs/publicdomain/zero/1.0/deed.en.html): "nor are the rights that other persons may have … such as publicity or privacy rights." |
| CHV'de 1.330 görüntü ve 6 sınıf var: person, vest ve 4 renkte baret. Görüntüler "İnternet ve açık veri setleri"nden toplanmış, yani kökeni belirsiz. | DOĞRULANDI | [CHV README](https://raw.githubusercontent.com/ZijianWang-ZW/PPE_detection/master/README.md): "only 1,330 high-quality images among 10,000 ones from the Internet and open datasets are selected." |
| CHV'nin lisansı yok: LICENSE dosyası 404 veriyor, README'de yalnız "free use" ifadesi ve atıf isteği var. Bu durumda hukuken "tüm haklar saklı" varsayılır. | DOĞRULANDI | [CHV README](https://raw.githubusercontent.com/ZijianWang-ZW/PPE_detection/master/README.md): "The dataset is open for free use" |
| Pictor-v3'te 774 kitle kaynaklı ve 698 web'den toplanmış görüntü var; sınıflar worker, hat, vest. | DOĞRULANDI | [Pictor-PPE README](https://raw.githubusercontent.com/ciber-lab/pictor-ppe/master/README.md): "774 crowd-sourced and 698 web-mined images." |
| Pictor-PPE'nin lisansı yok: LICENSE 404, README'de lisans cümlesi yok, yalnız atıf isteği var. | DOĞRULANDI | [Pictor-PPE README](https://raw.githubusercontent.com/ciber-lab/pictor-ppe/master/README.md): "Please cite the article if you use the dataset" |
| İddia: "Roboflow'daki pictor-ppe yeniden yüklemesi CC BY 4.0 yazıyor, dolayısıyla Pictor-PPE CC BY 4.0'dır." **Doğrusu:** Kaynak depo lisanssız ve üçüncü bir kişi başkasının verisini yeniden lisanslayamaz. Roboflow'daki lisans satırı yalnız yükleyicinin beyanıdır. | ÇÜRÜTÜLDÜ | [Pictor README](https://raw.githubusercontent.com/ciber-lab/pictor-ppe/master/README.md) · [Roboflow yeniden yüklemesi](https://universe.roboflow.com/liug0019-e-ntu-edu-sg/pictor-ppe-worker) (sayfa engelli) |
| SHWD'de 7.581 görüntü var; sınıflar `hat` ve `person`. Depo LICENSE'ı MIT. Pozitif örnekler Google ve Baidu görsel aramasından alınmış, bu yüzden görüntü telifi belirsiz. | DOĞRULANDI | [SHWD README](https://raw.githubusercontent.com/njvisionpower/Safety-Helmet-Wearing-Dataset/master/README.md): "The positive objects got from goolge or baidu" |
| İddia: "SHWD MIT lisanslı olduğu için ticari kullanıma tamamen açık." **Doğrusu:** Negatif örneklerin bir kısmı SCUT-HEAD'den geliyor ve SCUT-HEAD yalnız akademik araştırmaya açık. MIT lisansı yalnız depo sahibinin kendi katkısını kapsar. | ÇÜRÜTÜLDÜ | [SCUT-HEAD README](https://raw.githubusercontent.com/HCIILAB/SCUT-HEAD-Dataset-Release/master/README.md): "free to the academic community for research purpose usage only." |
| GDUT-HWD'de 3.174 görüntü, 18.893 örnek ve 5 sınıf var (blue, white, yellow, red, none). Depo Apache-2.0, veri Baidu ve Google Drive'da. Apache-2.0'ın depo dışındaki veriyi kapsadığı hiçbir yerde yazmıyor. | DOĞRULANDI | [GDUT-HWD README](https://raw.githubusercontent.com/wujixiu/helmet-detection/master/README.md): "It contains 18,893 instances falling into 5 classes" |
| SFCHD'de 12.373 görüntü ve 7 kategori var (Person, Safety Helmet, Safety Clothing, Other Clothing, Head, Blurred Clothing, Blurred Head). Görüntüler iki gerçek kimya tesisinden. LICENSE 404, makalede de lisans cümlesi yok. | DOĞRULANDI | [SFCHD deposu](https://github.com/lijfrank-open/SFCHD-SCALE) (depodaki makale PDF'i): "derived from two authentic chemical plants, comprising 12,373 images, 7 categories" |
| SFCHD README'sindeki karşılaştırma tablosu Pictor-v3 için "1.330 görüntü / 6 sınıf" yazıyor. Bu sayılar CHV'ye ait. Pictor ve CHV sayıları bu tablodan alınmamalı. | DOĞRULANDI | [SFCHD README](https://raw.githubusercontent.com/lijfrank-open/SFCHD-SCALE/main/README.md) ile Pictor ve CHV README'lerinin karşılaştırması |
| Ultralytics Construction-PPE: 1.416 görüntü ve 11 sınıf. Yelek için "no_vest" sınıfı yok. Lisans AGPL-3.0, bu da ADR-002'ye aykırı. | DOĞRULANDI | [Doküman kaynağı](https://raw.githubusercontent.com/ultralytics/ultralytics/main/docs/en/datasets/detect/construction-ppe.md): "developed and released under the AGPL-3.0 License" |
| SHEL5K, Kaggle SHD'nin 5.000 görüntüsünü 6 sınıfla (Helmet, Head, Head with helmet, Person with helmet, Person without helmet, Face) yeniden etiketliyor. Depoda LICENSE yok; yelek sınıfı yok. | DOĞRULANDI | [SHEL5K deposu](https://github.com/MoyoG/SHEL5K): "an enhanced version of the SHD (Safety Helmet Detection) dataset" |
| İddia: "Roboflow 100 içindeki 100 setin tamamı CC BY 4.0." **Doğrusu:** Birincil kaynaklar bunu desteklemiyor. Benchmark README'sinde lisans geçmiyor, LICENSE yalnız kodun MIT lisansı. Geçerli lisans, her setin orijinal Universe yüklemesinin lisansıdır (`construction-safety-gsnvb` → `computer-vision/worker-safety`). | ÇÜRÜTÜLDÜ | [RF100 README](https://raw.githubusercontent.com/roboflow/roboflow-100-benchmark/main/README.md) (lisans ifadesi yok) |
| İddia: "Roboflow Construction Site Safety'de 10 sınıf var (Hardhat … vehicle)." **Doğrusu:** Bu liste Kaggle aynasının eski sürümüne ait. Güncel projede 25 sınıf var ve proje çok sürümlü (v1 'original_raw-images' … v30). İndirilecek sürüm numarası sabitlenmeli. | ÇÜRÜTÜLDÜ (özet) | [Universe projesi](https://universe.roboflow.com/roboflow-universe-projects/construction-site-safety) (engelli; arama özeti) |
| İddia: "Mendeley `zkzghjvpn2` setinde 3.212 görüntü var ve Google Images da kaynaklar arasında." **Doğrusu:** Bu v2'ye ait bir bilgi. Güncel v6'da 2.286 görüntü var ve kaynaklar "GitHub, Kaggle, and Roboflow" olarak yazılı. Verinin lisans satırı okunamadı. | ÇÜRÜTÜLDÜ (özet) | [Mendeley v6](https://data.mendeley.com/datasets/zkzghjvpn2/6) (engelli; arama özeti) |
| DALSAN'ın mevcut planı kamu setini yalnız ön eğitim için kullanıyor. İnce ayar ve değerlendirme DALSAN verisiyle yapılıyor; kamu verisindeki başarı müşteriye raporlanmıyor. | DOĞRULANDI (yerel) | [04-KKD-BARET-YELEK.md](04-KKD-BARET-YELEK.md) satır 179: "değerlendirmeyi yalnızca DALSAN verisiyle yap." |

**Önemli sonuç:** Bu oturumda baret **ve** yelek içeren, lisansı birincil kaynaktan doğrulanmış, ticari kullanıma açık bir KKD seti bulunamadı. Aşağıdaki "DOĞRULANMADI" listesindeki adaylar ancak operatör tarayıcıda lisans satırını okuyup kaydettikten sonra kullanılabilir.

### DOĞRULANMADI

- **Roboflow Universe kuralı:** "Lisans belirtilmemişse yazar tüm hakları saklı tutar." docs.roboflow.com engelli; tek bir arama özetinden geliyor.
- **Construction Site Safety** (`roboflow-universe-projects`): 717 ham görüntü ve CC BY 4.0 bilgisi iki arama özetinde tutarlı, ama sayfa açılamadı.
- **Safety Vests** (`roboflow-universe-projects`): 3.897 görüntü var. CC BY 4.0 lisansı Universe özetinde **geçmiyor**; Kaggle aynasından (adilshamim8) karışmış olabilir. Sınıf adları doğrulanmadı.
- **HardHat & SafetyVest** (`ppe-kit-detection`): 22.068 görüntü, CC BY 4.0, Mayıs 2024 (arama özeti). Kökeni ve sınıfları bilinmiyor; başka setlerin, belki NC setlerin birleşimi olabilir.
- **Hard Hat Universe** (`ppe-pnqgr`): 8.051 görüntü. "Public Domain" lisansı **hiçbir özette geçmiyor.**
- **ppe detection public** (`ppe-wqipw`): 48 sınıf ve CC BY 4.0 arama özetinde var, görüntü sayısı yok. `amitslonimski111` hesabındaki "PPE detection" seti hiçbir kaynakla doğrulanmadı.
- **Hard Hat Workers** (`joseph-nelson`): 7.035 görüntü, Public Domain (arama özeti). Make ML kökeni ve "Northeastern University - China" atfı doğrulanamadı; `makeml.app` engelli.
- **Kaggle `andrewmvd` Safety Helmet Detection:** 5.000 görüntü, CC0 (Dataset Ninja ve HF özetleri). Kaggle'ın yapısal "License" alanı okunamadı.
- **SHEL5K'nın Mendeley kaydındaki CC BY 4.0:** Özet, makalenin CC BY lisansıyla verinin lisansını karıştırmış olabilir.
- **Mendeley `zkzghjvpn2` v6 ve `8vf7z6v5sb` (5-Class, Kasım 2025):** Lisans satırları, sınıflar ve sayılar okunamadı.
- **SODA** (19.846 görüntü, 15 sınıf): Lisans ve erişim koşulu bilinmiyor.
- **Kaggle `snehilsanyal` aynası** (2.801 görüntü, "CC BY 4.0"): Birincil kaynak Roboflow projesi.
- **Pexels lisansındaki "compile content to create a competing service" yasağı:** pexels.com engelli.

### Projeye öneri (en az parça)

1. **İki liste tut.** "Kullanılamaz" listesi kesindir (karar tablosuna bakın). "Koşullu" adaylar ancak operatör Universe veya Mendeley sayfasındaki lisans satırını tarayıcıda okuyup ekran görüntüsünü aldıktan sonra indirilir. Öncelik Roboflow'un kendi hesabındaki (`roboflow-universe-projects`) setlerde: **Construction Site Safety** (baret, yelek ve `NO-Hardhat` / `NO-Safety Vest` negatifleri) **sürüm numarası sabitlenerek**, ardından **Safety Vests.**
2. **Yeni paket ekleme.** Roboflow SDK'sı ya da `roboflow` pip paketi gerekmez. Sayfadan "YOLO txt" ya da "COCO JSON" zip'i bir kez indirilir. ADR-003'ün kişi kırpıntısı sınıflandırıcısı için kırpıntıları stdlib (`zipfile`, `pathlib`, `json`) ve zaten kurulu OpenCV ile çıkaran yaklaşık 40 satırlık tek bir `tools/` betiği yazılır.
3. **Kamu verisi ürünle dağıtılmaz.** Yalnız model ağırlığı üretmek için kullanılır. İnce ayar ve bütün değerlendirme DALSAN verisiyle yapılır ([04 §4.4](04-KKD-BARET-YELEK.md) zaten böyle diyor). Böylece CC BY atıf yükümlülüğü belgeye iner; görüntü telifi ve KVKK riski ürün paketine girmez.
4. **Kanıt dosyası tut.** Mevcut `LICENSE-THIRD-PARTY` dosyasına her set için şunlar yazılır: ad, URL, **sürüm numarası**, indirme tarihi, lisans satırının indirme anındaki ekran görüntüsü, zip içindeki `README.roboflow.txt` / `README.dataset.txt` ve BibTeX atfı. Roboflow'da yükleyici lisansı sonradan değiştirebilir, bu yüzden ekran görüntüsü önemli.
5. **İndirmeden önce köken kontrolü yap.** Yeni bir araç gerekmez. Büyük birleşik setlerin (ör. 22 bin görüntülük HardHat & SafetyVest) README'sinde SH17, Pictor ya da CHV izi varsa set havuzdan çıkarılır.
6. **SH17 kestirmesini deneme.** "Pexels URL listesini alıp görüntüleri kendimiz indirip etiketleriz" yolu MVP'de denenmez. Seçim listesi de NC-SA eserin parçası sayılabilir; hukuki görüş olmadan gri alan.
7. **Kaggle aynalarından indirme.** Kaggle'ın "License" alanı yükleyicinin serbest seçimidir. Birincil Roboflow ya da Mendeley sayfası kullanılır.
8. **Yalnız baret içeren setleri gerektiğinde ekle.** Hard Hat Workers, SHEL5K ve andrewmvd yalnız `helmet` çıkışına yarar. MVP'de gerekmiyorsa eklenmez (altın kural 1).

### Açık sorular

- CC BY atıfları kapalı üründe nerede gösterilecek? Sözleşme eğitim verisi lisanslarının müşteriye beyanını şart koşuyor mu?
- Operatör "koşullu" listedeki sayfaları tarayıcıda açıp lisans satırlarını kaydedecek mi, kim yapacak?
- HardHat & SafetyVest (22 bin görüntü) hangi setlerin birleşimi?
- Mendeley `zkzghjvpn2` v6 havuzda kalsın mı, yoksa yalnız Roboflow'un kendi hesabındaki iki set mi kullanılsın?
- Kamu verisi için bir saklama kuralı gerekli mi? `04 §4.3` DALSAN kırpıntıları için silme öngörüyor; kamu seti için bir şey yazmıyor.
- Yelek politikası (`04 §5.3`): Kamu setlerinde "vest" reflektif yelek demek. DALSAN'da mont ya da iş ceketi de yelek sayılacaksa kamu verisiyle ön eğitim yanıltıcı olur.

---

## 2. Forklift, tır ve iş makinesi verisi; YOLOX ince ayarı

### Özet

Forklift COCO'da, Objects365'te ve Open Images'ın kutulu sınıflarında **yok.** LVIS'te var ama "common" frekans sınıfında, yani az örnekli. Lisansı en temiz açık kaynak **LOCO** (TUM, CC0 1.0): forklift, pallet truck (§4.1'deki `pallet_jack`) ve pallet içeriyor. Roboflow'daki forklift setlerinin hiçbiri bu ortamdan açılamadı. Birinin görüntüleri ticari kullanıma kapalı images.cv'den geliyor.

YOLOX'un özel veriyle eğitim belgeleri ve kodu birebir doğrulandı. Ancak depo 2022 dönemi bağımlılıklarla duruyor ve export betiği PyTorch 2.5 ve sonrasında çalışmıyor (§5'e bakın).

### Olgular

| Olgu | Durum | Kaynak |
|---|---|---|
| Forklift COCO 2017'nin 80 sınıfı arasında yok; `person`, `car` ve `truck` var. | DOĞRULANDI | [YOLOX coco_classes.py](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/yolox/data/datasets/coco_classes.py) (80 girdi, "forklift" 0 eşleşme) |
| **LOCO** (TUM fml) CC0 1.0 lisanslı. 37.988 görüntünün 5.593'ü elle etiketli; toplam 152.421 anotasyon. Sınıflar: forklift, pallet truck, pallet, small load carrier, stillage. Anotasyon COCO biçiminde (`rgb/loco-all-v1.json`). **`person` sınıfı yok.** Görüntüler elde taşınan kamerayla çekilmiş, sabit kamera perspektifinden farklı. İndirme bağlantısı `go.mytum.de` engelli. | DOĞRULANDI | [LOCO README](https://raw.githubusercontent.com/tum-fml/loco/main/README.md): "Annotated classes include forklifts, pallet trucks, pallets, small load carriers and stillages." · [LICENSE](https://raw.githubusercontent.com/tum-fml/loco/main/LICENSE) "CC0 1.0 Universal" |
| Objects365'te (365 sınıf) forklift yok. Araçla ilgili sınıflar: Truck (65), Pickup Truck (87), Machinery Vehicle (109), Trolley (124), Crane (131), Fire Truck (188), Heavy Truck (199). İki bağımsız YAML kopyası tutarlı. | DOĞRULANDI | [Objects365.yaml (yolov5)](https://raw.githubusercontent.com/ultralytics/yolov5/master/data/Objects365.yaml): "65: Truck … 109: Machinery Vehicle" |
| Objects365 anotasyonları CC BY 4.0. Görüntülerin telifi konsorsiyumda değil, Flickr şartlarına tabi; görüntüler **yeniden dağıtılamaz.** Tam indirme yaklaşık 712 GB. | DOĞRULANDI | [DaTaSeg LICENSE (orijinal metnin birebir kopyası)](https://raw.githubusercontent.com/google-research-datasets/DaTaSeg-Objects365-Instance-Segmentation/main/LICENSE): "You will NOT distribute the above images." |
| Open Images V7'de anotasyonlar CC BY 4.0, görüntüler "CC BY 2.0 olarak listelenmiş". Google görüntü lisansları için garanti vermiyor; her görüntü tek tek kontrol edilmeli. | DOĞRULANDI | [OI V7 facts](https://storage.googleapis.com/openimages/web/factsfigures_v7.html): "The images are listed as having a CC BY 2.0 license." |
| İddia: "Forklift, Open Images V7'nin 600 kutulu sınıfından biri." **Doğrusu:** Kutulu sınıf listesinde (601 girdi) forklift yok. Forklift yalnız görüntü düzeyinde etiket. | ÇÜRÜTÜLDÜ | [boxable CSV](https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv) ("forklift" 0 eşleşme) |
| Open Images V7'nin görüntü düzeyindeki 20.931 sınıfı arasında `Forklift truck` (/m/01jfkf), `Pallet`, `Pallet jack` ve `Construction equipment` var. Bunların hiçbiri için kutu anotasyonu yok. | DOĞRULANDI | [class-descriptions CSV](https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions.csv): "/m/01jfkf,Forklift truck" |
| Open Images V7'de 1,4 milyon görüntüde 5.827 sınıf için 66,4 milyon nokta etiketi var. Bunlar kutu değil. Kartta doğrulanmamış görünüyordu; şüpheci geçiş resmi sayfadan doğruladı. | DOĞRULANDI | [OI V7 facts](https://storage.googleapis.com/openimages/web/factsfigures_v7.html): "66.4M point-level labels over 1.4M images, covering 5,827 classes" |
| LVIS v1'de `forklift` var: id 470, frequency `c` (common). Toplam 1.203 kategori. | DOĞRULANDI | [detectron2 lvis_v1_categories.py](https://raw.githubusercontent.com/facebookresearch/detectron2/main/detectron2/data/datasets/lvis_v1_categories.py): "'synonyms': ['forklift'], 'id': 470" |
| LVIS'te `truck` (1123), `pickup_truck`, `trailer_truck`, `tow_truck`, `garbage_truck`, `tractor_(farm_equipment)`, `bulldozer` (r) ve `cart` var. `loader`, `crane`, `excavator` ve sevkiyat paleti **yok.** `palette` (LVIS id 750; Ultralytics'in 0 tabanlı indeksiyle 749) ressam paletidir. | DOĞRULANDI | Aynı dosya: "'synset': 'palette.n.02' … 'id': 750" |
| İddia: "lvis-api README, LVIS görüntülerinin COCO 2017'den alındığını söylüyor." **Doğrusu:** README yalnız "159,623 images (100k train, 20k val, 20k test-dev, 20k test-challenge)" diyor. COCO 2017 kökeni başka kaynaklardan doğrulandı: TFDS builder görüntüleri doğrudan `images.cocodataset.org/zips/train2017.zip` adresinden indiriyor. | ÇÜRÜTÜLDÜ (alıntı) | [TFDS LVIS builder](https://raw.githubusercontent.com/tensorflow/datasets/master/tensorflow_datasets/datasets/lvis/lvis_dataset_builder.py) · [lvis-api README](https://raw.githubusercontent.com/lvis-dataset/lvis-api/master/README.md) |
| LVIS anotasyonları CC BY 4.0 lisanslı. | DOĞRULANDI | [gecko ATTRIBUTION.md](https://raw.githubusercontent.com/google-deepmind/gecko_benchmark_t2i/main/ATTRIBUTION.md): "LVIS annotations are licensed under CC-BY 4.0." |
| Roboflow verileri COCO JSON biçiminde dışa aktarabiliyor; YOLOX de bu biçimi okuyor. | DOĞRULANDI | [roboflow-python README](https://raw.githubusercontent.com/roboflow/roboflow-python/main/README.md): `format="coco", # annotation format: coco, yolov8, …` |
| SelimSavas forklift seti: 3.000 görüntü, forklift ve people sınıfları. Görüntüler ImageNet, Roboflow ve Kaggle'dan; lisans yok. | DOĞRULANDI | [SelimSavas README](https://raw.githubusercontent.com/SelimSavas/forklift-and-people-detection-with-YOLOv5/main/README.md): "from ImageNet, Roboflow and Kaggle platform" |
| YOLOX Apache License 2.0 lisanslı (Copyright 2021-2022 Megvii Inc.). | DOĞRULANDI | [YOLOX LICENSE](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/LICENSE) |
| YOLOX'un bakım durumu: PyPI'deki son sürüm 0.3.0 (22 Nis 2022), son commit 8 Haz 2025. `requirements.txt` içinde `torch>=1.7` ve `onnx-simplifier==0.4.10` var. Bu yüzden eğitim pip paketiyle değil, depo klonuyla yapılır. | DOĞRULANDI | [PyPI yolox](https://pypi.org/pypi/yolox/json): "0.3.0" · upload "2022-04-22" |
| Özel veriyle eğitim belgesi COCO ve VOC biçimlerini destekliyor; örnek Exp dosyaları `exps/example/custom` altında. | DOĞRULANDI | [train_custom_data.md](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/docs/train_custom_data.md): "We currently support COCO format and VOC format." |
| İnce ayar komutu: `python tools/train.py -f <Exp> -d 8 -b 64 --fp16 -o -c <ağırlık>`. Ön eğitimli ağırlıkla sınıf sayısı farklı olunca şekli uymayan tensörler `load_ckpt()` tarafından uyarıyla atlanıyor, sınıflandırma başı sıfırdan başlıyor. | DOĞRULANDI | [train_custom_data.md](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/docs/train_custom_data.md): "Don't worry for the different shape of detection head … we will handle it" |
| Özel Exp şablonu (`exps/example/custom/yolox_s.py`) şu değerleri kullanıyor: `data_dir="datasets/coco128"`, `num_classes = 71`, `max_epoch = 300`, depth 0.33, width 0.50. | DOĞRULANDI | [custom/yolox_s.py](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/exps/example/custom/yolox_s.py) |
| Dizin sözleşmesi: `<data_dir>/annotations/<json>`, `<data_dir>/train2017/` ve `<data_dir>/val2017/`. Sınıf indeksi, sıralı `category_id` listesindeki konumdur. | DOĞRULANDI | [coco.py](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/yolox/data/datasets/coco.py): `self.class_ids = sorted(self.coco.getCatIds())` |
| YOLOX-Tiny Exp: depth 0.33, width 0.375, girdi ve test boyutu (416,416), `enable_mixup = False`. Temel Exp'te (`yolox_base`) boyut (640,640) ve `num_classes = 80`. | DOĞRULANDI | [yolox_tiny.py](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/exps/default/yolox_tiny.py) |
| Resmi COCO sonuçları: YOLOX-s 640 boyutta 40.5 mAP, 9.0M parametre, 26.8 GFLOPs. YOLOX-Tiny 416 boyutta 32.8 mAP, 5.06M parametre, 6.45 GFLOPs. | DOĞRULANDI | [YOLOX README](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/README.md) (ana tablo; "Legacy models" tablosuyla karıştırılmamalı) |
| Eğitim çıktısı `YOLOX_outputs/<exp_adı>/` altına yazılıyor: `best_ckpt.pth`, `latest_ckpt.pth`, `last_epoch_ckpt.pth`. En iyi kontrol noktası doğrulama AP50:95 değerine göre seçiliyor. | DOĞRULANDI | [trainer.py](https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/main/yolox/core/trainer.py): `update_best_ckpt = ap50_95 > self.best_ap` |

### DOĞRULANMADI

Aşağıdaki Roboflow sayfalarının hiçbiri açılamadı; bilgiler yalnız arama özetlerinden.

- `csv2tfrecord/forklift-detection`: 7.383 görüntü, CC BY 4.0, Aralık 2023. **Sınıf listesi hiç görülmedi.**
- `CONTIL/Forklift-Dataset`: 1.606 görüntü. 4 sınıflık liste (forklift, worker, load, others) ve CC BY 4.0 lisansı ikinci turda hiçbir özette görünmedi.
- `Phantom/forklift-1`: 1.202 görüntü, sınıflar forklift, pallet, pallet_truck, stillage; CC BY 4.0. Sınıf kümesi LOCO'nunkiyle örtüşüyor, **büyük olasılıkla LOCO'nun yeniden yüklemesi.** Orijinali kullanılmalı.
- `Mohamed Traore/forklift` (421 görüntü) ve Hugging Face aynası `keremberke/forklift-object-detection` (295/84/42 bölünme). Görüntüler images.cv'den dışa aktarılmış.
- **images.cv şartları:** "non-commercial research", "does not grant you a commercial license to any underlying image". Arama özeti; site engelli. Operatör güncel metni teyit etmeli.
- `Baxter/ForkLift` (253 görüntü) ve `HITSZ/Forklift and Human` (1,9 bin görüntü, `cart` ve `person`). `cart` sınıfının forklift olup olmadığı bilinmiyor.
- **Roboflow forumu:** CC BY-NC-SA ile yayımlanmış setlerin CC BY 4.0 olarak yeniden yüklendiğine dair şikâyet (arama özeti).
- **Objects365 "Non-Commercial" etiketi:** İkincil sitelerde geçiyor, resmi lisans metninde yok.
- **COCO görüntülerinin Flickr şartlarına ve görüntü başına lisansa tabi olduğu:** cocodataset.org engelli.
- **LVIS `c` frekansının "11-100 eğitim görüntüsü" tanımı.**

### Projeye öneri (en az parça)

1. **Veri kaynağı sırası:**
   1. Müşteri kameralarından, KVKK dayanağı belgelenmiş birkaç yüz kare. Alan kayması için en değerli kaynak bu.
   2. **LOCO** (CC0): forklift, `pallet_jack` (LOCO'da "pallet truck") ve palet.
   3. LVIS'teki forklift örnekleri. Anotasyonlar CC BY 4.0, görüntüler COCO/Flickr; kullanmadan önce hukuki görüş alınmalı.
   4. Roboflow setleri, ancak lisans satırı ve görüntü kökeni tarayıcıdan teyit edilirse.

   **Kullanma:** Traore seti ve kopyaları (images.cv kaynaklı), SelimSavas seti (lisanssız, ImageNet kaynaklı).
2. **Objects365 ve Open Images MVP'ye alınmaz.** Objects365'te forklift yok ve indirme 712 GB. Open Images'ta forklift kutusu yok. `truck` ve `car` için COCO ön eğitimli ağırlık zaten yeterli bilgi taşıyor.
3. **Sınıf listesi budanır.** `loader` için hiçbir açık kaynakta sınıf yok. Sahada yoksa MVP'den çıkar, varsa yalnız müşteri görüntüsüyle etiketlenir. `pallet_jack` LOCO'dan gelir. LOCO'da `person` olmadığı için kişi bilgisi COCO ağırlığından ve müşteri karelerinden sağlanır.
4. **Yeni kütüphane ekleme.** COCO JSON'ları birleştirme, sınıf adlarını eşleme (ör. LOCO "pallet truck" → `pallet_jack`, CONTIL "worker" → `person`) ve `category_id`'yi projenin sınıf listesine çevirme işi stdlib `json` ve `pathlib` ile yaklaşık 50 satırlık tek bir betiktir. Çıktı YOLOX dizin sözleşmesine uyar.
5. **Eğitim ortamı çalışma zamanından ayrılır.** Eğitim YOLOX depo klonuyla, ayrı bir venv'de ve GPU'lu makinede yapılır. Ürüne yalnız `.onnx` dosyası girer. Export için PyTorch 2.4 ya da daha eski bir sürüm sabitlenir, ya da tek satırlık bir yama yapılır (§5).
6. **Model boyutu donanıma göre seçilir.** CPU'da YOLOX-Tiny @416, GPU'da YOLOX-s @640. İkisi de resmi ağırlıktan başlar.
7. **Export bayrakları mevcut kodla hizalanır.** `tespit.py` decode işini kendisi yaptığı için `--decode_in_inference` kullanılmaz. Opset 11 varsayılanı ve batch 1 kalır.
8. **Unutmaya karşı önlem:** COCO train2017'den `person`, `truck` ve `car` içeren küçük bir alt küme (2-3 bin görüntü) stdlib ile süzülüp eğitime katılır.

### Açık sorular

- Sahada donanım CPU mu GPU mu?
- MVP sınıf listesi gerçekten 6 mı? `loader` sahada görülüyor mu? Fabrika içindeki kamerada `truck` ve `car` ne sıklıkla görünüyor?
- Müşteri etiketlenebilir kare verebilecek mi (KVKK)? Etiketlemeyi kim yapacak?
- Flickr kaynaklı görüntülerle (COCO, LVIS) eğitilmiş modeli ticari müşteriye teslim etmek kabul edilebilir mi? Hukuki görüş alınacak mı?
- LOCO indirme bağlantısını (`go.mytum.de`) operatör açıp arşivi indirebilecek mi?
- Eğitim için GPU nereden gelecek? Epoch ve süre bütçesi ne?

---

## 3. Çevrimdışı Türkçe sesli uyarı (TTS)

### Özet

Piper'ın orijinal deposu MIT lisanslı ama 6 Ekim 2025'te arşivlendi. Halefi `piper-tts` aktif olarak geliştiriliyor (1.8.0, 4 Eyl 2026), ama lisansı **GPL-3.0-or-later.** Bugün kullanılabilir tek Türkçe Piper sesi `tr_TR-dfki-medium` ve iki ayrı engeli var: veri seti CC BY-NC-SA, üstelik ses ticari sentezi dışlayan lessac tabanından ince ayarlanmış. Piper projesinin kendisi de "yalnız kişisel kullanım ve araştırma" diyor.

espeak-ng GPL-3.0 lisanslı ve Türkçe destekliyor. Coqui XTTS-v2 (CPML) ve Meta MMS (CC-BY-NC) ticari kullanıma kapalı.

DALSAN zaten "önceden kaydedilmiş WAV çal" mimarisinde. Dinamik metin için de iki mevcut yolu var: tarayıcı `speechSynthesis` ve HTTP anons cihazının kendi TTS'i.

### Olgular

| Olgu | Durum | Kaynak |
|---|---|---|
| `rhasspy/piper` MIT lisanslı. 6 Ekim 2025'te arşivlendi; geliştirme `OHF-Voice/piper1-gpl` deposuna taşındı. | DOĞRULANDI | [rhasspy/piper](https://github.com/rhasspy/piper): "Development has moved: https://github.com/OHF-Voice/piper1-gpl" |
| İddia: "piper 2024'ten beri bakımsız." **Doğrusu:** Halef paket aktif. 1.5.0'dan 1.8.0'a kadar dört sürüm Temmuz-Eylül 2026'da çıktı; 1.8.0'ın tarihi 4 Eyl 2026. Ancak sınıflandırıcı "Development Status :: 3 - Alpha" diyor ve README bakımcı arıyor. | ÇÜRÜTÜLDÜ | [PyPI piper-tts JSON](https://pypi.org/pypi/piper-tts/json): "version": "1.8.0", upload "2026-09-04" |
| `piper-tts` paketinin lisansı **GPL-3.0-or-later**, MIT değil. | DOĞRULANDI | [PyPI piper-tts](https://pypi.org/project/piper-tts/): "License: GPL-3.0-or-later" |
| `piper-tts` Python 3.12'yi destekliyor. Her platform için tek bir `cp39-abi3` wheel'i var: Linux x86_64/aarch64, Windows x64, macOS Intel ve ARM. | DOĞRULANDI | [PyPI 1.8.0 JSON](https://pypi.org/pypi/piper-tts/1.8.0/json): "Programming Language :: Python :: 3.12" |
| Çekirdek bağımlılıklar `onnxruntime<2,>=1` ve `pathvalidate`. DALSAN'ın `onnxruntime==1.19.2` sabitiyle çakışma yok. | DOĞRULANDI | [PyPI JSON](https://pypi.org/pypi/piper-tts/json): "onnxruntime<2,>=1" |
| espeak-ng paketin içine statik olarak gömülü; sistemde ayrıca espeak-ng kurulu olması gerekmiyor. | DOĞRULANDI | [piper1-gpl CMakeLists.txt](https://raw.githubusercontent.com/OHF-Voice/piper1-gpl/main/CMakeLists.txt): "-DBUILD_SHARED_LIBS:BOOL=OFF" |
| İddia: "Türkçe Piper sesleri dfki, fahrettin ve fettah; üçü de medium kalitede." **Doğrusu:** Bu liste arşivlenmiş depodaki v1.0.0 anlık görüntüsüne ait. Güncel `VOICES.md` ses listesi içermiyor. Bugün yalnız `tr_TR-dfki-medium` mevcut görünüyor: `piper-samples` altında tr_TR için yalnız dfki var, sherpa-onnx fahrettin ve fettah'ı "# removed" diye işaretlemiş. | ÇÜRÜTÜLDÜ (bayat) | [rhasspy/piper VOICES.md](https://raw.githubusercontent.com/rhasspy/piper/master/VOICES.md) · [sherpa-onnx generate.py](https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/master/scripts/piper/generate.py) |
| Kalite seviyeleri: low 16.000 Hz, medium ve high 22.050 Hz. Türkçe ses medium seviyesinde. | DOĞRULANDI | [TRAINING.md](https://raw.githubusercontent.com/rhasspy/piper/master/TRAINING.md): "medium = 22,050 Hz sample rate" |
| `tr_TR-dfki-medium` sesinin veri seti CC BY-NC-SA 4.0 lisanslı ve ses "U.S. English lessac" sesinden ince ayarlanmış. | DOĞRULANDI | [MODEL_CARD](https://raw.githubusercontent.com/rhasspy/piper-samples/master/samples/tr/tr_TR/dfki/medium/MODEL_CARD): "License: https://creativecommons.org/licenses/by-nc-sa/4.0/" |
| lessac tabanı Blizzard 2013 Lessac lisansına bağlı ve bu lisansın ses sentezi ürünlerinin ticari geliştirilmesini dışladığı bildiriliyor. Bu, dfki için ikinci ve bağımsız bir engel. lessac'tan ince ayarlanan her ses aynı riski taşır. | DOĞRULANDI (ikincil) | [Piper tartışma #271](https://github.com/rhasspy/piper/discussions/271): "including the development … of voice synthesis products or services." (cstr.ed.ac.uk engelli) |
| Piper bakımcısı (2023): ses modellerine ek lisans konmuyor; son karar son kullanıcıya ait. | DOĞRULANDI | [#271](https://github.com/rhasspy/piper/discussions/271): "does not impose any additional licenses on the checkpoints or voice models" |
| Piper'ın güncel resmi tutumu: kişisel kullanım ve araştırma içindir; bazı seslerin kısıtlayıcı lisansı vardır. | DOĞRULANDI | [piper1-gpl VOICES.md](https://raw.githubusercontent.com/OHF-Voice/piper1-gpl/main/docs/VOICES.md): "intended for personal use and text to speech research only" |
| Komut satırı kullanımı: `python3 -m piper -m <ses> -f x.wav -- 'metin'`. Her çağrı modeli yeniden yüklediği için yavaş. | DOĞRULANDI | [CLI.md](https://raw.githubusercontent.com/OHF-Voice/piper1-gpl/main/docs/CLI.md): "slow since it needs to load the model each time" |
| espeak-ng GPL-3.0 lisanslı ve Türkçeyi `tr` koduyla destekliyor. `-w` ile WAV dosyasına yazabiliyor. Windows için MSI paketi var. Son sürüm 1.52.0 (12 Ara 2024). | DOĞRULANDI | [COPYING](https://raw.githubusercontent.com/espeak-ng/espeak-ng/master/COPYING) · [languages.md](https://raw.githubusercontent.com/espeak-ng/espeak-ng/master/docs/languages.md): "trk \| tr \| Turkic \| Turkish" · [1.52.0](https://github.com/espeak-ng/espeak-ng/releases/expanded_assets/1.52.0) |
| GPLv3 §5'e göre GPL'li bir programın "ayrı ve bağımsız" programlarla birlikte dağıtılması ("aggregate") ötekilere GPL uygulatmaz. §0'a göre yalnız ağ üzerinden etkileşim "conveying" sayılmaz. DALSAN müşteri sunucusuna **kurulduğu** için conveying vardır. | DOĞRULANDI | [GPLv3 metni (espeak-ng COPYING)](https://raw.githubusercontent.com/espeak-ng/espeak-ng/master/COPYING): "does not cause this License to apply to the other parts of the aggregate." |
| FSF SSS: pipe, soket ve komut satırı argümanıyla haberleşen modüller normalde ayrı programdır; ortak adres alanında birlikte çalışan modüller ise tek program sayılır. Python'da `import` aynı süreçtir. Kartın verdiği ayna 404 döndü; içerik başka bir kopyada birebir bulundu. gnu.org engelli. | DOĞRULANDI (kaynak değişti) | [sailuh/kaiaulu #12 (FSF SSS alıntısı)](https://github.com/sailuh/kaiaulu/issues/12): "pipes, sockets and command-line arguments are communication mechanisms normally used between two separate programs." |
| Coqui TTS'in kodu MPL-2.0, XTTS-v2 model ağırlığı ise CPML lisanslı. | DOĞRULANDI | [.models.json](https://raw.githubusercontent.com/coqui-ai/TTS/dev/TTS/.models.json): "license": "CPML" |
| CPML yalnız ticari olmayan kullanıma izin veriyor. | DOĞRULANDI | [CPML kopyası](https://raw.githubusercontent.com/jianchang512/clone-voice/main/LICENSE): "allows only non-commercial use of a machine learning model and its outputs." |
| Coqui kapandı; XTTS için ticari lisans alınabilecek kimse kalmadı. | DOĞRULANDI | [coqui-ai/TTS #4304](https://github.com/coqui-ai/TTS/discussions/4304): "there is no way of obtaining a commercial license." |
| Meta MMS kodu ve model ağırlıkları CC-BY-NC 4.0. `mms-tts-tur` modelinin varlığı yalnız ikincil kaynaklarda görüldü. | DOĞRULANDI | [fairseq MMS README](https://raw.githubusercontent.com/facebookresearch/fairseq/main/examples/mms/README.md): "released under the CC-BY-NC 4.0 license." |
| Windows'ta Türkçe "Microsoft Tolga" sesi var (ikincil kaynak). OneCore sesleri klasik SAPI5 listesinde görünmüyor. | DOĞRULANDI | [voices.json](https://raw.githubusercontent.com/daijro/camoufox/main/pythonlib/camoufox/voices.json) · [pyttsx3 #397](https://github.com/nateshmbhat/pyttsx3/issues/397): "Speech_OneCore\\Voices\\Tokens" |
| macOS'ta Türkçe `say` sesi "Yelda" (tr_TR). Kaynak 2014 tarihli; 2024'te kaldırılan sesler listesinde Yelda yok. | DOĞRULANDI | [gist](https://gist.github.com/mculp/4b95752e25c456d425c6): "Yelda tr_TR" |
| Python stdlib'deki `winsound.PlaySound` Windows'ta WAV çalabiliyor. | DOĞRULANDI | [winsound.rst](https://raw.githubusercontent.com/python/cpython/main/Doc/library/winsound.rst): "SND_FILENAME: The sound parameter is the name of a WAV file." |
| DALSAN zaten "WAV → subprocess" mimarisinde: `anons.py` WAV dosyasını afplay, paplay, aplay ya da PowerShell SoundPlayer ile çalıyor. | DOĞRULANDI (yerel) | [anons.py](../backend/app/olaylar/anons.py): `shutil.which("afplay") or shutil.which("paplay") or shutil.which("aplay")` |
| DALSAN dinamik metni **zaten** iki yoldan seslendiriyor: tarayıcıda `speechSynthesis` ile `tr-TR` (`uyari.js:70-78`) ve HTTP anons cihazının kendi TTS'i (`docs/14` §3.3). `docs/14` §8'e göre sunucuda TTS bilerek yapılmadı; `01-MVP-KAPSAM:99`'da TTS "NICE" önceliğinde. | DOĞRULANDI (yerel) | [uyari.js](../backend/app/web/static/uyari.js) · [14-ANONS-SISTEMI-BAGLAMA.md](14-ANONS-SISTEMI-BAGLAMA.md) |

### DOĞRULANMADI

- **piper'ın GPL'e geçme gerekçesi:** espeak-ng'nin gömülmesi olması muhtemel, ama bu bir çıkarım. CHANGELOG'da iki değişiklik yan yana duruyor, gerekçe cümlesi yok.
- **fahrettin ve fettah seslerinin "katkıcıların isteğiyle" kaldırılması:** Kaldırıldıkları güçlü dolaylı kanıtla destekleniyor, sebebi değil.
- **macOS `say -o x.wav --data-format=LEI16@22050`:** Apple man sayfası engelli. İkinci bir üçüncü taraf kaynak `--file-format=WAVE` bayrağını da ekliyor. `man say` ile teyit edilmeli.
- **macOS lisans sözleşmesinin (SLA) "System Voices" maddesi:** Sistem sesleri yalnız kişisel ve ticari olmayan kullanım içindir; ticari bağlamda kaydetmek ve dağıtmak izinli değildir. Birincil PDF (apple.com/legal/sla) engelli, **orta güven.**
- **Tolga'nın yalnız OneCore sesi olması:** Doğrulanmadı.
- **Windows sistem seslerinin ticari kullanım koşulları:** Doğrulanmadı.
- **Tarayıcı `speechSynthesis`'in çevrimdışı Türkçe sesi:** İstemcinin işletim sistemine bağlı. Sahada test edilmedi.
- **`tr_TR-dfki-medium` model boyutu (~60 MB):** Doğrulanmadı.

### Projeye öneri (en az parça)

1. **MVP'de TTS kütüphanesi eklenmez.** Sabit her mesaj için bir WAV dosyası yeterli; `docs/01` zaten böyle diyor. Yeni bağımlılık yok, lisans riski yok, çevrimdışı çalışma garanti.
2. **WAV'ların kaynağı insan kaydı olur.** Müşteri personeli ya da tek seferlik bir stüdyo kaydı. Şunlar müşteriye giden varlık olarak **kullanılmaz:** piper dfki sesi (NC-SA ve lessac), macOS `say` çıktısı (SLA riski, doğrulanmadı), Windows sistem sesleri (koşullar doğrulanmadı).
3. **Dinamik metin gerekirse önce mevcut yollar kullanılır.** Tarayıcı TTS'i ve HTTP anons cihazı yeni parça gerektirmez. Tarayıcıdaki Türkçe sesin kalitesi istemci işletim sistemine bağlı, sahada denenmeli.
4. **Sunucuda TTS ancak operatör E3'ü geri alırsa yapılır.** O durumda `piper-tts` ayrı bir venv'e kurulur ve `subprocess.run([<venv>/python, "-m", "piper", …])` ile çağrılır. `from piper import …` ile **asla** ana sürece alınmaz (GPL, aynı adres alanı, conveying). Ayrı venv'de de `onnxruntime` ana projedeki sürüme sabitlenir. WAV dosyası metnin hash'iyle diske önbelleğe alınır; çalma yolu yine `anons.py` olur. **Bugün ticari kullanım için temiz bir Türkçe Piper sesi yok.** Böyle bir ses için lessac olmayan bir kontrol noktasından ya da sıfırdan, kendi kaydıyla eğitim gerekir. Bu maliyet operatörün kararıdır.
5. **espeak-ng alternatifi:** Sistem paketi kurulur ve `subprocess.run(["espeak-ng","-v","tr","-w",wav,metin])` ile çağrılır. Python bağımlılığı sıfır, GPL de süreç sınırında kalır. Bedeli robotik ses; gürültülü sahada anlaşılırlığı denenmeli.
6. **Kesinlikle kullanılmayacaklar:** Coqui XTTS-v2 (CPML, ticari lisans satın alınamıyor) ve Meta MMS-TTS (CC-BY-NC, ayrıca torch ve transformers getiriyor). Bu ret kararı gelecek oturumlar yeniden denemesin diye `LICENSE-THIRD-PARTY` ya da bir ADR'ye yazılır.
7. **`docs/14` §2.3 madde 2 güncellenmeli.** "Bilgisayarın kendi seslendirmesi" seçeneğine ticari bağlamda lisans riski notu eklenmeli.

### Açık sorular

- Uyarı metinleri sabit mi, dinamik mi? Dinamikse hangi alanlar değişiyor? Bölüm adları sınırlı sayıdaysa bölüm başına bir WAV yeter.
- WAV'ları kim kaydedecek?
- Fabrika sunucusunda GPL-3.0 lisanslı ayrı bir süreç çalıştırılmasına müşterinin itirazı var mı?
- Sunucunun işletim sistemi kesin olarak Linux mu?
- Sesli uyarı, bip sesine göre sahada gerçekten daha etkili mi? Saha denemesi yapıldı mı?

---

## 4. Linux sunucuda Bluetooth hoparlör

### Özet

BlueZ, D-Bus üzerinden bağlantıyı yönetir ama **ses taşımaz.** A2DP için PipeWire, PulseAudio ya da BlueALSA gerekir. `bluetoothctl` betikle kullanılabilir, ama ilk karttaki üç varsayım yanlış çıktı:

- `scan on`, `-t` verilmezse kendiliğinden çıkmaz.
- `-t` ile çalıştırıldığında çıkış kodu **her zaman 0** olur.
- Etkileşimsiz modda `-a/--agent` bayrağı yok sayılır.

Python'dan D-Bus'a gitmek gerekirse aktif bakımlı tek aday `dbus-fast`. `bleak` yalnız BLE destekler, A2DP yapamaz.

Konteynerde host'un D-Bus soketi yeterli. `--privileged`, `NET_ADMIN` ve `NET_RAW` gereksiz. Windows'ta eşleştirme diyaloğu bastırılamıyor.

### Olgular

| Olgu | Durum | Kaynak |
|---|---|---|
| `org.bluez.Adapter1` şunları sunar: `StartDiscovery` / `StopDiscovery`, `RemoveDevice`, `SetDiscoveryFilter`, `ConnectDevice` [experimental]; özellikler `Powered` (rw) ve `Discovering` (ro). | DOĞRULANDI | [org.bluez.Adapter.rst](https://raw.githubusercontent.com/bluez/bluez/master/doc/org.bluez.Adapter.rst): "Starts device discovery session" |
| `org.bluez.Device1` şunları sunar: `Pair`, `Connect`, `Disconnect`, `CancelPairing`. `Trusted` (rw), `Connected` (ro, `PropertiesChanged` sinyaliyle). `RSSI` yalnız keşif ya da reklam sırasında dolar. | DOĞRULANDI | [org.bluez.Device.rst](https://raw.githubusercontent.com/bluez/bluez/master/doc/org.bluez.Device.rst): "Connects all profiles the remote device supports" |
| `AgentManager1.RegisterAgent` ve `RequestDefaultAgent` var. Beş yetenek değeri tanımlı; boş verilirse `KeyboardDisplay` kullanılır. | DOĞRULANDI | [org.bluez.AgentManager.rst](https://raw.githubusercontent.com/bluez/bluez/master/doc/org.bluez.AgentManager.rst): "Multiple agents per application is not supported." |
| BlueZ 5 ses yolunu barındırmıyor. A2DP için PipeWire, PulseAudio ya da BlueALSA (MIT) gerekir. | DOĞRULANDI | [bluez-alsa README](https://raw.githubusercontent.com/arkq/bluez-alsa/master/README.md): "the built-in integration has been removed in favor of 3rd party audio applications" |
| PulseAudio'da `module-bluetooth-discover`, `module-bluez5-discover` modülünü yükler. `default.pa` bu modülü `.ifexists` ile yükler (PulseAudio BlueZ desteğiyle derlenmişse). | DOĞRULANDI | [default.pa.in](https://raw.githubusercontent.com/pulseaudio/pulseaudio/master/src/daemon/default.pa.in) |
| PipeWire'ın bluez5 eklentisi `org.bluez` D-Bus arayüzlerini kullanıyor ve A2DP UUID'lerini tanıyor. `bluez5.codecs` seçenekleri arasında sbc, aac, aptx, ldac, lc3 ve diğerleri var. | DOĞRULANDI | [bluez5 defs.h](https://raw.githubusercontent.com/PipeWire/pipewire/master/spa/plugins/bluez5/defs.h): `#define BLUEZ_SERVICE "org.bluez"` |
| `bluetoothctl` komut satırından otomatikleştirilebilir. `-t` BlueZ 5.49'da eklendi; ayrıca `-a` ve `-s` bayrakları var. | DOĞRULANDI | [bluetoothctl.rst](https://raw.githubusercontent.com/bluez/bluez/master/doc/bluetoothctl.rst): "The tool is menu driven but can be automated from the command line." |
| Komutlar argüman olarak verilirse etkileşimsiz modda çalışır. Seçenekler komuttan **önce** yazılmalı, çünkü optstring `+` ile başlıyor ve ayrıştırma ilk komut kelimesinde duruyor. | DOĞRULANDI | [shell.c](https://raw.githubusercontent.com/bluez/bluez/master/src/shared/shell.c): `data.mode = (data.argc > 0) ? MODE_NON_INTERACTIVE : MODE_INTERACTIVE;` |
| İddia: "`scan on` yanıt gelince hemen çıkar; pair/connect/trust çıkış kodu anlamlıdır." **Doğrusu:** `scan on`, `-t` verilmezse kendiliğinden **çıkmaz** (`-EINPROGRESS` yok sayılıyor). `-t` verilince çıkış kodu **her zaman 0** olur. pair, connect ve trust sonucu çıkış kodundan yalnız `-t` kullanılmadığında okunabilir. | ÇÜRÜTÜLDÜ | [client/main.c](https://raw.githubusercontent.com/bluez/bluez/master/client/main.c): `return bt_shell_noninteractive_quit(-EINPROGRESS);` |
| Etkileşimsiz modda `-a/--agent` **yok sayılır.** Agent yoksa `Pair()` NoInputNoOutput yeteneğini kullanır, dolayısıyla `bluetoothctl pair MAC` zaten "just works" eşleşmesi yapar. PIN isteyen bir hoparlör etkileşimsiz modda eşleşmez. | DOĞRULANDI | [client/main.c](https://raw.githubusercontent.com/bluez/bluez/master/client/main.c): `if (auto_register_agent && !bt_shell_get_env("NON_INTERACTIVE"))` |
| `connect <cihaz> [uuid]` (ör. `a2dp-sink`) yalnız BlueZ 5.82 ve sonrasında var. Ubuntu 24.04'teki 5.72 sürümü bunu desteklemiyor. | DOĞRULANDI | client/main.c 5.72 ile 5.82 karşılaştırması: `"<dev>"` → `"<dev> [uuid]"` |
| Keşifte bulunup eşleşmemiş cihazlar 30 saniye sonra silinir (`TemporaryTimeout`). Sonrasında `pair`, "Device … not available" hatası verir. | DOĞRULANDI | [main.conf](https://raw.githubusercontent.com/bluez/bluez/master/src/main.conf): "How long to keep temporary devices around … Default is 30." |
| `info MAC` çıktısı `\tConnected: yes\|no` biçiminde. A2DP hoparlör `UUID: Audio Sink (0000110b-…)` satırıyla tanınır. Cihaz bulunamazsa `EXIT_FAILURE` döner. | DOĞRULANDI | [client/print.c](https://raw.githubusercontent.com/bluez/bluez/master/client/print.c): `valbool == TRUE ? "yes" : "no"` |
| Etkileşimsiz moddaki çıktı boruya tam tamponlanıyor: `vprintf` kullanılıyor, `fflush` yok. | DOĞRULANDI (koddan çıkarım) | [shell.c](https://raw.githubusercontent.com/bluez/bluez/master/src/shared/shell.c) |
| Ekransız eşleştirme dizisi **etkileşimli** bir oturumda şöyle: `--agent=NoInputNoOutput` → `default-agent` → `scan on` → `pair` → `connect` → `trust`. | DOĞRULANDI | [BlueALSA wiki](https://raw.githubusercontent.com/wiki/arkq/bluez-alsa/Bluetooth-Pairing-And-Connecting.md): "Pairing successful" |
| Python D-Bus kütüphaneleri: `dbus-next` 0.2.3 (2021, fiilen bakımsız). `dbus-fast` 5.0.22 (Haz 2026, MIT, Python ≥3.10, aktif). `pydbus` 0.6.0 (2016, LGPLv2+, PyGObject gerektiriyor). `dbus-python` 1.4.0 (MIT, "7 - Inactive", libdbus iş parçacığı sorunları var). | DOĞRULANDI | [PyPI dbus-fast](https://pypi.org/project/dbus-fast/) · [dbus-next](https://pypi.org/project/dbus-next/) · [pydbus](https://pypi.org/project/pydbus/) · [dbus-python](https://pypi.org/project/dbus-python/) |
| `bleak` yalnız BLE/GATT istemcisi; klasik Bluetooth ve A2DP desteği yok (#781 "wontfix"). | DOĞRULANDI | [bleak README](https://raw.githubusercontent.com/hbldh/bleak/develop/README.rst): "Bleak is a GATT client software" |
| `AF_BLUETOOTH` soketleri yalnız host'un ağ ad alanında açılabiliyor. Konteyner içinde HCI soketi açmak için `--net=host` gerekir; `--privileged` bunu çözmez. | DOĞRULANDI | [af_bluetooth.c](https://raw.githubusercontent.com/torvalds/linux/master/net/bluetooth/af_bluetooth.c): `if (net != &init_net) return -EAFNOSUPPORT;` |
| İddia: "Bluetooth için `--privileged` şart." **Doğrusu:** Ne gerekli ne yeterli. HCI soketi için belirleyici olan ağ ad alanı; D-Bus istemcisi için soket bağlamak yeterli. | ÇÜRÜTÜLDÜ | [moby #16208](https://github.com/moby/moby/issues/16208) ("Closed as not planned") |
| İddia: "D-Bus soketi yeterli, ama tam işlevsellik için `NET_ADMIN` ve `NET_RAW` önerilir." **Doğrusu:** Soket bağlamak `bluetoothctl` için yeterli. HA'nın bu önerisi kendi mgmt/HCI soket kullanımı için. Host ağ ad alanında çalışmayan bir konteynerde bu yetenekler işe yaramaz, **verilmemeli.** | ÇÜRÜTÜLDÜ (kısmen) | [HA bluetooth belgesi](https://raw.githubusercontent.com/home-assistant/home-assistant.io/current/source/_integrations/bluetooth.markdown): "-v /run/dbus:/run/dbus:ro" |
| D-Bus politikası her kullanıcının `org.bluez`'e mesaj göndermesine izin veriyor; adın sahibi yalnız root olabilir. Ubuntu buna ek olarak `bluetooth` grubu için bir kural koyuyor. | DOĞRULANDI | [bluetooth.conf](https://raw.githubusercontent.com/bluez/bluez/master/src/bluetooth.conf): `<allow send_destination="org.bluez"/>` |
| Konteynerden ses çalmak için `PULSE_SERVER` tanımlanır ve konteyner kullanıcısı host'takiyle aynı UID olmalıdır. PipeWire'da `pulse/native` soketi paylaşılır. | DOĞRULANDI | [x11docker wiki](https://raw.githubusercontent.com/wiki/mviereck/x11docker/Container-sound:-ALSA-or-Pulseaudio.md): "Container user must be same as on host" |
| `main.conf` [Policy] varsayılanları: `ReconnectAttempts=7`, aralıklar 1, 2, 4, 8, 16, 32, 64 saniye; UUID listesinde A2DP Sink ve Source var. | DOĞRULANDI | [main.conf](https://raw.githubusercontent.com/bluez/bluez/master/src/main.conf) · [policy.c](https://raw.githubusercontent.com/bluez/bluez/master/plugins/policy.c) |
| BlueZ yalnız bağlantı kaybında (link supervision timeout) ya da uykudan dönüşte yeniden bağlanmayı dener; hoparlörün kapatılıp açılması kapsam dışı. Agent yoksa güvenilmeyen cihazın gelen bağlantısı reddedilir. **`trust` şart.** | DOĞRULANDI | [policy.c](https://raw.githubusercontent.com/bluez/bluez/master/plugins/policy.c): `if (reason != MGMT_DEV_DISCONN_TIMEOUT && …) return;` |
| `AutoEnable` varsayılanı true. | DOĞRULANDI | [main.conf](https://raw.githubusercontent.com/bluez/bluez/master/src/main.conf): "Defaults to 'true'." |
| İddia: "`module-switch-on-connect` varsayılan olarak yüklü değil." **Doğrusu:** Upstream'de yüklü değil, ama **Ubuntu 24.04** `/etc/pulse/default.pa` dosyasında yükleniyor (LP #1702794). Önce mevcut dosyaya bakılmalı. | ÇÜRÜTÜLDÜ (dağıtıma göre) | [module-switch-on-connect.c](https://raw.githubusercontent.com/pulseaudio/pulseaudio/master/src/modules/module-switch-on-connect.c) · Ubuntu `pulseaudio 1:16.1` paketi |
| Bluetooth sink adı ses sunucusuna göre değişiyor: PulseAudio'da `bluez_sink.<adres>.<profil>`, PipeWire'da `bluez_output.<adres>…`. | DOĞRULANDI | [module-bluez5-device.c](https://raw.githubusercontent.com/pulseaudio/pulseaudio/master/src/modules/bluetooth/module-bluez5-device.c): `"bluez_sink.%s.%s"` |
| WirePlumber'da `bluez5.auto-connect` varsayılan olarak kapalı. Bluetooth izleyicisi yalnız logind oturumu (seat) "active" iken başlıyor. Ekransız sunucuda `main-systemwide` profili ya da `monitor.bluez.seat-monitoring = disabled` gerekir. | DOĞRULANDI | [enumerate-device.lua](https://raw.githubusercontent.com/PipeWire/wireplumber/master/src/scripts/monitors/bluez/enumerate-device.lua): "only activate the monitor if the seat is active" |
| `aplay -Dpulse` PulseAudio ya da pipewire-pulse üzerinden çalar. `pipewire-alsa` kuruluysa ALSA varsayılanı zaten PipeWire'dır. | DOĞRULANDI | [README-pulse](https://raw.githubusercontent.com/alsa-project/alsa-plugins/master/doc/README-pulse): "aplay -Dpulse foo.wav" |
| Konteyner yolu seçilirse imaja işletim sistemi paketleri girer: `bluez` istemcisi ve ALSA pulse eklentisi ya da `pulseaudio-utils`. Bunlar da birer "parça" sayılır. | DOĞRULANDI (paket adları hariç) | [x11docker wiki](https://raw.githubusercontent.com/wiki/mviereck/x11docker/Container-sound:-ALSA-or-Pulseaudio.md): "the container needs the PipeWire ALSA module" |
| Windows'ta WinRT `PairAsync` ile programatik eşleştirme mümkün. `bleak` bunu `winrt-Windows.Devices.Enumeration` paketiyle yapıyor (3.2.1, MIT). | DOĞRULANDI | [bleak winrt client.py](https://raw.githubusercontent.com/hbldh/bleak/develop/bleak/backends/winrt/client.py): `await custom_pairing.pair_async(ceremony)` |
| İddia: "Windows'ta A2DP eşleştirme diyaloğu bastırılabilir." **Doğrusu:** Microsoft belgesine göre masaüstünde sistem diyaloğu **her zaman** gösteriliyor. | ÇÜRÜTÜLDÜ | [MS pair-devices.md](https://raw.githubusercontent.com/MicrosoftDocs/windows-dev-docs/docs/hub/apps/develop/devices-sensors/pair-devices.md): "a system dialog will always be shown to the user" |
| macOS'ta `blueutil` ile `--pair`, `--connect` ve `--info` işlemleri yapılabiliyor. Araç IOBluetooth'un özel (private) API'sini kullanıyor; lisansı MIT. | DOĞRULANDI | [blueutil LICENSE](https://raw.githubusercontent.com/toy/blueutil/master/LICENSE.txt) |
| Ubuntu 24.04 paketindeki `bluetoothctl` (bluez 5.72) `-t/--timeout` bayrağını destekliyor. | DOĞRULANDI (yerel) | `apt-get download bluez` ile paket indirilip incelendi; [5.72 shell.c](https://raw.githubusercontent.com/bluez/bluez/5.72/src/shared/shell.c) |

### DOĞRULANMADI

- **"A2DP gecikmesi tipik olarak 100-250 ms (SBC), aptX LL ~40 ms":** Yayımlanmış bir ölçüm kaynağı açılamadı. Yalnız tekil uygulayıcı verileri var: 48 kHz SBC için ["Delay: 150.6 ms"](https://github.com/arkq/bluez-alsa/issues/727) ve bir kullanıcının senkron için 250 ms `DelaySync` ayarı.
- **Debian bookworm paketindeki `bluetoothctl -t`:** Kaynak kodda var, paketin kendisi kontrol edilemedi.
- **Paket adları `libasound2-plugins` ve `pulseaudio-utils`:** Paket deposundan doğrulanmadı.
- **"linger açık ama aktif seat yok" senaryosu:** Koddan çıkarım; sahada denenmedi.
- **Dağıtımların D-Bus politikasına ek kısıt koyup koymadığı (Debian):** Doğrulanmadı.

### Projeye öneri (en az parça)

1. **MVP (E2 ile uyumlu):** Eşleştirme, `trust` ve bağlantı host'ta, tek seferlik bir kurulum adımıyla yapılır. DALSAN yalnız varsayılan sink'e ses çalar (mevcut `anons.py` değişmez) ve kopmayı Anons sayfasında gösterir. Uygulama içi "tara/eşleştir" ekranı yalnız operatör E2'yi geri alırsa yapılır.
2. **Uygulama içi eşleştirme yapılacaksa kütüphane eklenmez; `subprocess` ve `bluetoothctl` doğru anlamlarıyla kullanılır:**
   - Tarama: `bluetoothctl -t 10 scan on`. Subprocess zaman aşımı 10 saniyeden uzun tutulur, `[NEW] Device` satırları regex ile toplanır. `-t` verildiği için çıkış kodu anlamsızdır.
   - Eşleştirme: `-t` **olmadan** sırasıyla `bluetoothctl pair MAC`, `trust MAC`, `connect MAC`. Bu durumda çıkış kodu anlamlıdır. Tarama bittikten sonra **30 saniye içinde** yapılmalıdır.
   - `-a` yazılmaz, çünkü etkisiz. PIN isteyen hoparlör etkileşimsiz modda eşleşmez; işletim sistemine bırakılır.
   - BlueZ 5.82'den eskiyse `connect MAC a2dp-sink` biçimi kullanılmaz.
   - Durum kontrolü: `bluetoothctl info MAC` çıktısında `^\s*Connected:\s*yes$` aranır.
3. **Sink adı koda sabit yazılmaz.** Sink, `pactl list short sinks` çıktısından bulunur (PulseAudio ile PipeWire'da adlar farklı).
4. **Yeniden bağlanma:** BlueZ yalnız bağlantı kaybında dener. Mevcut FastAPI sürecinde basit bir bekçi (her 10 saniyede `info`, gerekirse `connect`) yeterli. Yeni servis ya da kütüphane gerekmez.
5. **Docker:** `bluetoothd` ve ses sunucusu host'ta kalır. Konteynere yalnız şunlar verilir: `-v /run/dbus:/run/dbus:ro`, ses soketi, `PULSE_SERVER` ve `--user <host UID>`. `--privileged`, `--net=host`, `NET_ADMIN` ve `NET_RAW` **verilmez.** İmaja istemci paketleri eklenir. Bu da bir parça olduğundan, daha az parçalı yol Bluetooth işini tamamen host'ta bırakmaktır.
6. **Ekransız sunucu:** PipeWire kullanılıyorsa WirePlumber `main-systemwide` profili ya da `seat-monitoring = disabled` ayarı gerekir. PulseAudio kullanılıyorsa önce mevcut `default.pa` okunur (Ubuntu'da `switch-on-connect` zaten yüklü).
7. **Python'dan D-Bus gerekirse** yalnız `dbus-fast` kullanılır. `bleak`, `pydbus`, `dbus-next` ve `dbus-python` kullanılmaz.
8. **Gecikme ölçülür, sabit bir sayı yazılmaz.** "Olay anı → ses" toplamı sahada ölçülüp raporlanır.
9. **Windows ve macOS:** Eşleştirme işletim sistemi ayarlarında yapılır. Windows'ta sistem diyaloğu zaten bastırılamıyor.
10. **Hedef sunucuda kontrol listesi:** `bluetoothctl --version` (≥5.63 önerilir), `bluetoothctl --help` çıktısında `-t`, `pactl info` (PulseAudio mu, pipewire-pulse mu), `id -u`, `/etc/bluetooth/main.conf`.

### Açık sorular

- Hedef sunucunun dağıtımı ve sürümü ne? BlueZ, PipeWire/PulseAudio ve pipewire-alsa kurulu mu?
- Hoparlörün markası ve modeli ne? PIN istiyor mu? Kapatılıp açıldığında son kaynağa kendisi bağlanıyor mu?
- Uygulama içi eşleştirme MVP kapsamında mı (E2)?
- Tek hoparlör mü, bölge başına bir hoparlör mü?
- Müşterinin güvenlik politikası konteynere host D-Bus soketinin bağlanmasına izin veriyor mu?

---

## 5. ONNX Runtime: GPU, TensorRT, OpenVINO, INT8 ve YOLOX export

### Özet

Başlıca bulgular şunlar:

- **Paketler:** `onnxruntime` (CPU) ve `onnxruntime-gpu` ayrı paketler ve **aynı ortama kurulmamalı.** Son kurulan kazanır. CPU paketi sonradan kurulursa CUDA sessizce kaybolur.
- **CUDA sürümleri:** PyPI GPU paketi 1.27'den beri CUDA 13, 1.21-1.26 arası CUDA 12.8 ile derleniyor.
- **Güvenlik:** 1.19.2'de kalmanın bilinen bir güvenlik bedeli var. ORT, model yükleme yolunda etkilenen `onnx` kodunu gömülü olarak taşıyor (CVE-2026-14647).
- **Hız:** Bu makinede 1.30.0'a geçiş CPU çıkarımını yaklaşık %25 hızlandırdı. Bu kazanç OpenVINO'nunkinden büyük ve yeni parça gerektirmiyor.
- **Jetson ve TensorRT:** Jetson'da PyPI wheel'i işe yaramıyor. TensorRT ek kurulum ve sıkı sürüm eşleşmesi istiyor.
- **Mevcut modeller:** YOLOX'un resmi ONNX dosyaları güncel ORT ile sorunsuz açılıyor, yeniden export gerekmiyor.

### Olgular

| Olgu | Durum | Kaynak |
|---|---|---|
| `onnxruntime` (CPU) wheel'i yalnız CPU ve Azure EP'lerini içeriyor; CUDA ve TensorRT kütüphaneleri yok. | DOĞRULANDI (yerel deney) | [install/index.md](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/install/index.md): "CPU: onnxruntime" · deney: `['AzureExecutionProvider', 'CPUExecutionProvider']` |
| `onnxruntime-gpu` ayrı bir paket; TensorRT, CUDA ve CPU EP'lerini tek wheel'de taşıyor. Kartın #26807'ye atfettiği "superset" alıntısı o sayfada yok. | DOĞRULANDI (wheel ve deney) | [PyPI onnxruntime-gpu 1.30.0](https://pypi.org/project/onnxruntime-gpu/1.30.0/) · deney: `['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']` |
| İki paket aynı ortama kurulunca ikisi de `site-packages/onnxruntime/` dizinine yazıyor. CPU paketi GPU paketinin üstüne kurulunca CUDA EP kayboldu; `.so` dosyaları diskte kalmaya devam etti. | DOĞRULANDI (yerel deney) | [fastembed #608](https://github.com/qdrant/fastembed/issues/608): "CUDA execution provider to silently disappear" |
| İddia: "Kök neden: onnxruntime-gpu 1.20 ve sonrasında wheel'den `Provides-Dist` satırı kaldırıldı." **Doğrusu:** 1.12'den 1.30'a kadar hiçbir GPU wheel'inde `Provides-Dist` satırı yok. Sorun yeni değil, bütün sürümlerde var. | ÇÜRÜTÜLDÜ | PyPI PEP 658 metadata'sı (1.12.0 … 1.30.0) |
| 1.19.x için PyPI paketi CUDA 12.x ve cuDNN 9.x istiyor. CUDA 11.8 derlemesi yalnız Azure DevOps feed'inde var. cuDNN 8 ve 9 derlemeleri birbirinin yerine kullanılamıyor. | DOĞRULANDI | [CUDA EP](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/execution-providers/CUDA-ExecutionProvider.md): "\| 1.19.x \| 12.x \| 9.x \| Avaiable in PyPI." |
| 1.27 ve sonrası: PyPI GPU paketi **CUDA 13.0** ve cuDNN 9 ile derleniyor. 1.21-1.26 arası CUDA 12.8. Aynı ana sürüm içindeki alt sürümlerle uyumlu. `install.md`'deki "12.x since 1.19.0" satırı bayat. | DOĞRULANDI | [CUDA EP](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/execution-providers/CUDA-ExecutionProvider.md): "Starting with version 1.27, GPU packages … are built with CUDA 13.0" |
| Güncel sürüm 1.30.0 (10 Eyl 2026): Python ≥3.11, cp311-cp314 wheel'leri var. Sürüm notları model yüklemede sertleştirme içeriyor. | DOĞRULANDI | [PyPI onnxruntime](https://pypi.org/project/onnxruntime/#history): "Limited nested model-graph depth and canonicalized external-data locations to harden model loading" |
| 1.19.2 (4 Eyl 2024): yalnız cp38-cp312 wheel'leri var, sdist yok. Python 3.13 ve sonrasında **kurulamaz.** | DOĞRULANDI | [PyPI 1.19.2](https://pypi.org/project/onnxruntime/1.19.2/) |
| İddia: "Python ≥3.11 şartı 1.25.1'de başladı." **Doğrusu:** Şart 1.24.4'te (17 Mar 2026) başladı. Python 3.10 wheel'i olan son sürüm 1.23.2. | ÇÜRÜTÜLDÜ (küçük) | [PyPI JSON](https://pypi.org/pypi/onnxruntime/json) |
| macOS x86_64 wheel'i olan son sürüm 1.23.2; 1.24.1 ve sonrasında yalnız arm64 var. DALSAN'ın sürümü sabitleme gerekçesi doğru, ama sınır 1.19.2 değil 1.23.2. | DOĞRULANDI | [PyPI 1.23.2](https://pypi.org/project/onnxruntime/1.23.2/) |
| ORT için yayımlanmış bir GHSA yok. CVE-2026-28500, ORT'yi değil `onnx` paketindeki `onnx.hub.load()` fonksiyonunu etkiliyor. | DOĞRULANDI | [ORT security advisories](https://github.com/microsoft/onnxruntime/security/advisories): "There aren't any published security advisories" |
| İddia: "1.19.2'de kalmanın bilinen bir CVE riski yok." **Doğrusu:** CVE-2026-14647, 1.21.x ve öncesindeki `onnx` sürümlerinde Conv şekil çıkarımında heap over-read açığı. Açık, ORT'nin `InferenceSession::Load()` yolundan bulunmuş. ORT 1.19.2 `onnx` 1.16.1'i, 1.30.0 ise `onnx` 1.22.0'ı gömülü taşıyor. | ÇÜRÜTÜLDÜ | [Ubuntu CVE-2026-14647](https://ubuntu.com/security/CVE-2026-14647): "affects the function convPoolShapeInference_opset19 … of the component onnxruntime" |
| `providers` listesi öncelik sırasını belirler. `get_available_providers()` kurulumun destekleyebildiği EP'leri, `get_providers()` ise oturumda gerçekten kayıtlı olanları döndürür. | DOĞRULANDI | [inference_collection.py](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/onnxruntime_inference_collection.py): "The list of providers is ordered by precedence." |
| CPU paketi kuruluyken CUDA EP istenirse istisna fırlatılmaz: Python `UserWarning` basılır ve oturum CPU'da açılır. | DOĞRULANDI (yerel deney) | aynı dosya: "Specified provider '{}' is not in available provider names." |
| GPU paketi kurulu ama CUDA kütüphaneleri yoksa uyarı yalnız C++ tarafında stderr'e basılır. Python'da uyarı yok, oturum CPU'da açılır. Asıl "sessiz düşüş" bu. TensorRT istenip TensorRT yoksa ise ORT istisna fırlatır ve Python katmanı stdout'a "Falling back" yazıp CUDA ve CPU ile yeniden dener. | DOĞRULANDI (yerel deney) | [pybind_state.cc](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/onnxruntime_pybind_state.cc): "Failed to create … Require cuDNN" |
| `session.disable_cpu_ep_fallback="1"` ayarlanırsa, istenen EP kurulamadığında oturum açık bir hatayla düşer. Bu ayarla CPU EP listeye eklenemez. Anahtar 1.19.2'de de var. | DOĞRULANDI (yerel deney) | [config keys header](https://github.com/microsoft/onnxruntime/blob/main/include/onnxruntime/core/session/onnxruntime_session_options_config_keys.h): "session creation will fail if the execution providers other than the CPU EP cannot fully support all of the nodes" |
| `get_available_providers()` derleme zamanında belirlenen bir liste. Yanlış GPU mimarisi için derlenmiş bir wheel CUDA EP'yi listeler ama ilk çıkarımda çöker (Jetson Orin raporu). | DOĞRULANDI (topluluk kaynağı) | [straga/jetson-jp7-onnxruntime](https://github.com/straga/jetson-jp7-onnxruntime): "get_available_providers() is a compile-time list" |
| pip'le gelen CUDA kütüphaneleri (`[cuda,cudnn]` extras) otomatik yüklenmez. `onnxruntime.preload_dlls()` (1.21 ve sonrası) çağrılmalı ya da `LD_LIBRARY_PATH` ayarlanmalı. `libcuda.so.1` host'taki sürücüden gelir. cuBLAS `[cudnn]` üzerinden gelir. | DOĞRULANDI (GPU'da uçtan uca denenmedi) | [CUDA EP](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/execution-providers/CUDA-ExecutionProvider.md): "the onnxruntime-gpu package provides the preload_dlls function" |
| TensorRT EP sürüm eşlemesi: 1.19 → TRT 10.2, …, 1.22 → TRT 10.9. TensorRT sisteme ayrıca kurulmalı. | DOĞRULANDI | [TensorRT EP](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/execution-providers/TensorRT-ExecutionProvider.md): "\| 1.19 \| 10.2 \|" |
| İddia: "1.22'den itibaren yalnız CUDA 12 GPU paketleri yayımlanıyor." **Doğrusu:** 1.27 ve sonrası CUDA 13. 1.30'un TensorRT EP'si `libnvinfer.so.10` ile CUDA 13 kütüphanelerine bağlı. Tablonun "main → 10.9" satırı bayat. | ÇÜRÜTÜLDÜ | wheel `readelf` çıktısı · [TensorRT EP](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/execution-providers/TensorRT-ExecutionProvider.md) |
| Jetson için ORT'nin resmi yönlendirmesi NVIDIA'nın yönettiği Jetson Zoo. | DOĞRULANDI | [TensorRT EP](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/execution-providers/TensorRT-ExecutionProvider.md): "Pre-built packages and Docker images are available for Jetpack in the Jetson Zoo" |
| PyPI'de aarch64 GPU wheel'i 1.29.0'dan beri var ama CUDA 13 ile derlenmiş; JetPack 6 için uygun değil. Ultralytics'in 1.24.0 cp312 wheel'inin Orin'de `cudaErrorNoKernelImageForDevice` hatası verdiği raporlanmış. | DOĞRULANDI (topluluk kısmı ikincil) | [Ultralytics Jetson kılavuzu](https://github.com/ultralytics/ultralytics/blob/main/docs/en/guides/nvidia-jetson.md): "they do not replace the device-specific packages for every JetPack release." |
| `onnxruntime-openvino` 1.24.1 (26 Şub 2026): MIT, cp311-cp313, yalnız Linux x86_64 ve Windows x86_64. Linux wheel'i OpenVINO 2025.4.1'i gömülü taşıyor ve `setupvars` olmadan çalıştı. ORT ana sürümünün 6 alt sürüm gerisinde. `onnxruntime/` dizinine kurulduğu için CPU paketi üstüne kurulunca OpenVINO EP kayboldu. | DOĞRULANDI (yerel deney) | [PyPI onnxruntime-openvino](https://pypi.org/project/onnxruntime-openvino/1.24.1/): "comes with pre-built libraries of OpenVINO™ version 2025.4.1" |
| YOLOX `tools/export_onnx.py` bayrakları: `--opset` varsayılanı 11, `--decode_in_inference` varsayılan kapalı, `--batch-size` 1, `--dynamic`, `--no-onnxsim`. README, OpenVINO'ya dönüştürülecek modeller için opset 10 öneriyor. | DOĞRULANDI | [export_onnx.py](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/tools/export_onnx.py): `"-o", "--opset", default=11` |
| Export betiği `torch.onnx._export` çağırıyor. Bu fonksiyon PyTorch 2.5.0'da kaldırıldı; 2.9 ve sonrasında export'un varsayılanı `dynamo=True`. | DOĞRULANDI | [PyTorch v2.4.0 torch/onnx/__init__.py](https://github.com/pytorch/pytorch/blob/v2.4.0/torch/onnx/__init__.py): `def _export(*args, **kwargs)` (v2.5.0'da yok) |
| Resmi 0.1.1rc0 ONNX dosyaları: opset 11, IR 6, "pytorch 1.7". Çıktılar ham grid biçiminde (tiny için `[1,3549,85]`, s için `[1,8400,85]`). Decode ve NMS işi `tespit.py`'de yapılıyor. Dosyalar ORT 1.30 ile açılıyor. | DOĞRULANDI (yerel deney) | [onnx_inference.py](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/demo/ONNXRuntime/onnx_inference.py): `demo_postprocess(output[0], input_shape)` |
| INT8 kuantizasyonu: CNN'ler için statik QDQ S8S8 öneriliyor. Kazanç VNNI ya da dot-product komutlu donanımda görülüyor; VNNI'siz AVX2/AVX512'de U8S8 doygunluk sorunu yaşayabiliyor. `onnxruntime.quantization` modülü `onnx` paketi olmadan import edilemiyor. | DOĞRULANDI | [quantization.md](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/performance/model-optimizations/quantization.md): "static quantization for CNN models" |
| İş parçacığı ayarı: `intra_op_num_threads = 0` fiziksel çekirdek sayısı kadar iş parçacığı açar ve çekirdek yakınlığını (affinity) etkinleştirir. N verilirse affinity kapanır. Spin varsayılanı derleme bayrağına bağlı. | DOĞRULANDI | [threading.md](https://github.com/microsoft/onnxruntime/blob/gh-pages/docs/performance/tune-performance/threading.md): "there will be no affinity set to any of the created thread" |
| DALSAN'daki durum: `onnxruntime==1.19.2`. `tespit.py` sağlayıcıyı seçiyor ve `get_providers()` ile "CUDA seçili ama CPU'da çalışıyor" uyarısı veriyor. Oturum oluştururken çıkan **her** istisna "dosyası bozuk" mesajına çevriliyor (`tespit.py:102-114`). | DOĞRULANDI (yerel) | [tespit.py](../backend/app/analiz/tespit.py) |
| Aynı test makinesinde ORT 1.19.2'den 1.30.0'a geçiş: yolox_tiny ~25,5 ms'den ~18,8 ms'ye, yolox_s ~82 ms'den ~60-69 ms'ye indi. Ölçüm yalnız `session.run` süresi; hedef donanım değil. | DOĞRULANDI (yerel ölçüm) | 4 çekirdek Xeon, 40 koşunun ortancası; bkz. [AUDIT-OLCUM.md](AUDIT-OLCUM.md) |
| `models/indir.sh` indirilen modeli SHA-256 ile doğrulamıyor. | DOĞRULANDI (yerel) | `curl -L --fail … -o "$ad.part"` (hash kontrolü yok) |

### DOĞRULANMADI

- **OpenVINO EP'nin YOLOX'ta genel bir "anlamlı hız" kazancı sağladığı:** Bu makinedeki ölçüm ~%10-15 kazanç gösterdi. Buna karşılık YOLOv5n'de OpenVINO'nun [varsayılan CPU EP'den yavaş kaldığı](https://github.com/openvinotoolkit/openvino/issues/22401) raporlanmış. Hedef donanımda ölçülmeden genellenemez.
- **Jetson Zoo'daki güncel wheel listesi:** elinux.org engelli.
- **PyPI wheel'inin spin varsayılanı:** `ORT_CLIENT_PACKAGE_BUILD` bayrağıyla derlenip derlenmediği bilinmiyor.
- **ORT 1.23-1.30 için kesin TensorRT alt sürümü:** Doğrulanmadı.
- **CVE-2026-14647'nin ORT 1.19.2'de fiilen tetiklenip tetiklenemediği:** Gömülü `onnx` 1.16.1'de aynı kod deseni var, ama deneyle sınanmadı.
- **pip'le gelen CUDA kütüphaneleriyle GPU'da uçtan uca çalışma:** Bu ortamda GPU yok.
- **JetPack 6.1'in CUDA 12.6 kullandığı:** NVIDIA sayfaları engelli.

### Projeye öneri (en az parça)

1. **Tek paket kuralı.** CPU sunucusunda yalnız `onnxruntime`, GPU sunucusunda yalnız `onnxruntime-gpu` kurulu olur. Kurulum betiği GPU için önce `pip uninstall -y onnxruntime` çalıştırır. Açılışta stdlib `importlib.metadata` ile iki paketin birlikte kurulu olup olmadığına bakılır ve öyleyse panelde uyarı gösterilir. Mevcut `get_providers()` uyarısı sorunun **nedenini** söylemiyor.
2. **Sürüm sabitini yükselt.** Kod değişikliği gerekmez, API aynı. Linux ve Docker (Python 3.12) için `onnxruntime==1.30.0`. Kazanç iki yönlü: gömülü `onnx` 1.22.0 ile model yükleme sertleştirmeleri gelir, ölçülen CPU hızı yaklaşık %25 artar. Intel Mac geliştirici hâlâ varsa ya tek sabit `==1.23.2` kullanılır, ya da ortam işaretçili iki satır yazılır. Değişiklikten sonra `pytest` ve gerçek bir RTSP/USB kamerayla tek bir tespit turu yeterli.
3. **GPU yolu.** Önce sürücünün CUDA 13'ü destekleyip desteklemediğine bakılır. Destekliyorsa 1.27 ve sonrası kullanılır, sunucu CUDA 12'de kalacaksa 1.26.x. CUDA kütüphaneleri sisteme elle kurulacağına `pip install onnxruntime-gpu[cuda,cudnn]` ile getirilir ve tek satırlık `onnxruntime.preload_dlls()` çağrılır. Kurulumda **tek karelik gerçek bir çıkarım** duman testi yapılır; `get_providers()` tek başına yetmez.
4. **Sessiz düşüş.** Mevcut uyarı yeterli. Operatör "CUDA yoksa hiç başlatma" kararı verirse `disable_cpu_ep_fallback` ayarı eklenir. Bu durumda `tespit.py`'deki genel `except` bloğu ayrıştırılmalı, yoksa CUDA eksikliği yanlışlıkla "model dosyası bozuk" olarak raporlanır.
5. **TensorRT ve Jetson MVP dışında.** Jetson hedeflenirse JetPack'e özel wheel ayrı bir `requirements-jetson.txt` dosyasında tutulur. İlk adım yine CUDA EP olur.
6. **OpenVINO MVP dışında.** Ayrı bir paket, 6 alt sürüm geride ve aynı dizine kuruluyor. Sürüm yükseltmesi daha büyük kazanç veriyor.
7. **INT8 MVP dışında.** Denenecekse yalnız geliştirici makinesinde yapılır; `onnx` paketi sunucu bağımlılıklarına girmez. Önce `lscpu | grep -i vnni` ile donanım kontrol edilir.
8. **İş parçacığı ayarlarına dokunulmaz.** 0 = otomatik kalır. `session.intra_op.allow_spinning=0` ancak ölçümle denenir.
9. **Export.** Resmi ONNX dosyaları yeterli. Kendi modelimiz export edilecekse decode kapalı, opset 11 ve batch 1 kullanılır. PyTorch 2.4 ya da daha eski bir sürüm sabitlenir, ya da çağrı `torch.onnx.export(..., dynamo=False)` olarak yamalanır.
10. **`models/indir.sh`'e SHA-256 kontrolü eklenir.** `sha256sum -c` ya da stdlib `hashlib` ile sabit bir hash karşılaştırılır. Bu tek satır, model yükleme açıklarına karşı ucuz bir savunma.

### Açık sorular

- Fabrika sunucusunun CPU'su ne? VNNI ya da AMX var mı?
- GPU olacak mı? Varsa hangi model ve hangi sürücü (CUDA 12 mi, 13 mü)?
- GPU paketini hangi betik kuracak? "İlk Kurulumu Yap" düğmesi `CIKARIM_CIHAZI` ayarına göre paket seçmeli mi?
- Jetson gerçekten bir hedef mi? Hedefse hangi JetPack sürümü?
- Intel Mac geliştirme kısıtı hâlâ geçerli mi?
- "CUDA seçili ama CPU'da çalışıyor" durumunda ne yapılmalı: uyarıyla devam mı, başlatmayı reddetmek mi?

---

## 6. supervision (ByteTrack / PolygonZone) ve OpenCV (RTSP, FaceDetectorYN, homografi)

### Özet

- **supervision:** DALSAN'ın kullandığı 0.25.1 sürümünün API'si PyPI'deki sdist kaynak koduyla birebir doğrulandı (0.25.1 için git etiketi yok). `sv.ByteTrack` 0.28'de deprecated oldu ve 0.31'de kaldırılacak. 0.30.x ise PyAV bağımlılığı getiriyor.
- **ByteTrack parametreleri:** `docs/03`'teki `track_buffer` adı 0.23'te kaldırıldı. DALSAN'da kayıp iz ömrü **1 saniye.**
- **PolygonZone gerekmiyor:** §4.2'nin ayak noktası kuralını DALSAN'ın stdlib kodu zaten karşılıyor.
- **RTSP:** OpenCV'nin RTSP ayarı doğru.
- **Yüz bulanıklaştırma:** YuNet lisansı MIT (Apache değil) ve dosya boyutu yanlış yazılmış.
- **Kalibrasyon:** Homografi zaten saf numpy ile yapılıyor.

### Olgular

| Olgu | Durum | Kaynak |
|---|---|---|
| supervision 0.25.1'de `sv.ByteTrack` yapıcısı: `track_activation_threshold=0.25`, `lost_track_buffer=30`, `minimum_matching_threshold=0.8`, `frame_rate: int = 30`, `minimum_consecutive_frames=1`. | DOĞRULANDI | [0.25.1 sdist](https://files.pythonhosted.org/packages/4c/87/3daaa3aec1766f93d4c07d33f933a5ded0a6243a099b6b399b6268053bfe/supervision-0.25.1.tar.gz) (`tracker/byte_tracker/core.py`; DALSAN .venv ile bayt bayt aynı) |
| Kayıp iz ömrü `int(frame_rate / 30 × lost_track_buffer)` kare. `det_thresh` değeri `track_activation_threshold + 0.1`. | DOĞRULANDI | aynı dosya: `self.max_time_lost = int(frame_rate / 30.0 * lost_track_buffer)` |
| DALSAN `frame_rate` olarak örnekleme hızını (`KARE_ORNEKLEME_FPS=6`) veriyor. Varsayılan ayarla kayıp iz ömrü 6 kare, yani **1,0 saniye.** `int()` kırpması yüzünden 6 fps'te `lost_track_buffer` 5'ten küçük verilirse ömür 0 kare olur. | DOĞRULANDI (yerel) | [boru_hatti.py](../backend/app/analiz/boru_hatti.py):120 `Takipci(fps)` |
| `update_with_detections` yalnız bir izle eşleşen tespitleri döndürüyor. Henüz geçerli sayılmayan izler (`NO_ID = -1`) de eleniyor. `confidence` alanı zorunlu. | DOĞRULANDI | [0.25.1 sdist](https://files.pythonhosted.org/packages/4c/87/3daaa3aec1766f93d4c07d33f933a5ded0a6243a099b6b399b6268053bfe/supervision-0.25.1.tar.gz): `return detections[detections.tracker_id != -1]` |
| `docs/03` §5'teki "ByteTrack `track_buffer`" parametresi 0.23.0'da kaldırıldı; doğru adı `lost_track_buffer`. `takip.py:30`'daki yorum da eski adı kullanıyor ve "yüksek tut" diyor, ama kod bu parametreyi hiç vermiyor. | DOĞRULANDI | [deprecated.md](https://github.com/roboflow/supervision/blob/develop/docs/deprecated.md): "removed as of supervision-0.23.0. Use lost_track_buffer" |
| `PolygonZone(polygon, triggering_anchors=(BOTTOM_CENTER,))` piksel koordinatı istiyor ve değerleri tam sayıya çeviriyor. `frame_resolution_wh` yapıcı parametresi değil. | DOĞRULANDI | 0.25.1 `polygon_zone.py`: `self.polygon = polygon.astype(int)` |
| `trigger()` bütün tetik noktaları bölgenin içindeyse True döndürüyor. `require_all_anchors` parametresi 0.30.0'da eklendi (kartta 0.30.5 yazıyordu). | DOĞRULANDI (küçük düzeltmeyle) | 0.25.1 ve 0.30.0 sdist karşılaştırması: `np.all(is_in_zone, axis=1)` |
| `BOTTOM_CENTER` noktası `((x1+x2)/2, y2)` ve DALSAN'ın `ayak_noktasi()` fonksiyonuyla aynı formül. `import supervision` tek başına cv2'yi yüklediği için `rules/` katmanında supervision'ın tamamı yasak. | DOĞRULANDI | 0.25.1 `detection/core.py` · [tipler.py](../backend/app/rules/tipler.py) |
| İddia: "§4.2'deki ayak noktası gereksinimi depoda bulunamadı." **Doğrusu:** `GOREV-TANIMI-V2.md` §4.2 bu kuralı içeriyor: "Bölge testi, kutunun MERKEZİYLE değil AYAK NOKTASIYLA (alt-orta) yapılır." Aynı yerde koordinatların 0..1 aralığında normalize olduğu da yazılı. | ÇÜRÜTÜLDÜ | [GOREV-TANIMI-V2.md](GOREV-TANIMI-V2.md) §4.2 |
| supervision'ın lisansı MIT. | DOĞRULANDI | [LICENSE.md](https://github.com/roboflow/supervision/blob/develop/LICENSE.md): "MIT License Copyright (c) 2022 Roboflow" |
| Sürüm takvimi: 0.25.1 (13 Ara 2024), 0.26.0 (Tem 2025), 0.27.0 (Kas 2025), 0.28.0 (30 Nis 2026), 0.29.x (Haz 2026), 0.30.0 (4 Ağu 2026) … 0.30.5 (22 Eyl 2026). 0.31.0 henüz yok. Güncel sürümler Python ≥3.10 istiyor. | DOĞRULANDI | [PyPI supervision JSON](https://pypi.org/pypi/supervision/json) |
| Kırıcı değişiklikler: 0.26.0 Python 3.8'i bıraktı. 0.27.0 `overlap_ratio_wh` parametresini kaldırdı. 0.28.0 ByteTrack'i deprecated yaptı ve `fps` değerini float'a çevirdi. 0.30.0'da OpenCV artık varsayılan bağımlılık değil, Python ≥3.10 gerekiyor ve kaldırmalar 0.31.0'a ertelendi. | DOĞRULANDI | [0.30.0 sürüm notu](https://github.com/roboflow/supervision/releases/tag/0.30.0): "OpenCV no longer installed by default" |
| 0.30.5'te ByteTrack `@deprecated_class(remove_in="0.31.0")` ile işaretli. Yerine `trackers.ByteTrackTracker` ve `update()` metodu geliyor. 0.30.5'in bağımlılıkları arasında `av>=14.2` (PyAV) ve `pydeprecate` var. | DOĞRULANDI | [deprecated.md](https://github.com/roboflow/supervision/blob/develop/docs/deprecated.md): "its update method is update(), not update_with_detections()" |
| `trackers` paketi 2.6.0 sürümünde; lisansı Apache-2.0, Python ≥3.10 istiyor. | DOĞRULANDI | [PyPI trackers](https://pypi.org/pypi/trackers/json): "license": "Apache License 2.0" |
| opencv-python wheel'leri kendi FFmpeg'ini (LGPLv2.1) taşıyor. GUI'li Linux wheel'leri Qt5 (LGPLv3) içeriyor. Dört paketten yalnız biri kurulmalı. | DOĞRULANDI | [opencv-python README](https://github.com/opencv/opencv-python): "All wheels ship with FFmpeg licensed under the LGPLv2.1." |
| Dockerfile'daki apt `ffmpeg` paketini cv2 kullanmıyor ve backend ffmpeg komut satırını çağırmıyor. Kaldırma adayı. | DOĞRULANDI (yerel) | `/Dockerfile` satır 8-11 · .venv'deki `opencv_python.libs/libavcodec-*.so.59.37.100` |
| `OPENCV_FFMPEG_CAPTURE_OPTIONS` değişkeni VideoCapture açılırken okunuyor ve `anahtar;değer\|anahtar;değer` biçiminde ayrıştırılıyor. `kamera.py:38`'deki ayar doğru. | DOĞRULANDI | [cap_ffmpeg_impl.hpp 4.10.0](https://github.com/opencv/opencv/blob/4.10.0/modules/videoio/src/cap_ffmpeg_impl.hpp): `av_dict_parse_string(&dict, options, ";", "\|", 0);` |
| Değişken tanımlı değilse OpenCV 4.6 ve sonrası `rtsp_flags=prefer_tcp` kullanıyor. DALSAN'ın `rtsp_transport;tcp` ayarı TCP'yi **zorluyor.** | DOĞRULANDI | [PR #21561](https://github.com/opencv/opencv/pull/21561): "Default FFMPEG VideoCapture backend to rtsp_flags=prefer_tcp" |
| FFmpeg'in `rtsp_transport` seçeneği udp, tcp, udp_multicast, http ve https değerlerini alıyor. Birden çok değer verilirse sırayla deneniyor. | DOĞRULANDI | [protocols.texi](https://github.com/FFmpeg/FFmpeg/blob/master/doc/protocols.texi): "Multiple lower transport protocols may be specified" |
| opencv-python sürümleri: en yeni 5.0.0.93, 4.x hattının sonuncusu 4.14.0.94, DALSAN'ın kullandığı 4.10.0.84 Haziran 2024 tarihli. Lisans Apache 2.0. | DOĞRULANDI | [PyPI opencv-python](https://pypi.org/pypi/opencv-python/json) |
| `cv2.FaceDetectorYN` 4.10.0'da `objdetect` modülünde bulunuyor (4.5.4'ten beri var). `create(model, config, input_size, score_threshold=0.9, …)` imzası; `detect()` `[num_faces, 15]` boyutunda sonuç döndürüyor. Ek pip paketi gerekmiyor. | DOĞRULANDI | [face.hpp 4.10.0](https://github.com/opencv/opencv/blob/4.10.0/modules/objdetect/include/opencv2/objdetect/face.hpp) |
| YuNet model dosyaları: `2023mar` sabit girdili ve OpenCV 4.x için; `2026may` dinamik girdili, OpenCV 5.x için ve deponun **varsayılanı.** Model dizini MIT, depo kökü Apache-2.0 lisanslı. YuNet yaklaşık 10×10 ile 300×300 piksel arası yüzleri buluyor. | DOĞRULANDI | [opencv_zoo YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet): "faces of pixels between around 10x10 to 300x300" |
| İddia: "YuNet model dosyası Apache-2.0 lisanslı." **Doğrusu:** Lisans MIT, "Copyright (c) 2020 Shiqi Yu". Apache-2.0 yalnız depo kökünün lisansı. | ÇÜRÜTÜLDÜ | [YuNet LICENSE](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/LICENSE): "MIT License Copyright (c) 2020 Shiqi Yu" |
| İddia: "`face_detection_yunet_2023mar.onnx` yaklaşık 338 KB." **Doğrusu:** Dosya 232.589 bayt; sha256 değeri `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`. 338 KB, öğreticinin anlattığı eski modele ait. | ÇÜRÜTÜLDÜ | [Git LFS işaretçisi](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx) |
| `findHomography`, `getPerspectiveTransform` (4 nokta çifti) ve `perspectiveTransform` (seyrek noktalar) imzaları doğrulandı. | DOĞRULANDI | [calib3d.hpp 4.10.0](https://github.com/opencv/opencv/blob/4.10.0/modules/calib3d/include/opencv2/calib3d.hpp) |
| İddia: "Proje büyük olasılıkla `cv2.findHomography` kullanıyor." **Doğrusu:** `rules/kalibrasyon.py` tam 4 nokta çiftinden saf numpy ile doğrudan doğrusal dönüşüm (DLT) hesaplıyor (`np.linalg.solve`). `docs/05` ise "OpenCV homografi, `rules/calibration.py`" yazıyor; belge kodla çelişiyor. | ÇÜRÜTÜLDÜ | [kalibrasyon.py](../backend/app/rules/kalibrasyon.py): "saf numpy (OpenCV YOK, CLAUDE.md §6)" |
| DALSAN supervision'dan yalnız ByteTrack kullanıyor. `PolygonZone` depoda yalnız `docs/05`'te geçiyor. | DOĞRULANDI (yerel) | [takip.py](../backend/app/analiz/takip.py): `sv.ByteTrack(frame_rate=max(fps, 1))` |
| GOREV §4.10'a göre yüz bulanıklaştırma isteğe bağlı ve yalnız saklanan klip ile dışa aktarımlar için. §4.4'e göre izleme ByteTrack ya da BoT-SORT ile yapılacak; Re-ID v1'in dışında. | DOĞRULANDI (yerel) | [GOREV-TANIMI-V2.md](GOREV-TANIMI-V2.md) §4.4, §4.10 |
| Geliştirme ortamındaki .venv Python 3.11.15 kullanıyor, hedef 3.12. numpy sabitlenmemiş; kurulu sürüm 2.4.6. | DOĞRULANDI (yerel) | `.venv/bin/python --version` · [Dockerfile](../Dockerfile) `python:3.12-slim` |

### DOĞRULANMADI

- **supervision.roboflow.com'daki sürümlü belgeler:** Engelli. Kaynak kod esas alındı.
- **`prefer_tcp`'nin sahada UDP'ye düşme davranışı:** Doğrulanmadı.
- **Python 3.12 + numpy 2.x + supervision 0.25.1 + OpenCV 4.10.0.84 + ORT 1.19.2 birleşimi:** Bu birleşim hiç test edilmedi.

### Projeye öneri (en az parça)

1. **supervision 0.25.1'de kalınır.** 0.30.x'e geçmek `trackers` ve PyAV paketlerini getirir. `docs/07`'ye tek satır not düşülür: "0.31 ve sonrasına geçişte `trackers.ByteTrackTracker` kullanılacak; `update_with_detections()` → `update()`."
2. **PolygonZone eklenmez.** §4.2 ayak noktası kuralı zaten `ayak_noktasi()` ve stdlib ray-casting ile karşılanıyor. PolygonZone ayrıca cv2 yasağına, piksel koordinatına ve tam sayı maskeye takılır. Kuralın korunduğunu göstermek için `tests/rules` altına iki küçük test yeter.
3. **Kalıcı iz ömrü bir parametreyle ayarlanır, kütüphaneyle değil.** Saniye cinsinden bir `.env` anahtarı (ör. `TAKIP_KAYIP_IZ_SN`) eklenir. Kod bunu `lost_track_buffer = saniye × 30` olarak geçirir (kare sayısı olarak değil). `docs/03` §5 ve `takip.py:30` yorumu düzeltilir.
4. **RTSP ayarı olduğu gibi kalır.** PyAV, GStreamer ve ffmpeg-python eklenmez. Açılışta zaman aşımı parametreleri eklenir (§8). UDP'den başka bir şey konuşmayan bir kamera çıkarsa değişken `.env`'den geçersiz kılınabilir; bu durum `docs/12`'ye bir satır olarak yazılır.
5. **Yüz bulanıklaştırma Faz 2'de kalır.** İlk yol modelsizdir: kişi kutusunun üst yaklaşık %20'si bulanıklaştırılır. Uzak kameralarda YuNet zaten 10 pikselin altındaki yüzleri bulamıyor. Kalite yetmezse `cv2.FaceDetectorYN` ile birlikte **`2023mar`** dosyası kullanılır (depo varsayılanı olan `2026may` OpenCV 5 ister). Dosya 232.589 bayt; `indir.sh` üzerinden yukarıdaki sha256 değeriyle indirilir. `LICENSE-THIRD-PARTY`'ye "MIT, Copyright (c) 2020 Shiqi Yu" yazılır.
6. **Kalibrasyonda numpy korunur.** 4 nokta çifti için sonuç aynı; RANSAC ancak 4'ten fazla gürültülü noktada anlam taşır.
7. **Belge düzeltmeleri:** `docs/05` şöyle düzeltilir: "ByteTrack (yalnız)", "saf numpy homografi", `rules/kalibrasyon.py`.
8. **Dockerfile'daki `ffmpeg` apt paketi** bir RTSP provasından sonra kaldırılabilir.
9. **Geliştirme ortamı hedefe çekilir.** .venv Python 3.12 ile yeniden kurulur, testler 3.12'de koşar. numpy için alt ve üst sınır konması değerlendirilir.

### Açık sorular

- supervision 0.31 çıktığında ne yapılacak: 0.25.1'de süresiz mi kalınacak, yoksa Faz 2'de `trackers` paketine mi geçilecek?
- KVKK birimi yüz bulanıklaştırmayı şart koşuyor mu? Kutunun üst kısmını bulanıklaştırma yöntemi kabul edilir mi?
- Sahada yalnız UDP konuşan bir kamera var mı?
- Kayıp iz ömrü için hedef süre kaç saniye?

---

## 7. KVKK: iş yerinde kamerayla izleme yükümlülükleri

> **Bu bölüm hukuki tavsiye değildir; her madde için avukat teyidi gerekir.** Kanun, yönetmelik ve tebliğ metinleri resmi sitelerden açılamadı. Metinler bağımsız GitHub kopyalarında birebir eşleşmeyle doğrulandı. Kurul kararları ve 2026 duyuruları ise **yalnız arama özetleriyle** doğrulanabildi: sayfa başlıkları kvkk.gov.tr'den, içerik özetlerden. Bu kayıtlar tabloda "DOĞRULANDI (özet)" olarak işaretli ve güven düzeyleri daha düşük.

### Özet

İSG amacıyla kullanılan ve biyometrik analiz yapmayan kamera görüntüsü **genel nitelikli** kişisel veridir ve KVKK m.5 kapsamında değerlendirilir. Dayanak olarak m.5/2-ç (6331 m.4'ten doğan hukuki yükümlülük) ve m.5/2-f (meşru menfaat) öne çıkıyor (2022/797).

Ses kaydı, görüntünün yettiği yerde ölçülülük ilkesine aykırı bulunmuş (2020/212, 2023/2007). Yüz tanıma da ölçülülük ilkesine aykırı bulunup 500.000 TL cezayla sonuçlanmış (2022/797).

2026/921 sayılı İlke Kararı **yalnız mesai takibini** kapsıyor (27.08.2026 duyurusu). Mevzuatta sabit bir saklama süresi yok; ilke "mümkün olan en kısa süre ve otomatik imha" şeklinde.

### Olgular

| Olgu | Durum | Kaynak |
|---|---|---|
| KVKK m.10: Veri sorumlusu ilgili kişiyi beş konuda bilgilendirmek zorunda: kimliği, işlemenin amacı, verinin kime aktarılacağı, toplama yöntemi ve hukuki sebebi, m.11'deki haklar. | DOĞRULANDI | [6698 sayılı Kanun](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5): "Kişisel veri toplamanın yöntemi ve hukuki sebebi" |
| Aydınlatma Tebliği (RG 10.03.2018/30356) m.5: Amaç değişirse yeniden aydınlatma yapılır (b); ispat yükü veri sorumlusundadır (e); hukuki sebep açıkça belirtilir (h). m.5/1-c 2019'da yürürlükten kaldırıldı. | DOĞRULANDI | [Tebliğ (RG)](https://www.resmigazete.gov.tr/eskiler/2018/03/20180310-5.htm): "Aydınlatma yükümlülüğünün yerine getirildiğinin ispatı veri sorumlusuna aittir" |
| İddia: "Tebliğ 'katmanlı aydınlatma', 'kamera' ve 'tabela/levha' ifadelerini içeriyor." **Doğrusu:** Tebliğde bu ifadelerin hiçbiri geçmiyor. Katmanlı yöntem Aydınlatma Rehberi'nden ve Kamuoyu Duyurusu'ndan, kamera levhası uygulaması ise Kurul kararlarındaki pratikten geliyor. | ÇÜRÜTÜLDÜ | [Tebliğ](https://www.resmigazete.gov.tr/eskiler/2018/03/20180310-5.htm) |
| Katmanlı aydınlatma kabul edilen bir yöntem. İlk katmanda en azından veri sorumlusunun kimliği ve işleme amacı verilmeli (duyuru, 26 Haz 2020). | DOĞRULANDI (özet) | [Kamuoyu Duyurusu](https://www.kvkk.gov.tr/Icerik/6765/AYDINLATMA-YUKUMLULUGUNUN-YERINE-GETIRILMESI-HAKKINDA-KAMUOYU-DUYURUSU): "ilk aşamada temel bilgilerin … sunulduğundan emin olunmalı" |
| Kurul kararı 2023/2007 (30.11.2023): İş yerinde görüntü kaydı güvenlik amacına yetiyorken ayrıca ses kaydı alınmasında meşru menfaat yok. Ses verilerinin imhası talimatı verildi. Veri sorumlusunun uyguladığı aydınlatma yöntemi (girişlerde metin, sarı zemin üzerine kamera işaretli levhalar, kişi grubuna göre ayrı metinler) kararda yer alıyor. | DOĞRULANDI (özet) | [2023/2007](https://www.kvkk.gov.tr/Icerik/8846/2023-2007): "ilaveten ses kaydı alınmasında Veri Sorumlusunun meşru menfaatinin bulunmadığı" |
| Kurul kararı 2022/797 (04.08.2022; tehlikeli sınıfta bir kâğıt fabrikası): Biyometrik analiz yapmayan İSG kamerası genel nitelikli veri işler. İSG kamerası m.5/2-ç, e ve f kapsamında değerlendirilebilir. Soyunma odası, tuvalet, duş, mescit, dinlenme ve emzirme odası gibi alanlarda makul mahremiyet beklentisi var. | DOĞRULANDI (özet) | [2022/797](https://www.kvkk.gov.tr/Icerik/7434/2022-797): "kameralar vasıtasıyla işlenen kişisel verilerin genel nitelikte kişisel veri olduğu" |
| Aynı kararda işe giriş-çıkışta yüz tanıma: İstihdamdaki güç dengesizliği yüzünden açık rıza geçersiz. Kart, RFID ve SMS gibi alternatifler varken yüz tanıma ölçülü değil. Sonuç: 500.000 TL ceza, biyometrik verilerin imhası ve biyometrik girişin durdurulması. | DOĞRULANDI (özet) | [2022/797](https://www.kvkk.gov.tr/Icerik/7434/2022-797): "manyetik kart sistemi, RFID etiketi, cep telefonuna gönderilecek bir SMS" |
| Kurul kararı 2020/212 (12.03.2020; olay bir kamu kurumunda): Görüntü aynı faydayı sağlıyorsa ayrıca ses kaydı yapmak ölçülülük ilkesine aykırı. | DOĞRULANDI (özet) | [2020/212](https://www.kvkk.gov.tr/Icerik/6892/2020-212): "ses kaydının da yapılması … ölçülülük ilkesine aykırılık teşkil edecektir" |
| KVKK m.6, 7499 sayılı Kanunla değişti (yürürlük 1.6.2024). Yeni m.6/3'e göre özel nitelikli veri işlemek yasak; ancak açık rıza, kanunda açıkça öngörülme veya (f) "istihdam, iş sağlığı ve güvenliği … hukuki yükümlülükler için zorunlu olma" hâllerinde mümkün. m.6/4 ayrıca yeterli önlemleri şart koşuyor (Kurul kararı 2018/10). | DOĞRULANDI | [6698 m.6](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5): "f) İstihdam, iş sağlığı ve güvenliği … hukuki yükümlülüklerin yerine getirilmesi için zorunlu olması" |
| İlke Kararı 2026/921 (29.04.2026; RG 02.06.2026/33268): Yalnız mesai takibi amacıyla biyometrik veri işlemek m.6'daki hiçbir şarta dayanmıyor; açık rıza olsa bile ölçülülük ilkesini karşılamıyor. Alternatif olarak kart, PIN, RFID/NFC ve imza öneriliyor. | DOĞRULANDI (özet) | [Duyuru](https://www.kvkk.gov.tr/Icerik/8762/mesai-takibi-amaciyla-biyometrik-veri-islenmesi-hakkinda-kisisel-verileri-koruma-kurulunun-29-04-2026-tarihli-ve-2026-921-sayili-ilke-kararina-iliskin-kamuoyu-duyurusu) |
| 27.08.2026 duyurusu: İlke Kararı **yalnız mesai takibini** kapsıyor. Diğer biyometrik işlemelerin hukuka uygunluğunu veri sorumlusu somut olayına göre kendisi değerlendirmeli. | DOĞRULANDI (özet) | [Duyuru (Icerik/8912)](https://www.kvkk.gov.tr/Icerik/8912/29-04-2026-tarihli-ve-2026-921-sayili-mesai-takibi-amaciyla-biyometrik-veri-islenmesi-hakkinda-ilke-karari-na-iliskin-gorus-talepleri-hakkinda-kamuoyu-duyurusu): "Mesai takibi dışında kalan biyometrik veri işleme faaliyetleri, İlke Kararı kapsamında değerlendirilmeyecek" |
| İş Yerleri kamera duyurusu (8 Haz 2026) şu ilkeleri koyuyor: Meşru amaç İSG, iş yeri güvenliği ve suçun önlenmesi. Sürekli gözetim ile performans ve disiplin takibi meşru amaç değil. Tuvalet, soyunma odası ve mescitte kamera olmaz. Yetki matrisi kurulur. Saklama süresi mümkün olan en kısa süre olur ve otomatik imha yapılır. Bir olay yaşanırsa hukuki süreç boyunca yalnız ilgili kayıt saklanır. | DOĞRULANDI (özet) | [İş Yerleri duyurusu (8770)](https://www.kvkk.gov.tr/Icerik/8770/is-yerlerinde-guvenlik-kamerasi-sistemi-kullaniminda-dikkat-edilecek-hususlara-dair-kamuoyu-duyurusu): "sadece ilgili olan kayıt saklanmalıdır" |
| İddia: "8 Haziran İş Yerleri duyurusu, kamera sisteminin yüz tanıma ve ses kaydı özelliği **içermemesi** gerektiğini söylüyor." **Doğrusu:** Bu cümle aynı gün yayımlanan **Apartmanlar** duyurusuna (8769) ait. İş Yerleri duyurusunda ifade koşullu: ses kaydı "hukuka uygun gerekçesi ve gerekliliği açıkça ortaya konulmadan" kullanılmamalı, yüz tanıma "dikkatle değerlendirilmeli". | ÇÜRÜTÜLDÜ (kısmen) | [Apartmanlar duyurusu (8769)](https://www.kvkk.gov.tr/Icerik/8769/apartmanlarda-guvenlik-kamerasi-sistemi-kullaniminda-dikkat-edilecek-hususlara-dair-kamuoyu-duyurusu): "yüz tanıma, ses kaydı gibi … teknik özellikleri barındırmamalıdır" |
| Apartmanlar duyurusu ayrıca kameraların dar açıdan kayıt almasını ve gereksiz alanların maskelenmesini istiyor. Bu, iş yerleri için de Kurum'un teknik yaklaşımını gösteriyor. | DOĞRULANDI (özet) | [8769](https://www.kvkk.gov.tr/Icerik/8769/apartmanlarda-guvenlik-kamerasi-sistemi-kullaniminda-dikkat-edilecek-hususlara-dair-kamuoyu-duyurusu) |
| m.4/2-d: Veri yalnız gerekli olduğu süre kadar saklanır. m.7: Sebep ortadan kalkınca veri silinir, yok edilir ya da anonim hâle getirilir. | DOĞRULANDI | [6698](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5): "işlendikleri amaç için gerekli olan süre kadar muhafaza edilme" |
| Silme Yönetmeliği (RG 28.10.2017/30224): VERBİS'e kayıt yükümlüsü olanlar saklama ve imha politikası hazırlar (m.5). Periyodik imha en geç 6 ayda bir yapılır (m.11/2). Politika yükümlüsü olmayanlar 3 ay içinde imha eder (m.11/3). İlgili kişinin talebi 30 günde karşılanır (m.12). İmha kayıtları en az 3 yıl saklanır (m.7/3). | DOĞRULANDI | [Yönetmelik (RG)](https://www.resmigazete.gov.tr/eskiler/2017/10/20171028-10.htm): "Bu süre her halde altı ayı geçemez." |
| VERBİS muafiyeti (Kurul kararı 2025/1572): Yıllık çalışan sayısı 50'den az **ve** mali bilanço toplamı 100 milyon TL'den az olan veri sorumluları kayıttan muaf. | DOĞRULANDI (özet) | [Duyuru (8577)](https://www.kvkk.gov.tr/Icerik/8577/kisisel-verileri-koruma-kurulunun-04-09-2025-tarihli-ve-2025-1572-sayili-kararinin-uygulama-esaslarina-iliskin-kamuoyu-duyurusu) |
| m.5/2-ç (hukuki yükümlülük için zorunluluk) ve m.5/2-f (meşru menfaat için zorunluluk) açık rıza gerektirmeyen işleme şartları. | DOĞRULANDI | [6698 m.5](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5) |
| 6331 m.4/1: İşveren İSG tedbirlerine uyulup uyulmadığını izler ve denetler (b). Hayati tehlike bulunan yerlere yetkisiz girişe karşı tedbir alır (d). | DOĞRULANDI | [6331](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6331&MevzuatTur=1&MevzuatTertip=5): "tedbirlere uyulup uyulmadığını izler, denetler" |
| 6331 m.18/1-b: İşveren, yeni teknolojilerin çalışan sağlığı ve güvenliğine etkisi konusunda çalışanların ya da temsilcilerinin görüşünü alır. | DOĞRULANDI | [6331](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6331&MevzuatTur=1&MevzuatTertip=5): "Yeni teknolojilerin uygulanması … görüşlerinin alınması" |
| KVKK m.11/1-g: İlgili kişi, yalnız otomatik sistemlerle yapılan analiz sonucunda aleyhine bir sonuç çıkmasına itiraz edebilir. | DOĞRULANDI | [6698 m.11](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5): "münhasıran otomatik sistemler vasıtasıyla analiz edilmesi" |
| m.12: Veri sorumlusu teknik ve idari tedbirleri almakla yükümlü ve veri işleyenle birlikte **müştereken** sorumlu. İhlal durumunda bildirim yapılır. | DOĞRULANDI | [6698 m.12](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5) |
| m.18'deki taban ceza aralıkları: aydınlatma 5.000-100.000 TL, veri güvenliği 15.000-1.000.000 TL. Tutarlar her yıl yeniden değerleme oranında artıyor. Kurul cezalarına karşı idare mahkemesinde dava açılabiliyor. | DOĞRULANDI | [6698 m.18](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5) |
| İddia: "2026/347 sayılı İlke Kararı RG 31.03.2026/33210'da yayımlandı." **Doğrusu:** Karar **RG 24.03.2026/33203**'te yayımlandı. İçerik doğru: açık rıza metni ile aydınlatma metni ayrı ayrı düzenlenmeli (Tebliğ m.5/1-f ile uyumlu). | ÇÜRÜTÜLDÜ (künye) | [RG 24.03.2026](https://www.resmigazete.gov.tr/eskiler/2026/03/20260324-3.pdf) · [Duyuru (8710)](https://www.kvkk.gov.tr/Icerik/8710/veri-sorumlulari-tarafindan-acik-riza-ve-aydinlatma-metinlerinin-ayri-ayri-duzenlenmesi-gerektigi-hakkinda-kisisel-verileri-koruma-kurulunun-18-02-2026-tarihli-ve-2026-347-sayili-ilke-kararina-iliskin-kamuoyu-duyurusu) |
| İlgili rehberler: Biyometrik Veri Rehberi (Eyl 2021), Kişisel Veri Güvenliği Rehberi, Aydınlatma Rehberi, Kurul'un yeterli önlemler kararı (2018/10) ve Özel Nitelikli Veri Rehberi (26.02.2025; 7499 sonrası m.6 yorumu için güncel kaynak). | DOĞRULANDI (varlıkları; içerikleri okunmadı) | [Biyometrik Rehber](https://www.kvkk.gov.tr/Icerik/7047/Biyometrik-Verilerin-Islenmesinde-Dikkat-Edilmesi-Gereken-Hususlara-Iliskin-Rehber) · [Özel Nitelikli Rehber (PDF)](https://www.kvkk.gov.tr/SharedFolderServer/CMSFiles/70f95c73-06a2-44dc-81e9-34201bdd7f5c.pdf) |
| 2022/797'de aydınlatma metni yüz tanımadan hiç söz etmediği için, o veri bakımından aydınlatma yükümlülüğü yerine getirilmemiş sayıldı. Ek bir işleme varsa metinde ayrıca yazılmalı. | DOĞRULANDI (özet) | [2022/797](https://www.kvkk.gov.tr/Icerik/7434/2022-797) |

### DOĞRULANMADI

- **Kamera görüntülerinin "genel uygulama olarak 15-30 gün" saklanması:** Yalnız bir yorum yazısında ([alomaliye](https://www.alomaliye.com/2026/06/08/is-yerlerinde-guvenlik-kamerasi-kullaniminda-dikkat-edilecek-hususlar/)) geçiyor. Kanunda, yönetmelikte ya da Kurum duyurusunda **sabit bir gün sayısı yok.** Kural gibi yazılmamalı.
- **2023/2007'deki 125.000 TL ceza tutarı:** Yalnız tek bir arama özetinde geçiyor; karar metninden teyit edilmeli.
- **2026 yılı güncel ceza tutarları** (ör. aydınlatma 85.437-1.709.200 TL; veri güvenliği 256.357-17.092.242 TL): Yalnız ikincil kaynaklarda var. Resmi tablo ([Icerik/8145](https://www.kvkk.gov.tr/Icerik/8145/6698-sayili-kisisel-verilerin-korunmasi-kanunu-kapsaminda-idari-para-cezasi-tutarlari)) okunamadı.
- **2022/797'deki "değerlendirmede dikkate alınacak unsurlar" listesi** (kamera sayısı, görüş açısı, saklama süresi vb.): Doğrulanmadı.
- **2022/797'deki "rıza dışı bir dayanak varken rızaya dayanmak aldatıcıdır" ifadesi:** Doğrulanmadı.
- **Biyometrik Rehber'in 2024'te güncellendiği:** Doğrulanmadı.
- **6331 m.18'deki danışma yükümlülüğünün yapay zekâ kamera sistemine uygulanıp uygulanmadığı:** Bu bir yorum sorusu; avukata sorulmalı.

### Projeye öneri (en az parça)

1. **Yüz tanıma ve kimliklendirme yapılmaz.** Mevcut karar korunur ama **gerekçesi düzeltilir.** Dayanak m.4 ölçülülük ilkesi, 2022/797 ve m.6/3'te somut bir şartın bulunmamasıdır. 2026/921 mesai takibine özgü; ancak **benzetme yoluyla** anılabilir. "Açık rıza gerekir" cümlesi 2024 öncesinin hukukudur.

   Mühendislik karşılığı: ByteTrack `track_id`'si oturum içinde geçici bir kimlik olarak kalır. İz ile personel eşlemesi, yüz kırpıntısı, embedding ve Re-ID **hiçbir tabloya yazılmaz.** Bir "saklanmayanlar" listesi ve bunu doğrulayan bir test yeterli.
2. **Ses işlenmez.** OpenCV VideoCapture zaten ses okumuyor. Ara kayıt için ffmpeg kullanılırsa `-an` bayrağı zorunlu olur. Belgeye "sistem ses işlemez" cümlesi eklenir. Dayanaklar: 2020/212 ve 2023/2007. 8770 duyurusu ses kaydını koşullu olarak kısıtlıyor.
3. **Amaç ürün düzeyinde sınırlanır.** Sistem yalnız İSG olayları üretir. Mesai takibi, kişi bazlı performans ve "en çok ihlal yapan çalışan" gibi raporlar eklenmez (8770).
4. **İnsan onayı.** m.11/1-g gereği uyarılar bölge ve konum bazlı kalır. Bir kişi için sonuç doğmadan önce İSG uzmanı onayı şart koşulur; bu durum aydınlatma metnine yazılır. Yeni parça gerekmez.
5. **Saklama olay tabanlı olur.** Ham akış diske yazılmaz; yalnız olay klibi ve olayın meta verisi saklanır. Tek bir `.env` anahtarı (ör. `SAKLAMA_GUN`) ve FastAPI içinde çalışan stdlib bir temizlik döngüsü yeter (SQLite `DELETE` ve `os.remove`). En geç 6 ayda bir periyodik imha şartı günlük çalışmayla fazlasıyla karşılanır. Varsayılan gün sayısını **müşteri ve avukat** belirler; GOREV §4.9'daki "30 gün" bir kural değil.
6. **Olay dondurma.** Olaylar tablosuna `hold` ve `hold_reason` kolonları eklenir. Dondurulmuş kayıtlar temizlikten muaf tutulur (8770: "yalnız ilgili kayıt"; 6331 m.14).
7. **İmha günlüğü.** Her temizlik çalıştırması `purge_log` tablosuna yazılır. Bu tablo kişisel veri içermez ve en az 3 yıl saklanır (Yönetmelik m.7/3).
8. **Erişim denetimi ve günlüğü.** Klip görüntüleme ve indirme uçları kimlik doğrulaması ister. Her erişim (kim, ne zaman, hangi olay) SQLite'a yazılır (m.12, 2018/10, 8770 yetki matrisi). Mevcut `Depends` mekanizması ve `logging` yeterli.
9. **Kamera yerleşimi.** Kurulum kontrol listesine şu madde girer: "Tuvalet, soyunma odası, duş, mescit, dinlenme ve emzirme odası görüş alanında olamaz." Önce kameranın açısı düzeltilir; piksel maskesi ancak kaçınılmazsa kullanılır (8769: dar açı ve maskeleme). Aynı listeye "İSG kurulu ya da çalışan temsilcisine danışıldı" maddesi eklenir (6331 m.18).
10. **Aydınlatma paketi iki katmanlıdır.** (1) Kameralı alanlarda sarı zemin üzerine kamera işaretli kısa levha: veri sorumlusu, "İSG amacıyla görüntü işlenmektedir" ibaresi ve tam metnin nerede bulunacağı. (2) Tam metin: m.10'daki beş unsur ve hukuki sebep olarak m.5/2-ç ile m.5/2-f. Tam metinde "yüz tanıma yapılmaz, ses kaydı alınmaz" ibaresi, saklama süresi ve erişim yetkilileri yer alır. **Açık rıza kutucuğu konmaz** (2026/347; dayanak m.5/2-ç ve f). Mevcut CCTV için bir metin varsa yeni amaç için güncellenmesi gerekir (Tebliğ m.5/1-b).
11. **Rol ve sözleşme.** DALSAN ile müşteri arasında bir veri işleyen sözleşmesi yapılır (m.12/2 müşterek sorumluluk). Bulut, telemetri ve yurt dışı aktarımı olmaz. VERBİS eşiğini değerlendirmek müşterinin sorumluluğundadır.
12. **`docs/KVKK.md`.** Tek sayfalık bir uyum kartı yazılır. Her satır şöyle kurulur: yükümlülük → kaynak → üründeki karşılığı → "avukat teyidi gerekir".

### Açık sorular

- Veri sorumlusu kim? DALSAN yalnız veri işleyen mi, yoksa görüntüler DALSAN altyapısına da akıyor mu?
- Müşterinin çalışan sayısı ve bilançosu VERBİS eşiğini aşıyor mu? NACE tehlike sınıfı ne?
- Olay klipleri kaç gün saklanacak? Olay dondurma kararını kim verecek?
- Uyarılar kişi adıyla mı verilecek? Önerimiz hayır: yalnız bölge veya konum.
- Mevcut CCTV için bir aydınlatma metni var mı?
- RTSP akışlarında ses kanalı var mı?
- Herhangi bir kameranın görüş alanında mahremiyet beklentisi olan bir alan var mı?
- Son karardan önce bir avukat 2022/797, 2023/2007, 2026/921, 8770 ve 8912'yi bu ürün özelinde değerlendirecek mi?

---

## 8. Sağlık, metrik, bekçi (watchdog), SSE ve Python 3.12; OpenCV okuma davranışı

### Özet

- **Metrik:** Prometheus metin biçimi elle üretilebilir; Prometheus 3 geçerli bir `Content-Type` başlığını zorunlu tutuyor.
- **systemd bekçisi:** Protokolü stdlib `socket` ile yazılabiliyor (systemd'nin kendi MIT-0 örneği var).
- **Docker:** Sağlık kontrolü yalnız durumu değiştirir, container'ı yeniden başlatmaz. Açılışta çöken bir container ise yeniden başlatma döngüsüne girer; ilk karttaki "10 saniye" iddiası yanlış.
- **Belgedeki systemd birimi:** Bugün hiç başlamıyor. Paketlenmiş masaüstü uygulamasında "takılınca çık" deseni Kontrol Paneli'ni de öldürür.
- **SSE:** Proje SSE'yi ek paket olmadan kullanıyor. FastAPI 0.135 ve sonrasında yerleşik SSE var.
- **OpenCV:** FFmpeg arka ucunda `read()` varsayılan olarak 30 saniyeye kadar bloklayabilir. `CAP_PROP_BUFFERSIZE` bu arka uçta işlevsiz.

### Olgular

| Olgu | Durum | Kaynak |
|---|---|---|
| Prometheus metin biçimi 0.0.4 için kurallar: `Content-Type: text/plain; version=0.0.4`, UTF-8, satır sonu `\n` ve son satır da `\n` ile biter. Bir metriğin bütün satırları tek grup hâlinde yazılır, `HELP` ve `TYPE` önce gelir. Etiket değerlerinde `\`, `"` ve satır sonu kaçışlanır. | DOĞRULANDI | [exposition_formats.md](https://raw.githubusercontent.com/prometheus/docs/main/docs/instrumenting/exposition_formats.md): "The last line must end with a line feed character." |
| Prometheus 3 geçerli bir `Content-Type` başlığı istiyor; başlık yoksa scrape başarısız oluyor. Telafi için sunucu tarafında `fallback_scrape_protocol` ayarı var. | DOĞRULANDI | [migration.md](https://raw.githubusercontent.com/prometheus/prometheus/main/docs/migration.md): "Prometheus v3 will now fail the scrape in such cases." |
| Prometheus 3'ün varsayılan protokol listesinde `PrometheusText0.0.4` hâlâ var. | DOĞRULANDI | [configuration.md](https://raw.githubusercontent.com/prometheus/prometheus/main/docs/configuration/configuration.md) |
| `prometheus_client` 0.26.0 (24 Tem 2026): Lisansı **Apache-2.0 AND BSD-2-Clause** (içinde decorator 4.0.10 gömülü). Python ≥3.9, zorunlu bağımlılığı yok, wheel boyutu 64.494 bayt. Varsayılan içerik tipi artık `version=1.0.0`; 0.0.4 "uyumluluk biçimi" olarak duruyor. | DOĞRULANDI | [PyPI prometheus-client](https://pypi.org/pypi/prometheus-client/json): "Apache-2.0 AND BSD-2-Clause" |
| sd_notify protokolü: `$NOTIFY_SOCKET` adresine tek bir datagram gönderilir (adres `/` ya da `@` ile başlar). `WATCHDOG=1` canlılık sinyali. `READY=1` yalnız `Type=notify` birimlerinde kullanılıyor. `WATCHDOG=trigger` de var. | DOĞRULANDI | [sd_notify.xml](https://raw.githubusercontent.com/systemd/systemd/main/man/sd_notify.xml): "This is the keep-alive ping that services need to issue in regular intervals" |
| `WatchdogSec`: Sinyal gelmezse süreç SIGABRT ile sonlandırılır ve `Restart=` devreye girer. Süre sürece `WATCHDOG_USEC` ile iletilir. `NotifyAccess` örtük olarak `main`. Varsayılan 0, yani kapalı. | DOĞRULANDI | [systemd.service.xml](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.service.xml): "terminated with SIGABRT" |
| **İlk sinyal de** başlangıçtan sonraki `WatchdogSec` süresi içinde gelmeli. Önerilen sinyal sıklığı bu sürenin yarısı. | DOĞRULANDI | [sd_watchdog_enabled.xml](https://raw.githubusercontent.com/systemd/systemd/main/man/sd_watchdog_enabled.xml): "within the specified time after startup and after each previous message" |
| systemd protokolün libsystemd olmadan yeniden yazılmasını açıkça onaylıyor. Resmi Python örneği yalnız stdlib `socket` kullanıyor ve MIT-0 lisanslı. | DOĞRULANDI | [notify-selfcontained-example.py](https://raw.githubusercontent.com/systemd/systemd/main/man/notify-selfcontained-example.py): "Implement the systemd notify protocol without external dependencies." |
| `sdnotify` paketi 0.3.2 (2 Ağu 2017): yalnız 2.459 baytlık sdist, MIT (sınıflandırıcı ve LICENSE.txt; PyPI'deki lisans alanı boş), 59 satır. Kartta "~30 satır" yazıyordu. | DOĞRULANDI (küçük düzeltmeyle) | [PyPI sdnotify](https://pypi.org/pypi/sdnotify/json) |
| Docker `HEALTHCHECK` komutu container içinde çalışır. Sonucu yalnız sağlık durumunu ve `health_status` olayını etkiler. Varsayılanlar: 30s / 30s / 0s / 5s / 3 deneme. Zaman aşımında komut SIGKILL ile durdurulur. | DOĞRULANDI | [BuildKit reference.md](https://raw.githubusercontent.com/moby/buildkit/master/frontend/dockerfile/docs/reference.md): "a `health_status` event is generated" |
| Docker Engine ve Compose "unhealthy" durumdaki container'ı yeniden başlatmıyor. Bu özellik 2016'dan beri açık bir istek (#28400); `--exit-on-unhealthy` hiç birleştirilmedi. Swarm ise görevi değiştiriyor. | DOĞRULANDI | [docker-autoheal README](https://raw.githubusercontent.com/willfarrell/docker-autoheal/main/README.md): "didn't make the cut" |
| İddia: "Yeniden başlatma politikası ancak container 10 saniye ayakta kaldıktan sonra devreye girer; açılışta çöken container döngüye girmez." **Doğrusu:** moby kodu her çıkışta yeniden başlatıyor. Bekleme 100 ms'den başlayıp her seferinde ikiye katlanıyor, en fazla 1 dakikaya çıkıyor. 10 saniye yalnız bu sayacı sıfırlıyor. Yani açılışta çöken container **döngüye girer.** | ÇÜRÜTÜLDÜ | [restartmanager.go](https://raw.githubusercontent.com/moby/moby/master/daemon/internal/restartmanager/restartmanager.go): `defaultTimeout = 100 * time.Millisecond` |
| `restart: unless-stopped` çıkış koduna bakmadan container'ı yeniden başlatıyor. | DOĞRULANDI | [start-containers-automatically.md](https://raw.githubusercontent.com/docker/docs/main/content/manuals/engine/containers/start-containers-automatically.md) |
| Proje SSE'yi ek paket olmadan, `StreamingResponse` ile yapıyor. `sse-starlette` kurulu değil. `docs/05:22`'deki "`sse-starlette`" ifadesi kodla çelişiyor. | DOĞRULANDI (yerel) | [olaylar_web.py](../backend/app/web/olaylar_web.py): `media_type="text/event-stream"` |
| SSE tek yönlü, MIME tipi `text/event-stream`, `:` ile başlayan satır yorum. EventSource bağlantı kopunca otomatik yeniden bağlanıyor. HTTP/1.1'de tarayıcı ve alan adı başına en fazla 6 bağlantı açılabiliyor. | DOĞRULANDI | [MDN kaynağı](https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/api/server-sent_events/using_server-sent_events/index.md): "per browser + domain" |
| FastAPI 0.135.0 ve sonrasında yerleşik SSE var (`fastapi.sse.EventSourceResponse`). 15 saniyelik ping, `no-cache` ve `X-Accel-Buffering` otomatik ayarlanıyor. DALSAN'da fastapi sabitlenmemiş; .venv'de 0.141.1 kurulu. | DOĞRULANDI | [FastAPI SSE belgesi](https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/server-sent-events.md): "Added in FastAPI 0.135.0." |
| WebSocket için `websockets` ya da `wsproto` paketi gerekiyor. `uvicorn[standard]` extras'ı `websockets>=13.0` getiriyor; .venv'de 17.1 kurulu. | DOĞRULANDI | [uvicorn auto.py](https://raw.githubusercontent.com/Kludex/uvicorn/main/uvicorn/protocols/websockets/auto.py) |
| GOREV §4.11 "REST + WebSocket" istiyor; E7 ve `01-MVP-KAPSAM:94` bunu SSE lehine kapattı. Metrik isteği §4.9'da (§4.10'da değil) ve uç adı `/healthz`; DALSAN'daki uç ise `/saglik`. | DOĞRULANDI (yerel) | [GOREV-TANIMI-V2.md](GOREV-TANIMI-V2.md) §4.9, §4.11, E7 |
| Python 3.12'de `distutils`, `asynchat`, `asyncore` ve `imp` kaldırıldı; venv artık setuptools kurmuyor. `utcnow()` ve sqlite3'ün varsayılan adaptörleri deprecated. Çok iş parçacıklı bir süreçte `os.fork()` DeprecationWarning veriyor. `get_event_loop()` da uyarı veriyor. DALSAN'da bunların hiçbiri kullanılmıyor (grep boş döndü); `zaman.py` metin kullanıyor. | DOĞRULANDI | [3.12 whatsnew](https://raw.githubusercontent.com/python/cpython/3.12/Doc/whatsnew/3.12.rst): "The distutils package has been removed" |
| Sabitlenmiş bağımlılıkların Python 3.12 wheel'leri var. ORT 1.19.2'nin 3.13 ve sonrası için wheel'i ve sdist'i yok. Masaüstü başlatıcı yalnız "≥3.11" alt sınırını koyuyor (`dalsan_launcher.py:209`). | DOĞRULANDI (yerel ve PyPI) | [PyPI ORT 1.19.2](https://pypi.org/pypi/onnxruntime/1.19.2/json) |
| opencv-python'ın PyPI'deki "en son" sürümü 5.0.0.93; sürüm sabitlenmezse OpenCV 5 gelir. supervision 0.25.1 `opencv-python>=4.5.5.64` istiyor. | DOĞRULANDI | [PyPI opencv-python-headless](https://pypi.org/pypi/opencv-python-headless/json) |
| `VideoCapture` API'si bloklayıcı; her kamera için ayrı bir iş parçacığı gerekiyor. OpenCV nesneleri iş parçacığı güvenli değil. | DOĞRULANDI | [opencv #12077](https://github.com/opencv/opencv/issues/12077): "call to VideoCapture::read … will block calling thread" |
| Belgeye göre `grab()` kareyi yakalar, `retrieve()` çözer. Ancak FFmpeg arka ucunda çözme işi `grab()`'de yapılıyor; `retrieve()` yalnız renk dönüşümü yapıyor. | DOĞRULANDI | [videoio.hpp](https://raw.githubusercontent.com/opencv/opencv/4.x/modules/videoio/include/opencv2/videoio.hpp) · [cap_ffmpeg_impl.hpp](https://raw.githubusercontent.com/opencv/opencv/4.x/modules/videoio/src/cap_ffmpeg_impl.hpp) |
| `CAP_PROP_BUFFERSIZE` FFmpeg, GStreamer ve DShow arka uçlarında hiç ele alınmıyor. V4L2'de (1-10 arası, varsayılan 4) ve DC1394'te destekleniyor; MSMF false döndürüyor. | DOĞRULANDI | [cap_v4l.cpp](https://raw.githubusercontent.com/opencv/opencv/4.x/modules/videoio/src/cap_v4l.cpp): `#define DEFAULT_V4L_BUFFERS 4` |
| FFmpeg arka ucunda açma ve okuma zaman aşımı varsayılan olarak 30.000 ms. `CAP_PROP_OPEN_TIMEOUT_MSEC` ve `CAP_PROP_READ_TIMEOUT_MSEC` yalnız açılışta parametre olarak verilebiliyor. `kamera.py:223` bunları vermiyor. | DOĞRULANDI | [cap_ffmpeg_impl.hpp 4.x](https://raw.githubusercontent.com/opencv/opencv/4.x/modules/videoio/src/cap_ffmpeg_impl.hpp): `#define LIBAVFORMAT_INTERRUPT_READ_DEFAULT_TIMEOUT_MS 30000` |
| `/saglik` ucu her zaman 200 döndürüyor ve analiz döngüsünün gerçekten ilerleyip ilerlemediğini ölçmüyor. Compose sağlık kontrolü `curl` kullanıyor; Dockerfile'daki `curl` sırf bunun için kurulmuş. | DOĞRULANDI (yerel) | [rotalar.py](../backend/app/web/rotalar.py):129-142 |
| `docs/06`'daki systemd biriminde `ExecStart=… app.main:uygulama` yazıyor, ama modüldeki sembolün adı `app`. **Birim bugün başlamıyor** (AUDIT R26). | DOĞRULANDI (yerel) | [06-OPERASYON.md](06-OPERASYON.md):83 · `backend/app/main.py:63` `app = uygulamayi_kur()` |
| Paketlenmiş masaüstü uygulamasında uvicorn Tk Kontrol Paneli ile **aynı süreçte** çalışıyor; `os._exit` paneli de kapatır. Geliştirme kipinde alt süreç çıkınca onu yeniden başlatan bir döngü yok. | DOĞRULANDI (yerel) | [dalsan_launcher.py](../masaustu/dalsan_launcher.py):975-979 |
| `kamera.py` her kamera için bir daemon iş parçacığı açıyor ve son kareyi kilit altında tutuyor. 60 saniye kare gelmezse kamera çevrimdışı sayılıyor; yeniden deneme bekleme süresi 1'den 30 saniyeye üstel artıyor. | DOĞRULANDI (yerel) | [kamera.py](../backend/app/analiz/kamera.py) |

### DOĞRULANMADI

- **"`grab()` ile tamponu boşaltmak zaman kazandırmaz":** FFmpeg arka ucu her `grab()`'de kareyi çözüyor; atlanan tek şey renk dönüşümü. Kazanç olup olmadığı ölçülmeli.
- **OpenCV SSS'sinde iş parçacığı güvenliği garantisinin bulunmadığı:** Bu turda yeniden bakılmadı.
- **`OPENCV_FFMPEG_CAPTURE_OPTIONS` değişkeninin `import cv2`'den önce ayarlanması gerektiği:** Kaynağa göre değişken `open()` içinde okunuyor, yani bu sıralama gerekmiyor ama zararsız.

### Projeye öneri (en az parça)

1. **Metrik.** Müşteride Prometheus yoksa `/saglik` JSON'una fps, gecikme ve kuyruk alanları eklenmesi yeter. Prometheus varsa elle yazılmış bir `GET /metrics` ucu açılır: 5-8 gauge ve counter, `Content-Type` başlığı **zorunlu**, etiket olarak kamera adı değil kamera id'si. `prometheus_client` eklenmez. §4.9'daki `/healthz` adı ya aynı fonksiyona takma ad olarak bağlanır ya da E tablosuna sapma olarak yazılır.
2. **Bekçi.** Süpervizör döngüsü her turda bir `time.monotonic()` damgası yazar. Ayrı bir daemon iş parçacığı (stdlib) bu damgayı her 10 saniyede kontrol eder. Takılma şöyle tanımlanır: analiz açık, en az bir kamera kare üretiyor ve damga 90 saniyeden eski. Tepki dağıtım yoluna göre değişir:
   - **Docker ve systemd:** Günlüğe kayıt düşülür ve `os._exit(70)` çağrılır. Süreci yeniden başlatma politikası ya da `Restart=always` kaldırır. Docker'da tekrarlayan çıkışlarda bekleme 100 ms'den 1 dakikaya kadar uzar.
   - **Paketlenmiş masaüstü:** Süreçten **çıkılmaz.** `/saglik` 503 döndürür, panelde uyarı gösterilir ve günlüğe yazılır. Çıkış paneli de öldürür.
3. **systemd.** Önce `ExecStart` düzeltilir (`app.main:app`). Sonra `WatchdogSec=120` eklenir ve yaklaşık 15 satırlık stdlib bir bildirim yardımcısı yazılır (systemd'nin MIT-0 örneği temel alınır). Açılış evresinde (model yükleme) sinyal koşulsuz gönderilir ya da `EXTEND_TIMEOUT_USEC` kullanılır. `sdnotify` paketi eklenmez. `NOTIFY_SOCKET` Docker'a taşınmaz.
4. **Sağlık ucu.** `/saglik`, analiz takılmışsa 503 döndürür. Yeniden başlatma sağlık kontrolüne bağlanmaz. İsteğe bağlı olarak healthcheck `python -c "…urllib.request…"` ile yapılıp imajdan `curl` kaldırılabilir.
5. **OpenCV.** Açılışta `cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000])` kullanılır. `CAP_PROP_BUFFERSIZE` ayarlanmaz. Bir VideoCapture nesnesine yalnız ait olduğu kameranın iş parçacığı dokunur. Bekçi eşiği okuma zaman aşımından uzun tutulur.
6. **WebSocket reddedilir, SSE'de kalınır.** `docs/05:22` "Starlette `StreamingResponse` (ek paket yok)" olarak düzeltilir. `fastapi.sse`'ye geçmek zorunlu değil; geçilirse `fastapi>=0.135` alt sınırı konur. Belgeye şu not düşülür: HTTP/1.1'de aynı tarayıcıda 6'dan fazla izleme sekmesi açılmamalı.
7. **Python 3.12'de kalınır.** ORT 1.19.2 kalacaksa başlatıcıya `<3.13` üst sınırı **zorunlu** olarak eklenir; 1.30.0'a geçilirse bu engel ORT'den kalkar ama diğer paketler test edilmeli. Geliştirme .venv'i 3.12'ye çekilir. Her kamera için ayrı süreç açılmaz (E6; ayrıca 3.12'de çok iş parçacıklı süreçte fork uyarı veriyor). `opencv-python==4.10.0.84` sabiti korunur.

### Açık sorular

- Müşteride `/metrics` ucunu okuyacak bir Prometheus var mı?
- Üretimde hangi dağıtım yolları kullanılacak: Docker, systemd, masaüstü? Masaüstünde süreç çıkarsa onu kim yeniden başlatacak?
- "Takılma" tanımı ve 90 saniyelik eşik kabul ediliyor mu?
- §4.11'deki WebSocket maddesi sözleşmede bağlayıcı mı?
- Docker'sız kurulumda hedef makinede Python 3.12 garanti mi (Ubuntu 22.04'te sistem Python'u 3.10)?

---

## Karar tablosu: kullanılabilir / kullanılamaz

Karar, **lisansa ve ticari fabrika kurulumuna** göre verildi. "Koşullu" satırlar, lisans satırı kaynağında okunup kaydedilmeden kullanılamaz. Bütün satırlar için avukat teyidi gerekir.

### Veri setleri, modeller ve sesler

| Kaynak | Lisans (doğrulama düzeyi) | Karar | Gerekçe |
|---|---|---|---|
| SH17 | CC BY-NC-SA 4.0 ve "yalnız eğitim/araştırma" kaydı (DOĞRULANDI) | **KULLANILAMAZ** | NC ve ShareAlike; model ağırlığı da türev sayılabilir |
| CHV | Lisans yok (DOĞRULANDI) | **KULLANILAMAZ** | "open for free use" bir lisans değil |
| Pictor-PPE ve Roboflow'daki yeniden yüklemeleri | Lisans yok (DOĞRULANDI) | **KULLANILAMAZ** | Yükleyici yeniden lisanslayamaz |
| SFCHD | Lisans yok (DOĞRULANDI) | **KULLANILAMAZ** | Yazılı izin alınırsa en uygun alan verisi olur |
| SHWD | MIT, ama SCUT-HEAD yalnız araştırma (DOĞRULANDI) | **KULLANILAMAZ** | Karışık köken |
| SCUT-HEAD | Yalnız akademik araştırma (DOĞRULANDI) | **KULLANILAMAZ** | Ticari kullanıma kapalı |
| GDUT-HWD | Depo Apache-2.0, veri kapsamı belirsiz (DOĞRULANDI) | **KULLANMA** | Yazılı izin olmadan kullanılmaz |
| Ultralytics Construction-PPE | AGPL-3.0 (DOĞRULANDI) | **KULLANILAMAZ** | ADR-002 |
| SODA | Bilinmiyor | **KULLANMA** | Erişim koşulu belirsiz |
| Roboflow Construction Site Safety (`roboflow-universe-projects`) | CC BY 4.0 (DOĞRULANMADI, arama özeti) | **KOŞULLU** | Sürüm sabitlenmeli, lisans satırı kaydedilmeli; KKD için ilk aday |
| Roboflow Safety Vests (`roboflow-universe-projects`) | Lisans DOĞRULANMADI | **KOŞULLU** | Özette CC BY görünmüyor |
| Roboflow HardHat & SafetyVest (`ppe-kit-detection`) | CC BY 4.0 (arama özeti) | **KOŞULLU** | Kökeni bilinmiyor; NC setlerin birleşimi olabilir |
| Hard Hat Universe (`ppe-pnqgr`) | Lisans hiçbir yerde görülmedi | **KOŞULLU / şüpheli** | - |
| Hard Hat Workers (`joseph-nelson`) | Public Domain (arama özeti) | **KOŞULLU** | Yalnız baret; kökeni doğrulanmadı |
| Kaggle `andrewmvd` Safety Helmet Detection | CC0 (arama özeti) | **KOŞULLU** | Yalnız baret |
| SHEL5K | CC BY 4.0 (arama özeti); görüntüler andrewmvd'den | **KOŞULLU** | Lisansı SHD'nin lisansına bağlı |
| Mendeley `zkzghjvpn2` (v6) | Lisans DOĞRULANMADI | **KOŞULLU** | v2 bilgileri bayat |
| RF100 `construction-safety-gsnvb` | RF100'ün toplu CC BY iddiası ÇÜRÜTÜLDÜ | **KOŞULLU** | Orijinal yüklemenin lisansına bakılmalı |
| **LOCO** (TUM) | **CC0 1.0 (DOĞRULANDI)** | **KULLANILABİLİR** | forklift, pallet truck, pallet; `person` yok |
| LVIS (forklift, id 470) | Anotasyonlar CC BY 4.0 (DOĞRULANDI); görüntüler COCO/Flickr | **KOŞULLU** | Görüntü telifi için hukuk görüşü gerekir |
| COCO (ön eğitim, alt küme) | Anotasyonlar CC BY 4.0; görüntülerin Flickr şartlarına bağlılığı DOĞRULANMADI | **KOŞULLU** | Mevcut ağırlıklar da COCO'dan; hukuk görüşü alınmalı |
| Objects365 | Anotasyonlar CC BY 4.0; görüntüler Flickr ve yeniden dağıtılamaz (DOĞRULANDI) | **MVP'DE KULLANMA** | Forklift yok, 712 GB |
| Open Images V7 | CC BY 4.0 / görüntüler "CC BY 2.0 listed", garanti yok (DOĞRULANDI) | **MVP'DE KULLANMA** | Forklift kutusu yok |
| Roboflow forklift setleri (csv2tfrecord, CONTIL, HITSZ, Baxter) | CC BY 4.0 (arama özeti) | **KOŞULLU** | Lisans ve köken tarayıcıdan teyit edilmeli |
| Roboflow `Phantom/forklift-1` | CC BY 4.0 (arama özeti) | **LOCO'yu kullan** | Büyük olasılıkla LOCO türevi |
| Traore/forklift (421) ve kopyaları, HF `keremberke/forklift-object-detection` | CC BY 4.0 yazıyor, görüntüler images.cv'den | **KULLANILAMAZ** | Kaynak görüntülerin ticari lisansı yok |
| SelimSavas forklift (3.000) | Lisans yok, ImageNet kaynaklı (DOĞRULANDI) | **KULLANILAMAZ** | - |
| YOLOX kodu ve resmi ağırlıkları | Apache-2.0 (DOĞRULANDI) | **KULLANILABİLİR** | Mevcut seçim |
| YuNet `2023mar` | MIT, Shiqi Yu (DOĞRULANDI) | **KULLANILABİLİR** (Faz 2) | `2026may` OpenCV 5 ister |
| Piper `tr_TR-dfki-medium` | Veri CC BY-NC-SA ve lessac tabanı (DOĞRULANDI) | **KULLANILAMAZ** | İki ayrı ticari engel |
| Piper `tr_TR-fahrettin` / `tr_TR-fettah` | Kaldırılmış, model kartı yok | **KULLANILAMAZ** | - |
| Coqui XTTS-v2 | CPML (DOĞRULANDI) | **KULLANILAMAZ** | Ticari lisans satın alınamıyor |
| Meta MMS-TTS (`mms-tts-tur`) | CC-BY-NC 4.0 (DOĞRULANDI) | **KULLANILAMAZ** | Ayrıca torch ve transformers getirir |
| macOS "Yelda" (`say`) | SLA: yalnız kişisel ve ticari olmayan kullanım (DOĞRULANMADI, orta güven) | **Müşteriye giden varlık olarak KULLANMA** | Yalnız geliştirici denemesi için |
| Windows "Tolga" | Koşullar DOĞRULANMADI | **KULLANMA** | Ayrıca OneCore/SAPI5 sorunu var |
| İnsan kaydıyla hazırlanmış WAV | Kaydı yapanla yapılan sözleşmeye bağlı | **ÖNERİLEN** | Sıfır bağımlılık |

### Kütüphaneler ve araçlar

| Kütüphane / araç | Lisans (doğrulama) | Karar | Not |
|---|---|---|---|
| `onnxruntime` (CPU) | MIT (PyPI, DOĞRULANDI) | **KULLANILABİLİR** | Sabitin 1.30.0'a yükseltilmesi öneriliyor (§5) |
| `onnxruntime-gpu` | MIT (PyPI, DOĞRULANDI) | **KULLANILABİLİR** | Yalnız GPU sunucusunda ve CPU paketinin **yerine** |
| `onnxruntime-openvino` | MIT (DOĞRULANDI) | Lisans uygun; **MVP'de eklenmez** | Aynı dizine kuruluyor, 6 alt sürüm geride |
| TensorRT | NVIDIA lisansı (bu belgede incelenmedi) | **MVP dışında** | - |
| `opencv-python` 4.10.0.84 | Apache 2.0; gömülü FFmpeg LGPLv2.1, Qt5 LGPLv3 (DOĞRULANDI) | **KULLANILABİLİR** | LGPL bildirimi `LICENSE-THIRD-PARTY`'de yer almalı |
| `supervision` 0.25.1 | MIT (DOĞRULANDI) | **KULLANILABİLİR** | Sabit kalmalı |
| `trackers` | Apache-2.0 (DOĞRULANDI) | Lisans uygun; **MVP'de eklenmez** | supervision 0.31 geçişinde gerekecek |
| Ultralytics YOLOv8/YOLO11 | AGPL-3.0 (depo LICENSE, DOĞRULANDI) | **KULLANILAMAZ** | ADR-002 |
| `prometheus_client` | Apache-2.0 AND BSD-2-Clause (DOĞRULANDI) | Lisans uygun; **eklenmez** | Metin elle üretilir |
| `sdnotify` | MIT (DOĞRULANDI) | **Eklenmez** | stdlib `socket` yeterli; 2017'den beri güncellenmemiş |
| `sse-starlette` | - | **Eklenmez** | Proje `StreamingResponse` kullanıyor |
| `websockets` | BSD-3-Clause (PyPI) | Zaten kurulu (uvicorn[standard]); **WebSocket ucu açılmaz** | E7 |
| `fastapi` / `uvicorn` | MIT / BSD-3-Clause (PyPI) | **KULLANILABİLİR** (mevcut) | `fastapi.sse` için ≥0.135 gerekir |
| `dbus-fast` | MIT (DOĞRULANDI) | Yalnız subprocess yetmezse | Aktif bakımlı tek aday |
| `dbus-next` | MIT | **KULLANMA** | 2021'den beri güncellenmemiş |
| `pydbus` | LGPLv2+ | **KULLANMA** | 2016'dan beri güncellenmemiş, PyGObject gerektiriyor |
| `dbus-python` | MIT | **KULLANMA** | "Inactive"; senkron API, iş parçacığı sorunları |
| `bleak` | MIT | **KULLANMA** (yanlış araç) | Yalnız BLE; A2DP yapamaz |
| BlueALSA | MIT (DOĞRULANDI) | Yalnız PipeWire ve PulseAudio yoksa | Ek bir servis |
| `piper-tts` | GPL-3.0-or-later (DOĞRULANDI) | **MVP'de yok**; ileride yalnız ayrı süreçte | Asla `import` edilmez |
| espeak-ng | GPL-3.0 (DOĞRULANDI) | **MVP'de yok**; ileride yalnız ayrı süreçte | Robotik ses |
| `winrt-Windows.Devices.Enumeration` | MIT (DOĞRULANDI) | **MVP'de yok** | Diyalog bastırılamıyor |
| `blueutil` (macOS) | MIT (DOĞRULANDI) | **MVP'de yok** | Özel (private) API kullanıyor |
| `roboflow` Python SDK | (incelenmedi) | **Eklenmez** | Web'den zip indirmek yeterli |
| YOLOX eğitim bağımlılıkları (torch, onnx-simplifier, pycocotools) | (incelenmedi) | Yalnız ayrı eğitim venv'inde | Ürüne girmez |

---

## Prompt'taki hatalar

Bu bölüm, `GOREV-TANIMI-V2.md`'nin yanlış ya da eksik olduğu noktaları listeler. Önce §4.6-§4.7, ardından kartlarda ortaya çıkan diğer bölümler. EK A'da zaten bulunan maddeler (E1, E2, E3, E5, E7) belirtildi; **yeni** maddeler EK A'ya eklenmek üzere önerilmiştir. Bu belge `GOREV-TANIMI-V2.md` dosyasını değiştirmez.

### §4.6 Uyarı kanalları ve Bluetooth hoparlör

| # | Prompttaki ifade | Doğrusu / eksik olan | Kaynak (bu belgede) |
|---|---|---|---|
| P1 | "dinamik metin için çevrimdışı TTS (**piper Türkçe ses varsa**…)" | Teknik olarak bir Türkçe ses var, ama ticari olarak kullanılamaz. Bugünkü tek ses `tr_TR-dfki-medium`: verisi CC BY-NC-SA ve lessac tabanlı. Piper projesi de "yalnız kişisel kullanım ve araştırma" diyor. Ayrıca fahrettin ve fettah sesleri kaldırılmış. (E3'ü güçlendirir.) | §3 |
| P2 | piper ve espeak-ng birer "kütüphane" gibi anılıyor | `piper-tts` artık **GPL-3.0-or-later** (MIT değil), espeak-ng de GPL-3.0. İkisi de yalnız **ayrı süreç** olarak çalıştırılabilir; `import` edilemez. DALSAN müşteriye **kurulduğu** için GPL açısından "conveying" var. | §3 |
| P3 | Dinamik metin ihtiyacı sunucu TTS'i gerektiriyor gibi yazılmış | DALSAN dinamik metni zaten tarayıcının `speechSynthesis` API'siyle (`uyari.js`) ve HTTP anons cihazının TTS'iyle karşılıyor. Prompt bu iki yolu hiç anmıyor. | §3 |
| P4 | "Linux'ta BlueZ üzerinden D-Bus (`org.bluez`), A2DP sink profili" | Eksik. BlueZ 5 **ses taşımaz.** A2DP için PipeWire ya da PulseAudio (veya BlueALSA) şart. D-Bus yalnız bağlantıyı yönetir. Python'da `bleak` A2DP yapamaz (yalnız BLE). | §4 |
| P5 | "Arayüzde: tara → eşleştir → güven → bağlan" | E2'ye ek teknik engeller var. `bluetoothctl` etkileşimsiz modda `-a` bayrağını yok sayar. PIN isteyen hoparlör etkileşimsiz eşleşmez. Taramadan sonraki 30 saniye içinde eşleşme yapılmazsa cihaz silinir. `-t` ile çıkış kodu hep 0 olur. `connect … a2dp-sink` biçimi yalnız BlueZ 5.82 ve sonrasında var. | §4 |
| P6 | "Windows hedefleniyorsa … eşleştirilmiş cihaz" | Windows'ta programatik eşleştirmede sistem diyaloğu **her zaman** gösteriliyor, yani tam otomatik eşleştirme mümkün değil. | §4 |
| P7 | "Otomatik yeniden bağlanma (üstel geri çekilme, üst sınır 60 s)" | BlueZ'in kendi politikası yalnız bağlantı kaybında devreye giriyor (7 deneme, 1-64 s); hoparlörün kapatılıp açılması kapsam dışı. Gelen bağlantının kabul edilmesi için `trust` şart. Bu yüzden bir uygulama bekçisi gerekir. Prompt bu ayrımı yapmıyor. | §4 |
| P8 | "30 s kopuksa `local_audio`'ya düş" | Sink adı ses sunucusuna göre değişiyor (`bluez_sink.*` / `bluez_output.*`); sabit bir ad yazılamaz. PulseAudio'da `switch-on-connect` davranışı dağıtıma göre farklı. Ekransız sunucuda WirePlumber, logind oturumu aktif değilse Bluetooth sink'i hiç oluşturmayabiliyor. | §4 |
| P9 | "A2DP tipik olarak 100-250 ms" | Bu aralık yayımlanmış bir ölçümle doğrulanamadı; yalnız tekil ölçümler var (SBC için 150,6 ms). Sabit bir sayı yazılmamalı, ölçülmeli. | §4 |
| P10 | Docker imajında Bluetooth (§4.9 ile birlikte) | Eksik. Konteynere host'un D-Bus soketi ve ses soketi bağlanır, konteyner aynı UID ile çalışır. `--privileged`, `NET_ADMIN` ve `NET_RAW` gereksizdir. HCI soketi gerekiyorsa `--net=host` şart. İmaja ayrıca işletim sistemi paketleri girer. | §4 |
| P11 | "MAC adresi `config/alerts.yaml`" | E5: `.env` ya da SQLite kullanılmalı. | EK A |

### §4.7 Veri ve model

| # | Prompttaki ifade | Doğrusu / eksik olan | Kaynak (bu belgede) |
|---|---|---|---|
| P12 | "KKD için **SH17**" | CC BY-NC-SA 4.0 ve yazarın "yalnız eğitim/araştırma" kaydı var; elenir (E1). Ek bilgi: amaç sınırlaması Kaggle'da değil, yazarın kendi README'sinde yazılı. | §1 |
| P13 | "KKD için … **CHV**" | **Lisans yok.** "open for free use" bir lisans değil; elenir. E1'de yok, **yeni madde.** | §1 |
| P14 | "KKD için … **Pictor-PPE**" | **Lisans yok**; elenir. Roboflow'daki "CC BY 4.0" yeniden yüklemesi geçerli bir lisans değil. E1'de yok, **yeni madde.** | §1 |
| P15 | "forklift için Roboflow Universe setleri" | Roboflow'daki lisans satırı yükleyicinin beyanı. En az bir set ticari kullanıma kapalı images.cv'den geliyor, NC setlerin CC BY olarak yeniden yüklendiğine dair şikâyetler de var. Bu ortamdan hiçbir set doğrulanamadı. **Eksik olan:** LOCO (CC0; forklift, pallet truck, pallet), lisansı en temiz kaynak ama listede yok. | §2 |
| P16 | "COCO … + özel forklift, **loader**, pallet_jack" | `loader` için hiçbir açık kaynakta sınıf yok (LVIS'te bulldozer "rare", Objects365'te genel "Machinery Vehicle"). `pallet_jack` LOCO'da var. LOCO'da ise `person` sınıfı yok. | §2 |
| P17 | "Aday açık veri setleri (KULLANMADAN ÖNCE lisans … doğrula)" | Talimat doğru, ama aday listesinin kendisi yanlış: üç KKD adayının üçü de elendi. Bu oturumda KKD için lisansı birincil kaynaktan doğrulanmış ticari-uygun bir set bulunamadı. Ayrıca "Public Domain" ya da CC0 etiketi, görüntüdeki kişilerin mahremiyet haklarını kapsamaz. | §1 |
| P18 | "Model adayları: … YOLOX (Apache-2.0)" | Lisans doğru. Eksik: YOLOX'un PyPI sürümü 2022'den kalma, son commit Haziran 2025. Export betiği PyTorch 2.5'te kaldırılan `torch.onnx._export`'u kullanıyor; eğitim ortamında PyTorch 2.4 ya da öncesi sabitlenmeli veya betik yamalanmalı. Ultralytics'in hazır **veri setleri** de AGPL lisanslı (Construction-PPE). | §2, §5 |
| P19 | "Dışa aktarım: ONNX → TensorRT / OpenVINO" | Eksik ve kısmen yanlış. (a) `onnxruntime-gpu` ayrı bir paket; CPU paketiyle aynı ortama kurulursa CUDA sessizce kaybolur. (b) 1.27 ve sonrası CUDA 13 istiyor; 1.30'un TensorRT EP'si libnvinfer 10 ve CUDA 13 kütüphanelerine bağlı. (c) Jetson'da PyPI wheel'i çalışmıyor, JetPack'e özel wheel gerekiyor. (d) OpenVINO ayrı bir paket (`onnxruntime-openvino`), 6 alt sürüm geride ve aynı dizine kuruluyor; ölçülen kazanç ~%10-15, YOLOv5n'de daha yavaş olduğu da raporlanmış. (e) YOLOX README, OpenVINO için opset 10 öneriyor, resmi ONNX dosyaları ise opset 11. | §5 |
| P20 | "uç cihazda INT8 kalibrasyonlu" | INT8 kazancı ancak VNNI ya da dot-product komutları olan donanımda görülüyor. VNNI'siz AVX2/AVX512'de U8S8 doygunluk riski var. Kuantizasyon `onnx` paketini gerektiriyor; bu iş yalnız geliştirici makinesinde yapılmalı. Prompt donanım koşulunu yazmıyor. | §5 |
| P21 | "Model kayıt defteri … sha256" | Doğru. Ancak bugünkü `models/indir.sh` hash doğrulaması yapmıyor. CVE-2026-14647 (model yükleme yolu) bağlamında bu eksiklik önemli. | §5 |
| P22 | Prompt ORT sürümünden hiç söz etmiyor | 1.19.2'nin gömülü `onnx` 1.16.1'i CVE-2026-14647 kapsamında. Python 3.13 ve sonrası için wheel'i yok. Bu makinede 1.30.0 yaklaşık %25 daha hızlı çıktı. Sürüm yükseltmesi Faz 1'de ele alınmalı. | §5 |

### Diğer bölümler (kartlarda bulunanlar)

| # | Bölüm ve ifade | Doğrusu / eksik olan |
|---|---|---|
| P23 | §4.4 "ByteTrack ya da BoT-SORT" | `sv.ByteTrack` 0.28'de deprecated, 0.31'de kaldırılıyor; 0.25.1'de kalınmalı. DALSAN'daki kalıcılık ayarı (`lost_track_buffer`) varsayılan olarak 1 saniye; `docs/03`'teki `track_buffer` adı yanlış. |
| P24 | §4.2 ayak noktası | Kural doğru. `sv.Position.BOTTOM_CENTER` ile aynı formül; DALSAN bunu `rules/` katmanında stdlib ile zaten uyguluyor. PolygonZone gerekmiyor, zaten `rules/` içinde kullanılamaz (cv2 yasağı). |
| P25 | §4.9 "`/healthz`, Prometheus metrikleri" | DALSAN'daki uç `/saglik`. Prometheus 3 `Content-Type` başlığını zorunlu tutuyor. `prometheus_client` gerekmiyor (E7 ile uyumlu). |
| P26 | §4.9 "bekçi; çökünce otomatik yeniden başlatma" | Docker "unhealthy" container'ı yeniden başlatmıyor; açılışta çöken container ise döngüye giriyor. `docs/06`'daki systemd birimi bugün başlamıyor (`app.main:uygulama`). Paketlenmiş masaüstünde süreçten çıkmak Kontrol Paneli'ni de kapatır. Bekçinin tepkisi dağıtım yoluna göre tasarlanmalı. |
| P27 | §4.9 "RTSP kopunca üstel geri çekilme" | Bu zaten var. Eksik olan: FFmpeg `read()` varsayılan olarak 30 saniye bloklayabiliyor; `CAP_PROP_READ_TIMEOUT_MSEC` yalnız açılışta verilebiliyor. `CAP_PROP_BUFFERSIZE` FFmpeg'de işlevsiz. |
| P28 | §4.9 "saklama süresi … varsayılan 30 gün" | KVKK'da sabit bir gün sayısı yok. Kurum "mümkün olan en kısa süre ve otomatik imha" diyor (8770). 30 gün müşteri ve avukat tarafından gerekçelendirilmeli; periyodik imha en geç 6 ayda bir yapılmalı. |
| P29 | §4.9 "kamera başına ayrı işçi süreci" | E6. Ek olarak Python 3.12'de çok iş parçacıklı süreçte `fork` DeprecationWarning veriyor; OpenCV ve ONNX ile fork güvensiz. |
| P30 | §4.10 "Yüz tanıma … YAPILMAZ" | Doğru. Dayanağı m.4 ölçülülük ilkesi ve 2022/797 olarak yazılmalı. 2026/921 yalnız mesai takibini kapsıyor (27.08.2026 duyurusu). "Açık rıza gerekir" ifadesi 2024 öncesinin hukuku. |
| P31 | §4.10 "saha tabelası `docs/KVKK.md`" | Tebliğ'de tabeladan hiç söz edilmiyor. Levha ile tam metin uygulaması Kurul kararlarından (2023/2007) ve Rehber'den geliyor. Açık rıza kutucuğu konmamalı (2026/347, RG 24.03.2026/33203). Eksik: m.11/1-g (otomatik analize itiraz hakkı) ve 6331 m.18 (yeni teknoloji için çalışan görüşü). |
| P32 | §4.10 "isteğe bağlı yüz bulanıklaştırma" | YuNet 10 pikselin altındaki yüzleri bulamıyor. Uzak kamerada kutunun üst kısmını bulanıklaştırmak daha güvenli. YuNet'in lisansı MIT (Apache değil); OpenCV 4.x için `2023mar` dosyası kullanılmalı. |
| P33 | §4.11 "REST + WebSocket" | E7. Ek bilgi: FastAPI 0.135 ve sonrasında yerleşik SSE var. WebSocket çift yönlü olmaktan başka bir şey kazandırmıyor, projede de çift yönlü bir ihtiyaç yok. |
| P34 | §4.8 "≤ 500 ms kare → ses" | E13'e ek: A2DP gecikmesi bu bütçenin önemli bir kısmını yiyebilir ama yayımlanmış bir aralık doğrulanamadı; sahada ölçülmeli. |

---

## Depo içi tutarsızlıklar (dış doğrulama sırasında bulunan)

Bu belge yalnız kendisini değiştirebildiği için aşağıdaki düzeltmeler **yapılmadı.** Faz 1'e girdi olarak listeleniyor.

| Dosya:satır | Sorun | Doğrusu |
|---|---|---|
| `docs/03-KURAL-MOTORU.md:171` | "ByteTrack `track_buffer`" | `lost_track_buffer` (0.23'te yeniden adlandırıldı); saniye × 30 |
| `backend/app/analiz/takip.py:30` | Yorum "`track_buffer`'ı yüksek tut" diyor, kod parametreyi vermiyor | Yorum düzeltilmeli ya da parametre `.env`'den verilmeli |
| `docs/05-TEKNOLOJI-KARARLARI.md:19` | "ByteTrack, PolygonZone" | "ByteTrack (yalnız)" |
| `docs/05-TEKNOLOJI-KARARLARI.md:20` | "OpenCV homografi", `rules/calibration.py` | "saf numpy homografi", `rules/kalibrasyon.py` |
| `docs/05-TEKNOLOJI-KARARLARI.md:22` | "SSE (`sse-starlette`)" | "Starlette `StreamingResponse` (ek paket yok)" |
| `docs/06-OPERASYON.md:83` | `ExecStart=… app.main:uygulama` | `app.main:app`. Birim bugün başlamıyor. |
| `Dockerfile:8-11` | apt `ffmpeg` "RTSP çözmek için" kuruluyor | cv2 kendi FFmpeg'ini kullanıyor; RTSP provasından sonra kaldırma adayı |
| `Dockerfile:9-12` | `curl` yalnız healthcheck için kurulmuş | İsteğe bağlı: `python -c` kullanılabilir |
| `models/indir.sh` | SHA-256 doğrulaması yok | Sabit hash ile `sha256sum -c` |
| `backend/app/analiz/tespit.py:102-114` | Her oturum hatası "dosyası bozuk" diye raporlanıyor | EP hatası ile dosya hatası ayrıştırılmalı |
| `masaustu/dalsan_launcher.py:209` | Python için yalnız alt sınır (≥3.11) var | ORT 1.19.2 kalacaksa `<3.13` üst sınırı |
| `.venv` | Python 3.11.15 | Hedef 3.12 (Dockerfile ve CLAUDE.md) |
| `backend/requirements.txt` | `numpy` ve `fastapi` sabitlenmemiş | En azından alt sınır konmalı (`fastapi.sse` kullanılacaksa ≥0.135) |
| `docs/14-ANONS-SISTEMI-BAGLAMA.md` §2.3 madde 2 | "Bilgisayarın kendi seslendirmesi" | Ticari bağlamda lisans riski notu eklenmeli (macOS SLA, Windows koşulları doğrulanmadı) |

---

*Bu belge ham veridir ve karar vermez. Faz 1 tasarımı (`docs/17-V2-TASARIM.md`) kararlarını bu belgenin satırlarına atıf yaparak verir. Tarih 2026-09-22; sürümler ve lisans satırları değişebilir. Hukuki maddeler için avukat teyidi gerekir.*
