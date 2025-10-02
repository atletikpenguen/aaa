"""
Birden fazla siparişin durumunu Binance API üzerinden kontrol eder.
"""
import asyncio
import os
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# .env dosyasındaki ortam değişkenlerini yükle
load_dotenv()

# API anahtarlarını .env dosyasından al
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
USE_TESTNET = os.getenv("USE_TESTNET", 'false').lower() == 'true'

# Kontrol edilecek siparişler
ORDERS_TO_CHECK = [
    ("83203065004", "3644785f"),  # İlk strateji
    ("83183337535", "6c878207"),  # İkinci strateji - 1. işlem
    ("83187753447", "6c878207"),  # İkinci strateji - 2. işlem  
    ("83202741911", "6c878207"),  # İkinci strateji - 3. işlem
]

SYMBOL = "ETHUSDT"

def _convert_symbol_to_ccxt(symbol: str) -> str:
    """Sembolü CCXT formatına dönüştür: ETHUSDT -> ETH/USDT:USDT"""
    if symbol.endswith('USDT'):
        base = symbol[:-4]
        return f"{base}/USDT:USDT"
    return symbol

async def check_order_status(client, order_id, strategy_id):
    """Tek bir siparişin durumunu kontrol et"""
    try:
        order_status = await client.fetch_order(order_id, _convert_symbol_to_ccxt(SYMBOL))
        return {
            'order_id': order_id,
            'strategy_id': strategy_id,
            'status': 'FOUND',
            'details': order_status
        }
    except ccxt.OrderNotFound:
        return {
            'order_id': order_id,
            'strategy_id': strategy_id,
            'status': 'NOT_FOUND',
            'details': None
        }
    except Exception as e:
        return {
            'order_id': order_id,
            'strategy_id': strategy_id,
            'status': 'ERROR',
            'details': str(e)
        }

async def main():
    """Ana fonksiyon"""
    print("=== ÇOKLU SİPARİŞ DURUM KONTROLÜ ===")
    print(f"Kontrol edilecek sipariş sayısı: {len(ORDERS_TO_CHECK)}")
    print(f"Sembol: {SYMBOL}")
    print(f"Testnet: {USE_TESTNET}")
    print("=" * 50)

    if not API_KEY or not API_SECRET:
        print("\nHATA: API anahtarları bulunamadı.")
        return

    # CCXT client'ını başlat
    client_config = {
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'options': {
            'defaultType': 'future',
            'defaultSubType': 'linear'
        }
    }
    if USE_TESTNET:
        client_config['sandbox'] = True

    client = ccxt.binance(client_config)

    try:
        results = []
        
        # Tüm siparişleri paralel olarak kontrol et
        tasks = []
        for order_id, strategy_id in ORDERS_TO_CHECK:
            task = check_order_status(client, order_id, strategy_id)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Sonuçları analiz et
        found_count = 0
        not_found_count = 0
        error_count = 0
        
        print("\n=== SONUÇLAR ===")
        for result in results:
            print(f"\nSipariş: {result['order_id']} (Strateji: {result['strategy_id']})")
            print(f"Durum: {result['status']}")
            
            if result['status'] == 'FOUND':
                found_count += 1
                details = result['details']
                print(f"  - Binance Durumu: {details.get('status')}")
                print(f"  - Taraf: {details.get('side')}")
                print(f"  - Fiyat: {details.get('price')}")
                print(f"  - Miktar: {details.get('amount')}")
                print(f"  - Doldurulan: {details.get('filled')}")
            elif result['status'] == 'NOT_FOUND':
                not_found_count += 1
                print("  - [X] Binance'te bulunamadi")
            else:
                error_count += 1
                print(f"  - [X] Hata: {result['details']}")
        
        print(f"\n=== ÖZET ===")
        print(f"Toplam kontrol edilen: {len(ORDERS_TO_CHECK)}")
        print(f"Binance'te bulunan: {found_count}")
        print(f"Binance'te bulunamayan: {not_found_count}")
        print(f"Hata alan: {error_count}")
        
        if not_found_count > 0:
            print(f"\n[!] UYARI: {not_found_count} siparis Binance'te bulunamadi!")
            print("Bu durum 'hayalet pozisyon' problemi oldugunu gosterir.")
            print("State recovery islemi gerekebilir.")

    except Exception as e:
        print(f"\nGenel bir hata oluştu: {e}")

    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
