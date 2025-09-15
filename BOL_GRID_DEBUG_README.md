# BOL-Grid Detaylı Debug Sistemi

## 🎯 **Amaç**
BOL-Grid stratejisinin ilk aşamalarda doğru çalıştığını görmek ve tüm işlemleri detaylı olarak takip etmek için kapsamlı bir debug sistemi.

## 🔧 **Debug Özellikleri**

### **1. Otomatik Debug Modu**
- BOL-Grid stratejileri için debug modu **varsayılan olarak açık**
- Environment variables ile kontrol edilebilir:
  - `BOL_GRID_DEBUG_ENABLED=true` (varsayılan: true)
  - `BOL_GRID_DETAILED_DEBUG=true` (varsayılan: true)

### **2. Detaylı Log Sistemi**
- **Console Logs**: Ana uygulama loglarına BOL-Grid özel logları
- **Debug Log Dosyası**: `logs/bol_grid_debug_{strategy_id}.log`
- **Analiz JSON Dosyası**: `logs/bol_grid_analysis_{strategy_id}.json`

### **3. Log Kategorileri**

#### **📊 Sinyal Analizi**
- Bollinger Bands hesaplama detayları
- Fiyat pozisyonu analizi (üst/orta/alt band'a göre)
- Cross sinyal tespiti
- Pozisyon durumu ve kar/zarar analizi
- Sinyal karar süreci

#### **💰 Trade Execution**
- Fill işlemi öncesi/sonrası state
- Pozisyon güncellemeleri
- Ortalama maliyet hesaplamaları
- Döngü bilgisi güncellemeleri

#### **🔄 Döngü Geçişleri**
- Döngü başlangıçları (D0 → D1-1)
- Döngü kapanışları (D1-X → D0)
- Döngü içi geçişler (D1-1 → D1-2)

## 📁 **Debug Dosyaları**

### **Debug Log Dosyası** (`logs/bol_grid_debug_{strategy_id}.log`)
```
=== BOL-Grid Debug Log - {strategy_id} ===
Başlangıç: 2024-01-15T10:30:00.000Z
==================================================

[10:30:15.123] analysis
  💰 PRICE: 43250.500000 (vs bands: U:+2.15%, M:-0.85%, L:-3.25%)
  📊 POSITION: Qty=0.000000, Avg=0.000000, P&L=+0.00%
  🎯 SIGNAL: cross_above_lower
  ⚡ DECISION: first_buy - Alt band cross-above - İlk alım
--------------------------------------------------

[10:30:15.456] trade_execution
  🔄 TRADE: buy 0.002311 @ 43250.500000 (D1-1)
  📊 BEFORE: Cycle=D0, Qty=0.000000, Avg=0.000000
  📊 AFTER:  Cycle=D1-1, Qty=0.002311, Avg=43250.500000
--------------------------------------------------
```

### **Analiz JSON Dosyası** (`logs/bol_grid_analysis_{strategy_id}.json`)
```json
{
  "strategy_id": "abc123",
  "start_time": "2024-01-15T10:30:00.000Z",
  "last_update": "2024-01-15T10:35:00.000Z",
  "entries": [
    {
      "timestamp": "10:30:15.123",
      "price_analysis": {
        "current_price": 43250.5,
        "price_vs_upper_pct": 2.15,
        "price_vs_middle_pct": -0.85,
        "price_vs_lower_pct": -3.25,
        "band_width_pct": 5.4
      },
      "bollinger_bands": {
        "upper": 44180.2,
        "middle": 43620.8,
        "lower": 43061.4
      },
      "cross_signal": "cross_above_lower",
      "position_analysis": {
        "positions_count": 0,
        "total_quantity": 0,
        "total_value": 0,
        "average_cost": 0,
        "profit_loss": 0,
        "profit_pct": 0
      },
      "decision": {
        "action": "first_buy",
        "cycle_number": 1,
        "cycle_step": "D1-1",
        "quantity": 0.002311,
        "price": 43250.5,
        "usdt_amount": 100,
        "reason": "Alt band cross-above - İlk alım"
      }
    }
  ]
}
```

## 🌐 **Web API Endpoints**

### **Debug Bilgileri**
```
GET /api/strategies/{strategy_id}/bol-grid-debug
```
**Response:**
```json
{
  "strategy_id": "abc123",
  "strategy_name": "BTC BOL-Grid Test",
  "recent_analysis": [...],
  "cycle_summary": {
    "status": "active",
    "last_trade": {...},
    "last_analysis": {...},
    "total_entries": 150
  },
  "debug_files": {
    "debug_log": "logs/bol_grid_debug_abc123.log",
    "analysis_json": "logs/bol_grid_analysis_abc123.json"
  }
}
```

### **Debug Log İçeriği**
```
GET /api/strategies/{strategy_id}/bol-grid-debug/log
```
**Response:**
```json
{
  "content": "=== BOL-Grid Debug Log - abc123 ===\n..."
}
```

## 🔍 **Debug Analizi**

### **Sinyal Analizi Örnekleri**

#### **İlk Alım Sinyali**
```
[BOL-GRID DETAILED] abc123 | 10:30:15.123 | 💰 FIRST BUY DECISION
  action: first_buy
  cycle_number: 1
  cycle_step: D1-1
  quantity: 0.002311
  price: 43250.500000
  usdt_amount: 100.000000
  reason: Alt band cross-above - İlk alım
```

#### **Ek Alım Sinyali**
```
[BOL-GRID DETAILED] abc123 | 10:35:20.456 | 💰 ADDITIONAL BUY DECISION
  action: additional_buy
  cycle_number: 1
  cycle_step: D1-2
  quantity: 0.002311
  price: 42500.000000
  usdt_amount: 100.000000
  drop_pct: 1.73
  min_drop_required: 2.00
  average_cost: 43250.500000
  reason: Alt band cross-above + 1.73% düşüş
```

#### **Kısmi Satış Sinyali**
```
[BOL-GRID DETAILED] abc123 | 10:40:30.789 | 💰 PARTIAL SELL DECISION
  action: partial_sell
  cycle_number: 1
  cycle_step: D1-3
  quantity: 0.002311
  price: 43800.000000
  profit_pct: 1.27
  min_profit_required: 1.00
  average_cost: 43250.500000
  remaining_quantity: 0.002311
  remaining_value: 101.27
  threshold: 16.67
  reason: Orta/üst band cross-below + 1.27% kar
```

### **Fill İşlemi Analizi**

#### **Alım Fill İşlemi**
```
[BOL-GRID DETAILED] abc123 | 10:30:15.789 | 💰 POST-FILL STATE (BUY)
  action: buy_fill_processed
  new_state:
    cycle_number: 1
    cycle_step: D1-1
    cycle_trades: 1
    positions_count: 1
    total_quantity: 0.002311
    average_cost: 43250.500000
    last_buy_price: 43250.500000
  calculation:
    total_cost: 100.000000
    new_position:
      quantity: 0.002311
      price: 43250.500000
```

#### **Döngü Kapanış Fill İşlemi**
```
[BOL-GRID DETAILED] abc123 | 10:45:45.123 | 🔄 CYCLE CLOSE FILL PROCESSED
  action: cycle_close_fill_processed
  cycle_number: 1
  sold_quantity: 0.002311
  sell_price: 44000.000000
  new_state:
    cycle_number: 1
    cycle_step: D0
    cycle_trades: 0
    positions_count: 0
    total_quantity: 0.000000
    average_cost: 0.000000
    last_sell_price: 44000.000000
```

## 🚀 **Kullanım**

### **1. Strateji Oluşturma**
BOL-Grid stratejisi oluşturduğunuzda debug sistemi otomatik olarak aktif olur.

### **2. Debug Logları İzleme**
```bash
# Debug log dosyasını canlı izle
tail -f logs/bol_grid_debug_{strategy_id}.log

# Ana uygulama loglarında BOL-Grid loglarını filtrele
tail -f logs/app.log | grep "BOL-GRID"
```

### **3. Web API ile Debug Bilgileri**
```bash
# Debug bilgilerini getir
curl http://localhost:8000/api/strategies/{strategy_id}/bol-grid-debug

# Debug log içeriğini getir
curl http://localhost:8000/api/strategies/{strategy_id}/bol-grid-debug/log
```

### **4. Debug Modunu Kapatma**
```bash
# Environment variable ile kapat
export BOL_GRID_DEBUG_ENABLED=false
export BOL_GRID_DETAILED_DEBUG=false
```

## 📊 **Debug Metrikleri**

### **Takip Edilen Metrikler**
- **Bollinger Bands**: Upper, Middle, Lower değerleri
- **Fiyat Pozisyonu**: Her band'a göre yüzde farkı
- **Cross Sinyalleri**: Alt/orta/üst band geçişleri
- **Pozisyon Durumu**: Miktar, ortalama maliyet, kar/zarar
- **Döngü Bilgisi**: Döngü numarası, adım, işlem sayısı
- **Risk Metrikleri**: 1/6 kuralı, kalan pozisyon değeri

### **Performans Metrikleri**
- **Sinyal Tepki Süresi**: Cross tespitinden sinyal üretimine
- **Fill İşlem Süresi**: Trade execution süresi
- **State Güncelleme**: Pozisyon ve döngü güncelleme süresi

## ⚠️ **Önemli Notlar**

1. **Debug Dosyaları**: Her strateji için ayrı debug dosyası oluşturulur
2. **Dosya Boyutu**: Analiz JSON dosyası son 1000 entry'yi tutar
3. **Performans**: Debug modu açıkken minimal performans etkisi
4. **Güvenlik**: Debug dosyaları hassas bilgi içerebilir, güvenli tutun
5. **Temizlik**: Eski debug dosyalarını düzenli olarak temizleyin

## 🔧 **Sorun Giderme**

### **Debug Logları Görünmüyor**
- `BOL_GRID_DEBUG_ENABLED=true` kontrol edin
- `logs/` klasörünün yazma izni olduğundan emin olun
- Strateji ID'sinin doğru olduğunu kontrol edin

### **JSON Dosyası Bozuk**
- Dosyayı silin, yeniden oluşturulacak
- Disk alanı kontrol edin
- Dosya izinlerini kontrol edin

### **Web API Çalışmıyor**
- Strateji ID'sinin doğru olduğunu kontrol edin
- Strateji tipinin BOL-Grid olduğunu kontrol edin
- Uygulama loglarında hata mesajlarını kontrol edin

---

**BOL-Grid Debug Sistemi ile stratejinizin her adımını detaylı olarak takip edebilir ve doğru çalıştığından emin olabilirsiniz!** 🎯
