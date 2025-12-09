"""
Dinamik Backtest Scripti - Günlük Güncelleme ve Skor Bazlı Pozisyon Yönetimi

Özellikler:
1. Her gün yeni LONG/SHORT fırsatları değerlendirilir
2. Mevcut pozisyonların skorları kontrol edilir
3. FINAL_THG skoru düşerse LONG pozisyon azaltılır
4. SHORT_FINAL skoru yükselirse SHORT pozisyon azaltılır
5. Likidite kontrolü (AVG_ADV) yapılır
6. Toplam 40-70 hisse arasında tutulur
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
BACKTEST_YEARS = 2  # 2 yıl geriye dönük
REBALANCE_FREQUENCY = 'daily'  # Günlük güncelleme
TRANSACTION_COST = 0.001  # %0.1 işlem maliyeti
SHORT_MARGIN_COST = 0.05  # %5 yıllık short margin maliyeti
SLIPPAGE = 0.0005  # %0.05 slippage
MIN_STOCKS = 40  # Minimum hisse sayısı
MAX_STOCKS = 70  # Maksimum hisse sayısı
SCORE_DETERIORATION_THRESHOLD = 0.05  # Skor %5 kötüleşirse pozisyon azalt
POSITION_REDUCTION_RATIO = 0.5  # Pozisyonu %50 azalt

class DynamicBacktestEngine:
    def __init__(self, initial_capital: float, long_pct: float, short_pct: float):
        self.initial_capital = initial_capital
        self.long_pct = long_pct
        self.short_pct = short_pct
        self.ib = None
        self.portfolio_history = []
        self.trades_history = []
        self.current_positions = {}  # {symbol: {'type': 'LONG'/'SHORT', 'size': float, 'entry_price': float, 'entry_date': datetime, 'score': float, 'recsize': float}}
        
    def connect_to_ibkr(self):
        """IBKR'ye bağlan"""
        print("🔗 IBKR'ye bağlanılıyor...")
        self.ib = IB()
        try:
            ports = [7496, 4001]
            connected = False
            for port in ports:
                try:
                    self.ib.connect('127.0.0.1', port, clientId=1)
                    connected = True
                    print(f"✅ IBKR'ye bağlandı (port {port})")
                    break
                except:
                    continue
            if not connected:
                raise Exception("IBKR'ye bağlanılamadı")
        except Exception as e:
            print(f"❌ IBKR bağlantı hatası: {e}")
            raise
    
    def disconnect_from_ibkr(self):
        """IBKR bağlantısını kapat"""
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
            print("🔌 IBKR bağlantısı kapatıldı")
    
    def get_historical_prices(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """IBKR'den geçmiş fiyat verilerini çek"""
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime=end_date,
                durationStr='2 Y',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            
            if not bars:
                return None
            
            df = util.df(bars)
            df['date'] = pd.to_datetime(df['date'])
            df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
            df = df.sort_values('date')
            
            return df
            
        except Exception as e:
            print(f"⚠️ {symbol} için fiyat verisi çekilemedi: {e}")
            return None
    
    def get_daily_opportunities(self, date: datetime, all_stocks_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Her gün için LONG ve SHORT fırsatlarını belirle"""
        # LONG fırsatları: En yüksek FINAL_THG skorlarına sahip hisseler
        long_opportunities = all_stocks_df.nlargest(MAX_STOCKS, 'FINAL_THG').copy()
        
        # SHORT fırsatları: En düşük SHORT_FINAL skorlarına sahip hisseler
        short_opportunities = all_stocks_df.nsmallest(MAX_STOCKS, 'SHORT_FINAL').copy()
        
        return long_opportunities, short_opportunities
    
    def check_position_scores(self, date: datetime, all_stocks_df: pd.DataFrame) -> Tuple[dict, dict]:
        """
        Mevcut pozisyonların skorlarını kontrol et
        
        Returns:
            positions_to_reduce: Azaltılacak pozisyonlar
            positions_to_increase: Artırılacak pozisyonlar
        """
        positions_to_reduce = {}
        positions_to_increase = {}
        
        for symbol, position in self.current_positions.items():
            # Bu hisse için güncel skorları bul
            stock_data = all_stocks_df[all_stocks_df['PREF_IBKR'] == symbol]
            
            if len(stock_data) == 0:
                continue
            
            stock_row = stock_data.iloc[0]
            current_score = position.get('score', 0)
            
            if position['type'] == 'LONG':
                # LONG pozisyon: FINAL_THG skoru düşerse azalt
                new_score = stock_row.get('FINAL_THG', 0)
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
                # SHORT pozisyon: SHORT_FINAL skoru yükselirse azalt
                new_score = stock_row.get('SHORT_FINAL', 0)
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
        """Likidite kontrolü - AVG_ADV'ye göre pozisyon büyüklüğünü kontrol et"""
        avg_adv = stock_row.get('AVG_ADV', 0)
        
        if avg_adv == 0:
            return False
        
        # RECSIZE kontrolü
        recsize = stock_row.get('RECSIZE', 0)
        if recsize > 0:
            # RECSIZE AVG_ADV/6'dan fazla olmamalı (ntumcsvport.py mantığı)
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
            
            # Transaction costs
            entry_cost = position_size * TRANSACTION_COST
            exit_cost = (position_size + trade['pnl']) * TRANSACTION_COST
            trade['transaction_costs'] = entry_cost + exit_cost
            
            # Slippage
            trade['slippage'] = position_size * SLIPPAGE * 2
            
            # Short margin cost
            if position_type == 'SHORT':
                days_held = (exit_date - entry_date).days
                trade['margin_cost'] = position_size * (SHORT_MARGIN_COST / 365) * days_held
            else:
                trade['margin_cost'] = 0
            
            # Net PnL
            trade['net_pnl'] = trade['pnl'] - trade['transaction_costs'] - trade['slippage'] - trade['margin_cost']
            trade['return_pct'] = (trade['net_pnl'] / position_size) * 100
        
        return trade
    
    def get_rebalance_dates(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Rebalance tarihlerini belirle (günlük)"""
        dates = []
        current = start_date
        
        while current <= end_date:
            # Hafta sonlarını atla (opsiyonel)
            if current.weekday() < 5:  # Pazartesi=0, Cuma=4
                dates.append(current)
            current += timedelta(days=1)
        
        return dates
    
    def run_backtest(self, start_date: datetime, end_date: datetime, 
                    all_stocks_df: pd.DataFrame):
        """Dinamik Backtest - Her gün güncellenen fırsatlar ve skor bazlı pozisyon yönetimi"""
        print(f"\n🚀 Dinamik Backtest başlatılıyor...")
        print(f"📅 Tarih aralığı: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        print(f"💰 Başlangıç sermayesi: ${INITIAL_CAPITAL:,.2f}")
        print(f"📊 Dağılım: %{LONG_PERCENTAGE*100:.0f} LONG, %{SHORT_PERCENTAGE*100:.0f} SHORT")
        print(f"📈 Hedef hisse sayısı: {MIN_STOCKS}-{MAX_STOCKS} hisse")
        print(f"🔄 Rebalance sıklığı: {REBALANCE_FREQUENCY} (Her gün güncelleme)")
        print(f"📊 Skor bazlı pozisyon yönetimi: FINAL_THG düşerse LONG azalt, SHORT_FINAL yükselirse SHORT azalt\n")
        
        # IBKR'ye bağlan
        self.connect_to_ibkr()
        
        try:
            current_capital = INITIAL_CAPITAL
            rebalance_dates = self.get_rebalance_dates(start_date, end_date)
            
            print(f"🔄 Toplam işlem günü: {len(rebalance_dates)} adet\n")
            
            # Her gün portföyü güncelle
            for i, current_date in enumerate(rebalance_dates):
                if i % 10 == 0:  # Her 10 günde bir özet göster
                    print(f"\n{'='*60}")
                    print(f"📅 Gün #{i+1}/{len(rebalance_dates)}: {current_date.strftime('%Y-%m-%d')}")
                    print(f"{'='*60}")
                    print(f"💰 Mevcut portföy değeri: ${current_capital:,.2f}")
                    print(f"📊 Aktif pozisyon sayısı: {len(self.current_positions)}")
                
                # 1. Mevcut pozisyonların skorlarını kontrol et
                positions_to_reduce, positions_to_increase = self.check_position_scores(current_date, all_stocks_df)
                
                if (positions_to_reduce or positions_to_increase) and i % 10 == 0:
                    if positions_to_reduce:
                        print(f"\n📉 Pozisyon azaltma kararları: {len(positions_to_reduce)} adet")
                        for symbol, info in list(positions_to_reduce.items())[:3]:  # İlk 3'ünü göster
                            print(f"   {info['type']} {symbol}: {info['reason']}")
                    if positions_to_increase:
                        print(f"\n📈 Pozisyon artırma kararları: {len(positions_to_increase)} adet")
                        for symbol, info in list(positions_to_increase.items())[:3]:  # İlk 3'ünü göster
                            print(f"   {info['type']} {symbol}: {info['reason']}")
                
                # Pozisyonları azalt (skorlar kötüleştiğinde)
                for symbol, info in positions_to_reduce.items():
                    if symbol in self.current_positions:
                        position = self.current_positions[symbol]
                        reduction_size = position['size'] * info['reduction_ratio']
                        
                        # Fiyatı al ve trade simüle et
                        price_df = self.get_historical_prices(symbol, current_date, current_date + timedelta(days=1))
                        if price_df is not None and len(price_df) > 0:
                            exit_price = price_df['close'].iloc[0]
                            trade = self.simulate_trade(
                                symbol, info['type'], position['entry_date'],
                                position['entry_price'], reduction_size,
                                current_date, exit_price
                            )
                            self.trades_history.append(trade)
                            
                            # Pozisyonu güncelle
                            self.current_positions[symbol]['size'] -= reduction_size
                            current_capital += trade['net_pnl']
                            
                            if self.current_positions[symbol]['size'] <= 0:
                                del self.current_positions[symbol]
                
                # Pozisyonları artır (skorlar iyileştiğinde)
                for symbol, info in positions_to_increase.items():
                    if symbol in self.current_positions:
                        position = self.current_positions[symbol]
                        increase_size = position['size'] * info['increase_ratio']
                        
                        # Fiyatı al
                        price_df = self.get_historical_prices(symbol, current_date, current_date + timedelta(days=1))
                        if price_df is not None and len(price_df) > 0:
                            current_price = price_df['close'].iloc[0]
                            
                            # Pozisyonu artır (yeni fiyattan ek pozisyon aç)
                            # Ortalama giriş fiyatını güncelle
                            total_size = position['size'] + increase_size
                            avg_entry_price = ((position['entry_price'] * position['size']) + 
                                             (current_price * increase_size)) / total_size
                            
                            self.current_positions[symbol]['size'] = total_size
                            self.current_positions[symbol]['entry_price'] = avg_entry_price
                            self.current_positions[symbol]['score'] = info['new_score']
                            
                            # Trade kaydı (pozisyon artırma)
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
                
                # 2. Yeni LONG/SHORT fırsatlarını belirle
                long_opportunities, short_opportunities = self.get_daily_opportunities(current_date, all_stocks_df)
                
                # 3. Yeni pozisyonlar için fırsatları değerlendir
                # FINAL_THG yükselen hisseler için LONG açılır
                # SHORT_FINAL düşen hisseler için SHORT açılır
                
                current_long_count = sum(1 for p in self.current_positions.values() if p['type'] == 'LONG')
                current_short_count = sum(1 for p in self.current_positions.values() if p['type'] == 'SHORT')
                total_positions = len(self.current_positions)
                
                # Hedef: 40-70 hisse arası
                # Yeni pozisyonlar ekle (FINAL_THG yüksek olanlar LONG, SHORT_FINAL düşük olanlar SHORT)
                if total_positions < MAX_STOCKS:
                    # Yeni pozisyonlar ekle
                    target_long = int(MIN_STOCKS * LONG_PERCENTAGE)
                    target_short = int(MIN_STOCKS * SHORT_PERCENTAGE)
                    
                    # LONG pozisyonları ekle (FINAL_THG yüksek olanlar)
                    long_capital = current_capital * self.long_pct
                    long_total_recsize = long_opportunities['RECSIZE'].fillna(0).sum() if 'RECSIZE' in long_opportunities.columns else 0
                    
                    if long_total_recsize == 0:
                        long_total_recsize = len(long_opportunities) * AVG_PREF_PRICE * 100
                    
                    # FINAL_THG skoruna göre sırala (yüksekten düşüğe)
                    long_opportunities_sorted = long_opportunities.sort_values('FINAL_THG', ascending=False)
                    
                    # Mevcut pozisyonlarda olmayan ve FINAL_THG yüksek olanları seç
                    new_long_count = min(MAX_STOCKS - total_positions, target_long - current_long_count)
                    
                    for idx, stock in long_opportunities_sorted.iterrows():
                        if new_long_count <= 0:
                            break
                            
                        symbol = stock['PREF_IBKR']
                        
                        if symbol in self.current_positions:
                            continue
                        
                        # Likidite kontrolü
                        if not self.check_liquidity(stock, 0):
                            continue
                        
                        # Fiyatı al
                        price_df = self.get_historical_prices(symbol, current_date, current_date + timedelta(days=1))
                        if price_df is None or len(price_df) == 0:
                            continue
                        
                        entry_price = price_df['close'].iloc[0]
                        recsize = stock.get('RECSIZE', 0)
                        final_thg = stock.get('FINAL_THG', 0)
                        
                        if recsize > 0 and long_total_recsize > 0:
                            recsize_ratio = recsize / long_total_recsize
                            position_size = long_capital * recsize_ratio / new_long_count
                        else:
                            position_size = long_capital / new_long_count
                        
                        # Pozisyonu ekle
                        self.current_positions[symbol] = {
                            'type': 'LONG',
                            'size': position_size,
                            'entry_price': entry_price,
                            'entry_date': current_date,
                            'score': final_thg,
                            'recsize': recsize
                        }
                        
                        new_long_count -= 1
                        
                        # Trade kaydı
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
                    
                    # SHORT pozisyonları ekle (SHORT_FINAL düşük olanlar)
                    short_capital = current_capital * self.short_pct
                    short_total_recsize = short_opportunities['RECSIZE'].fillna(0).sum() if 'RECSIZE' in short_opportunities.columns else 0
                    
                    if short_total_recsize == 0:
                        short_total_recsize = len(short_opportunities) * AVG_PREF_PRICE * 100
                    
                    # SHORT_FINAL skoruna göre sırala (düşükten yükseğe - en düşük en iyi SHORT)
                    short_opportunities_sorted = short_opportunities.sort_values('SHORT_FINAL', ascending=True)
                    
                    # Mevcut pozisyonlarda olmayan ve SHORT_FINAL düşük olanları seç
                    new_short_count = min(MAX_STOCKS - total_positions, target_short - current_short_count)
                    
                    for idx, stock in short_opportunities_sorted.iterrows():
                        if new_short_count <= 0:
                            break
                            
                        symbol = stock['PREF_IBKR']
                        
                        if symbol in self.current_positions:
                            continue
                        
                        # Likidite kontrolü
                        if not self.check_liquidity(stock, 0):
                            continue
                        
                        # Fiyatı al
                        price_df = self.get_historical_prices(symbol, current_date, current_date + timedelta(days=1))
                        if price_df is None or len(price_df) == 0:
                            continue
                        
                        entry_price = price_df['close'].iloc[0]
                        recsize = stock.get('RECSIZE', 0)
                        short_final = stock.get('SHORT_FINAL', 0)
                        
                        if recsize > 0 and short_total_recsize > 0:
                            recsize_ratio = recsize / short_total_recsize
                            position_size = short_capital * recsize_ratio / new_short_count
                        else:
                            position_size = short_capital / new_short_count
                        
                        # Pozisyonu ekle
                        self.current_positions[symbol] = {
                            'type': 'SHORT',
                            'size': position_size,
                            'entry_price': entry_price,
                            'entry_date': current_date,
                            'score': short_final,
                            'recsize': recsize
                        }
                        
                        new_short_count -= 1
                        
                        # Trade kaydı
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
                
                # 4. Mevcut pozisyonların değerini güncelle
                if i % 10 == 0:  # Her 10 günde bir portföy değerini güncelle
                    total_pnl = 0
                    for symbol, position in self.current_positions.items():
                        price_df = self.get_historical_prices(symbol, current_date, current_date + timedelta(days=1))
                        if price_df is not None and len(price_df) > 0:
                            current_price = price_df['close'].iloc[0]
                            if position['type'] == 'LONG':
                                pnl = (current_price - position['entry_price']) * (position['size'] / position['entry_price'])
                            else:  # SHORT
                                pnl = (position['entry_price'] - current_price) * (position['size'] / position['entry_price'])
                            total_pnl += pnl
                    
                    # Portföy geçmişini kaydet
                    self.portfolio_history.append({
                        'date': current_date,
                        'capital': current_capital + total_pnl,
                        'num_positions': len(self.current_positions),
                        'num_long': current_long_count,
                        'num_short': current_short_count,
                        'return_pct': ((current_capital + total_pnl - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
                    })
                
                # Rate limiting
                if i % 10 == 0:
                    time.sleep(0.1)
            
            # Son günde tüm pozisyonları kapat
            print(f"\n📅 Son gün: Tüm pozisyonlar kapatılıyor...")
            final_date = rebalance_dates[-1]
            for symbol, position in list(self.current_positions.items()):
                price_df = self.get_historical_prices(symbol, final_date, final_date + timedelta(days=1))
                if price_df is not None and len(price_df) > 0:
                    exit_price = price_df['close'].iloc[0]
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
            print("⚠️ Trade geçmişi yok!")
            return
        
        trades_df = pd.DataFrame(self.trades_history)
        portfolio_df = pd.DataFrame(self.portfolio_history)
        
        print(f"\n{'='*60}")
        print(f"📊 BACKTEST SONUÇLARI")
        print(f"{'='*60}")
        
        if len(portfolio_df) > 0:
            final_capital = portfolio_df['capital'].iloc[-1]
            total_return = ((final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
            print(f"💰 Final Portföy Değeri: ${final_capital:,.2f}")
            print(f"📈 Toplam Getiri: {total_return:.2f}%")
            print(f"📊 Ortalama Pozisyon Sayısı: {portfolio_df['num_positions'].mean():.1f}")
        
        if len(trades_df) > 0:
            long_trades = trades_df[trades_df['type'] == 'LONG']
            short_trades = trades_df[trades_df['type'] == 'SHORT']
            
            print(f"\n🟢 LONG Trades: {len(long_trades)} adet")
            if len(long_trades) > 0:
                print(f"   Ortalama Getiri: {long_trades['return_pct'].mean():.2f}%")
                print(f"   Win Rate: {(long_trades['return_pct'] > 0).sum() / len(long_trades) * 100:.1f}%")
            
            print(f"\n🔴 SHORT Trades: {len(short_trades)} adet")
            if len(short_trades) > 0:
                print(f"   Ortalama Getiri: {short_trades['return_pct'].mean():.2f}%")
                print(f"   Win Rate: {(short_trades['return_pct'] > 0).sum() / len(short_trades) * 100:.1f}%")
        
        # Dosyalara kaydet
        if len(trades_df) > 0:
            trades_df.to_csv('backtest_dynamic_trades.csv', index=False)
            print(f"\n💾 Trade detayları 'backtest_dynamic_trades.csv' dosyasına kaydedildi")
        
        if len(portfolio_df) > 0:
            portfolio_df.to_csv('backtest_dynamic_portfolio_history.csv', index=False)
            print(f"💾 Portföy geçmişi 'backtest_dynamic_portfolio_history.csv' dosyasına kaydedildi")


if __name__ == "__main__":
    # Örnek kullanım
    from datetime import datetime, timedelta
    
    # Tarihleri belirle
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2 yıl
    
    # LONG/SHORT seçimlerini yükle
    try:
        long_stocks = pd.read_csv('tumcsvlong.csv')
        short_stocks = pd.read_csv('tumcsvshort.csv')
        all_stocks = pd.concat([long_stocks, short_stocks]).drop_duplicates(subset=['PREF_IBKR'], keep='first')
        
        # Backtest'i çalıştır
        engine = DynamicBacktestEngine(INITIAL_CAPITAL, LONG_PERCENTAGE, SHORT_PERCENTAGE)
        final_capital = engine.run_backtest(start_date, end_date, all_stocks)
        engine.generate_report()
        
    except FileNotFoundError:
        print("❌ tumcsvlong.csv veya tumcsvshort.csv dosyaları bulunamadı!")
        print("💡 Önce 'python ntumcsvport.py' komutunu çalıştırın.")

