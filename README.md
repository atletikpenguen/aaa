# Trader YLMZ 2.0

## 📋 **VERSİYON TAKİBİ**

### **VPS Aktif Versiyon (5 Ekim 2025)**
- **Durum**: VPS'te çalışan aktif versiyon
- **Son Değişiklikler**: 
  - ✅ Kısmi satış hatası düzeltildi: `'dict' object has no attribute 'quantity'`
  - ✅ Strateji f1db794e hatası çözüldü
  - ⚠️ Risk kontrolü aktif: Minimum pozisyon limiti -400.00$ aşıldı

### **Değişen Dosyalar**
- **core/dca_ott_strategy.py** (5 Ekim 2025)
  - Kısmi satış hatası düzeltildi: `last_position.quantity` → `last_position["quantity"]`
  - `last_position.order_id` → `last_position["order_id"]` düzeltmesi
  - `last_position.buy_price` → `last_position["buy_price"]` düzeltmesi
  - Dict erişim hataları tamamen çözüldü

---

masasütü
PS C:\pythonProjeler\0_corsur\_trader\vps_aktif\aaa> python -m uvicorn app:app --reload


vps
root@ns1:~# cd aaa
root@ns1:~/aaa# source venv/bin/activate
(venv) root@ns1:~/aaa# nohup python3 app.py > bot.log 2>&1 &
(venv) root@ns1:~/aaa# tail -f bot.log

(venv) root@ns1:~/aaa# pkill -9 -f "app.py"



## 🚀 **Proje Özeti**

Trader YLMZ 2.0, Binance API kullanarak otomatik kripto para trading yapan gelişmiş bir trading bot sistemidir. Grid+OTT ve DCA+OTT stratejilerini destekleyen, gerçek zamanlı monitoring ve risk yönetimi özelliklerine sahip profesyonel bir trading platformudur.

### 🔧 KRİTİK DÜZELTME: Döngü Hesaplama Sorunu Çözüldü (30 Eylül 2025)

**🚨 SORUN:** DCA stratejisinde döngü numarası yanlış hesaplanıyordu
- **Hata**: İlk döngü D0 olarak başlıyordu (D1 olmalı)
- **Sebep**: `cycle_number` default değeri 0, +1 ekleme mantığı hatası
- **Sonuç**: Trades'te D0-1, D0-2... görünüyordu, state'te cycle_number: 0

**✅ ÇÖZÜM:**
- **Döngü Başlangıcı**: İlk döngü D1 olarak başlar (D0 değil)
- **Debug Sistemi**: WARNING düzeyinde döngü debug sistemi eklendi
- **State Düzeltmesi**: Mevcut stratejilerin cycle_number'ı düzeltildi
- **Sonuç**: Artık D1-1, D1-2, D2-1, D2-2... şeklinde doğru döngü numaraları

### 🔧 KRİTİK DÜZELTME: DCA Stratejisi Ardışık Alım Sorunu Çözüldü (25 Eylül 2025)

**🚨 SORUN:** DCA stratejisinde ardışık alım fiyat artışı hatası
- **Hata**: `consecutive_buy_price_increase` - DCA mantığına aykırı kontrol
- **Sebep**: Çok katı güvenlik kontrolleri DCA mantığını engelliyordu
- **Sonuç**: Stratejiler otomatik durduruluyordu

**✅ ÇÖZÜM:**
- **DCA Alım Kontrolü**: Son alım fiyatı kontrolü kaldırıldı (çok katıydı)
- **Debug Monitor**: Ardışık alım kontrolü %5 eşiğine çıkarıldı
- **Telegram Format**: HTML entity escape hatası düzeltildi
- **Sonuç**: DCA stratejisi artık doğru mantıkla çalışacak

### 🎯 YENİ ÖZELLİK: DCA Stratejisinde Kar Alım Eşiği Parametresi (25 Eylül 2025)

**💰 DCA+OTT Stratejisinde Kar Alım Eşiği Artık Değişken**
- **Yeni Parametre**: `profit_threshold_pct` - Kar alım eşiği yüzdesi
- **Önceki Durum**: Sabit %1 kar alım şartı
- **Yeni Durum**: %0.1 - %10.0 arası ayarlanabilir kar alım eşiği
- **Varsayılan**: %1.0 (eski davranışı korur)
- **Etkilenen Alanlar**: Tam satış, kısmi satış, backtest engine, debug logları

### 📊 YENİ ÖZELLİK: Excel Backtest Analiz Sistemi (23 Eylül 2025)

**🔥 YENİ ÖZELLİK: Excel Verisiyle Strateji Backtest Analizi**
- **Excel OHLCV Yükleme**: Date, Time, Open, High, Low, Close, Volume formatında Excel dosyalarını yükleyin
- **Strateji Seçimi**: Mevcut stratejilerimizden birini seçin (BOL-Grid, DCA+OTT, Grid+OTT)
- **Parametre Ayarlama**: Strateji parametrelerini özelleştirin
- **Gerçek Backtest**: Bizim PnL hesaplama sistemimizle gerçek backtest analizi
- **Grafik Görselleştirme**: Fiyat ve bakiye performansının grafiksel gösterimi
- **Detaylı Rapor**: İşlem tablosu, kar/zarar analizi, istatistikler

**🎯 PINE SCRIPT OTT MANTĞI UYGULANDI (23 Eylül 2025)**
- **VIDYA Algoritması**: Variable Index Dynamic Average hesaplama eklendi
- **CMO Hesaplama**: Chande Momentum Oscillator ile ağırlıklandırma
- **Trailing Stop Mantığı**: Pine Script koduna uygun OTT hesaplama
- **OTT Sinyal Mantığı**: OTT < OTT_SUP → AL, OTT ≥ OTT_SUP → SAT
- **Backtest Yardım Dosyası**: `backtestyardım.md` - Pine Script kodu ve açıklamaları

