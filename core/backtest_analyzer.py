"""
Backtest Analiz Modülü
Trading verilerini analiz eder ve performans metrikleri hesaplar.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import io
import re
from core.utils import logger


class BacktestAnalyzer:
    """
    Trading verilerini analiz eden sınıf.
    Excel dosyası veya yapıştırılan veri formatını destekler.
    """
    
    def __init__(self):
        self.required_columns = [
            'Tarih', 'Zaman', 'Sembol', 'İşlem', 'Durum', 'Adet', 
            'Fiyat', 'Gerçekleşme Fiyatı', 'Yüzde Değişim'
        ]
    
    def analyze_excel_file(self, file_content: bytes) -> Dict:
        """
        Excel dosyasını analiz eder.
        
        Args:
            file_content: Excel dosyasının byte içeriği
            
        Returns:
            Analiz sonuçları
        """
        try:
            logger.info(f"Excel dosyası analiz ediliyor, boyut: {len(file_content)} bytes")
            
            # Excel dosyasını oku
            df = pd.read_excel(io.BytesIO(file_content))
            logger.info(f"Excel okundu, satır sayısı: {len(df)}")
            logger.info(f"Sütunlar: {list(df.columns)}")
            
            # Sütun isimlerini temizle
            df.columns = df.columns.str.strip()
            
            # Veriyi analiz et
            result = self._analyze_dataframe(df)
            logger.info(f"Analiz tamamlandı, {len(result.get('trades', []))} işlem bulundu")
            
            return result
            
        except Exception as e:
            logger.error(f"Excel analiz hatası: {e}")
            logger.error(f"Hata detayı: {str(e)}")
            raise Exception(f"Excel dosyası analiz edilemedi: {str(e)}")
    
    def analyze_pasted_data(self, data: str) -> Dict:
        """
        Yapıştırılan veriyi analiz eder.
        
        Args:
            data: Yapıştırılan veri string'i
            
        Returns:
            Analiz sonuçları
        """
        try:
            # Veriyi satırlara böl
            lines = data.strip().split('\n')
            
            if len(lines) < 2:
                raise Exception("Yeterli veri bulunamadı")
            
            # İlk satırı header olarak kullan
            headers = [col.strip() for col in lines[0].split('\t')]
            
            # Veri satırlarını işle
            data_rows = []
            for line in lines[1:]:
                if line.strip():
                    values = line.split('\t')
                    if len(values) >= len(headers):
                        data_rows.append(values[:len(headers)])
            
            # DataFrame oluştur
            df = pd.DataFrame(data_rows, columns=headers)
            
            # Veriyi analiz et
            return self._analyze_dataframe(df)
            
        except Exception as e:
            logger.error(f"Pasted data analiz hatası: {e}")
            raise Exception(f"Veri analiz edilemedi: {str(e)}")
    
    def _analyze_dataframe(self, df: pd.DataFrame) -> Dict:
        """
        DataFrame'i analiz eder.
        
        Args:
            df: Analiz edilecek DataFrame
            
        Returns:
            Analiz sonuçları
        """
        try:
            # Veriyi temizle ve dönüştür
            df = self._clean_dataframe(df)
            
            # İşlem çiftlerini bul
            trade_pairs = self._find_trade_pairs(df)
            
            # Analiz metriklerini hesapla
            analysis = self._calculate_metrics(df, trade_pairs)
            
            return analysis
            
        except Exception as e:
            logger.error(f"DataFrame analiz hatası: {e}")
            raise Exception(f"Veri analiz edilemedi: {str(e)}")
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        DataFrame'i temizler ve dönüştürür.
        """
        # Sadece gerçekleşen işlemleri al
        df = df[df['Durum'] == 'Gerçekleşti'].copy()
        
        # Tarih sütununu birleştir
        if 'Tarih' in df.columns and 'Zaman' in df.columns:
            df['DateTime'] = pd.to_datetime(df['Tarih'] + ' ' + df['Zaman'], errors='coerce')
        elif 'Tarih' in df.columns:
            df['DateTime'] = pd.to_datetime(df['Tarih'], errors='coerce')
        else:
            raise Exception("Tarih bilgisi bulunamadı")
        
        # Sayısal sütunları dönüştür
        numeric_columns = ['Adet', 'Fiyat', 'Gerçekleşme Fiyatı', 'Yüzde Değişim']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Boş değerleri temizle
        df = df.dropna(subset=['DateTime', 'İşlem', 'Fiyat'])
        
        return df
    
    def _find_trade_pairs(self, df: pd.DataFrame) -> List[Dict]:
        """
        Alış-satış çiftlerini bulur.
        
        Args:
            df: Temizlenmiş DataFrame
            
        Returns:
            İşlem çiftleri listesi
        """
        trade_pairs = []
        
        # Alış ve satış işlemlerini ayır
        buy_trades = df[df['İşlem'] == 'Alış'].copy()
        sell_trades = df[df['İşlem'] == 'Satış'].copy()
        
        # Tarihe göre sırala
        buy_trades = buy_trades.sort_values('DateTime')
        sell_trades = sell_trades.sort_values('DateTime')
        
        # Her alış için sonraki satışı bul
        for _, buy_trade in buy_trades.iterrows():
            # Bu alıştan sonraki ilk satışı bul
            next_sell = sell_trades[sell_trades['DateTime'] > buy_trade['DateTime']]
            
            if not next_sell.empty:
                sell_trade = next_sell.iloc[0]
                
                # İşlem çifti oluştur
                trade_pair = {
                    'buy_date': buy_trade['DateTime'],
                    'sell_date': sell_trade['DateTime'],
                    'buy_price': buy_trade['Fiyat'],
                    'sell_price': sell_trade['Fiyat'],
                    'quantity': buy_trade['Adet'],
                    'duration_hours': (sell_trade['DateTime'] - buy_trade['DateTime']).total_seconds() / 3600,
                    'profit_loss_pct': ((sell_trade['Fiyat'] - buy_trade['Fiyat']) / buy_trade['Fiyat']) * 100,
                    'profit_loss_usd': (sell_trade['Fiyat'] - buy_trade['Fiyat']) * buy_trade['Adet']
                }
                
                trade_pairs.append(trade_pair)
        
        return trade_pairs
    
    def _calculate_metrics(self, df: pd.DataFrame, trade_pairs: List[Dict]) -> Dict:
        """
        Analiz metriklerini hesaplar.
        
        Args:
            df: Temizlenmiş DataFrame
            trade_pairs: İşlem çiftleri
            
        Returns:
            Analiz sonuçları
        """
        if not trade_pairs:
            return {
                'summary': {
                    'totalTrades': 0,
                    'avgTradeDuration': 0,
                    'avgProfitLoss': 0,
                    'winRate': 0
                },
                'durationHistogram': [],
                'profitLossHistogram': [],
                'trades': []
            }
        
        # Temel istatistikler
        durations = [pair['duration_hours'] for pair in trade_pairs]
        profit_losses = [pair['profit_loss_pct'] for pair in trade_pairs]
        
        # Özet istatistikler
        summary = {
            'totalTrades': len(trade_pairs),
            'avgTradeDuration': np.mean(durations),
            'avgProfitLoss': np.mean(profit_losses),
            'winRate': len([p for p in profit_losses if p > 0]) / len(profit_losses) * 100 if profit_losses else 0
        }
        
        # Süre histogramı
        duration_histogram = self._create_duration_histogram(durations)
        
        # Kar/zarar histogramı
        profit_loss_histogram = self._create_profit_loss_histogram(profit_losses)
        
        # İşlem detayları
        trades = []
        for pair in trade_pairs:
            trades.append({
                'side': 'Alış-Satış',
                'date': pair['buy_date'].strftime('%Y-%m-%d %H:%M:%S'),
                'price': pair['buy_price'],
                'quantity': pair['quantity'],
                'duration': pair['duration_hours'],
                'profitLoss': pair['profit_loss_pct']
            })
        
        return {
            'summary': summary,
            'durationHistogram': duration_histogram,
            'profitLossHistogram': profit_loss_histogram,
            'trades': trades
        }
    
    def _create_duration_histogram(self, durations: List[float]) -> List[Dict]:
        """
        Süre histogramı oluşturur.
        """
        if not durations:
            return []
        
        # Süre aralıklarını belirle
        min_duration = min(durations)
        max_duration = max(durations)
        
        # Aralıkları oluştur
        ranges = [
            (0, 1, "0-1 saat"),
            (1, 6, "1-6 saat"),
            (6, 24, "6-24 saat"),
            (24, 72, "1-3 gün"),
            (72, 168, "3-7 gün"),
            (168, 720, "1-4 hafta"),
            (720, float('inf'), "1+ ay")
        ]
        
        histogram = []
        for min_val, max_val, label in ranges:
            count = len([d for d in durations if min_val <= d < max_val])
            if count > 0:
                histogram.append({
                    'range': label,
                    'count': count,
                    'avgDuration': np.mean([d for d in durations if min_val <= d < max_val])
                })
        
        return histogram
    
    def _create_profit_loss_histogram(self, profit_losses: List[float]) -> List[Dict]:
        """
        Kar/zarar histogramı oluşturur.
        """
        if not profit_losses:
            return []
        
        # Kar/zarar aralıklarını belirle
        ranges = [
            (-float('inf'), -10, "-10% ve altı"),
            (-10, -5, "-10% ile -5%"),
            (-5, -2, "-5% ile -2%"),
            (-2, 0, "-2% ile 0%"),
            (0, 2, "0% ile 2%"),
            (2, 5, "2% ile 5%"),
            (5, 10, "5% ile 10%"),
            (10, float('inf'), "10% ve üstü")
        ]
        
        histogram = []
        for min_val, max_val, label in ranges:
            matching_values = [p for p in profit_losses if min_val <= p < max_val]
            count = len(matching_values)
            if count > 0:
                histogram.append({
                    'range': label,
                    'count': count,
                    'avgProfitLoss': np.mean(matching_values)
                })
        
        return histogram


# Global analyzer instance
backtest_analyzer = BacktestAnalyzer()
