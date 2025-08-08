import pandas as pd
from Ptahaf.utils.reasoning_logger import log_reasoning
import math

class PSFAlgo1Utils:
    """PSFAlgo1 Yardımcı fonksiyonlar ve hesaplamalar"""
    
    # Helper fonksiyonlar
    def get_long_positions(self):
        """Mevcut long pozisyonları döndür"""
        if hasattr(self.market_data, 'get_positions'):
            positions = self.market_data.get_positions()
            return [pos for pos in positions if pos['quantity'] > 0]
        return []

    def get_short_positions(self):
        """Mevcut short pozisyonları döndür"""
        if hasattr(self.market_data, 'get_positions'):
            positions = self.market_data.get_positions()
            return [pos for pos in positions if pos['quantity'] < 0]
        return []

    def get_ask_sell_score(self, ticker):
        """Ask sell pahalilik skorunu al"""
        try:
            df = pd.read_csv('mastermind_histport.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['Ask sell pahalilik skoru'])
        except Exception:
            pass
        return 0.0

    def get_front_sell_score(self, ticker):
        """Front sell pahalilik skorunu al"""
        try:
            df = pd.read_csv('mastermind_histport.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['Front sell pahalilik skoru'])
        except Exception:
            pass
        return 0.0

    def get_bid_buy_score(self, ticker):
        """Bid buy ucuzluk skorunu al"""
        try:
            df = pd.read_csv('mastermind_histport.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['Bid buy Ucuzluk skoru'])
        except Exception:
            pass
        return 0.0

    def get_front_buy_score(self, ticker):
        """Front buy ucuzluk skorunu al"""
        try:
            df = pd.read_csv('mastermind_histport.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['Front buy ucuzluk skoru'])
        except Exception:
            pass
        return 0.0

    def get_t_top_losers(self):
        """T-top losers listesini döndür (GUI veya veri kaynağından)."""
        if hasattr(self.market_data, 'get_t_top_losers'):
            return self.market_data.get_t_top_losers()
        return []

    def get_t_top_gainers(self):
        """T-top gainers listesini döndür (GUI veya veri kaynağından)."""
        if hasattr(self.market_data, 'get_t_top_gainers'):
            return self.market_data.get_t_top_gainers()
        return []

    def get_scores_for_ticker(self, ticker):
        # scored_stocks.csv'den skorları çek
        try:
            row = self.scores_df.loc[ticker]
            return {
                'FINAL_THG': float(row.get('FINAL_THG', 0)),
                'bidbuy_ucuzluk': float(row.get('bidbuy_ucuzluk', 0)),
                'asksell_pahali': float(row.get('asksell_pahali', 0))
            }
        except Exception:
            return {'FINAL_THG': 0, 'bidbuy_ucuzluk': 0, 'asksell_pahali': 0}

    def get_position(self, ticker):
        # market_data.get_positions() IBKR'den pozisyonları döndürür
        if hasattr(self.market_data, 'get_positions'):
            positions = self.market_data.get_positions()
            for pos in positions:
                if pos['symbol'] == ticker:
                    return {'size': pos['quantity'], 'avgCost': pos.get('avgCost', 0)}
        return None

    def calculate_benchmark_at_fill(self, ticker):
        """Fill anında benchmark hesapla"""
        try:
            # Basit benchmark hesaplama
            current_price = self.get_current_price(ticker)
            if current_price:
                return current_price * 1.0  # Şimdilik current price
            return 0
        except Exception:
            return 0

    def test_reverse_order_system(self, ticker="JAGX", side="long", fill_price=2.89, fill_size=200):
        """Reverse order sistemini test et"""
        print(f"[TEST REVERSE ORDER] 🧪 Test başlatılıyor: {ticker} {side} {fill_size} @ {fill_price}")
        
        # Test fill simülasyonu
        self.on_fill(ticker, side, fill_price, fill_size)
        
        print(f"[TEST REVERSE ORDER] ✅ Test tamamlandı")

    def debug_daily_fills(self):
        """Günlük fill istatistiklerini debug et"""
        print("[DEBUG DAILY FILLS] 📊 Günlük fill istatistikleri:")
        
        for date, tickers in self.daily_fills.items():
            print(f"[DEBUG] {date}:")
            for ticker, fills in tickers.items():
                total = fills['long'] + fills['short']
                print(f"[DEBUG]   {ticker}: Long={fills['long']}, Short={fills['short']}, Total={total}")

    def polygonize_ticker(self, ticker):
        """IBKR ticker'ını Polygon formatına çevir"""
        # Preferred stock formatını çevir: "ABC PRA" -> "ABC-PA"
        if ' PR' in ticker:
            base, pref = ticker.split(' PR')
            return f"{base}-P{pref}"
        return ticker

    def get_top_stocks_by_score(self, window, score_column, count=5, ascending=True, score_range=(0, 1500)):
        """
        Penceredeki hisseleri belirtilen skor kolonuna göre sıralar ve en iyi 'count' tanesini döndürür
        Exclude listesindeki hisseler atlanır ve gerekirse daha fazla hisse alınır
        
        Args:
            window: Pencere objesi (rows ve COLUMNS içermeli)
            score_column: Skor kolonu adı
            count: Seçilecek hisse sayısı
            ascending: True = en düşük skorlar (min), False = en yüksek skorlar (max)
            score_range: Geçerli skor aralığı (min, max)
        
        Returns:
            [(ticker, score), ...] listesi
        """
        if not window or not hasattr(window, 'rows') or not hasattr(window, 'COLUMNS'):
            print(f"[GET TOP STOCKS] ❌ Geçersiz pencere objesi")
            return []
        
        rows = window.rows
        columns = window.COLUMNS
        
        if score_column not in columns:
            print(f"[GET TOP STOCKS] ❌ Skor kolonu bulunamadı: {score_column}")
            return []
        
        score_index = columns.index(score_column)
        valid_stocks = []
        
        # TÜM hisseleri analiz et (exclude sonrası yeterli hisse kalması için)
        for row in rows:
            try:
                if len(row) <= max(1, score_index):
                    continue
                    
                ticker = row[1] if len(row) > 1 else ""
                score_str = row[score_index] if len(row) > score_index else ""
                
                if not ticker or not score_str:
                    continue
                
                # Komple exclude listesindeki hisseleri atla
                if ticker in self.exclude_list:
                    print(f"[GET TOP STOCKS] ⏭️ {ticker} komple exclude listesinde, atlanıyor")
                    continue
                
                # Half-sized kontrolü - dinamik lot sistemi
                if hasattr(self, 'half_sized_list') and ticker in self.half_sized_list:
                    # Varsayılan lot boyutu (şu anda 200, gelecekte değişebilir)
                    intended_lot_size = getattr(self, 'default_lot_size', 200)
                    half_sized_lot = intended_lot_size // 2
                    minimum_lot_threshold = 200  # Minimum kabul edilebilir lot
                    
                    if intended_lot_size < 400:  # 400'ün altındaysa yarısı 200'den az olacak
                        print(f"[GET TOP STOCKS] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                        continue
                    else:
                        print(f"[GET TOP STOCKS] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
                
                # Score'u float'a çevir
                try:
                    score = float(score_str)
                except (ValueError, TypeError):
                    print(f"[GET TOP STOCKS] ⚠️ {ticker} geçersiz skor: {score_str}")
                    continue
                
                # Skor aralığı kontrolü
                if score_range and (score < score_range[0] or score > score_range[1]):
                    continue
                
                valid_stocks.append((ticker, score))
                
            except Exception as e:
                print(f"[GET TOP STOCKS] ❌ Satır işleme hatası: {e}")
                continue
        
        if not valid_stocks:
            print(f"[GET TOP STOCKS] ❌ {score_column} için geçerli hisse bulunamadı")
            return []
        
        # Skorlara göre sırala
        valid_stocks.sort(key=lambda x: x[1], reverse=not ascending)
        
        # En iyi 'count' tanesini seç
        selected_stocks = valid_stocks[:count]
        
        print(f"[GET TOP STOCKS] ✅ {score_column} için {len(selected_stocks)} hisse seçildi:")
        for ticker, score in selected_stocks:
            print(f"[GET TOP STOCKS]   {ticker}: {score}")
        
        return selected_stocks

    def check_front_spread_condition(self, ticker, order_type):
        """Front spread koşulunu kontrol et"""
        try:
            # Basit spread kontrolü - gerçek implementasyon daha karmaşık olabilir
            current_price = self.get_current_price(ticker)
            if not current_price:
                return False, "Fiyat bilgisi yok"
            
            # Örnek spread kontrolü (%0.1)
            min_spread = current_price * 0.001
            
            # Simülasyon için her zaman True döndür
            return True, f"Spread OK: {min_spread:.4f}"
            
        except Exception as e:
            return False, f"Spread kontrol hatası: {e}"

    def check_front_order_spread_condition(self, ticker, order_type, target_price):
        """
        Front emirleri için spread*0.35 uzaklık kontrolü
        
        Args:
            ticker: Hisse senedi kodu
            order_type: 'front_buy' veya 'front_sell'
            target_price: Hedef emir fiyatı
        
        Returns:
            (bool, str): (koşul_sağlanıyor_mu, açıklama_mesajı)
        """
        try:
            # Market data'dan bid/ask bilgilerini al
            bid_price, ask_price = self.get_bid_ask_prices(ticker)
            
            if not bid_price or not ask_price or bid_price <= 0 or ask_price <= 0:
                return False, f"Bid/Ask fiyat bilgisi alınamadı - Bid: {bid_price}, Ask: {ask_price}"
            
            # Spread hesapla
            spread = ask_price - bid_price
            if spread <= 0:
                return False, f"Geçersiz spread: {spread:.4f} (Bid: {bid_price:.3f}, Ask: {ask_price:.3f})"
            
            # Spread*0.35 toleransını hesapla
            spread_tolerance = spread * 0.35
            
            if order_type.lower() == 'front_buy':
                # Front buy: bid'e uzaklık spread*0.35'ten fazla olmamalı
                distance_from_bid = target_price - bid_price
                
                if distance_from_bid > spread_tolerance:
                    return False, (f"Front buy koşulu ihlali - Hedef: {target_price:.3f}, "
                                 f"Bid: {bid_price:.3f}, Uzaklık: {distance_from_bid:.3f}, "
                                 f"Max izin: {spread_tolerance:.3f} (spread*0.35)")
                
                return True, (f"Front buy OK - Hedef: {target_price:.3f}, Bid: {bid_price:.3f}, "
                            f"Uzaklık: {distance_from_bid:.3f} ≤ {spread_tolerance:.3f}")
                
            elif order_type.lower() == 'front_sell':
                # Front sell: ask'a uzaklık spread*0.35'ten fazla olmamalı
                distance_from_ask = ask_price - target_price
                
                if distance_from_ask > spread_tolerance:
                    return False, (f"Front sell koşulu ihlali - Hedef: {target_price:.3f}, "
                                 f"Ask: {ask_price:.3f}, Uzaklık: {distance_from_ask:.3f}, "
                                 f"Max izin: {spread_tolerance:.3f} (spread*0.35)")
                
                return True, (f"Front sell OK - Hedef: {target_price:.3f}, Ask: {ask_price:.3f}, "
                            f"Uzaklık: {distance_from_ask:.3f} ≤ {spread_tolerance:.3f}")
            
            else:
                return False, f"Geçersiz emir türü: {order_type}"
                
        except Exception as e:
            return False, f"Front spread kontrolü hatası: {str(e)}"

    def get_bid_ask_prices(self, ticker):
        """
        Ticker için bid/ask fiyatlarını al (Thread-safe)
        
        Returns:
            (float, float): (bid_price, ask_price)
        """
        try:
            # 1. Önce pencere verisinden al (Thread-safe)
            if hasattr(self, 'current_window') and self.current_window:
                bid_price = self.get_price_from_window(self.current_window, ticker, 'Bid')
                ask_price = self.get_price_from_window(self.current_window, ticker, 'Ask')
                
                if bid_price and ask_price and bid_price > 0 and ask_price > 0:
                    print(f"[BID/ASK] {ticker} pencere verisinden alındı: Bid={bid_price:.3f}, Ask={ask_price:.3f}")
                    return bid_price, ask_price
                else:
                    print(f"[BID/ASK] {ticker} pencere verisi eksik: Bid={bid_price}, Ask={ask_price}")
            
            # 2. Market_data_dict'ten al (Polygon verileri)
            if hasattr(self.market_data, 'last_data') and self.market_data.last_data:
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.market_data.last_data:
                    data = self.market_data.last_data[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[BID/ASK] {ticker} market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
                    else:
                        print(f"[BID/ASK] {ticker} market_data bid/ask eksik: Bid={bid}, Ask={ask}")
            
            # 3. Ana pencereden market_data_dict al
            if hasattr(self, 'main_window') and self.main_window and hasattr(self.main_window, 'market_data_dict'):
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.main_window.market_data_dict:
                    data = self.main_window.market_data_dict[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[BID/ASK] {ticker} ana pencere market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
            
            # 4. Current window'daki market_data_dict'i dene
            if hasattr(self, 'current_window') and self.current_window and hasattr(self.current_window, 'market_data_dict'):
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.current_window.market_data_dict:
                    data = self.current_window.market_data_dict[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[BID/ASK] {ticker} current_window market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
            
            # 5. Son çare: current price'ın %0.5'i kadar spread varsay
            current_price = self.get_current_price(ticker)
            if current_price and current_price > 0:
                estimated_spread = current_price * 0.005  # %0.5 spread varsayımı
                bid = current_price - (estimated_spread / 2)
                ask = current_price + (estimated_spread / 2)
                print(f"[BID/ASK] {ticker} tahmini bid/ask: Bid={bid:.3f}, Ask={ask:.3f} (spread: {estimated_spread:.3f})")
                return bid, ask
            
            print(f"[BID/ASK] {ticker} hiçbir kaynaktan fiyat alınamadı")
            return None, None
            
        except Exception as e:
            print(f"[BID/ASK] {ticker} bid/ask alma hatası: {e}")
            return None, None

    def validate_front_order_before_sending(self, ticker, order_type, target_price):
        """
        Front emir göndermeden önce spread koşulunu kontrol et
        
        Args:
            ticker: Hisse senedi kodu
            order_type: 'front_buy' veya 'front_sell'
            target_price: Hedef emir fiyatı
        
        Returns:
            (bool, str): (emir_gönderilebilir_mi, açıklama_mesajı)
        """
        print(f"[FRONT VALIDATION] {ticker} {order_type} @ {target_price:.3f} spread kontrolü...")
        
        # ✅ SPREAD BOYUTU KONTROLÜ - 0.06 centten küçükse kontrol yapma
        bid_price, ask_price = self.get_bid_ask_prices(ticker)
        
        if bid_price and ask_price and bid_price > 0 and ask_price > 0:
            spread = ask_price - bid_price
            
            if spread < 0.06:
                print(f"[FRONT VALIDATION] ✅ {ticker} {order_type} - Spread çok dar ({spread:.4f} < 0.06), kontrol atlanıyor")
                return True, f"Dar spread ({spread:.4f} < 0.06) - kontrol atlandı"
            
            print(f"[FRONT VALIDATION] 🔍 {ticker} {order_type} - Geniş spread ({spread:.4f} ≥ 0.06), kontrol yapılıyor")
        else:
            print(f"[FRONT VALIDATION] ⚠️ {ticker} {order_type} - Bid/Ask alınamadı, kontrol yapılıyor")
        
        # Front spread koşulunu kontrol et
        is_valid, message = self.check_front_order_spread_condition(ticker, order_type, target_price)
        
        if is_valid:
            print(f"[FRONT VALIDATION] ✅ {ticker} {order_type} - {message}")
            return True, message
        else:
            print(f"[FRONT VALIDATION] ❌ {ticker} {order_type} - {message}")
            return False, message

    def get_position_safe_lot_size(self, ticker, action, requested_lot):
        """Pozisyon güvenli lot büyüklüğünü hesapla"""
        try:
            current_pos = self.get_position_size(ticker)
            
            # BEFDAY limitlerini kontrol et
            if ticker in self.daily_position_limits:
                min_limit, max_limit = self.daily_position_limits[ticker]
                
                if action.lower() in ['buy', 'long']:
                    max_safe_lot = max_limit - current_pos
                else:
                    max_safe_lot = current_pos - min_limit
                
                safe_lot = min(requested_lot, max(0, max_safe_lot))
                
                print(f"[SAFE LOT] {ticker}: Talep={requested_lot}, Güvenli={safe_lot}, Pozisyon={current_pos}, Limit=[{min_limit}, {max_limit}]")
                return safe_lot
            
            return requested_lot
            
        except Exception as e:
            print(f"[SAFE LOT] {ticker} hesaplama hatası: {e}")
            return requested_lot

    def check_existing_orders_conflict(self, ticker, target_price, order_side, tolerance=0.10):
        """
        Mevcut emirlerle çakışma kontrolü yapar
        
        Args:
            ticker: Hisse senedi kodu
            target_price: Hedef fiyat
            order_side: 'BUY' veya 'SELL'
            tolerance: Fiyat toleransı (varsayılan: ±0.08)
        
        Returns:
            (bool, str): (çakışma_var_mı, açıklama_mesajı)
        """
        try:
            # ✅ Güvenlik kontrolü: target_price geçerli mi?
            if target_price is None or target_price <= 0:
                return False, f"Geçersiz hedef fiyat: {target_price}"
            
            target_price = float(target_price)  # Float'a çevir
            
            # IBKR bağlantısı var mı?
            if not hasattr(self.market_data, 'ib') or not self.market_data.ib:
                print(f"[ORDER CONFLICT] ⚠️ {ticker} - IBKR bağlantısı yok")
                return False, "IBKR bağlantısı yok"
            
            # Mevcut emirleri al
            open_trades = self.market_data.ib.openTrades()
            print(f"[ORDER CONFLICT] 🔍 {ticker} - IBKR'den {len(open_trades)} adet mevcut emir çekildi")
            
            # Ticker için mevcut emirleri kontrol et
            ticker_orders_found = 0
            
            for trade in open_trades:
                contract = trade.contract
                order = trade.order
                
                # Hisse kodunu logla (debug için)
                existing_symbol = contract.symbol
                print(f"[ORDER CONFLICT] 📋 Mevcut emir: {existing_symbol} {order.action} {order.totalQuantity} @ {order.lmtPrice}")
                
                if existing_symbol != ticker:
                    continue  # Bu ticker değil, geç
                
                ticker_orders_found += 1
                print(f"[ORDER CONFLICT] 🎯 {ticker} için mevcut emir bulundu: {order.action} {order.totalQuantity} @ {order.lmtPrice}")
                    
                existing_action = order.action  # BUY/SELL
                existing_price = order.lmtPrice
                existing_quantity = order.totalQuantity
                
                # ✅ Güvenlik kontrolü: existing_price geçerli mi?
                if existing_price is None or existing_price <= 0:
                    print(f"[ORDER CONFLICT] ⚠️ {ticker} - Geçersiz fiyat: {existing_price}")
                    continue
                
                existing_price = float(existing_price)  # Float'a çevir
                
                # Aynı yönde emir mi?
                if existing_action != order_side:
                    print(f"[ORDER CONFLICT] ↔️ {ticker} - Farklı yön: Mevcut={existing_action}, Hedef={order_side}")
                    continue
                
                # AGRESİF ÇAKIŞMA KONTROLÜ: Aynı ticker + aynı yön = çakışma (fiyat fark etmez)
                price_diff = abs(existing_price - target_price)
                print(f"[ORDER CONFLICT] 📊 {ticker} - ÇAKIŞMA TESPİT EDİLDİ! Aynı ticker ve yönde mevcut emir var")
                print(f"[ORDER CONFLICT] 📊 Mevcut: {existing_action} {existing_quantity} @ {existing_price:.3f}")
                print(f"[ORDER CONFLICT] 📊 Hedef: {order_side} @ {target_price:.3f}")
                print(f"[ORDER CONFLICT] 📊 Fiyat farkı: {price_diff:.3f}")
                
                # AGRESİF MOD: Aynı ticker + aynı yönde herhangi bir emir varsa çakışma!
                conflict_msg = (f"AGRESİF ÇAKIŞMA - Mevcut: {existing_action} {existing_quantity} @ {existing_price:.3f}, "
                              f"Hedef: {order_side} @ {target_price:.3f} - Aynı ticker+yön tekrarı engellendi!")
                
                print(f"[ORDER CONFLICT] ❌ {ticker} - {conflict_msg}")
                return True, conflict_msg
            
            print(f"[ORDER CONFLICT] 📊 {ticker} - Toplam {ticker_orders_found} adet mevcut emir kontrol edildi")
            
            # Çakışma yok
            return False, f"Çakışma yok - {order_side} @ {target_price:.3f} (tolerance: ±{tolerance})"
            
        except Exception as e:
            print(f"[ORDER CONFLICT] ❌ {ticker} emir çakışma kontrolü hatası: {e}")
            return False, f"Kontrol hatası: {str(e)}"

    def filter_stocks_by_existing_orders(self, selected_stocks, order_side, window, price_column=None):
        """
        Seçili hisselerden mevcut emirlerle çakışanları filtreler ve sıradaki hisseleri ekler
        
        Args:
            selected_stocks: [(ticker, score), ...] listesi
            order_side: 'BUY' veya 'SELL'
            window: Pencere objesi (fiyat bilgisi için)
            price_column: Fiyat kolonu adı (None ise current price kullanılır)
        
        Returns:
            [(ticker, score), ...] filtrelenmiş liste
        """
        if not selected_stocks:
            return []
        
        filtered_stocks = []
        conflicts_found = []
        
        for ticker, score in selected_stocks:
            # Hedef fiyatı belirle
            if price_column and hasattr(window, 'rows') and hasattr(window, 'COLUMNS'):
                try:
                    # Pencereden fiyat bilgisini al
                    target_price = self.get_price_from_window(window, ticker, price_column)
                    if not target_price:
                        target_price = self.get_current_price(ticker) or 0
                except:
                    target_price = self.get_current_price(ticker) or 0
            else:
                # Current price kullan
                target_price = self.get_current_price(ticker) or 0
            
            if target_price <= 0:
                print(f"[ORDER FILTER] ⚠️ {ticker} için fiyat alınamadı, atlanıyor")
                continue
            
            # Çakışma kontrolü
            has_conflict, conflict_msg = self.check_existing_orders_conflict(ticker, target_price, order_side)
            
            if has_conflict:
                conflicts_found.append((ticker, score, conflict_msg))
                print(f"[ORDER FILTER] ❌ {ticker} (skor:{score:.2f}) - {conflict_msg}")
            else:
                filtered_stocks.append((ticker, score))
                print(f"[ORDER FILTER] ✅ {ticker} (skor:{score:.2f}) - Çakışma yok, fiyat: {target_price:.3f}")
        
        if conflicts_found:
            print(f"[ORDER FILTER] ⚠️ {len(conflicts_found)} hisse çakışma nedeniyle filtrelendi:")
            for ticker, score, msg in conflicts_found:
                print(f"[ORDER FILTER]   - {ticker}: {msg}")
        
        return filtered_stocks

    def get_price_from_window(self, window, ticker, price_column):
        """Pencereden belirli ticker için fiyat bilgisini al"""
        try:
            if not hasattr(window, 'rows') or not hasattr(window, 'COLUMNS'):
                return None
                
            rows = window.rows
            columns = window.COLUMNS
            
            if price_column not in columns:
                return None
                
            price_index = columns.index(price_column)
            
            for row in rows:
                if len(row) > 1 and row[1] == ticker and len(row) > price_index:
                    try:
                        return float(row[price_index])
                    except (ValueError, TypeError):
                        continue
            
            return None
            
        except Exception as e:
            print(f"[PRICE FROM WINDOW] ❌ {ticker} fiyat alma hatası: {e}")
            return None

    def get_extended_stock_selection(self, window, score_column, original_count, needed_count, ascending=True, score_range=(0, 1500), order_side='BUY'):
        """
        Çakışma nedeniyle filtrelenen hisseler için genişletilmiş seçim yapar
        
        Args:
            window: Pencere objesi
            score_column: Skor kolonu adı
            original_count: Orijinal seçim sayısı
            needed_count: İhtiyaç duyulan ek hisse sayısı
            ascending: Sıralama yönü
            score_range: Skor aralığı
            order_side: Emir yönü ('BUY'/'SELL')
        
        Returns:
            [(ticker, score), ...] genişletilmiş liste
        """
        # Daha geniş bir seçim yap (original_count + needed_count + buffer)
        buffer_count = max(5, needed_count * 2)  # En az 5, ideal olarak needed_count'un 2 katı
        extended_count = original_count + needed_count + buffer_count
        
        print(f"[EXTENDED SELECTION] 🔍 {score_column} için genişletilmiş seçim: {extended_count} hisse")
        
        # Genişletilmiş seçim yap
        extended_stocks = self.get_top_stocks_by_score(
            window, 
            score_column, 
            count=extended_count,
            ascending=ascending,
            score_range=score_range
        )
        
        if not extended_stocks:
            return []
        
        # Çakışma filtresi uygula
        filtered_stocks = self.filter_stocks_by_existing_orders(
            extended_stocks, 
            order_side, 
            window
        )
        
        print(f"[EXTENDED SELECTION] ✅ {len(extended_stocks)} → {len(filtered_stocks)} hisse (çakışma filtresi sonrası)")
        
        # İhtiyaç duyulan sayıda hisse döndür
        return filtered_stocks[:original_count]

    # YENİ 8 ADIMLI SİSTEM FONKSİYONLARI
    def run_new_t_losers_bb(self):
        """1. YENİ T-Losers BID BUY"""
        print("[PSF CHAIN 1] 📉 T-Losers BID BUY başlatılıyor...")
        
        # ✅ PSFAlgo1 aktif mi kontrolü
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - T-Losers BB işlenmedi")
            return
            
        # ✅ Zaten onay bekleme durumunda mı?
        if hasattr(self, 'waiting_for_approval') and self.waiting_for_approval:
            print("[PSF CHAIN 1] ⏸️ Zaten onay bekleniyor, yeni işlem başlatılmıyor")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
        
        # FINAL BB skoruna göre en yüksek 5 hisse seç (exclude list hariç)
        selected_stocks = self.get_top_stocks_by_score_with_smart_filtering(
            self.current_window, 
            'Final BB skor', 
            count=5, 
            ascending=False,  # En yüksek skorlar
            score_range=(0.01, 1500),  # 0 ve negatif değerleri filtrele
            order_side='BUY',
            smi_check=False  # Buy emirleri için SMI kontrolü yok
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 1] ❌ Final BB skor için uygun hisse bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        selected_tickers = set([ticker for ticker, score in selected_stocks])
        self.current_window.selected_tickers = selected_tickers
        
        # Reasoning logla
        for ticker, score in selected_stocks:
            msg = f"{ticker} seçildi - Final BB skor: {score}"
            print("[REASONING]", msg)
            log_reasoning(msg)
        
        # Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Bid buy butonunu tetikle
        print("[DEBUG] send_bid_buy_orders çağrılıyor...")
        self.current_window.send_bid_buy_orders()
        
        print("[PSF CHAIN 1] T-Losers BID BUY onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_new_t_losers_fb(self):
        """2. YENİ T-Losers FINAL BUY"""
        print("[PSF CHAIN 2] 📉 T-Losers FINAL BUY başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - T-Losers FB işlenmedi")
            return
            
        # ✅ Zaten onay bekleme durumunda mı?
        if hasattr(self, 'waiting_for_approval') and self.waiting_for_approval:
            print("[PSF CHAIN 2] ⏸️ Zaten onay bekleniyor, yeni işlem başlatılmıyor")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
        
        # FINAL FB skoruna göre en yüksek 5 hisse seç (exclude list hariç)
        selected_stocks = self.get_top_stocks_by_score_with_smart_filtering(
            self.current_window, 
            'Final FB skor', 
            count=5, 
            ascending=False,  # En yüksek skorlar
            score_range=(0.01, 1500),  # 0 ve negatif değerleri filtrele
            order_side='BUY',
            smi_check=False  # Buy emirleri için SMI kontrolü yok
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 2] ❌ Final FB skor için uygun hisse bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        selected_tickers = set([ticker for ticker, score in selected_stocks])
        self.current_window.selected_tickers = selected_tickers
        
        # Reasoning logla
        for ticker, score in selected_stocks:
            msg = f"{ticker} seçildi - Final FB skor: {score}"
            print("[REASONING]", msg)
            log_reasoning(msg)
        
        # Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Front buy butonunu tetikle
        print("[DEBUG] send_front_buy_orders çağrılıyor...")
        self.current_window.send_front_buy_orders()
        
        print("[PSF CHAIN 2] T-Losers FINAL BUY onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_new_t_gainers_as(self):
        """3. YENİ T-Gainers ASK SELL"""
        print("[PSF CHAIN 3] 📈 T-Gainers ASK SELL başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - T-Gainers AS işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
        
        # Final AS skor'una göre EN DÜŞÜK 5 hisse seç (en iyi satış fırsatları)
        selected_stocks = self.get_top_stocks_by_score_with_smart_filtering(
            self.current_window, 
            'Final AS skor', 
            count=5, 
            ascending=True,  # EN DÜŞÜK skorlar (satış için en iyi)
            score_range=(0.01, 1500),  # 0 ve negatif değerleri filtrele
            order_side='SELL',
            smi_check=True  # Short artırma için SMI < 0.28 kontrolü
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 3] ❌ Final AS skor için uygun hisse bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        selected_tickers = set([ticker for ticker, score in selected_stocks])
        self.current_window.selected_tickers = selected_tickers
        
        # Reasoning logla
        for ticker, score in selected_stocks:
            msg = f"{ticker} seçildi - Final AS skor: {score} (EN DÜŞÜK = EN İYİ SATIŞ)"
            print("[REASONING]", msg)
            log_reasoning(msg)
        
        # Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Ask sell butonunu tetikle
        print("[DEBUG] send_ask_sell_orders çağrılıyor...")
        self.current_window.send_ask_sell_orders()
        
        print("[PSF CHAIN 3] T-Gainers ASK SELL onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_new_t_gainers_fs(self):
        """4. YENİ T-Gainers FINAL SELL"""
        print("[PSF CHAIN 4] 📈 T-Gainers FINAL SELL başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - T-Gainers FS işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
        
        # Final FS skor'una göre EN DÜŞÜK 5 hisse seç (en iyi satış fırsatları)
        selected_stocks = self.get_top_stocks_by_score_with_smart_filtering(
            self.current_window, 
            'Final FS skor', 
            count=5, 
            ascending=True,  # EN DÜŞÜK skorlar (satış için en iyi)
            score_range=(0.01, 1500),  # 0 ve negatif değerleri filtrele
            order_side='SELL',
            smi_check=True  # Short artırma için SMI < 0.28 kontrolü
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 4] ❌ Final FS skor için uygun hisse bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        selected_tickers = set([ticker for ticker, score in selected_stocks])
        self.current_window.selected_tickers = selected_tickers
        
        # Reasoning logla
        for ticker, score in selected_stocks:
            msg = f"{ticker} seçildi - Final FS skor: {score} (EN DÜŞÜK = EN İYİ SATIŞ)"
            print("[REASONING]", msg)
            log_reasoning(msg)
        
        # Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Front sell butonunu tetikle
        print("[DEBUG] send_front_sell_orders çağrılıyor...")
        self.current_window.send_front_sell_orders()
        
        print("[PSF CHAIN 4] T-Gainers FINAL SELL onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_new_long_tp_as(self):
        """5. YENİ Long TP ASK SELL"""
        print("[PSF CHAIN 5] 💰 Long TP ASK SELL başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - Long TP AS işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
        
        # Final AS skor'una göre EN DÜŞÜK 3 hisse seç (TP için daha az)
        selected_stocks = self.get_top_stocks_by_score_with_smart_filtering(
            self.current_window, 
            'Final AS skor', 
            count=3, 
            ascending=True,  # EN DÜŞÜK skorlar (satış için en iyi)
            score_range=(0.01, 1500),  # 0 ve negatif değerleri filtrele
            order_side='SELL',
            smi_check=False  # Long TP için SMI kontrolü yok
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 5] ❌ Final AS skor için uygun hisse bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        selected_tickers = set([ticker for ticker, score in selected_stocks])
        self.current_window.selected_tickers = selected_tickers
        
        # Reasoning logla
        for ticker, score in selected_stocks:
            msg = f"{ticker} seçildi - Long TP Final AS skor: {score}"
            print("[REASONING]", msg)
            log_reasoning(msg)
        
        # Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Ask sell butonunu tetikle
        print("[DEBUG] send_ask_sell_orders çağrılıyor...")
        self.current_window.send_ask_sell_orders()
        
        print("[PSF CHAIN 5] Long TP ASK SELL onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_new_long_tp_fs(self):
        """6. YENİ Long TP FINAL SELL"""
        print("[PSF CHAIN 6] 💰 Long TP FINAL SELL başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - Long TP FS işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
        
        # Final FS skor'una göre EN DÜŞÜK 3 hisse seç (TP için daha az)
        selected_stocks = self.get_top_stocks_by_score_with_smart_filtering(
            self.current_window, 
            'Final FS skor', 
            count=3, 
            ascending=True,  # EN DÜŞÜK skorlar (satış için en iyi)
            score_range=(0.01, 1500),  # 0 ve negatif değerleri filtrele
            order_side='SELL',
            smi_check=False  # Long TP için SMI kontrolü yok
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 6] ❌ Final FS skor için uygun hisse bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        selected_tickers = set([ticker for ticker, score in selected_stocks])
        self.current_window.selected_tickers = selected_tickers
        
        # Reasoning logla
        for ticker, score in selected_stocks:
            msg = f"{ticker} seçildi - Long TP Final FS skor: {score}"
            print("[REASONING]", msg)
            log_reasoning(msg)
        
        # Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Front sell butonunu tetikle
        print("[DEBUG] send_front_sell_orders çağrılıyor...")
        self.current_window.send_front_sell_orders()
        
        print("[PSF CHAIN 6] Long TP FINAL SELL onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def get_top_stocks_by_score_with_smart_filtering(self, window, score_column, count=5, ascending=True, score_range=(0, 1500), order_side='BUY', smi_check=False):
        """
        Akıllı filtreli hisse seçimi:
        1. Skor filtreleme (geçerli aralıkta)
        2. SMI kontrolü (short artırma için)
        3. Çakışma kontrolü (±0.08 fiyat toleransı)
        """
        print(f"[SMART FILTERING] {score_column} için akıllı seçim başlatılıyor...")
        print(f"[SMART FILTERING] Count: {count}, Ascending: {ascending}, Score Range: {score_range}")
        print(f"[SMART FILTERING] Order Side: {order_side}, SMI Check: {smi_check}")
        
        rows = window.rows
        columns = window.COLUMNS
        
        if not rows:
            print("[SMART FILTERING] ❌ Veri yok")
            return []
        
        # Skor kolonu indeksini bul
        try:
            score_index = columns.index(score_column)
        except ValueError:
            print(f"[SMART FILTERING] ❌ {score_column} kolonu bulunamadı")
            return []
        
        # SMI rate kolonu indeksi (ihtiyaç halinde)
        smi_index = None
        if smi_check:
            try:
                smi_index = columns.index('SMI rate')
            except ValueError:
                print("[SMART FILTERING] ⚠️ SMI rate kolonu bulunamadı, SMI kontrolü atlanıyor")
                smi_check = False
        
        # TÜM hisseleri analiz et
        valid_stocks = []
        for row in rows:
            try:
                if len(row) <= max(1, score_index):
                    continue
                    
                ticker = row[1] if len(row) > 1 else ""
                score_str = row[score_index] if len(row) > score_index else ""
                
                if not ticker or not score_str:
                    continue
                
                # Komple exclude listesindeki hisseleri atla
                if ticker in self.exclude_list:
                    print(f"[SMART FILTERING] ⏭️ {ticker} komple exclude listesinde, atlanıyor")
                    continue
                
                # Half-sized kontrolü - dinamik lot sistemi
                if hasattr(self, 'half_sized_list') and ticker in self.half_sized_list:
                    # Varsayılan lot boyutu (şu anda 200, gelecekte değişebilir)
                    intended_lot_size = getattr(self, 'default_lot_size', 200)
                    half_sized_lot = intended_lot_size // 2
                    minimum_lot_threshold = 200  # Minimum kabul edilebilir lot
                    
                    if intended_lot_size < 400:  # 400'ün altındaysa yarısı 200'den az olacak
                        print(f"[SMART FILTERING] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                        continue
                    else:
                        print(f"[SMART FILTERING] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
                
                # Score'u float'a çevir
                try:
                    score = float(score_str)
                except (ValueError, TypeError):
                    continue
                
                # Skor aralığı kontrolü
                if score_range and (score < score_range[0] or score > score_range[1]):
                    continue
                
                # SMI kontrolü (short artırma emirleri için)
                if smi_check and smi_index is not None and order_side == 'SELL':
                    try:
                        smi_value = float(row[smi_index]) if len(row) > smi_index and row[smi_index] else 1.0
                        if smi_value >= 0.28:
                            print(f"[SMART FILTERING] ⏭️ {ticker} SMI kontrolü başarısız: {smi_value} >= 0.28")
                            continue
                    except (ValueError, TypeError):
                        # SMI değeri okunamıyorsa güvenlik için atla
                        continue
                
                valid_stocks.append((ticker, score))
                
            except Exception as e:
                continue
        
        if not valid_stocks:
            print(f"[SMART FILTERING] ❌ {score_column} için geçerli hisse bulunamadı")
            return []
        
        # Skorlara göre sırala
        valid_stocks.sort(key=lambda x: x[1], reverse=not ascending)
        
        print(f"[SMART FILTERING] 📊 Skorlamadan {len(valid_stocks)} geçerli hisse bulundu")
        
        # ✅ 3. ŞİRKET LİMİTİ FİLTRESİ (YENİ!) - Aynı şirketten maksimum 3 hisse
        print(f"[SMART FILTERING] 🏢 Şirket limiti kontrolü uygulanıyor...")
        
        # Şirket limitlerini uygula
        company_filtered_stocks = self.filter_by_company_limits(valid_stocks, max_selections=None)
        
        print(f"[SMART FILTERING] 📊 Şirket limiti sonrası {len(company_filtered_stocks)} hisse kaldı")
        
        # ✅ 4. ÇAKIŞMA FİLTRESİ (AKTİF - GENİŞLETİLMİŞ ADAY HAVUZU)
        print(f"[SMART FILTERING] 🔍 Çakışma kontrolü için genişletilmiş aday havuzu oluşturuluyor...")
        
        # GENİŞLETİLMİŞ ADAY HAVUZU: JPM PRK gibi çakışmaları aşmak için
        # 5 hisse istiyorsak, en az 20 adaya bak (çakışma rezervi için)
        max_candidates = min(count * 4, len(company_filtered_stocks))  # Hedefin 4 katı, min 20
        max_candidates = max(max_candidates, 15)  # En az 15 aday
        candidate_stocks = company_filtered_stocks[:max_candidates]
        
        print(f"[SMART FILTERING] 📊 {count} hisse seçmek için {max_candidates} aday incelenecek")
        print(f"[SMART FILTERING] 🎯 İlk {min(8, len(candidate_stocks))} aday:")
        for i, (ticker, score) in enumerate(candidate_stocks[:8], 1):
            print(f"[SMART FILTERING]   {i:2d}. {ticker}: {score:.2f}")
        if len(candidate_stocks) > 8:
            print(f"[SMART FILTERING]   ... ve {len(candidate_stocks)-8} aday daha")
        
        # Çakışma filtresi uygula
        filtered_stocks = self.filter_stocks_by_existing_orders_advanced(
            candidate_stocks, 
            order_side, 
            window,
            target_count=count
        )
        
        # Sonuç kontrol
        if len(filtered_stocks) < count:
            print(f"[SMART FILTERING] ⚠️ Çakışma filtresi sonrası {len(filtered_stocks)} hisse kaldı, {count} gerekiyordu")
            print(f"[SMART FILTERING] 💡 En iyi {max_candidates} hisse arasında yeterli çakışmasız hisse bulunamadı")
            
            # Eğer hiç hisse yoksa, o adımda emir sunma
            if len(filtered_stocks) == 0:
                print(f"[SMART FILTERING] ❌ Hiç uygun hisse yok - bu adımda emir sunulmayacak")
                return []
        
        print(f"[SMART FILTERING] 📊 {len(candidate_stocks)} → {len(filtered_stocks)} hisse (çakışma filtresi sonrası)")
        
        # ✅ 5. CROSS-STEP VALIDATION (MAXALW + Şirket limiti kontrolü)
        print(f"[SMART FILTERING] 🔍 Cross-step validation uygulanıyor...")
        
        # Mevcut adım numarasını belirle (PSFAlgo1 için)
        step_number = 1  # Varsayılan olarak 1. adım
        
        # Cross-step validation uygula
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            filtered_stocks[:count],  # İlk count kadar hisseyi kontrol et
            step_number=step_number,
            order_side=order_side,
            target_count=count,  # Hedef sayı
            extended_candidates=filtered_stocks  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # Sonuç kontrol
        if len(cross_step_valid) < count:
            print(f"[SMART FILTERING] ⚠️ Cross-step validation sonrası {len(cross_step_valid)} hisse kaldı, {count} gerekiyordu")
            
            # Eğer hiç hisse yoksa, o adımda emir sunma
            if len(cross_step_valid) == 0:
                print(f"[SMART FILTERING] ❌ Hiç uygun hisse yok - bu adımda emir sunulmayacak")
                return []
        
        print(f"[SMART FILTERING] 📊 {len(filtered_stocks)} → {len(cross_step_valid)} hisse (cross-step validation sonrası)")
        
        # Seçilen hisseleri logla
        if cross_step_valid:
            print(f"[SMART FILTERING] ✅ {len(cross_step_valid)} hisse seçildi")
            for i, (ticker, score) in enumerate(cross_step_valid, 1):
                print(f"[SMART FILTERING]   {i}. {ticker}: {score_column} = {score}")
        
        return cross_step_valid

    def filter_candidates_by_cross_step_rules(self, candidate_list, step_number, order_side, target_count=5, extended_candidates=None):
        """
        Aday hisse listesini cross-step kurallarına göre filtreler
        Elenen hisselerin yerine diğer adayları geçirir
        """
        if not candidate_list:
            return []
        
        # Genişletilmiş aday listesi yoksa, orijinal listeyi kullan
        if extended_candidates is None:
            extended_candidates = candidate_list
        
        print(f"[PSFAlgo1 CROSS-STEP FILTER] 🔍 Adım {step_number} için {len(candidate_list)} aday filtreleniyor...")
        print(f"[PSFAlgo1 CROSS-STEP FILTER] 📊 Genişletilmiş aday havuzu: {len(extended_candidates)} hisse")
        print(f"[PSFAlgo1 CROSS-STEP FILTER] 🎯 Hedef: {target_count} hisse seçilecek")
        
        valid_candidates = []
        rejected_candidates = []
        
        # İlk olarak verilen aday listesini kontrol et
        for candidate in candidate_list:
            ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
            score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
            
            # Validation yap (PSFAlgo1 için basit validation)
            is_valid, reason = self.validate_order_before_approval(ticker, order_side, 200, step_number)
            
            if is_valid:
                valid_candidates.append((ticker, score))
            else:
                rejected_candidates.append((ticker, score, reason))
        
        # Eğer hedef sayıya ulaşılmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_candidates) < target_count and len(extended_candidates) > len(candidate_list):
            print(f"[PSFAlgo1 CROSS-STEP FILTER] ⚠️ Hedef sayıya ulaşılamadı ({len(valid_candidates)}/{target_count}), genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in candidate_list])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in extended_candidates:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_candidates) >= target_count:
                    break
                
                # Validation yap
                is_valid, reason = self.validate_order_before_approval(ticker, order_side, 200, step_number)
                
                if is_valid:
                    valid_candidates.append((ticker, score))
                    print(f"[PSFAlgo1 CROSS-STEP FILTER] ✅ {ticker} (skor: {score:.2f}) - Genişletilmiş adaydan eklendi")
                else:
                    rejected_candidates.append((ticker, score, reason))
                    print(f"[PSFAlgo1 CROSS-STEP FILTER] ❌ {ticker} (skor: {score:.2f}) - {reason} (genişletilmiş aday)")
        
        # Sonuçları bildir
        print(f"[PSFAlgo1 CROSS-STEP FILTER] ✅ {len(valid_candidates)} hisse geçerli:")
        for ticker, score in valid_candidates:
            print(f"[PSFAlgo1 CROSS-STEP FILTER]   ✅ {ticker} (skor: {score:.2f})")
        
        if rejected_candidates:
            print(f"[PSFAlgo1 CROSS-STEP FILTER] ❌ {len(rejected_candidates)} hisse elendi:")
            for ticker, score, reason in rejected_candidates:
                print(f"[PSFAlgo1 CROSS-STEP FILTER]   ❌ {ticker} (skor: {score:.2f}) - {reason}")
        
        # Hedef sayıya ulaşılamadıysa uyarı ver
        if len(valid_candidates) < target_count:
            shortage = target_count - len(valid_candidates)
            print(f"[PSFAlgo1 CROSS-STEP FILTER] ⚠️ Hedef sayıya ulaşılamadı: {shortage} hisse eksik")
            print(f"[PSFAlgo1 CROSS-STEP FILTER] 💡 {len(extended_candidates)} aday arasından sadece {len(valid_candidates)} uygun hisse bulundu")
        
        return valid_candidates

    def validate_order_before_approval(self, ticker, side, size, step_number):
        """
        PSFAlgo1 için basit validation (PSFAlgo'dan kopyalandı)
        """
        print(f"[PSFAlgo1 ORDER VALIDATION] 🔍 {ticker} {side} {size} lot (Adım {step_number}) doğrulanıyor...")
        
        # Basit validation - sadece pozisyon kontrolü
        try:
            # Pozisyon güvenli lot hesapla
            safe_lot = self.get_position_safe_lot_size(ticker, side, size)
            
            if safe_lot > 0:
                print(f"[PSFAlgo1 ORDER VALIDATION] ✅ {ticker} {side} {size} lot onaylandı")
                return True, "Onaylandı"
            else:
                print(f"[PSFAlgo1 ORDER VALIDATION] ❌ {ticker} {side} {size} lot - Pozisyon güvenliği: {safe_lot}")
                return False, f"Pozisyon güvenliği: {safe_lot}"
                
        except Exception as e:
            print(f"[PSFAlgo1 ORDER VALIDATION] ❌ {ticker} validation hatası: {e}")
            return False, f"Validation hatası: {e}"

    def filter_stocks_by_existing_orders_advanced(self, candidate_stocks, order_side, window, target_count=5):
        """
        GELİŞMİŞ ÇAKIŞMA FİLTRESİ - SIRADAKİ ADAYLARA GEÇİŞ SİSTEMİ:
        1. Mevcut emirlerle çakışan hisseleri çıkar (±0.08 toleransı)
        2. Front emirler için spread kontrolü yap (spread ≥ 0.06 ise)
        3. Hedef sayıya ulaşana kadar sıradaki adayları dene
        4. JPM PRK gibi tekrarlanan emirleri engelle
        """
        print(f"[ADVANCED FILTER] 🔍 {len(candidate_stocks)} aday hisse için gelişmiş filtreleme...")
        print(f"[ADVANCED FILTER] 🎯 Hedef: {target_count} hisse seçilecek")
        
        filtered_stocks = []
        skipped_stocks = []
        
        for i, (ticker, score) in enumerate(candidate_stocks):
            print(f"[ADVANCED FILTER] 📊 {i+1}/{len(candidate_stocks)}: {ticker} (skor: {score:.2f}) kontrol ediliyor...")
            
            # Hedef fiyatı pencereden al
            target_price = self.get_price_from_window_for_order(window, ticker, order_side)
            
            if not target_price or target_price <= 0:
                print(f"[ADVANCED FILTER] ⚠️ {ticker} için fiyat alınamadı, atlanıyor")
                skipped_stocks.append((ticker, score, "Fiyat bilgisi yok"))
                continue
            
            # 1. ÇAKIŞMA KONTROLÜ - Kritik!
            has_conflict, conflict_msg = self.check_existing_orders_conflict(
                ticker, 
                target_price, 
                order_side, 
                tolerance=0.10  # ±10 cent tolerans (JPM PRK gibi durumlar için)
            )
            
            if has_conflict:
                print(f"[ADVANCED FILTER] ❌ {ticker} çakışma nedeniyle atlandı: {conflict_msg}")
                skipped_stocks.append((ticker, score, f"Çakışma: {conflict_msg}"))
                continue
            
            # 2. FRONT EMIR SPREAD KONTROLÜ (sadece front emirler için)
            is_front_order = False
            if hasattr(self, 'current_window') and self.current_window:
                # Chain state'den front emir olup olmadığını anla
                chain_state = getattr(self, 'chain_state', '')
                if 'FB' in chain_state or 'FS' in chain_state or 'FRONT' in chain_state:
                    is_front_order = True
            
            if is_front_order:
                # Front buy mu front sell mi belirle
                front_order_type = 'front_buy' if order_side == 'BUY' else 'front_sell'
                
                # Front spread kontrolü yap
                is_valid, spread_msg = self.validate_front_order_before_sending(ticker, front_order_type, target_price)
                
                if not is_valid:
                    print(f"[ADVANCED FILTER] ❌ {ticker} front spread kontrolü başarısız: {spread_msg}")
                    skipped_stocks.append((ticker, score, f"Front spread: {spread_msg}"))
                    continue
            
            # 3. TÜM KONTROLLER BAŞARILI - HİSSEYİ EKLE
            filtered_stocks.append((ticker, score))
            print(f"[ADVANCED FILTER] ✅ {ticker} eklendi (fiyat: {target_price:.3f}) - Toplam: {len(filtered_stocks)}/{target_count}")
            
            # 4. HEDEF SAYIYA ULAŞTIK MI?
            if len(filtered_stocks) >= target_count:
                print(f"[ADVANCED FILTER] 🎯 Hedef sayıya ulaşıldı: {target_count} hisse")
                break
        
        # 5. SONUÇ RAPORU
        print(f"[ADVANCED FILTER] 📊 Filtreleme sonucu: {len(candidate_stocks)} → {len(filtered_stocks)} hisse")
        
        if skipped_stocks:
            print(f"[ADVANCED FILTER] ⏭️ Atlanan {len(skipped_stocks)} hisse:")
            for ticker, score, reason in skipped_stocks:
                print(f"[ADVANCED FILTER]   ❌ {ticker} (skor: {score:.2f}): {reason}")
        
        if filtered_stocks:
            print(f"[ADVANCED FILTER] ✅ Seçilen {len(filtered_stocks)} hisse:")
            for i, (ticker, score) in enumerate(filtered_stocks, 1):
                print(f"[ADVANCED FILTER]   {i}. {ticker} (skor: {score:.2f})")
        
        # 6. YETERİNCE HİSSE BULUNAMADIYSA UYARI
        if len(filtered_stocks) < target_count:
            shortage = target_count - len(filtered_stocks)
            print(f"[ADVANCED FILTER] ⚠️ Hedef sayıya ulaşılamadı: {shortage} hisse eksik")
            print(f"[ADVANCED FILTER] 💡 {len(candidate_stocks)} aday arasından sadece {len(filtered_stocks)} uygun hisse bulundu")
        
        return filtered_stocks
    
    def get_price_from_window_for_order(self, window, ticker, order_side):
        """Pencereden emir türüne göre uygun fiyatı al"""
        try:
            if not hasattr(window, 'rows') or not hasattr(window, 'COLUMNS'):
                return self.get_current_price(ticker)
                
            rows = window.rows
            columns = window.COLUMNS
            
            # Emir türüne göre fiyat kolonu belirle
            if order_side == 'BUY':
                # Buy emirleri için bid veya current price
                price_columns = ['Bid', 'Current Price', 'Last']
            else:
                # Sell emirleri için ask veya current price  
                price_columns = ['Ask', 'Current Price', 'Last']
            
            # Ticker'ın satırını bul
            for row in rows:
                if len(row) > 1 and row[1] == ticker:
                    # Uygun fiyat kolonunu bul ve kullan
                    for price_col in price_columns:
                        if price_col in columns:
                            price_index = columns.index(price_col)
                            if len(row) > price_index:
                                try:
                                    price = float(row[price_index])
                                    if price > 0:
                                        return price
                                except (ValueError, TypeError):
                                    continue
                    break
            
            # Pencereden alınamazsa current price kullan
            return self.get_current_price(ticker)
            
        except Exception as e:
            print(f"[PRICE FOR ORDER] ❌ {ticker} fiyat alma hatası: {e}")
            return self.get_current_price(ticker)

    def run_new_short_tp_bb(self):
        """7. YENİ Short TP BID BUY"""
        print("[PSF CHAIN 7] 💰 Short TP BID BUY başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - Short TP BB işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
        
        # Final BB skoruna göre en yüksek 3 hisse seç (TP için daha az)
        selected_stocks = self.get_top_stocks_by_score_with_smart_filtering(
            self.current_window, 
            'Final BB skor', 
            count=3, 
            ascending=False,  # En yüksek skorlar
            score_range=(0.01, 1500),  # 0 ve negatif değerleri filtrele
            order_side='BUY',
            smi_check=False  # Buy emirleri için SMI kontrolü yok
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 7] ❌ Final BB skor için uygun hisse bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        selected_tickers = set([ticker for ticker, score in selected_stocks])
        self.current_window.selected_tickers = selected_tickers
        
        # Reasoning logla
        for ticker, score in selected_stocks:
            msg = f"{ticker} seçildi - Short TP Final BB skor: {score}"
            print("[REASONING]", msg)
            log_reasoning(msg)
        
        # Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Bid buy butonunu tetikle
        print("[DEBUG] send_bid_buy_orders çağrılıyor...")
        self.current_window.send_bid_buy_orders()
        
        print("[PSF CHAIN 7] Short TP BID BUY onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_new_short_tp_fb(self):
        """8. YENİ Short TP FRONT BUY"""
        print("[PSF CHAIN 8] 🎯 Short TP FRONT BUY başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - Short TP FB işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
        
        # Final FB skoruna göre en yüksek 3 hisse seç (TP için daha az)
        selected_stocks = self.get_top_stocks_by_score_with_smart_filtering(
            self.current_window, 
            'Final FB skor', 
            count=3, 
            ascending=False,  # En yüksek skorlar
            score_range=(0.01, 1500),  # 0 ve negatif değerleri filtrele
            order_side='BUY',
            smi_check=False  # Buy emirleri için SMI kontrolü yok
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 8] ❌ Final FB skor için uygun hisse bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        selected_tickers = set([ticker for ticker, score in selected_stocks])
        self.current_window.selected_tickers = selected_tickers
        
        # Reasoning logla
        for ticker, score in selected_stocks:
            msg = f"{ticker} seçildi - Short TP Final FB skor: {score}"
            print("[REASONING]", msg)
            log_reasoning(msg)
        
        # Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Front buy butonunu tetikle
        print("[DEBUG] send_front_buy_orders çağrılıyor...")
        self.current_window.send_front_buy_orders()
        
        print("[PSF CHAIN 8] Short TP FRONT BUY onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def extract_company_symbol(self, ticker):
        """
        Ticker'dan şirket adını çıkarır
        Örnekler: 'INN PRE' -> 'INN', 'PEB PRF' -> 'PEB', 'JAGX' -> 'JAGX'
        """
        if not ticker:
            return ""
        
        # Eğer boşluk varsa, ilk kısmı şirket adı olarak al
        if ' ' in ticker:
            return ticker.split(' ')[0]
        
        # Boşluk yoksa tüm ticker şirket adı
        return ticker
    
    def calculate_max_orders_for_company(self, company, candidate_list):
        """
        Belirli bir şirket için aday listesindeki toplam hisse sayısına göre
        maximum emir sayısını hesaplar
        
        Formül: min(3, max(1, round(total_stocks_for_company / 3)))
        """
        if not company or not candidate_list:
            return 1
        
        # Aynı şirketten kaç hisse var sayalım
        company_stocks_count = 0
        for candidate in candidate_list:
            ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
            if self.extract_company_symbol(ticker) == company:
                company_stocks_count += 1
        
        if company_stocks_count == 0:
            return 1
        
        # 3'e böl ve en yakın tam sayıya yuvarla
        calculated_max = round(company_stocks_count / 3)
        
        # Minimum 1, maksimum 3 sınırlarını uygula
        final_max = max(1, min(3, calculated_max))
        
        print(f"[COMPANY LIMIT] {company}: {company_stocks_count} hisse → {company_stocks_count}/3 = {company_stocks_count/3:.2f} → max {final_max} emir")
        
        return final_max
    
    def filter_by_company_limits(self, candidate_list, max_selections=None):
        """
        Aday hisse listesini şirket bazlı emir limitlerine göre filtreler
        Her şirketten sadece izin verilen maksimum sayıda hisse seçer (en yüksek skorlu olanları)
        
        Args:
            candidate_list: [(ticker, score), ...] formatında aday listesi
            max_selections: Toplam seçilecek maksimum hisse sayısı (None = limit yok)
        
        Returns:
            Filtrelenmiş [(ticker, score), ...] listesi
        """
        if not candidate_list:
            return []
        
        print(f"[COMPANY FILTER] 🔍 Şirket limiti uygulanıyor - {len(candidate_list)} aday")
        
        # Şirketlere göre grupla
        company_groups = {}
        for candidate in candidate_list:
            ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
            score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
            
            company = self.extract_company_symbol(ticker)
            if company not in company_groups:
                company_groups[company] = []
            
            company_groups[company].append((ticker, score))
        
        # Her şirket için maximum emir sayısını hesapla ve en yüksek skorluları seç
        filtered_candidates = []
        
        for company, company_candidates in company_groups.items():
            # Bu şirket için maksimum emir sayısını hesapla (tüm aday listeye göre)
            max_orders = self.calculate_max_orders_for_company(company, candidate_list)
            
            # Şirketin hisselerini score'a göre sırala (en yüksek score ilk)
            company_candidates_sorted = sorted(company_candidates, key=lambda x: x[1], reverse=True)
            
            # Maximum sayıda hisse seç
            selected_for_company = company_candidates_sorted[:max_orders]
            
            print(f"[COMPANY FILTER] {company}: {len(company_candidates)} aday → {len(selected_for_company)} seçildi")
            for ticker, score in selected_for_company:
                print(f"[COMPANY FILTER]   ✅ {ticker} (skor: {score:.2f})")
            
            # Seçilmeyenleri bildir
            if len(company_candidates_sorted) > max_orders:
                not_selected = company_candidates_sorted[max_orders:]
                print(f"[COMPANY FILTER] {company}: {len(not_selected)} hisse elendi:")
                for ticker, score in not_selected:
                    print(f"[COMPANY FILTER]   ❌ {ticker} (skor: {score:.2f}) - şirket limiti")
            
            filtered_candidates.extend(selected_for_company)
        
        # Eğer maksimum seçim sayısı belirtilmişse, son filtre uygula
        if max_selections and len(filtered_candidates) > max_selections:
            # Tüm listeden en yüksek skorluları seç
            filtered_candidates_sorted = sorted(filtered_candidates, key=lambda x: x[1], reverse=True)
            final_selection = filtered_candidates_sorted[:max_selections]
            
            print(f"[COMPANY FILTER] 📊 Final seçim: {len(filtered_candidates)} → {len(final_selection)} (toplam limit)")
            
            return final_selection
        
        print(f"[COMPANY FILTER] ✅ Toplam {len(filtered_candidates)} hisse seçildi")
        return filtered_candidates
    
    def apply_company_limits_to_approval_list(self, approval_list):
        """
        Emir onayı listesine şirket limitlerini uygular
        
        Args:
            approval_list: Onay bekleyen emirlerin listesi
            
        Returns:
            Filtrelenmiş emir listesi
        """
        if not approval_list:
            return []
        
        print(f"[COMPANY APPROVAL] 🎯 Emir onayında şirket limiti kontrolü: {len(approval_list)} emir")
        
        # Emir listesini (ticker, score) formatına dönüştür
        candidates = []
        for order_info in approval_list:
            ticker = order_info.get('ticker', '') if isinstance(order_info, dict) else order_info[0]
            # Score için farklı kaynaklardan veri al
            score = 0
            if isinstance(order_info, dict):
                score = order_info.get('score', 0) or order_info.get('final_thg', 0)
            elif isinstance(order_info, (list, tuple)) and len(order_info) > 1:
                score = order_info[1]
            
            # Eğer score yok ise, scored_stocks.csv'den al
            if score == 0:
                scores = self.get_scores_for_ticker(ticker)
                score = scores.get('FINAL_THG', 0)
            
            candidates.append((ticker, score))
        
        # Şirket limitlerini uygula
        filtered_candidates = self.filter_by_company_limits(candidates)
        
        # Orijinal format'a geri dönüştür
        filtered_approval_list = []
        filtered_tickers = [item[0] for item in filtered_candidates]
        
        for order_info in approval_list:
            ticker = order_info.get('ticker', '') if isinstance(order_info, dict) else order_info[0]
            if ticker in filtered_tickers:
                filtered_approval_list.append(order_info)
        
        print(f"[COMPANY APPROVAL] ✅ Şirket limiti sonrası: {len(filtered_approval_list)} emir onaylandı")
        
        return filtered_approval_list 