**📈 BACKTEST ÖZELLİKLERİ:**
- **Gerçek Strateji Motoru**: Canlı sistemde kullandığımız stratejilerin aynısı
- **Pine Script OTT İndikatörü**: VIDYA + CMO + Trailing Stop mantığı ile gerçek OTT hesaplaması
- **PnL Hesaplama**: Bizim kar-zarar hesaplama sistemimizle uyumlu
- **İşlem Simülasyonu**: Kapanış fiyatında sinyal, sonraki açılışta işlem
- **Risk Metrikleri**: Win rate, max drawdown, ortalama getiri
- **Zaman Analizi**: Test süresi, işlem sıklığı
- **OTT Değer Takibi**: İşlem detaylarında OTT Mode, Upper, Lower değerleri

**🎯 KULLANIM ADIMLARı:**
1. Dashboard'da "Backtest Analiz" sayfasına gidin
2. **Adım 1**: Excel dosyanızı yükleyin (OHLCV formatında)
3. **Adım 2**: Strateji seçin ve parametrelerini ayarlayın
4. **Adım 3**: Backtest sonuçlarını inceleyin
5. Grafik ve detaylı tabloları analiz edin

**📋 EXCEL FORMAT ÖRNEĞİ:**
```
Date        Time   Open     High     Low      Close    Volume   WClose
05.11.2024  00:00  2423.55  2429.34  2356.00  2369.99  393320   2387.28
05.11.2024  01:00  2369.98  2413.80  2364.91  2405.17  162084   2389.61
```

### 🔧 KRİTİK DÜZELTME: Overflow Hataları Çözüldü (23 Eylül 2025)

**🚨 SORUN:** Sistemde ciddi matematiksel overflow hataları vardı
- ❌ **"Result too large"** hataları: Matematiksel hesaplamalarda taşma
- ❌ **"overflow encountered"** uyarıları: NumPy hesaplamalarında taşma
- ❌ **Sync calculate signal hatası**: Excel backtest'te sürekli hata
- ❌ **PnL hesaplama hataları**: Pozisyon değerlerinde overflow

**✅ ÇÖZÜM:** Tüm matematiksel hesaplamalar overflow korumalı hale getirildi
- ✅ **PnL Calculator**: `core/pnl_calculator.py` overflow korumalı
- ✅ **Signal Calculation**: `core/excel_backtest_engine.py` güvenli hesaplama
- ✅ **Indicators**: `core/indicators.py` EMA/SMA/OTT overflow korumalı
- ✅ **Güvenlik Limitleri**: 1e15 maksimum, 1e-15 minimum değer kontrolü
- ✅ **Hata Yakalama**: Try-catch blokları ile güvenli hesaplama
- ✅ **Fallback Değerler**: Hata durumunda güvenli varsayılan değerler

**🎯 SONUÇ:** Artık sistem overflow hataları olmadan çalışıyor
- ✅ Excel backtest'te "Result too large" hataları çözüldü
- ✅ PnL hesaplamalarında overflow uyarıları yok
- ✅ Tüm matematiksel işlemler güvenli aralıklarda
- ✅ Sistem kararlı ve güvenilir çalışıyor

### 🔧 DÜZELTME: DCA Referans Sistemi (23 Eylül 2025)

**🚨 SORUN:** DCA alış mantığında referans fiyat sistemi bozulmuştu
- ❌ **Yanlış referans**: Son satış fiyatından düşüş kontrolü yapıyordu
- ❌ **Kısmi satış sonrası**: Referans fiyatı güncellenmiyordu
- ❌ **Tam satış sonrası**: Yeni döngü için referans sıfırlanmıyordu

**✅ ÇÖZÜM:** Yeni referans sistemi implement edildi
- ✅ **Alış yapıldığında**: Referans = Alış fiyatı
- ✅ **Kısmi satış yapıldığında**: Referans = Satış fiyatı  
- ✅ **Tam satış yapıldığında**: Referans = 0 (yeni döngü için)
- ✅ **Referans = 0 iken OTT AL**: Yeni döngü alışı
- ✅ **Referans > 0 iken OTT AL**: DCA alışı (referans fiyattan düşüş kontrolü)

**🎯 SONUÇ:** DCA mantığı artık doğru çalışıyor
- ✅ İlk alış: Referans = x0 (alış fiyatı)
- ✅ DCA alış: Referans = x1 (yeni alış fiyatı) 
- ✅ Kısmi satış: Referans = x4 (satış fiyatı)
- ✅ Tam satış: Referans = 0 (yeni döngü için)

### 💰 DÜZELTİLMİŞ PnL SİSTEMİ: Profesyonel Kar-Zarar Takibi (22 Eylül 2025)

**🔥 KRİTİK DÜZELTME: Short Pozisyon Unrealized PnL Bug Düzeltmesi (22 Eylül 2025 - Akşam)**
- ❌ **SORUN:** Short pozisyonda fiyat artarken kar gözüküyordu (b24c6190 HUMAUSDT)
- ✅ **ÇÖZÜM:** `core/pnl_calculator.py` formülü düzeltildi - abs() eklendi
- ✅ **SONUÇ:** Artık short pozisyonda fiyat artışı doğru şekilde zarar gözüküyor

**🔥 KRİTİK DÜZELTME: Gerçek Trading Mantığına Uygun Hale Getirildi**

