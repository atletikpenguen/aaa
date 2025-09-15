"""
FastAPI Web Uygulaması - Grid + OTT Trading Bot
"""

import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import pytz

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Form, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import uvicorn


# Core imports
from core.models import (
    Strategy, StrategyCreate, StrategyUpdate, StrategyResponse,
    State, DashboardStats, Symbol, Timeframe, OTTParams, StrategyType
)
from core.storage import storage
from core.binance import binance_client
from core.strategy_engine import strategy_engine
from core.utils import logger, generate_strategy_id, validate_symbol, validate_timeframe, setup_logger, clear_terminal_manual
from core.bol_grid_debug import get_bol_grid_debugger

# Environment variables yükle

# Terminal temizleme ayarları
TERMINAL_CLEAR_INTERVAL = int(os.getenv('TERMINAL_CLEAR_INTERVAL', '300'))  # 5 dakika varsayılan
logger = setup_logger(clear_interval=TERMINAL_CLEAR_INTERVAL)


# Background task manager
class BackgroundTaskManager:
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        self.paused = False  # Bekletme durumu
    
    async def start(self):
        """Background task manager'ı başlat"""
        self.running = True
        logger.info("Background task manager başlatıldı")
        
        # Ana koordinatör task'ını başlat
        self.tasks['coordinator'] = asyncio.create_task(self._coordinator_loop())
        
        # ⚡ YENİ: Order monitor task'ını başlat
        self.tasks['order_monitor'] = asyncio.create_task(self._order_monitor_loop())
    
    async def stop(self):
        """Background task manager'ı durdur"""
        self.running = False
        
        # Tüm task'ları iptal et
        for task_name, task in self.tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info(f"Task iptal edildi: {task_name}")
        
        self.tasks.clear()
        logger.info("Background task manager durduruldu")
    
    def pause(self):
        """Trading işlemlerini beklet"""
        self.paused = True
        logger.info("Trading işlemleri bekletildi")
    
    def resume(self):
        """Trading işlemlerini devam ettir"""
        self.paused = False
        logger.info("Trading işlemleri devam ettirildi")
    
    def is_paused(self):
        """Bekletme durumunu kontrol et"""
        return self.paused
    
    async def _coordinator_loop(self):
        """Ana koordinatör döngüsü - aktif stratejileri işle"""
        while self.running:
            try:
                # Bekletme durumunda ise sadece bekle
                if self.paused:
                    await asyncio.sleep(5)  # 5 saniye bekle
                    continue
                
                # Aktif stratejileri al
                strategies = await storage.load_strategies()
                active_strategies = [s for s in strategies if s.active]
                
                # Her aktif strateji için task başlat/kontrol et
                for strategy in active_strategies:
                    task_name = f"strategy_{strategy.id}"
                    
                    # Task yoksa veya bitmişse yeni başlat
                    if task_name not in self.tasks or self.tasks[task_name].done():
                        self.tasks[task_name] = asyncio.create_task(
                            self._strategy_loop(strategy)
                        )
                        logger.info(f"Strateji task başlatıldı: {strategy.id}")
                
                # Pasif olan stratejiler için task'ları durdur
                current_task_names = set(self.tasks.keys())
                for task_name in current_task_names:
                    if task_name.startswith('strategy_'):
                        strategy_id = task_name.replace('strategy_', '')
                        strategy_exists = any(s.id == strategy_id and s.active for s in active_strategies)
                        
                        if not strategy_exists and not self.tasks[task_name].done():
                            self.tasks[task_name].cancel()
                            try:
                                await self.tasks[task_name]
                            except asyncio.CancelledError:
                                pass
                            del self.tasks[task_name]
                            logger.info(f"Strateji task durduruldu: {strategy_id}")
                
                # 5 dakika bekle - coordinator çok sık çalışmasın
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Coordinator loop hatası: {e}")
                await asyncio.sleep(30)  # Hata durumunda daha uzun bekle
    
    async def _order_monitor_loop(self):
        """
        ⚡ Order Monitor - 30 saniyede bir emirleri kontrol et
        
        🎯 Hedef:
        - Hızlı fill detection (30s)
        - Timeout kontrolü (3dk)
        - Partial fill iptal
        """
        logger.info("🔍 Order Monitor başlatıldı - 30s aralıklarla kontrol")
        
        while self.running:
            try:
                # Aktif stratejileri al
                strategies = await storage.load_strategies()
                active_strategies = [s for s in strategies if s.active]
                
                # Monitor istatistikleri
                total_orders = 0
                total_fills = 0
                total_timeouts = 0
                total_partials = 0
                
                for strategy in active_strategies:
                    try:
                        # State'i yükle
                        state = await storage.load_state(strategy.id)
                        if not state or not state.open_orders:
                            continue
                        
                        total_orders += len(state.open_orders)
                        
                        # Order lifecycle management (unified strategy engine'den)
                        await strategy_engine.manage_order_lifecycle(strategy, state)
                        
                        # Fill kontrolü (unified)
                        filled_trades = await strategy_engine.check_order_fills(strategy, state)
                        total_fills += len(filled_trades)
                        
                        # State güncellemelerini kaydet
                        if filled_trades:
                            await storage.save_state(state)
                            
                    except Exception as e:
                        logger.error(f"❌ Order monitor {strategy.id} hatası: {e}")
                
                # Özet log (sadece aktivite varsa)
                if total_orders > 0:
                    logger.debug(f"🔍 Order Monitor: {len(active_strategies)} strateji, {total_orders} emir, {total_fills} fill")
                
                # 30 saniye bekle
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ Order monitor loop hatası: {e}")
                await asyncio.sleep(60)  # Hata durumunda 1 dakika bekle
    
    async def _strategy_loop(self, strategy: Strategy):
        """Tek strateji için döngü"""
        strategy_id = strategy.id
        active_check_counter = 0
        last_minute_report = datetime.now()
        
        try:
            # Grid engine'de stratejiyi aktif yap
            await strategy_engine.start_strategy(strategy_id)
            
            while self.running:
                try:
                    # Her 10 döngüde bir strateji aktif mi kontrol et (gereksiz storage çağrılarını azalt)
                    if active_check_counter % 10 == 0:
                        current_strategy = await storage.get_strategy(strategy_id)
                        if not current_strategy or not current_strategy.active:
                            logger.info(f"Strateji artık aktif değil: {strategy_id}")
                            break
                        strategy = current_strategy  # Güncel stratejiyi kullan
                    
                    active_check_counter += 1
                    
                    # Strategy tick işle
                    # Strategy engine ile tick işle (unified)
                    # State'i yükle
                    state = await storage.load_state(strategy.id)
                    if not state:
                        logger.warning(f"State bulunamadı: {strategy.id}")
                        await asyncio.sleep(60)
                        continue
                    
                    # Market verilerini al
                    current_price = await binance_client.get_current_price(strategy.symbol.value)
                    if not current_price:
                        logger.warning(f"Fiyat alınamadı: {strategy.symbol.value}")
                        await asyncio.sleep(60)
                        continue
                    
                    # OHLCV verilerini al
                    ohlcv_data = await binance_client.fetch_ohlcv(
                        strategy.symbol.value,
                        strategy.timeframe.value,
                        limit=max(100, strategy.ott.period + 10)
                    )
                    
                    market_data = {
                        'price': current_price,
                        'klines': ohlcv_data,
                        'volume_24h': 0.0,  # Şu an için 0
                        'price_change_24h': 0.0  # Şu an için 0
                    }
                    
                    # Strategy tick işle
                    result = await strategy_engine.process_strategy_tick(strategy)
                    
                    # process_strategy_tick boolean döndürüyor, dict'e çevir
                    if result:
                        # Başarılı işlem
                        logger.debug(f"Strateji işlendi: {strategy_id}")
                        
                        # Dakikada bir durum raporu
                        current_time = datetime.now()
                        if (current_time - last_minute_report).total_seconds() >= 60:
                            await self._log_strategy_status(strategy, {'status': 'processed'})
                            last_minute_report = current_time
                        
                        # Timeframe'e göre bekleme süresi
                        sleep_time = self._get_sleep_time(strategy.timeframe.value)
                        await asyncio.sleep(sleep_time)
                    else:
                        # İşlem yapılmadı, normal bekleme
                        sleep_time = self._get_sleep_time(strategy.timeframe.value)
                        await asyncio.sleep(sleep_time)
                
                except Exception as e:
                    logger.error(f"Strateji loop hatası {strategy_id}: {e}")
                    await asyncio.sleep(60)
        
        except asyncio.CancelledError:
            logger.info(f"Strateji loop iptal edildi: {strategy_id}")
        except Exception as e:
            logger.error(f"Strateji loop genel hatası {strategy_id}: {e}")
        finally:
            # Grid engine'de stratejiyi pasif yap
            await strategy_engine.stop_strategy(strategy_id)
    
    def _get_sleep_time(self, timeframe: str) -> int:
        """Timeframe'e göre uygun bekleme süresi - tüm timeframe'ler için 1 dakika"""
        sleep_map = {
            '1m': 60,   # 1 dakika
            '5m': 60,   # 1 dakika
            '15m': 60,  # 1 dakika
            '1h': 60,   # 1 dakika
            '1d': 60    # 1 dakika
        }
        return sleep_map.get(timeframe, 60)
    
    async def _log_strategy_status(self, strategy: Strategy, result: dict):
        """Dakikalık strateji durum raporu"""
        try:
            # State bilgisini al
            state = await storage.load_state(strategy.id)
            if not state:
                return
                
            # Güncel fiyat al
            current_price = await binance_client.get_current_price(strategy.symbol.value)
            if not current_price:
                return
                
            # GF farkını hesapla
            price_gf_diff = current_price - state.gf if state.gf and state.gf > 0 else 0
            price_gf_diff_pct = (price_gf_diff / state.gf * 100) if state.gf and state.gf > 0 else 0
            
            # Açık emir sayısı
            open_orders_count = len(state.open_orders)
            
            # Durum mesajı
            status_msg = f"📊 {strategy.name} ({strategy.symbol.value}): "
            status_msg += f"Fiyat=${current_price:.6f}, GF=${state.gf:.6f}, "
            status_msg += f"Fark={price_gf_diff:+.6f} ({price_gf_diff_pct:+.2f}%), "
            status_msg += f"Emirler={open_orders_count}"
            
            logger.info(status_msg)
            
        except Exception as e:
            logger.debug(f"Durum raporu hatası {strategy.id}: {e}")

