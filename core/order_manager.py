# core/order_manager.py
# 29 Eylül 2025
# Bu modül, botun emir yaşam döngüsü yönetimini (order lifecycle management) merkezileştirir.
# Amacı:
# 1. Emirlerin borsaya güvenli bir şekilde gönderilmesini sağlamak (Write-Ahead Log).
# 2. Gönderilen emirlerin durumunu periyodik olarak borsa ile karşılaştırarak takip etmek (Reconciliation).
# 3. Belirli bir sürede gerçekleşmeyen emirleri otomatik olarak iptal etmek (Timeout).
# 4. Bot çöküp yeniden başladığında, havada kalmış emirleri tespit edip durumu onarmak (Crash Recovery).
# Bu merkezi yapı, state.json dosyasının bozulması riskini ortadan kaldırır ve tüm stratejiler için
# tutarlı ve güvenilir bir emir yönetimi sağlar.

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import uuid
import os

from .binance import BinanceClient, binance_client
from .models import OrderSide, Trade, Strategy
from .storage import StorageManager
from .utils import logger
from .telegram import telegram_notifier


class OrderManager:
    def __init__(self, storage: StorageManager, binance: BinanceClient, strategy_id: str):
        self.storage = storage
        self.binance = binance
        self.strategy_id = strategy_id
        self.pending_orders: Dict[str, Any] = {}
        self.lock = asyncio.Lock()
        self.timeout_minutes = 5  # 3 dakika sonra zaman aşımı
        self.strategy: Optional[Strategy] = None # Strateji objesini tutmak için

    async def initialize(self):
        """OrderManager'ı başlatır, bekleyen emirleri yükler ve onarma işlemini tetikler."""
        logger.info(f"🔧 DEBUG: [{self.strategy_id}] OrderManager.initialize() çağrıldı")
        async with self.lock:
            # Strateji objesini yükle, sembol bilgisi gibi detaylar için gerekli
            self.strategy = await self.storage.get_strategy(self.strategy_id)
            if not self.strategy:
                logger.error(f"[{self.strategy_id}] OrderManager başlatılamadı: Strateji bulunamadı.")
                return

            self.pending_orders = await self.storage.load_pending_orders(self.strategy_id)
            logger.info(f"[{self.strategy_id}] OrderManager başlatıldı. {len(self.pending_orders)} bekleyen emir yüklendi.")
            logger.info(f"🔧 DEBUG: [{self.strategy_id}] Pending orders: {list(self.pending_orders.keys())}")
        
        # Başlangıçta onarma (reconciliation) işlemini tetikle
        await self.reconcile_orders()

    async def create_order(self, side: OrderSide, quantity: float, price: Optional[float] = None, order_type: str = "LIMIT") -> Optional[Dict[str, Any]]:
        """
        Yeni bir emir oluşturur. Emri önce diske 'PENDING_SUBMIT' olarak yazar, sonra borsaya gönderir.
        """
        if not self.strategy:
            logger.error(f"[{self.strategy_id}] Emir oluşturulamadı: Strateji yüklenmemiş.")
            return None

        internal_id = str(uuid.uuid4())

        # Mevcut state'ten döngü bilgisini al
        state = await self.storage.load_state(self.strategy_id)
        cycle_info = f"D{state.cycle_number}-{state.cycle_trade_count + 1}" if state else "D?-?"

        order_data = {
            "internal_id": internal_id,
            "strategy_id": self.strategy_id,
            "order_id": None,
            "side": side.value,
            "quantity": quantity,
            "price": price,
            "order_type": order_type,
            "status": "PENDING_SUBMIT",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "cycle_info": cycle_info,  # DÖNGÜ BİLGİSİ EKLENDİ
        }

        async with self.lock:
            self.pending_orders[internal_id] = order_data
            await self._save_pending_orders()
            logger.info(f"[{self.strategy_id}] Yeni emir diske kaydedildi (ID: {internal_id}). Borsaya gönderiliyor...")

        try:
            if order_type.upper() == "MARKET":
                order_result = await self.binance.create_market_order(
                    symbol=self.strategy.symbol.value,
                    side=side,
                    quantity=quantity,
                    strategy_id=self.strategy_id,
                    strategy_type=self.strategy.strategy_type.value
                )
            else: # LIMIT
                if price is None:
                    raise ValueError("Limit emir için fiyat belirtilmelidir.")
                order_result = await self.binance.create_limit_order(
                    symbol=self.strategy.symbol.value,
                    side=side,
                    quantity=quantity,
                    price=price,
                    strategy_id=self.strategy_id,
                    strategy_type=self.strategy.strategy_type.value
                )

            if order_result and 'id' in order_result:
                async with self.lock:
                    self.pending_orders[internal_id]['status'] = 'SUBMITTED'
                    self.pending_orders[internal_id]['order_id'] = str(order_result['id'])
                    self.pending_orders[internal_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
                    await self._save_pending_orders()
                    logger.info(f"[{self.strategy_id}] Emir borsaya başarıyla gönderildi. Order ID: {order_result['id']}")
                    
                    # Telegram bildirimi gönder
                    try:
                        await telegram_notifier.send_trade_notification(
                            strategy_name=self.strategy.name,
                            symbol=self.strategy.symbol.value,
                            side=side.value,
                            quantity=quantity,
                            price=price,
                            order_id=str(order_result['id']),
                            order_type=order_type
                        )
                    except Exception as e:
                        logger.error(f"[{self.strategy_id}] Telegram bildirimi gönderilemedi: {e}")
                    
                return self.pending_orders[internal_id]
            else:
                raise Exception("Borsadan emir onayı alınamadı veya order ID eksik.")

        except Exception as e:
            logger.error(f"[{self.strategy_id}] Emir gönderme hatası (ID: {internal_id}): {e}")
            async with self.lock:
                self.pending_orders[internal_id]['status'] = 'SUBMIT_FAILED'
                self.pending_orders[internal_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
                await self._save_pending_orders()
            return self.pending_orders[internal_id]

    async def reconcile_orders(self):
        """
        Bekleyen tüm emirlerin durumunu borsa ile karşılaştırır ve yerel kaydı günceller.
        Bu fonksiyon periyodik olarak ve bot başladığında çalıştırılmalıdır.
        """
        logger.info(f"🔧 DEBUG: [{self.strategy_id}] reconcile_orders() çağrıldı")
        async with self.lock:
            # ÖNEMLİ: Pending orders'ı her seferinde yeniden yükle
            self.pending_orders = await self.storage.load_pending_orders(self.strategy_id)
            logger.info(f"🔧 DEBUG: [{self.strategy_id}] Pending orders yeniden yüklendi: {len(self.pending_orders)} emir")
            
            if not self.pending_orders:
                logger.info(f"🔧 DEBUG: [{self.strategy_id}] Pending orders boş, reconciliation atlanıyor")
                return

            logger.info(f"[{self.strategy_id}] {len(self.pending_orders)} bekleyen emir için mutabakat başlatılıyor...")
            
            # Durumu kontrol edilecek order_id'leri topla
            orders_to_check = {
                p['internal_id']: p['order_id'] 
                for p in self.pending_orders.values() 
                if p['status'] in ['SUBMITTED', 'PENDING_CANCEL'] and p['order_id']
            }
            
            logger.info(f"🔧 DEBUG: [{self.strategy_id}] Orders to check: {orders_to_check}")
            
            if not orders_to_check:
                logger.info(f"[{self.strategy_id}] Durumu kontrol edilecek (SUBMITTED) emir bulunamadı.")
                return

            try:
                # Toplu olarak emir durumlarını Borsa'dan al
                logger.info(f"🔧 DEBUG: [{self.strategy_id}] Binance'den emir durumları alınıyor...")
                order_statuses = await self.binance.check_order_status_detailed(
                    self.strategy.symbol.value, 
                    list(orders_to_check.values())
                )
                
                logger.info(f"🔧 DEBUG: [{self.strategy_id}] Binance'den gelen durumlar: {order_statuses}")
                status_map = {str(s['order_id']): s for s in order_statuses}

                # Her bir emri işle
                for internal_id, order_id in orders_to_check.items():
                    if order_id in status_map:
                        await self.process_order_update(internal_id, status_map[order_id])
                    else:
                        # Borsa'da bulunamayan emirleri kontrol et (belki çoktan doldu ve aradan zaman geçti)
                        logger.warning(f"[{self.strategy_id}] Emir {order_id} borsa durum sorgusunda bulunamadı. Zaman aşımı kontrolü yapılacak.")
                        # ÖNEMLİ: Binance'te bulunamayan emirler için hayalet pozisyon oluşturma riski var
                        # Bu emirleri hemen iptal et veya timeout kontrolüne bırak
                        pending_order = self.pending_orders.get(internal_id)
                        if pending_order:
                            created_at = datetime.fromisoformat(pending_order['created_at'])
                            age_minutes = (datetime.now(timezone.utc) - created_at).total_seconds() / 60
                            if age_minutes > 5:  # 5 dakikadan eski emirler için
                                logger.warning(f"[{self.strategy_id}] Emir {order_id} {age_minutes:.1f} dakikadır Binance'te bulunamıyor. Hayalet pozisyon riski! İptal ediliyor.")
                                await self.cancel_order(internal_id, reason=f"not_found_on_binance_{age_minutes:.1f}min")

            except Exception as e:
                logger.error(f"[{self.strategy_id}] Emir durumlarını kontrol ederken hata: {e}")

            # Zaman aşımı kontrolü (Borsa'da bulunamayan veya hala açık olanlar için)
            await self._check_timeouts()


    async def process_order_update(self, internal_id: str, binance_order_status: Dict[str, Any]):
        """
        Borsadan gelen güncel emir durumunu işler ve gerekli aksiyonları alır.
        NOT: Bu fonksiyon zaten kilitli bir alandan (reconcile_orders) çağrıldığı için
        tekrar kilit ALMAMALIDIR.
        """
        pending_order = self.pending_orders.get(internal_id)
        if not pending_order:
            return # Emir zaten işlenmiş olabilir

        status = binance_order_status.get('status', '').upper()
        
        logger.info(f"🔧 DEBUG: [{self.strategy_id}] Processing order {internal_id} with status: {status}")
        
        if status in ['FILLED', 'CLOSED']:
            logger.info(f"✅ [{self.strategy_id}] Emir DOLDU: {pending_order['order_id']}")
            
            # ÖNEMLİ: Binance'ten gelen veriyi doğrula
            if not binance_order_status.get('filled_qty') or float(binance_order_status.get('filled_qty', 0)) <= 0:
                logger.error(f"❌ [{self.strategy_id}] HATA: Emir FILLED olarak işaretlendi ama filled_qty yok veya 0! Binance verisi: {binance_order_status}")
                return
            
            try:
                # 1. Strateji handler'ını al
                from .strategy_engine import strategy_engine
                handler = strategy_engine.get_strategy_handler(self.strategy.strategy_type)
                if not handler:
                    logger.error(f"[{self.strategy_id}] Strateji handler bulunamadı: {self.strategy.strategy_type}")
                    return

                # 2. Trade nesnesi oluştur
                trade = self._create_trade_from_fill(pending_order, binance_order_status)
                logger.info(f"🔧 DEBUG: [{self.strategy_id}] Trade nesnesi oluşturuldu: {trade}")

                # 3. State'i yükle ve güncelle
                state = await self.storage.load_state(self.strategy_id)
                logger.info(f"🔧 DEBUG: [{self.strategy_id}] State yüklendi, process_fill çağrılıyor...")
                await handler.process_fill(self.strategy, state, trade)
                logger.info(f"🔧 DEBUG: [{self.strategy_id}] process_fill tamamlandı")
                
                # 4. Güncellenmiş state'i ve trade'i kaydet
                await self.storage.save_state(state)
                await self.storage.save_trade(trade)
                logger.info(f"🔧 DEBUG: [{self.strategy_id}] State ve trade kaydedildi")
                
                # 5. Bekleyen emirlerden temizle
                if internal_id in self.pending_orders:
                    del self.pending_orders[internal_id]
                await self._save_pending_orders()
                logger.info(f"[{self.strategy_id}] State ve trade kaydedildi. Emir {internal_id} listeden kaldırıldı.")
                
                # 6. Telegram bildirimi gönder (emir gerçekleşti)
                try:
                    await telegram_notifier.send_fill_notification(
                        strategy_name=self.strategy.name,
                        symbol=self.strategy.symbol.value,
                        side=pending_order['side'],
                        quantity=trade.quantity,
                        price=trade.price
                    )
                except Exception as e:
                    logger.error(f"[{self.strategy_id}] Telegram fill bildirimi gönderilemedi: {e}")
                
            except Exception as e:
                logger.error(f"❌ [{self.strategy_id}] process_order_update hatası: {e}")
                import traceback
                logger.error(f"❌ [{self.strategy_id}] Traceback: {traceback.format_exc()}")
                return

        elif status in ['CANCELED', 'EXPIRED', 'REJECTED']:
            logger.info(f"❌ [{self.strategy_id}] Emir İPTAL EDİLDİ/GEÇERSİZ: {pending_order['order_id']} (Durum: {status})")
            if internal_id in self.pending_orders:
                del self.pending_orders[internal_id]
            await self._save_pending_orders()

        elif status in ['NEW', 'PARTIALLY_FILLED']:
            # Zaman aşımı bu durumları ayrıca ele alacak. Şimdilik sadece log.
            logger.debug(f"⏳ [{self.strategy_id}] Emir hala açık: {pending_order['order_id']} (Durum: {status})")


    async def cancel_order(self, internal_id: str, reason: str = "manual"):
        """Bir emri iptal etmek için istek gönderir."""
        async with self.lock:
            order = self.pending_orders.get(internal_id)
            if not order or not order.get("order_id"):
                logger.warning(f"[{self.strategy_id}] İptal edilecek emir bulunamadı veya order_id'si yok: {internal_id}")
                return

            if order['status'] == 'PENDING_CANCEL':
                return # Zaten iptal isteği gönderilmiş

            logger.info(f"[{self.strategy_id}] Emir (ID: {order['order_id']}) için iptal isteği gönderiliyor... Sebep: {reason}")
            try:
                await self.binance.cancel_order(self.strategy.symbol.value, order['order_id'])
                order['status'] = 'PENDING_CANCEL'
                order['updated_at'] = datetime.now(timezone.utc).isoformat()
                await self._save_pending_orders()
            except Exception as e:
                logger.error(f"[{self.strategy_id}] Emir iptal edilirken hata oluştu: {e}")
            
    async def _save_pending_orders(self):
        """Bekleyen emirlerin güncel halini dosyaya kaydeder."""
        await self.storage.save_pending_orders(self.strategy_id, self.pending_orders)

    def has_pending_orders(self) -> bool:
        """Bekleyen emir olup olmadığını kontrol eder."""
        return len(self.pending_orders) > 0

    def get_pending_order_count(self) -> int:
        """Bekleyen emir sayısını döndürür."""
        return len(self.pending_orders)

    def _create_trade_from_fill(self, pending_order: Dict, binance_fill: Dict) -> Trade:
        """Borsa fill verisinden bir Trade nesnesi oluşturur."""
        # ÖNEMLİ: Binance verilerini doğrula
        filled_qty = float(binance_fill.get('filled_qty', 0.0))
        if filled_qty <= 0:
            raise ValueError(f"Geçersiz filled_qty: {filled_qty}. Binance verisi: {binance_fill}")
        
        price = float(binance_fill.get('average_price', binance_fill.get('price', 0.0)))
        if price <= 0:
            raise ValueError(f"Geçersiz price: {price}. Binance verisi: {binance_fill}")
        
        # Commission alanını güvenli şekilde işle
        commission_value = binance_fill.get('commission')
        if commission_value is None:
            commission_value = 0.0
        else:
            commission_value = float(commission_value)
        
        return Trade(
            timestamp=binance_fill.get('timestamp', datetime.now(timezone.utc)),
            strategy_id=self.strategy_id,
            side=OrderSide(pending_order['side'].lower()),
            price=price,
            quantity=filled_qty,
            notional=filled_qty * price,
            order_id=pending_order['order_id'],
            commission=commission_value,
            cycle_info=pending_order.get('cycle_info'),  # None olarak bırak, strateji tipine göre doldurulacak
            z=0,  # process_fill içinde doldurulacak
            gf_before=0.0,  # process_fill içinde doldurulacak
            gf_after=0.0  # process_fill içinde doldurulacak
        )

    async def _check_timeouts(self):
        """Zaman aşımına uğramış emirleri kontrol eder ve iptal eder."""
        now = datetime.now(timezone.utc)
        orders_to_cancel = []
        for internal_id, order in self.pending_orders.items():
            if order['status'] in ['SUBMITTED', 'PENDING_SUBMIT']:
                created_at = datetime.fromisoformat(order['created_at'])
                age = now - created_at
                if age > timedelta(minutes=self.timeout_minutes):
                    orders_to_cancel.append((internal_id, f"timeout_{age.total_seconds()/60:.1f}dk"))
        
        for internal_id, reason in orders_to_cancel:
            await self.cancel_order(internal_id, reason=reason)
