#!/bin/bash
# VPS Deployment için Build Script
# Bu script projeyi PyInstaller ile executable haline getirir

echo "🚀 Trader Bot VPS Build Script"
echo "==============================="

# Renkli çıktı için
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Hata durumunda çık
set -e

# Başlangıç zamanı
start_time=$(date +%s)

echo -e "${BLUE}📦 Build işlemi başlıyor...${NC}"

# 1. Sanal çevre kontrolü
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${YELLOW}⚠️  Sanal çevre aktif değil. Aktifleştiriliyor...${NC}"
    if [ -d "venv" ]; then
        source venv/bin/activate
        echo -e "${GREEN}✅ Sanal çevre aktifleştirildi${NC}"
    else
        echo -e "${RED}❌ Sanal çevre bulunamadı! Önce 'python -m venv venv' çalıştırın${NC}"
        exit 1
    fi
fi

# 2. Bağımlılıkları kontrol et
echo -e "${BLUE}📋 Bağımlılıklar kontrol ediliyor...${NC}"
pip install -r requirements.txt

# 3. PyInstaller yükle
echo -e "${BLUE}🔧 PyInstaller kontrol ediliyor...${NC}"
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${YELLOW}⚠️  PyInstaller bulunamadı. Yükleniyor...${NC}"
    pip install pyinstaller
fi

# 4. Eski build'leri temizle
if [ -d "dist" ]; then
    echo -e "${YELLOW}🗑️  Eski build dosyaları temizleniyor...${NC}"
    rm -rf dist/
fi

if [ -d "build" ]; then
    rm -rf build/
fi

# 5. PyInstaller ile build et
echo -e "${BLUE}🔨 Executable oluşturuluyor...${NC}"
pyinstaller trader_bot.spec

# 6. Build kontrolü
if [ ! -f "dist/trader_bot" ]; then
    echo -e "${RED}❌ Build başarısız! Executable oluşturulamadı${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Executable başarıyla oluşturuldu${NC}"

# 7. Gerekli dosyaları dist/ klasörüne kopyala
echo -e "${BLUE}📁 Gerekli dosyalar kopyalanıyor...${NC}"

# Klasörleri oluştur
mkdir -p dist/logs
mkdir -p dist/data

# .env dosyası
if [ -f ".env" ]; then
    cp .env dist/
    echo -e "${GREEN}✅ .env dosyası kopyalandı${NC}"
else
    cp env.example dist/.env
    echo -e "${YELLOW}⚠️  .env dosyası bulunamadı. env.example kopyalandı${NC}"
fi

# Diğer gerekli dosyalar (eğer varsa)
if [ -f "strateji.md" ]; then
    cp strateji.md dist/
fi

if [ -f "README.md" ]; then
    cp README.md dist/
fi

# 8. Çalıştırma scripti oluştur
echo -e "${BLUE}📝 Çalıştırma scripti oluşturuluyor...${NC}"
cat > dist/start.sh << 'EOF'
#!/bin/bash
# Trader Bot Başlatma Scripti

echo "🚀 Trader Bot başlatılıyor..."

# Çalışma dizinini ayarla
cd "$(dirname "$0")"

# .env dosyası kontrolü
if [ ! -f ".env" ]; then
    echo "❌ .env dosyası bulunamadı!"
    echo "env.example dosyasını .env olarak kopyalayın ve API anahtarlarınızı girin."
    exit 1
fi

# Gerekli dizinleri oluştur
mkdir -p logs data

# Executable'ı çalıştır
echo "✅ Bot başlatıldı. Web arayüzü: http://localhost:8000"
./trader_bot

echo "✅ Bot kapatıldı."
EOF

chmod +x dist/start.sh

# 9. Durdurma scripti oluştur
cat > dist/stop.sh << 'EOF'
#!/bin/bash
# Trader Bot Durdurma Scripti

echo "🛑 Trader Bot durduruluyor..."

# Process ID'yi bul ve durdur
pkill -f trader_bot

echo "✅ Bot durduruldu."
EOF

chmod +x dist/stop.sh

# 10. Güncelleme scripti oluştur
cat > dist/update.sh << 'EOF'
#!/bin/bash
# Trader Bot Güncelleme Scripti

echo "🔄 Trader Bot güncelleniyor..."

# Bot'u durdur
./stop.sh

# Git'ten güncellemeleri çek (eğer git repository'si varsa)
if [ -d "../.git" ]; then
    cd ..
    git pull origin main
    ./build.sh
    echo "✅ Güncelleme tamamlandı!"
else
    echo "❌ Git repository bulunamadı. Manuel güncelleme gerekli."
fi
EOF

chmod +x dist/update.sh

# 11. Boyut bilgisi
executable_size=$(du -h dist/trader_bot | cut -f1)
total_size=$(du -sh dist/ | cut -f1)

# 12. Build sonuç raporu
end_time=$(date +%s)
build_time=$((end_time - start_time))

echo ""
echo -e "${GREEN}🎉 BUILD TAMAMLANDI!${NC}"
echo "========================"
echo -e "📁 Executable: ${BLUE}dist/trader_bot${NC}"
echo -e "📦 Executable boyutu: ${BLUE}$executable_size${NC}"
echo -e "📁 Toplam boyut: ${BLUE}$total_size${NC}"
echo -e "⏱️  Build süresi: ${BLUE}${build_time} saniye${NC}"
echo ""
echo -e "${YELLOW}📋 VPS'ye yükleme adımları:${NC}"
echo "1. dist/ klasörünü VPS'ye yükle"
echo "2. chmod +x trader_bot start.sh stop.sh update.sh"
echo "3. .env dosyasını düzenle"
echo "4. ./start.sh ile başlat"
echo ""
echo -e "${GREEN}✅ Build başarıyla tamamlandı!${NC}"