**Önceki Sistem Sorunları:**
- ❌ Pozisyon artırımında bakiye yanlış azalıyordu
- ❌ Pozisyon azaltımında ortalama maliyet yanlış değişiyordu
- ❌ Gerçek trading mantığına uygun değildi
- ❌ Short pozisyon unrealized PnL hesaplama hatası (YENİ DÜZELTME)

**YENİ SİSTEM ÖZELLİKLERİ:**
- ✅ **DOĞRU Bakiye Mantığı**: Sadece realized PnL'de bakiye değişir
- ✅ **DOĞRU Ortalama Maliyet**: Pozisyon artırımında güncellenir, azaltımında değişmez
- ✅ **Profesyonel Trading Mantığı**: Gerçek borsalara uygun
- ✅ **1000 USD Başlangıç**: Her strateji 1000 USD ile başlar
- ✅ **Gerçek Zamanlı PnL**: Anlık fiyat değişimlerine göre unrealized PnL

**🆕 PnL GEÇMİŞİ SİSTEMİ (21 Eylül 2025):**
- **Otomatik kayıt**: Her trade sonrası PnL durumu otomatik kaydedilir
- **Detaylı takip**: Bakiye, kar/zarar, pozisyon bilgileri timestamp ile saklanır
- **CSV dosyası**: `data/{strategy_id}/pnl_history.csv` dosyasında geçmiş tutulur

**DÜZELTME ÖNCESİ VE SONRASI:**
```
❌ ESKİ (YANLIŞ):
→ 100 adet 1 USD'dan al → Bakiye: 900 USD (yanlış!)
→ 100 adet 0.7'den al → Bakiye: 880 USD (yanlış!)

✅ YENİ (DOĞRU):
→ 100 adet 1 USD'dan al → Bakiye: 1000 USD (değişmez)
→ 100 adet 0.7'den al → Bakiye: 1000 USD (hala değişmez)
→ 150 adet 1.15'ten sat → Realized PnL: +45 USD → Bakiye: 1045 USD
```

**TEMEL KURALLAR:**
- 🔄 **Pozisyon Artırımı**: Bakiye değişmez, ortalama maliyet güncellenir
- 💰 **Pozisyon Azaltımı**: Realized PnL bakiyeye eklenir, ortalama maliyet değişmez

### ♻️ DÜZELTME: DCA+OTT Döngü Mantığı Bug Düzeltmesi (20 Eylül 2025)

- **Döngü sıfırlama bugı düzeltildi**: Full exit sonrası yeni döngü başlangıcında döngü numarası yanlış hesaplanıyordu
- **Strategy Engine düzeltmesi**: `strategy_engine.py`'de döngü bilgisi hesaplama mantığı tamamen yeniden yazıldı
- **DCA Strategy düzeltmesi**: `dca_ott_strategy.py`'de döngü geçiş mantığı düzeltildi
- **State düzeltmeleri**: Tüm DCA stratejilerinin döngü numaraları trade geçmişiyle uyumlu hale getirildi
- **Gelecek trade'ler**: Artık tüm yeni trade'ler doğru döngü bilgileriyle kaydedilecek

### ♻️ DÜZELTME: BOL-Grid Precision & Min Notional (9 Eylül 2025)

- **Precision düzeltmesi**: `quantity_precision` alanı kullanılmıyor; yerine `step_size` ve `min_qty` ile miktar hesaplanıyor.
- **Min notional kontrolü**: Alım ve kısmi satış için `min_notional` doğrulaması eklendi.
- **Kısmi satış miktarı**: `step_size`'a göre aşağı yuvarlanıyor; `min_qty` ve `min_notional` altındaysa emir gönderilmiyor.

## 🔧 **SON GÜNCELLEMELER (6 Eylül 2025)**

### **🛡️ Universal Debug Monitor ve Güvenlik Sistemi**

**Yeni Güvenlik Özellikleri:**
- ✅ **Universal Monitoring** - Tüm strateji türleri için profesyonel monitoring (DCA+OTT + Grid+OTT)
- ✅ **Otomatik Strateji Durdurma** - Kritik sorunlarda stratejileri otomatik durdurma
- ✅ **Telegram Error Bildirimleri** - Error ve Critical seviyeli sorunlar anında Telegram'a
- ✅ **State Corruption Tespiti** - Pozisyon kaybı, tutarsızlık tespiti ve düzeltme
- ✅ **Trade Mantık Doğrulama** - Yanlış trade'lerin otomatik tespiti ve engellenmesi
- ✅ **Grid+OTT Validations** - GF kontrolü, grid parametreleri validation
- ✅ **Performance Optimizasyonu** - 5 dakika aralıklarla background monitoring

**Güvenlik Kuralları:**
- 🚨 **Kritik Sorunlar**: State corruption, pozisyon kaybı → Anında durdur
- ❌ **Çoklu Error**: 3+ error birikimi → Durdur  
- 🔄 **DCA Kural İhlali**: Son alımın üstünde alım → Durdur
- ⚡ **Grid Anomali**: Hızlı ardışık trade'ler → Uyar
- 📱 **Telegram Alert**: Error/Critical seviyeler → Anında bildir

### **🔄 State Recovery Sistemi**

**Otomatik Pozisyon Kurtarma:**
- ✅ **Trade History Rebuild** - Trade history'den state'leri yeniden inşa eder
- ✅ **DCA Pozisyon Düzeltme** - DCA pozisyon kaybı durumlarını düzeltir
- ✅ **Validation API'leri** - Tüm stratejiler için otomatik validation
- ✅ **Manuel Recovery** - API ile manuel recovery tetiklenebilir

