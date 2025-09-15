"""
Telegram Bot Entegrasyonu - Trading bildirimler için
"""

import asyncio
import aiohttp
import json
from typing import Optional, Dict, Any
from datetime import datetime
from core.utils import logger
from core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class TelegramNotifier:
    """Telegram bot ile bildirim gönderme sınıfı"""
    
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            logger.warning("Telegram bot ayarları eksik - bildirimler kapalı")
    
    async def send_message(self, text: str, parse_mode: str = "Markdown", max_retries: int = 3) -> bool:
        """Telegram'a mesaj gönder - retry mekanizması ile"""
        if not self.enabled:
            logger.debug(f"Telegram kapalı - mesaj gönderilmedi: {text[:50]}...")
            return False
        
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as response:
                        if response.status == 200:
                            logger.debug("Telegram mesajı başarıyla gönderildi")
                            return True
                        else:
                            result = await response.text()
                            logger.error(f"Telegram mesaj hatası {response.status}: {result}")
                            
            except Exception as e:
                logger.error(f"Telegram mesaj gönderme hatası (deneme {attempt + 1}/{max_retries}): {e}")
            
            # Son deneme değilse 30 saniye bekle
            if attempt < max_retries - 1:
                logger.info(f"Telegram mesajı gönderilemedi, 30 saniye sonra tekrar denenecek... (deneme {attempt + 1}/{max_retries})")
                await asyncio.sleep(30)
        
        # Tüm denemeler başarısız
        logger.error(f"Telegram mesajı {max_retries} deneme sonunda gönderilemedi - strateji durdurulacak!")
        return False
    
    async def send_trade_notification(self, strategy_name: str, symbol: str, side: str, 
                                    quantity: float, price: float, order_id: str = None, order_type: str = "LIMIT") -> bool:
        """Trading emri bildirimi gönder"""
        try:
            # Emoji seçimi
            side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
            action = "ALIM" if side.upper() == "BUY" else "SATIM"
            
            # Mesaj formatı
            order_type_emoji = "🚀" if order_type == "MARKET" else "⏳"
            price_info = f"💲 *Fiyat:* `${price:.6f}`" if price else "💲 *Fiyat:* `Market`"
            total_info = f"💵 *Toplam:* `${(quantity * price):.2f} USDT`" if price else "💵 *Toplam:* `Market`"
            
            message = f"""
{side_emoji} *{action} EMRİ OLUŞTURULDU* {order_type_emoji}

📈 *Strateji:* `{strategy_name}`
💱 *Sembol:* `{symbol}`
📊 *İşlem:* {action}
🚀 *Emir Türü:* `{order_type}`
💰 *Miktar:* `{quantity:.6f}`
{price_info}
{total_info}
🕐 *Zaman:* `{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}`
"""
            
            if order_id:
                message += f"🔖 *Emir ID:* `{order_id}`"
            
            return await self.send_message(message)
            
        except Exception as e:
            logger.error(f"Trade notification hatası: {e}")
            return False
    
    async def send_fill_notification(self, strategy_name: str, symbol: str, side: str, 
                                   quantity: float, price: float, profit: float = None) -> bool:
        """Emir gerçekleşme bildirimi gönder"""
        try:
            # Emoji seçimi
            side_emoji = "✅" if side.upper() == "BUY" else "✅"
            action = "ALIM" if side.upper() == "BUY" else "SATIM"
            
            # Mesaj formatı
            message = f"""
{side_emoji} *{action} EMRİ GERÇEKLEŞTİ*

📈 *Strateji:* `{strategy_name}`
💱 *Sembol:* `{symbol}`
📊 *İşlem:* {action} TAMAMLANDI
💰 *Miktar:* `{quantity:.6f}`
💲 *Fiyat:* `${price:.6f}`
💵 *Toplam:* `${(quantity * price):.2f} USDT`
🕐 *Zaman:* `{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}`
"""
            
            if profit is not None:
                profit_emoji = "💚" if profit > 0 else "❤️" if profit < 0 else "💛"
                message += f"{profit_emoji} *Kar/Zarar:* `${profit:.2f} USDT`"
            
            return await self.send_message(message)
            
        except Exception as e:
            logger.error(f"Fill notification hatası: {e}")
            return False
    
    async def send_strategy_notification(self, strategy_name: str, symbol: str, 
                                       message_type: str, details: str = "") -> bool:
        """Strateji durum bildirimi gönder"""
        try:
            emoji_map = {
                "started": "🚀",
                "stopped": "⏹️",
                "error": "⚠️",
                "warning": "⚠️",
                "info": "ℹ️"
            }
            
            emoji = emoji_map.get(message_type, "📊")
            type_text = {
                "started": "BAŞLATILDI",
                "stopped": "DURDURULDU", 
                "error": "HATA",
                "warning": "UYARI",
                "info": "BİLGİ"
            }.get(message_type, "DURUM")
            
            message = f"""
{emoji} *STRATEJİ {type_text}*

📈 *Strateji:* `{strategy_name}`
💱 *Sembol:* `{symbol}`
🕐 *Zaman:* `{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}`
"""
            
            if details:
                message += f"\n📝 *Detay:* {details}"
            
            return await self.send_message(message)
            
        except Exception as e:
            logger.error(f"Strategy notification hatası: {e}")
            return False
    
    async def send_daily_summary(self, total_trades: int, total_profit: float, 
                                active_strategies: int) -> bool:
        """Günlük özet bildirimi gönder"""
        try:
            profit_emoji = "💚" if total_profit > 0 else "❤️" if total_profit < 0 else "💛"
            
            message = f"""
📊 *GÜNLÜK ÖZET RAPORU*

📈 *Aktif Strateji:* `{active_strategies}`
🔄 *Toplam İşlem:* `{total_trades}`
{profit_emoji} *Net Kar/Zarar:* `${total_profit:.2f} USDT`
🕐 *Rapor Zamanı:* `{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}`

Bot çalışmaya devam ediyor... 🤖
"""
            
            return await self.send_message(message)
            
        except Exception as e:
            logger.error(f"Daily summary hatası: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """Telegram bot bağlantısını test et"""
        if not self.enabled:
            return False
            
        test_message = f"""
🤖 *TELEGRAM BOT TEST*

Grid + OTT Trading Bot bağlantısı başarılı!
🕐 Test Zamanı: `{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}`

Bot hazır ve bildirimler aktif ✅
"""
        
        return await self.send_message(test_message)


# Global telegram notifier instance
telegram_notifier = TelegramNotifier()