# Global background task manager
task_manager = BackgroundTaskManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifecycle - startup ve shutdown"""
    # Startup
    logger.info("Trading bot başlatılıyor...")
    
    # Eski log dosyalarını temizle (30 günden eski)
    try:
        from core.utils import cleanup_old_logs
        cleanup_old_logs(30)
        logger.info("✅ Eski log dosyaları temizlendi")
    except Exception as e:
        logger.warning(f"Log temizleme hatası: {e}")
    
    # Background task manager'ı başlat
    await task_manager.start()
    
    yield
    
    # Shutdown
    logger.info("Trading bot kapatılıyor...")
    
    # Background task manager'ı durdur
    await task_manager.stop()
    
    # Tüm stratejileri temizle
    strategies = await storage.load_strategies()
    for strategy in strategies:
        if strategy.active:
            await strategy_engine.cleanup_strategy(strategy.id)

# FastAPI uygulaması
app = FastAPI(
    title="Grid + OTT Trading Bot",
    description="Binance USDⓈ-M Futures Grid Trading Bot with OTT Indicator",
    version="1.0.0",
    lifespan=lifespan
)

# Static files ve templates (VPS deployment için paths helper kullan)
from core.paths import get_static_dir, get_templates_dir
app.mount("/static", StaticFiles(directory=get_static_dir()), name="static")
templates = Jinja2Templates(directory=get_templates_dir())

# Jinja2 template filters
def format_number(value, decimals=8):
    """Sayı formatla"""
    if value is None:
        return "0"
    try:
        return f"{float(value):.{decimals}f}".rstrip('0').rstrip('.')
    except:
        return str(value)

def format_datetime(value):
    """Datetime formatla - İstanbul zaman dilimine göre"""
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        
        # UTC timezone yoksa ekle
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        elif value.tzinfo != timezone.utc:
            # Zaten UTC değilse UTC'ye çevir
            value = value.astimezone(timezone.utc)
        
        # İstanbul zaman dilimine çevir
        istanbul_tz = pytz.timezone('Europe/Istanbul')
        istanbul_time = value.astimezone(istanbul_tz)
        
        return istanbul_time.strftime("%d.%m.%Y %H:%M:%S")
    except Exception as e:
        return str(value)

def format_date_only(value):
    """Sadece tarih formatla - İstanbul zaman dilimine göre"""
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        
        # UTC timezone yoksa ekle
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        elif value.tzinfo != timezone.utc:
            value = value.astimezone(timezone.utc)
        
        # İstanbul zaman dilimine çevir
        istanbul_tz = pytz.timezone('Europe/Istanbul')
        istanbul_time = value.astimezone(istanbul_tz)
        
        return istanbul_time.strftime("%d.%m.%Y")
    except Exception as e:
        return str(value)

def format_time_only(value):
    """Sadece saat formatla - İstanbul zaman dilimine göre"""
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        
        # UTC timezone yoksa ekle
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        elif value.tzinfo != timezone.utc:
            value = value.astimezone(timezone.utc)
        
        # İstanbul zaman dilimine çevir
        istanbul_tz = pytz.timezone('Europe/Istanbul')
        istanbul_time = value.astimezone(istanbul_tz)
        
        return istanbul_time.strftime("%H:%M:%S")
    except Exception as e:
        return str(value)

def get_istanbul_now():
    """İstanbul zamanını al"""
    istanbul_tz = pytz.timezone('Europe/Istanbul')
    return datetime.now(istanbul_tz)

templates.env.filters["format_number"] = format_number
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_date_only"] = format_date_only
templates.env.filters["format_time_only"] = format_time_only
templates.env.globals["get_istanbul_now"] = get_istanbul_now

# ============= WEB ROUTES =============

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, strategy_filter: Optional[str] = None):
    """Ana dashboard"""
    try:
        # Stratejileri yükle
        strategies = await storage.load_strategies()
        
        # Dashboard istatistikleri
        active_count = sum(1 for s in strategies if s.active)
        total_open_orders = 0
        
        # Her strateji için state bilgisi al
        strategy_summaries = []
        for strategy in strategies:
            state = await storage.load_state(strategy.id)
            
            # Son 24 saat trade sayısı
            trades_today = 0
            try:
                trades = await storage.load_trades(strategy.id, limit=100)
                today = datetime.now(timezone.utc).date()
                trades_today = sum(1 for t in trades if t.timestamp.date() == today)
            except:
                pass
            
            # Kar-zarar istatistikleri al
            pnl_stats = None
            try:
                pnl_stats = await storage.calculate_realized_pnl(strategy.id)
            except Exception as e:
                logger.warning(f"PnL hesaplama hatası {strategy.id}: {e}")
                pnl_stats = {
                    'realized_pnl': 0.0,
                    'total_profit': 0.0,
                    'total_loss': 0.0,
                    'win_rate': 0.0,
                    'profit_trades': 0,
                    'loss_trades': 0
                }
            
            total_open_orders += len(state.open_orders) if state else 0
            
            # Güncel fiyat al (cache için)
            current_price = None
            ott_mode = None
            price_gf_diff = None
            price_gf_diff_pct = None
            
            try:
                current_price = await binance_client.get_current_price(strategy.symbol.value)
                
                # OTT hesaplama için OHLCV verisi al
                if current_price:
                    try:
                        ohlcv_data = await binance_client.fetch_ohlcv(
                            strategy.symbol.value,
                            strategy.timeframe.value,
                            limit=max(100, strategy.ott.period + 10)
                        )
                        
                        if ohlcv_data:
                            from core.indicators import calculate_ott
                            close_prices = [float(bar[4]) for bar in ohlcv_data[:-1]]
                            ott_result = calculate_ott(close_prices, strategy.ott.period, strategy.ott.opt, strategy.name)
                            
                            if ott_result:
                                ott_mode = ott_result.mode.value
                    except:
                        pass
                
                # Fiyat-GF farkı hesapla
                if current_price and state and state.gf and state.gf > 0:
                    price_gf_diff = current_price - state.gf
                    price_gf_diff_pct = (price_gf_diff / state.gf) * 100
                    
            except:
                pass
            
            # DCA stratejileri için ek bilgiler
            dca_info = {}
            if strategy.strategy_type.value == 'dca_ott' and state:
                # Döngü sayısı ve işlem sayacı
                dca_info['cycle_number'] = state.cycle_number
                dca_info['cycle_trade_count'] = state.cycle_trade_count
                
                if state.dca_positions:
                    # İlk alım fiyatı
                    first_position = min(state.dca_positions, key=lambda x: x.timestamp)
                    dca_info['first_buy_price'] = first_position.buy_price
                    
                    # Son alım fiyatı
                    last_position = max(state.dca_positions, key=lambda x: x.timestamp)
                    dca_info['last_buy_price'] = last_position.buy_price
                    
                    # Pozisyon sayısı
                    dca_info['position_count'] = len(state.dca_positions)
                else:
                    dca_info['first_buy_price'] = None
                    dca_info['last_buy_price'] = None
                    dca_info['position_count'] = 0
            
            # Hata sayısını al
            error_count = strategy_engine.get_error_count(strategy.id)
            
            strategy_summaries.append({
                'strategy': strategy,
                'state': state,
                'current_price': current_price,
                'ott_mode': ott_mode,
                'price_gf_diff': price_gf_diff,
                'price_gf_diff_pct': price_gf_diff_pct,
                'trades_today': trades_today,
                'pnl_stats': pnl_stats,
                'is_running': task_manager.tasks.get(f'strategy_{strategy.id}') is not None,
                'dca_info': dca_info,
                'error_count': error_count
            })
        
        # Toplam kar-zarar hesapla
        total_realized_pnl = sum(s['pnl_stats']['realized_pnl'] for s in strategy_summaries if s['pnl_stats'])
        
        stats = DashboardStats(
            total_strategies=len(strategies),
            active_strategies=active_count,
            total_open_orders=total_open_orders,
            total_trades_today=sum(s['trades_today'] for s in strategy_summaries),
            total_profit_today=total_realized_pnl  # Gerçekleşen toplam kar-zarar
        )
        
        # Son işlemleri getir ve zenginleştir
        if strategy_filter and strategy_filter != "all":
            # Belirli strateji seçili
            recent_trades_raw = await storage.load_trades(strategy_filter, limit=20)
        else:
            # Tüm stratejiler seçili
            recent_trades_raw = await storage.load_all_trades(limit=20)
        
        recent_trades = await storage.enrich_trades_with_grid_data(recent_trades_raw)
        
        # Açık emirleri topla
        open_orders_summary = []
        for strategy in strategies:
            if strategy.active:
                state = await storage.load_state(strategy.id)
                if state and state.open_orders:
                    for order in state.open_orders:
                        # Emir tipini belirle
                        order_type = "LIMIT" if order.price else "MARKET"
                        
                        # Emir durumunu belirle (Binance'den güncel bilgi al)
                        try:
                            order_status = await binance_client.check_order_status_detailed(
                                strategy.symbol.value, 
                                [order.order_id]
                            )
                            if order_status:
                                order_detail = order_status[0]
                                filled_qty = order_detail.get('filled_qty', 0)
                                remaining_qty = order_detail.get('remaining_qty', order.quantity)
                                fill_percentage = (filled_qty / order.quantity * 100) if order.quantity > 0 else 0
                                status_text = f"{fill_percentage:.1f}% dolu ({filled_qty:.6f}/{order.quantity:.6f})"
                            else:
                                status_text = "Kontrol ediliyor..."
                        except Exception as e:
                            logger.warning(f"Emir durumu kontrol hatası {order.order_id}: {e}")
                            status_text = "Durum bilinmiyor"
                        
                        open_orders_summary.append({
                            'strategy_name': strategy.name,
                            'strategy_id': strategy.id,
                            'symbol': strategy.symbol.value,
                            'side': order.side.value,
                            'quantity': order.quantity,
                            'price': order.price,
                            'order_type': order_type,
                            'status': status_text,
                            'timestamp': order.timestamp,
                            'z': order.z
                        })
        
        # Açık emirleri zamana göre sırala (en yeni üstte)
        open_orders_summary.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "strategies": strategy_summaries,
                "stats": stats,
                "recent_trades": recent_trades,
                "open_orders": open_orders_summary,
                "symbols": [s.value for s in Symbol],
                "timeframes": [t.value for t in Timeframe],
                "datetime": datetime,
                "selected_strategy_filter": strategy_filter or "all"
            }
        )
        
    except Exception as e:
        logger.error(f"Dashboard hatası: {e}")
        raise HTTPException(status_code=500, detail="Dashboard yüklenemedi")

@app.get("/strategies/{strategy_id}", response_class=HTMLResponse)
async def strategy_detail(request: Request, strategy_id: str):
    """Strateji detay sayfası"""
    try:
        # Strateji ve state yükle
        strategy = await storage.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strateji bulunamadı")
        
        state = await storage.load_state(strategy_id)
        
        # Son trades'leri al
        recent_trades = await storage.load_trades(strategy_id, limit=50)
        
        # Trade istatistikleri
        trade_stats = await storage.get_trade_statistics(strategy_id)
        
        # Güncel market bilgisi
        current_price = None
        ott_mode = None
        delta = None
        target_z = None
        target_price = None
        
        try:
            # Güncel fiyat
            current_price = await binance_client.get_current_price(strategy.symbol.value)
            
            # Son OTT hesaplama
            if current_price and state and state.gf and state.gf > 0:
                # OHLCV al
                ohlcv_data = await binance_client.fetch_ohlcv(
                    strategy.symbol.value,
                    strategy.timeframe.value,
                    limit=max(100, strategy.ott.period + 10)
                )
                
                if ohlcv_data:
                    from core.indicators import calculate_ott
                    close_prices = [float(bar[4]) for bar in ohlcv_data[:-1]]
                    ott_result = calculate_ott(close_prices, strategy.ott.period, strategy.ott.opt, strategy.name)
                    
                    if ott_result:
                        ott_mode = ott_result.mode.value
                        delta = abs(current_price - state.gf)
                        
                        # Hedef z hesapla
                        if ott_result.mode.value == "AL" and current_price < state.gf:
                            delta_calc = state.gf - current_price
                            if delta_calc > strategy.y:
                                target_z = int(delta_calc // strategy.y)
                                target_price = state.gf - (target_z * strategy.y)
                        elif ott_result.mode.value == "SAT" and current_price > state.gf:
                            delta_calc = current_price - state.gf
                            if delta_calc > strategy.y:
                                target_z = int(delta_calc // strategy.y)
                                target_price = state.gf + (target_z * strategy.y)
        except Exception as e:
            logger.warning(f"Market bilgisi alma hatası: {e}")
        
        # Task durumu
        is_running = task_manager.tasks.get(f'strategy_{strategy_id}') is not None
        
        return templates.TemplateResponse(
            "detail.html",
            {
                "request": request,
                "strategy": strategy,
                "state": state,
                "current_price": current_price,
                "ott_mode": ott_mode,
                "delta": delta,
                "target_z": target_z,
                "target_price": target_price,
                "recent_trades": recent_trades,
                "trade_stats": trade_stats,
                "is_running": is_running
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strateji detay hatası: {e}")
        raise HTTPException(status_code=500, detail="Strateji detayları yüklenemedi")

# ============= API ROUTES =============

@app.get("/api/strategies", response_model=List[StrategyResponse])
async def get_strategies():
    """Tüm stratejileri listele"""
    try:
        strategies = await storage.load_strategies()
        
        response = []
        for strategy in strategies:
            state = await storage.load_state(strategy.id)
            
            # Güncel fiyat al
            current_price = None
            try:
                current_price = await binance_client.get_current_price(strategy.symbol.value)
            except:
                pass
            
            response.append(StrategyResponse(
                strategy=strategy,
                state=state,
                current_price=current_price
            ))
        
        return response
        
    except Exception as e:
        logger.error(f"Stratejiler listesi hatası: {e}")
        raise HTTPException(status_code=500, detail="Stratejiler listelenemedi")

@app.post("/api/strategies", response_model=StrategyResponse)
async def create_strategy(strategy_data: StrategyCreate):
    """Yeni strateji oluştur"""
    try:
        # Validation
        if not validate_symbol(strategy_data.symbol.value):
            raise HTTPException(status_code=400, detail="Geçersiz sembol")
        
        if not validate_timeframe(strategy_data.timeframe.value):
            raise HTTPException(status_code=400, detail="Geçersiz timeframe")
        
        # Market bilgisi kontrol et
        market_info = await binance_client.get_market_info(strategy_data.symbol.value)
        if not market_info:
            raise HTTPException(status_code=400, detail="Market bilgisi alınamadı")
        
        # Fiyat limitleri validasyonu
        if (strategy_data.price_min is not None and strategy_data.price_min > 0 and 
            strategy_data.price_max is not None and strategy_data.price_max > 0):
            if strategy_data.price_min >= strategy_data.price_max:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Minimum fiyat ({strategy_data.price_min}) maksimum fiyattan ({strategy_data.price_max}) büyük veya eşit olamaz"
                )

        # Strategy oluştur
        strategy_id = generate_strategy_id()
        
        # Strateji tipine göre parametreleri hazırla
        parameters = strategy_data.parameters.copy()
        
        # Grid+OTT için özel parametreler
        if strategy_data.strategy_type == StrategyType.GRID_OTT:
            if strategy_data.y is not None:
                parameters['y'] = strategy_data.y
            if strategy_data.usdt_grid is not None:
                parameters['usdt_grid'] = strategy_data.usdt_grid
        
        # DCA+OTT için özel parametreler
        elif strategy_data.strategy_type == StrategyType.DCA_OTT:
            if strategy_data.base_usdt is not None:
                parameters['base_usdt'] = strategy_data.base_usdt
            elif 'base_usdt' not in parameters:
                parameters['base_usdt'] = 100.0  # Varsayılan
            
            if strategy_data.dca_multiplier is not None:
                parameters['dca_multiplier'] = strategy_data.dca_multiplier
            elif 'dca_multiplier' not in parameters:
                parameters['dca_multiplier'] = 1.5  # Varsayılan
                
            if strategy_data.min_drop_pct is not None:
                parameters['min_drop_pct'] = strategy_data.min_drop_pct
            elif 'min_drop_pct' not in parameters:
                parameters['min_drop_pct'] = 2.0  # Varsayılan
        
        # BOL-Grid için özel parametreler
        elif strategy_data.strategy_type == StrategyType.BOL_GRID:
            if strategy_data.initial_usdt is not None:
                parameters['initial_usdt'] = strategy_data.initial_usdt
            elif 'initial_usdt' not in parameters:
                parameters['initial_usdt'] = 100.0  # Varsayılan
            
            if strategy_data.min_drop_pct is not None:
                parameters['min_drop_pct'] = strategy_data.min_drop_pct
            elif 'min_drop_pct' not in parameters:
                parameters['min_drop_pct'] = 2.0  # Varsayılan
                
            if strategy_data.min_profit_pct is not None:
                parameters['min_profit_pct'] = strategy_data.min_profit_pct
            elif 'min_profit_pct' not in parameters:
                parameters['min_profit_pct'] = 1.0  # Varsayılan
                
            if strategy_data.bollinger_period is not None:
                parameters['bollinger_period'] = strategy_data.bollinger_period
            elif 'bollinger_period' not in parameters:
                parameters['bollinger_period'] = 250  # Varsayılan
                
            if strategy_data.bollinger_std is not None:
                parameters['bollinger_std'] = strategy_data.bollinger_std
            elif 'bollinger_std' not in parameters:
                parameters['bollinger_std'] = 2.0  # Varsayılan
            
            # BOL-Grid için OTT değerlerini varsayılan yap (kullanılmaz ama gerekli)
            if not strategy_data.ott_period:
                strategy_data.ott_period = 14  # Varsayılan
            if not strategy_data.ott_opt:
                strategy_data.ott_opt = 2.0  # Varsayılan
        
        strategy = Strategy(
            id=strategy_id,
            name=strategy_data.name,
            symbol=strategy_data.symbol,
            timeframe=strategy_data.timeframe,
            strategy_type=strategy_data.strategy_type,
            parameters=parameters,
            y=strategy_data.y,  # Legacy uyumluluk
            usdt_grid=strategy_data.usdt_grid,  # Legacy uyumluluk
            gf=strategy_data.gf,  # Legacy uyumluluk
            price_min=strategy_data.price_min,
            price_max=strategy_data.price_max,
            ott=OTTParams(
                period=strategy_data.ott_period,
                opt=strategy_data.ott_opt
            ),
            active=False  # Manuel başlatma
        )
        
        # Strateji konfigürasyonunu validate et
        is_valid, validation_message = await strategy_engine.validate_strategy(strategy)
        if not is_valid:
            raise HTTPException(status_code=400, detail=validation_message)
        
        # Kaydet
        await storage.save_strategy(strategy)
        
        # İlk state oluştur (unified)
        initial_state = await strategy_engine.initialize_strategy_state(strategy)
        await storage.save_state(initial_state)
        
        logger.info(f"Yeni strateji oluşturuldu: {strategy_id}")
        
        return StrategyResponse(
            strategy=strategy,
            state=initial_state
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strateji oluşturma hatası: {e}")
        raise HTTPException(status_code=500, detail="Strateji oluşturulamadı")

@app.post("/api/strategies/{strategy_id}/start")
async def start_strategy(strategy_id: str):
    """Stratejiyi başlat"""
    try:
        strategy = await storage.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strateji bulunamadı")
        
        # Stratejiyi aktif yap
        strategy.active = True
        await storage.save_strategy(strategy)
        
        logger.info(f"Strateji başlatıldı: {strategy_id}")
        
        return {"status": "started", "strategy_id": strategy_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strateji başlatma hatası: {e}")
        raise HTTPException(status_code=500, detail="Strateji başlatılamadı")

@app.post("/api/strategies/{strategy_id}/stop")
async def stop_strategy(strategy_id: str):
    """Stratejiyi durdur"""
    try:
        strategy = await storage.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strateji bulunamadı")
        
        # Stratejiyi pasif yap
        strategy.active = False
        await storage.save_strategy(strategy)
        
        # Açık emirleri iptal et
        await strategy_engine.cleanup_strategy(strategy_id)
        
        logger.info(f"Strateji durduruldu: {strategy_id}")
        
        return {"status": "stopped", "strategy_id": strategy_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strateji durdurma hatası: {e}")
        raise HTTPException(status_code=500, detail="Strateji durdurulamadı")

@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    """Strateji sil"""
    try:
        strategy = await storage.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strateji bulunamadı")
        
        # Önce durdur
        if strategy.active:
            strategy.active = False
            await storage.save_strategy(strategy)
            await strategy_engine.cleanup_strategy(strategy_id)
        
        # Sil
        await storage.delete_strategy(strategy_id)
        
        logger.info(f"Strateji silindi: {strategy_id}")
        
        return {"status": "deleted", "strategy_id": strategy_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strateji silme hatası: {e}")
        raise HTTPException(status_code=500, detail="Strateji silinemedi")

@app.put("/api/strategies/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(strategy_id: str, strategy_data: StrategyUpdate):
    """Strateji güncelle"""
    try:
        # Mevcut stratejiyi al
        strategy = await storage.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strateji bulunamadı")
        
        # Fiyat limitleri validasyonu
        price_min = strategy_data.price_min if strategy_data.price_min is not None else strategy.price_min
        price_max = strategy_data.price_max if strategy_data.price_max is not None else strategy.price_max
        
        if (price_min is not None and price_min > 0 and 
            price_max is not None and price_max > 0):
            if price_min >= price_max:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Minimum fiyat ({price_min}) maksimum fiyattan ({price_max}) büyük veya eşit olamaz"
                )
        
        # Güncelleme için alanları belirle
        update_data = {}
        if strategy_data.name is not None:
            update_data["name"] = strategy_data.name
        if strategy_data.y is not None:
            update_data["y"] = strategy_data.y
        if strategy_data.usdt_grid is not None:
            update_data["usdt_grid"] = strategy_data.usdt_grid
        if strategy_data.gf is not None:
            update_data["gf"] = strategy_data.gf
        if strategy_data.price_min is not None:
            update_data["price_min"] = strategy_data.price_min if strategy_data.price_min > 0 else None
        if strategy_data.price_max is not None:
            update_data["price_max"] = strategy_data.price_max if strategy_data.price_max > 0 else None
        if strategy_data.ott_period is not None:
            strategy.ott.period = strategy_data.ott_period
        if strategy_data.ott_opt is not None:
            strategy.ott.opt = strategy_data.ott_opt
        
        # Strateji objesi güncelle
        for key, value in update_data.items():
            setattr(strategy, key, value)
        
        strategy.updated_at = datetime.now()
        
        # Kaydet
        await storage.save_strategy(strategy)
        
        logger.info(f"Strateji güncellendi: {strategy_id}")
        
        return StrategyResponse(
            strategy=strategy
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strateji güncelleme hatası: {e}")
        raise HTTPException(status_code=500, detail="Strateji güncellenemedi")

@app.get("/api/strategies/{strategy_id}/trades.csv")
async def download_trades_csv(strategy_id: str):
    """Trade geçmişi CSV indir"""
    try:
        csv_content = await storage.get_trades_csv_content(strategy_id)
        if not csv_content:
            raise HTTPException(status_code=404, detail="Trade verileri bulunamadı")
        
        def iter_csv():
            yield csv_content.encode('utf-8')
        
        return StreamingResponse(
            iter_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=trades_{strategy_id}.csv"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CSV indirme hatası: {e}")
        raise HTTPException(status_code=500, detail="CSV indirilemedi")

# ============= BOL-GRID DEBUG ENDPOINTS =============

@app.get("/api/strategies/{strategy_id}/bol-grid-debug")
async def get_bol_grid_debug(strategy_id: str):
    """BOL-Grid stratejisi için debug bilgilerini getir"""
    try:
        # Strateji var mı kontrol et
        strategy = await storage.load_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strateji bulunamadı")
        
        if strategy.strategy_type != StrategyType.BOL_GRID:
            raise HTTPException(status_code=400, detail="Bu strateji BOL-Grid değil")
        
        # Debug bilgilerini getir
        debugger = get_bol_grid_debugger(strategy_id)
        recent_analysis = debugger.get_recent_analysis(50)
        cycle_summary = debugger.get_cycle_summary()
        
        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy.name,
            "recent_analysis": recent_analysis,
            "cycle_summary": cycle_summary,
            "debug_files": {
                "debug_log": f"logs/bol_grid_debug_{strategy_id}.log",
                "analysis_json": f"logs/bol_grid_analysis_{strategy_id}.json"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"BOL-Grid debug bilgisi alma hatası: {e}")
        raise HTTPException(status_code=500, detail="Debug bilgisi alınamadı")

@app.get("/api/strategies/{strategy_id}/bol-grid-debug/log")
async def get_bol_grid_debug_log(strategy_id: str):
    """BOL-Grid debug log dosyasını getir"""
    try:
        # Strateji var mı kontrol et
        strategy = await storage.load_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strateji bulunamadı")
        
        if strategy.strategy_type != StrategyType.BOL_GRID:
            raise HTTPException(status_code=400, detail="Bu strateji BOL-Grid değil")
        
        debug_file = f"logs/bol_grid_debug_{strategy_id}.log"
        
        if not os.path.exists(debug_file):
            return {"content": "Debug log dosyası henüz oluşturulmamış."}
        
        with open(debug_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {"content": content}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"BOL-Grid debug log alma hatası: {e}")
        raise HTTPException(status_code=500, detail="Debug log alınamadı")

# ============= FORM ROUTES (Web UI için) =============

@app.post("/strategies", response_class=HTMLResponse)
async def create_strategy_form(
    request: Request,
    name: str = Form(...),
    symbol: str = Form(...),
    timeframe: str = Form(...),
    strategy_type: str = Form(default="grid_ott"),
    # Grid+OTT parametreleri
    y: Optional[str] = Form(None),
    usdt_grid: Optional[str] = Form(None),
    gf: Optional[str] = Form(None),
    # DCA+OTT parametreleri
    base_usdt: Optional[str] = Form(None),
    dca_multiplier: Optional[str] = Form(None),
    min_drop_pct: Optional[str] = Form(None),
    # BOL-Grid parametreleri
    initial_usdt: Optional[str] = Form(None),
    min_profit_pct: Optional[str] = Form(None),
    bollinger_period: Optional[str] = Form(None),
    bollinger_std: Optional[str] = Form(None),
    # Ortak parametreler
    price_min: Optional[str] = Form(None),
    price_max: Optional[str] = Form(None),
    ott_period: int = Form(14),
    ott_opt: float = Form(2.0)
):
    """Form'dan strateji oluştur"""
    try:
        # String değerleri float'a çevir (boş string'leri None yap)
        def parse_float(value: Optional[str]) -> Optional[float]:
            if value is None or value.strip() == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None
        
        # StrategyCreate objesi oluştur
        strategy_data = StrategyCreate(
            name=name,
            symbol=symbol,  # Pydantic otomatik convert eder
            timeframe=timeframe,  # Pydantic otomatik convert eder
            strategy_type=strategy_type,  # Pydantic otomatik convert eder
            y=parse_float(y),
            usdt_grid=parse_float(usdt_grid),
            gf=parse_float(gf) if parse_float(gf) is not None else 0,
            base_usdt=parse_float(base_usdt),
            dca_multiplier=parse_float(dca_multiplier),
            min_drop_pct=parse_float(min_drop_pct),
            # BOL-Grid parametreleri
            initial_usdt=parse_float(initial_usdt),
            min_profit_pct=parse_float(min_profit_pct),
            bollinger_period=int(parse_float(bollinger_period)) if parse_float(bollinger_period) else None,
            bollinger_std=parse_float(bollinger_std),
            price_min=parse_float(price_min) if parse_float(price_min) and parse_float(price_min) > 0 else None,
            price_max=parse_float(price_max) if parse_float(price_max) and parse_float(price_max) > 0 else None,
            # BOL-Grid için OTT değerleri varsayılan (kullanılmaz)
            ott_period=14 if strategy_type == 'bol_grid' else ott_period,
            ott_opt=2.0 if strategy_type == 'bol_grid' else ott_opt
        )
        
        # API endpoint'ini çağır
        await create_strategy(strategy_data)
        
        # Dashboard'a redirect (HTMX için)
        return HTMLResponse(
            status_code=200,
            content="""
            <div hx-get="/" hx-target="body" hx-trigger="load"></div>
            <script>window.location.href = '/';</script>
            """
        )
        
    except Exception as e:
        logger.error(f"Form strateji oluşturma hatası: {e}")
        error_message = str(e)
        
        # Pydantic validation hatalarını daha okunabilir hale getir
        if "validation error" in error_message.lower():
            error_message = "Form verilerinde hata var. Lütfen tüm zorunlu alanları doldurun."
        
        return HTMLResponse(
            status_code=400,
            content=f"""
            <div class="bg-red-50 border border-red-200 rounded-md p-4 mb-4">
                <div class="flex">
                    <div class="flex-shrink-0">
                        <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                        </svg>
                    </div>
                    <div class="ml-3">
                        <h3 class="text-sm font-medium text-red-800">Strateji Oluşturulamadı</h3>
                        <div class="mt-2 text-sm text-red-700">
                            <p>{error_message}</p>
                        </div>
                    </div>
                </div>
            </div>
            <script>
                // Modal'ı kapatma, sadece hata mesajını göster
                document.querySelector('.modal-content').innerHTML = document.querySelector('.modal-content').innerHTML + arguments[0];
            </script>
            """
        )

