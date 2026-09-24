# Forklift modelini fabrikanın kendi görüntüsüyle eğitmek

Fotoğraf çekmeniz ya da kod yazmanız gerekmez. Program kareleri kameralardan
kendisi toplar; sizin işiniz etiketlemek, eğitimi tek dosyayla başlatmak ve
çıkan modeli kurmaktır.

Fabrika kareleri çalışanları da gösterebilir: kişisel veridir (KVKK). Kareler
yalnız programın bilgisayarında ve eğitimi yaptığınız bilgisayarda durur;
internete, paylaşılan bir klasöre ya da GitHub'a konmaz.

## 1. Kareleri toplayın ve etiketleyin (programda, Forklift sayfası)

1. "Kare toplamayı aç". Açmadan önce çalışanlara aydınlatma yapılmış ve bu
   amacın hukuki dayanağı (Rev.02 ya da ek protokol) olmalıdır; sayfa bunu
   onay kutusuyla sorar.
2. Bir iki hafta bekleyin. Program forklift ya da araç görünen kareyi kamera
   başına saatte en çok 12 kez, boş kareyi daha seyrek saklar.
3. "Etiketlemeye başla". Her karede kutuya tıklayıp Forklift, Transpalet ya da
   Değil seçin; önerilmeyen forkliftin etrafına fareyle kutu çizin; karede
   forklift yoksa "Forklift yok". Hedef: en az iki ayrı günden birkaç yüz kare.
   Son günler (yaklaşık dörtte biri) test içindir: test günlerinde en az 50
   forklift kutusu ve birkaç boş kare ("Forklift yok") olsun, yoksa ölçüm
   güvenilir olmaz. Sayfa eksik olanı uyarı olarak yazar.
4. "Eğitim verisini indir (.zip)".

## 2. Eğitin (kapalı bir Windows bilgisayarda)

Gerekenler: Windows 10 ya da 11, Python 3.12 (python.org), en az 8 GB bellek,
6 GB boş disk ve internet (yalnız indirmeler için: eğitim paketleri, açık veri
seti LOCO ve ölçüm kaynakları; fabrika kareleri hiçbir yere gitmez).

1. Programın kaynak klasörünü GitHub'dan ZIP olarak indirip açın.
2. `egitim\forklift\Egit-Windows.bat` dosyasının üstüne indirdiğiniz zip'i
   sürükleyip bırakın.
3. Bekleyin. İlk seferde paketler (yaklaşık 1 GB) ve LOCO (yaklaşık 770 MB)
   iner. Önce birkaç dakikalık bir ön deneme ortamı sınar; sonra asıl eğitim
   başlar ve bilgisayarın hızına göre birkaç saatten bir güne kadar sürebilir.
   Pencere kapanır ya da bilgisayar yeniden başlarsa aynı zip'i yeniden
   bırakın: biten adımlar atlanır, eğitim kaldığı yerden sürer.
4. Sonuç `C:\NextGen-Forklift\SONUC.txt` dosyasındadır. "GEÇTİ" yazıyorsa
   kurulacak model `C:\NextGen-Forklift\KURULACAK\` klasöründedir. "KALDI"
   yazıyorsa hangi ölçümün kaldığı ve ne yapılacağı da yazar (çoğu zaman: daha
   çok ve daha çeşitli kare etiketlemek).

Eğitim fabrikanın izleme bilgisayarında da çalışabilir: düşük öncelikle ve
çekirdeklerin yarısıyla koşar. Yine de canlı izleme yavaşlayabilir; geceleri
çalıştırmak ya da ayrı bir bilgisayar kullanmak daha iyidir.

## 3. Modeli kurun (programda, Forklift sayfası)

"4. Modeli kur" bölümünde `KURULACAK` klasöründeki iki dosyayı seçin (model
`.onnx` ve ölçümü `.olcum.json`) ve "Denetle ve kur"a basın. Program kurmadan
önce denetler: ölçüm bu modele mi ait, ölçüm kapılarının hepsinden geçmiş mi,
model programın kendi tespit motoruyla açılıyor ve forklifti tanıyor mu.

Kurulan model Ayarlar'daki "Tanıma modeli" listesine gelir; siz seçip
kaydetmedikçe çalışan model değişmez. Seçtikten sonra programı yeniden
başlatın. Seçilen model bir gün açılamazsa (dosya silinmiş ya da bozulmuş)
program hazır modelle çalışmayı sürdürür ve bunu ekranda ve Olaylar'da söyler.

Forkliftli modele geçince kurulum listesine bakın: yalnız "Tır/Araç" seçili
araç kuralları forklifti artık görmez, "Forklift"i de işaretlemek gerekir.

## Teknik ayrıntı

- Komut: `python egitim/forklift/yerel.py --saha PAKET.zip --calisma C:\NextGen-Forklift`
  (seçenekler: `--boy tiny|s`, `--kip`, `--devir`, `--saha-tekrar`,
  `--is-parcacigi`, `--loco-veri`, `--duman`; `python egitim/forklift/yerel.py -h`).
- `--duman` yalnız kurulumu birkaç dakikada sınar; onun modeli kurulmaz.
- Linux'ta: `python3.12 -m venv ortam`, sonra
  `ortam/bin/python -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu`,
  `ortam/bin/python -m pip install -r egitim/forklift/gereksinimler-yerel.txt`
  ve yukarıdaki komut.
- Adımlar: veri.py (`saha_paketini_ac`, `hazirla`, `birlestir`), egit.py,
  model.py (`disa-aktar`, `denetle`), degerlendir.py. Kapılar
  `egitim/forklift/esikler.json`'dur; burada değiştirilmez.
- Çalışma klasörünün yolunda Türkçe karakter olmamalı: görüntü kitaplığı
  (OpenCV) bu yolları Windows'ta açamaz; betik bunu en başta söyler.
