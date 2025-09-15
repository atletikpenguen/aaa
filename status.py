#!/usr/bin/env python3
"""
Strateji Durum Monitörü - Aktif stratejilerin anlık bilgilerini gösterir
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from core.storage import storage
from core.binance import binance_client
from core.indicators import calculate_ott

def format_number(value, decimals=8):
    """Sayı formatla"""
    if value is None:
        return "0"
    try:
        return f"{float(value):.{decimals}f}".rstrip('0').rstrip('.')
    except:
        return str(value)


async def get_strategy_status():
    """Tüm aktif stratejilerin durumunu al"""
    try:
        # Stratejileri yükle
        strategies = await storage.load_strategies()
        active_strategies = [s for s in strategies if s.active]
        
        if not active_strategies:
            print("❌ Aktif strateji bulunamadı!")
            return
        
        print(f"📊 AKTİF STRATEJİLER ({len(active_strategies)} adet)")
        print("=" * 80)
        
        for i, strategy in enumerate(active_strategies, 1):
            await print_strategy_status(i, strategy)
            if i < len(active_strategies):
                print("-" * 80)
                
    except Exception as e:
        print(f"❌ Hata: {e}")


async def print_strategy_status(index, strategy):
    """Tek strateji durumunu yazdır"""
    try:
        # State yükle
        state = await storage.load_state(strategy.id)
        
        # Güncel fiyat al
        current_price = None
        try:
            current_price = await binance_client.get_current_price(strategy.symbol.value)
        except:
            pass
        
        # OTT hesapla
        ott_result = None
        if current_price:
            try:
                # OHLCV verisi al
                ohlcv_data = await binance_client.fetch_ohlcv(
                    strategy.symbol.value,
                    strategy.timeframe.value,
                    limit=max(100, strategy.ott.period + 10)
                )
                
                if ohlcv_data:
                    close_prices = [float(bar[4]) for bar in ohlcv_data[:-1]]
                    ott_result = calculate_ott(close_prices, strategy.ott.period, strategy.ott.opt, strategy.name)
            except:
                pass
        
        # Header
        print(f"🎯 {index}. {strategy.name} ({strategy.symbol.value})")
        print(f"   ⏱️  Timeframe: {strategy.timeframe.value} | Grid: {format_number(strategy.y, 6)} | USDT/Grid: {format_number(strategy.usdt_grid, 2)}")
        
        # Fiyat Bilgileri
        if current_price and state and state.gf is not None and state.gf > 0:
            delta = abs(current_price - state.gf)
            delta_pct = (delta / state.gf) * 100 if state.gf is not None and state.gf > 0 else 0
            
            print(f"   💰 Güncel Fiyat: ${format_number(current_price, 6)}")
            print(f"   🎯 Grid Foundation (GF): ${format_number(state.gf, 6)}")
            print(f"   📏 Delta: {format_number(delta, 6)} ({delta_pct:.2f}%)")
            
            # Grid analizi
            if delta > strategy.y:
                z = int(delta // strategy.y)
                if current_price > state.gf:
                    target_price = state.gf + (z * strategy.y)
                    print(f"   📈 SAT Sinyali: Z={z}, Hedef: ${format_number(target_price, 6)}")
                else:
                    target_price = state.gf - (z * strategy.y)
                    print(f"   📉 AL Sinyali: Z={z}, Hedef: ${format_number(target_price, 6)}")
            else:
                print(f"   ⏳ Sinyal Yok (Delta < Grid Aralığı)")
        else:
            if current_price:
                print(f"   💰 Güncel Fiyat: ${format_number(current_price, 6)}")
            if not state or state.gf == 0:
                print(f"   🎯 Grid Foundation: Henüz ayarlanmadı")
        
        # OTT Bilgileri
        if ott_result:
            print(f"   🔄 OTT Modu: {ott_result.mode.value} | EMA: ${format_number(ott_result.baseline, 6)}")
            print(f"   📊 OTT Bantları: Alt=${format_number(ott_result.lower, 6)} | Üst=${format_number(ott_result.upper, 6)}")
        else:
            print(f"   🔄 OTT: {strategy.ott.period}/{strategy.ott.opt}% (hesaplanamadı)")
        
        # Emir Durumu
        if state and state.open_orders:
            print(f"   📋 Açık Emirler: {len(state.open_orders)} adet")
            for order in state.open_orders[-3:]:  # Son 3 emri göster
                side_emoji = "🟢" if order.side.value == "buy" else "🔴"
                print(f"      {side_emoji} {order.side.value.upper()} Z{order.z}: {format_number(order.quantity, 8)} @ ${format_number(order.price, 6)}")
        else:
            print(f"   📋 Açık Emirler: Yok")
        
        # Son Güncelleme
        if state and state.last_update:
            time_diff = datetime.now(timezone.utc) - state.last_update
            minutes_ago = int(time_diff.total_seconds() / 60)
            print(f"   🕐 Son Güncelleme: {minutes_ago} dakika önce")
        
        # İstatistikler
        print(f"   📈 Toplam İşlem: {strategy.total_trades}")
        
    except Exception as e:
        print(f"❌ {strategy.name} durumu alınamadı: {e}")


async def get_quick_status():
    """Hızlı durum özeti"""
    try:
        strategies = await storage.load_strategies()
        active_strategies = [s for s in strategies if s.active]
        
        if not active_strategies:
            print("❌ Aktif strateji yok")
            return
        
        print(f"⚡ HIZLI DURUM ({len(active_strategies)} aktif strateji)")
        
        for strategy in active_strategies:
            state = await storage.load_state(strategy.id)
            
            try:
                current_price = await binance_client.get_current_price(strategy.symbol.value)
                price_str = f"${format_number(current_price, 4)}" if current_price else "N/A"
            except:
                price_str = "N/A"
            
            gf_str = f"${format_number(state.gf, 4)}" if state and state.gf is not None and state.gf > 0 else "N/A"
            orders_count = len(state.open_orders) if state else 0
            
            print(f"  🎯 {strategy.name} ({strategy.symbol.value}): Fiyat={price_str} | GF={gf_str} | Emirler={orders_count}")
            
    except Exception as e:
        print(f"❌ Hata: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        asyncio.run(get_quick_status())
    else:
        asyncio.run(get_strategy_status())