@app.post("/strategies/update", response_class=HTMLResponse)
async def update_strategy_form(
    request: Request,
    strategy_id: str = Form(...),
    method_override: str = Form(..., alias="method_override"),
    name: str = Form(...),
    y: float = Form(...),
    usdt_grid: float = Form(...),
    gf: float = Form(0),
    price_min: Optional[float] = Form(None),
    price_max: Optional[float] = Form(None),
    ott_period: int = Form(14),
    ott_opt: float = Form(2.0)
):
    """Form'dan strateji güncelle"""
    try:
        # StrategyUpdate objesi oluştur
        strategy_data = StrategyUpdate(
            name=name,
            y=y,
            usdt_grid=usdt_grid,
            gf=gf,
            price_min=price_min if price_min and price_min > 0 else None,
            price_max=price_max if price_max and price_max > 0 else None,
            ott_period=ott_period,
            ott_opt=ott_opt
        )
        
        # API endpoint'ini çağır
        await update_strategy(strategy_id, strategy_data)
        
        # Dashboard'a redirect (HTMX için)
        return HTMLResponse(
            status_code=200,
            content="""
            <div hx-get="/" hx-target="body" hx-trigger="load"></div>
            <script>window.location.href = '/';</script>
            """
        )
        
    except Exception as e:
        logger.error(f"Form strateji güncelleme hatası: {e}")
        return HTMLResponse(
            status_code=400,
            content=f"<div class='alert alert-danger'>Hata: {str(e)}</div>"
        )