**Recovery API'leri:**
```bash
POST /api/recovery/validate-all        # Tüm stratejileri kontrol et
POST /api/recovery/strategy/{id}       # Belirli strateji recover et
```

### **💰 Net Pozisyon Takip ve Risk Yönetim Sistemi**

**Eklenen Özellikler:**
- ✅ **Binance Pozisyon Takibi** - Hesaptaki tüm pozisyonları gerçek zamanlı takip
- ✅ **Net Pozisyon Hesaplama** - Long pozisyonlar (+), Short pozisyonlar (-) olarak net değer
- ✅ **Risk Limit Sistemi** - Maksimum ve minimum pozisyon limitleri (varsayılan: Max=$2000, Min=-$1200)
- ✅ **Emir Öncesi Risk Kontrolü** - Limit aşımında otomatik emir iptali
- ✅ **Dashboard Container** - Ana sayfada pozisyon takip alanı
- ✅ **Gerçek Zamanlı Göstergeler** - Risk durumu ve pozisyon analizi
- ✅ **Ayarlanabilir Limitler** - Web arayüzünden limit değiştirme
- ✅ **Kalıcı Ayarlar** - Backend'de pozisyon limit ayarları saklanıyor

**Risk Kontrol Mantığı:**
- **Alış Emri**: Net pozisyon + emir tutarı > Max limit → İptal
- **Satış Emri**: Net pozisyon - emir tutarı < Min limit → İptal
- **Güvenlik**: API hatası durumunda emirler otomatik iptal edilir

### **📱 Telegram Retry Mekanizması ve Otomatik Strateji Durdurma**

**Eklenen Özellikler:**
- ✅ **3 Deneme Retry Sistemi** - Telegram mesajları için 3 deneme + 30 saniye bekleme
- ✅ **Otomatik Strateji Durdurma** - Telegram mesajı gönderilemezse strateji otomatik durdurulur
- ✅ **Detaylı Hata Loglama** - Her deneme ayrı ayrı loglanır
- ✅ **Güvenlik Önceliği** - Telegram bağlantısı olmadan trading yapılmaz
- ✅ **Graceful Degradation** - Son denemede başarısız olursa temiz kapanış

**Teknik Detaylar:**
- `telegram.py`'de `send_message()` fonksiyonuna retry mekanizması eklendi
- `strategy_engine.py`'de telegram başarısızlığında strateji durdurma eklendi
- Her deneme arasında 30 saniye bekleme
- 3 deneme sonunda başarısız olursa strateji otomatik durdurulur

### **🔄 DCA+OTT Döngü Bilgisi Dashboard ve Trade Kayıtlarında**

**Eklenen Özellikler:**
- ✅ **Dashboard Döngü Gösterimi** - Grid Z sütununda DCA stratejileri için döngü bilgisi (D1-1, D1-2...)
- ✅ **Trade Kayıt Sistemi** - CSV dosyalarına cycle_info sütunu eklendi
- ✅ **Döngü Takibi** - Her işlemde döngü ve işlem sayısı kaydediliyor
- ✅ **Görsel Ayrım** - DCA döngüleri mor badge ile, Grid Z değerleri normal gösterimle
- ✅ **Geriye Uyumluluk** - Eski trade kayıtları için cycle_info=null desteği

---

## 📁 **Proje Dosya Yapısı**

### 🏗️ **Ana Dizin Dosyaları**

#### **Uygulama Dosyaları**
- **`app.py`** (50KB, 1292 satır) - Ana FastAPI web uygulaması
  - Web arayüzü ve API endpoint'leri
  - Background task yönetimi (strateji koordinatörü)
  - Order monitor sistemi
  - Dashboard ve strateji yönetimi

- **`status.py`** (6.6KB, 174 satır) - Strateji durum monitörü
  - Aktif stratejilerin anlık durumunu gösterir
  - Terminal üzerinden hızlı durum kontrolü
  - OTT hesaplamaları ve grid analizi

- **`debug_tasks.py`** (8.2KB, 320 satır) - Professional Debug Monitor Script
  - Strateji task'larının sürekli kontrolü
  - 5 dakikalık aralıklarla monitoring
  - Detaylı sinyal analizi ve sorun tespiti

- **`test_telegram.py`** (1.5KB, 48 satır) - Telegram bot test scripti
  - Telegram bağlantısını test eder
  - Bot token ve chat ID kontrolü
  - Örnek bildirim gönderimi

#### **Konfigürasyon Dosyaları**
- **`requirements.txt`** (223B, 13 satır) - Python bağımlılıkları
  - FastAPI, uvicorn, ccxt, pydantic vb.

- **`env.example`** (520B, 25 satır) - Örnek environment dosyası
  - API anahtarları, bot token'ları
  - Log ve terminal ayarları

- **`howtorun.txt`** (556B, 22 satır) - Çalıştırma talimatları
  - Development ve production modları
  - Uvicorn komutları

- **`check_status.bat`** (109B, 8 satır) - Windows batch dosyası
  - Hızlı durum kontrolü için
  - `status.py` scriptini çalıştırır

### 🧠 **Core Modülü (`core/`)**

#### **Strateji Motorları**
- **`strategy_engine.py`** (22KB, 517 satır) - Ana strateji motoru
  - Strateji yaşam döngüsü yönetimi
  - Handler'lar ve event sistemi
  - Strateji başlatma/durdurma
  - Error counting ve otomatik durdurma

