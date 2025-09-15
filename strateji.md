# Trading Stratejileri Dokümantasyonu

## 🛡️ **GÜVENLİK VE MONİTORİNG SİSTEMİ (6 Eylül 2025)**

### **Universal Debug Monitor Sistemi**

**Tüm Strateji Türleri İçin Profesyonel Monitoring:**
- ✅ **DCA+OTT**: State corruption, pozisyon tutarlılık, döngü mantığı
- ✅ **Grid+OTT**: GF kontrolü, grid parametreleri, hızlı trade tespiti
- ✅ **Genel**: OTT parametreleri, state güncelleme, aktiflik kontrolü

**Otomatik Güvenlik Müdahaleleri:**
- 🚨 **Kritik Sorunlar**: State corruption → Anında durdur
- ❌ **Çoklu Error**: 3+ error birikimi → Durdur
- 🔄 **DCA Kural İhlali**: Yanlış alım pattern'i → Durdur
- ⚡ **Grid Anomali**: Şüpheli trade pattern'leri → Uyar
- 📱 **Telegram Alert**: Error/Critical → Anında bildir

**Monitoring API'leri:**
```bash
GET /api/debug/strategies          # Tüm stratejiler
GET /api/debug/strategy/{id}       # Detaylı diagnostics
POST /api/debug/auto-stop/enable   # Güvenlik sistemi aktif
```

**Debug Script:**
```bash
python debug_tasks.py  # Professional monitoring
```

### **State Recovery Sistemi**

**Otomatik Pozisyon Kurtarma:**
- Trade history'den state'leri yeniden inşa eder
- DCA pozisyon kaybı durumlarını düzeltir
- Tüm stratejiler için otomatik validation
- API ile manuel recovery tetiklenebilir

**Recovery API'leri:**
```bash
POST /api/recovery/validate-all        # Tüm stratejileri kontrol et
POST /api/recovery/strategy/{id}       # Belirli strateji recover et
```

**Ne Zaman Gerekir:**
- Pozisyon kaybı tespit edildiğinde
- State corruption uyarılarında  
- Trade-State tutarsızlığı durumlarında
- Geliştirme sonrası migration'larda

### **Telegram Retry ve Otomatik Strateji Durdurma Sistemi**

**Yeni Güvenlik Özelliği:**
- ✅ **3 Deneme Retry** - Telegram mesajları için otomatik retry mekanizması
- ✅ **30 Saniye Bekleme** - Her deneme arasında ağ bağlantısı için bekleme
- ✅ **Otomatik Durdurma** - Telegram mesajı gönderilemezse strateji durdurulur
- ✅ **Güvenlik Önceliği** - Telegram bağlantısı olmadan trading yapılmaz
- ✅ **Detaylı Loglama** - Her deneme ayrı ayrı loglanır

**Çalışma Mantığı:**
1. **1. Deneme** - Telegram mesajı gönderilmeye çalışılır
2. **Başarısızlık** - 30 saniye beklenir, log yazılır
3. **2. Deneme** - Tekrar gönderilmeye çalışılır
4. **Başarısızlık** - 30 saniye beklenir, log yazılır
5. **3. Deneme** - Son deneme yapılır
6. **Başarısızlık** - Strateji otomatik durdurulur

**Log Mesajları:**
```
Telegram mesajı gönderilemedi, 30 saniye sonra tekrar denenecek... (deneme 1/3)
Telegram mesajı gönderilemedi, 30 saniye sonra tekrar denenecek... (deneme 2/3)
Telegram mesajı 3 deneme sonunda gönderilemedi - strateji durdurulacak!
🚨 TELEGRAM MESAJI BAŞARISIZ - Strateji durduruluyor: {strategy_id}
```

---

## ♻️ DÜZELTME: BOL-Grid Precision & Min Notional (9 Eylül 2025)

- **Precision düzeltmesi**: BOL-Grid stratejisinde `MarketInfo.quantity_precision` alanı yerine `step_size` ve `min_qty` kullanımı standart hale getirildi.
- **Min notional kontrolü**: Alım ve kısmi satışta `min_notional` doğrulaması eklendi.
- **Kısmi satış miktarı**: `step_size`'a göre aşağı yuvarlama ve alt limit doğrulamaları ile güvence altına alındı.

## 🔧 **SON GÜNCELLEMELER (3 Eylül 2025)**

### **YENİ ÖZELLİK: Binance İşlemleri Zorunlu Loglama**

