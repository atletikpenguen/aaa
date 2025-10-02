# 🐳 Docker Kurulumu - Trading Bot

Bu dosya, trading bot'unuzu Docker ile güvenli şekilde çalıştırmak için oluşturuldu.

## 📋 Gereksinimler

- Docker
- Docker Compose
- .env dosyası (API anahtarları ile)

## 🚀 Hızlı Başlangıç

### 1. Docker Kurulumu (VPS'de)

```bash
# Docker kurulumu
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker Compose kurulumu
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Bot'u Çalıştırma

```bash
# Otomatik script ile
./docker-run.sh

# Manuel olarak
docker-compose up -d
```

### 3. Durum Kontrolü

```bash
# Container durumu
docker-compose ps

# Logları görme
docker-compose logs -f

# Durdurma
docker-compose down
```

## 🔧 Yapılandırma

### Environment Variables (.env)

```bash
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_secret
USE_TESTNET=false

# Server
HTTP_PORT=8000
HTTP_HOST=0.0.0.0

# Telegram (opsiyonel)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 📊 Avantajlar

### ✅ Güvenlik
- İzole çalışma ortamı
- Sistem dosyalarını etkilemez
- Non-root user ile çalışır

### ✅ Stabilite
- Otomatik restart
- Resource limits
- Health checks

### ✅ Kolay Yönetim
- Tek komutla başlatma/durdurma
- Log yönetimi
- Kolay güncelleme

## 🛠️ Komutlar

```bash
# Başlatma
docker-compose up -d

# Durdurma
docker-compose down

# Yeniden başlatma
docker-compose restart

# Logları görme
docker-compose logs -f

# Container'a giriş
docker-compose exec trading-bot bash

# Güncelleme
docker-compose down
docker-compose build
docker-compose up -d
```

## 📁 Dosya Yapısı

```
├── Dockerfile              # Container tanımı
├── docker-compose.yml      # Compose konfigürasyonu
├── docker-run.sh          # Otomatik başlatma scripti
├── .dockerignore          # Docker ignore dosyası
├── .env                   # Environment variables
├── data/                  # Trading verileri (volume)
├── logs/                  # Log dosyaları (volume)
└── app.py                 # Ana uygulama
```

## 🔍 Sorun Giderme

### Port Zaten Kullanımda
```bash
# Port kullanımını kontrol et
lsof -i :8000

# Process'i durdur
kill -9 <PID>
```

### Container Başlamıyor
```bash
# Logları kontrol et
docker-compose logs

# Container'ı yeniden build et
docker-compose build --no-cache
```

### Veri Kaybı Korkusu
- `data/` ve `logs/` klasörleri volume olarak mount edilir
- Verileriniz korunur
- Container silinse bile veriler kalır

## 🚨 Önemli Notlar

1. **İlk çalıştırmadan önce .env dosyasını kontrol edin**
2. **API anahtarlarınızı doğru girdiğinizden emin olun**
3. **Testnet kullanıyorsanız USE_TESTNET=true yapın**
4. **VPS'de firewall ayarlarını kontrol edin (port 8000)**

## 📞 Destek

Sorun yaşarsanız:
1. Logları kontrol edin: `docker-compose logs -f`
2. Container durumunu kontrol edin: `docker-compose ps`
3. .env dosyasını kontrol edin
4. Port 8000'in açık olduğundan emin olun