- **`base_strategy.py`** (5.1KB, 153 satır) - Temel strateji sınıfı
  - Ortak strateji metodları
  - Abstract base class

- **`grid_ott_strategy.py`** (11KB, 353 satır) - Grid+OTT stratejisi
  - Grid trading mantığı
  - OTT entegrasyonu
  - Emir yönetimi

- **`dca_ott_strategy.py`** (34KB, 678 satır) - DCA+OTT stratejisi
  - Dollar Cost Averaging mantığı
  - Döngü takip sistemi
  - Pozisyon yönetimi
  - Debug sistemi

#### **Borsa ve Veri İşleme**
- **`binance.py`** (34KB, 770 satır) - Binance API client
  - Market veri çekimi
  - Emir işlemleri (create, cancel, check)
  - OHLCV ve fiyat verileri
  - Pozisyon takibi

- **`indicators.py`** (12KB, 400+ satır) - Teknik indikatörler
  - Pine Script OTT (Optimized Trend Tracker) hesaplama
  - VIDYA (Variable Index Dynamic Average) algoritması
  - CMO (Chande Momentum Oscillator) hesaplama
  - EMA, SMA ve diğer indikatörler

#### **Veri Yönetimi**
- **`storage.py`** (34KB, 825 satır) - Veri depolama sistemi
  - JSON state kaydetme/yükleme
  - CSV trade kaydetme
  - Strateji konfigürasyonu
  - Pozisyon limit yönetimi

- **`models.py`** (11KB, 325 satır) - Pydantic modelleri
  - Strategy, State, Order modelleri
  - API request/response modelleri

#### **Yardımcı Modüller**
- **`utils.py`** (16KB, 494 satır) - Yardımcı fonksiyonlar
  - Log yönetimi
  - Terminal temizleme
  - Sayı formatlama ve validasyon
  - Binance trading logger

- **`config.py`** (1.4KB, 41 satır) - Konfigürasyon yönetimi
  - Environment variables
  - Uygulama ayarları

- **`telegram.py`** (7.2KB, 201 satır) - Telegram bildirim sistemi
  - Bot entegrasyonu
  - Trade bildirimleri
  - Hata bildirimleri
  - Retry mekanizması

#### **Güvenlik ve Monitoring**
- **`debug_monitor.py`** (25KB, 767 satır) - **YENİ** Universal Debug Monitor
  - Tüm strateji türleri için profesyonel monitoring
  - State corruption ve trade mantık doğrulama
  - Otomatik strateji durdurma sistemi
  - Telegram error bildirimleri
  - Performance optimizasyonu

- **`state_recovery.py`** (10KB, 200 satır) - **YENİ** State Recovery Sistemi
  - Trade history'den otomatik state rebuild
  - DCA pozisyon kaybı düzeltme
  - Validation ve recovery API'leri
  - Kritik bug prevention sistemi

### 🎨 **Web Arayüzü**

#### **Templates (`templates/`)**
- **`base.html`** (36KB, 688 satır) - Ana template
  - CSS/JS include'ları
  - Navigation ve layout

- **`index.html`** (60KB, 1078 satır) - Ana dashboard
  - Strateji listesi
  - Yeni strateji ekleme formu
  - Genel istatistikler
  - Açık emirler tablosu
  - Pozisyon takip alanı

- **`detail.html`** (36KB, 624 satır) - Strateji detay sayfası
  - Emir geçmişi
  - Trade detayları
  - Canlı durum bilgileri

#### **Static (`static/`)**
- **`app.css`** (7.1KB, 404 satır) - CSS stilleri
  - Dashboard tasarımı
  - Responsive layout
  - Strateji renk kodlaması

### 📊 **Veri Dosyaları (`data/`)**

#### **Strateji Verileri**
- **`strategies.json`** (4.6KB, 193 satır) - Tüm stratejiler
  - Aktif/pasif strateji listesi
  - Konfigürasyon parametreleri

- **`order_logs.csv`** (18KB, 112 satır) - Emir geçmişi
  - Tüm emir işlemleri
  - Performans metrikleri
  - Hata logları

- **`position_limits.json`** - Pozisyon limit ayarları
  - Risk yönetimi limitleri
  - Maksimum/minimum pozisyon değerleri

#### **Strateji Dizinleri**
Her strateji için ayrı dizin (`<strategy_id>/`):
- **`state.json`** - Strateji durumu
  - Grid Foundation (GF)
  - Pozisyon bilgileri
  - Döngü sayıları

- **`trades.csv`** - Trade geçmişi (bazı stratejiler için)
  - Gerçekleşen işlemler
  - Kar/zarar bilgileri

### 📝 **Log Dosyaları (`logs/`)**
- **`YYYYMMDD-app.log`** - Günlük log dosyaları (örn: `20250107-app.log`)
  - Her gün otomatik olarak yeni dosya oluşturulur
  - Hata mesajları, debug bilgileri, performans metrikleri
  - 30 günden eski dosyalar otomatik temizlenir
  - API ile log yönetimi: `/api/logs/info`, `/api/logs/cleanup`, `/api/logs/current`

---

## 🎯 **Özellikler**

### **Desteklenen Stratejiler**
- **Grid+OTT**: Grid trading ile OTT indikatörü kombinasyonu
- **DCA+OTT**: Dollar Cost Averaging ile OTT indikatörü kombinasyonu

### **DCA+OTT Strateji Kuralları**
1. **OTT AL** verdiğinde → İlk alım yapılır
2. **OTT SAT** verdiğinde → Pozisyon yoksa satış yapılmaz
3. **DCA Alım**: Fiyat düştüğünde ek alımlar yapılır
4. **Karlı Satış**: Ortalama maliyetin üstünde satış yapılır

