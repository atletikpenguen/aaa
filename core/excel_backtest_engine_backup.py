# Excel Backtest Engine - Yeni Backtest Sistemi (22 Eylül 2025)
# Bu dosyada Excel verisiyle backtest analizi yapabileceğimiz sistem oluşturduk
# ÖZELLİKLER:
# - Excel dosyası yükleme ve OHLCV verisi işleme
# - Strateji seçimi ve parametreleri (mevcut stratejilerden)
# - Gerçek zamanlı kar-zarar hesaplaması (bizim PnL sistemimiz)
# - Grafik verileri oluşturma (fiyat, bakiye, işlemler)
# - Detaylı işlem tablosu
# 
# EXCEL FORMAT: Date, Time, Open, High, Low, Close, Volume, WClose
# İşlemler kapanış fiyatına göre, bir sonraki açılış fiyatında gerçekleşir
#
# DÜZELTME (25 Eylül 2025): Excel tarih formatı sorunu çözüldü
# - Sorun: Excel'deki DD.MM.YYYY formatı yanlış parse ediliyordu
# - Çözüm: Format belirtilerek doğru parse etme eklendi
# - Sonuç: Tarih ve işlem detaylarındaki tarihler artık uyumlu
#
# DÜZELTME (25 Eylül 2025): NumPy veri tipi uyumsuzluğu sorunu çözüldü
# - Sorun: Excel'den gelen fiyat verileri string olabiliyordu
# - Çözüm: OTT hesaplama öncesi float dönüşümü eklendi
# - Sonuç: "ufunc 'greater_equal' did not contain a loop" hatası çözüldü
#
# DÜZELTME (25 Eylül 2025): _sync_calculate_signal veri tipi güvenliği
# - Sorun: _sync_calculate_signal'de fiyat karşılaştırmalarında veri tipi uyumsuzluğu
# - Çözüm: Tüm fiyat karşılaştırmalarında float() dönüşümü eklendi
# - Sonuç: Excel backtest engine'de veri tipi hataları çözüldü
#
# DÜZELTME (25 Eylül 2025): DCA alım referansı sorunu (Excel backtest)
# - Sorun: Kısmi satış sonrası yanlış referans kullanılıyordu (son alım yerine son satış)
# - Çözüm: Son satış fiyatından düşüş kontrolü yapılacak şekilde düzeltildi
# - Sonuç: Excel backtest'te DCA mantığı canlı strateji ile uyumlu hale getirildi

import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict

from .models import Strategy, State, OrderSide, OTTMode, StrategyType
from .base_strategy import BaseStrategy
from .bol_grid_strategy import BollingerGridStrategy
from .dca_ott_strategy import DCAOTTStrategy
from .grid_ott_strategy import GridOTTStrategy
from .indicators import calculate_ott, calculate_bollinger_bands
from .pnl_calculator import pnl_calculator
from .utils import logger
from .backtest_debug import backtest_debugger


@dataclass
class BacktestTrade:
    """Backtest işlemi"""
    timestamp: datetime
    side: str  # "BUY" veya "SELL"
    price: float
    quantity: float
    total_value: float
    balance_before: float
    balance_after: float
    position_quantity_before: float
    position_quantity_after: float
    position_avg_cost: float  # Ortalama maliyet
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    signal_reason: str
    cash_flow: float  # Kasa akışı (kümülatif)
    # OTT değerleri
    ott_mode: str = None
    ott_upper: float = None
    ott_lower: float = None
    ott_baseline: float = None


@dataclass
class BacktestResult:
    """Backtest sonuçları"""
    # Temel bilgiler
    symbol: str
    strategy_name: str
    strategy_type: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    duration_days: float
    
    # Finansal sonuçlar
    initial_balance: float
    final_balance: float
    final_position_value: float
    total_return: float
    total_return_pct: float
    realized_pnl: float
    unrealized_pnl: float
    
    # İşlem istatistikleri
    total_trades: int
    buy_trades: int
    sell_trades: int
    profitable_trades: int
    losing_trades: int
    win_rate: float
    avg_trade_return: float
    max_drawdown: float
    max_profit: float
    
    # Detaylar
    trades: List[BacktestTrade]
    balance_history: List[Dict[str, Any]]
    parameters: Dict[str, Any]


