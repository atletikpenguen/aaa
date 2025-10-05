# 🐳 Docker Trading Bot - Kullanım Kılavuzu

Bu dosya, Docker ile çalışan trading bot'unuzu nasıl yöneteceğinizi adım adım anlatır.

## 📁 **Önemli: Hangi Dizinde Çalıştırmalısınız?**

**HER ZAMAN** proje dizininde çalıştırın:
```bash
cd /root/aaa  # VEYA projenizin bulunduğu dizin
```

## 🚀 **1. BOT'U ÇALIŞTIRMA**

### **Yöntem 1: Otomatik Script (ÖNERİLEN)**
```bash
# Proje dizininde
cd /root/aaa
./docker-run.sh
```

### **Yöntem 2: Manuel**
```bash
# Proje dizininde
cd /root/aaa
docker-compose up -d
```

## 🛑 **2. BOT'U DURDURMA**

### **Güvenli Durdurma (ÖNERİLEN)**
```bash
# Proje dizininde
cd /root/aaa
docker-compose down
```

### **Acil Durdurma**
```bash
# Proje dizininde
cd /root/aaa
docker-compose kill
docker-compose down
```

## 📊 **3. BOT DURUMUNU KONTROL ETME**

### **Container Durumu**
```bash
# Proje dizininde
cd /root/aaa
docker-compose ps
```

### **Logları Görme**
```bash
# Proje dizininde
cd /root/aaa
docker-compose up -d
```

### **Son 50 Log Satırı**
```bash
# Proje dizininde
cd /root/aaa
docker-compose logs --tail=50
```

## 🔄 **4. BOT'U YENİDEN BAŞLATMA**

### **Hızlı Restart**
```bash
# Proje dizininde
cd /root/aaa
docker-compose restart
```

### **Tamamen Yeniden Başlatma**
```bash
# Proje dizininde
cd /root/aaa
docker-compose down
docker-compose up -d
```

## 📋 **5. LOG KAYITLARI**

### **Log Dosyalarının Yeri**
```bash
# Loglar bu dizinde saklanır
/root/aaa/logs/
```

### **Log Dosyalarını Görme**
```bash
# Proje dizininde
cd /root/aaa
ls -la logs/
```

### **Canlı Log Takibi**
```bash
# Proje dizininde
cd /root/aaa
docker-compose logs -f
```

## 🌐 **6. WEB ARAYÜZÜNE ERİŞİM**

### **Erişim Adresleri**
- **VPS IP**: `http://VPS_IP:8000`
- **Lokal**: `http://localhost:8000`

### **Örnek**
```
http://37.148.209.104:8000
```

## 📦 **7. BAŞKA YERE AKTARIM**

### **A) Projeyi Yedekleme**
```bash
# Proje dizininde
cd /root/aaa
tar -czf trading-bot-backup.tar.gz .
```

### **B) Başka VPS'e Aktarma**
```bash
# 1. Yedek dosyasını yeni VPS'e yükleyin
# 2. Yeni VPS'de açın
tar -xzf trading-bot-backup.tar.gz
cd aaa

# 3. .env dosyasını düzenleyin
nano .env

# 4. Bot'u çalıştırın
./docker-run.sh
```

### **C) Zip ile Aktarma**
```bash
# Proje dizininde
cd /root/aaa
zip -r trading-bot.zip .
```

## 🔧 **8. SORUN GİDERME**

### **Bot Çalışmıyor**
```bash
# Proje dizininde
cd /root/aaa
docker-compose ps
docker-compose logs
```

### **Port Zaten Kullanımda**
```bash
# Port 8000'i kullanan process'i bul
lsof -i :8000

# Process'i durdur
kill -9 <PID>
```

### **Container Başlamıyor**
```bash
# Proje dizininde
cd /root/aaa
docker-compose down
docker-compose build
docker-compose up -d
```

## 📱 **9. TELEGRAM BİLDİRİMLERİ**

### **Telegram Ayarları**
```bash
# .env dosyasını düzenleyin
nano .env

# Bu satırları ekleyin:
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 🚨 **10. ACİL DURUM KOMUTLARI**

### **Tüm Container'ları Durdur**
```bash
# Proje dizininde
cd /root/aaa
docker-compose down
```

### **Sistem Yeniden Başlatma Sonrası**
```bash
# Proje dizininde
cd /root/aaa
docker-compose up -d
```

### **Logları Temizle**
```bash
# Proje dizininde
cd /root/aaa
docker-compose logs --tail=0
```

## 📋 **11. GÜNLÜK KULLANIM**

### **Sabah Kontrolü**
```bash
# Proje dizininde
cd /root/aaa
docker-compose ps
docker-compose logs --tail=20
```

### **Akşam Kontrolü**
```bash
# Proje dizininde
cd /root/aaa
docker-compose logs --tail=50
```

## ⚠️ **12. ÖNEMLİ NOTLAR**

### **Her Zaman Proje Dizininde Çalıştırın**
```bash
cd /root/aaa  # ÖNEMLİ!
```

### **API Anahtarlarını Kontrol Edin**
```bash
nano .env
```

### **Logları Düzenli Takip Edin**
```bash
docker-compose logs -f
```

### **Bot'u Durdurmadan Önce**
```bash
docker-compose down
```

## 🎯 **13. HIZLI REFERANS**

| İşlem | Komut | Dizin |
|-------|-------|-------|
| Bot'u Başlat | `docker-compose up -d` | `/root/aaa` |
| Bot'u Durdur | `docker-compose down` | `/root/aaa` |
| Logları Gör | `docker-compose logs -f` | `/root/aaa` |
| Durum Kontrol | `docker-compose ps` | `/root/aaa` |
| Yeniden Başlat | `docker-compose restart` | `/root/aaa` |

## 🆘 **14. YARDIM**

### **Sorun Yaşarsanız**
1. **Logları kontrol edin**: `docker-compose logs -f`
2. **Durum kontrolü**: `docker-compose ps`
3. **Yeniden başlatın**: `docker-compose restart`
4. **Tamamen yeniden başlatın**: `docker-compose down && docker-compose up -d`

### **Web Arayüzü**
- Dashboard: `http://VPS_IP:8000`
- API Durumu: `http://VPS_IP:8000/health`

---

**🎉 Artık trading bot'unuzu profesyonelce yönetebilirsiniz!**