### **DCA+OTT Döngü Sistemi**
- **Döngü Başlangıcı**: İlk alım ile döngü sayısı artırılır (D0 → D1)
- **Döngü İçi İşlemler**: Her işlemde işlem sayacı artırılır (D1-1, D1-2, D1-3...)
- **Döngü Tamamlanması**: Tam satış (tüm pozisyonlar satıldığında) sonrası döngü sıfırlanır (D1 → D0)
- **Döngü Takibi**: Dashboard'da mevcut döngü ve işlem sayısı gösterilir
- **Log Mesajları**: Tüm işlemlerde döngü ve işlem sayısı loglanır

#### **Döngü Örnekleri:**
- **D0**: Başlangıç durumu, henüz işlem yok
- **D1-1**: İlk döngü, ilk alım
- **D1-2**: İlk döngü, ikinci alım (DCA)
- **D1-3**: İlk döngü, kısmi satış
- **D1-4**: İlk döngü, üçüncü alım (DCA)
- **D1 (TAMAMLANDI)**: İlk döngü, tam satış
- **D2-1**: İkinci döngü, ilk alım
- Ve böyle devam eder...

---

## 🚀 **Kurulum**

```bash
# Sanal çevre oluştur
python -m venv venv

# Sanal çevreyi aktifleştir (Windows)
venv\Scripts\activate

# Bağımlılıkları yükle
pip install -r requirements.txt
```

## ▶️ **Çalıştırma**

```bash
# Ana uygulamayı başlat
python app.py

# Web arayüzü: http://localhost:8000
```

### **Development vs Production**

**Development (Geliştirme):**
```bash
uvicorn app:app --reload
```
- ✅ Dosya değişikliklerinde otomatik restart
- ⚠️ Her .py dosyası değişince yeniden başlar
- 🔄 Log'da restart mesajları görünür

**Production (Üretim):**
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```
- ✅ Kararlı çalışma, restart yok
- ✅ Emir takibi kesintisiz
- ✅ Trading için idealdir

---

## 🔌 **API Endpoints**

### **Debug ve Monitoring**
```bash
# Tüm stratejiler monitoring
GET /api/debug/strategies

# Belirli strateji diagnostics
GET /api/debug/strategy/{strategy_id}

# Debug monitoring enable/disable
POST /api/debug/enable
POST /api/debug/disable

# Otomatik durdurma yönetimi
POST /api/debug/auto-stop/enable
POST /api/debug/auto-stop/disable
GET /api/debug/auto-stop/status
POST /api/debug/auto-stop/configure

# State recovery sistemi
POST /api/recovery/validate-all
POST /api/recovery/strategy/{strategy_id}
```

### **Pozisyon Yönetimi**
```bash
# Pozisyon bilgileri
GET /api/positions

# Pozisyon limitlerini güncelle
POST /api/positions/limits
```

### **Trading Kontrol**
```bash
# Trading durumu
GET /api/trading/status

# Trading bekletme/devam ettirme
POST /api/trading/pause
POST /api/trading/resume
```

### **Strateji Yönetimi**
```bash
# Tüm stratejiler
GET /api/strategies

# Strateji oluştur
POST /api/strategies

# Strateji güncelle
PUT /api/strategies/{strategy_id}

# Strateji sil
DELETE /api/strategies/{strategy_id}

# Strateji başlat/durdur
POST /api/strategies/{strategy_id}/start
POST /api/strategies/{strategy_id}/stop
```

### **Log Yönetimi**
```bash
# Log dosyaları hakkında bilgi
GET /api/logs/info

# Eski log dosyalarını temizle (30 günden eski)
POST /api/logs/cleanup?days_to_keep=30

# Güncel log dosyasının son 100 satırını al
GET /api/logs/current
```

---

## ⚙️ **Konfigürasyon**

`.env` dosyasını `env.example` dosyasından kopyalayın ve API anahtarlarınızı ekleyin:

```env
# Binance API Ayarları
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_api_secret_here

# Testnet kullanımı (true/false)
USE_TESTNET=false

# HTTP Server Ayarları  
HTTP_PORT=8000
HTTP_HOST=0.0.0.0

# Log Ayarları
LOG_LEVEL=INFO
LOG_MAX_BYTES=1048576
LOG_BACKUP_COUNT=3

# Günlük Log Dosyaları (YYYYMMDD-app.log formatında)
# Otomatik olarak her gün yeni log dosyası oluşturulur
# 30 günden eski log dosyaları otomatik temizlenir

# Terminal Temizleme Ayarları (saniye cinsinden)
TERMINAL_CLEAR_INTERVAL=300

# Debug Ayarları
DCA_DEBUG_ENABLED=false

# Güvenlik (üretim için)
SECRET_KEY=your_secret_key_here
```

---

## 📊 **Strateji Yönetimi**

### **Yeni Strateji Ekleme**
1. Web arayüzünden strateji türünü seçin
2. Parametreleri ayarlayın
3. Stratejiyi başlatın

### **Strateji İzleme**
- Web arayüzünden tüm stratejileri görüntüleyin
- Detay sayfasından emir ve trade geçmişini inceleyin
- Telegram bildirimleri ile anlık durum takibi

### **Debug ve Monitoring**
```bash
# Professional debug script
python debug_tasks.py

