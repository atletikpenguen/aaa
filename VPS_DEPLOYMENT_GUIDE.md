# 🚀 VPS Deployment Rehberi - Trader Bot

Bu rehber, Trader YLMZ 3.0 projesini Ubuntu VPS sunucusunda çalıştırmak için gerekli tüm adımları içerir.


cmdye

ssh root@37.148.209.104
root
Onqwe@25**



## 📍 **ÖNEMLİ NOTLAR**

- **📍 NEREDE:** Her bölümde komutların nerede çalıştırılacağı belirtilmiştir
- **VPS Terminal:** VPS sunucunuzda SSH ile bağlandıktan sonra terminal'de
- **Lokal Makine:** Kendi bilgisayarınızda
- **Tarayıcı:** Web arayüzüne erişim için

## 🎯 **Hızlı Başlangıç**

1. **VPS'ye bağlan** → SSH ile VPS'ye bağlan
2. **Projeyi yükle** → Git ile veya manuel yükleme
3. **Build et** → `./build.sh` çalıştır
4. **Başlat** → `./start.sh` çalıştır
5. **Erişim** → Tarayıcıda `http://your-vps-ip:8000`

## 📋 VPS Gereksinimleri

- **OS**: Ubuntu 20.04 LTS veya üzeri
- **CPU**: 1 vCPU (minimum)
- **RAM**: 1 GB (minimum)
- **Disk**: 20 GB SSD
- **Network**: Stabil internet bağlantısı

## 🔧 1. Sunucu Hazırlığı

> **📍 NEREDE:** VPS sunucunuzda SSH ile bağlandıktan sonra terminal'de

### Sistem Güncellemesi
```bash
# VPS terminal'de çalıştır
sudo apt update && sudo apt upgrade -y
```

### Gerekli Paketleri Yükle
```bash
# VPS terminal'de çalıştır
sudo apt install -y python3 python3-pip python3-venv git curl wget htop lsof
```

### Python Versiyonu Kontrol
```bash
# VPS terminal'de çalıştır
python3 --version  # 3.8+ olmalı
```

## 📦 2. Proje Kurulumu

> **📍 NEREDE:** VPS sunucunuzda, proje klasöründe

### Projeyi VPS'ye Yükle
```bash
# VPS terminal'de çalıştır - proje ana dizininde
# Git ile (önerilen)
git clone https://github.com/your-repo/trader_ylmz_3.git
cd trader_ylmz_3

# Veya manuel yükleme
# 1. Lokal makinenizde projeyi zip'le
# 2. VPS'ye yükle (scp, ftp, vs.)
# 3. VPS'de aç: unzip trader_ylmz_3.zip
# 4. cd trader_ylmz_3
```

### Sanal Çevre Oluştur
```bash
# VPS terminal'de çalıştır - proje klasöründe (/home/ubuntu/trader_ylmz_3)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Dosyası Hazırla
```bash
# VPS terminal'de çalıştır - proje klasöründe
cp env.example .env
nano .env  # API anahtarlarınızı girin
```

`.env` dosyasını düzenle:
```env
# Binance API Ayarları
BINANCE_API_KEY=your_actual_binance_api_key
BINANCE_API_SECRET=your_actual_binance_api_secret

# Testnet kullanımı (üretim için false)
USE_TESTNET=false

# HTTP Server Ayarları
HTTP_PORT=8000
HTTP_HOST=0.0.0.0

# Log Ayarları
LOG_LEVEL=INFO