**Eklenen Özellikler:**
- ✅ **LOG_LEVEL Bağımsız Loglama** - Binance alış veriş işlemleri LOG_LEVEL ayarından bağımsız loglanır
- ✅ **Özel Binance Logger** - `binance_trading` logger'ı ile ayrı loglama sistemi
- ✅ **Terminal + Dosya Yazımı** - Hem terminal hem de `logs/app.log` dosyasına eş zamanlı yazım
- ✅ **Tüm İşlem Tipleri** - Market order, limit order, cancel order tüm işlemler loglanır
- ✅ **Hata Logları** - Binance işlem hataları da zorunlu olarak loglanır

**Teknik Detaylar:**
- `core/utils.py`'de `setup_binance_trading_logger()` fonksiyonu eklendi
- `log_binance_trading_action()` fonksiyonu ile özel loglama
- `_log_order_action()` metodu güncellenererek otomatik Binance loglama eklendi
- Log formatı: `[BINANCE-BUY]`, `[BINANCE-SELL]`, `[BINANCE-CANCEL]`, `[BINANCE-ERROR]`
- Logger propagation kapalı olarak ana logger'dan bağımsız çalışıyor

**Güvenlik Özellikleri:**
- LOG_LEVEL=ERROR olsa bile Binance işlemleri loglanır
- Dosya yazım hatalarında bile terminal çıktısı devam eder
- Binance işlemlerinde tam şeffaflık sağlanır

---

### **YENİ ÖZELLİK: Dashboard Açık Emirler Alanı**

**Eklenen Özellikler:**
- ✅ **Açık Emirler Tablosu** - Son işlemler tablosunun üstünde özel alan
- ✅ **Detaylı Emir Bilgileri** - Strateji adı, sembol, işlem yönü, miktar, fiyat
- ✅ **Emir Tipi Göstergesi** - Limit/Market emir türü görsel olarak belirtiliyor
- ✅ **Gerçek Zamanlı Durum** - Binance'den güncel emir durumu alınıyor
- ✅ **Grid Z Bilgisi** - Grid stratejiler için kademe bilgisi
- ✅ **Zaman Bilgisi** - Emir oluşturulma tarihi ve saati

**Gösterilen Bilgiler:**
- **Strateji Adı**: Tıklanabilir link ile strateji detayına gidiş
- **Sembol**: Trading çifti (BTCUSDT, ETHUSDT vb.)
- **İşlem**: 🟢 AL / 🔴 SAT göstergesi
- **Miktar**: Emir miktarı (6 ondalık basamak)
- **Fiyat**: Limit emir fiyatı veya "Market" göstergesi
- **Emir Tipi**: 📋 Limit / ⚡ Market badge'leri
- **Emir Durumu**: Doldurulma yüzdesi ve miktar bilgisi
- **Grid Z**: Grid kademesi (varsa)
- **Zaman**: Emir oluşturulma tarihi ve saati

---

### **YENİ ÖZELLİK: Hata Durumunda Otomatik Strateji Durdurma Sistemi**

**Eklenen Özellikler:**
- ✅ **Otomatik Hata Sayacı** - Her strateji için hata sayısı takibi
- ✅ **Maksimum Hata Limiti** - 3 hata sonrası strateji otomatik durdurulur
- ✅ **Güvenli Durdurma** - Hata durumunda strateji storage'da da pasif yapılır
- ✅ **Dashboard Görselleştirme** - Pasif stratejiler turuncu satırla gösterilir
- ✅ **Hata Sayısı Göstergesi** - Aktif stratejilerde hata sayısı görüntülenir

**Teknik Detaylar:**
- `strategy_engine.py`'de `error_counts` sözlüğü eklendi
- `increment_error_count()` metodu ile hata sayacı artırılıyor
- `reset_error_count()` metodu ile başarılı işlem sonrası sayaç sıfırlanıyor
- Dashboard'da pasif stratejiler `bg-orange-50` ve `border-orange-400` ile vurgulanıyor
- Hata sayısı 3'e ulaştığında strateji otomatik olarak durduruluyor

**Güvenlik Özellikleri:**
- Defalarca emir gönderimi engelleniyor
- Hata durumunda strateji loop'u güvenli şekilde sonlanıyor
- Storage'da strateji durumu senkronize ediliyor
- Telegram bildirimleri ile kritik durumlar raporlanıyor

---