# Strateji durum kontrolü
python status.py
```

---

## 🔧 **Sorun Giderme**

### **JSON Serialization Hatası**
Eğer "Object of type datetime is not JSON serializable" hatası alırsanız:
- Bu hata artık düzeltildi
- State kaydetme sırasında tüm datetime objeleri ISO string formatına çevriliyor

### **Strateji Emir Göndermiyor**
1. OTT modunu kontrol edin (AL/SAT)
2. Açık emirlerin olup olmadığını kontrol edin
3. Fiyat limitlerini kontrol edin
4. Minimum USDT tutarını kontrol edin

### **DCA+OTT Debug Sistemi**
Debug sistemi aktif olduğunda aşağıdaki detaylı logları görebilirsiniz:

#### **Debug Log Örnekleri:**
```
[DCA+OTT DEBUG] 80aa9fea | 15:17:15.050 | 🔍 Açık emir kontrolü: 0 emir
[DCA+OTT DEBUG] 80aa9fea | 15:17:15.051 | ✅ Açık emir yok - yeni emir gönderilebilir
[DCA+OTT DEBUG] 80aa9fea | 15:17:15.059 | 📊 Pozisyon Analizi:
[DCA+OTT DEBUG] 80aa9fea | 15:17:15.060 |   💰 Pozisyon var: False
[DCA+OTT DEBUG] 80aa9fea | 15:17:15.066 | 🎯 OTT Analizi:
[DCA+OTT DEBUG] 80aa9fea | 15:17:15.067 |   🔄 OTT Modu: AL
[DCA+OTT DEBUG] 80aa9fea | 15:17:15.076 | ✅ İlk alım sinyali onaylandı: 1.0 @ $24.58
```

#### **Debug Sistemi Özellikleri:**
- **Açık Emir Kontrolü**: Açık emir varken yeni emir gönderilmesini engeller
- **Pozisyon Analizi**: Mevcut pozisyonların detaylı analizi
- **OTT Analizi**: OTT modu ve fiyat farkları
- **DCA Parametreleri**: Strateji parametrelerinin kontrolü
- **Sinyal Kararları**: Alım/satım kararlarının detaylı açıklaması
- **Fill İşlemleri**: Emir gerçekleşme süreçlerinin takibi

#### **Debug Modunu Aktifleştirme:**
```python
# Environment variable ile
DCA_DEBUG_ENABLED=true

# Veya strateji handler'ında
handler = engine.get_strategy_handler(StrategyType.DCA_OTT)
handler.debug_enabled = True
```

### **Market Emir Desteği**
DCA+OTT stratejisinde market emir kullanımı ile daha hızlı işlem gerçekleştirme:

#### **Market Emir Avantajları:**
- **Hızlı Gerçekleşme**: Emirler anında gerçekleşir
- **Zamanlama**: DCA stratejisinde kritik olan zamanlama avantajı
- **Slippage Kontrolü**: Küçük miktarlarda slippage riski düşük
- **Likidite**: Yüksek likidite ile emirler hemen doldurulur

#### **Market Emir Kullanımı:**
```python
# State'de market emir ayarı
state.custom_data["use_market_orders"] = True  # Market emir aktif
state.custom_data["use_market_orders"] = False # Limit emir aktif
```

#### **Debug Log Örnekleri:**
```
[DCA+OTT DEBUG] 80aa9fea | 15:26:39.181 | 🚀 Market emir: ✅ Aktif
[DCA+OTT DEBUG] 80aa9fea | 15:26:39.182 | ✅ İlk alım sinyali onaylandı: 1.0 @ $24.58 (MARKET)
[DCA+OTT DEBUG] 80aa9fea | 15:26:39.183 | ✅ SİNYAL ONAYLANDI: BUY 1.0 @ None
```

#### **Telegram Bildirimleri:**
- Market emirler için 🚀 emoji
- Limit emirler için ⏳ emoji
- Fiyat bilgisi market emirlerde "Market" olarak gösterilir

---

## 🖥️ **Terminal Temizleme Sistemi**

### **Otomatik Temizleme**
- **Zaman Bazlı**: Varsayılan olarak 5 dakikada bir terminal temizlenir
- **Satır Sayısı Bazlı**: 1000 satır aşıldığında otomatik temizleme
- **Ayarlanabilir**: `TERMINAL_CLEAR_INTERVAL` ile süre değiştirilebilir

### **Manuel Temizleme**
- **Dashboard Butonu**: Web arayüzünden "Terminal Temizle" butonu
- **API Endpoint**: `POST /api/terminal/clear` ile programatik temizleme

### **Konfigürasyon**
```env
# 5 dakika (300 saniye) - varsayılan
TERMINAL_CLEAR_INTERVAL=300

# 2 dakika
TERMINAL_CLEAR_INTERVAL=120

