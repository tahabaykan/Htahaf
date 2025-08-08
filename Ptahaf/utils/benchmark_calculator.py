"""
BDATA için benchmark hesaplama utility'si
Ticker türüne göre doğru benchmark değerini hesaplar
"""

class BenchmarkCalculator:
    def __init__(self, main_window):
        self.main_window = main_window
        
    def get_benchmark_for_ticker(self, ticker):
        """Ticker için doğru benchmark değerini hesapla"""
        try:
            # ETF verilerini al
            if hasattr(self.main_window, 'market_data') and self.main_window.market_data:
                etf_data = self.main_window.market_data.get_etf_data()
            else:
                print(f"[BENCHMARK CALC] {ticker} - market_data bulunamadı")
                return None
            
            pff_last = etf_data.get('PFF', {}).get('last', None)
            tlt_last = etf_data.get('TLT', {}).get('last', None)
            
            if pff_last is None or tlt_last is None:
                print(f"[BENCHMARK CALC] {ticker} - PFF/TLT verileri eksik: PFF={pff_last}, TLT={tlt_last}")
                return None
            
            # T-pref benchmark hesaplama
            if hasattr(self.main_window, 'historical_tickers') and ticker in self.main_window.historical_tickers:
                if hasattr(self.main_window, 'get_tpref_benchmark'):
                    benchmark = self.main_window.get_tpref_benchmark(ticker, pff_last, tlt_last)
                    print(f"[BENCHMARK CALC] {ticker} T-pref benchmark: {benchmark}")
                    return benchmark
                else:
                    print(f"[BENCHMARK CALC] {ticker} - get_tpref_benchmark fonksiyonu bulunamadı")
                    return None
            
            # C-pref benchmark hesaplama
            elif (hasattr(self.main_window, 'extended_tickers') and ticker in self.main_window.extended_tickers) or \
                 (hasattr(self.main_window, 'c_type_extra_tickers') and ticker in getattr(self.main_window, 'c_type_extra_tickers', set())):
                try:
                    benchmark = float(pff_last) * 1.3 - float(tlt_last) * 0.1
                    print(f"[BENCHMARK CALC] {ticker} C-pref benchmark: {benchmark}")
                    return benchmark
                except Exception as e:
                    print(f"[BENCHMARK CALC] {ticker} C-pref hesaplama hatası: {e}")
                    return None
            
            # Diğer durumlar
            else:
                print(f"[BENCHMARK CALC] {ticker} - bilinmeyen ticker türü")
                return None
                
        except Exception as e:
            print(f"[BENCHMARK CALC] {ticker} genel benchmark hesaplama hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_fill_time_benchmark(self, ticker, fill_time):
        """Fill zamanındaki benchmark değerini hesapla"""
        # TODO: Fill zamanındaki PFF/TLT değerlerini kullanarak benchmark hesapla
        # Şimdilik mevcut benchmark'ı kullan
        return self.get_benchmark_for_ticker(ticker) 
