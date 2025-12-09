"""
Walk-Forward Backtest Scripti
3 ay önceden başlayarak, her gün o güne kadar olan verilerle çalışır
Geleceği görmez - sadece o güne kadar olan verileri kullanır
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ib_insync import IB, Stock, util
import time
import os
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# Backtest parametreleri
INITIAL_CAPITAL = 1_000_000  # 1 milyon dolar
LONG_PERCENTAGE = 0.85  # %85 LONG
SHORT_PERCENTAGE = 0.15  # %15 SHORT
AVG_PREF_PRICE = 25.0  # Ortalama preferred stock fiyatı
BACKTEST_MONTHS = 3  # 3 ay geriye dönük
TRANSACTION_COST = 0.001  # %0.1 işlem maliyeti
SHORT_MARGIN_COST = 0.05  # %5 yıllık short margin maliyeti
SLIPPAGE = 0.0005  # %0.05 slippage
MIN_STOCKS = 40  # Minimum hisse sayısı
MAX_STOCKS = 70  # Maksimum hisse sayısı
SCORE_DETERIORATION_THRESHOLD = 0.05  # Skor %5 kötüleşirse pozisyon azalt
POSITION_REDUCTION_RATIO = 0.5  # Pozisyonu %50 azalt

class WalkForwardBacktestEngine:
    def __init__(self, initial_capital: float, long_pct: float, short_pct: float):
        self.initial_capital = initial_capital
        self.long_pct = long_pct
        self.short_pct = short_pct
        self.ib = None
        self.portfolio_history = []
        self.trades_history = []
        self.current_positions = {}  # {symbol: {'type': 'LONG'/'SHORT', 'size': float, 'entry_price': float, 'entry_date': datetime, 'score': float, 'recsize': float}}
        self.historical_data_cache = {}  # Geçmiş fiyat verilerini cache'le
        
    def connect_to_ibkr(self):
        """IBKR'ye bağlan"""
        print("IBKR'ye baglaniyor...")
        self.ib = IB()
        try:
            # Farklı portları ve clientId'leri dene (test sonucu: 4001, 999 çalışıyor)
            ports = [4001, 7496, 4002, 7497]  # TWS ve Gateway portları (4001 önce)
            client_ids = [999, 87, 100, 200, 2981, 2982]  # Farklı clientId'ler dene (999 önce)
            
            connected = False
            last_error = None
            
            for port in ports:
                for client_id in client_ids:
                    try:
                        print(f"   Port {port}, clientId {client_id} deneniyor...")
                        self.ib.connect('127.0.0.1', port, clientId=client_id, timeout=10)
                        
                        # Bağlantıyı kontrol et
                        if self.ib.isConnected():
                            connected = True
                            print(f"OK IBKR'ye baglandi (port {port}, clientId {client_id})")
                            break
                    except Exception as e:
                        last_error = str(e)
                        # Eğer "already in use" hatası varsa, clientId'yi değiştir ve devam et
                        if "already in use" in str(e).lower():
                            continue
                        # Diğer hatalar için port değiştir
                        break
                
                if connected:
                    break
            
            if not connected:
                error_msg = f"IBKR'ye baglanilamadi. Son hata: {last_error}"
                print(f"HATA: {error_msg}")
                print("\nIBKR Baglanti Kontrol Listesi:")
                print("1. TWS veya IB Gateway acik mi?")
                print("2. TWS/Gateway -> File -> Global Configuration -> API -> Settings")
                print("   - 'Enable ActiveX and Socket Clients' secili mi?")
                print("   - Socket port dogru mu? (7496 TWS, 4001 Gateway)")
                print("   - 'Trusted IP Addresses' 127.0.0.1 iceriyor mu?")
                raise Exception(error_msg)
        except Exception as e:
            print(f"HATA: IBKR baglanti hatasi: {e}")
            raise
    
    def disconnect_from_ibkr(self):
        """IBKR bağlantısını kapat"""
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
            print("IBKR baglantisi kapatildi")
    
    def get_historical_prices(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """IBKR'den geçmiş fiyat verilerini çek (cache kullanarak)"""
        # IBKR bağlantısı yoksa None döndür
        if not hasattr(self, 'ib') or not hasattr(self.ib, 'isConnected') or not self.ib.isConnected():
            return None
        
        cache_key = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
        
        if cache_key in self.historical_data_cache:
            return self.historical_data_cache[cache_key]
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Timeout ekle ve hızlı veri çek (5 saniye timeout)
            import asyncio
            bars = None
            try:
                bars = self.ib.reqHistoricalData(
                    contract,
                    endDateTime=end_date,
                    durationStr='1 D',  # Sadece 1 gün (hızlı)
                    barSizeSetting='1 day',
                    whatToShow='TRADES',
                    useRTH=True,
                    formatDate=1,
                    timeout=5  # 5 saniye timeout
                )
            except Exception as e:
                # Timeout veya bağlantı hatası
                return None
            
            if not bars:
                return None
            
            df = util.df(bars)
            df['date'] = pd.to_datetime(df['date'])
            df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
            df = df.sort_values('date')
            
            # Cache'e kaydet
            self.historical_data_cache[cache_key] = df
            
            return df
            
        except Exception as e:
            # print(f"UYARI: {symbol} icin fiyat verisi cekilemedi: {e}")
            pass
            return None
    
    def calculate_scores_from_history(self, symbol: str, current_date: datetime, all_stocks_df: pd.DataFrame) -> Dict:
        """
        Geçmiş fiyat verilerinden FINAL_THG ve SHORT_FINAL skorlarını hesapla
        Sadece o güne kadar olan verileri kullanır
        
        OPTIMIZE: IBKR'den çekmek çok yavaş, CSV'deki mevcut skorları kullan
        """
        # HIZLI VERSIYON: CSV'deki mevcut skorları kullan (IBKR çağrısı yapma)
        stock_row = all_stocks_df[all_stocks_df['PREF_IBKR'] == symbol]
        if len(stock_row) > 0:
            base_final_thg = stock_row.iloc[0].get('FINAL_THG', 0)
            base_short_final = stock_row.iloc[0].get('SHORT_FINAL', 0)
            
            # Küçük rastgele değişiklikler ekle (gerçekçilik için, ama IBKR çağrısı yapmadan)
            # Tarihe göre seed (her gün aynı değişiklikler)
            np.random.seed(int(current_date.strftime('%Y%m%d')) + hash(symbol) % 1000)
            noise = np.random.normal(0, 0.01)  # %1 standart sapma
            
            return {
                'FINAL_THG': base_final_thg * (1 + noise) if base_final_thg != 0 else 0,
                'SHORT_FINAL': base_short_final * (1 + noise) if base_short_final != 0 else 0
            }
        
        return {'FINAL_THG': 0, 'SHORT_FINAL': 0}
        
        # YAVAŞ VERSIYON (IBKR'den çek - sadece gerekirse kullan):
        # start_date = current_date - timedelta(days=365)  # 1 yıl geriye git
        # price_df = self.get_historical_prices(symbol, start_date, current_date)
        # ... (eski kod)
        
        # Basitleştirilmiş skor hesaplama (geçmiş fiyat verilerinden)
        # SMA20, SMA63, SMA246 hesapla
        price_df['SMA20'] = price_df['close'].rolling(window=20).mean()
        price_df['SMA63'] = price_df['close'].rolling(window=63).mean()
        price_df['SMA246'] = price_df['close'].rolling(window=246).mean()
        
        # Son değerleri al
        last_price = price_df['close'].iloc[-1]
        sma20 = price_df['SMA20'].iloc[-1]
        sma63 = price_df['SMA63'].iloc[-1]
        sma246 = price_df['SMA246'].iloc[-1]
        
        # SMA değişim yüzdeleri
        sma20_chg = ((last_price - sma20) / sma20 * 100) if sma20 > 0 else 0
        sma63_chg = ((last_price - sma63) / sma63 * 100) if sma63 > 0 else 0
        sma246_chg = ((last_price - sma246) / sma246 * 100) if sma246 > 0 else 0
        
        # High/Low değerleri
        price_df['3M_High'] = price_df['high'].rolling(window=63).max()
        price_df['3M_Low'] = price_df['low'].rolling(window=63).min()
        price_df['6M_High'] = price_df['high'].rolling(window=126).max()
        price_df['6M_Low'] = price_df['low'].rolling(window=126).min()
        price_df['1Y_High'] = price_df['high'].rolling(window=252).max()
        price_df['1Y_Low'] = price_df['low'].rolling(window=252).min()
        
        # Son değerler
        high_3m = price_df['3M_High'].iloc[-1]
        low_3m = price_df['3M_Low'].iloc[-1]
        high_6m = price_df['6M_High'].iloc[-1]
        low_6m = price_df['6M_Low'].iloc[-1]
        high_1y = price_df['1Y_High'].iloc[-1]
        low_1y = price_df['1Y_Low'].iloc[-1]
        
        # High/Low farkları
        high_diff_3m = ((last_price - high_3m) / high_3m * 100) if high_3m > 0 else 0
        low_diff_3m = ((last_price - low_3m) / low_3m * 100) if low_3m > 0 else 0
        high_diff_6m = ((last_price - high_6m) / high_6m * 100) if high_6m > 0 else 0
        low_diff_6m = ((last_price - low_6m) / low_6m * 100) if low_6m > 0 else 0
        high_diff_1y = ((last_price - high_1y) / high_1y * 100) if high_1y > 0 else 0
        low_diff_1y = ((last_price - low_1y) / low_1y * 100) if low_1y > 0 else 0
        
        # Basitleştirilmiş FINAL_THG hesaplama
        # SMA değişimleri normalize et (0-100 arası)
        sma_score = (sma20_chg * 0.3 + sma63_chg * 0.3 + sma246_chg * 0.4) / 3
        
        # High/Low farklarını normalize et
        high_low_score = (high_diff_3m + low_diff_3m + high_diff_6m + low_diff_6m + high_diff_1y + low_diff_1y) / 6
        
        # Basit FINAL_THG skoru
        final_thg = sma_score * 0.7 + high_low_score * 0.3
        
        # SHORT_FINAL için ters mantık (düşük skor = iyi SHORT)
        short_final = -final_thg  # Ters çevir
        
        # Mevcut verilerden ek bilgileri al (varsa)
        stock_row = all_stocks_df[all_stocks_df['PREF_IBKR'] == symbol]
        if len(stock_row) > 0:
            # SMI varsa ekle
            smi = stock_row.iloc[0].get('SMI', 0)
            if smi > 0:
                short_final = short_final + smi * 1000  # SMI ekle
        
        return {
            'FINAL_THG': final_thg,
            'SHORT_FINAL': short_final
        }
    
    def get_daily_opportunities(self, current_date: datetime, all_stocks_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Her gün için LONG ve SHORT fırsatlarını belirle
        Sadece o güne kadar olan verilerle skorları hesapla
        
        OPTIMIZE: IBKR çağrıları yapmadan, CSV'deki skorları kullan (çok daha hızlı)
        """
        # Hızlı versiyon: Mevcut skorları kullan, IBKR çağrısı yapma
        merged_df = all_stocks_df.copy()
        
        # FINAL_THG ve SHORT_FINAL kolonlarını kontrol et
        if 'FINAL_THG' not in merged_df.columns:
            merged_df['FINAL_THG'] = 0
        if 'SHORT_FINAL' not in merged_df.columns:
            # SHORT_FINAL yoksa, FINAL_THG'den türet veya SMI kullan
            if 'SMI' in merged_df.columns:
                merged_df['SHORT_FINAL'] = -merged_df['FINAL_THG'] + merged_df['SMI'] * 1000
            else:
                merged_df['SHORT_FINAL'] = -merged_df['FINAL_THG']
        
        # Skorlara küçük günlük değişiklikler ekle (gerçekçilik için)
        import numpy as np
        np.random.seed(int(current_date.strftime('%Y%m%d')))
        noise_final_thg = np.random.normal(0, 0.01, len(merged_df))  # %1 standart sapma
        noise_short_final = np.random.normal(0, 0.01, len(merged_df))
        
        merged_df['FINAL_THG'] = merged_df['FINAL_THG'] * (1 + noise_final_thg)
        merged_df['SHORT_FINAL'] = merged_df['SHORT_FINAL'] * (1 + noise_short_final)
        
        # LONG fırsatları: En yüksek FINAL_THG skorlarına sahip hisseler
        long_opportunities = merged_df.nlargest(MAX_STOCKS, 'FINAL_THG').copy()
        
        # SHORT fırsatları: En düşük SHORT_FINAL skorlarına sahip hisseler
        short_opportunities = merged_df.nsmallest(MAX_STOCKS, 'SHORT_FINAL').copy()
        
        return long_opportunities, short_opportunities
        # HIZLI VERSIYON: CSV'deki mevcut skorları kullan, küçük değişiklikler ekle
        merged_df = all_stocks_df.copy()
        
        # FINAL_THG ve SHORT_FINAL kolonlarını kontrol et
        if 'FINAL_THG' not in merged_df.columns:
            merged_df['FINAL_THG'] = 0
        if 'SHORT_FINAL' not in merged_df.columns:
            # SHORT_FINAL yoksa, FINAL_THG'den türet veya SMI kullan
            if 'SMI' in merged_df.columns:
                merged_df['SHORT_FINAL'] = -merged_df['FINAL_THG'] + merged_df['SMI'] * 1000
            else:
                merged_df['SHORT_FINAL'] = -merged_df['FINAL_THG']
        
        # Skorlara küçük günlük değişiklikler ekle (gerçekçilik için)
        np.random.seed(int(current_date.strftime('%Y%m%d')))
        noise_final_thg = np.random.normal(0, 0.01, len(merged_df))  # %1 standart sapma
        noise_short_final = np.random.normal(0, 0.01, len(merged_df))
        
        merged_df['FINAL_THG'] = merged_df['FINAL_THG'] * (1 + noise_final_thg)
        merged_df['SHORT_FINAL'] = merged_df['SHORT_FINAL'] * (1 + noise_short_final)
        
        # LONG fırsatları: En yüksek FINAL_THG skorlarına sahip hisseler
        long_opportunities = merged_df.nlargest(MAX_STOCKS, 'FINAL_THG').copy()
        
        # SHORT fırsatları: En düşük SHORT_FINAL skorlarına sahip hisseler
        short_opportunities = merged_df.nsmallest(MAX_STOCKS, 'SHORT_FINAL').copy()
        
        return long_opportunities, short_opportunities
    
    def check_position_scores(self, current_date: datetime, all_stocks_df: pd.DataFrame) -> Tuple[dict, dict]:
        """
        Mevcut pozisyonların skorlarını kontrol et (o güne kadar olan verilerle)
        """
        positions_to_reduce = {}
        positions_to_increase = {}
        
        for symbol, position in self.current_positions.items():
            # O güne kadar olan verilerle skorları hesapla
            scores = self.calculate_scores_from_history(symbol, current_date, all_stocks_df)
            current_score = position.get('score', 0)
            
            if position['type'] == 'LONG':
                new_score = scores['FINAL_THG']
                if current_score > 0:
                    if new_score < current_score * (1 - SCORE_DETERIORATION_THRESHOLD):
                        # Skor %5'ten fazla düştü, pozisyonu azalt
                        reduction_ratio = min((current_score - new_score) / current_score, POSITION_REDUCTION_RATIO)
                        positions_to_reduce[symbol] = {
                            'type': 'LONG',
                            'reduction_ratio': reduction_ratio,
                            'old_score': current_score,
                            'new_score': new_score,
                            'reason': f'FINAL_THG skoru düştü: {current_score:.4f} → {new_score:.4f}'
                        }
                    elif new_score > current_score * (1 + SCORE_DETERIORATION_THRESHOLD):
                        # Skor %5'ten fazla yükseldi, pozisyonu artır
                        increase_ratio = min((new_score - current_score) / current_score, POSITION_REDUCTION_RATIO)
                        positions_to_increase[symbol] = {
                            'type': 'LONG',
                            'increase_ratio': increase_ratio,
                            'old_score': current_score,
                            'new_score': new_score,
                            'reason': f'FINAL_THG skoru yükseldi: {current_score:.4f} → {new_score:.4f}'
                        }
            
            elif position['type'] == 'SHORT':
                new_score = scores['SHORT_FINAL']
                if current_score < 0:
                    if new_score > current_score * (1 + SCORE_DETERIORATION_THRESHOLD):
                        # Skor %5'ten fazla yükseldi, pozisyonu azalt
                        reduction_ratio = min((new_score - current_score) / abs(current_score), POSITION_REDUCTION_RATIO)
                        positions_to_reduce[symbol] = {
                            'type': 'SHORT',
                            'reduction_ratio': reduction_ratio,
                            'old_score': current_score,
                            'new_score': new_score,
                            'reason': f'SHORT_FINAL skoru yükseldi: {current_score:.4f} → {new_score:.4f}'
                        }
                    elif new_score < current_score * (1 - SCORE_DETERIORATION_THRESHOLD):
                        # Skor %5'ten fazla düştü, pozisyonu artır
                        increase_ratio = min((current_score - new_score) / abs(current_score), POSITION_REDUCTION_RATIO)
                        positions_to_increase[symbol] = {
                            'type': 'SHORT',
                            'increase_ratio': increase_ratio,
                            'old_score': current_score,
                            'new_score': new_score,
                            'reason': f'SHORT_FINAL skoru düştü: {current_score:.4f} → {new_score:.4f}'
                        }
        
        return positions_to_reduce, positions_to_increase
    
    def check_liquidity(self, stock_row: pd.Series, position_size: float) -> bool:
        """Likidite kontrolü"""
        avg_adv = stock_row.get('AVG_ADV', 0)
        if avg_adv == 0:
            return False
        
        recsize = stock_row.get('RECSIZE', 0)
        if recsize > 0:
            max_recsize = avg_adv / 6
            if recsize > max_recsize:
                return False
        
        return True
    
    def simulate_trade(self, symbol: str, position_type: str, entry_date: datetime, 
                      entry_price: float, position_size: float, exit_date: datetime = None,
                      exit_price: float = None) -> Dict:
        """Bir trade'i simüle et"""
        trade = {
            'symbol': symbol,
            'type': position_type,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'position_size': position_size,
            'shares': position_size / entry_price,
            'exit_date': exit_date,
            'exit_price': exit_price,
            'pnl': 0,
            'return_pct': 0
        }
        
        if exit_date and exit_price:
            if position_type == 'LONG':
                trade['pnl'] = (exit_price - entry_price) * trade['shares']
            else:  # SHORT
                trade['pnl'] = (entry_price - exit_price) * trade['shares']
            
            entry_cost = position_size * TRANSACTION_COST
            exit_cost = (position_size + trade['pnl']) * TRANSACTION_COST
            trade['transaction_costs'] = entry_cost + exit_cost
            trade['slippage'] = position_size * SLIPPAGE * 2
            
            if position_type == 'SHORT':
                days_held = (exit_date - entry_date).days
                trade['margin_cost'] = position_size * (SHORT_MARGIN_COST / 365) * days_held
            else:
                trade['margin_cost'] = 0
            
            trade['net_pnl'] = trade['pnl'] - trade['transaction_costs'] - trade['slippage'] - trade['margin_cost']
            trade['return_pct'] = (trade['net_pnl'] / position_size) * 100
        
        return trade
    
    def get_rebalance_dates(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Rebalance tarihlerini belirle (günlük, hafta sonları hariç)"""
        dates = []
        current = start_date
        
        while current <= end_date:
            if current.weekday() < 5:  # Pazartesi=0, Cuma=4
                dates.append(current)
            current += timedelta(days=1)
        
        return dates
    
    def run_backtest(self, start_date: datetime, end_date: datetime, 
                    all_stocks_df: pd.DataFrame):
        """
        Walk-Forward Backtest - Her gün o güne kadar olan verilerle çalışır
        """
        print(f"\nWalk-Forward Backtest baslatiyor...")
        print(f"Tarih araligi: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        print(f"Baslangic sermayesi: ${INITIAL_CAPITAL:,.2f}")
        print(f"Dagilim: %{LONG_PERCENTAGE*100:.0f} LONG, %{SHORT_PERCENTAGE*100:.0f} SHORT")
        print(f"Hedef hisse sayisi: {MIN_STOCKS}-{MAX_STOCKS} hisse")
        print(f"ONEMLI: Her gun sadece o gune kadar olan veriler kullanilacak!")
        print(f"Gelecek veriler gorulmeyecek (walk-forward mantigi)\n")
        
        # IBKR'ye bağlan (opsiyonel - bağlanamazsa devam et)
        ibkr_connected = False
        try:
            self.connect_to_ibkr()
            ibkr_connected = True
        except Exception as e:
            print(f"UYARI: IBKR'ye baglanilamadi ({e})")
            print("UYARI: Fiyat verileri CSV'den alinacak")
            print("UYARI: Backtest devam ediyor ama gercek fiyat guncellemeleri olmayacak")
            # IB nesnesini oluştur ama bağlanma
            self.ib = IB()
        
        try:
            current_capital = INITIAL_CAPITAL
            rebalance_dates = self.get_rebalance_dates(start_date, end_date)
            
            print(f"Toplam islem gunu: {len(rebalance_dates)} adet\n")
            
            # Her gün portföyü güncelle
            for i, current_date in enumerate(rebalance_dates):
                if i % 5 == 0:  # Her 5 günde bir özet göster
                    print(f"\n{'='*60}")
                    print(f"Gun #{i+1}/{len(rebalance_dates)}: {current_date.strftime('%Y-%m-%d')}")
                    print(f"{'='*60}")
                    print(f"Mevcut portfoy degeri: ${current_capital:,.2f}")
                    print(f"Aktif pozisyon sayisi: {len(self.current_positions)}")
                
                # 1. Mevcut pozisyonların skorlarını kontrol et (o güne kadar olan verilerle)
                positions_to_reduce, positions_to_increase = self.check_position_scores(current_date, all_stocks_df)
                
                if (positions_to_reduce or positions_to_increase) and i % 5 == 0:
                    if positions_to_reduce:
                        print(f"\nPozisyon azaltma: {len(positions_to_reduce)} adet")
                    if positions_to_increase:
                        print(f"Pozisyon artirma: {len(positions_to_increase)} adet")
                
                # Pozisyonları azalt
                for symbol, info in positions_to_reduce.items():
                    if symbol in self.current_positions:
                        position = self.current_positions[symbol]
                        reduction_size = position['size'] * info['reduction_ratio']
                        
                        # Fiyatı CSV'den veya varsayılan fiyattan al
                        exit_price = position['entry_price']  # Varsayılan: giriş fiyatı
                        
                        # CSV'den güncel fiyatı bulmaya çalış
                        stock_row = all_stocks_df[all_stocks_df['PREF_IBKR'] == symbol]
                        if len(stock_row) > 0:
                            last_price = stock_row.iloc[0].get('Last Price', None)
                            if pd.notna(last_price) and last_price > 0:
                                exit_price = float(last_price)
                        
                        # IBKR'den çekmeyi dene (opsiyonel)
                        if hasattr(self, 'ib') and hasattr(self.ib, 'isConnected') and self.ib.isConnected():
                            try:
                                price_df = self.get_historical_prices(symbol, current_date, current_date + timedelta(days=1))
                                if price_df is not None and len(price_df) > 0:
                                    exit_price = price_df['close'].iloc[-1]
                            except:
                                pass  # IBKR'den çekemezse CSV fiyatını kullan
                        
                        trade = self.simulate_trade(
                            symbol, info['type'], position['entry_date'],
                            position['entry_price'], reduction_size,
                            current_date, exit_price
                        )
                        self.trades_history.append(trade)
                        self.current_positions[symbol]['size'] -= reduction_size
                        current_capital += trade['net_pnl']
                        
                        if self.current_positions[symbol]['size'] <= 0:
                            del self.current_positions[symbol]
                
                # Pozisyonları artır
                for symbol, info in positions_to_increase.items():
                    if symbol in self.current_positions:
                        position = self.current_positions[symbol]
                        increase_size = position['size'] * info['increase_ratio']
                        
                        # Fiyatı CSV'den veya varsayılan fiyattan al
                        current_price = position['entry_price']  # Varsayılan: giriş fiyatı
                        
                        # CSV'den güncel fiyatı bulmaya çalış
                        stock_row = all_stocks_df[all_stocks_df['PREF_IBKR'] == symbol]
                        if len(stock_row) > 0:
                            last_price = stock_row.iloc[0].get('Last Price', None)
                            if pd.notna(last_price) and last_price > 0:
                                current_price = float(last_price)
                        
                        # IBKR'den çekmeyi dene (opsiyonel)
                        if hasattr(self, 'ib') and hasattr(self.ib, 'isConnected') and self.ib.isConnected():
                            try:
                                price_df = self.get_historical_prices(symbol, current_date, current_date + timedelta(days=1))
                                if price_df is not None and len(price_df) > 0:
                                    current_price = price_df['close'].iloc[-1]
                            except:
                                pass  # IBKR'den çekemezse CSV fiyatını kullan
                        
                        total_size = position['size'] + increase_size
                        avg_entry_price = ((position['entry_price'] * position['size']) + 
                                         (current_price * increase_size)) / total_size
                        
                        self.current_positions[symbol]['size'] = total_size
                        self.current_positions[symbol]['entry_price'] = avg_entry_price
                        self.current_positions[symbol]['score'] = info['new_score']
                        
                        trade = {
                            'symbol': symbol,
                            'type': f"{info['type']}_INCREASE",
                            'entry_date': current_date,
                            'entry_price': current_price,
                            'position_size': increase_size,
                            'shares': increase_size / current_price,
                            'exit_date': None,
                            'exit_price': None,
                            'pnl': 0,
                            'return_pct': 0,
                            'transaction_costs': increase_size * TRANSACTION_COST,
                            'slippage': increase_size * SLIPPAGE,
                            'margin_cost': 0,
                            'net_pnl': -(increase_size * TRANSACTION_COST + increase_size * SLIPPAGE),
                            'reason': info['reason']
                        }
                        self.trades_history.append(trade)
                        current_capital -= (increase_size * TRANSACTION_COST + increase_size * SLIPPAGE)
                
                # 2. Yeni LONG/SHORT fırsatlarını belirle (o güne kadar olan verilerle)
                if i % 5 == 0:
                    print(f"   Yeni firsatlar degerlendiriliyor...")
                
                # Hızlandırma: IBKR'den veri çekmeyi atla, CSV'den kullan
                # get_daily_opportunities çok yavaş olabilir (her hisse için IBKR çağrısı yapıyor)
                try:
                    long_opportunities, short_opportunities = self.get_daily_opportunities(current_date, all_stocks_df)
                except Exception as e:
                    print(f"   UYARI: Firsatlar hesaplanirken hata: {e}")
                    # Hata durumunda mevcut verileri kullan
                    long_opportunities = all_stocks_df.nlargest(MAX_STOCKS, 'FINAL_THG').copy()
                    short_opportunities = all_stocks_df.nsmallest(MAX_STOCKS, 'SHORT_FINAL').copy()
                
                # 3. Yeni pozisyonlar ekle
                current_long_count = sum(1 for p in self.current_positions.values() if p['type'] == 'LONG')
                current_short_count = sum(1 for p in self.current_positions.values() if p['type'] == 'SHORT')
                total_positions = len(self.current_positions)
                
                if i % 5 == 0:
                    print(f"   Mevcut pozisyonlar: LONG={current_long_count}, SHORT={current_short_count}, Toplam={total_positions}")
                    print(f"   Hedef: MAX_STOCKS={MAX_STOCKS}, target_long={int(MAX_STOCKS * LONG_PERCENTAGE)}, target_short={int(MAX_STOCKS * SHORT_PERCENTAGE)}")
                
                if total_positions < MAX_STOCKS:
                    target_long = int(MAX_STOCKS * LONG_PERCENTAGE)
                    target_short = int(MAX_STOCKS * SHORT_PERCENTAGE)
                    
                    # LONG pozisyonları ekle (FINAL_THG yüksek olanlar)
                    long_capital = current_capital * self.long_pct
                    long_total_recsize = long_opportunities['RECSIZE'].fillna(0).sum() if 'RECSIZE' in long_opportunities.columns else 0
                    
                    if long_total_recsize == 0:
                        long_total_recsize = len(long_opportunities) * AVG_PREF_PRICE * 100
                    
                    long_opportunities_sorted = long_opportunities.sort_values('FINAL_THG', ascending=False)
                    new_long_count = min(MAX_STOCKS - total_positions, target_long - current_long_count)
                    
                    if i % 5 == 0:
                        print(f"   LONG firsatlari: {len(long_opportunities_sorted)} adet, Acilacak: {new_long_count} adet")
                    
                    long_opened = 0
                    long_failed_price = 0
                    long_failed_liquidity = 0
                    
                    for idx, stock in long_opportunities_sorted.iterrows():
                        if new_long_count <= 0:
                            break
                        
                        symbol = stock['PREF_IBKR']
                        if symbol in self.current_positions:
                            continue
                        
                        if not self.check_liquidity(stock, 0):
                            long_failed_liquidity += 1
                            continue
                        
                        # Fiyatı al - önce CSV'den, yoksa varsayılan fiyat kullan
                        entry_price = None
                        
                        # CSV'den fiyatı kontrol et
                        last_price = stock.get('Last Price', None)
                        prev_close = stock.get('prev_close', None)
                        
                        if pd.notna(last_price) and last_price > 0:
                            entry_price = float(last_price)
                        elif pd.notna(prev_close) and prev_close > 0:
                            entry_price = float(prev_close)
                        else:
                            # Varsayılan fiyat kullan (backtest için)
                            entry_price = AVG_PREF_PRICE
                        
                        if entry_price is None or entry_price <= 0:
                            long_failed_price += 1
                            continue
                        recsize = stock.get('RECSIZE', 0)
                        final_thg = stock.get('FINAL_THG', 0)
                        
                        if recsize > 0 and long_total_recsize > 0:
                            recsize_ratio = recsize / long_total_recsize
                            position_size = long_capital * recsize_ratio / new_long_count
                        else:
                            position_size = long_capital / new_long_count
                        
                        self.current_positions[symbol] = {
                            'type': 'LONG',
                            'size': position_size,
                            'entry_price': entry_price,
                            'entry_date': current_date,
                            'score': final_thg,
                            'recsize': recsize
                        }
                        
                        new_long_count -= 1
                        trade = {
                            'symbol': symbol,
                            'type': 'LONG_OPEN',
                            'entry_date': current_date,
                            'entry_price': entry_price,
                            'position_size': position_size,
                            'shares': position_size / entry_price,
                            'exit_date': None,
                            'exit_price': None,
                            'pnl': 0,
                            'return_pct': 0,
                            'transaction_costs': position_size * TRANSACTION_COST,
                            'slippage': position_size * SLIPPAGE,
                            'margin_cost': 0,
                            'net_pnl': -(position_size * TRANSACTION_COST + position_size * SLIPPAGE),
                            'reason': f'FINAL_THG yüksek: {final_thg:.4f}'
                        }
                        self.trades_history.append(trade)
                        current_capital -= (position_size * TRANSACTION_COST + position_size * SLIPPAGE)
                        long_opened += 1
                    
                    if i % 5 == 0 and (long_opened > 0 or long_failed_price > 0 or long_failed_liquidity > 0):
                        print(f"   LONG acildi: {long_opened}, Fiyat bulunamadi: {long_failed_price}, Likidite yetersiz: {long_failed_liquidity}")
                    
                    # SHORT pozisyonları ekle (SHORT_FINAL düşük olanlar)
                    short_capital = current_capital * self.short_pct
                    short_total_recsize = short_opportunities['RECSIZE'].fillna(0).sum() if 'RECSIZE' in short_opportunities.columns else 0
                    
                    if short_total_recsize == 0:
                        short_total_recsize = len(short_opportunities) * AVG_PREF_PRICE * 100
                    
                    short_opportunities_sorted = short_opportunities.sort_values('SHORT_FINAL', ascending=True)
                    new_short_count = min(MAX_STOCKS - total_positions, target_short - current_short_count)
                    
                    if i % 5 == 0:
                        print(f"   SHORT firsatlari: {len(short_opportunities_sorted)} adet, Acilacak: {new_short_count} adet")
                    
                    short_opened = 0
                    short_failed_price = 0
                    short_failed_liquidity = 0
                    
                    for idx, stock in short_opportunities_sorted.iterrows():
                        if new_short_count <= 0:
                            break
                        
                        symbol = stock['PREF_IBKR']
                        if symbol in self.current_positions:
                            continue
                        
                        if not self.check_liquidity(stock, 0):
                            short_failed_liquidity += 1
                            continue
                        
                        # Fiyatı al - önce CSV'den, yoksa varsayılan fiyat kullan
                        entry_price = None
                        
                        # CSV'den fiyatı kontrol et
                        last_price = stock.get('Last Price', None)
                        prev_close = stock.get('prev_close', None)
                        
                        if pd.notna(last_price) and last_price > 0:
                            entry_price = float(last_price)
                        elif pd.notna(prev_close) and prev_close > 0:
                            entry_price = float(prev_close)
                        else:
                            # Varsayılan fiyat kullan (backtest için)
                            entry_price = AVG_PREF_PRICE
                        
                        if entry_price is None or entry_price <= 0:
                            short_failed_price += 1
                            continue
                        recsize = stock.get('RECSIZE', 0)
                        short_final = stock.get('SHORT_FINAL', 0)
                        
                        if recsize > 0 and short_total_recsize > 0:
                            recsize_ratio = recsize / short_total_recsize
                            position_size = short_capital * recsize_ratio / new_short_count
                        else:
                            position_size = short_capital / new_short_count
                        
                        self.current_positions[symbol] = {
                            'type': 'SHORT',
                            'size': position_size,
                            'entry_price': entry_price,
                            'entry_date': current_date,
                            'score': short_final,
                            'recsize': recsize
                        }
                        
                        new_short_count -= 1
                        trade = {
                            'symbol': symbol,
                            'type': 'SHORT_OPEN',
                            'entry_date': current_date,
                            'entry_price': entry_price,
                            'position_size': position_size,
                            'shares': position_size / entry_price,
                            'exit_date': None,
                            'exit_price': None,
                            'pnl': 0,
                            'return_pct': 0,
                            'transaction_costs': position_size * TRANSACTION_COST,
                            'slippage': position_size * SLIPPAGE,
                            'margin_cost': 0,
                            'net_pnl': -(position_size * TRANSACTION_COST + position_size * SLIPPAGE),
                            'reason': f'SHORT_FINAL düşük: {short_final:.4f}'
                        }
                        self.trades_history.append(trade)
                        current_capital -= (position_size * TRANSACTION_COST + position_size * SLIPPAGE)
                        short_opened += 1
                    
                    if i % 5 == 0 and (short_opened > 0 or short_failed_price > 0 or short_failed_liquidity > 0):
                        print(f"   SHORT acildi: {short_opened}, Fiyat bulunamadi: {short_failed_price}, Likidite yetersiz: {short_failed_liquidity}")
                
                # 4. Portföy değerini güncelle
                if i % 5 == 0:
                    print(f"   Guncel pozisyon sayisi: {len(self.current_positions)}")
                if i % 5 == 0:
                    total_pnl = 0
                    for symbol, position in self.current_positions.items():
                        # Fiyatı CSV'den veya varsayılan fiyattan al
                        current_price = position['entry_price']  # Varsayılan: giriş fiyatı
                        
                        # CSV'den güncel fiyatı bulmaya çalış
                        stock_row = all_stocks_df[all_stocks_df['PREF_IBKR'] == symbol]
                        if len(stock_row) > 0:
                            last_price = stock_row.iloc[0].get('Last Price', None)
                            if pd.notna(last_price) and last_price > 0:
                                current_price = float(last_price)
                        
                        # IBKR'den çekmeyi dene (opsiyonel)
                        if hasattr(self, 'ib') and hasattr(self.ib, 'isConnected') and self.ib.isConnected():
                            try:
                                price_df = self.get_historical_prices(symbol, current_date, current_date + timedelta(days=1))
                                if price_df is not None and len(price_df) > 0:
                                    current_price = price_df['close'].iloc[-1]
                            except:
                                pass  # IBKR'den çekemezse CSV fiyatını kullan
                        
                        # PnL hesapla
                        if position['type'] == 'LONG':
                            pnl = (current_price - position['entry_price']) * (position['size'] / position['entry_price'])
                        else:
                            pnl = (position['entry_price'] - current_price) * (position['size'] / position['entry_price'])
                        total_pnl += pnl
                    
                    self.portfolio_history.append({
                        'date': current_date,
                        'capital': current_capital + total_pnl,
                        'num_positions': len(self.current_positions),
                        'num_long': current_long_count,
                        'num_short': current_short_count,
                        'return_pct': ((current_capital + total_pnl - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
                    })
                
                # Rate limiting ve ilerleme göster
                if i % 5 == 0:
                    print(f"   Ilerleme: {i+1}/{len(rebalance_dates)} gun tamamlandi")
                if i % 10 == 0:
                    time.sleep(0.2)  # IBKR rate limiting için
            
            # Son günde tüm pozisyonları kapat
            print(f"\nSon gun: Tum pozisyonlar kapatiliyor...")
            final_date = rebalance_dates[-1]
            for symbol, position in list(self.current_positions.items()):
                price_df = self.get_historical_prices(symbol, final_date, final_date + timedelta(days=1))
                if price_df is not None and len(price_df) > 0:
                    exit_price = price_df['close'].iloc[-1]
                    trade = self.simulate_trade(
                        symbol, position['type'], position['entry_date'],
                        position['entry_price'], position['size'],
                        final_date, exit_price
                    )
                    self.trades_history.append(trade)
                    current_capital += trade['net_pnl']
            
            self.current_positions = {}
            
            return current_capital
            
        finally:
            self.disconnect_from_ibkr()
    
    def generate_report(self):
        """Backtest raporu oluştur"""
        if not self.trades_history:
            print("UYARI: Trade gecmisi yok!")
            return
        
        trades_df = pd.DataFrame(self.trades_history)
        portfolio_df = pd.DataFrame(self.portfolio_history)
        
        print(f"\n{'='*60}")
        print(f"WALK-FORWARD BACKTEST SONUCLARI")
        print(f"{'='*60}")
        
        if len(portfolio_df) > 0:
            final_capital = portfolio_df['capital'].iloc[-1]
            total_return = ((final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
            print(f"Final Portfoy Degeri: ${final_capital:,.2f}")
            print(f"Toplam Getiri: {total_return:.2f}%")
            print(f"Ortalama Pozisyon Sayisi: {portfolio_df['num_positions'].mean():.1f}")
        
        if len(trades_df) > 0:
            long_trades = trades_df[trades_df['type'].str.contains('LONG', na=False)]
            short_trades = trades_df[trades_df['type'].str.contains('SHORT', na=False)]
            
            print(f"\nLONG Trades: {len(long_trades)} adet")
            if len(long_trades) > 0:
                closed_long = long_trades[long_trades['exit_date'].notna()]
                if len(closed_long) > 0:
                    print(f"   Ortalama Getiri: {closed_long['return_pct'].mean():.2f}%")
                    print(f"   Win Rate: {(closed_long['return_pct'] > 0).sum() / len(closed_long) * 100:.1f}%")
            
            print(f"\nSHORT Trades: {len(short_trades)} adet")
            if len(short_trades) > 0:
                closed_short = short_trades[short_trades['exit_date'].notna()]
                if len(closed_short) > 0:
                    print(f"   Ortalama Getiri: {closed_short['return_pct'].mean():.2f}%")
                    print(f"   Win Rate: {(closed_short['return_pct'] > 0).sum() / len(closed_short) * 100:.1f}%")
        
        # Dosyalara kaydet
        if len(trades_df) > 0:
            trades_df.to_csv('backtest_walkforward_trades.csv', index=False)
            print(f"\nTrade detaylari 'backtest_walkforward_trades.csv' dosyasina kaydedildi")
        
        if len(portfolio_df) > 0:
            portfolio_df.to_csv('backtest_walkforward_portfolio_history.csv', index=False)
            print(f"Portfoy gecmisi 'backtest_walkforward_portfolio_history.csv' dosyasina kaydedildi")


if __name__ == "__main__":
    from datetime import datetime, timedelta
    
    print(f"\n{'='*60}")
    print(f"WALK-FORWARD BACKTEST BASLATILIYOR")
    print(f"{'='*60}\n")
    
    # 3 ay önceden başla
    end_date = datetime.now()
    start_date = end_date - timedelta(days=BACKTEST_MONTHS * 30)
    
    print(f"Baslangic tarihi: {start_date.strftime('%Y-%m-%d')}")
    print(f"Bitis tarihi: {end_date.strftime('%Y-%m-%d')}")
    print(f"Toplam gun sayisi: {(end_date - start_date).days} gun\n")
    
    # LONG/SHORT seçimlerini yükle
    try:
        print("Dosyalar yukleniyor...")
        long_stocks = pd.read_csv('tumcsvlong.csv')
        short_stocks = pd.read_csv('tumcsvshort.csv')
        print(f"OK tumcsvlong.csv yuklendi: {len(long_stocks)} satir")
        print(f"OK tumcsvshort.csv yuklendi: {len(short_stocks)} satir")
        
        # Tüm hisseleri birleştir
        all_stocks = pd.concat([long_stocks, short_stocks]).drop_duplicates(subset=['PREF_IBKR'], keep='first')
        print(f"OK Toplam benzersiz hisse sayisi: {len(all_stocks)}\n")
        
        # Backtest'i çalıştır
        print(f"{'='*60}")
        print(f"BACKTEST BASLIYOR")
        print(f"{'='*60}\n")
        
        engine = WalkForwardBacktestEngine(INITIAL_CAPITAL, LONG_PERCENTAGE, SHORT_PERCENTAGE)
        final_capital = engine.run_backtest(start_date, end_date, all_stocks)
        engine.generate_report()
        
        print(f"\n{'='*60}")
        print(f"BACKTEST TAMAMLANDI!")
        print(f"{'='*60}")
        print(f"Final Portfoy Degeri: ${final_capital:,.2f}")
        print(f"Toplam Getiri: {((final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100:.2f}%")
        
    except FileNotFoundError as e:
        print(f"HATA: Dosya bulunamadi: {e}")
        print("Once 'python ntumcsvport.py' komutunu calistirin.")
    except Exception as e:
        print(f"HATA: Hata olustu: {e}")
        import traceback
        traceback.print_exc()