### **DÜZELTME: Order Fill Kontrol Hatası ve Bilinmeyen Satış Türü Sorunu**

**Çözülen Sorunlar:**
- ✅ **Order Fill Kontrol Hatası** - `unsupported format string passed to NoneType.__format__` hatası çözüldü
- ✅ **Bilinmeyen Satış Türü** - DCA+OTT stratejisinde `sell_type: unknown` sorunu çözüldü
- ✅ **Strategy Specific Data Aktarımı** - Trade objelerine strategy özel verilerinin aktarımı düzeltildi

**Teknik Detaylar:**
- `strategy_engine.py`'de `check_order_fills` fonksiyonunda `strategy` parametresi `None` kontrolü eklendi
- `OpenOrder` ve `Trade` modellerine `strategy_specific_data` alanı eklendi
- `binance.py`'de `check_order_fills` fonksiyonunda `strategy_specific_data` alanı dolduruldu
- Emir oluştururken `strategy_specific_data` alanının `OpenOrder` objesine aktarımı sağlandı
- Trade oluştururken `strategy_specific_data` alanının `OpenOrder`'dan alınması sağlandı

**Sonuç:**
- DCA+OTT stratejisinde satış türü artık doğru şekilde belirleniyor
- Order fill kontrol hataları ortadan kalktı
- Strategy özel verileri trade kayıtlarında korunuyor

---

### **YENİ ÖZELLİK: Strateji Task Debug Script**

**Eklenen Özellikler:**
- ✅ **Debug Script** - `debug_tasks.py` ile strateji task'larının sürekli kontrolü
- ✅ **5 Dakikalık Kontrol** - Tüm stratejilerin durumunu 5 dakikada bir kontrol eder
- ✅ **Detaylı Sinyal Analizi** - Her strateji için sinyal testi ve emir oluşturma durumu
- ✅ **Gerçek Zamanlı Takip** - Strateji task'larının çalışıp çalışmadığını anlık takip
- ✅ **Sorun Tespiti** - b90f9f87 stratejisinde miktar hesaplama sorunu tespit edildi

**Kullanım:**
```bash
python debug_tasks.py
```

**Tespit Edilen Sorunlar:**
- **b90f9f87 (btc5m):** USDT/Grid miktarı ($100) çok düşük, minimum miktar hesaplaması başarısız
- **Çözüm:** USDT/Grid miktarını $110.88'den yüksek yapmak gerekiyor

### **DÜZELTME: Dashboard Son İşlemler Duplicate Sorunu**

**Çözülen Sorun:**
- ✅ **Duplicate Trade Gösterimi** - Dashboard'da aynı emir ID'sinin 2 defa görünmesi sorunu çözüldü
- ✅ **Backend Duplicate Kontrolü** - `load_all_trades` fonksiyonunda unique key kontrolü eklendi
- ✅ **Frontend Duplicate Kontrolü** - Real-time updates'te daha iyi duplicate kontrolü eklendi
- ✅ **Trade ID Sistemi** - Her trade için benzersiz ID oluşturma sistemi iyileştirildi

**Teknik Detaylar:**
- Backend'de `timestamp + strategy_id + side + price + quantity + order_id` kombinasyonu ile unique key oluşturuluyor
- Frontend'de mevcut trade ID'leri Set ile takip ediliyor
- Real-time updates sadece gerçekten yeni trade'ler için tabloyu güncelliyor
- Console'da yeni trade sayısı loglanıyor

### **YENİ ÖZELLİK: Trading Bekletme Sistemi**

**Eklenen Özellikler:**
- ✅ **Trading Bekletme Düğmesi** - Dashboard'da trading işlemlerini bekletme/devam ettirme
- ✅ **Gerçek Zamanlı Durum Göstergesi** - Trading durumunu anlık takip etme
- ✅ **Strateji Yönetimi** - Bekletme sırasında strateji ekleme/düzenleme imkanı
- ✅ **Güvenli Bekletme** - Mevcut pozisyonları koruyarak sadece yeni işlemleri durdurma

**Kullanım:**
- Dashboard'da "Trading Beklet" düğmesine basarak trading işlemlerini durdurabilirsiniz
- "Trading Devam Et" düğmesi ile işlemleri tekrar başlatabilirsiniz
- Bekletme sırasında strateji ekleyebilir, düzenleyebilir veya silebilirsiniz
- Trading durumu kartında anlık durumu görebilirsiniz

