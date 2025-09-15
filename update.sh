#!/bin/bash
# VPS Update Script - Trader Bot
# Bu script VPS'de trader bot'u günceller

echo "🔄 Trader Bot VPS Update"
echo "========================"

# Renkli çıktı
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Çalışma dizinini ayarla
cd "$(dirname "$0")"

echo -e "${BLUE}📍 Çalışma dizini: $(pwd)${NC}"

# 1. Git repository kontrolü
if [ ! -d ".git" ]; then
    echo -e "${RED}❌ Git repository bulunamadı!${NC}"
    echo -e "${YELLOW}💡 Manuel güncelleme yapmanız gerekiyor:${NC}"
    echo "   1. Yeni kod dosyalarını yükle"
    echo "   2. ./build.sh çalıştır"
    echo "   3. ./startup.sh ile başlat"
    exit 1
fi

# 2. Mevcut durumu yedekle
echo -e "${BLUE}💾 Mevcut durum yedekleniyor...${NC}"
backup_dir="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup_dir"

# Önemli dosyaları yedekle
if [ -f ".env" ]; then
    cp .env "$backup_dir/"
    echo -e "${GREEN}✅ .env dosyası yedeklendi${NC}"
fi

if [ -d "data" ]; then
    cp -r data "$backup_dir/"
    echo -e "${GREEN}✅ Data klasörü yedeklendi${NC}"
fi

if [ -d "logs" ]; then
    cp -r logs "$backup_dir/"
    echo -e "${GREEN}✅ Logs klasörü yedeklendi${NC}"
fi

# 3. Bot'u durdur (eğer çalışıyorsa)
echo -e "${BLUE}🛑 Bot durduruluyor...${NC}"
if pgrep -f trader_bot > /dev/null; then
    pkill -f trader_bot
    echo -e "${GREEN}✅ Bot durduruldu${NC}"
    sleep 3
else
    echo -e "${YELLOW}⚠️  Bot zaten çalışmıyor${NC}"
fi

# 4. Git'ten güncellemeleri kontrol et
echo -e "${BLUE}🔍 Git güncellemeleri kontrol ediliyor...${NC}"
git fetch origin

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "${GREEN}✅ Kod zaten güncel${NC}"
    echo -e "${BLUE}🚀 Bot yeniden başlatılıyor...${NC}"
    ./startup.sh
    exit 0
fi

echo -e "${YELLOW}🔄 Yeni güncellemeler bulundu!${NC}"

# 5. Değişiklikleri göster
echo -e "${BLUE}📝 Değişiklikler:${NC}"
git log --oneline $LOCAL..$REMOTE

# 6. Onay al
read -p "Güncellemek istiyor musunuz? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}❌ Güncelleme iptal edildi${NC}"
    exit 0
fi

# 7. Git pull
echo -e "${BLUE}⬇️  Kod güncellemeleri çekiliyor...${NC}"
if git pull origin main; then
    echo -e "${GREEN}✅ Kod başarıyla güncellendi${NC}"
else
    echo -e "${RED}❌ Git pull başarısız!${NC}"
    echo -e "${YELLOW}🔄 Yedekten geri yükleme...${NC}"
    
    # Yedekten geri yükle
    if [ -f "$backup_dir/.env" ]; then
        cp "$backup_dir/.env" .
    fi
    
    exit 1
fi

# 8. Sanal çevre kontrolü
if [ -d "venv" ]; then
    echo -e "${BLUE}🐍 Sanal çevre aktifleştiriliyor...${NC}"
    source venv/bin/activate
else
    echo -e "${YELLOW}⚠️  Sanal çevre bulunamadı${NC}"
fi

# 9. Bağımlılıkları güncelle
echo -e "${BLUE}📦 Bağımlılıklar güncelleniyor...${NC}"
pip install -r requirements.txt

# 10. Yeni executable oluştur
echo -e "${BLUE}🔨 Yeni executable oluşturuluyor...${NC}"
if [ -f "build.sh" ]; then
    ./build.sh
else
    echo -e "${YELLOW}⚠️  build.sh bulunamadı, manuel build gerekli${NC}"
    pyinstaller trader_bot.spec
fi

# 11. Yedeklenen dosyaları geri yükle
echo -e "${BLUE}🔄 Yedeklenen dosyalar geri yükleniyor...${NC}"

if [ -f "$backup_dir/.env" ]; then
    cp "$backup_dir/.env" .
    echo -e "${GREEN}✅ .env dosyası geri yüklendi${NC}"
fi

if [ -d "$backup_dir/data" ]; then
    cp -r "$backup_dir/data/"* data/ 2>/dev/null || true
    echo -e "${GREEN}✅ Data dosyaları geri yüklendi${NC}"
fi

# 12. Bot'u başlat
echo -e "${GREEN}🎉 Güncelleme tamamlandı!${NC}"
echo -e "${BLUE}🚀 Bot yeniden başlatılıyor...${NC}"

# Kısa bekleme
sleep 2

# Bot'u başlat
./startup.sh

echo -e "${GREEN}✅ Güncelleme ve yeniden başlatma tamamlandı!${NC}"
echo -e "${BLUE}📁 Yedek dosyalar: $backup_dir/${NC}"
