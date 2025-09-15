"""
Telegram Bot Test Scripti
Bu script ile Telegram bot ayarlarını test edebilirsiniz.
"""

import asyncio
from core.telegram import telegram_notifier


async def test_telegram():
    """Telegram bot bağlantısını test et"""
    print("🤖 Telegram bot test ediliyor...")
    
    if not telegram_notifier.enabled:
        print("❌ Telegram bot kapalı - .env dosyasında TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID ayarlayın")
        print(f"📞 Bot Token: '{telegram_notifier.bot_token}'")
        print(f"💬 Chat ID: '{telegram_notifier.chat_id}'")
        return
    
    print(f"📞 Bot Token: {telegram_notifier.bot_token[:10]}...")
    print(f"💬 Chat ID: {telegram_notifier.chat_id}")
    
    # Bağlantı testi
    success = await telegram_notifier.test_connection()
    
    if success:
        print("✅ Telegram bot başarıyla test edildi!")
        print("📱 Test mesajı gönderildi")
        
        # Örnek bildirim testi
        print("\n📊 Örnek trading bildirimi test ediliyor...")
        await telegram_notifier.send_trade_notification(
            strategy_name="TEST Stratejisi",
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.001,
            price=50000.0,
            order_id="TEST123"
        )
        print("✅ Trading bildirimi gönderildi")
        
    else:
        print("❌ Telegram bot testi başarısız!")
        print("🔧 Lütfen bot token ve chat ID'yi kontrol edin")


if __name__ == "__main__":
    asyncio.run(test_telegram())