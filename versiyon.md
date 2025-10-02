# Sürüm Notları

## 29 Eylül 2025

### Yeni Özellik: Güvenli Emir Yönetim Sistemi (Order Lifecycle Management)

**Özellik:**
- Bot artık daha güvenli bir emir yönetim sistemi kullanıyor
- Emirler gönderilmeden önce `pending_orders.json` dosyasına kaydediliyor (Write-Ahead Log prensibi)
- Binance'den gelen emir durumları düzenli olarak kontrol ediliyor (Reconciliation)
- Sistem çöktüğünde bile bekleyen emirler güvenli şekilde işleniyor

**Yeni Dosyalar:**
- `core/order_manager.py` - Merkezi emir yönetim modülü
- `data/[strategy_id]/pending_orders.json` - Her strateji için bekleyen emirler

**Emir Akışı:**
1. **Emir Oluşturma:** Strateji sinyal üretir → `OrderManager.create_order()` çağrılır
2. **Write-Ahead Log:** Emir `pending_orders.json`'a kaydedilir (SUBMITTED durumunda)
3. **Binance'e Gönderim:** Emir Binance API'ye gönderilir
4. **Durum Güncelleme:** `pending_orders.json`'da status `SUBMITTED` olur
5. **Reconciliation:** Düzenli aralıklarla Binance'den emir durumu kontrol edilir
6. **Fill İşleme:** Emir dolduğunda `trades.csv` ve `state.json` güncellenir
7. **Temizlik:** İşlenen emir `pending_orders.json`'dan kaldırılır

**Güvenlik Özellikleri:**
- **Crash Recovery:** Sistem yeniden başladığında bekleyen emirler otomatik kontrol edilir
- **Duplicate Prevention:** Aynı emir ID'si ile tekrar işlem yapılmaz
- **Timeout Management:** Uzun süre bekleyen emirler otomatik iptal edilir
- **State Consistency:** `state.json` sadece doğrulanmış işlemlerle güncellenir

**Debug Sistemi:**
- Logger sistemi basitleştirildi (asyncio uyumluluğu için)
- Doğrudan dosya yazma debug mekanizması eklendi
- Ana trading döngüsü tek bir `_main_trading_loop` fonksiyonunda toplandı

**Sorun Çözümleri:**
- **Logger Seviyesi Sorunu:** Logger seviyesi `WARNING` (30) olarak ayarlanmıştı, `INFO` (20) olarak düzeltildi
- **Status Kontrolü Sorunu:** `process_order_update` fonksiyonunda `'FILLED'` kontrolü yapılıyordu, `['FILLED', 'CLOSED']` olarak güncellendi
- **Trade Nesnesi Sorunu:** `Trade` nesnesi oluşturulurken `z`, `gf_before`, `gf_after` alanları eksikti, varsayılan değerlerle düzeltildi

**Sonuç:**
- ✅ Emirler artık başarıyla işleniyor
- ✅ `pending_orders.json` dosyasından emirler kaldırılıyor
- ✅ `trades.csv` dosyası oluşturuluyor
- ✅ `state.json` dosyası güncelleniyor
- ✅ Sistem güvenli şekilde çalışıyor

## 28 Eylül 2025

### Sorun Tespiti ve Çözümü: `TypeError` Kaynaklı Otomatik Strateji Durdurma

**Sorun:**
- Bot, `can't subtract offset-naive and offset-aware datetimes` şeklinde bir `TypeError` hatası vererek bazı stratejileri otomatik olarak durduruyordu.
- Bu hatanın temel nedeni, `state.json` dosyası okunamadığında veya eski kayıtlarda zaman dilimi bilgisi olmayan tarih/saat formatları bulunduğunda ortaya çıkıyordu. Kodun farklı bölümleri, zaman dilimi bilgisine sahip (aware) ve sahip olmayan (naive) `datetime` nesnelerini bir arada kullanmaya çalışıyordu.

**Yapılan Değişiklikler:**
Bu hatayı kalıcı olarak çözmek ve sistemin zaman yönetimi tutarlılığını artırmak için iki ana dosyada değişiklik yapıldı:

1.  **`core/models.py`**
    - `State` Pydantic modelindeki `last_update` alanı, varsayılan olarak her zaman UTC zaman diliminde (`timezone.utc`) bir `datetime` nesnesi oluşturacak şekilde güncellendi. Bu, özellikle yeni veya geçici `State` nesneleri oluşturulduğunda hatanın önüne geçer.

2.  **`core/storage.py`**
    - `load_state` fonksiyonu güncellendi. Artık `state.json` dosyasından okunan `last_bar_timestamp` ve `last_update` gibi tarih/saat alanları, eğer zaman dilimi bilgisi içermiyorsa (naive ise), otomatik olarak UTC zaman dilimine sahip (aware) hale getiriliyor. Bu, eski kayıtlarla geriye dönük uyumluluğu sağlar.

**Sonuç:**
Bu iki değişiklik sayesinde, tüm sistem genelinde `datetime` nesneleri tutarlı bir şekilde zaman dilimi bilgisine sahip olacak ve bu kritik `TypeError` hatasının tekrar oluşması engellenmiştir.
