import threading
import time
import pandas as pd
from datetime import datetime

class PSFAlgo1Orders:
    """PSFAlgo1 Emir yönetimi ve Fill işlemleri"""
    
    def check_befday_limits(self, ticker, side, quantity):
        """BEFDAY günlük pozisyon limitlerini kontrol et"""
        if ticker not in self.daily_position_limits:
            return True, "BEFDAY limitinde değil"
        
        min_limit, max_limit = self.daily_position_limits[ticker]
        current_pos = self.get_position_size(ticker)
        
        # Yeni pozisyon hesapla
        if side.lower() in ['buy', 'long']:
            new_pos = current_pos + quantity
        else:
            new_pos = current_pos - quantity
        
        # Limit kontrolü
        if new_pos < min_limit:
            return False, f"BEFDAY min limit aşılır: {new_pos} < {min_limit}"
        elif new_pos > max_limit:
            return False, f"BEFDAY max limit aşılır: {new_pos} > {max_limit}"
        else:
            return True, f"BEFDAY limit OK: {new_pos} [{min_limit}, {max_limit}]"

    def check_maxalw_limits(self, ticker, side, quantity):
        """MAXALW günlük işlem limitlerini kontrol et"""
        try:
            # MAXALW.csv dosyasından limitleri oku
            df = pd.read_csv('MAXALW.csv')
            row = df[df['PREF IBKR'] == ticker]
            
            if row.empty:
                return True, "MAXALW limitinde değil"
            
            max_daily_size = int(row.iloc[0]['Max Daily Size'])
            
            # Günlük toplam işlem miktarını hesapla
            daily_total = self.get_daily_fill_total(ticker, 'both')
            
            # Yeni işlemle birlikte toplam
            new_total = daily_total + quantity
            
            if new_total > max_daily_size:
                return False, f"MAXALW günlük limit aşılır: {new_total} > {max_daily_size}"
            else:
                return True, f"MAXALW limit OK: {new_total}/{max_daily_size}"
                
        except FileNotFoundError:
            return True, "MAXALW.csv bulunamadı"
        except Exception as e:
            print(f"[MAXALW] Kontrol hatası: {e}")
            return True, "MAXALW kontrol hatası"

    def get_maxalw_size(self, ticker):
        """Ticker için MAXALW günlük limitini döndür"""
        try:
            df = pd.read_csv('MAXALW.csv')
            row = df[df['PREF IBKR'] == ticker]
            
            if not row.empty:
                return int(row.iloc[0]['Max Daily Size'])
            else:
                return None
                
        except Exception:
            return None

    def get_pending_orders_for_ticker(self, ticker):
        """Ticker için bekleyen emirleri döndür"""
        try:
            if not hasattr(self.market_data, 'ib') or not self.market_data.ib:
                return []
            
            trades = self.market_data.ib.openTrades()
            pending_orders = []
            
            for trade in trades:
                if trade.contract.symbol == ticker:
                    pending_orders.append({
                        'action': trade.order.action,
                        'quantity': trade.order.totalQuantity,
                        'price': trade.order.lmtPrice,
                        'order_type': trade.order.orderType
                    })
            
            return pending_orders
            
        except Exception as e:
            print(f"[PENDING ORDERS] {ticker} kontrol hatası: {e}")
            return []

    def on_fill(self, ticker, side, price, size, **kwargs):
        """Fill geldiğinde pozisyon yönetimi ve reverse order kontrolü yapar."""
        
        # ✅ PSFAlgo aktif değilse hiçbir şey yapma
        if not self.is_active:
            print(f"[PSFAlgo1] ⏸️ PSFAlgo1 pasif - {ticker} fill işlenmedi")
            return
            
        # ✅ EXCLUDE LIST kontrolü - fill'ler de ignore edilmeli
        if ticker in self.exclude_list:
            print(f"[PSFAlgo1 EXCLUDE] ❌ {ticker} exclude listesinde - fill işlenmedi")
            return
            
        print(f"[FILL] {ticker} fill alındı: {side} {size} lot @ {price}")
        
        # Side parametresini normalize et
        if side.upper() in ['BUY', 'BOT']:
            normalized_side = 'long'
        elif side.upper() in ['SELL', 'SLD']:
            normalized_side = 'short'
        else:
            normalized_side = side.lower()
        
        # ✅ MEVCUT POZİSYON BİLGİSİNİ AL
        current_position = self.get_position_size(ticker)
        
        # ✅ SNAPSHOT TABALLI BDATA GÜNCELLEMESİ
        try:
            benchmark_at_fill = self.calculate_benchmark_at_fill(ticker)
            
            self.bdata_storage.add_fill_record(
                ticker=ticker,
                side=normalized_side,
                size=size,
                price=price,
                timestamp=datetime.now(),
                current_position=current_position,
                benchmark_at_fill=benchmark_at_fill,
                pisdongu_cycle=self.pisdongu_cycle_count,
                chain_state=self.chain_state
            )
            
        except Exception as e:
            print(f"[BDATA] {ticker} snapshot kayıt hatası: {e}")
        
        # ✅ GÜNLÜK FILL TAKİBİ
        self.update_daily_fills(ticker, normalized_side, size)
        
        # ✅ REVERSE ORDER KONTROLÜ
        try:
            # Pozisyon tersine çevrildi mi?
            old_sign = 1 if current_position > 0 else (-1 if current_position < 0 else 0)
            
            if normalized_side == 'long':
                new_position = current_position + size
            else:
                new_position = current_position - size
            
            new_sign = 1 if new_position > 0 else (-1 if new_position < 0 else 0)
            
            # Pozisyon işareti değişti ve sıfırdan geçti
            if old_sign != 0 and new_sign != 0 and old_sign != new_sign:
                reverse_size = abs(new_position)
                print(f"[REVERSE ORDER] 🔄 {ticker} pozisyon tersine çevrildi: {current_position} → {new_position}")
                
                # Reverse order aç
                self.open_reverse_order(ticker, normalized_side, reverse_size, price)
                
        except Exception as e:
            print(f"[REVERSE ORDER] {ticker} kontrol hatası: {e}")

    def update_daily_fills(self, ticker, side, size):
        """Günlük fill istatistiklerini güncelle"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today not in self.daily_fills:
            self.daily_fills[today] = {}
        
        if ticker not in self.daily_fills[today]:
            self.daily_fills[today][ticker] = {'long': 0, 'short': 0}
        
        self.daily_fills[today][ticker][side] += size
        
        print(f"[DAILY FILLS] {ticker} günlük: Long={self.daily_fills[today][ticker]['long']}, Short={self.daily_fills[today][ticker]['short']}")

    def get_daily_fill_total(self, ticker, side):
        """Günlük fill toplamını döndür"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today not in self.daily_fills or ticker not in self.daily_fills[today]:
            return 0
        
        if side == 'both':
            return self.daily_fills[today][ticker]['long'] + self.daily_fills[today][ticker]['short']
        else:
            return self.daily_fills[today][ticker].get(side, 0)

    def get_daily_reverse_orders(self, ticker):
        """Günlük reverse order sayısını döndür"""
        today = datetime.now().strftime('%Y-%m-%d')
        return self.daily_reverse_orders.get(today, {}).get(ticker, 0)

    def update_daily_reverse_orders(self, ticker, size):
        """Günlük reverse order istatistiklerini güncelle"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today not in self.daily_reverse_orders:
            self.daily_reverse_orders[today] = {}
        
        if ticker not in self.daily_reverse_orders[today]:
            self.daily_reverse_orders[today][ticker] = 0
        
        self.daily_reverse_orders[today][ticker] += size

    def open_reverse_order(self, ticker, side, size, fill_price):
        """Reverse order aç"""
        print(f"[REVERSE ORDER] 🔄 {ticker} için reverse order açılıyor: {side} {size} lot")
        
        try:
            # Günlük reverse order limitini kontrol et
            daily_reverse = self.get_daily_reverse_orders(ticker)
            max_daily_reverse = 1000  # Günlük max reverse order limiti
            
            if daily_reverse + size > max_daily_reverse:
                print(f"[REVERSE ORDER] ❌ {ticker} günlük reverse limit aşılır: {daily_reverse + size} > {max_daily_reverse}")
                return
            
            # Reverse order fiyatını hesapla (fill fiyatının %0.1 üstü/altı)
            if side == 'long':
                # Long reverse order - fill fiyatının %0.1 altında bid
                reverse_price = fill_price * 0.999
                reverse_side = 'SELL'
            else:
                # Short reverse order - fill fiyatının %0.1 üstünde ask
                reverse_price = fill_price * 1.001
                reverse_side = 'BUY'
            
            # Lot büyüklüğünü 200'lük parçalara böl
            chunks = self._split_lot_to_chunks(size, 200)
            
            for chunk_size in chunks:
                # BEFDAY limit kontrolü
                befday_ok, befday_msg = self.check_befday_limits(ticker, reverse_side.lower(), chunk_size)
                if not befday_ok:
                    print(f"[REVERSE ORDER] ❌ {ticker} BEFDAY limit: {befday_msg}")
                    continue
                
                # MAXALW limit kontrolü
                maxalw_ok, maxalw_msg = self.check_maxalw_limits(ticker, reverse_side.lower(), chunk_size)
                if not maxalw_ok:
                    print(f"[REVERSE ORDER] ❌ {ticker} MAXALW limit: {maxalw_msg}")
                    continue
                
                # Emir gönder
                print(f"[REVERSE ORDER] 📤 {ticker} reverse order: {reverse_side} {chunk_size} @ {reverse_price:.3f}")
                
                # Gerçek emir gönderimi (simülasyon için commented)
                # self.send_order(ticker, reverse_price, 0, reverse_side.lower(), chunk_size)
                
                # İstatistik güncelle
                self.update_daily_reverse_orders(ticker, chunk_size)
            
        except Exception as e:
            print(f"[REVERSE ORDER] ❌ {ticker} reverse order hatası: {e}")

    def get_position_size(self, ticker):
        """Ticker için mevcut pozisyon büyüklüğünü döndür"""
        try:
            position = self.get_position(ticker)
            return position['size'] if position else 0
        except:
            return 0

    def send_order(self, ticker, price, final_thg, side, size=200):
        """Emir gönder"""
        if not self.is_active:
            print(f"[ORDER] ⏸️ PSFAlgo1 pasif - {ticker} emri gönderilmedi")
            return False
        
        # Exclude list kontrolü
        if ticker in self.exclude_list:
            print(f"[ORDER EXCLUDE] ❌ {ticker} exclude listesinde - emir gönderilmedi")
            return False
        
        print(f"[ORDER] 📤 {ticker} emir hazırlanıyor: {side.upper()} {size} @ {price:.3f}")
        
        try:
            # BEFDAY limit kontrolü
            befday_ok, befday_msg = self.check_befday_limits(ticker, side, size)
            if not befday_ok:
                print(f"[ORDER] ❌ {ticker} BEFDAY limit: {befday_msg}")
                return False
            
            # MAXALW limit kontrolü
            maxalw_ok, maxalw_msg = self.check_maxalw_limits(ticker, side, size)
            if not maxalw_ok:
                print(f"[ORDER] ❌ {ticker} MAXALW limit: {maxalw_msg}")
                return False
            
            # Mevcut pozisyon kontrolü
            current_pos = self.get_position_size(ticker)
            order_type = self._get_order_type(side, current_pos)
            
            print(f"[ORDER] ✅ {ticker} emir gönderiliyor: {order_type} {side.upper()} {size} @ {price:.3f}")
            print(f"[ORDER] 📊 {ticker} mevcut pozisyon: {current_pos}, BEFDAY: {befday_msg}, MAXALW: {maxalw_msg}")
            
            # Gerçek emir gönderimi (market_data üzerinden)
            if hasattr(self.market_data, 'send_order'):
                result = self.market_data.send_order(
                    symbol=ticker,
                    action=side.upper(),
                    quantity=size,
                    price=price,
                    order_type=order_type
                )
                return result
            else:
                print(f"[ORDER] ⚠️ market_data.send_order mevcut değil - simülasyon modu")
                return True
                
        except Exception as e:
            print(f"[ORDER] ❌ {ticker} emir gönderim hatası: {e}")
            return False

    def get_smi_rate(self, ticker):
        """SMI oranını hesapla"""
        try:
            current_price = self.get_current_price(ticker)
            if not current_price:
                return 0
            
            # Basit SMI hesaplama (gerçek implementasyon daha karmaşık olabilir)
            return current_price * 0.001  # %0.1 SMI
            
        except Exception:
            return 0

    def _get_order_type(self, side, current_position):
        """Pozisyon durumuna göre emir tipini belirle"""
        if current_position == 0:
            return "MKT"  # Pozisyon yoksa market order
        elif (side.lower() == 'buy' and current_position < 0) or (side.lower() == 'sell' and current_position > 0):
            return "MKT"  # Pozisyon kapatma - market order
        else:
            return "LMT"  # Pozisyon artırma - limit order

    def _is_number(self, val):
        """Değerin sayı olup olmadığını kontrol et"""
        try:
            float(val)
            return True
        except (ValueError, TypeError):
            return False

    def _split_lot_to_chunks(self, total_lot, chunk_size=200):
        """Toplam lot'u parçalara böl"""
        chunks = []
        remaining = total_lot
        
        while remaining > 0:
            chunk = min(remaining, chunk_size)
            chunks.append(chunk)
            remaining -= chunk
        
        return chunks

    def get_current_price(self, ticker):
        """Mevcut fiyatı al"""
        try:
            # Önce market_data'dan fiyatı çek
            if hasattr(self.market_data, 'last_data') and self.market_data.last_data:
                # Polygon ticker formatına çevir
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.market_data.last_data:
                    data = self.market_data.last_data[poly_ticker]
                    if 'last' in data and data['last']:
                        price = float(data['last'])
                        if price > 0:
                            return price
                    elif 'close' in data and data['close']:
                        price = float(data['close'])
                        if price > 0:
                            return price
            
            # Fallback: scored_stocks.csv'den last price çek
            if hasattr(self, 'scores_df') and not self.scores_df.empty:
                if ticker in self.scores_df.index:
                    row = self.scores_df.loc[ticker]
                    if 'last_price' in row:
                        price = float(row['last_price'])
                        if price > 0:
                            return price
            
            # Son çare: 0 döndür (None değil)
            print(f"[GET CURRENT PRICE] ⚠️ {ticker} için fiyat alınamadı, 0 döndürülüyor")
            return 0.0
            
        except Exception as e:
            print(f"[GET CURRENT PRICE] ❌ {ticker} fiyat alma hatası: {e}")
            return 0.0

    def check_and_prevent_position_reversal(self):
        """Pozisyon tersine çevirme kontrolü başlat"""
        def position_control_loop():
            while True:
                try:
                    if self.is_active:
                        threading.Thread(target=self._position_control_main_thread, daemon=True).start()
                    time.sleep(30)  # 30 saniyede bir kontrol
                except Exception as e:
                    print(f"[POSITION CONTROL] Kontrol döngüsü hatası: {e}")
                    time.sleep(60)
        
        threading.Thread(target=position_control_loop, daemon=True).start()

    def _position_control_main_thread(self):
        """Ana thread'de pozisyon kontrolü"""
        try:
            if not hasattr(self.market_data, 'ib') or not self.market_data.ib:
                return
            
            positions = self.market_data.ib.positions()
            
            for position in positions:
                ticker = position.contract.symbol
                current_size = position.position
                
                # Sadece aktif pozisyonları kontrol et
                if abs(current_size) < 10:
                    continue
                
                # BEFDAY başlangıç pozisyonu ile karşılaştır
                if ticker in self.befday_positions:
                    starting_pos = self.befday_positions[ticker]
                    
                    # Pozisyon işareti değişti mi?
                    if (starting_pos > 0 and current_size < 0) or (starting_pos < 0 and current_size > 0):
                        print(f"[POSITION REVERSAL] 🚨 {ticker} pozisyon tersine çevrildi: {starting_pos} → {current_size}")
                        
                        # Uyarı ver ama otomatik işlem yapma
                        # Kullanıcı müdahalesi gerekebilir
                        
        except Exception as e:
            print(f"[POSITION CONTROL] Kontrol hatası: {e}")

    def manual_fill_check(self):
        """Manuel fill kontrolü"""
        print("[MANUAL FILL CHECK] 🔍 IBKR'den fill'ler kontrol ediliyor...")
        
        try:
            if not hasattr(self.market_data, 'get_recent_fills'):
                print("[MANUAL FILL CHECK] ⚠️ Market data'da get_recent_fills yok")
                return
            
            recent_fills = self.market_data.get_recent_fills()
            
            for fill in recent_fills:
                ticker = fill.get('symbol', '')
                side = fill.get('side', '')
                price = fill.get('price', 0)
                size = fill.get('size', 0)
                
                if ticker and side and price and size:
                    print(f"[MANUAL FILL CHECK] 📊 {ticker}: {side} {size} @ {price}")
                    self.on_fill(ticker, side, price, size)
                    
        except Exception as e:
            print(f"[MANUAL FILL CHECK] ❌ Kontrol hatası: {e}")

    def start_auto_fill_check(self):
        """Otomatik fill kontrolü başlat"""
        def auto_check():
            while True:
                try:
                    if self.is_active:
                        self.manual_fill_check()
                    time.sleep(60)  # 1 dakikada bir kontrol
                except Exception as e:
                    print(f"[AUTO FILL CHECK] Kontrol hatası: {e}")
                    time.sleep(120)
        
        threading.Thread(target=auto_check, daemon=True).start() 