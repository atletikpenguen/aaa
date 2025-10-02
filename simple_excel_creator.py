# Basit Excel dosyası oluşturucu (22 Eylül 2025)
# pandas sorunu nedeniyle xlsxwriter ile direkt Excel oluşturuyoruz

import xlsxwriter
from datetime import datetime, timedelta

# Excel dosyası oluştur
workbook = xlsxwriter.Workbook('test_backtest_data.xlsx')
worksheet = workbook.add_worksheet('OHLCV')

# Headers
headers = ['Date', 'Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'WClose']
for col, header in enumerate(headers):
    worksheet.write(0, col, header)

# Test verisini oluştur ve yaz
base_price = 65400
base_time = datetime(2024, 11, 5, 0, 0)

for i in range(48):  # 48 saat = 2 gün
    row = i + 1
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
    
    # Veriyi Excel'e yaz
    worksheet.write(row, 0, timestamp.strftime('%d.%m.%Y'))
    worksheet.write(row, 1, timestamp.strftime('%H:%M'))
    worksheet.write(row, 2, round(open_price, 2))
    worksheet.write(row, 3, round(high_price, 2))
    worksheet.write(row, 4, round(low_price, 2))
    worksheet.write(row, 5, round(close_price, 2))
    worksheet.write(row, 6, int(volume))
    worksheet.write(row, 7, round(wclose, 2))

# Excel dosyasını kapat
workbook.close()

print("✅ Excel dosyası oluşturuldu: test_backtest_data.xlsx")
print("📊 48 saatlik Bitcoin simülasyon verisi")
print("💰 Fiyat aralığı: $65,400 - $65,500")
print("📈 Sütunlar: Date, Time, Open, High, Low, Close, Volume, WClose")
print("🎯 Backtest sistemi için hazır!")
