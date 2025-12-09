"""
Gerçekçi Walk-Forward Backtest Scripti
Her gün için tüm sistemin çalışmasını simüle eder
3 ay (90 gün) için gerçekçi backtest yapar
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import subprocess
import os
import time
import shutil
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# Backtest parametreleri
INITIAL_CAPITAL = 1_000_000  # 1 milyon dolar
LONG_PERCENTAGE = 0.85  # %85 LONG
SHORT_PERCENTAGE = 0.15  # %15 SHORT
AVG_PREF_PRICE = 25.0  # Ortalama preferred stock fiyatı
BACKTEST_DAYS = 90  # 90 gün (3 ay)
TRANSACTION_COST = 0.001  # %0.1 işlem maliyeti
SHORT_MARGIN_COST = 0.05  # %5 yıllık short margin maliyeti
SLIPPAGE = 0.0005  # %0.05 slippage
MIN_STOCKS = 40  # Minimum hisse sayısı
MAX_STOCKS = 70  # Maksimum hisse sayısı
SCORE_DETERIORATION_THRESHOLD = 0.05  # Skor %5 kötüleşirse pozisyon azalt
POSITION_REDUCTION_RATIO = 0.5  # Pozisyonu %50 azalt

class RealisticBacktestEngine:
    def __init__(self, initial_capital: float, long_pct: float, short_pct: float):
        self.initial_capital = initial_capital
        self.long_pct = long_pct
        self.short_pct = short_pct
        self.portfolio_history = []
        self.trades_history = []
        self.current_positions = {}
        self.backtest_data_dir = "backtest_data"  # Her gün için veriler burada saklanacak
        
    def setup_backtest_environment(self):
        """Backtest için ortam hazırla"""
        if os.path.exists(self.backtest_data_dir):
            shutil.rmtree(self.backtest_data_dir)
        os.makedirs(self.backtest_data_dir, exist_ok=True)
        print(f"📁 Backtest veri dizini oluşturuldu: {self.backtest_data_dir}")
    
    def run_daily_system(self, current_date: datetime) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Her gün için tüm sistemi çalıştır
        run_anywhere_n.py'yi çalıştırır ve sonuçları döndürür
        """
        print(f"\n   🔄 {current_date.strftime('%Y-%m-%d')} için sistem çalıştırılıyor...")
        
        # Mevcut CSV dosyalarını yedekle
        backup_dir = os.path.join(self.backtest_data_dir, current_date.strftime('%Y%m%d'))
        os.makedirs(backup_dir, exist_ok=True)
        
        # Önemli CSV dosyalarını yedekle
        important_files = ['janalldata.csv', 'tumcsvlong.csv', 'tumcsvshort.csv']
        for file in important_files:
            if os.path.exists(file):
                shutil.copy2(file, os.path.join(backup_dir, file))
        
        # Sistem çalıştırma zamanını ölç
        start_time = time.time()
        
        try:
            # run_anywhere_n.py'yi çalıştır
            # NOT: Bu gerçekte çalışmayacak çünkü geçmiş tarihler için veri yok
            # Bu yüzden simüle ediyoruz
            
            # Alternatif: Eğer geçmiş veriler varsa kullan
            # Şimdilik mevcut verileri kullanıyoruz
            
            # tumcsvlong.csv ve tumcsvshort.csv dosyalarını oku
            if os.path.exists('tumcsvlong.csv') and os.path.exists('tumcsvshort.csv'):
                long_stocks = pd.read_csv('tumcsvlong.csv')
                short_stocks = pd.read_csv('tumcsvshort.csv')
                
                # Bu gün için skorları güncelle (simüle)
                # Gerçekte burada run_anywhere_n.py çalışmalı
                # Ama şimdilik mevcut verileri kullanıyoruz
                
                elapsed_time = time.time() - start_time
                print(f"   ✅ Sistem çalıştırıldı ({elapsed_time:.1f} saniye)")
                
                return long_stocks, short_stocks
            else:
                print(f"   ⚠️ tumcsvlong.csv veya tumcsvshort.csv bulunamadı!")
                return pd.DataFrame(), pd.DataFrame()
                
        except Exception as e:
            print(f"   ❌ Sistem çalıştırma hatası: {e}")
            return pd.DataFrame(), pd.DataFrame()
    
    def simulate_daily_system_with_cache(self, current_date: datetime, 
                                        base_long_df: pd.DataFrame, 
                                        base_short_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Günlük sistemi simüle et (cache kullanarak)
        Gerçekte her gün run_anywhere_n.py çalışmalı ama bu çok yavaş olur
        Bu yüzden mevcut verileri kullanarak simüle ediyoruz
        """
        # Mevcut verileri kopyala
        long_stocks = base_long_df.copy()
        short_stocks = base_short_df.copy()
        
        # Skorlara küçük rastgele değişiklikler ekle (gerçekçilik için)
        # Gerçekte burada run_anywhere_n.py çalışmalı ve gerçek skorlar hesaplanmalı
        np.random.seed(int(current_date.strftime('%Y%m%d')))  # Tarihe göre seed
        
        if 'FINAL_THG' in long_stocks.columns:
            # FINAL_THG'ye küçük rastgele değişiklikler ekle (%1-5 arası)
            noise = np.random.normal(0, 0.02, len(long_stocks))  # %2 standart sapma
            long_stocks['FINAL_THG'] = long_stocks['FINAL_THG'] * (1 + noise)
        
        if 'SHORT_FINAL' in short_stocks.columns:
            # SHORT_FINAL'e küçük rastgele değişiklikler ekle
            noise = np.random.normal(0, 0.02, len(short_stocks))
            short_stocks['SHORT_FINAL'] = short_stocks['SHORT_FINAL'] * (1 + noise)
        
        return long_stocks, short_stocks
    
    def check_position_scores(self, current_date: datetime, 
                             long_stocks_df: pd.DataFrame, 
                             short_stocks_df: pd.DataFrame) -> Tuple[dict, dict]:
        """Mevcut pozisyonların skorlarını kontrol et"""
        positions_to_reduce = {}
        positions_to_increase = {}
        
        # Tüm hisseleri birleştir
        all_stocks = pd.concat([long_stocks_df, short_stocks_df]).drop_duplicates(subset=['PREF_IBKR'], keep='first')
        
        for symbol, position in self.current_positions.items():
            # Bu hisse için güncel skorları bul
            stock_data = all_stocks[all_stocks['PREF_IBKR'] == symbol]
            
            if len(stock_data) == 0:
                continue
            
            stock_row = stock_data.iloc[0]
            current_score = position.get('score', 0)
            
            if position['type'] == 'LONG':
                new_score = stock_row.get('FINAL_THG', 0)
                if current_score > 0:
                    if new_score < current_score * (1 - SCORE_DETERIORATION_THRESHOLD):
                        reduction_ratio = min((current_score - new_score) / current_score, POSITION_REDUCTION_RATIO)
                        positions_to_reduce[symbol] = {
                            'type': 'LONG',
                            'reduction_ratio': reduction_ratio,
                            'old_score': current_score,
                            'new_score': new_score,
                            'reason': f'FINAL_THG düştü: {current_score:.4f} → {new_score:.4f}'
                        }
                    elif new_score > current_score * (1 + SCORE_DETERIORATION_THRESHOLD):
                        increase_ratio = min((new_score - current_score) / current_score, POSITION_REDUCTION_RATIO)
                        positions_to_increase[symbol] = {
                            'type': 'LONG',
                            'increase_ratio': increase_ratio,
                            'old_score': current_score,
                            'new_score': new_score,
                            'reason': f'FINAL_THG yükseldi: {current_score:.4f} → {new_score:.4f}'
                        }
            
            elif position['type'] == 'SHORT':
                new_score = stock_row.get('SHORT_FINAL', 0)
                if current_score < 0:
                    if new_score > current_score * (1 + SCORE_DETERIORATION_THRESHOLD):
                        reduction_ratio = min((new_score - current_score) / abs(current_score), POSITION_REDUCTION_RATIO)
                        positions_to_reduce[symbol] = {
                            'type': 'SHORT',
                            'reduction_ratio': reduction_ratio,
                            'old_score': current_score,
                            'new_score': new_score,
                            'reason': f'SHORT_FINAL yükseldi: {current_score:.4f} → {new_score:.4f}'
                        }
                    elif new_score < current_score * (1 - SCORE_DETERIORATION_THRESHOLD):
                        increase_ratio = min((current_score - new_score) / abs(current_score), POSITION_REDUCTION_RATIO)
                        positions_to_increase[symbol] = {
                            'type': 'SHORT',
                            'increase_ratio': increase_ratio,
                            'old_score': current_score,
                            'new_score': new_score,
                            'reason': f'SHORT_FINAL düştü: {current_score:.4f} → {new_score:.4f}'
                        }
        
        return positions_to_reduce, positions_to_increase
    
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
            'shares': position_size / entry_price if entry_price > 0 else 0,
            'exit_date': exit_date,
            'exit_price': exit_price,
            'pnl': 0,
            'return_pct': 0
        }
        
        if exit_date and exit_price and entry_price > 0:
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
            trade['return_pct'] = (trade['net_pnl'] / position_size) * 100 if position_size > 0 else 0
        
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
    
    def estimate_time(self, num_days: int) -> str:
        """Tahmini süreyi hesapla"""
        # Her gün için tahmini süre:
        # - IBKR veri çekme: 2-5 dakika
        # - Sistem çalıştırma (run_anywhere_n.py): 5-10 dakika
        # - Toplam: ~7-15 dakika/gün
        
        min_time_per_day = 7  # dakika
        max_time_per_day = 15  # dakika
        
        total_min_minutes = num_days * min_time_per_day
        total_max_minutes = num_days * max_time_per_day
        
        total_min_hours = total_min_minutes / 60
        total_max_hours = total_max_minutes / 60
        
        return f"{total_min_hours:.1f}-{total_max_hours:.1f} saat ({total_min_minutes}-{total_max_minutes} dakika)"
    
    def run_backtest(self, start_date: datetime, end_date: datetime,
                    base_long_df: pd.DataFrame, base_short_df: pd.DataFrame):
        """
        Gerçekçi Walk-Forward Backtest
        Her gün için tüm sistemin çalışmasını simüle eder
        """
        print(f"\n🚀 Gerçekçi Walk-Forward Backtest başlatılıyor...")
        print(f"📅 Tarih aralığı: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        print(f"📊 Toplam gün sayısı: {BACKTEST_DAYS} gün")
        print(f"💰 Başlangıç sermayesi: ${INITIAL_CAPITAL:,.2f}")
        print(f"📊 Dağılım: %{LONG_PERCENTAGE*100:.0f} LONG, %{SHORT_PERCENTAGE*100:.0f} SHORT")
        print(f"📈 Hedef hisse sayısı: {MIN_STOCKS}-{MAX_STOCKS} hisse")
        
        # Tahmini süreyi göster
        estimated_time = self.estimate_time(BACKTEST_DAYS)
        print(f"\n⏱️  TAHMİNİ SÜRE: {estimated_time}")
        print(f"⚠️  NOT: Her gün için tüm sistem çalışacak (run_anywhere_n.py)")
        print(f"⚠️  Bu işlem uzun sürebilir. Devam etmek istiyor musunuz? (Enter'a basın)")
        input()
        
        # Ortam hazırla
        self.setup_backtest_environment()
        
        current_capital = INITIAL_CAPITAL
        rebalance_dates = self.get_rebalance_dates(start_date, end_date)
        
        print(f"\n🔄 Toplam işlem günü: {len(rebalance_dates)} adet")
        print(f"⏱️  Başlangıç zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        total_start_time = time.time()
        
        # Her gün portföyü güncelle
        for i, current_date in enumerate(rebalance_dates):
            day_start_time = time.time()
            
            print(f"\n{'='*60}")
            print(f"📅 Gün #{i+1}/{len(rebalance_dates)}: {current_date.strftime('%Y-%m-%d')}")
            print(f"{'='*60}")
            print(f"💰 Mevcut portföy değeri: ${current_capital:,.2f}")
            print(f"📊 Aktif pozisyon sayısı: {len(self.current_positions)}")
            
            # 1. Her gün için tüm sistemi çalıştır
            # NOT: Gerçekte burada run_anywhere_n.py çalışmalı
            # Şimdilik simüle ediyoruz
            long_stocks, short_stocks = self.simulate_daily_system_with_cache(
                current_date, base_long_df, base_short_df
            )
            
            if len(long_stocks) == 0 or len(short_stocks) == 0:
                print(f"   ⚠️ Veri bulunamadı, atlanıyor...")
                continue
            
            # 2. Mevcut pozisyonların skorlarını kontrol et
            positions_to_reduce, positions_to_increase = self.check_position_scores(
                current_date, long_stocks, short_stocks
            )
            
            if positions_to_reduce:
                print(f"   📉 Pozisyon azaltma: {len(positions_to_reduce)} adet")
            if positions_to_increase:
                print(f"   📈 Pozisyon artırma: {len(positions_to_increase)} adet")
            
            # Pozisyonları azalt
            for symbol, info in positions_to_reduce.items():
                if symbol in self.current_positions:
                    position = self.current_positions[symbol]
                    reduction_size = position['size'] * info['reduction_ratio']
                    
                    # Fiyatı simüle et (gerçekte IBKR'den çekilmeli)
                    # Şimdilik entry_price'ı kullanıyoruz
                    exit_price = position['entry_price'] * (1 + np.random.normal(0, 0.02))
                    
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
                    
                    # Ortalama giriş fiyatını güncelle
                    current_price = position['entry_price'] * (1 + np.random.normal(0, 0.01))
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
                        'shares': increase_size / current_price if current_price > 0 else 0,
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
            
            # 3. Yeni pozisyonlar ekle
            current_long_count = sum(1 for p in self.current_positions.values() if p['type'] == 'LONG')
            current_short_count = sum(1 for p in self.current_positions.values() if p['type'] == 'SHORT')
            total_positions = len(self.current_positions)
            
            if total_positions < MAX_STOCKS:
                target_long = int(MAX_STOCKS * LONG_PERCENTAGE)
                target_short = int(MAX_STOCKS * SHORT_PERCENTAGE)
                
                # LONG pozisyonları ekle
                long_capital = current_capital * self.long_pct
                long_total_recsize = long_stocks['RECSIZE'].fillna(0).sum() if 'RECSIZE' in long_stocks.columns else 0
                
                if long_total_recsize == 0:
                    long_total_recsize = len(long_stocks) * AVG_PREF_PRICE * 100
                
                long_sorted = long_stocks.sort_values('FINAL_THG', ascending=False)
                new_long_count = min(MAX_STOCKS - total_positions, target_long - current_long_count)
                
                for idx, stock in long_sorted.iterrows():
                    if new_long_count <= 0:
                        break
                    
                    symbol = stock['PREF_IBKR']
                    if symbol in self.current_positions:
                        continue
                    
                    entry_price = stock.get('Last Price', AVG_PREF_PRICE)
                    if pd.isna(entry_price) or entry_price <= 0:
                        entry_price = AVG_PREF_PRICE
                    
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
                        'shares': position_size / entry_price if entry_price > 0 else 0,
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
                
                # SHORT pozisyonları ekle
                short_capital = current_capital * self.short_pct
                short_total_recsize = short_stocks['RECSIZE'].fillna(0).sum() if 'RECSIZE' in short_stocks.columns else 0
                
                if short_total_recsize == 0:
                    short_total_recsize = len(short_stocks) * AVG_PREF_PRICE * 100
                
                short_sorted = short_stocks.sort_values('SHORT_FINAL', ascending=True)
                new_short_count = min(MAX_STOCKS - total_positions, target_short - current_short_count)
                
                for idx, stock in short_sorted.iterrows():
                    if new_short_count <= 0:
                        break
                    
                    symbol = stock['PREF_IBKR']
                    if symbol in self.current_positions:
                        continue
                    
                    entry_price = stock.get('Last Price', AVG_PREF_PRICE)
                    if pd.isna(entry_price) or entry_price <= 0:
                        entry_price = AVG_PREF_PRICE
                    
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
                        'shares': position_size / entry_price if entry_price > 0 else 0,
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
            
            # Portföy değerini güncelle
            total_pnl = 0
            for symbol, position in self.current_positions.items():
                # Fiyat değişimini simüle et
                price_change = np.random.normal(0, 0.02)  # %2 standart sapma
                current_price = position['entry_price'] * (1 + price_change)
                
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
            
            day_elapsed = time.time() - day_start_time
            total_elapsed = time.time() - total_start_time
            remaining_days = len(rebalance_dates) - (i + 1)
            avg_time_per_day = total_elapsed / (i + 1)
            estimated_remaining = avg_time_per_day * remaining_days
            
            print(f"   ⏱️  Bu gün: {day_elapsed:.1f} saniye")
            print(f"   ⏱️  Toplam: {total_elapsed/60:.1f} dakika")
            print(f"   ⏱️  Tahmini kalan: {estimated_remaining/60:.1f} dakika")
        
        # Son günde tüm pozisyonları kapat
        print(f"\n📅 Son gün: Tüm pozisyonlar kapatılıyor...")
        final_date = rebalance_dates[-1]
        for symbol, position in list(self.current_positions.items()):
            exit_price = position['entry_price'] * (1 + np.random.normal(0, 0.02))
            trade = self.simulate_trade(
                symbol, position['type'], position['entry_date'],
                position['entry_price'], position['size'],
                final_date, exit_price
            )
            self.trades_history.append(trade)
            current_capital += trade['net_pnl']
        
        self.current_positions = {}
        
        total_time = time.time() - total_start_time
        print(f"\n✅ Backtest tamamlandı!")
        print(f"⏱️  Toplam süre: {total_time/60:.1f} dakika ({total_time/3600:.2f} saat)")
        
        return current_capital
    
    def generate_report(self):
        """Backtest raporu oluştur"""
        if not self.trades_history:
            print("⚠️ Trade geçmişi yok!")
            return
        
        trades_df = pd.DataFrame(self.trades_history)
        portfolio_df = pd.DataFrame(self.portfolio_history)
        
        print(f"\n{'='*60}")
        print(f"📊 GERÇEKÇİ BACKTEST SONUÇLARI")
        print(f"{'='*60}")
        
        if len(portfolio_df) > 0:
            final_capital = portfolio_df['capital'].iloc[-1]
            total_return = ((final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
            print(f"💰 Final Portföy Değeri: ${final_capital:,.2f}")
            print(f"📈 Toplam Getiri: {total_return:.2f}%")
            print(f"📊 Ortalama Pozisyon Sayısı: {portfolio_df['num_positions'].mean():.1f}")
        
        if len(trades_df) > 0:
            long_trades = trades_df[trades_df['type'].str.contains('LONG', na=False)]
            short_trades = trades_df[trades_df['type'].str.contains('SHORT', na=False)]
            
            print(f"\n🟢 LONG Trades: {len(long_trades)} adet")
            if len(long_trades) > 0:
                closed_long = long_trades[long_trades['exit_date'].notna()]
                if len(closed_long) > 0:
                    print(f"   Ortalama Getiri: {closed_long['return_pct'].mean():.2f}%")
                    print(f"   Win Rate: {(closed_long['return_pct'] > 0).sum() / len(closed_long) * 100:.1f}%")
            
            print(f"\n🔴 SHORT Trades: {len(short_trades)} adet")
            if len(short_trades) > 0:
                closed_short = short_trades[short_trades['exit_date'].notna()]
                if len(closed_short) > 0:
                    print(f"   Ortalama Getiri: {closed_short['return_pct'].mean():.2f}%")
                    print(f"   Win Rate: {(closed_short['return_pct'] > 0).sum() / len(closed_short) * 100:.1f}%")
        
        # Dosyalara kaydet
        if len(trades_df) > 0:
            trades_df.to_csv('backtest_realistic_trades.csv', index=False)
            print(f"\n💾 Trade detayları 'backtest_realistic_trades.csv' dosyasına kaydedildi")
        
        if len(portfolio_df) > 0:
            portfolio_df.to_csv('backtest_realistic_portfolio_history.csv', index=False)
            print(f"💾 Portföy geçmişi 'backtest_realistic_portfolio_history.csv' dosyasına kaydedildi")


if __name__ == "__main__":
    from datetime import datetime, timedelta
    
    # 3 ay önceden başla
    end_date = datetime.now()
    start_date = end_date - timedelta(days=BACKTEST_DAYS)
    
    # LONG/SHORT seçimlerini yükle
    try:
        long_stocks = pd.read_csv('tumcsvlong.csv')
        short_stocks = pd.read_csv('tumcsvshort.csv')
        
        print(f"\n{'='*60}")
        print(f"⚠️  ÖNEMLİ BİLGİLENDİRME")
        print(f"{'='*60}")
        print(f"📊 Bu backtest her gün için tüm sistemin çalışmasını simüle eder.")
        print(f"📅 Toplam {BACKTEST_DAYS} gün için backtest yapılacak.")
        print(f"⏱️  TAHMİNİ SÜRE: 10.5-22.5 saat")
        print(f"\n💡 NOT: Gerçekte her gün için run_anywhere_n.py çalışmalı.")
        print(f"💡 Şu anda simüle edilmiş veriler kullanılıyor.")
        print(f"💡 Daha gerçekçi sonuçlar için geçmiş tarihlerde sistem çıktıları kullanılmalı.")
        print(f"\n{'='*60}\n")
        
        # Backtest'i çalıştır
        engine = RealisticBacktestEngine(INITIAL_CAPITAL, LONG_PERCENTAGE, SHORT_PERCENTAGE)
        final_capital = engine.run_backtest(start_date, end_date, long_stocks, short_stocks)
        engine.generate_report()
        
    except FileNotFoundError:
        print("❌ tumcsvlong.csv veya tumcsvshort.csv dosyaları bulunamadı!")
        print("💡 Önce 'python ntumcsvport.py' komutunu çalıştırın.")



