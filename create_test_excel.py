# Test Excel dosyası oluşturucu (22 Eylül 2025)
# Bu script ile Excel backtest sistemi için test verisi oluşturuyoruz

import pandas as pd
from datetime import datetime, timedelta

# Test verisini oluştur
data = []
base_price = 65400
base_time = datetime(2024, 11, 5, 0, 0)

for i in range(48):  # 48 saat = 2 gün
    timestamp = base_time + timedelta(hours=i)
    
    # Fiyat dalgalanması simüle et
    price_change = (i % 12 - 6) * 10  # -60 ile +50 arası değişim
    current_price = base_price + price_change + (i * 2)  # Genel yükseliş trendi
    
    # OHLC verisi oluştur
    open_price = current_price - 5 + (i % 3)
    high_price = current_price + 15 + (i % 7)
    low_price = current_price - 12 - (i % 5)
    close_price = current_price
    volume = 50000 + (i * 1000) + ((i % 10) * 5000)
    wclose = current_price + ((i % 5) - 2)
    
    data.append({
        'Date': timestamp.strftime('%d.%m.%Y'),
        'Time': timestamp.strftime('%H:%M'),
        'Open': round(open_price, 2),
        'High': round(high_price, 2),
        'Low': round(low_price, 2),
        'Close': round(close_price, 2),
        'Volume': int(volume),
        'WClose': round(wclose, 2)
    })

# DataFrame oluştur
df = pd.DataFrame(data)

# Excel dosyasına kaydet
try:
    df.to_excel('test_backtest_data.xlsx', index=False)
    print(f"✅ Excel dosyası oluşturuldu: test_backtest_data.xlsx")
    print(f"📊 Satır sayısı: {len(df)}")
    print(f"📅 Tarih aralığı: {df['Date'].iloc[0]} - {df['Date'].iloc[-1]}")
    print(f"💰 Fiyat aralığı: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")
    print(f"📈 Sütunlar: {list(df.columns)}")
    print("\n🔍 İlk 5 satır:")
    print(df.head().to_string(index=False))
    
except Exception as e:
    print(f"❌ Hata: {e}")
    # CSV olarak kaydet
    df.to_csv('test_backtest_data.csv', index=False)
    print(f"📄 CSV dosyası oluşturuldu: test_backtest_data.csv")