**Teknik Detaylar:**
- Background task manager'da `paused` durumu eklendi
- Coordinator loop'u bekletme durumunda sadece bekleme yapar
- Mevcut strateji task'ları çalışmaya devam eder (güvenli bekletme)
- API endpoint'leri: `/api/trading/pause`, `/api/trading/resume`, `/api/trading/status`

---

### **KRİTİK DÜZELTME: afb5f1c4 Strateji Sorunu**

**Sorun:** `afb5f1c4` ID'li DCA+OTT stratejisinde aynı pozisyonun defalarca satılmaya çalışılması sorunu yaşanıyordu.

**Tespit Edilen Sorunlar:**
1. **Açık emir kontrolü başarısız oluyordu** - State'de açık emir var ama sistem bunu görmüyordu
2. **Fill işlemi düzgün çalışmıyordu** - Satış gerçekleşiyor ama state güncellenmiyordu
3. **sell_type bilgisi aktarılmıyordu** - Trade objesine strategy_specific_data doğru aktarılmıyordu

**Yapılan Düzeltmeler:**
- ✅ **Fill işlemi güçlendirildi** - sell_type bilgisi daha güvenli şekilde alınıyor
- ✅ **Strategy engine düzeltildi** - Trade objesine strategy_specific_data aktarımı eklendi
- ✅ **Açık emir kontrolü güçlendirildi** - Daha sıkı kontrol mekanizması
- ✅ **State tutarlılığı sağlandı** - Pozisyon ve emir durumları senkronize edildi
- ✅ **Manuel state düzeltmesi** - afb5f1c4 stratejisinin state dosyası temizlendi

**Sonuç:** Strateji artık düzgün çalışacak ve aynı pozisyonun defalarca satılması sorunu çözülecek.

---

## 📋 **Strateji Türleri**

### **1. Grid+OTT Strateji**
Grid trading ile OTT (Optimized Trend Tracker) indikatörünün kombinasyonu.

### **2. DCA+OTT Strateji**
Dollar Cost Averaging (DCA) ile OTT indikatörünün kombinasyonu.

---

## 🔄 **DCA+OTT Strateji Detayları**

### **Strateji Mantığı**
DCA+OTT stratejisi, düşen fiyatlarda artan alım yaparak ortalama maliyeti düşürmeyi ve OTT indikatörü ile trend takibi yapmayı hedefler.

### **Alım Kuralları**
1. **OTT AL** verdiğinde → İlk alım yapılır
2. **DCA Alım**: Fiyat düştüğünde ek alımlar yapılır
3. **DCA Miktarı**: `base_usdt × (dca_multiplier ^ pozisyon_sayısı)`
4. **Minimum Düşüş**: `min_drop_pct` kadar düşüş olmalı

### **Satış Kuralları**
1. **Kısmi Satış**: OTT SAT verdiğinde, fiyat son alım fiyatının %1 üzerindeyse → sadece son pozisyonu sat
2. **Tam Satış**: OTT SAT verdiğinde, fiyat ortalama maliyetin %1 üzerindeyse → tüm pozisyonu sat
3. **Tam Satış Sonrası**: Yeni döngü başlar (state sıfırlanır)

### **Döngü Sistemi**
- **Döngü Başlangıcı**: İlk alım ile döngü sayısı artırılır (D0 → D1)
- **Döngü İçi İşlemler**: Her işlemde işlem sayacı artırılır (D1-1, D1-2, D1-3...)
- **Döngü Tamamlanması**: Tam satış sonrası döngü sıfırlanır (D1 → D0)

#### **Döngü Örnekleri:**
- **D0**: Başlangıç durumu, henüz işlem yok
- **D1-1**: İlk döngü, ilk alım
- **D1-2**: İlk döngü, ikinci alım (DCA)
- **D1-3**: İlk döngü, kısmi satış
- **D1-4**: İlk döngü, üçüncü alım (DCA)
- **D1 (TAMAMLANDI)**: İlk döngü, tam satış
- **D2-1**: İkinci döngü, ilk alım

### **Parametreler**
- **base_usdt**: İlk alım tutarı (USDT)
- **dca_multiplier**: DCA çarpanı (varsayılan: 1.5)
- **min_drop_pct**: Minimum düşüş yüzdesi (varsayılan: 2.0%)
- **use_market_orders**: Market emir kullanımı (varsayılan: true)