# 10 dakika
TERMINAL_CLEAR_INTERVAL=600
```

---

## 📝 **Loglar**

### **Uygulama Logları**
Loglar `logs/app.log` dosyasında tutulur. Hata ayıklama için bu dosyayı kontrol edin.

#### **Binance Alış Veriş Logları**
**ÖNEMLİ**: Tüm Binance alış veriş işlemleri (market order, limit order, cancel order vb.) LOG_LEVEL ayarından bağımsız olarak her zaman hem terminale hem de `logs/app.log` dosyasına yazılır. Bu loglar `[BINANCE-BUY]`, `[BINANCE-SELL]`, `[BINANCE-CANCEL]` formatında görünür.

### **Emir Logları**
Tüm emir işlemleri `data/order_logs.csv` dosyasında detaylı olarak tutulur:

#### **Log Alanları:**
- **timestamp**: Emir zamanı (UTC)
- **strategy_id**: Strateji ID'si
- **strategy_type**: Strateji türü (GRID_OTT, DCA_OTT)
- **order_id**: Binance emir ID'si
- **symbol**: Trading çifti (BTCUSDT, ETHUSDT)
- **side**: İşlem yönü (buy/sell)
- **order_type**: Emir türü (market/limit)
- **quantity**: Miktar
- **price**: Market emirlerde gerçekleşen fiyat
- **limit_price**: Limit emirlerde hedef fiyat
- **status**: Emir durumu (sent, received, filled, cancelled, error)
- **action**: İşlem türü (create, cancel, check, fill)
- **message**: Açıklayıcı mesaj
- **error**: Hata mesajı (varsa)
- **execution_time_ms**: İşlem süresi (milisaniye)
- **grid_level**: Grid kademesi (grid stratejiler için)
- **notional**: USDT tutarı

#### **Log Örnekleri:**
```csv
timestamp,strategy_id,strategy_type,order_id,symbol,side,order_type,quantity,price,limit_price,status,action,message,error,execution_time_ms,grid_level,notional
2025-08-27T23:38:18.663734+00:00,7bba0875,GRID_OTT,12345,BTCUSDT,buy,limit,0.001,,50000.0,sent,create,Limit emir oluşturuldu: BTCUSDT buy 0.001 @ 50000.0,,150,3,50.0
2025-08-27T23:38:20.123456+00:00,7bba0875,GRID_OTT,12345,BTCUSDT,buy,limit,0.001,50001.2,50000.0,filled,fill,Emir dolduruldu: 12345 - 0.001 @ 50001.2,,200,3,50.012
```

### **Rotating Log Dosyaları**
- **Maksimum Boyut**: 1MB (ayarlanabilir)
- **Yedek Dosyalar**: 3 adet (ayarlanabilir)
- **Otomatik Döndürme**: Boyut aşıldığında otomatik olarak yeni dosya oluşturulur

### **Log Yönetimi**
- **Manuel Temizleme**: Dashboard'dan "Log Temizle" butonu ile
- **Otomatik Yedekleme**: Temizleme sırasında eski loglar yedeklenir
- **Debug Modu**: `DCA_DEBUG_ENABLED=true` ile detaylı loglar açılabilir
- **Log Seviyesi**: `LOG_LEVEL=WARNING` ile sadece önemli loglar kaydedilir
- **Binance İşlemleri**: Binance alış veriş işlemleri LOG_LEVEL'dan bağımsız olarak her zaman loglanır

---

## 🛡️ **Güvenlik Özellikleri**

### **Universal Debug Monitor**
- **State Corruption Tespiti**: Pozisyon kaybı ve tutarsızlık otomatik tespiti
- **Trade Mantık Doğrulama**: Yanlış trade'lerin otomatik tespiti ve engellenmesi
- **Otomatik Strateji Durdurma**: Kritik sorunlarda otomatik güvenlik müdahalesi
- **Telegram Error Bildirimleri**: Error ve Critical seviyeli sorunların anında bildirimi

### **Risk Yönetimi**
- **Net Pozisyon Takibi**: Binance hesabı pozisyon takibi
- **Pozisyon Limitleri**: Maksimum ve minimum pozisyon limitleri
- **Emir Öncesi Risk Kontrolü**: Limit aşımında otomatik emir iptali
- **Hata Sayacı**: 3 hata sonrası otomatik strateji durdurma

### **State Recovery**
- **Otomatik Pozisyon Kurtarma**: Trade history'den state rebuild
- **Validation API'leri**: Tüm stratejiler için otomatik validation
- **Manuel Recovery**: API ile manuel recovery tetiklenebilir

---

## 📈 **Performans İzleme**

### **Dashboard Metrikleri**
- **Strateji Durumu**: Aktif/Pasif
- **Pozisyon Bilgileri**: Miktar, ortalama maliyet
- **Kar/Zarar**: Gerçekleşmemiş kâr/zarar
- **Döngü Bilgileri**: Mevcut döngü ve işlem sayısı
- **OTT Durumu**: AL/SAT modu
- **Açık Emirler**: Gerçek zamanlı emir takibi
- **Net Pozisyon**: Risk durumu ve pozisyon analizi

### **Monitoring Araçları**
- **Professional Debug Script**: `python debug_tasks.py`
- **Strateji Durum Kontrolü**: `python status.py`
- **Web Dashboard**: Real-time monitoring
- **Telegram Bildirimleri**: Anlık durum takibi

---

## 🚀 **Gelecek Geliştirmeler**

### **Planlanan Özellikler**
1. **Çoklu Sembol Desteği**: Aynı anda birden fazla trading çifti
2. **Gelişmiş Risk Yönetimi**: Stop-loss ve take-profit
3. **Backtest Sistemi**: Geçmiş verilerle strateji testi
4. **Portföy Yönetimi**: Toplam portföy görünümü
5. **Mobil Uygulama**: Telefon uygulaması

### **Optimizasyonlar**
1. **Performans İyileştirmeleri**: Daha hızlı işlem
2. **Bellek Optimizasyonu**: Daha az RAM kullanımı
3. **API Limit Optimizasyonu**: Daha verimli API kullanımı
4. **Hata Toleransı**: Daha güçlü hata yönetimi

---

## 🤝 **Katkıda Bulunma**

1. Fork yapın
2. Feature branch oluşturun
3. Değişikliklerinizi commit edin
4. Pull request gönderin

---

## 📄 **Lisans**

Bu proje MIT lisansı altında lisanslanmıştır.

---

**Son Güncelleme:** 23 Eylül 2025  
**Versiyon:** 2.2.0  
**Geliştirici:** YLMZ Trading Systems