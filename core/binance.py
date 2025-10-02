"""
Binance CCXT Client - Market metadata ve order işlemleri
"""

import ccxt
from ccxt.base.errors import OrderNotFound, InvalidOrder
from ccxt.base.errors import OrderNotFound
import asyncio
import os
from core.config import API_KEY, API_SECRET, USE_TESTNET
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
import time

from .models import MarketInfo, OrderSide, OpenOrder, OrderLog, OrderLogManager
from .utils import logger, round_to_tick, floor_to_step, log_trading_action, log_binance_trading_action, is_valid_min_qty


class BinanceClient:
    """Binance USDⓈ-M Futures client wrapper"""
    
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False):
        self.api_key = api_key or API_KEY
        self.api_secret = api_secret or API_SECRET
        self.testnet = testnet if testnet is not None else USE_TESTNET
        
        # Market metadata cache
        self.markets_cache: Dict[str, MarketInfo] = {}
        self.last_markets_update = 0
        self.markets_cache_ttl = 3600  # 1 saat
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 100ms minimum
        
        # Order logging
        self.order_logger = OrderLogManager()
        
        self._initialize_client()
    
    def _convert_symbol_to_ccxt(self, symbol: str) -> str:
        """Sembol dönüştür: BTCUSDT -> BTC/USDT:USDT"""
        if symbol.endswith('USDT'):
            base = symbol[:-4]  # USDT'yi çıkar
            return f"{base}/USDT:USDT"
        return symbol
    
    def _convert_symbol_from_ccxt(self, ccxt_symbol: str) -> str:
        """Sembol dönüştür: BTC/USDT:USDT -> BTCUSDT"""
        if '/USDT:USDT' in ccxt_symbol:
            return ccxt_symbol.replace('/USDT:USDT', 'USDT')
        return ccxt_symbol
    
    def _initialize_client(self):
        """CCXT client'ını başlat"""
        try:
            if self.testnet:
                logger.info("Binance testnet kullanılıyor")
                self.client = ccxt.binance({
                    'apiKey': self.api_key,
                    'secret': self.api_secret,
                    'sandbox': True,  # Testnet
                    'options': {
                        'defaultType': 'future',  # USDⓈ-M Futures
                        'defaultSubType': 'linear'  # Linear/USDT-M
                    }
                })
            else:
                logger.info("Binance mainnet kullanılıyor")
                self.client = ccxt.binance({
                    'apiKey': self.api_key,
                    'secret': self.api_secret,
                    'options': {
                        'defaultType': 'future',  # USDⓈ-M Futures
                        'defaultSubType': 'linear'  # Linear/USDT-M
                    }
                })
            
            # Test bağlantısı
            if self.api_key and self.api_secret:
                try:
                    self.client.fetch_balance()
                    logger.info("Binance API bağlantısı başarılı")
                except Exception as e:
                    logger.warning(f"Binance API test hatası: {e}")
            else:
                logger.warning("Binance API keys bulunamadı - sadece market data modu")
                
        except Exception as e:
            logger.error(f"Binance client başlatma hatası: {e}")
            raise
    
    async def _rate_limit(self):
        """Rate limiting uygula"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    async def fetch_markets(self, force_refresh: bool = False) -> Dict[str, MarketInfo]:
        """Market metadata'sını al ve cache'le"""
        now = time.time()
        
        # Cache kontrol
        if not force_refresh and self.markets_cache and (now - self.last_markets_update) < self.markets_cache_ttl:
            return self.markets_cache
        
        try:
            await self._rate_limit()
            markets = self.client.fetch_markets()
            
            self.markets_cache.clear()
            
            for market in markets:
                # Perpetual USDT futures filtreleme
                if (market.get('linear') and 
                    market.get('swap') and 
                    market['quote'] == 'USDT' and
                    market.get('active', True)):
                    
                    ccxt_symbol = market['symbol']
                    # BTC/USDT:USDT -> BTCUSDT
                    symbol = self._convert_symbol_from_ccxt(ccxt_symbol)
                    
                    # Market limits'lerini al
                    limits = market.get('limits', {})
                    precision = market.get('precision', {})
                    
                    # Tick size (price precision)
                    tick_size = precision.get('price', 0.01)
                    if isinstance(tick_size, (int, float)) and tick_size > 0:
                        pass  # OK
                    else:
                        tick_size = 0.01
                    
                    # Step size (amount precision)
                    step_size = precision.get('amount', 0.001)
                    if isinstance(step_size, (int, float)) and step_size > 0:
                        pass  # OK
                    else:
                        step_size = 0.001
                    
                    # Min quantity
                    min_qty = limits.get('amount', {}).get('min', step_size)
                    if not isinstance(min_qty, (int, float)) or min_qty <= 0:
                        min_qty = step_size
                    
                    # Min notional
                    min_notional = limits.get('cost', {}).get('min', 5.0)
                    if not isinstance(min_notional, (int, float)) or min_notional <= 0:
                        min_notional = 5.0
                    
                    # current_price burada hesaplanmaz; sadece metadata cache'lenir
                    market_info = MarketInfo(
                        symbol=symbol,
                        current_price=0.0,
                        tick_size=float(tick_size),
                        step_size=float(step_size),
                        min_qty=float(min_qty),
                        min_notional=float(min_notional)
                    )
                    
                    self.markets_cache[symbol] = market_info
            
            self.last_markets_update = now
            logger.info(f"{len(self.markets_cache)} futures market bilgisi güncellendi")
            
            return self.markets_cache
            
        except Exception as e:
            logger.error(f"Markets fetch hatası: {e}")
            # Cache'de varsa onu döndür
            if self.markets_cache:
                logger.warning("Cache'deki market bilgileri kullanılıyor")
                return self.markets_cache
            raise
    
    async def get_market_info(self, symbol: str) -> Optional[MarketInfo]:
        """Belirli bir symbol için market info al"""
        markets = await self.fetch_markets()
        info = markets.get(symbol)
        if not info:
            return None
        # current_price'ı sadece istenen sembol için bloklamadan çek
        try:
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            import asyncio as _asyncio
            ticker = await _asyncio.to_thread(self.client.fetch_ticker, ccxt_symbol)
            last_price = ticker.get('last') or ticker.get('close') or 0.0
            info.current_price = float(last_price) if last_price is not None else 0.0
        except Exception as e:
            logger.warning(f"Güncel fiyat alınamadı {symbol}: {e}")
        return info
    
    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List[List]:
        """OHLCV verisi al"""
        try:
            await self._rate_limit()
            
            # CCXT timeframe format
            tf_map = {
                '1m': '1m',
                '5m': '5m', 
                '15m': '15m',
                '1h': '1h',
                '1d': '1d'
            }
            ccxt_timeframe = tf_map.get(timeframe, '1m')
            
            # Symbol dönüşümü: BTCUSDT -> BTC/USDT:USDT
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            
            ohlcv = self.client.fetch_ohlcv(ccxt_symbol, ccxt_timeframe, limit=limit)
            
            logger.debug(f"OHLCV verisi alındı: {symbol} {timeframe} ({len(ohlcv)} bar)")
            return ohlcv
            
        except Exception as e:
            logger.error(f"OHLCV fetch hatası {symbol}: {e}")
            return []
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Güncel fiyat al"""
        try:
            await self._rate_limit()
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            ticker = self.client.fetch_ticker(ccxt_symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"Fiyat alma hatası {symbol}: {e}")
            return None
    
    async def get_symbol_ticker(self, symbol: str) -> Optional[Dict]:
        """Symbol ticker bilgisi al (app.py uyumluluğu için)"""
        try:
            await self._rate_limit()
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            ticker = self.client.fetch_ticker(ccxt_symbol)
            return {
                'price': ticker.get('last', 0.0),
                'symbol': symbol,
                'timestamp': ticker.get('timestamp', 0)
            }
        except Exception as e:
            logger.error(f"Ticker alma hatası {symbol}: {e}")
            return None
    
    async def create_market_order(self, symbol: str, side: OrderSide, quantity: float, 
                                 strategy_id: str = "", strategy_type: str = "", 
                                 grid_level: Optional[int] = None) -> Optional[Dict]:
        """Market emir oluştur"""
        start_time = time.time()
        
        if not self.api_key or not self.api_secret:
            error_msg = "API keys gerekli - emir oluşturulamıyor"
            logger.error(error_msg)
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                symbol=symbol, side=side, order_type="market", quantity=quantity,
                status="error", action="create", message=error_msg, error=error_msg
            )
            return None
        
        try:
            # Market info kontrolü
            market_info = await self.get_market_info(symbol)
            if not market_info:
                error_msg = f"Market info bulunamadı: {symbol}"
                logger.error(error_msg)
                self._log_order_action(
                    strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                    symbol=symbol, side=side, order_type="market", quantity=quantity,
                    status="error", action="create", message=error_msg, error=error_msg
                )
                return None
            
            # Miktarı yuvarla
            rounded_qty = floor_to_step(quantity, market_info.step_size)
            
            # Validasyonlar
            if not is_valid_min_qty(rounded_qty, market_info.min_qty):
                error_msg = f"Minimum miktar altında: {rounded_qty} < {market_info.min_qty}"
                logger.error(error_msg)
                self._log_order_action(
                    strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                    symbol=symbol, side=side, order_type="market", quantity=rounded_qty,
                    status="error", action="create", message=error_msg, error=error_msg
                )
                return None
            
            await self._rate_limit()
            
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            
            # Emir gönderme öncesi log
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                symbol=symbol, side=side, order_type="market", quantity=rounded_qty,
                status="sending", action="create", message=f"Market emir gönderiliyor: {symbol} {side.value} {rounded_qty}",
                grid_level=grid_level
            )
            
            order = self.client.create_order(
                symbol=ccxt_symbol,
                type='market',
                side=side.value,  # 'buy' or 'sell'
                amount=rounded_qty
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            # Başarılı emir logu
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id=str(order.get('id', '')),
                symbol=symbol, side=side, order_type="market", quantity=rounded_qty,
                status="sent", action="create", message=f"Market emir oluşturuldu: {symbol} {side.value} {rounded_qty}",
                execution_time_ms=execution_time, grid_level=grid_level,
                binance_response=order
            )
            
            return order
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            error_msg = f"Market emir oluşturma hatası {symbol}: {e}"
            logger.error(error_msg)
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                symbol=symbol, side=side, order_type="market", quantity=quantity,
                status="error", action="create", message=error_msg, error=str(e),
                execution_time_ms=execution_time, grid_level=grid_level
            )
            return None
    
    async def create_limit_order(self, symbol: str, side: OrderSide, quantity: float, price: float,
                                strategy_id: str = "", strategy_type: str = "", 
                                grid_level: Optional[int] = None) -> Optional[Dict]:
        """Limit emir oluştur"""
        start_time = time.time()
        
        if not self.api_key or not self.api_secret:
            error_msg = "API keys gerekli - emir oluşturulamıyor"
            logger.error(error_msg)
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                symbol=symbol, side=side, order_type="limit", quantity=quantity, limit_price=price,
                status="error", action="create", message=error_msg, error=error_msg
            )
            return None
        
        try:
            # Market info kontrolü
            market_info = await self.get_market_info(symbol)
            if not market_info:
                error_msg = f"Market info bulunamadı: {symbol}"
                logger.error(error_msg)
                self._log_order_action(
                    strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                    symbol=symbol, side=side, order_type="limit", quantity=quantity, limit_price=price,
                    status="error", action="create", message=error_msg, error=error_msg
                )
                return None
            
            # Fiyat ve miktarı yuvarla
            rounded_price = round_to_tick(price, market_info.tick_size)
            rounded_qty = floor_to_step(quantity, market_info.step_size)
            
            # Validasyonlar
            if not is_valid_min_qty(rounded_qty, market_info.min_qty):
                error_msg = f"Minimum miktar altında: {rounded_qty} < {market_info.min_qty}"
                logger.error(error_msg)
                self._log_order_action(
                    strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                    symbol=symbol, side=side, order_type="limit", quantity=rounded_qty, limit_price=rounded_price,
                    status="error", action="create", message=error_msg, error=error_msg
                )
                return None
            
            notional = rounded_qty * rounded_price
            if notional < market_info.min_notional:
                error_msg = f"Minimum notional altında: {notional} < {market_info.min_notional}"
                logger.error(error_msg)
                self._log_order_action(
                    strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                    symbol=symbol, side=side, order_type="limit", quantity=rounded_qty, limit_price=rounded_price,
                    status="error", action="create", message=error_msg, error=error_msg, notional=notional
                )
                return None
            
            await self._rate_limit()
            
            # CCXT order parametreleri
            order_params = {
                'timeInForce': 'GTC'  # Good Till Cancelled
            }
            
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            
            # Emir gönderme öncesi log
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                symbol=symbol, side=side, order_type="limit", quantity=rounded_qty, limit_price=rounded_price,
                status="sending", action="create", message=f"Limit emir gönderiliyor: {symbol} {side.value} {rounded_qty} @ {rounded_price}",
                grid_level=grid_level, notional=notional
            )
            
            order = self.client.create_order(
                symbol=ccxt_symbol,
                type='limit',
                side=side.value,  # 'buy' or 'sell'
                amount=rounded_qty,
                price=rounded_price,
                params=order_params
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            # Başarılı emir logu
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id=str(order.get('id', '')),
                symbol=symbol, side=side, order_type="limit", quantity=rounded_qty, limit_price=rounded_price,
                status="sent", action="create", message=f"Limit emir oluşturuldu: {symbol} {side.value} {rounded_qty} @ {rounded_price}",
                execution_time_ms=execution_time, grid_level=grid_level, notional=notional,
                binance_response=order
            )
            
            return order
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            error_msg = f"Emir oluşturma hatası {symbol}: {e}"
            logger.error(error_msg)
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id="", 
                symbol=symbol, side=side, order_type="limit", quantity=quantity, limit_price=price,
                status="error", action="create", message=error_msg, error=str(e),
                execution_time_ms=execution_time, grid_level=grid_level
            )
            return None
    
    async def cancel_order(self, symbol: str, order_id: str, strategy_id: str = "", strategy_type: str = "") -> bool:
        """Emir iptal et"""
        start_time = time.time()
        
        if not self.api_key or not self.api_secret:
            error_msg = "API keys gerekli - emir iptal edilemiyor"
            logger.error(error_msg)
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                symbol=symbol, side=OrderSide.BUY, order_type="", quantity=0,
                status="error", action="cancel", message=error_msg, error=error_msg
            )
            return False
        
        try:
            await self._rate_limit()
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            
            # İptal öncesi log
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                symbol=symbol, side=OrderSide.BUY, order_type="", quantity=0,
                status="cancelling", action="cancel", message=f"Emir iptal ediliyor: {order_id}"
            )
            
            self.client.cancel_order(order_id, ccxt_symbol)
            
            execution_time = int((time.time() - start_time) * 1000)
            
            # Başarılı iptal logu
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                symbol=symbol, side=OrderSide.BUY, order_type="", quantity=0,
                status="cancelled", action="cancel", message=f"Emir iptal edildi: {order_id}",
                execution_time_ms=execution_time
            )
            
            return True
            
        except OrderNotFound:
            # Emir zaten yok (iptal edilmiş veya doldurulmuş)
            execution_time = int((time.time() - start_time) * 1000)
            warning_msg = f"Emir bulunamadı (zaten iptal/dolu olabilir): {order_id}"
            logger.warning(warning_msg)
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                symbol=symbol, side=OrderSide.BUY, order_type="", quantity=0,
                status="not_found", action="cancel", message=warning_msg,
                execution_time_ms=execution_time
            )
            return True  # İptal başarılı sayılır çünkü emir artık yok
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            error_msg = f"Emir iptal hatası {order_id}: {e}"
            logger.error(error_msg)
            self._log_order_action(
                strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                symbol=symbol, side=OrderSide.BUY, order_type="", quantity=0,
                status="error", action="cancel", message=error_msg, error=str(e),
                execution_time_ms=execution_time
            )
            return False
    
    async def cancel_all_orders(self, symbol: str) -> int:
        """Sembolün tüm açık emirlerini iptal et"""
        if not self.api_key or not self.api_secret:
            logger.error("API keys gerekli - emirler iptal edilemiyor")
            return 0
        
        try:
            await self._rate_limit()
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            open_orders = self.client.fetch_open_orders(ccxt_symbol)
            
            cancelled_count = 0
            for order in open_orders:
                try:
                    await self.cancel_order(symbol, order['id'])
                    cancelled_count += 1
                except Exception as e:
                    logger.warning(f"Emir iptal hatası {order['id']}: {e}")
            
            logger.info(f"{cancelled_count} emir iptal edildi: {symbol}")
            return cancelled_count
            
        except Exception as e:
            logger.error(f"Toplu emir iptal hatası {symbol}: {e}")
            return 0
    
    async def fetch_open_orders(self, symbol: str) -> List[OpenOrder]:
        """Açık emirleri al"""
        if not self.api_key or not self.api_secret:
            return []
        
        try:
            await self._rate_limit()
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            orders = self.client.fetch_open_orders(ccxt_symbol)
            
            open_orders = []
            for order in orders:
                try:
                    open_order = OpenOrder(
                        order_id=str(order['id']),
                        side=OrderSide(order['side']),
                        price=float(order['price']),
                        quantity=float(order['amount']),
                        z=0,  # Grid level - state'den alınacak
                        timestamp=datetime.fromtimestamp(order['timestamp'] / 1000, tz=timezone.utc)
                    )
                    open_orders.append(open_order)
                except Exception as e:
                    logger.warning(f"Open order parse hatası: {e}")
            
            return open_orders
            
        except Exception as e:
            logger.error(f"Open orders fetch hatası {symbol}: {e}")
            return []
    
    async def check_order_fills(self, symbol: str, order_ids: List[str], strategy_id: str = "", strategy_type: str = "") -> List[Dict]:
        """Emir doldurulma durumlarını kontrol et"""
        if not self.api_key or not self.api_secret:
            return []
        
        fills = []
        
        for order_id in order_ids:
            try:
                await self._rate_limit()
                ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
                
                # Kontrol öncesi log
                self._log_order_action(
                    strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                    symbol=symbol, side=OrderSide.BUY, order_type="", quantity=0,
                    status="checking", action="check", message=f"Emir durumu kontrol ediliyor: {order_id}"
                )
                
                order = self.client.fetch_order(order_id, ccxt_symbol)
                
                # Emir durumu logu
                self._log_order_action(
                    strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                    symbol=symbol, side=OrderSide(order['side']), order_type=order['type'],
                    quantity=float(order['amount']), price=float(order['price']),
                    status=order['status'], action="check", 
                    message=f"Emir durumu: {order['status']} - Dolu: {order['filled']}/{order['amount']}",
                    binance_response=order
                )
                
                if order['status'] == 'closed':  # Sadece tamamen dolan emirler
                    # Gerçekleşen ortalama fiyatı kullan (order['average']), limit fiyatını değil
                    actual_price = float(order['average']) if order['average'] else float(order['price'])
                    
                    # Doldurulma logu
                    self._log_order_action(
                        strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                        symbol=symbol, side=OrderSide(order['side']), order_type=order['type'],
                        quantity=float(order['filled']), price=actual_price, limit_price=float(order['price']),
                        status="filled", action="fill", 
                        message=f"Emir dolduruldu: {order_id} - {order['filled']} @ {actual_price}",
                        binance_response=order
                    )
                    
                    fills.append({
                        'order_id': order_id,
                        'symbol': symbol,
                        'side': order['side'],
                        'price': actual_price,  # Gerçekleşen ortalama fiyat
                        'limit_price': float(order['price']),  # Limit fiyat (referans için)
                        'filled_qty': float(order['filled']),
                        'timestamp': datetime.fromtimestamp(order['timestamp'] / 1000, tz=timezone.utc),
                        'fee': order.get('fee', {}),
                        'strategy_specific_data': {}  # Strategy özel verilerini ekle
                    })
                
            except Exception as e:
                error_msg = f"Order status kontrol hatası {order_id}: {e}"
                logger.warning(error_msg)
                self._log_order_action(
                    strategy_id=strategy_id, strategy_type=strategy_type, order_id=order_id, 
                    symbol=symbol, side=OrderSide.BUY, order_type="", quantity=0,
                    status="error", action="check", message=error_msg, error=str(e)
                )
        
        return fills
    
    async def check_order_status_detailed(self, symbol: str, order_ids: List[str]) -> List[Dict]:
        """Emir durumlarını detaylı kontrol et (partial fill, timeout vs.)"""
        if not self.api_key or not self.api_secret:
            return []
        
        order_details = []
        
        for order_id in order_ids:
            try:
                await self._rate_limit()
                ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
                order = self.client.fetch_order(order_id, ccxt_symbol)
                
                order_details.append({
                    'order_id': order_id,
                    'status': order['status'],  # open, closed, canceled, partially_filled
                    'filled_qty': float(order['filled']),
                    'remaining_qty': float(order['remaining']),
                    'original_qty': float(order['amount']),
                    'price': float(order['price']),
                    'average_price': float(order['average']) if order['average'] else None,
                    'timestamp': datetime.fromtimestamp(order['timestamp'] / 1000, tz=timezone.utc),
                    'side': order['side'],
                    'is_partial': order['status'] == 'partially_filled' and float(order['filled']) > 0
                })
                
            except Exception as e:
                logger.warning(f"Order detailed status kontrol hatası {order_id}: {e}")
        
        return order_details
    
    async def cancel_orders_batch(self, symbol: str, order_ids: List[str]) -> int:
        """Toplu emir iptali"""
        if not self.api_key or not self.api_secret:
            return 0
        
        cancelled_count = 0
        ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
        
        for order_id in order_ids:
            try:
                await self._rate_limit()
                result = self.client.cancel_order(order_id, ccxt_symbol)
                if result:
                    cancelled_count += 1
                    logger.info(f"Emir iptal edildi: {order_id}")
                else:
                    logger.warning(f"Emir iptal edilemedi: {order_id}")
                    
            except OrderNotFound:
                logger.warning(f"Emir bulunamadı (zaten iptal/dolu): {order_id}")
                cancelled_count += 1  # Zaten yok sayılır
            except Exception as e:
                logger.error(f"Emir iptal hatası {order_id}: {e}")
        
        return cancelled_count
    
    async def get_account_balance(self) -> Dict:
        """Hesap bakiyesi al"""
        if not self.api_key or not self.api_secret:
            return {}
        
        try:
            await self._rate_limit()
            balance = self.client.fetch_balance()
            
            # USDT bakiyesi
            usdt_balance = balance.get('USDT', {})
            
            return {
                'free': float(usdt_balance.get('free', 0)),
                'used': float(usdt_balance.get('used', 0)),
                'total': float(usdt_balance.get('total', 0))
            }
            
        except Exception as e:
            logger.error(f"Balance fetch hatası: {e}")
            return {}
    
    async def get_position_info(self, symbol: str) -> Dict:
        """Pozisyon bilgisi al"""
        if not self.api_key or not self.api_secret:
            return {}
        
        try:
            await self._rate_limit()
            ccxt_symbol = self._convert_symbol_to_ccxt(symbol)
            positions = self.client.fetch_positions([ccxt_symbol])
            
            if positions:
                pos = positions[0]
                return {
                    'symbol': symbol,
                    'size': float(pos.get('contracts', 0)),
                    'side': pos.get('side', 'none'),
                    'entry_price': float(pos.get('entryPrice', 0)),
                    'mark_price': float(pos.get('markPrice', 0)),
                    'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                    'percentage': float(pos.get('percentage', 0))
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Position fetch hatası {symbol}: {e}")
            return {}
    
    async def get_all_positions(self) -> Dict:
        """Tüm pozisyonları al ve net pozisyon hesapla"""
        if not self.api_key or not self.api_secret:
            return {
                'positions': [],
                'net_position_usd': 0.0,
                'total_long_usd': 0.0,
                'total_short_usd': 0.0,
                'error': 'API anahtarları bulunamadı'
            }
        
        try:
            await self._rate_limit()
            
            # Tüm pozisyonları al
            positions = self.client.fetch_positions()
            
            active_positions = []
            total_long_usd = 0.0
            total_short_usd = 0.0
            
            for pos in positions:
                size = float(pos.get('contracts', 0))
                if size == 0:  # Pozisyon yoksa atla
                    continue
                
                symbol = self._convert_symbol_from_ccxt(pos.get('symbol', ''))
                side = pos.get('side', 'none')
                mark_price = float(pos.get('markPrice', 0))
                entry_price = float(pos.get('entryPrice', 0))
                unrealized_pnl = float(pos.get('unrealizedPnl', 0))
                notional = float(pos.get('notional', 0))
                
                # USD değeri hesapla
                position_usd = abs(notional)
                
                # Long/Short ayırımı
                if side == 'long':
                    total_long_usd += position_usd
                elif side == 'short':
                    total_short_usd += position_usd
                
                active_positions.append({
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'entry_price': entry_price,
                    'mark_price': mark_price,
                    'unrealized_pnl': unrealized_pnl,
                    'notional_usd': notional,
                    'position_usd': position_usd
                })
            
            # Net pozisyon hesapla (Long + Short -)
            net_position_usd = total_long_usd - total_short_usd
            
            return {
                'positions': active_positions,
                'net_position_usd': net_position_usd,
                'total_long_usd': total_long_usd,
                'total_short_usd': total_short_usd,
                'position_count': len(active_positions),
                'last_update': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            logger.error(f"Tüm pozisyonları alma hatası: {e}")
            return {
                'positions': [],
                'net_position_usd': 0.0,
                'total_long_usd': 0.0,
                'total_short_usd': 0.0,
                'error': str(e)
            }
    
    def is_connected(self) -> bool:
        """Bağlantı durumunu kontrol et"""
        return self.client is not None
    
    def get_server_time(self) -> datetime:
        """Sunucu zamanını al"""
        try:
            server_time = self.client.fetch_time()
            return datetime.fromtimestamp(server_time / 1000, tz=timezone.utc)
        except Exception as e:
            logger.warning(f"Server time fetch hatası: {e}")
            return datetime.now(timezone.utc)

    def _log_order_action(self, strategy_id: str, strategy_type: str, order_id: str, symbol: str, 
                         side: OrderSide, order_type: str, quantity: float, price: Optional[float] = None,
                         limit_price: Optional[float] = None, status: str = "sent", action: str = "create",
                         message: str = "", error: Optional[str] = None, execution_time_ms: Optional[int] = None,
                         grid_level: Optional[int] = None, notional: Optional[float] = None,
                         binance_response: Optional[Dict] = None):
        """Emir aksiyonunu logla"""
        try:
            order_log = OrderLog(
                timestamp=datetime.now(timezone.utc),
                strategy_id=strategy_id,
                strategy_type=strategy_type,
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                limit_price=limit_price,
                status=status,
                action=action,
                message=message,
                error=error,
                execution_time_ms=execution_time_ms,
                grid_level=grid_level,
                notional=notional,
                binance_response=binance_response
            )
            self.order_logger.log_order_action(order_log)
            
            # Binance alış veriş işlemlerini her zaman logla (LOG_LEVEL'dan bağımsız)
            if action in ["create", "cancel", "fill"] and status != "error":
                action_type = "ORDER"
                if action == "cancel":
                    action_type = "CANCEL"
                elif action == "fill":
                    action_type = side.value.upper()  # BUY veya SELL
                elif action == "create":
                    action_type = side.value.upper()  # BUY veya SELL
                
                log_binance_trading_action(
                    message,
                    action_type=action_type
                )
            elif status == "error":
                # Hataları da logla
                log_binance_trading_action(
                    f"HATA - {message}: {error}",
                    action_type="ERROR"
                )
                
        except Exception as e:
            logger.error(f"Order log hatası: {e}")


# Global Binance client instance
binance_client = BinanceClient()