# ============= HEALTH CHECK =============

@app.get("/api/stream")
async def stream_strategy_updates(request: Request):
    """Server-Sent Events stream for real-time strategy updates"""
    
    async def event_generator():
        last_update = datetime.now()
        last_strategy_load = datetime.now()
        cached_strategies = []
        
        while True:
            try:
                # Client bağlantısı koptu mu kontrol et
                if await request.is_disconnected():
                    break
                
                # Stratejileri 2 dakikada bir yükle (cache kullan)
                current_time = datetime.now()
                if (current_time - last_strategy_load).total_seconds() > 120:
                    cached_strategies = await storage.load_strategies()
                    last_strategy_load = current_time
                
                active_strategies = [s for s in cached_strategies if s.active]
                
                if not active_strategies:
                    await asyncio.sleep(5)
                    continue
                
                # Güncellenmiş veri var mı kontrol et - 1 dakikada bir güncelle
                if (current_time - last_update).total_seconds() < 60:  # 60 saniye minimum
                    await asyncio.sleep(5)
                    continue
                
                # Strateji özetlerini hazırla
                updates = []
                for strategy in active_strategies[:3]:  # İlk 3 strateji
                    try:
                        state = await storage.load_state(strategy.id)
                        current_price = await binance_client.get_current_price(strategy.symbol.value)
                        
                        if current_price and state:
                            price_gf_diff = current_price - state.gf if state.gf and state.gf > 0 else 0
                            updates.append({
                                'id': strategy.id,
                                'name': strategy.name,
                                'symbol': strategy.symbol.value,
                                'price': round(current_price, 6),
                                'gf': round(state.gf, 6) if state.gf and state.gf > 0 else 0,
                                'diff': round(price_gf_diff, 6),
                                'open_orders': len(state.open_orders)
                            })
                    except:
                        continue
                
                if updates:
                    # Son işlemleri de dahil et
                    recent_trades_data = []
                    try:
                        recent_trades = await storage.load_all_trades(limit=10)
                        # Stratejileri yükle (strategy_type için)
                        strategies = await storage.load_strategies()
                        strategy_map = {s.id: s for s in strategies}
                        
                        recent_trades_data = []
                        for trade in recent_trades:
                            strategy = strategy_map.get(trade.strategy_id)
                            strategy_type = strategy.strategy_type.value if strategy else 'unknown'
                            
                            recent_trades_data.append({
                                'timestamp': trade.timestamp.isoformat(),
                                'strategy_id': trade.strategy_id,
                                'strategy_type': strategy_type,
                                'side': trade.side.value,
                                'price': round(trade.price, 6),
                                'quantity': round(trade.quantity, 6),
                                'notional': round(trade.notional, 2),
                                'z': trade.z,
                                'cycle_info': trade.cycle_info,
                                'order_id': trade.order_id[:12] + '...' if trade.order_id else None
                            })
                    except:
                        pass
                    
                    # JSON formatında gönder
                    yield {
                        "event": "strategy_update", 
                        "data": json.dumps({
                            'timestamp': current_time.isoformat(),
                            'strategies': updates,
                            'recent_trades': recent_trades_data
                        })
                    }
                    last_update = current_time
                
                await asyncio.sleep(30)  # 30 saniye bekle - daha responsive
                
            except Exception as e:
                logger.error(f"SSE stream hatası: {e}")
                await asyncio.sleep(10)
    
    return EventSourceResponse(event_generator())

