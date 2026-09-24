# DALSAN İSG - fabrika sunucusu için tek container (CLAUDE.md §4).
# Geliştirmede Docker KULLANILMAZ; bu dosya yalnızca fabrika kurulumu içindir.
FROM python:3.12-slim

# OpenCV'nin çalışması için gereken sistem kütüphaneleri:
#  libgl1, libglib2.0-0 → görüntü işleme
#  libsm6, libxext6      → bazı OpenCV yapılarının bağımlılığı
#  ffmpeg                → RTSP akışının çözülmesi
# curl: sağlık kontrolü (healthcheck) için
# pulseaudio-utils: paplay ve pactl. "Ses çıkışı" uyarı kanalı (kablolu amfi ya
#   da Bluetooth hoparlör) container'dan host'un ses sunucusuna çalar
#   (docker-compose.ses.yml; docs/17 §7.6 yol A, docs/14 §2.4). Ses sunucusu
#   imajda YOKTUR, yalnız istemci araçları. Bluetooth yeniden bağlanma bekçisi
#   yazılmadığı için bluez istemcisi eklenmez (docs/17 §7.5-3, S9).
#   Paket adı bu depoda imaj derlenerek denenmedi (DOĞRULANMADI).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 ffmpeg curl pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /uygulama

# Önce yalnızca bağımlılıklar: kod değişince bu katman yeniden kurulmaz
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
# Proje belgeleri uygulamanın içinde gösterilir (backend/app/web/belge_rotalari.py)
COPY docs/ docs/
COPY models/ models/
# Model dosyası olmadan container sessizce "tespit yapmayan" bir sisteme
# dönüşürdü. Derleme burada, ANLAŞILIR bir mesajla durur.
RUN test -s models/yolox_tiny.onnx || ( \
      echo "" && \
      echo "HATA: models/yolox_tiny.onnx bulunamadi." && \
      echo "Cozum: imaji derlemeden ONCE su komutu calistirin:" && \
      echo "        bash models/indir.sh" && \
      echo "" && exit 1 )
# Bozuk ya da değiştirilmiş bir model de imaja girmesin (docs/17 §10.5 R17):
# klasördeki her resmi model, models/SHA256SUMS'taki özetle karşılaştırılır.
RUN cd models && sha256sum -c --ignore-missing SHA256SUMS || ( \
      echo "" && \
      echo "HATA: models/ klasorundeki model dosyasi dogrulanamadi (bozuk ya da farkli surum)." && \
      echo "Cozum: dosyayi silip imaji derlemeden ONCE su komutu calistirin:" && \
      echo "        bash models/indir.sh" && \
      echo "" && exit 1 )


# veri/ ve ayar/ container DIŞINDAN bağlanır (docker-compose.yml'e bakın):
# böylece container silinse de veritabanı, olay fotoğrafları ve ayarlar kalır.
#
# Ayar dosyası bir DİZİNLE bağlanır (./ayar → /uygulama/ayar). Tek dosya
# bağlandığında Ayarlar sayfasının kaydı (geçici dosya + tek adımda yerine
# koyma) orada çalışmıyordu (docs/17 §10.5 R27). Uygulama .env'i kökte arar;
# kökteki .env o dizindeki dosyaya işaret eden bir bağdır.
RUN ln -s ayar/.env /uygulama/.env
# Kapsayıcı işareti (app/kaynaklar.py → kapsayicida_mi): şifresiz açılış
# reddedilir (R13) ve eksik ayar dosyası için Docker'a özgü tarif verilir.
ENV DALSAN_KAPSAYICI=1
WORKDIR /uygulama/backend

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# Kontrol Paneli'nin kullandığı komutun aynısı - davranış birebir aynı olsun.
# --timeout-graceful-shutdown: açık canlı akış (SSE) bağlantısı kapanışı
# sonsuza kadar bekletmesin; `docker stop` 10 sn sonra SIGKILL gönderir ve
# kapanış kodu ("Sistem durdu", kameraların durması) hiç çalışmazdı.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", \
     "--timeout-graceful-shutdown", "3"]