### **Debug Sistemi**
Debug modu aktif olduğunda (`DCA_DEBUG_ENABLED=true`) aşağıdaki detaylı logları görebilirsiniz:

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

---

## 📊 **Grid+OTT Strateji Detayları**

### **Strateji Mantığı**
Grid+OTT stratejisi, belirli fiyat aralıklarında alım-satım yaparak ve OTT indikatörü ile trend yönünü belirleyerek kâr elde etmeyi hedefler.

### **Grid Sistemi**
- **GF (Grid Foundation)**: Grid'in merkez fiyatı
- **Y**: Grid aralığı (fiyat farkı)
- **Z**: Grid seviyesi (pozitif: üst grid, negatif: alt grid)
- **USDT Grid**: Her grid seviyesindeki USDT tutarı

### **Alım Kuralları**
1. **OTT AL** verdiğinde → Alt gridlerde alım yapılır
2. **Grid Seviyesi**: Fiyat GF'nin altındaki grid seviyelerinde alım
3. **Miktar Hesaplama**: `usdt_grid / current_price`

### **Satış Kuralları**
1. **OTT SAT** verdiğinde → Üst gridlerde satış yapılır
2. **Grid Seviyesi**: Fiyat GF'nin üstündeki grid seviyelerinde satış
3. **Kâr Hesaplama**: Grid seviyesi farkı × miktar

### **Parametreler**
- **y**: Grid aralığı (fiyat farkı)
- **usdt_grid**: Her grid seviyesindeki USDT tutarı
- **gf**: Grid Foundation (otomatik ayarlanır)

---

## 🔧 **Teknik Detaylar**

### **OTT (Optimized Trend Tracker)**
OTT indikatörü, trend yönünü belirlemek için kullanılır:
- **OTT AL**: Fiyat baseline'ın üzerinde, yükseliş trendi
- **OTT SAT**: Fiyat baseline'ın altında, düşüş trendi

### **State Yönetimi**
Her strateji için ayrı state dosyası tutulur:
- **Pozisyon bilgileri**: Alım fiyatları, miktarlar
- **Grid bilgileri**: GF, grid seviyeleri
- **Döngü bilgileri**: Döngü sayısı, işlem sayacı
- **Açık emirler**: Bekleyen emirler

### **Emir Yönetimi**
- **Market Emirler**: Hızlı işlem için
- **Limit Emirler**: Belirli fiyattan işlem için
- **Timeout Kontrolü**: Belirli süre sonra emir iptali
- **Batch İptal**: Toplu emir iptali

### **Hata Yönetimi**
- **Açık Emir Kontrolü**: Açık emir varken yeni emir engelleme
- **Fiyat Limitleri**: Aşırı fiyatları engelleme
- **State Tutarlılığı**: Pozisyon ve emir durumlarının senkronizasyonu
- **Güvenli Satış**: Bilinmeyen durumlar için varsayılan davranış

---

## 📈 **Performans İzleme**

### **Dashboard Metrikleri**
- **Strateji Durumu**: Aktif/Pasif
- **Pozisyon Bilgileri**: Miktar, ortalama maliyet
- **Kar/Zarar**: Gerçekleşmemiş kâr/zarar
- **Döngü Bilgileri**: Mevcut döngü ve işlem sayısı
- **OTT Durumu**: AL/SAT modu

### **Log Sistemi**
- **Uygulama Logları**: `logs/app.log`
- **Emir Logları**: `data/order_logs.csv`
- **Debug Logları**: DCA+OTT özel logları
- **Trade Geçmişi**: `data/<strategy_id>/trades.csv`

---

## ⚠️ **Bilinen Sorunlar ve Çözümler**

### **afb5f1c4 Sorunu (ÇÖZÜLDÜ)**
- **Sorun:** Aynı pozisyon defalarca satılmaya çalışılıyordu
- **Çözüm:** Fill işlemi ve state yönetimi düzeltildi

### **Emir Timeout Sorunu**
- **Sorun:** Emirler zaman aşımına uğruyor
- **Çözüm:** Otomatik iptal mekanizması eklendi

### **JSON Serialization Hatası**
- **Sorun:** Datetime objeleri JSON'a çevrilemiyor
- **Çözüm:** Tüm datetime objeleri ISO string formatına çevriliyor

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

**Son Güncelleme:** 6 Eylül 2025  
**Versiyon:** 2.1.0  
**Geliştirici:** YLMZ Trading Systems