@app.get("/health")
async def health_check():
    """Sistem durumu kontrolü"""
    try:
        # Binance bağlantısı
        binance_connected = binance_client.is_connected()
        
        # Storage testi
        strategies = await storage.load_strategies()
        storage_ok = True
        
        # Task manager durumu
        task_manager_ok = task_manager.running
        
        return {
            "status": "healthy" if all([binance_connected, storage_ok, task_manager_ok]) else "unhealthy",
            "binance_connected": binance_connected,
            "storage_ok": storage_ok,
            "task_manager_running": task_manager_ok,
            "active_strategies": len([s for s in strategies if s.active]),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check hatası: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@app.post("/api/terminal/clear")
async def clear_terminal():
    """Terminali manuel olarak temizle"""
    try:
        clear_terminal_manual()
        return {"status": "success", "message": "Terminal temizlendi"}
    except Exception as e:
        logger.error(f"Terminal temizleme hatası: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/logs/clear")
async def clear_logs():
    """Log dosyalarını temizle"""
    try:
        import shutil
        from pathlib import Path
        
        logs_dir = Path("logs")
        if logs_dir.exists():
            # Mevcut log dosyalarını yedekle
            backup_dir = logs_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_dir.mkdir(exist_ok=True)
            
            # Log dosyalarını yedekle
            for log_file in logs_dir.glob("*.log*"):
                if log_file.is_file():
                    shutil.move(str(log_file), str(backup_dir / log_file.name))
            
            # Yeni boş log dosyası oluştur
            new_log_file = logs_dir / "app.log"
            new_log_file.touch()
            
            logger.info("Log dosyaları temizlendi ve yedeklendi")
            return {
                "status": "success", 
                "message": "Log dosyaları temizlendi",
                "backup_dir": str(backup_dir)
            }
        else:
            return {"status": "error", "message": "Logs dizini bulunamadı"}
            
    except Exception as e:
        logger.error(f"Log temizleme hatası: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/logs/info")
async def get_logs_info():
    """Log dosyaları hakkında bilgi al"""
    try:
        from pathlib import Path
        
        logs_dir = Path("logs")
        if not logs_dir.exists():
            return {"status": "error", "message": "Logs dizini bulunamadı"}
        
        log_files = []
        total_size = 0
        
        for log_file in logs_dir.glob("*.log*"):
            if log_file.is_file():
                size = log_file.stat().st_size
                total_size += size
                log_files.append({
                    "name": log_file.name,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "modified": datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
                })
        
        return {
            "status": "success",
            "total_files": len(log_files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "files": log_files
        }
        
    except Exception as e:
        logger.error(f"Log bilgisi alma hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/trading/pause")
async def pause_trading():
    """Trading işlemlerini beklet"""
    try:
        task_manager.pause()
        return {"status": "success", "message": "Trading işlemleri bekletildi", "paused": True}
    except Exception as e:
        logger.error(f"Trading bekletme hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/trading/resume")
async def resume_trading():
    """Trading işlemlerini devam ettir"""
    try:
        task_manager.resume()
        return {"status": "success", "message": "Trading işlemleri devam ettirildi", "paused": False}
    except Exception as e:
        logger.error(f"Trading devam ettirme hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/trading/status")
async def get_trading_status():
    """Trading durumunu kontrol et"""
    try:
        return {
            "status": "success",
            "paused": task_manager.is_paused(),
            "running": task_manager.running
        }
    except Exception as e:
        logger.error(f"Trading durum kontrolü hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/volume/daily")
async def get_daily_volume_stats(days: int = 3):
    """Son N günün günlük long/short hacim istatistiklerini al"""
    try:
        if days < 1 or days > 30:
            raise HTTPException(status_code=400, detail="Days parametresi 1-30 arasında olmalı")
        
        volume_stats = await storage.get_daily_volume_stats(days)
        
        return {
            "status": "success",
            "data": volume_stats
        }
    except Exception as e:
        logger.error(f"Günlük hacim istatistikleri hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/positions")
async def get_positions():
    """Tüm pozisyonları ve net pozisyon bilgilerini al"""
    try:
        positions_data = await binance_client.get_all_positions()
        limits = await storage.load_position_limits()
        
        return {
            "status": "success",
            "data": {
                **positions_data,
                "limits": limits
            }
        }
    except Exception as e:
        logger.error(f"Pozisyon bilgisi alma hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/positions/limits")
async def update_position_limits(
    max_position_usd: float = Form(...),
    min_position_usd: float = Form(...)
):
    """Pozisyon limitlerini güncelle"""
    try:
        # Validasyon
        if max_position_usd <= min_position_usd:
            raise HTTPException(
                status_code=400, 
                detail=f"Maksimum pozisyon ({max_position_usd}) minimum pozisyondan ({min_position_usd}) büyük olmalı"
            )
        
        await storage.save_position_limits(max_position_usd, min_position_usd)
        
        return {
            "status": "success",
            "message": "Pozisyon limitleri güncellendi",
            "max_position_usd": max_position_usd,
            "min_position_usd": min_position_usd
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pozisyon limitleri güncelleme hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/debug/strategies")
async def get_all_strategies_debug_info():
    """TÜM STRATEJİLER için debug bilgileri"""
    try:
        from core.debug_monitor import universal_debug_monitor
        
        # Tüm stratejileri monitor et
        monitor_result = await universal_debug_monitor.monitor_all_strategies()
        
        # Son alert'leri ekle
        recent_alerts = universal_debug_monitor.get_recent_alerts(limit=10)
        
        # Performance stats
        performance = universal_debug_monitor.get_performance_stats()
        
        return {
            "status": "success",
            "data": {
                "monitor_result": monitor_result,
                "recent_alerts": recent_alerts,
                "performance": performance
            }
        }
    except Exception as e:
        logger.error(f"Universal debug info hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/debug/strategy/{strategy_id}")
async def get_strategy_diagnostics(strategy_id: str):
    """Belirli strateji için detaylı diagnostics (TÜM STRATEJİLER)"""
    try:
        from core.debug_monitor import universal_debug_monitor
        
        diagnostics = await universal_debug_monitor.get_strategy_diagnostics(strategy_id)
        
        return {
            "status": "success",
            "data": diagnostics
        }
    except Exception as e:
        logger.error(f"Strategy diagnostics hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/debug/enable")
async def enable_debug():
    """Debug monitoring'i aktif et (TÜM STRATEJİLER)"""
    try:
        from core.debug_monitor import universal_debug_monitor
        universal_debug_monitor.enable_debug()
        return {"status": "success", "message": "Universal debug monitoring aktif edildi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/debug/disable") 
async def disable_debug():
    """Debug monitoring'i pasif et (TÜM STRATEJİLER)"""
    try:
        from core.debug_monitor import universal_debug_monitor
        universal_debug_monitor.disable_debug()
        return {"status": "success", "message": "Universal debug monitoring pasif edildi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/debug/auto-stop/enable")
async def enable_auto_stop():
    """Otomatik strateji durdurma'yı aktif et"""
    try:
        from core.debug_monitor import universal_debug_monitor
        universal_debug_monitor.enable_auto_stop()
        return {"status": "success", "message": "Otomatik strateji durdurma aktif edildi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/debug/auto-stop/disable")
async def disable_auto_stop():
    """Otomatik strateji durdurma'yı pasif et"""
    try:
        from core.debug_monitor import universal_debug_monitor
        universal_debug_monitor.disable_auto_stop()
        return {"status": "success", "message": "Otomatik strateji durdurma pasif edildi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/debug/auto-stop/status")
async def get_auto_stop_status():
    """Otomatik durdurma durumunu al"""
    try:
        from core.debug_monitor import universal_debug_monitor
        return {
            "status": "success",
            "data": {
                "enabled": universal_debug_monitor.auto_stop_enabled,
                "rules": universal_debug_monitor.auto_stop_rules,
                "stopped_strategies": universal_debug_monitor.get_stopped_strategies()
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/debug/auto-stop/configure")
async def configure_auto_stop(
    critical_issues: bool = Form(True),
    multiple_errors: bool = Form(True), 
    state_corruption: bool = Form(True),
    consecutive_wrong_trades: bool = Form(True)
):
    """Otomatik durdurma kurallarını yapılandır"""
    try:
        from core.debug_monitor import universal_debug_monitor
        
        rules = {
            'critical_issues': critical_issues,
            'multiple_errors': multiple_errors,
            'state_corruption': state_corruption,
            'consecutive_wrong_trades': consecutive_wrong_trades
        }
        
        universal_debug_monitor.configure_auto_stop(**rules)
        
        return {
            "status": "success", 
            "message": "Auto-stop kuralları güncellendi",
            "rules": rules
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/recovery/validate-all")
async def validate_all_strategies():
    """Tüm stratejileri validate et ve gerekirse recover et"""
    try:
        from core.state_recovery import state_recovery_manager
        
        recovery_result = await state_recovery_manager.recover_all_strategies()
        
        return {
            "status": "success",
            "data": recovery_result
        }
    except Exception as e:
        logger.error(f"State recovery hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/recovery/strategy/{strategy_id}")
async def recover_strategy_state(strategy_id: str):
    """Belirli strateji için state recovery"""
    try:
        from core.state_recovery import state_recovery_manager
        
        strategy = await storage.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strateji bulunamadı")
        
        recovery_result = await state_recovery_manager.validate_and_recover_strategy_state(strategy)
        
        return {
            "status": "success",
            "data": recovery_result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strategy recovery hatası: {e}")
        return {"status": "error", "message": str(e)}

# ============= LOG YÖNETİMİ =============

@app.get("/api/logs/info")
async def get_log_info():
    """Log dosyaları hakkında bilgi al"""
    try:
        from core.utils import get_log_file_info
        log_info = get_log_file_info()
        return {
            "status": "success",
            "data": log_info
        }
    except Exception as e:
        logger.error(f"Log bilgi alma hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/logs/cleanup")
async def cleanup_logs(days_to_keep: int = 30):
    """Eski log dosyalarını temizle"""
    try:
        from core.utils import cleanup_old_logs
        cleanup_old_logs(days_to_keep)
        return {
            "status": "success",
            "message": f"{days_to_keep} günden eski log dosyaları temizlendi"
        }
    except Exception as e:
        logger.error(f"Log temizleme hatası: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/logs/current")
async def get_current_log():
    """Güncel log dosyasının içeriğini al (son 100 satır)"""
    try:
        from core.utils import get_daily_log_filename
        import os
        
        current_log_file = get_daily_log_filename()
        
        if not os.path.exists(current_log_file):
            return {
                "status": "success",
                "data": {
                    "filename": os.path.basename(current_log_file),
                    "lines": [],
                    "total_lines": 0
                }
            }
        
        # Son 100 satırı oku
        with open(current_log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Son 100 satırı al
        recent_lines = lines[-100:] if len(lines) > 100 else lines
        
        return {
            "status": "success",
            "data": {
                "filename": os.path.basename(current_log_file),
                "lines": [line.strip() for line in recent_lines],
                "total_lines": len(lines),
                "showing_last": len(recent_lines)
            }
        }
    except Exception as e:
        logger.error(f"Log okuma hatası: {e}")
        return {"status": "error", "message": str(e)}

# ============= MAIN =============

if __name__ == "__main__":
    # Ortam değişkenlerini al
    from core.config import HTTP_HOST, HTTP_PORT
    
    
    # Uvicorn ile çalıştır
    uvicorn.run(
        "app:app",
        host=HTTP_HOST,
        port=HTTP_PORT,
        reload=True,
        log_level="info"
    )