class ExcelBacktestEngine:
    """
    Excel dosyasından OHLCV verisi alarak backtest yapan motor
    """
    
    def __init__(self):
        self.strategies = {
            'bol_grid': BollingerGridStrategy(),
            'dca_ott': DCAOTTStrategy(),
            'grid_ott': GridOTTStrategy()
        }
    
    def process_excel_file(self, file_content: bytes) -> pd.DataFrame:
        """
        Excel dosyasını işleyip OHLCV DataFrame'i döndür
        
        Args:
            file_content: Excel dosyasının byte içeriği
            
        Returns:
            OHLCV DataFrame
        """
        try:
            logger.info(f"Excel dosyası işleniyor, boyut: {len(file_content)} bytes")
            
            # Excel dosyasını oku
            df = pd.read_excel(io.BytesIO(file_content))
            logger.info(f"Excel okundu, satır sayısı: {len(df)}")
            logger.info(f"Sütunlar: {list(df.columns)}")
            
            # Sütun isimlerini temizle
            df.columns = df.columns.str.strip()
            
            # Gerekli sütunları kontrol et
            required_columns = ['Date', 'Time', 'Open', 'High', 'Low', 'Close']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise Exception(f"Eksik sütunlar: {missing_columns}")
            
            # Tarih ve saat sütunlarını birleştir
            # Excel formatı: DD.MM.YYYY HH:MM (Türkçe format)
            if 'Time' in df.columns:
                # Format belirtilerek doğru parse et
                df['DateTime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str), format='%d.%m.%Y %H:%M', errors='coerce')
            else:
                # Sadece tarih varsa
                df['DateTime'] = pd.to_datetime(df['Date'], format='%d.%m.%Y', errors='coerce')
            
            # Sayısal sütunları dönüştür
            numeric_columns = ['Open', 'High', 'Low', 'Close']
            if 'Volume' in df.columns:
                numeric_columns.append('Volume')
            
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Boş değerleri temizle
            df = df.dropna(subset=['DateTime'] + numeric_columns)
            
            # Tarihe göre sırala
            df = df.sort_values('DateTime').reset_index(drop=True)
            
            logger.info(f"OHLCV verisi hazır: {len(df)} satır, tarih aralığı: {df['DateTime'].min()} - {df['DateTime'].max()}")
            
            return df
            
        except Exception as e:
            logger.error(f"Excel işleme hatası: {e}")
            raise Exception(f"Excel dosyası işlenemedi: {str(e)}")
    
    def run_backtest(
        self, 
        ohlcv_data: pd.DataFrame, 
        strategy_type: str,
        strategy_params: Dict[str, Any],
        symbol: str = "ETHUSDT",  # Excel verisi için varsayılan
        timeframe: str = "1h"
    ) -> BacktestResult:
        """
        OHLCV verisiyle backtest çalıştır
        
        Args:
            ohlcv_data: OHLCV DataFrame
            strategy_type: Strateji tipi ('bol_grid', 'dca_ott', 'grid_ott')
            strategy_params: Strateji parametreleri
            symbol: Sembol adı
            timeframe: Zaman dilimi
            
        Returns:
            BacktestResult
        """
        try:
            # Debug başlat
            backtest_debugger.log_debug(f"Backtest başlatılıyor: {strategy_type} - {symbol} - {len(ohlcv_data)} mum")
            backtest_debugger.log_debug(f"Strategy params: {strategy_params}")
            
            logger.info(f"Backtest başlatılıyor: {strategy_type} - {symbol} - {len(ohlcv_data)} mum")
            
            # Stratejiyi al
            if strategy_type not in self.strategies:
                raise Exception(f"Desteklenmeyen strateji: {strategy_type}")
            
            strategy_instance = self.strategies[strategy_type]
            
            # OTT parametrelerini ayır
            ott_params = strategy_params.pop('ott', {'period': 14, 'opt': 2.0})
            
            # Debug: OTT parametreleri
            logger.info(f"OTT parametreleri alındı: {ott_params}")
            backtest_debugger.log_debug(f"OTT parametreleri alındı: {ott_params}")
            
            # Strategy objesi oluştur
            from .models import OTTParams
            
            # Debug: StrategyType oluşturma
            backtest_debugger.log_debug(f"Creating StrategyType from: {strategy_type}")
            strategy_type_enum = StrategyType(strategy_type)
            backtest_debugger.debug_object_type(strategy_type_enum, "strategy_type_enum")
            
            # OTTParams oluştur
            ott_obj = OTTParams(
                period=ott_params.get('period', 14),
                opt=ott_params.get('opt', 2.0)
            )
            
            # Debug: OTTParams objesi
            logger.info(f"OTTParams oluşturuldu: period={ott_obj.period}, opt={ott_obj.opt}")
            backtest_debugger.log_debug(f"OTTParams oluşturuldu: period={ott_obj.period}, opt={ott_obj.opt}")
            
            strategy = Strategy(
                id="backtest_001",
                name=f"backtest_{strategy_type}",
                symbol=symbol,
                timeframe=timeframe,
                strategy_type=strategy_type_enum,
                parameters=strategy_params,
                ott=ott_obj,
                active=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Debug: Strategy objesi
            backtest_debugger.debug_object_type(strategy, "strategy")
            backtest_debugger.debug_object_type(strategy.strategy_type, "strategy.strategy_type")
            
            # State başlat
            state = State(
                strategy_id="backtest_001",
                symbol=symbol,
                active=True,
                created_at=None,  # JSON serialization için None
                updated_at=None,  # JSON serialization için None
                open_orders=[],
                trades=[],
                custom_data={}
            )
            
            # Backtest için özel alanlar ekle
            state._last_buy_price = None
            state.dca_positions = []
            
            # PnL calculator'ı initialize et
            pnl_calculator.initialize_state_pnl(state)
            
            # Strateji state'ini initialize et (sync version)
            custom_data = self._sync_initialize_state(strategy_instance, strategy)
            state.custom_data = custom_data
            
            # Backtest değişkenleri
            trades = []
            balance_history = []
            
            # İlk bakiye kaydı
            initial_balance = state.cash_balance
            balance_history.append({
                'timestamp': ohlcv_data.iloc[0]['DateTime'],
                'price': ohlcv_data.iloc[0]['Close'],
                'cash_balance': state.cash_balance,
                'position_quantity': state.position_quantity,
                'position_value': 0.0,
                'unrealized_pnl': 0.0,
                'total_balance': state.cash_balance
            })
            
            # OTT hesaplama için minimum veri kontrolü
            # OTT period parametresine göre minimum veri gereksinimi
            ott_params = getattr(strategy, 'ott', None)
            if ott_params:
                min_ott_data_points = ott_params.period
                logger.info(f"Backtest başlangıcı - OTT parametreleri: Period={ott_params.period}, Opt={ott_params.opt}")
                backtest_debugger.log_debug(f"Backtest başlangıcı - OTT parametreleri: Period={ott_params.period}, Opt={ott_params.opt}")
            else:
                min_ott_data_points = 14
                logger.warning("Backtest başlangıcı - OTT parametreleri bulunamadı, varsayılan period=14 kullanılıyor")
                backtest_debugger.log_debug("Backtest başlangıcı - OTT parametreleri bulunamadı, varsayılan period=14 kullanılıyor")
            
            start_processing_index = min_ott_data_points
            
            logger.info(f"Backtest başlangıcı: {len(ohlcv_data)} mum, OTT hesaplama için {start_processing_index} mumdan sonra başlanacak (OTT period: {min_ott_data_points})")
            
            # Her mum için işle (OTT hesaplama için yeterli veri olduktan sonra)
            for i in range(start_processing_index, len(ohlcv_data)):
                row = ohlcv_data.iloc[i]
                current_price = row['Close']
                timestamp = row['DateTime']
                
                # OHLCV verisi hazırla (son 100 mum - OTT için yeterli veri)
                end_idx = i + 1
                start_idx = max(0, end_idx - 100)
                ohlcv_slice = ohlcv_data.iloc[start_idx:end_idx]
                
                # OTT hesapla
                ott_result = self._calculate_ott_for_backtest(ohlcv_slice, strategy)
                
                # OTT hesaplanamadıysa bu mumu atla
                if ott_result is None:
                    logger.warning(f"OTT hesaplanamadı, mum atlanıyor: {timestamp}")
                    continue
                
                # Market info hazırla
                market_info = self._create_market_info(symbol, current_price)
                
                # Sinyal hesapla (sync version)
                signal = self._sync_calculate_signal(
                    strategy_instance, strategy, state, current_price, 
                    ott_result, market_info, ohlcv_slice.to_dict('records')
                )
                
                # Eğer sinyal varsa işlem yap
                if signal.should_trade:
                    trade_price = self._get_execution_price(ohlcv_data, i, signal.side)
                    
                    if trade_price > 0:
                        # İşlem oluştur
                        trade = self._create_trade(
                            timestamp=timestamp,
                            side=signal.side,
                            price=trade_price,
                            quantity=signal.quantity,
                            state=state,
                            signal_reason=signal.reason,
                            ott_result=ott_result
                        )
                        
                        # Trade'i state'e uygula
                        pnl_result = pnl_calculator.process_trade_fill(state, trade)
                        
                        # Backtest için state güncellemeleri
                        if signal.side == OrderSide.BUY:
                            state._last_buy_price = trade_price
                            # DCA pozisyonu ekle
                            from .models import DCAPosition
                            dca_position = DCAPosition(
                                timestamp=timestamp,
                                buy_price=trade_price,
                                quantity=trade.quantity
                            )
                            state.dca_positions.append(dca_position)
                        elif signal.side == OrderSide.SELL:
                            # Satış türüne göre state güncelleme
                            if "Tam satış" in signal.reason:
                                # Tam satış: Tüm pozisyonları temizle
                                state._last_buy_price = None
                                state.dca_positions = []
                                backtest_debugger.log_debug("TAM SATIŞ: Tüm pozisyonlar temizlendi")
                            elif "Kısmi satış" in signal.reason:
                                # Kısmi satış: Son pozisyonu DCA listesinden çıkar
                                if hasattr(state, 'dca_positions') and state.dca_positions:
                                    # En son pozisyonu çıkar
                                    state.dca_positions = state.dca_positions[:-1]
                                    # Son alım fiyatını güncelle
                                    if state.dca_positions:
                                        state._last_buy_price = max(state.dca_positions, key=lambda x: x.timestamp).buy_price
                                    else:
                                        state._last_buy_price = None
                                backtest_debugger.log_debug("KISMİ SATIŞ: Son pozisyon çıkarıldı")
                        
                        # Trade'i kaydet
                        trades.append(trade)
                
                # Güncel durumu kaydet
                pnl_summary = pnl_calculator.get_pnl_summary(state, current_price)
                balance_history.append({
                    'timestamp': timestamp,
                    'price': current_price,
                    'cash_balance': state.cash_balance,
                    'position_quantity': state.position_quantity,
                    'position_value': pnl_summary['position_value'],
                    'position_avg_cost': state.position_avg_cost if state.position_avg_cost is not None else 0.0,
                    'unrealized_pnl': pnl_summary['unrealized_pnl'],
                    'total_balance': pnl_summary['total_balance']
                })
            
            # Sonuçları hesapla
            result = self._calculate_backtest_results(
                trades=trades,
                balance_history=balance_history,
                strategy=strategy,
                ohlcv_data=ohlcv_data,
                initial_balance=initial_balance
            )
            
            logger.info(f"Backtest tamamlandı: {len(trades)} işlem, final balance: ${result.final_balance:.2f}")
            
            # Debug özeti
            debug_summary = backtest_debugger.get_debug_summary()
            backtest_debugger.log_debug(f"Backtest debug özeti: {debug_summary}")
            
            return result
            
        except Exception as e:
            # Debug: Hata detayları
            backtest_debugger.log_error(e, "Backtest genel hatası")
            debug_summary = backtest_debugger.get_debug_summary()
            backtest_debugger.log_debug(f"Backtest hata debug özeti: {debug_summary}")
            
            logger.error(f"Backtest hatası: {e}")
            raise Exception(f"Backtest çalıştırılamadı: {str(e)}")
    
    def _calculate_ott_for_backtest(self, ohlcv_data: pd.DataFrame, strategy: Strategy) -> Any:
        """Backtest için OTT hesapla"""
        try:
            # OHLC verilerini hazırla - veri tipi güvenliği
            close_prices = [float(x) for x in ohlcv_data['Close'].tolist() if pd.notna(x)]
            current_price = float(close_prices[-1]) if close_prices else 65400.0
            
            # OTT parametreleri
            ott_params = getattr(strategy, 'ott', None)
            if ott_params:
                period = ott_params.period
                opt = ott_params.opt
                logger.info(f"OTT parametreleri alındı - Period: {period}, Opt: {opt}")
                backtest_debugger.log_debug(f"OTT parametreleri alındı - Period: {period}, Opt: {opt}")
            else:
                period = 14
                opt = 2.0
                logger.warning("OTT parametreleri bulunamadı, varsayılan değerler kullanılıyor")
                backtest_debugger.log_debug("OTT parametreleri bulunamadı, varsayılan değerler kullanılıyor")
            
            if len(close_prices) < period:
                # Yetersiz veri - None döndür (işlem yapılmasın)
                logger.warning(f"OTT hesaplama için yeterli veri yok. Gerekli: {period}, Mevcut: {len(close_prices)}")
                backtest_debugger.log_debug(f"OTT hesaplama için yeterli veri yok. Gerekli: {period}, Mevcut: {len(close_prices)}")
                return None
            
            # OTT hesapla
            ott_result = calculate_ott(close_prices, period=period, opt=opt, strategy_name="backtest")
            
            # Debug: OTT hesaplama sonucu
            logger.info(f"OTT hesaplama - Period: {period}, Opt: {opt}, Data points: {len(close_prices)}, Result: {ott_result}")
            backtest_debugger.log_debug(f"OTT hesaplama - Period: {period}, Opt: {opt}, Data points: {len(close_prices)}, Result: {ott_result}")
            
            # OTT sonucu kontrolü
            if ott_result is None:
                logger.warning("OTT result is None after calculation")
                backtest_debugger.log_debug("OTT result is None after calculation")
            
            # OTT sonucu None ise varsayılan değer döndür
            if ott_result is None:
                logger.warning("OTT result is None, using default values")
                backtest_debugger.log_debug("OTT result is None, using default values")
                from .models import OTTResult, OTTMode
                return OTTResult(
                    mode=OTTMode.AL,
                    baseline=current_price,
                    trend_direction=1,
                    upper=current_price * 1.02,
                    lower=current_price * 0.98,
                    current_price=current_price
                )
            
            # Eksik alanları ekle
            if not hasattr(ott_result, 'upper') or ott_result.upper is None:
                ott_result.upper = current_price * 1.02
                logger.info(f"OTT upper eksik, varsayılan değer: {ott_result.upper}")
            if not hasattr(ott_result, 'lower') or ott_result.lower is None:
                ott_result.lower = current_price * 0.98
                logger.info(f"OTT lower eksik, varsayılan değer: {ott_result.lower}")
            if not hasattr(ott_result, 'current_price') or ott_result.current_price is None:
                ott_result.current_price = current_price
                logger.info(f"OTT current_price eksik, varsayılan değer: {ott_result.current_price}")
            
            # Debug: Final OTT değerleri
            logger.info(f"Final OTT değerleri - Mode: {ott_result.mode}, Upper: {ott_result.upper}, Lower: {ott_result.lower}, Baseline: {ott_result.baseline}")
            backtest_debugger.log_debug(f"Final OTT değerleri - Mode: {ott_result.mode}, Upper: {ott_result.upper}, Lower: {ott_result.lower}, Baseline: {ott_result.baseline}")
                
            return ott_result
            
        except Exception as e:
            logger.error(f"OTT hesaplama hatası: {e}")
            backtest_debugger.log_debug(f"OTT hesaplama hatası: {e}")
            # Varsayılan değer döndür
            from .models import OTTResult, OTTMode
            current_price = ohlcv_data['Close'].iloc[-1] if len(ohlcv_data) > 0 else 65400.0
            fallback_result = OTTResult(
                mode=OTTMode.AL,
                baseline=current_price,
                trend_direction=1,
                upper=current_price * 1.02,
                lower=current_price * 0.98,
                current_price=current_price
            )
            logger.info(f"Fallback OTT değerleri - Mode: {fallback_result.mode}, Upper: {fallback_result.upper}, Lower: {fallback_result.lower}")
            backtest_debugger.log_debug(f"Fallback OTT değerleri - Mode: {fallback_result.mode}, Upper: {fallback_result.upper}, Lower: {fallback_result.lower}")
            return fallback_result
    
    def _create_market_info(self, symbol: str, current_price: float) -> Any:
        """Market info oluştur"""
        from .models import MarketInfo
        return MarketInfo(
            symbol=symbol,
            price=current_price,
            current_price=current_price,
            bid=current_price * 0.999,
            ask=current_price * 1.001,
            volume_24h=1000000.0,
            price_change_24h=0.0,
            price_change_pct_24h=0.0,
            tick_size=0.01,
            step_size=0.001,
            min_qty=0.001,
            min_notional=10.0,
            timestamp=datetime.now()
        )
    
    def _get_execution_price(self, ohlcv_data: pd.DataFrame, current_index: int, side) -> float:
        """
        İşlem gerçekleşme fiyatını hesapla
        Kapanış fiyatına göre sinyal, bir sonraki açılış fiyatında işlem
        """
        try:
            # Debug: Mevcut fiyat bilgisi
            current_close = float(ohlcv_data.iloc[current_index]['Close'])
            backtest_debugger.log_debug(f"Execution price - Current index: {current_index}, Current close: {current_close}")
            
            # Bir sonraki mumun açılış fiyatını al
            if current_index + 1 < len(ohlcv_data):
                next_open = float(ohlcv_data.iloc[current_index + 1]['Open'])
                backtest_debugger.log_debug(f"Execution price - Next open: {next_open}")
                return next_open
            else:
                # Son mum ise, mevcut kapanış fiyatını kullan
                backtest_debugger.log_debug(f"Execution price - Using current close: {current_close}")
                return current_close
                
        except Exception as e:
            logger.error(f"Execution price hesaplama hatası: {e}")
            current_close = float(ohlcv_data.iloc[current_index]['Close'])
            backtest_debugger.log_debug(f"Execution price - Error fallback: {current_close}")
            return current_close
    
    def _create_trade(
        self, 
        timestamp: datetime, 
        side, 
        price: float, 
        quantity: float,
        state: State,
        signal_reason: str,
        ott_result=None
    ) -> BacktestTrade:
        """Backtest trade objesi oluştur"""
        
        # Debug: Side parametresi kontrolü
        backtest_debugger.log_debug("_create_trade başlatılıyor")
        backtest_debugger.debug_object_type(side, "side parameter")
        
        # Önceki durumu kaydet
        balance_before = state.cash_balance
        position_before = state.position_quantity
        
        # Unrealized PnL hesapla (trade öncesi)
        pnl_before = pnl_calculator.calculate_unrealized_pnl(state, price)
        
        # Trade objesi oluştur (PnL hesaplaması için)
        from .models import Trade
        trade_obj = Trade(
            id=f"backtest_{timestamp.isoformat()}",
            timestamp=timestamp,
            strategy_id=state.strategy_id,
            side=side,
            price=price,
            quantity=quantity,
            z=0,  # Grid kademesi (backtest için 0)
            notional=price * quantity,  # USDT tutarı
            gf_before=state.position_avg_cost or price,  # İşlem öncesi ortalama fiyat
            gf_after=price,  # İşlem sonrası fiyat
            commission=0.0,  # Komisyon (backtest için 0)
            order_id=f"backtest_order_{timestamp.isoformat()}"
        )
        
        # PnL hesapla (geçici state kopyası ile)
        temp_state = State(**state.__dict__)
        pnl_result = pnl_calculator.process_trade_fill(temp_state, trade_obj)
        
        # Sonraki durumu al
        balance_after = temp_state.cash_balance
        position_after = temp_state.position_quantity
        
        # Unrealized PnL hesapla (trade sonrası)
        pnl_after = pnl_calculator.calculate_unrealized_pnl(temp_state, price)
        
        # Debug: Side değeri güvenli erişim
        side_value = backtest_debugger.safe_enum_access(side, 'UNKNOWN')
        backtest_debugger.log_debug(f"Side value for BacktestTrade: {side_value}")
        
        # Kasa akışı hesapla (işlem için yapılan harcama)
        # Alış işleminde: -total_value (para çıkışı)
        # Satış işleminde: +total_value (para girişi)
        if side_value.upper() == 'BUY':
            cash_flow = -(price * quantity)  # Para çıkışı (negatif)
        else:  # SELL
            cash_flow = price * quantity  # Para girişi (pozitif)
        
        # Debug: Kasa akışı hesaplama
        logger.info(f"Cash flow calculation - Side: {side_value}, Price: {price}, Quantity: {quantity}, Cash Flow: {cash_flow}")
        
        # OTT değerlerini hazırla
        ott_mode = None
        ott_upper = None
        ott_lower = None
        ott_baseline = None
        
        if ott_result:
            try:
                ott_mode = str(ott_result.mode) if hasattr(ott_result, 'mode') else None
                ott_upper = float(ott_result.upper) if hasattr(ott_result, 'upper') and ott_result.upper is not None else None
                ott_lower = float(ott_result.lower) if hasattr(ott_result, 'lower') and ott_result.lower is not None else None
                ott_baseline = float(ott_result.baseline) if hasattr(ott_result, 'baseline') and ott_result.baseline else None
                
                # Debug: OTT değerlerini logla
                logger.info(f"OTT değerleri - Mode: {ott_mode}, Upper: {ott_upper}, Lower: {ott_lower}, Baseline: {ott_baseline}")
                backtest_debugger.log_debug(f"OTT değerleri - Mode: {ott_mode}, Upper: {ott_upper}, Lower: {ott_lower}, Baseline: {ott_baseline}")
                
                # Debug: OTT result objesini kontrol et
                if ott_result:
                    logger.info(f"OTT result attributes: {dir(ott_result)}")
                    logger.info(f"OTT result values: mode={getattr(ott_result, 'mode', None)}, upper={getattr(ott_result, 'upper', None)}, lower={getattr(ott_result, 'lower', None)}")
                else:
                    logger.warning("OTT result is None in trade creation")
                
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"OTT değerleri alınamadı: {e}")
                backtest_debugger.log_debug(f"OTT değerleri alınamadı: {e}")
        else:
            logger.warning("OTT result is None")
            backtest_debugger.log_debug("OTT result is None")
        
        # BacktestTrade oluştur
        backtest_trade = BacktestTrade(
            timestamp=timestamp,
            side=side_value,
            price=price,
            quantity=quantity,
            total_value=price * quantity,
            balance_before=balance_before,
            balance_after=balance_after,
            position_quantity_before=position_before,
            position_quantity_after=position_after,
            position_avg_cost=temp_state.position_avg_cost if temp_state.position_avg_cost is not None else 0.0,
            realized_pnl=pnl_result['realized_pnl_change'],
            unrealized_pnl=pnl_after['unrealized_pnl'],
            total_pnl=pnl_result['realized_pnl_change'] + pnl_after['unrealized_pnl'],
            signal_reason=signal_reason,
            cash_flow=cash_flow,
            ott_mode=ott_mode,
            ott_upper=ott_upper,
            ott_lower=ott_lower,
            ott_baseline=ott_baseline
        )
        
        return backtest_trade
    
    def _calculate_backtest_results(
        self,
        trades: List[BacktestTrade],
        balance_history: List[Dict[str, Any]],
        strategy: Strategy,
        ohlcv_data: pd.DataFrame,
        initial_balance: float
    ) -> BacktestResult:
        """Backtest sonuçlarını hesapla"""
        
        # Temel bilgiler
        start_date = ohlcv_data.iloc[0]['DateTime']
        end_date = ohlcv_data.iloc[-1]['DateTime']
        duration_days = (end_date - start_date).total_seconds() / 86400
        
        # Final durumu
        final_balance_data = balance_history[-1]
        final_balance = final_balance_data['cash_balance']
        final_position_value = final_balance_data['position_value']
        final_unrealized_pnl = final_balance_data['unrealized_pnl']
        total_balance = final_balance_data['total_balance']
        
        # Return hesaplamaları
        total_return = total_balance - initial_balance
        total_return_pct = (total_return / initial_balance * 100) if initial_balance > 0 else 0.0
        
        # İşlem istatistikleri
        total_trades = len(trades)
        buy_trades = len([t for t in trades if t.side == "BUY"])
        sell_trades = len([t for t in trades if t.side == "SELL"])
        
        # Kar/zarar analizi
        profitable_trades = len([t for t in trades if t.realized_pnl > 0])
        losing_trades = len([t for t in trades if t.realized_pnl < 0])
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # Ortalama işlem getirisi
        trade_returns = [t.realized_pnl for t in trades if t.realized_pnl != 0]
        avg_trade_return = np.mean(trade_returns) if trade_returns else 0.0
        
        # Drawdown hesaplama
        balance_values = [b['total_balance'] for b in balance_history]
        peak_balance = initial_balance
        max_drawdown = 0.0
        max_profit = 0.0
        
        for balance in balance_values:
            if balance > peak_balance:
                peak_balance = balance
                profit = balance - initial_balance
                if profit > max_profit:
                    max_profit = profit
            else:
                drawdown = (peak_balance - balance) / peak_balance * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        # Realized PnL toplamı
        realized_pnl = sum([t.realized_pnl for t in trades])
        
        # Debug: Strategy type güvenli erişim
        strategy_type_value = backtest_debugger.safe_enum_access(strategy.strategy_type, 'unknown')
        backtest_debugger.log_debug(f"Strategy type for BacktestResult: {strategy_type_value}")
        
        # Sonuç objesi oluştur
        result = BacktestResult(
            symbol=strategy.symbol,
            strategy_name=strategy.name,
            strategy_type=strategy_type_value,
            timeframe=strategy.timeframe,
            start_date=start_date,
            end_date=end_date,
            duration_days=duration_days,
            
            initial_balance=initial_balance,
            final_balance=final_balance,
            final_position_value=final_position_value,
            total_return=total_return,
            total_return_pct=total_return_pct,
            realized_pnl=realized_pnl,
            unrealized_pnl=final_unrealized_pnl,
            
            total_trades=total_trades,
            buy_trades=buy_trades,
            sell_trades=sell_trades,
            profitable_trades=profitable_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_trade_return=avg_trade_return,
            max_drawdown=max_drawdown,
            max_profit=max_profit,
            
            trades=trades,
            balance_history=balance_history,
            parameters=strategy.parameters
        )
        
        return result
    
    def _sync_initialize_state(self, strategy_instance, strategy):
        """Sync version of strategy initialize_state"""
        try:
            # Debug: Strategy type kontrolü
            backtest_debugger.log_debug("_sync_initialize_state başlatılıyor")
            backtest_debugger.debug_object_type(strategy.strategy_type, "strategy.strategy_type in _sync_initialize_state")
            
            # Basit sync implementasyon - stratejiye göre default değerler
            strategy_type_value = backtest_debugger.safe_enum_access(strategy.strategy_type, 'unknown')
            backtest_debugger.log_debug(f"Strategy type value: {strategy_type_value}")
            
            if strategy_type_value == 'dca_ott':
                return {
                    "positions": [],
                    "last_ott_mode": None,
                    "last_signal_time": None
                }
            elif strategy_type_value == 'bol_grid':
                return {
                    "cycles": [],
                    "current_cycle": None,
                    "last_bollinger": None
                }
            elif strategy_type_value == 'grid_ott':
                return {
                    "gf_initialized": False,
                    "last_grid_z": 0
                }
            else:
                return {}
        except Exception as e:
            logger.error(f"Sync initialize state hatası: {e}")
            return {}
    
    def _sync_calculate_signal(self, strategy_instance, strategy, state, current_price, ott_result, market_info, ohlcv_data):
        """Sync version of strategy calculate_signal - OVERFLOW KORUMALI VERSİYON"""
        try:
            from .models import TradingSignal, OrderSide
            
            # Debug: OTT result kontrolü
            backtest_debugger.log_debug("_sync_calculate_signal başlatılıyor")
            backtest_debugger.debug_object_type(ott_result, "ott_result")
            backtest_debugger.debug_object_type(ott_result.mode, "ott_result.mode")
            
            # Güvenlik kontrolleri - overflow önleme
            max_safe_value = 1e15  # 1 katrilyon - çok büyük değerler için limit
            min_safe_value = 1e-15  # Çok küçük değerler için limit
            
            # Current price güvenlik kontrolü
            try:
                current_price_float = float(current_price)
                if abs(current_price_float) > max_safe_value or current_price_float <= 0:
                    backtest_debugger.log_debug(f"Geçersiz fiyat: {current_price_float}")
                    return TradingSignal(should_trade=False, reason="Geçersiz fiyat")
            except (ValueError, TypeError, OverflowError):
                backtest_debugger.log_debug(f"Fiyat dönüşüm hatası: {current_price}")
                return TradingSignal(should_trade=False, reason="Fiyat dönüşüm hatası")
            
            # Basit sinyal mantığı - sadece OTT'ye göre
            ott_mode = backtest_debugger.safe_enum_access(ott_result.mode, 'unknown')
            backtest_debugger.log_debug(f"OTT mode: {ott_mode}")
            
            if ott_mode == 'AL':
                # AL sinyali - uzun süre bekledikten sonra alış yap
                # YENİ REFERANS SİSTEMİ: Referans fiyatı 0 ise yeni döngü için alış yap
                reference_price = state.custom_data.get('reference_price', None)
                if reference_price == 0 or not hasattr(state, '_last_buy_price') or state._last_buy_price is None:
                    # İlk alış - overflow korumalı
                    try:
                        quantity = self._calculate_backtest_quantity(strategy, current_price_float)
                        if abs(quantity) > max_safe_value or quantity <= 0:
                            backtest_debugger.log_debug(f"Geçersiz miktar: {quantity}")
                            return TradingSignal(should_trade=False, reason="Geçersiz miktar")
                        
                        state._last_buy_price = current_price_float
                        
                        # YENİ REFERANS SİSTEMİ: İlk alışta referans fiyatı güncelle
                        state.custom_data['reference_price'] = current_price_float
                        backtest_debugger.log_debug(f"İlk alış - Referans fiyat güncellendi: {current_price_float}")
                        
                        return TradingSignal(
                            should_trade=True,
                            side=OrderSide.BUY,
                            quantity=quantity,
                            reason="OTT AL sinyali - Yeni döngü alışı" if reference_price == 0 else "OTT AL sinyali - İlk alış"
                        )
                    except (OverflowError, ValueError, ZeroDivisionError) as e:
                        backtest_debugger.log_debug(f"İlk alış hesaplama hatası: {e}")
                        return TradingSignal(should_trade=False, reason="İlk alış hesaplama hatası")
                else:
                    # DCA alışı - min düşüş yüzdesi kontrolü (CANLI STRATEJİ İLE AYNI MANTIK)
                    try:
                        min_drop_pct = float(strategy.parameters.get('min_drop_pct', 2.0))  # Varsayılan %2
                        profit_threshold_pct = float(strategy.parameters.get('profit_threshold_pct', 1.0))  # Varsayılan %1
                        
                        # YENİ REFERANS SİSTEMİ: Son işlem tipine göre referans fiyat belirleme
                        # Referans fiyatı: Son alış fiyatı (kısmi satış sonrası güncellenir)
                        reference_price = state.custom_data.get('reference_price', state._last_buy_price)
                        reference_price_float = float(reference_price)
                        
                        # Overflow kontrolü
                        if (abs(reference_price_float) > max_safe_value or 
                            abs(current_price_float) > max_safe_value or
                            reference_price_float <= 0):
                            backtest_debugger.log_debug(f"Geçersiz fiyat değerleri: reference={reference_price_float}, current={current_price_float}")
                            return TradingSignal(should_trade=False, reason="Geçersiz fiyat değerleri")
                        
                        # Güvenli düşüş hesaplama - referans fiyattan düşüş
                        drop_from_reference = ((reference_price_float - current_price_float) / reference_price_float) * 100
                        
                        # Debug bilgisi
                        backtest_debugger.log_debug(f"DCA kontrolü - Referans: {reference_price_float}, Current: {current_price_float}, Drop: {drop_from_reference:.2f}%, Min: {min_drop_pct}%")
                        
                        if drop_from_reference >= min_drop_pct:
                            # DCA alışı - düşüş yeterli - overflow korumalı
                            try:
                                dca_multiplier = float(strategy.parameters.get('dca_multiplier', 1.5))
                                position_count = len(state.dca_positions) if hasattr(state, 'dca_positions') else 0
                                
                                # Güvenli üs hesaplama
                                if position_count > 100:  # Çok büyük üs önleme
                                    position_count = 100
                                    backtest_debugger.log_debug(f"Position count sınırlandı: {position_count}")
                                
                                dca_usdt = float(strategy.parameters.get('base_usdt', 50.0)) * (dca_multiplier ** position_count)
                                
                                # Overflow kontrolü
                                if abs(dca_usdt) > max_safe_value:
                                    dca_usdt = max_safe_value
                                    backtest_debugger.log_debug(f"DCA USDT overflow korundu: {dca_usdt}")
                                
                                quantity = dca_usdt / current_price_float
                                
                                # Miktar kontrolü
                                if abs(quantity) > max_safe_value or quantity <= 0:
                                    backtest_debugger.log_debug(f"Geçersiz DCA miktarı: {quantity}")
                                    return TradingSignal(should_trade=False, reason="Geçersiz DCA miktarı")
                                
                                backtest_debugger.log_debug(f"DCA alışı yapılıyor - Düşüş: {drop_from_reference:.2f}%, DCA USDT: {dca_usdt}")
                                
                                # YENİ REFERANS SİSTEMİ: Alış yapıldığında referans fiyatı güncelle
                                state.custom_data['reference_price'] = current_price_float
                                backtest_debugger.log_debug(f"Referans fiyat güncellendi: {current_price_float}")
                                
                                return TradingSignal(
                                    should_trade=True,
                                    side=OrderSide.BUY,
                                    quantity=quantity,
                                    reason=f"OTT AL sinyali - DCA alışı (Düşüş: {drop_from_reference:.2f}%)"
                                )
                            except (OverflowError, ValueError, ZeroDivisionError) as e:
                                backtest_debugger.log_debug(f"DCA hesaplama hatası: {e}")
                                return TradingSignal(should_trade=False, reason="DCA hesaplama hatası")
                        else:
                            # Düşüş yetersiz
                            backtest_debugger.log_debug(f"DCA alışı engellendi - Düşüş: {drop_from_reference:.2f}%, Min: {min_drop_pct}%")
                            return TradingSignal(
                                should_trade=False,
                                reason=f"OTT AL engellendi: Düşüş ({drop_from_reference:.2f}%) minimum eşiğin ({min_drop_pct}%) altında"
                            )
                    except (OverflowError, ValueError, ZeroDivisionError) as e:
                        backtest_debugger.log_debug(f"DCA kontrol hesaplama hatası: {e}")
                        return TradingSignal(should_trade=False, reason="DCA kontrol hesaplama hatası")
            
            elif ott_mode == 'SAT' and hasattr(state, '_last_buy_price') and state._last_buy_price:
                # SAT sinyali - CANLI STRATEJİ İLE AYNI MANTIK
                try:
                    # SAT sinyali için parametreleri al
                    profit_threshold_pct = float(strategy.parameters.get('profit_threshold_pct', 1.0))  # Varsayılan %1
                    if state.position_quantity > 0:
                        # Ortalama maliyet hesapla - overflow korumalı
                        avg_cost = state.position_avg_cost if state.position_avg_cost is not None else state._last_buy_price
                        avg_cost_float = float(avg_cost)
                        
                        # Overflow kontrolü
                        if (abs(avg_cost_float) > max_safe_value or 
                            abs(current_price_float) > max_safe_value or
                            avg_cost_float <= 0):
                            backtest_debugger.log_debug(f"Geçersiz ortalama maliyet: {avg_cost_float}")
                            return TradingSignal(should_trade=False, reason="Geçersiz ortalama maliyet")
                        
                        # Tam satış kontrolü: Ortalama maliyetin profit_threshold_pct üzerinde - overflow korumalı
                        if current_price_float >= avg_cost_float * (1 + profit_threshold_pct / 100):
                            quantity = float(state.position_quantity)
                            
                            # Miktar kontrolü
                            if abs(quantity) > max_safe_value or quantity <= 0:
                                backtest_debugger.log_debug(f"Geçersiz satış miktarı: {quantity}")
                                return TradingSignal(should_trade=False, reason="Geçersiz satış miktarı")
                            
                            # YENİ REFERANS SİSTEMİ: Tam satışta referans fiyatı sıfırla (yeni döngü için)
                            state.custom_data['reference_price'] = 0
                            backtest_debugger.log_debug(f"TAM SATIŞ: Fiyat {current_price_float} >= Ort. maliyet {avg_cost_float} * (1 + {profit_threshold_pct}/100)")
                            backtest_debugger.log_debug(f"Referans fiyat sıfırlandı (yeni döngü için)")
                            return TradingSignal(
                                should_trade=True,
                                side=OrderSide.SELL,
                                quantity=quantity,
                                reason=f"OTT SAT sinyali - Tam satış (Ort. maliyet %{profit_threshold_pct} üzeri)"
                            )
                        
                        # Kısmi satış kontrolü: Referans fiyatın profit_threshold_pct üzerinde - overflow korumalı
                        reference_price = state.custom_data.get('reference_price', state._last_buy_price)
                        reference_price_float = float(reference_price)
                        
                        if (abs(reference_price_float) > max_safe_value or reference_price_float <= 0):
                            backtest_debugger.log_debug(f"Geçersiz referans fiyatı: {reference_price_float}")
                            return TradingSignal(should_trade=False, reason="Geçersiz referans fiyatı")
                        
                        if current_price_float >= reference_price_float * (1 + profit_threshold_pct / 100):
                            # Son pozisyonu sat (DCA pozisyonlarından son alımı) - overflow korumalı
                            if hasattr(state, 'dca_positions') and state.dca_positions:
                                last_position = max(state.dca_positions, key=lambda x: x.timestamp)
                                quantity = float(last_position.quantity)
                            else:
                                quantity = float(state.position_quantity)
                            
                            # Miktar kontrolü
                            if abs(quantity) > max_safe_value or quantity <= 0:
                                backtest_debugger.log_debug(f"Geçersiz kısmi satış miktarı: {quantity}")
                                return TradingSignal(should_trade=False, reason="Geçersiz kısmi satış miktarı")
                            
                            # YENİ REFERANS SİSTEMİ: Kısmi satışta referans fiyatı güncelle (satış fiyatı)
                            state.custom_data['reference_price'] = current_price_float
                            backtest_debugger.log_debug(f"KISMİ SATIŞ: Fiyat {current_price_float} >= Referans {reference_price_float} * (1 + {profit_threshold_pct}/100)")
                            backtest_debugger.log_debug(f"Referans fiyat güncellendi: {current_price_float}")
                            return TradingSignal(
                                should_trade=True,
                                side=OrderSide.SELL,
                                quantity=quantity,
                                reason=f"OTT SAT sinyali - Kısmi satış (Referans %{profit_threshold_pct} üzeri)"
                            )
                except (OverflowError, ValueError, ZeroDivisionError) as e:
                    backtest_debugger.log_debug(f"SAT sinyali hesaplama hatası: {e}")
                    return TradingSignal(should_trade=False, reason="SAT sinyali hesaplama hatası")
            
            # Sinyal yok
            return TradingSignal(
                should_trade=False,
                reason="Uygun sinyal bulunamadı"
            )
            
        except Exception as e:
            logger.error(f"Sync calculate signal hatası: {e}")
            from .models import TradingSignal
            return TradingSignal(
                should_trade=False,
                reason=f"Hata: {str(e)}"
            )
    
    def _calculate_backtest_quantity(self, strategy, current_price):
        """Backtest için işlem miktarı hesapla - OVERFLOW KORUMALI VERSİYON"""
        try:
            # Debug: Strategy type güvenli erişim
            strategy_type_value = backtest_debugger.safe_enum_access(strategy.strategy_type, 'unknown')
            backtest_debugger.log_debug(f"Strategy type for quantity calculation: {strategy_type_value}")
            
            # Güvenlik kontrolleri - overflow önleme
            max_safe_value = 1e15  # 1 katrilyon - çok büyük değerler için limit
            min_safe_value = 1e-15  # Çok küçük değerler için limit
            
            # Current price'ı float'a çevir - overflow korumalı
            try:
                current_price_float = float(current_price)
                if abs(current_price_float) > max_safe_value or current_price_float <= 0:
                    backtest_debugger.log_debug(f"Geçersiz fiyat: {current_price_float}")
                    current_price_float = 65400.0  # Varsayılan fiyat
            except (ValueError, TypeError, OverflowError):
                backtest_debugger.log_debug(f"Current price conversion error: {current_price}")
                current_price_float = 65400.0  # Varsayılan fiyat
            
            backtest_debugger.log_debug(f"Current price: {current_price} -> {current_price_float}")
            
            # Strateji tipine göre miktar hesapla - overflow korumalı
            try:
                if strategy_type_value == 'dca_ott':
                    base_usdt = float(strategy.parameters.get('base_usdt', 50.0))
                    if abs(base_usdt) > max_safe_value or base_usdt <= 0:
                        base_usdt = 50.0
                        backtest_debugger.log_debug(f"Base USDT sınırlandı: {base_usdt}")
                    quantity = base_usdt / current_price_float
                elif strategy_type_value == 'grid_ott':
                    usdt_grid = float(strategy.parameters.get('usdt_grid', 30.0))
                    if abs(usdt_grid) > max_safe_value or usdt_grid <= 0:
                        usdt_grid = 30.0
                        backtest_debugger.log_debug(f"USDT grid sınırlandı: {usdt_grid}")
                    quantity = usdt_grid / current_price_float
                elif strategy_type_value == 'bol_grid':
                    initial_usdt = float(strategy.parameters.get('initial_usdt', 50.0))
                    if abs(initial_usdt) > max_safe_value or initial_usdt <= 0:
                        initial_usdt = 50.0
                        backtest_debugger.log_debug(f"Initial USDT sınırlandı: {initial_usdt}")
                    quantity = initial_usdt / current_price_float
                else:
                    quantity = 50.0 / current_price_float  # Default
                
                # Miktar kontrolü
                if abs(quantity) > max_safe_value or quantity <= 0:
                    backtest_debugger.log_debug(f"Geçersiz miktar: {quantity}")
                    quantity = 0.001  # Minimum güvenli miktar
                
                return quantity
                
            except (OverflowError, ValueError, ZeroDivisionError) as e:
                backtest_debugger.log_debug(f"Quantity hesaplama hatası: {e}")
                return 0.001  # Minimum güvenli miktar
                
        except Exception as e:
            backtest_debugger.log_error(e, "Quantity calculation error")
            return 0.001  # Minimum güvenli miktar


# Global instance
excel_backtest_engine = ExcelBacktestEngine()
