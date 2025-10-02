"""
Professional Debug Monitor System
DCA+OTT stratejilerindeki kritik sorunları tespit eden gelişmiş monitoring sistemi
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from .models import Strategy, State, Trade, DCAPosition, StrategyType
from .storage import storage
from .binance import binance_client
from .utils import logger


class AlertLevel(str, Enum):
    """Alert seviyeleri"""
    INFO = "info"
    WARNING = "warning" 
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class DebugAlert:
    """Debug alert modeli"""
    timestamp: datetime
    strategy_id: str
    level: AlertLevel
    category: str
    message: str
    details: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'strategy_id': self.strategy_id,
            'level': self.level.value,
            'category': self.category,
            'message': self.message,
            'details': self.details
        }


class DCADebugMonitor:
    """
    TÜM STRATEJILER için profesyonel debug monitoring sistemi
    
    Özellikler:
    - DCA+OTT: State corruption, pozisyon tutarlılık
    - Grid+OTT: GF tutarlılık, grid mantık kontrolleri  
    - Genel: Trade mantık doğrulama, performance monitoring
    - Alert sistemi ve Telegram bildirimleri
    - Otomatik strateji durdurma (güvenlik)
    """
    
    def __init__(self):
        self.alerts: List[DebugAlert] = []
        self.max_alerts = 100  # Maksimum alert sayısı
        self.last_check: Dict[str, datetime] = {}
        self.check_interval = 300  # 5 dakika
        self.enabled = True
        
        # Performance metrics
        self.check_count = 0
        self.total_check_time = 0.0
        
        # Auto-stop configuration
        self.auto_stop_enabled = True
        self.auto_stop_rules = {
            'critical_issues': True,        # Kritik sorunlarda durdur
            'multiple_errors': True,        # 3+ error'da durdur
            'state_corruption': True,       # State corruption'da durdur
            'consecutive_wrong_trades': True # Ardışık yanlış trade'lerde durdur
        }
        self.stopped_strategies: Dict[str, datetime] = {}  # Otomatik durdurulan stratejiler
        
    def is_check_needed(self, strategy_id: str) -> bool:
        """Check gerekli mi? (Performance optimization)"""
        if not self.enabled:
            return False
        
        # Otomatik durdurulmuş stratejileri kontrol etme
        if strategy_id in self.stopped_strategies:
            return False
            
        last_check = self.last_check.get(strategy_id)
        if not last_check:
            return True
            
        return (datetime.now(timezone.utc) - last_check).total_seconds() > self.check_interval
    
    def add_alert(self, strategy_id: str, level: AlertLevel, category: str, 
                  message: str, details: Dict[str, Any] = None):
        """Alert ekle"""
        alert = DebugAlert(
            timestamp=datetime.now(timezone.utc),
            strategy_id=strategy_id,
            level=level,
            category=category,
            message=message,
            details=details or {}
        )
        
        self.alerts.append(alert)
        
        # Alert limitini aş
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        # Log'a yaz
        log_message = f"[DEBUG-{level.value.upper()}] {strategy_id} | {category} | {message}"
        
        if level == AlertLevel.CRITICAL:
            logger.error(log_message)
        elif level == AlertLevel.ERROR:
            logger.error(log_message)
        elif level == AlertLevel.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        # 📱 TELEGRAM BİLDİRİMİ: Error ve Critical seviyeler için
        if level in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
            asyncio.create_task(self._send_telegram_alert(alert))
    
    async def validate_strategy_state(self, strategy: Strategy, state: State) -> List[Dict]:
        """
        Strateji state'ini detaylı validate et (TÜM STRATEJİLER)
        """
        issues = []
        
        # DCA+OTT validations
        if strategy.strategy_type == StrategyType.DCA_OTT:
            issues.extend(await self._validate_dca_state(strategy, state))
        
        # Grid+OTT validations
        elif strategy.strategy_type == StrategyType.GRID_OTT:
            issues.extend(await self._validate_grid_state(strategy, state))
        
        # BOL-Grid validations
        elif strategy.strategy_type == StrategyType.BOL_GRID:
            issues.extend(await self._validate_bol_grid_state(strategy, state))
        
        # Genel validations (tüm stratejiler için)
        issues.extend(await self._validate_general_state(strategy, state))
        
        return issues
    
    async def _validate_dca_state(self, strategy: Strategy, state: State) -> List[Dict]:
        """
        DCA state'ini detaylı validate et
        """
        issues = []
        
        # 1. Pozisyon tutarlılık kontrolü
        calculated_total = sum(pos.quantity for pos in state.dca_positions)
        if abs(calculated_total - state.total_quantity) > 0.000001:
            issues.append({
                'type': 'position_quantity_mismatch',
                'severity': 'error',
                'calculated': calculated_total,
                'stored': state.total_quantity,
                'difference': abs(calculated_total - state.total_quantity)
            })
        
        # 2. Ortalama maliyet kontrolü
        if state.dca_positions:
            total_cost = sum(pos.buy_price * pos.quantity for pos in state.dca_positions)
            calculated_avg = total_cost / calculated_total if calculated_total > 0 else 0
            
            # Floating point precision için daha toleranslı threshold (0.05$)
            if state.avg_cost and abs(calculated_avg - state.avg_cost) > 0.05:
                issues.append({
                    'type': 'avg_cost_mismatch',
                    'severity': 'error',
                    'calculated': calculated_avg,
                    'stored': state.avg_cost,
                    'difference': abs(calculated_avg - state.avg_cost)
                })
            elif state.avg_cost and abs(calculated_avg - state.avg_cost) > 0.01:
                # Küçük farklar için warning
                issues.append({
                    'type': 'avg_cost_precision_warning',
                    'severity': 'warning',
                    'calculated': calculated_avg,
                    'stored': state.avg_cost,
                    'difference': abs(calculated_avg - state.avg_cost)
                })
        
        # 3. Döngü mantık kontrolü
        if state.dca_positions and state.cycle_number == 0:
            issues.append({
                'type': 'cycle_number_zero_with_positions',
                'severity': 'warning',
                'positions_count': len(state.dca_positions),
                'cycle_number': state.cycle_number
            })
        
        # 4. Pozisyon sırası kontrolü (DCA mantığı)
        if len(state.dca_positions) > 1:
            sorted_positions = sorted(state.dca_positions, key=lambda x: x.timestamp)
            for i in range(1, len(sorted_positions)):
                prev_price = sorted_positions[i-1].buy_price
                curr_price = sorted_positions[i].buy_price
                
                # DCA mantığı: Her alım öncekinden düşük olmalı (genelde)
                if curr_price > prev_price:
                    price_increase = ((curr_price - prev_price) / prev_price) * 100
                    issues.append({
                        'type': 'dca_price_increase',
                        'severity': 'warning',
                        'position_index': i,
                        'prev_price': prev_price,
                        'curr_price': curr_price,
                        'increase_pct': price_increase
                    })
        
        return issues
    
    async def _validate_grid_state(self, strategy: Strategy, state: State) -> List[Dict]:
        """
        Grid+OTT state'ini validate et
        """
        issues = []
        
        # 1. GF (Grid Foundation) kontrolü
        if state.gf is None or state.gf <= 0:
            issues.append({
                'type': 'invalid_grid_foundation',
                'severity': 'warning',
                'gf_value': state.gf,
                'message': 'Grid Foundation (GF) geçersiz veya sıfır'
            })
        
        # 2. Grid parametreleri kontrolü
        if not strategy.y or strategy.y <= 0:
            issues.append({
                'type': 'invalid_grid_step',
                'severity': 'error',
                'y_value': strategy.y,
                'message': 'Grid step (y) geçersiz'
            })
        
        if not strategy.usdt_grid or strategy.usdt_grid <= 0:
            issues.append({
                'type': 'invalid_usdt_grid',
                'severity': 'error', 
                'usdt_grid_value': strategy.usdt_grid,
                'message': 'USDT/Grid miktarı geçersiz'
            })
        
        # 3. Açık emir sayısı kontrolü
        if len(state.open_orders) > 10:
            issues.append({
                'type': 'too_many_open_orders',
                'severity': 'warning',
                'open_orders_count': len(state.open_orders),
                'message': f'Çok fazla açık emir: {len(state.open_orders)}'
            })
        
        return issues
    
    async def _validate_general_state(self, strategy: Strategy, state: State) -> List[Dict]:
        """
        Tüm stratejiler için genel validations
        """
        issues = []
        
        # 1. Son güncelleme kontrolü
        if state.last_update:
            time_diff = datetime.now(timezone.utc) - state.last_update
            if time_diff.total_seconds() > 3600:  # 1 saat
                issues.append({
                    'type': 'stale_state',
                    'severity': 'warning',
                    'hours_ago': time_diff.total_seconds() / 3600,
                    'message': f'State {time_diff.total_seconds() / 3600:.1f} saat önce güncellenmiş'
                })
        
        # 2. Strateji aktiflik kontrolü
        if not strategy.active:
            issues.append({
                'type': 'strategy_inactive',
                'severity': 'info',
                'message': 'Strateji pasif durumda'
            })
        
        # 3. OTT parametreleri kontrolü
        if not strategy.ott or strategy.ott.period < 5 or strategy.ott.period > 100:
            issues.append({
                'type': 'invalid_ott_period',
                'severity': 'warning',
                'ott_period': strategy.ott.period if strategy.ott else None,
                'message': 'OTT period geçersiz aralıkta'
            })
        
        return issues
    
    async def _validate_bol_grid_state(self, strategy: Strategy, state: State) -> List[Dict]:
        """
        BOL-Grid state'ini validate et
        """
        issues = []
        
        # 1. Döngü tutarlılık kontrolü
        custom_data = state.custom_data or {}
        cycle_number = custom_data.get('cycle_number', 0)
        cycle_step = custom_data.get('cycle_step', 'D0')
        positions = custom_data.get('positions', [])
        
        # Döngü numarası ve pozisyon tutarlılığı
        if cycle_number > 0 and not positions:
            issues.append({
                'type': 'cycle_position_mismatch',
                'severity': 'critical',
                'cycle_number': cycle_number,
                'positions_count': len(positions),
                'message': f'Döngü {cycle_number} aktif ama pozisyon yok'
            })
        
        if cycle_number == 0 and positions:
            issues.append({
                'type': 'orphan_positions',
                'severity': 'warning',
                'cycle_number': cycle_number,
                'positions_count': len(positions),
                'message': 'Döngü 0 ama pozisyon var'
            })
        
        # 2. Pozisyon tutarlılık kontrolü
        if positions:
            calculated_total = sum(float(pos.get('quantity', 0)) for pos in positions)
            stated_total = custom_data.get('total_quantity', 0)
            
            if abs(calculated_total - stated_total) > 0.000001:
                issues.append({
                    'type': 'position_quantity_mismatch',
                    'severity': 'critical',
                    'calculated_total': calculated_total,
                    'stated_total': stated_total,
                    'message': 'Pozisyon miktarları tutmuyor'
                })
            
            # Ortalama maliyet kontrolü
            if calculated_total > 0:
                calculated_avg = sum(float(pos.get('quantity', 0)) * float(pos.get('price', 0)) for pos in positions) / calculated_total
                stated_avg = custom_data.get('average_cost', 0)
                
                if abs(calculated_avg - stated_avg) > 0.01:  # 1 cent tolerance
                    issues.append({
                        'type': 'average_cost_mismatch',
                        'severity': 'error',
                        'calculated_avg': calculated_avg,
                        'stated_avg': stated_avg,
                        'message': 'Ortalama maliyet hesabı yanlış'
                    })
        
        # 3. Bollinger Bands parametreleri kontrolü
        params = strategy.parameters or {}
        bollinger_period = params.get('bollinger_period', 250)
        bollinger_std = params.get('bollinger_std', 2.0)
        
        if bollinger_period < 20 or bollinger_period > 500:
            issues.append({
                'type': 'invalid_bollinger_period',
                'severity': 'warning',
                'period': bollinger_period,
                'message': f'Bollinger periyodu geçersiz: {bollinger_period}'
            })
        
        if bollinger_std < 1.0 or bollinger_std > 3.0:
            issues.append({
                'type': 'invalid_bollinger_std',
                'severity': 'warning',
                'std_dev': bollinger_std,
                'message': f'Bollinger standart sapma geçersiz: {bollinger_std}'
            })
        
        # 4. Risk parametreleri kontrolü
        initial_usdt = params.get('initial_usdt', 100)
        min_drop_pct = params.get('min_drop_pct', 2.0)
        min_profit_pct = params.get('min_profit_pct', 1.0)
        
        if initial_usdt < 10 or initial_usdt > 10000:
            issues.append({
                'type': 'invalid_initial_usdt',
                'severity': 'warning',
                'initial_usdt': initial_usdt,
                'message': f'İlk alım tutarı geçersiz: ${initial_usdt}'
            })
        
        if min_drop_pct < 0.5 or min_drop_pct > 20:
            issues.append({
                'type': 'invalid_min_drop',
                'severity': 'warning',
                'min_drop_pct': min_drop_pct,
                'message': f'Min düşüş % geçersiz: {min_drop_pct}%'
            })
        
        if min_profit_pct < 0.1 or min_profit_pct > 10:
            issues.append({
                'type': 'invalid_min_profit',
                'severity': 'warning',
                'min_profit_pct': min_profit_pct,
                'message': f'Min kar % geçersiz: {min_profit_pct}%'
            })
        
        # 5. Son alım/satış fiyat tutarlılığı
        last_buy_price = custom_data.get('last_buy_price', 0)
        last_sell_price = custom_data.get('last_sell_price', 0)
        
        if positions and last_buy_price <= 0:
            issues.append({
                'type': 'missing_last_buy_price',
                'severity': 'warning',
                'message': 'Pozisyon var ama son alım fiyatı kayıtlı değil'
            })
        
        # 6. Bollinger Bands veri kontrolü
        last_bollinger = custom_data.get('last_bollinger', {})
        if not last_bollinger or not all(k in last_bollinger for k in ['upper', 'middle', 'lower']):
            issues.append({
                'type': 'missing_bollinger_data',
                'severity': 'info',
                'message': 'Bollinger Bands verisi eksik'
            })
        
        return issues
    
    async def validate_recent_trades(self, strategy: Strategy, limit: int = 10) -> List[Dict]:
        """
        Son trade'lerin mantığını validate et (TÜM STRATEJİLER)
        """
        issues = []
        
        try:
            trades = await storage.load_trades(strategy.id, limit=limit)
            if len(trades) < 2:
                return issues
            
            # State yükle - sadece state ile tutarlı trade'leri kontrol et
            state = await storage.load_state(strategy.id)
            if not state:
                return issues
            
            # Sadece son 24 saatteki trade'leri kontrol et (eski trade'ler için sürekli alert engelle)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            recent_trades = [t for t in trades if t.timestamp > recent_cutoff]
            
            # DCA stratejileri için: Sadece state'deki pozisyonlarla ilişkili trade'leri kontrol et
            if strategy.strategy_type == StrategyType.DCA_OTT and state.dca_positions:
                state_order_ids = {pos.order_id for pos in state.dca_positions}
                # Sadece state'de olan pozisyonların trade'lerini kontrol et
                recent_trades = [t for t in recent_trades if t.order_id in state_order_ids]
            
            if len(recent_trades) < 2:
                return issues
            
            # Trade'leri zaman sırasına göre sırala (sadece son 24 saat)
            sorted_trades = sorted(recent_trades, key=lambda x: x.timestamp)
            
            for i in range(1, len(sorted_trades)):
                prev_trade = sorted_trades[i-1]
                curr_trade = sorted_trades[i]
                
                # DCA stratejileri için ardışık alım kontrolü - DÜZELTME (25 Eylül 2025)
                # Bu kontrol çok katıydı, DCA'da ardışık alımlar normal olabilir
                # Sadece çok büyük fiyat artışlarını kontrol et
                if strategy.strategy_type == StrategyType.DCA_OTT:
                    if prev_trade.side.value == 'buy' and curr_trade.side.value == 'buy':
                        if curr_trade.price > prev_trade.price:
                            price_increase = ((curr_trade.price - prev_trade.price) / prev_trade.price) * 100
                            # Sadece %5'ten büyük artışları kritik olarak işaretle
                            if price_increase > 5.0:  # %5'ten büyük artış
                                issues.append({
                                    'type': 'consecutive_buy_price_increase',
                                    'severity': 'critical',
                                    'strategy_type': 'dca_ott',
                                    'prev_trade': {
                                        'timestamp': prev_trade.timestamp.isoformat(),
                                        'price': prev_trade.price,
                                        'quantity': prev_trade.quantity
                                    },
                                    'curr_trade': {
                                        'timestamp': curr_trade.timestamp.isoformat(),
                                        'price': curr_trade.price,
                                        'quantity': curr_trade.quantity
                                    },
                                    'price_increase_pct': price_increase
                                })
                            else:
                                # Küçük artışları sadece warning olarak işaretle
                                issues.append({
                                    'type': 'consecutive_buy_price_increase',
                                    'severity': 'warning',
                                    'strategy_type': 'dca_ott',
                                    'prev_trade': {
                                        'timestamp': prev_trade.timestamp.isoformat(),
                                        'price': prev_trade.price,
                                        'quantity': prev_trade.quantity
                                    },
                                    'curr_trade': {
                                        'timestamp': curr_trade.timestamp.isoformat(),
                                        'price': curr_trade.price,
                                        'quantity': curr_trade.quantity
                                    },
                                    'price_increase_pct': price_increase
                                })
                
                # Grid stratejileri için mantık kontrolleri
                elif strategy.strategy_type == StrategyType.GRID_OTT:
                    # Grid'de çok hızlı ardışık trade'ler şüpheli olabilir
                    time_diff = (curr_trade.timestamp - prev_trade.timestamp).total_seconds()
                    if time_diff < 60:  # 1 dakikadan kısa
                        issues.append({
                            'type': 'rapid_consecutive_trades',
                            'severity': 'warning',
                            'strategy_type': 'grid_ott',
                            'time_diff_seconds': time_diff,
                            'message': f'Çok hızlı ardışık trade: {time_diff:.1f}s'
                        })
        
        except Exception as e:
            issues.append({
                'type': 'trade_validation_error',
                'severity': 'error',
                'error': str(e)
            })
        
        return issues
    
    async def check_strategy_health(self, strategy: Strategy) -> Dict[str, Any]:
        """
        Strateji sağlığını kapsamlı kontrol et (TÜM STRATEJİLER)
        """
        start_time = datetime.now(timezone.utc)
        health_report = {
            'strategy_id': strategy.id,
            'strategy_name': strategy.name,
            'check_timestamp': start_time.isoformat(),
            'status': 'healthy',
            'issues': [],
            'metrics': {},
            'recommendations': []
        }
        
        try:
            # State yükle
            state = await storage.load_state(strategy.id)
            if not state:
                health_report['status'] = 'critical'
                health_report['issues'].append({
                    'type': 'state_not_found',
                    'severity': 'critical',
                    'message': 'State dosyası bulunamadı'
                })
                return health_report
            
            # State validation (tüm stratejiler için)
            state_issues = await self.validate_strategy_state(strategy, state)
            health_report['issues'].extend(state_issues)
            
            # Trade validation
            trade_issues = await self.validate_recent_trades(strategy)
            health_report['issues'].extend(trade_issues)
            
            # Metrics hesapla
            health_report['metrics'] = {
                'positions_count': len(state.dca_positions),
                'total_quantity': state.total_quantity,
                'avg_cost': state.avg_cost,
                'cycle_number': state.cycle_number,
                'cycle_trade_count': state.cycle_trade_count,
                'last_update_minutes_ago': (start_time - state.last_update).total_seconds() / 60
            }
            
            # Genel sağlık durumu
            critical_issues = [i for i in health_report['issues'] if i.get('severity') == 'critical']
            error_issues = [i for i in health_report['issues'] if i.get('severity') == 'error']
            
            if critical_issues:
                health_report['status'] = 'critical'
            elif error_issues:
                health_report['status'] = 'error'
            elif health_report['issues']:
                health_report['status'] = 'warning'
            
            # Öneriler
            if critical_issues or error_issues:
                health_report['recommendations'].append('Stratejiyi durdurup manuel kontrol edin')
            
            if len(state.dca_positions) > 5:
                health_report['recommendations'].append('Çok fazla pozisyon var, kısmi satış düşünün')
            
            # Performance metric
            check_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.total_check_time += check_duration
            self.check_count += 1
            
        except Exception as e:
            health_report['status'] = 'critical'
            health_report['issues'].append({
                'type': 'health_check_error',
                'severity': 'critical',
                'error': str(e)
            })
        
        return health_report
    
    async def monitor_all_strategies(self) -> Dict[str, Any]:
        """
        TÜM STRATEJİLERİ monitoring et (DCA+OTT + Grid+OTT)
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            strategies = await storage.load_strategies()
            active_strategies = [s for s in strategies if s.active]
            
            if not active_strategies:
                return {
                    'status': 'no_active_strategies',
                    'message': 'Aktif strateji bulunamadı'
                }
            
            results = {
                'check_timestamp': start_time.isoformat(),
                'strategies_checked': len(active_strategies),
                'strategy_breakdown': {
                    'dca_ott': len([s for s in active_strategies if s.strategy_type == StrategyType.DCA_OTT]),
                    'grid_ott': len([s for s in active_strategies if s.strategy_type == StrategyType.GRID_OTT])
                },
                'results': {},
                'summary': {
                    'healthy': 0,
                    'warning': 0,
                    'error': 0,
                    'critical': 0
                }
            }
            
            # Her stratejiyi kontrol et
            for strategy in active_strategies:
                if not self.is_check_needed(strategy.id):
                    continue
                
                health_report = await self.check_strategy_health(strategy)
                results['results'][strategy.id] = health_report
                
                # Summary güncelle
                status = health_report['status']
                if status in results['summary']:
                    results['summary'][status] += 1
                
                # Alert oluştur (kritik durumlar için)
                if health_report['issues']:
                    for issue in health_report['issues']:
                        if issue.get('severity') in ['critical', 'error']:
                            self.add_alert(
                                strategy.id,
                                AlertLevel.CRITICAL if issue.get('severity') == 'critical' else AlertLevel.ERROR,
                                issue.get('type', 'unknown'),
                                issue.get('message', str(issue)),
                                issue
                            )
                
                # Son check zamanını güncelle
                self.last_check[strategy.id] = start_time
            
            # Performance summary
            check_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            results['performance'] = {
                'check_duration_ms': int(check_duration * 1000),
                'avg_check_time_ms': int((self.total_check_time / self.check_count * 1000)) if self.check_count > 0 else 0,
                'total_checks': self.check_count
            }
            
            return results
            
        except Exception as e:
            logger.error(f"DCA monitoring hatası: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'check_timestamp': start_time.isoformat()
            }
    
    async def get_strategy_diagnostics(self, strategy_id: str) -> Dict[str, Any]:
        """
        Belirli strateji için detaylı diagnostics
        """
        try:
            strategy = await storage.get_strategy(strategy_id)
            if not strategy or strategy.strategy_type != StrategyType.DCA_OTT:
                return {'error': 'DCA stratejisi bulunamadı'}
            
            state = await storage.load_state(strategy_id)
            if not state:
                return {'error': 'State bulunamadı'}
            
            # Son 20 trade'i al
            trades = await storage.load_trades(strategy_id, limit=20)
            
            # Güncel market bilgisi
            current_price = None
            try:
                current_price = await binance_client.get_current_price(strategy.symbol.value)
            except:
                pass
            
            # Detaylı analiz
            diagnostics = {
                'strategy_info': {
                    'id': strategy.id,
                    'name': strategy.name,
                    'symbol': strategy.symbol.value,
                    'active': strategy.active
                },
                'state_analysis': {
                    'positions_count': len(state.dca_positions),
                    'total_quantity': state.total_quantity,
                    'avg_cost': state.avg_cost,
                    'cycle_number': state.cycle_number,
                    'cycle_trade_count': state.cycle_trade_count,
                    'last_update_ago_minutes': (datetime.now(timezone.utc) - state.last_update).total_seconds() / 60
                },
                'trade_analysis': {
                    'total_trades': len(trades),
                    'buy_count': sum(1 for t in trades if t.side.value == 'buy'),
                    'sell_count': sum(1 for t in trades if t.side.value == 'sell'),
                    'trades_with_cycle_info': sum(1 for t in trades if t.cycle_info),
                    'last_trade': trades[0].timestamp.isoformat() if trades else None
                },
                'market_info': {
                    'current_price': current_price,
                    'price_vs_avg_cost': ((current_price / state.avg_cost - 1) * 100) if current_price and state.avg_cost else None
                },
                'issues': [],
                'recommendations': []
            }
            
            # State validation
            state_issues = await self.validate_dca_state(strategy, state)
            diagnostics['issues'].extend(state_issues)
            
            # Trade validation
            trade_issues = await self.validate_recent_trades(strategy, limit=10)
            diagnostics['issues'].extend(trade_issues)
            
            # Öneriler
            if len(state.dca_positions) == 0 and state.cycle_number > 0:
                diagnostics['recommendations'].append('Döngü tamamlanmış, yeni döngü için hazır')
            
            if len(state.dca_positions) > 3:
                diagnostics['recommendations'].append('Çok fazla pozisyon var, kısmi satış düşünülebilir')
            
            if current_price and state.avg_cost and current_price > state.avg_cost * 1.02:
                profit_pct = (current_price / state.avg_cost - 1) * 100
                diagnostics['recommendations'].append(f'%{profit_pct:.1f} kârda, satış düşünülebilir')
            
            return diagnostics
            
        except Exception as e:
            return {'error': f'Diagnostics hatası: {e}'}
    
    def get_recent_alerts(self, strategy_id: str = None, limit: int = 20) -> List[Dict]:
        """Son alert'leri getir"""
        filtered_alerts = self.alerts
        
        if strategy_id:
            filtered_alerts = [a for a in self.alerts if a.strategy_id == strategy_id]
        
        # En yeni en üstte
        sorted_alerts = sorted(filtered_alerts, key=lambda x: x.timestamp, reverse=True)
        
        return [alert.to_dict() for alert in sorted_alerts[:limit]]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Performance istatistikleri"""
        return {
            'total_checks': self.check_count,
            'avg_check_time_ms': int((self.total_check_time / self.check_count * 1000)) if self.check_count > 0 else 0,
            'total_alerts': len(self.alerts),
            'enabled': self.enabled,
            'check_interval_seconds': self.check_interval
        }
    
    def enable_debug(self):
        """Debug monitoring'i aktif et"""
        self.enabled = True
        logger.info("DCA Debug Monitor aktif edildi")
    
    def disable_debug(self):
        """Debug monitoring'i pasif et"""
        self.enabled = False
        logger.info("DCA Debug Monitor pasif edildi")
    
    async def evaluate_auto_stop(self, strategy: Strategy, health_report: Dict) -> bool:
        """
        Stratejiyi otomatik durdurma kararı ver
        """
        if not self.auto_stop_enabled:
            return False
        
        strategy_id = strategy.id
        issues = health_report.get('issues', [])
        
        # Kritik sorun sayıları
        critical_count = sum(1 for i in issues if i.get('severity') == 'critical')
        error_count = sum(1 for i in issues if i.get('severity') == 'error')
        
        should_stop = False
        stop_reason = ""
        
        # Kural 1: Kritik sorunlar
        if critical_count > 0 and self.auto_stop_rules['critical_issues']:
            should_stop = True
            stop_reason = f"{critical_count} kritik sorun tespit edildi"
        
        # Kural 2: Çoklu error'lar
        elif error_count >= 3 and self.auto_stop_rules['multiple_errors']:
            should_stop = True
            stop_reason = f"{error_count} error tespit edildi"
        
        # Kural 3: State corruption
        elif any(i.get('type') in ['position_quantity_mismatch', 'avg_cost_mismatch'] 
                 and i.get('severity') in ['critical', 'error'] for i in issues) and self.auto_stop_rules['state_corruption']:
            should_stop = True
            stop_reason = "State corruption tespit edildi"
        
        # Kural 4: Ardışık yanlış trade'ler
        elif any(i.get('type') == 'consecutive_buy_price_increase' 
                 and i.get('severity') == 'critical' for i in issues) and self.auto_stop_rules['consecutive_wrong_trades']:
            should_stop = True
            stop_reason = "Ardışık yanlış trade tespit edildi"
        
        if should_stop:
            try:
                # Stratejiyi durdur
                strategy.active = False
                from .storage import storage
                await storage.save_strategy(strategy)
                
                # Otomatik durdurma kaydı
                self.stopped_strategies[strategy_id] = datetime.now(timezone.utc)
                
                # Critical alert oluştur
                self.add_alert(
                    strategy_id,
                    AlertLevel.CRITICAL,
                    'auto_stop',
                    f"Strateji otomatik durduruldu: {stop_reason}",
                    {
                        'stop_reason': stop_reason,
                        'critical_count': critical_count,
                        'error_count': error_count,
                        'issues': issues
                    }
                )
                
                # Telegram bildirimi gönder
                try:
                    from .telegram import telegram_notifier
                    await telegram_notifier.send_message(
                        f"🚨 OTOMATIK DURDURMA\n"
                        f"Strateji: {strategy.name}\n"
                        f"Sebep: {stop_reason}\n"
                        f"Kritik: {critical_count}, Error: {error_count}"
                    )
                except:
                    pass
                
                logger.error(f"🚨 OTOMATIK DURDURMA: {strategy.name} ({strategy_id}) - {stop_reason}")
                return True
                
            except Exception as e:
                logger.error(f"Otomatik durdurma hatası {strategy_id}: {e}")
                return False
        
        return False
    
    def configure_auto_stop(self, **rules):
        """Auto-stop kurallarını yapılandır"""
        self.auto_stop_rules.update(rules)
        logger.info(f"Auto-stop kuralları güncellendi: {self.auto_stop_rules}")
    
    def enable_auto_stop(self):
        """Otomatik durdurma'yı aktif et"""
        self.auto_stop_enabled = True
        logger.info("Otomatik strateji durdurma aktif edildi")
    
    def disable_auto_stop(self):
        """Otomatik durdurma'yı pasif et"""
        self.auto_stop_enabled = False
        logger.info("Otomatik strateji durdurma pasif edildi")
    
    def get_stopped_strategies(self) -> Dict[str, str]:
        """Otomatik durdurulan stratejileri listele"""
        return {
            strategy_id: stop_time.isoformat() 
            for strategy_id, stop_time in self.stopped_strategies.items()
        }
    
    def clear_stopped_strategy(self, strategy_id: str):
        """Durdurulmuş stratejiyi listeden çıkar (yeniden monitoring için)"""
        if strategy_id in self.stopped_strategies:
            del self.stopped_strategies[strategy_id]
            logger.info(f"Durdurulmuş strateji listeden çıkarıldı: {strategy_id}")
    
    async def _send_telegram_alert(self, alert: DebugAlert):
        """
        Telegram'a debug alert gönder
        """
        try:
            from .telegram import telegram_notifier
            
            # Alert seviyesine göre emoji
            level_emoji = {
                'critical': '🚨',
                'error': '❌',
                'warning': '⚠️',
                'info': 'ℹ️'
            }
            
            emoji = level_emoji.get(alert.level.value, '❓')
            
            # Mesaj formatı (Telegram özel karakterlerini escape et)
            message = f"{emoji} DEBUG ALERT\n"
            message += f"Strateji: {alert.strategy_id[:8]}...\n"
            message += f"Seviye: {alert.level.value.upper()}\n"
            message += f"Kategori: {alert.category}\n"
            message += f"Mesaj: {alert.message.replace('$', 'USD').replace('%', 'pct')}\n"
            message += f"Zaman: {alert.timestamp.strftime('%H:%M:%S')}"
            
            # Detayları ekle (önemli alanlar) - özel karakterleri escape et
            if alert.details:
                if 'calculated' in alert.details and 'stored' in alert.details:
                    calc_val = str(alert.details['calculated']).replace('$', 'USD')
                    stored_val = str(alert.details['stored']).replace('$', 'USD')
                    message += f"\nHesaplanan: {calc_val}"
                    message += f"\nSaklanan: {stored_val}"
                
                if 'price_increase_pct' in alert.details:
                    pct_val = alert.details['price_increase_pct']
                    message += f"\nFiyat Artisi: {pct_val:.2f}pct"
            
            await telegram_notifier.send_message(message)
            
        except Exception as e:
            logger.warning(f"Telegram alert gönderme hatası: {e}")


# Global debug monitor instance - TÜM STRATEJİLER için
universal_debug_monitor = DCADebugMonitor()
