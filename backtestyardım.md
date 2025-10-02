# Backtest Yardım Dosyası - OTT Hesaplama Detayları

## OTT(20,2) Pine Script Kodu

```pinescript
// 20 periyot VIDYA (destek çizgisi) hesaplama
cmo = ta.cmo(close, 9)                          // 9 periyot CMO hesabı
alpha = 2.0 / (20 + 1)                          // EMA alpha değeri (20 periyot)
vma = 0.0                                       // VIDYA değişken ortalama
vma := nz(vma[1]) + alpha * math.abs(cmo) * (close - nz(vma[1]))

// Yüzde faktörü ve trailing stop hesaplama (factor=2)
factor = 2.0
offset = vma * factor / 100.0
longStop = vma - offset
shortStop = vma + offset
// ... (longStop/shortStop sadece trend yönünde güncellenir; trend flip kontrolü yapılır)

// OTT trend çizgisi hesaplama
ottLine = (dir == 1) ? longStop * (1 + factor/200) : shortStop * (1 - factor/200)

// Sinyal koşulu: destek çizgisi vs OTT çizgisi
plot(ottLine, color = color.red)
plot(vma, color = color.blue, style = plot.style_dotted)
```

## OTT Açıklaması

**OTT(20,2) göstergesi**, 20 periyotluk değişken ortalama ve %2'lik offset ile oluşturulan bir trend takip çizgisidir. 

**OTTsup(20)** ise aynı periyot için kullanılan destek çizgisidir (hareketli ortalama). 

Göstergenin matematiksel temeli, hareketli ortalamaya dayalı destek çizgisinin, belirli bir yüzde offset ile trailing stop mantığında yukarı/aşağı hareket ettirilmesidir. 

**OTT(20,2) < OTTsup(20)** durumunda destek çizgisi trend çizgisini yukarı kesmiş olur ve bu bir alıcılı trendin başlangıcı olarak yorumlanır – teknik analizde güçlü bir alım sinyali kriteridir.

## OTT Hesaplama Bileşenleri

1. **VIDYA (Variable Index Dynamic Average)**: 
   - CMO (Chande Momentum Oscillator) ile ağırlıklandırılmış EMA
   - 9 periyot CMO hesabı
   - 20 periyot EMA alpha değeri

2. **Trailing Stop Hesaplama**:
   - Offset = VMA * factor / 100 (factor = 2)
   - Long Stop = VMA - offset
   - Short Stop = VMA + offset

3. **OTT Trend Çizgisi**:
   - Trend yönüne göre longStop veya shortStop kullanılır
   - Ek factor/200 düzeltmesi uygulanır

## Sinyal Mantığı

- **OTT < OTT_SUP** → **AL** sinyali (Destek çizgisi trend çizgisini yukarı kesti)
- **OTT ≥ OTT_SUP** → **SAT** sinyali

## Mevcut Durum

- **24.03.2025 tarihinde**: OTT mantığı düzeltildi, artık SAT modu doğru hesaplanıyor
- **Backtest engine**: OTT değerleri trade objesine aktarılıyor
- **Web sayfası**: OTT değerleri JSON'da mevcut

## Yapılacaklar

1. **VIDYA hesaplama algoritması** eklenebilir (şu an basit EMA kullanılıyor)
2. **CMO hesaplama** eklenebilir
3. **Trailing stop mantığı** iyileştirilebilir
4. **OTT değerleri** web sayfasında görünüyor mu kontrol edilmeli
