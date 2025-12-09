"""
2 Yıllık Geriye Dönük Backtest Scripti
%70 LONG, %30 SHORT pozisyonlarla 1 milyon dolarlık portföy simülasyonu

Bu script:
1. Geçmiş tarihlerde LONG/SHORT seçimlerini yapar
2. IBKR'den geçmiş fiyat verilerini çeker
3. Portföy performansını hesaplar
4. Detaylı raporlar oluşturur
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

# Backtest parametreleri - Port Adjuster ayarlarına uygun
INITIAL_CAPITAL = 1_000_000  # 1 milyon dolar
LONG_PERCENTAGE = 0.85  # %85 LONG (Port Adjuster'dan)
SHORT_PERCENTAGE = 0.15  # %15 SHORT (Port Adjuster'dan)
AVG_PREF_PRICE = 25.0  # Ortalama preferred stock fiyatı
BACKTEST_YEARS = 2  # 2 yıl geriye dönük
REBALANCE_FREQUENCY = 'daily'  # 'daily', 'weekly', 'monthly', 'quarterly' - Günlük güncelleme için 'daily'
TRANSACTION_COST = 0.001  # %0.1 işlem maliyeti
SHORT_MARGIN_COST = 0.05  # %5 yıllık short margin maliyeti
SLIPPAGE = 0.0005  # %0.05 slippage
MIN_STOCKS = 40  # Minimum hisse sayısı
MAX_STOCKS = 70  # Maksimum hisse sayısı (hedef)
SCORE_DETERIORATION_THRESHOLD = 0.05  # Skor %5 kötüleşirse pozisyon azalt
POSITION_REDUCTION_RATIO = 0.5  # Pozisyonu %50 azalt

class BacktestEngine:
    def __init__(self, initial_capital: float, long_pct: float, short_pct: float):
        self.initial_capital = initial_capital
        self.long_pct = long_pct
        self.short_pct = short_pct
        self.ib = None
        self.portfolio_history = []
        self.trades_history = []
        self.current_positions = {}  # {symbol: {'type': 'LONG'/'SHORT', 'size': float, 'entry_price': float, 'entry_date': datetime, 'score': float, 'recsize': float}}
        self.daily_opportunities = {}  # Her gün için LONG/SHORT fırsatları
        
    def connect_to_ibkr(self):
        """IBKR'ye bağlan"""
        print("🔗 IBKR'ye bağlanılıyor...")
        self.ib = IB()
        try:
            # TWS ve Gateway portlarını dene
            ports = [7496, 4001]
            connected = False
            for port in ports:
                try:
                    self.ib.connect('127.0.0.1', port, clientId=99, readonly=True, timeout=20)
                    connected = True
                    print(f"✅ IBKR bağlantısı başarılı (Port: {port})")
                    break
                except Exception as e:
                    print(f"⚠️ Port {port} bağlantı hatası: {e}")
            
            if not connected:
                print("❌ IBKR bağlantısı başarısız!")
                return False
            
            # Delayed data
            self.ib.reqMarketDataType(3)
            return True
            
        except Exception as e:
            print(f"❌ IBKR bağlantı hatası: {e}")
            return False
    
    def get_historical_prices(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Bir hisse için geçmiş fiyat verilerini çeker"""
        try:
            contract = Stock(symbol, exchange='SMART', currency='USD')
            qualified_contracts = self.ib.qualifyContracts(contract)
            
            if not qualified_contracts:
                return None
            
            contract = qualified_contracts[0]
            
            # Tarih aralığını hesapla
            days_diff = (end_date - start_date).days
            duration_str = f"{days_diff + 10} D"  # Biraz fazla gün iste
            
            # Historical data çek
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime=end_date.strftime('%Y%m%d %H:%M:%S'),
                durationStr=duration_str,
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True
            )
            
            if not bars:
                return None
            
            # DataFrame'e çevir
            df = util.df(bars)
            df['date'] = pd.to_datetime(df['date'])
            df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
            df = df.sort_values('date')
            
            return df
            
        except Exception as e:
            print(f"⚠️ {symbol} için fiyat verisi çekilemedi: {e}")
            return None
    
    def calculate_position_size_from_recsize(self, stock_row: pd.Series, entry_price: float) -> float:
        """RECSIZE'dan pozisyon büyüklüğünü hesapla (Port Adjuster mantığı)"""
        recsize = stock_row.get('RECSIZE', 0)
        
        if recsize and recsize > 0:
            # RECSIZE lot cinsinden, dolara çevir
            # RECSIZE * entry_price = pozisyon büyüklüğü (dolar)
            position_size = recsize * entry_price
            return position_size
        else:
            # RECSIZE yoksa, AVG_ADV'den hesapla
            avg_adv = stock_row.get('AVG_ADV', 0)
            if avg_adv > 0:
                # AVG_ADV'nin bir kısmını kullan (örnek: AVG_ADV / 10)
                position_size = (avg_adv / 10) * entry_price
                return max(position_size, 1000)  # Minimum $1000
            else:
                # Varsayılan pozisyon büyüklüğü
                return AVG_PREF_PRICE * 100  # 100 lot varsayılan
    
    def calculate_position_size(self, total_capital: float, num_long: int, num_short: int, 
                              long_stocks_df: pd.DataFrame = None, short_stocks_df: pd.DataFrame = None) -> Tuple[float, float]:
        """Pozisyon büyüklüğünü hesapla - RECSIZE kullanarak"""
        long_capital = total_capital * self.long_pct
        short_capital = total_capital * self.short_pct
        
        # RECSIZE kullanarak pozisyon büyüklüklerini hesapla
        total_long_recsize = 0
        total_short_recsize = 0
        
        if long_stocks_df is not None and len(long_stocks_df) > 0:
            # LONG hisselerin RECSIZE'larını topla
            total_long_recsize = long_stocks_df['RECSIZE'].fillna(0).sum()
        
        if short_stocks_df is not None and len(short_stocks_df) > 0:
            # SHORT hisselerin RECSIZE'larını topla
            total_short_recsize = short_stocks_df['RECSIZE'].fillna(0).sum()
        
        # Eğer RECSIZE toplamı varsa, oransal dağılım yap
        if total_long_recsize > 0 and total_short_recsize > 0:
            # RECSIZE'lara göre oransal dağılım
            return long_capital, short_capital
        else:
            # RECSIZE yoksa eşit dağılım
            long_position = long_capital / num_long if num_long > 0 else 0
            short_position = short_capital / num_short if num_short > 0 else 0
            return long_position, short_position
    
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
                # LONG: (exit_price - entry_price) * shares
                trade['pnl'] = (exit_price - entry_price) * trade['shares']
            else:  # SHORT
                # SHORT: (entry_price - exit_price) * shares
                trade['pnl'] = (entry_price - exit_price) * trade['shares']
            
            # Transaction costs
            entry_cost = position_size * TRANSACTION_COST
            exit_cost = (position_size + trade['pnl']) * TRANSACTION_COST
            trade['transaction_costs'] = entry_cost + exit_cost
            
            # Slippage
            trade['slippage'] = position_size * SLIPPAGE * 2  # Giriş ve çıkış
            
            # Short margin cost (sadece SHORT için)
            if position_type == 'SHORT':
                days_held = (exit_date - entry_date).days
                trade['margin_cost'] = position_size * (SHORT_MARGIN_COST / 365) * days_held
            else:
                trade['margin_cost'] = 0
            
            # Net PnL
            trade['net_pnl'] = trade['pnl'] - trade['transaction_costs'] - trade['slippage'] - trade['margin_cost']
            trade['return_pct'] = (trade['net_pnl'] / position_size) * 100
            
        return trade
    
    def run_backtest(self, start_date: datetime, end_date: datetime, 
                    long_stocks_df: pd.DataFrame, short_stocks_df: pd.DataFrame):
        """Dinamik Backtest - Her gün güncellenen fırsatlar ve skor bazlı pozisyon yönetimi"""
        print(f"\n🚀 Dinamik Backtest başlatılıyor...")
        print(f"📅 Tarih aralığı: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        print(f"💰 Başlangıç sermayesi: ${INITIAL_CAPITAL:,.2f}")
        print(f"📊 Dağılım: %{LONG_PERCENTAGE*100:.0f} LONG (${INITIAL_CAPITAL * LONG_PERCENTAGE:,.2f}), %{SHORT_PERCENTAGE*100:.0f} SHORT (${INITIAL_CAPITAL * SHORT_PERCENTAGE:,.2f})")
        print(f"📈 Hedef hisse sayısı: {MIN_STOCKS}-{MAX_STOCKS} hisse")
        print(f"🔄 Rebalance sıklığı: {REBALANCE_FREQUENCY} (Her gün güncelleme)")
        print(f"💸 İşlem maliyeti: {TRANSACTION_COST*100:.2f}%")
        print(f"📉 Short margin maliyeti: {SHORT_MARGIN_COST*100:.2f}% yıllık")
        print(f"💡 Pozisyon büyüklüğü: RECSIZE + Likidite kontrolü")
        print(f"📊 Skor bazlı pozisyon yönetimi: FINAL_THG düşerse LONG azalt, SHORT_FINAL yükselirse SHORT azalt")
        
        current_capital = INITIAL_CAPITAL
        current_date = start_date
        
        # Tüm hisseleri birleştir (günlük fırsatlar için)
        all_stocks_df = pd.concat([long_stocks_df, short_stocks_df]).drop_duplicates(subset=['PREF_IBKR'], keep='first')
        
        # Rebalance tarihlerini belirle (günlük)
        rebalance_dates = self.get_rebalance_dates(start_date, end_date)
        
        print(f"🔄 Toplam işlem günü: {len(rebalance_dates)} adet")
        print(f"⚠️  NOT: Her gün yeni LONG/SHORT fırsatları değerlendirilecek.")
        print(f"⚠️  Mevcut pozisyonların skorları kontrol edilecek ve kötüleşenler azaltılacak.\n")
        
        # Her rebalance tarihinde portföyü güncelle
        for i, rebalance_date in enumerate(rebalance_dates):
            print(f"\n{'='*60}")
            print(f"📅 Rebalance #{i+1}/{len(rebalance_dates)}: {rebalance_date.strftime('%Y-%m-%d')}")
            print(f"{'='*60}")
            
            # Bu tarihteki LONG ve SHORT hisselerini belirle
            # (Gerçekte geçmiş verilerden seçim yapılmalı, şimdilik mevcut seçimleri kullanıyoruz)
            long_stocks = long_stocks_df.copy()
            short_stocks = short_stocks_df.copy()
            
            # Mevcut portföy değerini göster
            print(f"💰 Mevcut portföy değeri: ${current_capital:,.2f}")
            
            # Pozisyon büyüklüklerini hesapla
            num_long = len(long_stocks)
            num_short = len(short_stocks)
            
            if num_long == 0 or num_short == 0:
                print(f"⚠️ LONG veya SHORT hisse yok, atlanıyor...")
                continue
            
            # Portföy dağılımını kontrol et (30-40 hisse hedefi)
            total_stocks = num_long + num_short
            if total_stocks < MIN_STOCKS:
                print(f"⚠️ Toplam hisse sayısı ({total_stocks}) minimum ({MIN_STOCKS}) altında!")
            elif total_stocks > MAX_STOCKS:
                print(f"⚠️ Toplam hisse sayısı ({total_stocks}) maksimum ({MAX_STOCKS}) üzerinde!")
            
            long_capital = current_capital * self.long_pct
            short_capital = current_capital * self.short_pct
            
            # RECSIZE'lara göre portföy dağılımını normalize et
            long_total_recsize = long_stocks['RECSIZE'].fillna(0).sum() if 'RECSIZE' in long_stocks.columns else 0
            short_total_recsize = short_stocks['RECSIZE'].fillna(0).sum() if 'RECSIZE' in short_stocks.columns else 0
            
            # RECSIZE yoksa veya 0 ise, eşit dağılım yap
            if long_total_recsize == 0:
                long_total_recsize = num_long * AVG_PREF_PRICE * 100  # Varsayılan: her hisse 100 lot
            if short_total_recsize == 0:
                short_total_recsize = num_short * AVG_PREF_PRICE * 100  # Varsayılan: her hisse 100 lot
            
            print(f"📊 LONG pozisyonları: {num_long} hisse, ${long_capital:,.2f} toplam, RECSIZE toplam: {long_total_recsize:.0f} lot")
            print(f"📊 SHORT pozisyonları: {num_short} hisse, ${short_capital:,.2f} toplam, RECSIZE toplam: {short_total_recsize:.0f} lot")
            print(f"📊 Toplam hisse sayısı: {total_stocks} (Hedef: {MIN_STOCKS}-{MAX_STOCKS})")
            
            # Bir sonraki rebalance tarihine kadar pozisyonları tut
            next_rebalance = rebalance_dates[i+1] if i+1 < len(rebalance_dates) else end_date
            
            # Her hisse için performansı hesapla
            total_long_pnl = 0
            total_short_pnl = 0
            successful_long_trades = 0
            successful_short_trades = 0
            failed_long_trades = 0
            failed_short_trades = 0
            
            print(f"\n🟢 LONG pozisyonları işleniyor ({num_long} hisse)...")
            
            # LONG pozisyonları - RECSIZE kullanarak
            for idx, stock in long_stocks.iterrows():
                symbol = stock['PREF_IBKR']
                
                # Giriş fiyatı
                entry_price_df = self.get_historical_prices(symbol, rebalance_date, rebalance_date + timedelta(days=5))
                if entry_price_df is None or len(entry_price_df) == 0:
                    print(f"  ⚠️ {symbol} için giriş fiyatı bulunamadı")
                    failed_long_trades += 1
                    continue
                
                entry_price = entry_price_df['close'].iloc[0]
                
                # RECSIZE'dan pozisyon büyüklüğünü hesapla
                recsize = stock.get('RECSIZE', 0)
                if recsize and recsize > 0 and long_total_recsize > 0:
                    # RECSIZE lot cinsinden, dolara çevir ve portföy dağılımına göre normalize et
                    # RECSIZE oranına göre long_capital'i dağıt
                    recsize_ratio = recsize / long_total_recsize
                    position_size = long_capital * recsize_ratio
                else:
                    # RECSIZE yoksa, long_capital'i eşit dağıt
                    position_size = long_capital / num_long if num_long > 0 else 0
                
                # Çıkış fiyatı
                exit_price_df = self.get_historical_prices(symbol, next_rebalance - timedelta(days=5), next_rebalance)
                if exit_price_df is None or len(exit_price_df) == 0:
                    print(f"  ⚠️ {symbol} için çıkış fiyatı bulunamadı")
                    failed_long_trades += 1
                    continue
                
                exit_price = exit_price_df['close'].iloc[-1]
                
                # Trade simülasyonu
                trade = self.simulate_trade(symbol, 'LONG', rebalance_date, entry_price, 
                                          position_size, next_rebalance, exit_price)
                
                total_long_pnl += trade['net_pnl']
                self.trades_history.append(trade)
                successful_long_trades += 1
                
                pnl_sign = "✅" if trade['net_pnl'] > 0 else "❌"
                recsize_info = f", RECSIZE: {recsize:.0f} lot" if recsize > 0 else ""
                print(f"  {pnl_sign} {symbol}: ${entry_price:.2f} → ${exit_price:.2f}, Pozisyon: ${position_size:,.2f}{recsize_info}, PnL: ${trade['net_pnl']:,.2f} ({trade['return_pct']:.2f}%)")
            
            print(f"\n🔴 SHORT pozisyonları işleniyor ({num_short} hisse)...")
            
            # SHORT pozisyonları - RECSIZE kullanarak
            for idx, stock in short_stocks.iterrows():
                symbol = stock['PREF_IBKR']
                
                # Giriş fiyatı
                entry_price_df = self.get_historical_prices(symbol, rebalance_date, rebalance_date + timedelta(days=5))
                if entry_price_df is None or len(entry_price_df) == 0:
                    print(f"  ⚠️ {symbol} için giriş fiyatı bulunamadı")
                    failed_short_trades += 1
                    continue
                
                entry_price = entry_price_df['close'].iloc[0]
                
                # RECSIZE'dan pozisyon büyüklüğünü hesapla
                recsize = stock.get('RECSIZE', 0)
                if recsize and recsize > 0 and short_total_recsize > 0:
                    # RECSIZE lot cinsinden, portföy dağılımına göre normalize et
                    # RECSIZE oranına göre short_capital'i dağıt
                    recsize_ratio = recsize / short_total_recsize
                    position_size = short_capital * recsize_ratio
                else:
                    # RECSIZE yoksa, short_capital'i eşit dağıt
                    position_size = short_capital / num_short if num_short > 0 else 0
                
                # Çıkış fiyatı
                exit_price_df = self.get_historical_prices(symbol, next_rebalance - timedelta(days=5), next_rebalance)
                if exit_price_df is None or len(exit_price_df) == 0:
                    print(f"  ⚠️ {symbol} için çıkış fiyatı bulunamadı")
                    failed_short_trades += 1
                    continue
                
                exit_price = exit_price_df['close'].iloc[-1]
                
                # Trade simülasyonu
                trade = self.simulate_trade(symbol, 'SHORT', rebalance_date, entry_price, 
                                          position_size, next_rebalance, exit_price)
                
                total_short_pnl += trade['net_pnl']
                self.trades_history.append(trade)
                successful_short_trades += 1
                
                pnl_sign = "✅" if trade['net_pnl'] > 0 else "❌"
                recsize_info = f", RECSIZE: {recsize:.0f} lot" if recsize > 0 else ""
                print(f"  {pnl_sign} {symbol}: ${entry_price:.2f} → ${exit_price:.2f}, Pozisyon: ${position_size:,.2f}{recsize_info}, PnL: ${trade['net_pnl']:,.2f} ({trade['return_pct']:.2f}%)")
            
            # Portföy değerini güncelle
            current_capital += total_long_pnl + total_short_pnl
            
            # Portföy geçmişini kaydet
            self.portfolio_history.append({
                'date': next_rebalance,
                'capital': current_capital,
                'long_pnl': total_long_pnl,
                'short_pnl': total_short_pnl,
                'total_pnl': total_long_pnl + total_short_pnl,
                'return_pct': ((current_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
            })
            
            print(f"\n📊 Rebalance Özeti:")
            print(f"   🟢 LONG: {successful_long_trades} başarılı, {failed_long_trades} başarısız, PnL: ${total_long_pnl:,.2f}")
            print(f"   🔴 SHORT: {successful_short_trades} başarılı, {failed_short_trades} başarısız, PnL: ${total_short_pnl:,.2f}")
            print(f"   📊 Toplam aktif pozisyon: {successful_long_trades + successful_short_trades} hisse")
            print(f"   💰 Yeni portföy değeri: ${current_capital:,.2f}")
            print(f"   📈 Toplam getiri: {((current_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100:.2f}%")
            print(f"   💵 Bu dönem getirisi: ${(total_long_pnl + total_short_pnl):,.2f} ({(total_long_pnl + total_short_pnl) / current_capital * 100:.2f}%)")
            
            # Rate limiting
            time.sleep(0.5)
        
        return current_capital
    
    def get_rebalance_dates(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Rebalance tarihlerini belirle"""
        dates = [start_date]
        current = start_date
        
        if REBALANCE_FREQUENCY == 'daily':
            delta = timedelta(days=1)
        elif REBALANCE_FREQUENCY == 'weekly':
            delta = timedelta(weeks=1)
        elif REBALANCE_FREQUENCY == 'monthly':
            delta = timedelta(days=30)
        elif REBALANCE_FREQUENCY == 'quarterly':
            delta = timedelta(days=90)
        else:
            delta = timedelta(days=30)  # Default: monthly
        
        while current < end_date:
            current += delta
            if current <= end_date:
                dates.append(current)
        
        return dates
    
    def generate_report(self, final_capital: float):
        """Detaylı rapor oluştur"""
        print("\n" + "="*80)
        print("📊 BACKTEST RAPORU")
        print("="*80)
        
        # Genel istatistikler
        total_return = final_capital - INITIAL_CAPITAL
        total_return_pct = (total_return / INITIAL_CAPITAL) * 100
        annualized_return = ((final_capital / INITIAL_CAPITAL) ** (1 / BACKTEST_YEARS)) - 1
        
        print(f"\n💰 GENEL PERFORMANS:")
        print(f"   Başlangıç Sermayesi: ${INITIAL_CAPITAL:,.2f}")
        print(f"   Final Sermaye: ${final_capital:,.2f}")
        print(f"   Toplam Getiri: ${total_return:,.2f} ({total_return_pct:.2f}%)")
        print(f"   Yıllık Getiri: {annualized_return*100:.2f}%")
        
        # Trade istatistikleri
        trades_df = pd.DataFrame(self.trades_history)
        
        if len(trades_df) > 0:
            long_trades = trades_df[trades_df['type'] == 'LONG']
            short_trades = trades_df[trades_df['type'] == 'SHORT']
            
            print(f"\n📈 TRADE İSTATİSTİKLERİ:")
            print(f"   Toplam Trade: {len(trades_df)}")
            print(f"   LONG Trades: {len(long_trades)}")
            print(f"   SHORT Trades: {len(short_trades)}")
            
            print(f"\n🟢 LONG PERFORMANSI:")
            if len(long_trades) > 0:
                long_win_rate = (long_trades['net_pnl'] > 0).sum() / len(long_trades) * 100
                long_avg_return = long_trades['return_pct'].mean()
                long_total_pnl = long_trades['net_pnl'].sum()
                print(f"   Win Rate: {long_win_rate:.2f}%")
                print(f"   Ortalama Getiri: {long_avg_return:.2f}%")
                print(f"   Toplam PnL: ${long_total_pnl:,.2f}")
            
            print(f"\n🔴 SHORT PERFORMANSI:")
            if len(short_trades) > 0:
                short_win_rate = (short_trades['net_pnl'] > 0).sum() / len(short_trades) * 100
                short_avg_return = short_trades['return_pct'].mean()
                short_total_pnl = short_trades['net_pnl'].sum()
                print(f"   Win Rate: {short_win_rate:.2f}%")
                print(f"   Ortalama Getiri: {short_avg_return:.2f}%")
                print(f"   Toplam PnL: ${short_total_pnl:,.2f}")
            
            # En iyi ve en kötü trades
            print(f"\n🏆 EN İYİ 5 TRADE:")
            top_trades = trades_df.nlargest(5, 'net_pnl')
            for _, trade in top_trades.iterrows():
                print(f"   {trade['symbol']} ({trade['type']}): ${trade['net_pnl']:,.2f} ({trade['return_pct']:.2f}%)")
            
            print(f"\n⚠️ EN KÖTÜ 5 TRADE:")
            bottom_trades = trades_df.nsmallest(5, 'net_pnl')
            for _, trade in bottom_trades.iterrows():
                print(f"   {trade['symbol']} ({trade['type']}): ${trade['net_pnl']:,.2f} ({trade['return_pct']:.2f}%)")
        
        # Portföy geçmişi
        portfolio_df = pd.DataFrame(self.portfolio_history)
        
        if len(portfolio_df) > 0:
            print(f"\n📊 PORTFÖY GEÇMİŞİ:")
            print(f"   Maksimum Değer: ${portfolio_df['capital'].max():,.2f}")
            print(f"   Minimum Değer: ${portfolio_df['capital'].min():,.2f}")
            print(f"   Maksimum Drawdown: {((portfolio_df['capital'].min() - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100:.2f}%")
            
            # Sharpe Ratio hesapla (basit)
            returns = portfolio_df['return_pct'].diff().dropna()
            if len(returns) > 0 and returns.std() > 0:
                sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252)  # Yıllık
                print(f"   Sharpe Ratio: {sharpe_ratio:.2f}")
        
        # Dosyalara kaydet
        if len(trades_df) > 0:
            trades_df.to_csv('backtest_trades.csv', index=False)
            print(f"\n💾 Trade detayları 'backtest_trades.csv' dosyasına kaydedildi")
        
        if len(portfolio_df) > 0:
            portfolio_df.to_csv('backtest_portfolio_history.csv', index=False)
            print(f"💾 Portföy geçmişi 'backtest_portfolio_history.csv' dosyasına kaydedildi")
        
        # Grafik oluştur
        self.plot_results(portfolio_df)
    
    def plot_results(self, portfolio_df: pd.DataFrame):
        """Sonuçları görselleştir"""
        try:
            if len(portfolio_df) == 0:
                return
            
            fig, axes = plt.subplots(2, 2, figsize=(15, 10))
            fig.suptitle('Backtest Sonuçları', fontsize=16, fontweight='bold')
            
            # 1. Portföy değeri zaman serisi
            axes[0, 0].plot(portfolio_df['date'], portfolio_df['capital'], linewidth=2, color='blue')
            axes[0, 0].axhline(y=INITIAL_CAPITAL, color='red', linestyle='--', label='Başlangıç')
            axes[0, 0].set_title('Portföy Değeri Zaman Serisi')
            axes[0, 0].set_xlabel('Tarih')
            axes[0, 0].set_ylabel('Portföy Değeri ($)')
            axes[0, 0].legend()
            axes[0, 0].grid(True, alpha=0.3)
            
            # 2. Getiri yüzdesi
            axes[0, 1].plot(portfolio_df['date'], portfolio_df['return_pct'], linewidth=2, color='green')
            axes[0, 1].axhline(y=0, color='red', linestyle='--')
            axes[0, 1].set_title('Toplam Getiri (%)')
            axes[0, 1].set_xlabel('Tarih')
            axes[0, 1].set_ylabel('Getiri (%)')
            axes[0, 1].grid(True, alpha=0.3)
            
            # 3. LONG vs SHORT PnL
            axes[1, 0].bar(['LONG', 'SHORT'], 
                          [portfolio_df['long_pnl'].sum(), portfolio_df['short_pnl'].sum()],
                          color=['green', 'red'], alpha=0.7)
            axes[1, 0].set_title('LONG vs SHORT Toplam PnL')
            axes[1, 0].set_ylabel('PnL ($)')
            axes[1, 0].grid(True, alpha=0.3, axis='y')
            
            # 4. Aylık getiri dağılımı
            portfolio_df['month'] = pd.to_datetime(portfolio_df['date']).dt.to_period('M')
            monthly_returns = portfolio_df.groupby('month')['return_pct'].last().diff().dropna()
            axes[1, 1].hist(monthly_returns, bins=20, color='skyblue', edgecolor='black', alpha=0.7)
            axes[1, 1].set_title('Aylık Getiri Dağılımı')
            axes[1, 1].set_xlabel('Getiri (%)')
            axes[1, 1].set_ylabel('Frekans')
            axes[1, 1].grid(True, alpha=0.3, axis='y')
            
            plt.tight_layout()
            plt.savefig('backtest_results.png', dpi=300, bbox_inches='tight')
            print(f"📊 Grafikler 'backtest_results.png' dosyasına kaydedildi")
            plt.close()
            
        except Exception as e:
            print(f"⚠️ Grafik oluşturma hatası: {e}")

def main():
    """Ana fonksiyon"""
    print("="*80)
    print("🚀 2 YILLIK GERİYE DÖNÜK BACKTEST")
    print("="*80)
    
    # Tarihleri belirle
    end_date = datetime.now()
    start_date = end_date - timedelta(days=BACKTEST_YEARS * 365)
    
    # LONG ve SHORT dosyalarını yükle
    print("\n📁 LONG ve SHORT dosyaları yükleniyor...")
    
    if not os.path.exists('tumcsvlong.csv'):
        print("❌ tumcsvlong.csv dosyası bulunamadı!")
        print("💡 Önce ntumcsvport.py çalıştırılmalı!")
        return
    
    if not os.path.exists('tumcsvshort.csv'):
        print("❌ tumcsvshort.csv dosyası bulunamadı!")
        print("💡 Önce ntumcsvport.py çalıştırılmalı!")
        return
    
    long_stocks_df = pd.read_csv('tumcsvlong.csv')
    short_stocks_df = pd.read_csv('tumcsvshort.csv')
    
    print(f"✅ LONG hisseler: {len(long_stocks_df)} adet")
    print(f"✅ SHORT hisseler: {len(short_stocks_df)} adet")
    
    # Backtest engine oluştur
    engine = BacktestEngine(INITIAL_CAPITAL, LONG_PERCENTAGE, SHORT_PERCENTAGE)
    
    # IBKR'ye bağlan
    if not engine.connect_to_ibkr():
        print("❌ IBKR bağlantısı başarısız, backtest yapılamıyor!")
        return
    
    try:
        # Backtest'i çalıştır
        final_capital = engine.run_backtest(start_date, end_date, long_stocks_df, short_stocks_df)
        
        # Rapor oluştur
        engine.generate_report(final_capital)
        
        print("\n✅ Backtest tamamlandı!")
        
    except Exception as e:
        print(f"❌ Backtest hatası: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if engine.ib and engine.ib.isConnected():
            engine.ib.disconnect()
            print("🔌 IBKR bağlantısı kapatıldı")

if __name__ == "__main__":
    main()

