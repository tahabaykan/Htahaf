"""
Benchmark Service - Benchmark hesaplama servisi
Tkinter uygulamasındaki benchmark hesaplama mantığını web'e aktarır
"""

import pandas as pd

class BenchmarkService:
    """Benchmark hesaplama servisi"""
    
    def __init__(self):
        # Benchmark formülleri (kupon oranlarına göre) - %20 AZALTILMIŞ KATSAYILAR
        self.benchmark_formulas = {
            'DEFAULT': {'PFF': 1.1, 'TLT': -0.08, 'IEF': 0.0, 'IEI': 0.0},
            'C400': {'PFF': 0.36, 'TLT': 0.36, 'IEF': 0.08, 'IEI': 0.0},
            'C425': {'PFF': 0.368, 'TLT': 0.34, 'IEF': 0.092, 'IEI': 0.0},
            'C450': {'PFF': 0.38, 'TLT': 0.32, 'IEF': 0.10, 'IEI': 0.0},
            'C475': {'PFF': 0.40, 'TLT': 0.30, 'IEF': 0.12, 'IEI': 0.0},
            'C500': {'PFF': 0.32, 'TLT': 0.40, 'IEF': 0.08, 'IEI': 0.0},
            'C525': {'PFF': 0.42, 'TLT': 0.28, 'IEF': 0.14, 'IEI': 0.0},
            'C550': {'PFF': 0.408, 'TLT': 0.2, 'IEF': 0.152, 'IEI': 0.04},
            'C575': {'PFF': 0.44, 'TLT': 0.24, 'IEF': 0.16, 'IEI': 0.0},
            'C600': {'PFF': 0.432, 'TLT': 0.12, 'IEF': 0.168, 'IEI': 0.08},
            'C625': {'PFF': 0.448, 'TLT': 0.08, 'IEF': 0.172, 'IEI': 0.1}
        }
        
        self.etf_changes = {}  # ETF değişimleri
        self.benchmark_shift = 0.0  # Benchmark shift değeri
    
    def get_benchmark_type_for_ticker(self, ticker, df):
        """
        Ticker için benchmark tipini belirle (CGRUP'a göre)
        
        Args:
            ticker: Sembol
            df: DataFrame (CSV verisi)
        
        Returns:
            str: Benchmark tipi (C400, C425, vb. veya DEFAULT)
        """
        try:
            if df.empty:
                return 'DEFAULT'
            
            # Ticker'ı DataFrame'de ara
            ticker_row = df[df['PREF IBKR'] == ticker]
            
            if ticker_row.empty:
                return 'DEFAULT'
            
            # CGRUP kolonundan değeri al
            cgrup_str = ticker_row.iloc[0]['CGRUP']
            
            if pd.isna(cgrup_str) or cgrup_str == '':
                return 'DEFAULT'
            
            # CGRUP değerini benchmark key'e çevir
            if str(cgrup_str).lower().startswith('c'):
                benchmark_key = str(cgrup_str).upper()
            else:
                # Eski format: sayısal değer (5.25 -> C525)
                benchmark_key = f"C{int(float(cgrup_str) * 100)}"
            
            if benchmark_key in self.benchmark_formulas:
                return benchmark_key
            else:
                return 'DEFAULT'
                
        except Exception as e:
            return 'DEFAULT'
    
    def calculate_benchmark_change(self, ticker, df, etf_changes, benchmark_shift=0.0):
        """
        Ticker için benchmark değişimini hesapla
        
        Args:
            ticker: Sembol
            df: DataFrame (CSV verisi)
            etf_changes: dict - ETF değişimleri {'PFF': 0.01, 'TLT': -0.02, ...}
            benchmark_shift: float - Benchmark shift değeri
        
        Returns:
            float: Benchmark değişimi
        """
        try:
            if not etf_changes:
                return 0.0
            
            # Ticker'ın benchmark tipini al
            benchmark_type = self.get_benchmark_type_for_ticker(ticker, df)
            formula = self.benchmark_formulas.get(benchmark_type, self.benchmark_formulas['DEFAULT'])
            
            # Benchmark değişimini hesapla
            benchmark_change = 0.0
            for etf, coefficient in formula.items():
                if etf in etf_changes and coefficient != 0:
                    etf_change = round(etf_changes[etf], 4)
                    coefficient_rounded = round(coefficient, 2)
                    contribution = etf_change * coefficient_rounded
                    benchmark_change += contribution
            
            # 4 decimal'e yuvarla
            benchmark_change = round(benchmark_change, 4)
            
            # Benchmark shift değerini uygula
            if benchmark_shift != 0.0:
                benchmark_change = benchmark_change + benchmark_shift
                benchmark_change = round(benchmark_change, 4)
            
            return benchmark_change
            
        except Exception as e:
            return 0.0
    
    def update_etf_changes(self, etf_changes):
        """ETF değişimlerini güncelle"""
        self.etf_changes = etf_changes
    
    def set_benchmark_shift(self, shift):
        """Benchmark shift değerini ayarla"""
        self.benchmark_shift = shift
    
    def update_etf_changes_from_market_data(self, market_data_service):
        """
        ETF değişimlerini market data'dan güncelle (Tkinter'daki update_etf_data_for_benchmark gibi)
        
        Args:
            market_data_service: MarketDataService instance
        """
        try:
            # Benchmark ETF'ler
            benchmark_etfs = ['SPY', 'TLT', 'IEF', 'IEI', 'PFF', 'KRE', 'IWM']
            
            updated_changes = {}
            
            for etf in benchmark_etfs:
                # Market data'dan ETF fiyatını al
                market_data = market_data_service.get_market_data(etf) if market_data_service else None
                
                if market_data:
                    last_price = market_data.get('last', 0)
                    prev_close = market_data.get('prevClose', 0)
                    
                    if last_price > 0 and prev_close > 0:
                        # Değişimi hesapla (dollars cinsinden)
                        change_dollars = round(last_price - prev_close, 4)
                        updated_changes[etf] = change_dollars
                    else:
                        updated_changes[etf] = 0.0
                else:
                    updated_changes[etf] = 0.0
            
            # ETF değişimlerini güncelle
            self.etf_changes = updated_changes
            
            return updated_changes
        except Exception as e:
            print(f"[BenchmarkService] ETF güncelleme hatası: {e}")
            return {}