# Güvenlik
SECRET_KEY=your_strong_secret_key_here
```

## 🔨 3. Executable Oluşturma

> **📍 NEREDE:** VPS sunucunuzda, proje klasöründe, sanal çevre aktifken

### PyInstaller Yükle
```bash
# VPS terminal'de çalıştır - proje klasöründe, sanal çevre aktifken
pip install pyinstaller
```

### Build Scriptini Çalıştır
```bash
# VPS terminal'de çalıştır - proje klasöründe
chmod +x build.sh
./build.sh
```

Bu script:
- ✅ Executable oluşturur (`dist/trader_bot`)
- ✅ Gerekli dosyaları kopyalar
- ✅ Startup scriptleri oluşturur
- ✅ Build raporunu gösterir

## 🚀 4. Bot'u Çalıştırma

> **📍 NEREDE:** VPS sunucunuzda, dist/ klasöründe

### Manuel Çalıştırma
```bash
# VPS terminal'de çalıştır - dist/ klasöründe
cd dist/
chmod +x trader_bot start.sh stop.sh update.sh
./start.sh
```

### Web Arayüzüne Erişim
```
# Tarayıcınızda açın (lokal makinenizden)
http://your-vps-ip:8000
# Örnek: http://192.168.1.100:8000
```

## ⚙️ 5. Sistemd Servisi (Otomatik Başlatma)

> **📍 NEREDE:** VPS sunucunuzda, proje klasöründe

### Servis Dosyasını Kopyala
```bash
# VPS terminal'de çalıştır - proje klasöründe
sudo cp trader-bot.service /etc/systemd/system/
```

### Servis Dosyasını Düzenle
```bash
# VPS terminal'de çalıştır
sudo nano /etc/systemd/system/trader-bot.service
```

**ÖNEMLİ:** Dosyada `/home/ubuntu/trader_bot` yolunu kendi yolunuzla değiştirin.
- Örnek: `/home/yourusername/trader_ylmz_3/dist`

### Servisi Aktifleştir
```bash
# VPS terminal'de çalıştır
sudo systemctl daemon-reload
sudo systemctl enable trader-bot
sudo systemctl start trader-bot
```

### Servis Durumunu Kontrol Et
```bash
# VPS terminal'de çalıştır
sudo systemctl status trader-bot
```

## 🔐 6. Güvenlik Ayarları

> **📍 NEREDE:** VPS sunucunuzda

### Firewall Konfigürasyonu
```bash
# VPS terminal'de çalıştır
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 8000
```

### Nginx Reverse Proxy (Opsiyonel)
```bash
# VPS terminal'de çalıştır
sudo apt install nginx -y
sudo nano /etc/nginx/sites-available/trader-bot
```

Nginx konfigürasyonu:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# VPS terminal'de çalıştır
sudo ln -s /etc/nginx/sites-available/trader-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### SSL Sertifikası (Opsiyonel)
```bash
# VPS terminal'de çalıştır
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

## 📊 7. Monitoring ve Log Takibi

> **📍 NEREDE:** VPS sunucunuzda

### Log Dosyalarını Takip Et
```bash
# VPS terminal'de çalıştır - dist/ klasöründe
# Uygulama logları
tail -f logs/app.log

# Systemd logları
sudo journalctl -u trader-bot -f

# Sistem kaynakları
htop
```

### Servis Yönetimi
```bash
# VPS terminal'de çalıştır
# Başlat
sudo systemctl start trader-bot

# Durdur
sudo systemctl stop trader-bot

# Yeniden başlat
sudo systemctl restart trader-bot

# Durum kontrol
sudo systemctl status trader-bot

# Otomatik başlatmayı kapat
sudo systemctl disable trader-bot
```

## 🔄 8. Güncelleme İşlemleri

> **📍 NEREDE:** VPS sunucunuzda, proje klasöründe

### Otomatik Güncelleme (Git ile)
```bash
# VPS terminal'de çalıştır - proje klasöründe
./update.sh
```

### Manuel Güncelleme
```bash
# VPS terminal'de çalıştır - proje klasöründe
# 1. Bot'u durdur
sudo systemctl stop trader-bot

# 2. Kod güncellemelerini çek
git pull origin main

# 3. Yeniden build et
./build.sh

# 4. Bot'u başlat
sudo systemctl start trader-bot
```

## 💾 9. Backup ve Restore

> **📍 NEREDE:** VPS sunucunuzda, proje klasöründe

### Otomatik Backup Scripti
```bash
# VPS terminal'de çalıştır - proje klasöründe
nano backup.sh
```

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/ubuntu/backups"
PROJECT_DIR="/home/ubuntu/trader_bot"

mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/trader_bot_$DATE.tar.gz -C $PROJECT_DIR .

# 7 günden eski backup'ları sil
find $BACKUP_DIR -name "trader_bot_*.tar.gz" -mtime +7 -delete
```

```bash
# VPS terminal'de çalıştır
chmod +x backup.sh

# Crontab'a ekle (günlük backup)
crontab -e
# 0 2 * * * /home/ubuntu/backup.sh
```

### Restore İşlemi
```bash
# VPS terminal'de çalıştır
# Bot'u durdur
sudo systemctl stop trader-bot

# Backup'tan geri yükle
tar -xzf /home/ubuntu/backups/trader_bot_YYYYMMDD_HHMMSS.tar.gz

# Bot'u başlat
sudo systemctl start trader-bot
```

## 🔍 10. Sorun Giderme

> **📍 NEREDE:** VPS sunucunuzda

### Log Kontrolü
```bash
# VPS terminal'de çalıştır - dist/ klasöründe
# Uygulama logları
tail -n 100 logs/app.log

# Systemd logları
sudo journalctl -u trader-bot --since "1 hour ago"

# Sistem kaynakları
free -h
df -h
```

### Port Kontrolü
```bash
# VPS terminal'de çalıştır
# Port kullanımı
sudo lsof -i :8000

# Network bağlantıları
sudo netstat -tulpn | grep 8000
```

### Process Kontrolü
```bash
# VPS terminal'de çalıştır
# Bot process'i
ps aux | grep trader_bot

# Bot'u manuel durdur
pkill -f trader_bot
```

### Yaygın Sorunlar

**1. Port zaten kullanımda**
```bash
# VPS terminal'de çalıştır
sudo lsof -i :8000
sudo kill -9 <PID>
```

**2. Permission denied**
```bash
# VPS terminal'de çalıştır - dist/ klasöründe
chmod +x trader_bot
chown $USER:$USER trader_bot
```

**3. .env dosyası bulunamadı**
```bash
# VPS terminal'de çalıştır - dist/ klasöründe
cp env.example .env
nano .env  # API anahtarlarını gir
```

**4. Python modülü bulunamadı**
```bash
# VPS terminal'de çalıştır - proje klasöründe
source venv/bin/activate
pip install -r requirements.txt
```

## 📱 11. Web Arayüzü Erişimi

> **📍 NEREDE:** Tarayıcınızda (lokal makinenizden)

### Lokal Erişim
```
# VPS sunucusunda çalıştırıyorsanız
http://localhost:8000
```

### Uzak Erişim
```
# Tarayıcınızda açın
http://your-vps-ip:8000
# Örnek: http://192.168.1.100:8000
```

### Domain ile Erişim (Nginx ile)
```
# Tarayıcınızda açın
http://your-domain.com
https://your-domain.com  # SSL ile
```

## ✅ 12. Kurulum Kontrolü

> **📍 NEREDE:** VPS terminal'de ve tarayıcınızda

Bot başarıyla çalışıyor mu kontrol etmek için:

1. **Servis Durumu**: VPS terminal'de `sudo systemctl status trader-bot`
2. **Web Arayüzü**: Tarayıcınızda `http://your-vps-ip:8000` açılıyor mu?
3. **Log Dosyaları**: VPS terminal'de `tail -f logs/app.log` hata var mı?
4. **API Bağlantısı**: Web arayüzünde Dashboard'da Binance bağlantısı aktif mi?
5. **Strateji Ekleme**: Web arayüzünde test stratejisi eklenebiliyor mu?

## 📞 Destek

Sorun yaşarsanız:
1. Log dosyalarını kontrol edin
2. GitHub Issues'da sorun bildirin
3. Dokumentasyonu tekrar gözden geçirin

---

**Son Güncelleme**: $(date +"%d.%m.%Y")
**Versiyon**: 3.0
**Platform**: Ubuntu 20.04+ VPS
