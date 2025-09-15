#!/usr/bin/env python3
"""
Professional Debug Monitor Script
DCA+OTT stratejilerindeki kritik sorunları tespit eden gelişmiş monitoring sistemi
"""

import asyncio
import time
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Core modüllerini import et
from core.storage import storage
from core.strategy_engine import StrategyEngine
from core.binance import binance_client
from core.indicators import calculate_ott
from core.models import Strategy, State, StrategyType
from core.utils import logger
from core.debug_monitor import universal_debug_monitor, AlertLevel


class TaskDebugger:
    """Profesyonel strateji debug sistemi"""
    
    def __init__(self):
        self.engine = StrategyEngine()
        self.check_interval = 300  # 5 dakika (saniye)
        self.last_check = {}
        self.focus_on_dca = True  # DCA stratejilerine odaklan
        
    async def check_all_strategies(self):
        """Tüm stratejileri profesyonel monitoring ile kontrol et"""
        try:
            print(f"\n{'='*80}")
            print(f"🔍 PROFESSIONAL DEBUG MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*80}")
            
            # Stratejileri yükle
            strategies = await storage.load_strategies()
            active_strategies = [s for s in strategies if s.active]
            
            if not active_strategies:
                print("❌ Aktif strateji bulunamadı!")
                return
            
            # DCA stratejilerine odaklan
            if self.focus_on_dca:
                dca_strategies = [s for s in active_strategies if s.strategy_type == StrategyType.DCA_OTT]
                if dca_strategies:
                    print(f"🎯 DCA+OTT stratejilerine odaklanılıyor: {len(dca_strategies)} strateji")
                    await self._check_dca_strategies_professional(dca_strategies)
                else:
                    print("📊 DCA+OTT stratejisi bulunamadı")
            
            # Genel strateji kontrolü
            print(f"\n📊 Genel Strateji Durumu: {len(active_strategies)} aktif strateji")
            for i, strategy in enumerate(active_strategies, 1):
                await self.check_strategy_status(i, strategy)
                
            print(f"{'='*80}")
            print(f"✅ Professional debug kontrolü tamamlandı - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*80}\n")
            
        except Exception as e:
            logger.error(f"Debug kontrolü hatası: {e}")
            print(f"❌ Debug kontrolü hatası: {e}")
    
    async def _check_dca_strategies_professional(self, dca_strategies: List[Strategy]):
        """DCA stratejileri için profesyonel monitoring"""
        print(f"\n🔬 DCA PROFESSIONAL MONITORING")
        print(f"{'─'*60}")
        
        # Tüm stratejileri monitor et
        monitor_result = await universal_debug_monitor.monitor_all_strategies()
        
        if monitor_result.get('status') == 'error':
            print(f"❌ Monitoring hatası: {monitor_result.get('error')}")
            return
        
        # Summary göster
        summary = monitor_result.get('summary', {})
        print(f"📊 Sağlık Özeti:")
        print(f"   ✅ Sağlıklı: {summary.get('healthy', 0)}")
        print(f"   ⚠️ Uyarı: {summary.get('warning', 0)}")
        print(f"   ❌ Hata: {summary.get('error', 0)}")
        print(f"   🚨 Kritik: {summary.get('critical', 0)}")
        
        # Detaylı sonuçlar
        results = monitor_result.get('results', {})
        for strategy_id, health_report in results.items():
            strategy = next((s for s in dca_strategies if s.id == strategy_id), None)
            if not strategy:
                continue
                
            print(f"\n🎯 {strategy.name} ({strategy_id[:8]}...)")
            print(f"   📊 Durum: {health_report['status'].upper()}")
            
            # Metrics
            metrics = health_report.get('metrics', {})
            print(f"   💰 Pozisyon: {metrics.get('positions_count', 0)} adet")
            print(f"   🔄 Döngü: D{metrics.get('cycle_number', 0)}-{metrics.get('cycle_trade_count', 0)}")
            print(f"   💵 Ortalama Maliyet: ${metrics.get('avg_cost', 0):.4f}")
            print(f"   ⏰ Son Güncelleme: {metrics.get('last_update_minutes_ago', 0):.1f} dakika önce")
            
            # Issues
            issues = health_report.get('issues', [])
            if issues:
                print(f"   ⚠️ Sorunlar ({len(issues)} adet):")
                for issue in issues[:3]:  # İlk 3 sorunu göster
                    severity_icon = {
                        'critical': '🚨',
                        'error': '❌', 
                        'warning': '⚠️',
                        'info': 'ℹ️'
                    }.get(issue.get('severity'), '❓')
                    print(f"      {severity_icon} {issue.get('type', 'unknown')}")
                
                if len(issues) > 3:
                    print(f"      ... ve {len(issues) - 3} sorun daha")
            
            # Öneriler
            recommendations = health_report.get('recommendations', [])
            if recommendations:
                print(f"   💡 Öneriler:")
                for rec in recommendations[:2]:
                    print(f"      • {rec}")
        
        # Performance
        performance = monitor_result.get('performance', {})
        print(f"\n⚡ Performance:")
        print(f"   🕐 Kontrol süresi: {performance.get('check_duration_ms', 0)}ms")
        print(f"   📊 Ortalama süre: {performance.get('avg_check_time_ms', 0)}ms")
        
        # Son alert'ler
        recent_alerts = universal_debug_monitor.get_recent_alerts(limit=5)
        if recent_alerts:
            print(f"\n🚨 Son Alert'ler ({len(recent_alerts)} adet):")
            for alert in recent_alerts:
                timestamp = datetime.fromisoformat(alert['timestamp']).strftime('%H:%M:%S')
                level_icon = {
                    'critical': '🚨',
                    'error': '❌',
                    'warning': '⚠️',
                    'info': 'ℹ️'
                }.get(alert['level'], '❓')
                print(f"   {level_icon} {timestamp} | {alert['strategy_id'][:8]}... | {alert['message']}")
        
        print(f"{'─'*60}")
        print(f"🔬 DCA Professional Monitoring tamamlandı")
    
    async def check_strategy_status(self, index: int, strategy: Strategy):
        """Tek strateji durumunu kontrol et"""
        try:
            print(f"\n🎯 {index}. {strategy.name} ({strategy.symbol.value})")
            print(f"   📋 ID: {strategy.id}")
            print(f"   ⏱️  Timeframe: {strategy.timeframe.value}")
            print(f"   🔧 Strateji Türü: {strategy.strategy_type.value}")
            
            # State yükle
            state = await storage.load_state(strategy.id)
            if not state:
                print(f"   ❌ State yüklenemedi!")
                return
            
            # Güncel fiyat al
            current_price = None
            try:
                current_price = await binance_client.get_current_price(strategy.symbol.value)
            except Exception as e:
                print(f"   ❌ Fiyat alma hatası: {e}")
            
            # OTT hesapla
            ott_result = None
            if current_price:
                try:
                    ohlcv_data = await binance_client.fetch_ohlcv(
                        strategy.symbol.value,
                        strategy.timeframe.value,
                        limit=max(100, strategy.ott.period + 10)
                    )
                    
                    if ohlcv_data:
                        close_prices = [float(bar[4]) for bar in ohlcv_data[:-1]]
                        ott_result = calculate_ott(close_prices, strategy.ott.period, strategy.ott.opt, strategy.name)
                except Exception as e:
                    print(f"   ❌ OTT hesaplama hatası: {e}")
            
            # Durum bilgileri
            print(f"   💰 Güncel Fiyat: ${current_price:.6f}" if current_price else "   💰 Güncel Fiyat: N/A")
            
            if state.gf is not None and state.gf > 0:
                print(f"   🎯 Grid Foundation (GF): ${state.gf:.6f}")
                
                if current_price:
                    delta = abs(current_price - state.gf)
                    delta_pct = (delta / state.gf) * 100
                    print(f"   📏 Delta: {delta:.6f} ({delta_pct:.2f}%)")
                    
                    # Grid analizi
                    if strategy.strategy_type.value == 'grid_ott' and strategy.y:
                        if delta > strategy.y:
                            z = int(delta // strategy.y)
                            if current_price > state.gf:
                                target_price = state.gf + (z * strategy.y)
                                print(f"   📈 SAT Sinyali: Z={z}, Hedef: ${target_price:.6f}")
                            else:
                                target_price = state.gf - (z * strategy.y)
                                print(f"   📉 AL Sinyali: Z={z}, Hedef: ${target_price:.6f}")
                        else:
                            print(f"   ⏳ Sinyal Yok (Delta < Grid Aralığı: {strategy.y})")
            else:
                print(f"   🎯 Grid Foundation: Henüz ayarlanmadı")
            
            # OTT bilgileri
            if ott_result:
                print(f"   🔄 OTT Modu: {ott_result.mode.value}")
                print(f"   📊 OTT EMA: ${ott_result.baseline:.6f}")
                print(f"   📊 OTT Bantları: Alt=${ott_result.lower:.6f} | Üst=${ott_result.upper:.6f}")
            else:
                print(f"   🔄 OTT: Hesaplanamadı")
            
            # Emir durumu
            open_orders_count = len(state.open_orders) if state.open_orders else 0
            print(f"   📋 Açık Emirler: {open_orders_count}")
            
            if open_orders_count > 0:
                for order in state.open_orders[:3]:  # İlk 3 emri göster
                    print(f"      - {order.side.value} {order.quantity} @ ${order.price:.6f}")
                if len(state.open_orders) > 3:
                    print(f"      ... ve {len(state.open_orders) - 3} emir daha")
            
            # Son güncelleme
            if state.last_update:
                time_diff = datetime.now(timezone.utc) - state.last_update
                minutes_ago = int(time_diff.total_seconds() / 60)
                print(f"   🕐 Son Güncelleme: {minutes_ago} dakika önce")
            
            # İstatistikler
            print(f"   📈 Toplam İşlem: {strategy.total_trades}")
            print(f"   💰 Toplam Kar: ${strategy.total_profit:.2f}")
            
            # Sinyal testi
            await self.test_strategy_signal(strategy, state, current_price, ott_result)
            
        except Exception as e:
            print(f"   ❌ Strateji kontrolü hatası: {e}")
    
    async def test_strategy_signal(self, strategy: Strategy, state: State, current_price: float, ott_result):
        """Strateji sinyal testi"""
        try:
            if not current_price or not ott_result:
                print(f"   ⚠️  Sinyal testi yapılamadı (fiyat veya OTT eksik)")
                return
            
            # Market info al
            market_info = await binance_client.get_market_info(strategy.symbol.value)
            if not market_info:
                print(f"   ⚠️  Market info alınamadı")
                return
            
            # Handler al
            handler = self.engine.get_strategy_handler(strategy.strategy_type)
            if not handler:
                print(f"   ⚠️  Strateji handler bulunamadı")
                return
            
            # Sinyal hesapla
            signal = await handler.calculate_signal(
                strategy, state, current_price, ott_result, market_info
            )
            
            print(f"   🔍 Sinyal Testi:")
            print(f"      - Sinyal Var: {'✅' if signal.should_trade else '❌'}")
            
            if signal.should_trade:
                print(f"      - Yön: {signal.side.value}")
                print(f"      - Hedef Fiyat: ${signal.target_price:.6f}")
                print(f"      - Miktar: {signal.quantity}")
                print(f"      - Sebep: {signal.reason}")
                
                # Strateji özel veriler
                if signal.strategy_specific_data:
                    for key, value in signal.strategy_specific_data.items():
                        print(f"      - {key}: {value}")
            else:
                print(f"      - Sebep: {signal.reason}")
                
        except Exception as e:
            print(f"   ❌ Sinyal testi hatası: {e}")
    
    async def run_continuous_debug(self):
        """Sürekli debug döngüsü"""
        print("🚀 Strateji Task Debug Script başlatıldı")
        print(f"⏰ Kontrol aralığı: {self.check_interval} saniye ({self.check_interval/60:.1f} dakika)")
        print("🛑 Durdurmak için Ctrl+C tuşlayın\n")
        
        try:
            while True:
                await self.check_all_strategies()
                
                # Sonraki kontrol için bekle
                print(f"⏳ Sonraki kontrol için {self.check_interval} saniye bekleniyor...")
                await asyncio.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Debug script durduruldu")
        except Exception as e:
            print(f"\n❌ Debug script hatası: {e}")


async def main():
    """Ana fonksiyon"""
    debugger = TaskDebugger()
    await debugger.run_continuous_debug()


if __name__ == "__main__":
    asyncio.run(main())
