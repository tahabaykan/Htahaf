"""
Pressure Analyzer - Alış/Satış Baskısı Analizi
Preferred stock gibi spread'i geniş ve likiditesi düşük ürünlerde
satış/alış baskısını ölçmek için ağırlıklı skor modeli

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
=================================
"""

import pandas as pd
import os
from datetime import datetime, timedelta
from collections import defaultdict
import time

class PressureAnalyzer:
    def __init__(self, hammer_client, main_window=None):
        """
        Pressure Analyzer başlatıcı
        
        Args:
            hammer_client: HammerClient instance
            main_window: MainWindow instance (AVG_ADV için)
        """
        self.hammer = hammer_client
        self.main_window = main_window
        
        # Print ağırlıkları - Büyük lotlar için daha yüksek ağırlık
        # Lot büyüklüğüne göre logaritmik ağırlık (büyük lotlar daha önemli)
        
        # Zaman dilimleri - Sadece 1 günlük analiz
        self.time_windows = {
            '1day': {'minutes': 390, 'weight': 1.0}  # Sadece trading day
        }
    
    def get_print_weight(self, size):
        """
        Print lot büyüklüğüne göre ağırlık döndür
        Büyük lotlar için daha yüksek ağırlık (logaritmik ölçek)
        
        Args:
            size: Print lot büyüklüğü
            
        Returns:
            float: Print ağırlığı
        """
        size = int(size)
        
        if size < 10:
            return 0.0  # < 10 lot sayılmaz
        elif size < 25:
            return 0.1
        elif size < 50:
            return 0.25
        elif size < 100:
            return 0.5
        elif size < 200:
            return 1.0
        elif size < 500:
            return 1.5
        elif size < 1000:
            return 2.0
        elif size < 5000:
            return 3.0
        else:  # >= 5000 lot
            return 4.0  # Çok büyük lotlar için maksimum ağırlık
    
    def get_ticks_for_symbol(self, symbol, minutes_back=15):
        """
        Hammer Pro'dan son N dakikanın tick verilerini al
        
        Args:
            symbol: Hisse sembolü (örn: "GS PRA")
            minutes_back: Kaç dakika geriye gidilecek
            
        Returns:
            list: Tick verileri listesi
        """
        try:
            if not self.hammer or not self.hammer.is_connected():
                print(f"[PRESSURE] ❌ Hammer client bağlı değil")
                return []
            
            # Sembol formatını düzelt ("GS PRA" -> "GS-A")
            formatted_symbol = symbol
            if " PR" in symbol:
                parts = symbol.split(" PR")
                if len(parts) == 2:
                    base_symbol = parts[0]
                    suffix = parts[1]
                    formatted_symbol = f"{base_symbol}-{suffix}"
            
            # HammerClient'ın get_ticks metodunu kullan
            result = self.hammer.get_ticks(formatted_symbol, lastFew=1000, tradesOnly=False, regHoursOnly=True)
            
            if not result or not isinstance(result, dict):
                print(f"[PRESSURE] ⚠️ {symbol} tick verisi alınamadı")
                return []
            
            ticks = result.get('data', [])
            
            # Son N dakikanın başlangıç zamanı (naive datetime kullan)
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=minutes_back)
            
            # Tick'leri filtrele (sadece trade olanları ve zaman aralığında olanlar)
            trade_ticks = []
            skipped_count = 0
            for tick in ticks:
                try:
                    # Size > 0 ise trade
                    tick_size = float(tick.get('s', 0)) if tick.get('s') else 0.0
                    if tick_size <= 0:
                        continue
                    
                    # Timestamp'i parse et
                    tick_time_str = tick.get('t', '')
                    if not tick_time_str:
                        # Timestamp yoksa son N tick'i al (zaman filtresi olmadan)
                        trade_ticks.append({
                            'timestamp': tick_time_str,
                            'price': float(tick.get('p', 0)) if tick.get('p') else 0.0,
                            'size': tick_size,
                            'bid': float(tick.get('b', 0)) if tick.get('b') else None,
                            'ask': float(tick.get('a', 0)) if tick.get('a') else None
                        })
                        continue
                    
                    # ISO formatını parse et - daha esnek parsing
                    try:
                        # Önce Z'yi kaldır, sonra parse et
                        tick_time_str_clean = tick_time_str.replace('Z', '').replace('+00:00', '')
                        # ISO format: 2025-08-05T18:07:04.896
                        if 'T' in tick_time_str_clean:
                            tick_time = datetime.fromisoformat(tick_time_str_clean)
                        else:
                            # Format yoksa skip et ama tick'i ekle
                            trade_ticks.append({
                                'timestamp': tick_time_str,
                                'price': float(tick.get('p', 0)) if tick.get('p') else 0.0,
                                'size': tick_size,
                                'bid': float(tick.get('b', 0)) if tick.get('b') else None,
                                'ask': float(tick.get('a', 0)) if tick.get('a') else None
                            })
                            continue
                        
                        # Timezone bilgisi yoksa naive datetime olarak kabul et
                        if tick_time.tzinfo is None:
                            # Naive datetime'ları karşılaştır
                            if tick_time >= start_time:
                                trade_ticks.append({
                                    'timestamp': tick_time_str,
                                    'price': float(tick.get('p', 0)) if tick.get('p') else 0.0,
                                    'size': tick_size,
                                    'bid': float(tick.get('b', 0)) if tick.get('b') else None,
                                    'ask': float(tick.get('a', 0)) if tick.get('a') else None
                                })
                            else:
                                skipped_count += 1
                        else:
                            # Timezone var, end_time'a da timezone ekle
                            if end_time.tzinfo is None:
                                # End time'a timezone ekle (UTC varsay)
                                end_time_tz = end_time.replace(tzinfo=tick_time.tzinfo)
                                start_time_tz = end_time_tz - timedelta(minutes=minutes_back)
                            else:
                                start_time_tz = start_time
                            
                            if tick_time >= start_time_tz:
                                trade_ticks.append({
                                    'timestamp': tick_time_str,
                                    'price': float(tick.get('p', 0)) if tick.get('p') else 0.0,
                                    'size': tick_size,
                                    'bid': float(tick.get('b', 0)) if tick.get('b') else None,
                                    'ask': float(tick.get('a', 0)) if tick.get('a') else None
                                })
                            else:
                                skipped_count += 1
                    except (ValueError, AttributeError) as e:
                        # Parse edilemezse bile tick'i ekle (zaman filtresi olmadan)
                        trade_ticks.append({
                            'timestamp': tick_time_str,
                            'price': float(tick.get('p', 0)) if tick.get('p') else 0.0,
                            'size': tick_size,
                            'bid': float(tick.get('b', 0)) if tick.get('b') else None,
                            'ask': float(tick.get('a', 0)) if tick.get('a') else None
                        })
                except Exception as e:
                    continue
            
            # Eğer zaman filtresi çok fazla tick'i elediyse, son N tick'i al (zaman filtresi olmadan)
            if len(trade_ticks) == 0 and len(ticks) > 0:
                print(f"[PRESSURE] ⚠️ {symbol}: Zaman filtresi çok sıkı, son {min(100, len(ticks))} tick alınıyor")
                for tick in ticks[-100:]:  # Son 100 tick
                    tick_size = float(tick.get('s', 0)) if tick.get('s') else 0.0
                    if tick_size > 0:
                        trade_ticks.append({
                            'timestamp': tick.get('t', ''),
                            'price': float(tick.get('p', 0)) if tick.get('p') else 0.0,
                            'size': tick_size,
                            'bid': float(tick.get('b', 0)) if tick.get('b') else None,
                            'ask': float(tick.get('a', 0)) if tick.get('a') else None
                        })
            
            print(f"[PRESSURE] ✅ {symbol}: {len(trade_ticks)} trade tick bulundu (son {minutes_back} dakika, {skipped_count} tick atlandı)")
            return trade_ticks
            
        except Exception as e:
            print(f"[PRESSURE] ❌ {symbol} tick alma hatası: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_symbol_snapshot(self, symbol, ticks=None):
        """
        Symbol snapshot verilerini al (bid, ask, prevClose, vb.)
        L1 streaming verilerini kullanır, yoksa tick verilerinden çıkarır
        
        Args:
            symbol: Hisse sembolü (örn: "GS PRA")
            ticks: Tick verileri (opsiyonel, bid/ask yoksa bunlardan çıkarılır)
            
        Returns:
            dict: Snapshot verileri (bid/ask yoksa bile varsayılan değerlerle döner)
        """
        try:
            bid = 0.0
            ask = 0.0
            last = 0.0
            prev_close = 0.0
            spread = 0.0
            
            # Önce HammerClient'ın get_market_data metodunu kullan
            if self.hammer and self.hammer.is_connected():
                market_data = self.hammer.get_market_data(symbol)
                
                if not market_data:
                    # Eğer market_data yoksa, sembol formatını manuel düzelt ve tekrar dene
                    formatted_symbol = symbol
                    if " PR" in symbol:
                        parts = symbol.split(" PR")
                        if len(parts) == 2:
                            base_symbol = parts[0]
                            suffix = parts[1]
                            formatted_symbol = f"{base_symbol}-{suffix}"
                    
                    # Display symbol formatında da dene (market_data display_symbol ile saklanıyor)
                    market_data = self.hammer.market_data.get(symbol, {})
                    if not market_data:
                        market_data = self.hammer.market_data.get(formatted_symbol, {})
                
                if market_data:
                    bid = float(market_data.get('bid', 0)) if market_data.get('bid') else 0.0
                    ask = float(market_data.get('ask', 0)) if market_data.get('ask') else 0.0
                    last = float(market_data.get('last', 0)) or float(market_data.get('price', 0)) if market_data.get('last') or market_data.get('price') else 0.0
                    prev_close = float(market_data.get('prevClose', 0)) or float(market_data.get('prev_close', 0)) if market_data.get('prevClose') or market_data.get('prev_close') else 0.0
            
            # Eğer bid/ask yoksa, tick verilerinden çıkar
            if (bid <= 0 or ask <= 0) and ticks:
                bid_prices = []
                ask_prices = []
                prices = []
                
                for tick in ticks:
                    tick_price = tick.get('price', 0)
                    if tick_price > 0:
                        prices.append(tick_price)
                    
                    tick_bid = tick.get('bid')
                    tick_ask = tick.get('ask')
                    
                    if tick_bid and tick_bid > 0:
                        bid_prices.append(tick_bid)
                    if tick_ask and tick_ask > 0:
                        ask_prices.append(tick_ask)
                
                # En son bid/ask değerlerini kullan
                if bid_prices:
                    bid = bid_prices[-1]
                if ask_prices:
                    ask = ask_prices[-1]
                
                # Last price'ı tick'lerden al
                if prices:
                    last = prices[-1]
            
            # Spread hesapla (sadece bid ve ask varsa)
            if ask > 0 and bid > 0:
                spread = ask - bid
            else:
                spread = None  # Bid/ask yoksa spread de yok
            
            # Bid/ask yoksa None döndür (varsayılan değer kullanma)
            if bid <= 0 or ask <= 0:
                return {
                    'bid': None,  # N/A
                    'ask': None,  # N/A
                    'last': last if last > 0 else None,
                    'prevClose': prev_close if prev_close > 0 else None,
                    'spread': None  # N/A
                }
            
            return {
                'bid': bid,
                'ask': ask,
                'last': last if last > 0 else None,
                'prevClose': prev_close if prev_close > 0 else None,
                'spread': spread
            }
            
        except Exception as e:
            print(f"[PRESSURE] ⚠️ {symbol} snapshot alma hatası: {e}")
            # Hata olsa bile None döndür (varsayılan değer kullanma)
            return {
                'bid': None,
                'ask': None,
                'last': None,
                'prevClose': None,
                'spread': None
            }
    
    def classify_print_side(self, print_price, bid, ask, ticks=None):
        """
        Print'in bid tarafında mı ask tarafında mı olduğunu belirle
        Bid/ask yoksa tick verilerinden tahmin et
        
        Args:
            print_price: Print fiyatı
            bid: Bid fiyatı
            ask: Ask fiyatı
            ticks: Tick verileri (opsiyonel, bid/ask yoksa kullanılır)
            
        Returns:
            str: 'bid' (satış baskısı) veya 'ask' (alış baskısı) veya None
        """
        # Bid/ask varsa normal mantık
        if bid > 0 and ask > 0:
            bid_distance = abs(print_price - bid)
            ask_distance = abs(print_price - ask)
            
            if bid_distance < ask_distance:
                return 'bid'  # Bid tarafında = SATIŞ baskısı
            else:
                return 'ask'  # Ask tarafında = ALIŞ baskısı
        
        # Bid/ask yoksa, tick verilerinden ortalama fiyat hesapla
        if ticks and len(ticks) > 0:
            prices = [t.get('price', 0) for t in ticks if t.get('price', 0) > 0]
            if prices:
                avg_price = sum(prices) / len(prices)
                # Print fiyatı ortalamanın altındaysa bid (satış), üstündeyse ask (alış)
                if print_price < avg_price:
                    return 'bid'  # Satış baskısı
                else:
                    return 'ask'  # Alış baskısı
        
        # Hiçbir veri yoksa, print fiyatına göre tahmin et (basit mantık)
        # Bu durumda None döndür, analiz diğer metriklerle devam etsin
        return None
    
    def analyze_bid_ask_resilience(self, ticks, snapshot, time_window_minutes):
        """
        Bid/Ask dayanıklılık analizi
        
        Args:
            ticks: Tick verileri listesi
            snapshot: Symbol snapshot verileri
            time_window_minutes: Zaman penceresi (dakika)
            
        Returns:
            dict: Bid/Ask dayanıklılık metrikleri
        """
        try:
            if not ticks or not snapshot:
                return {
                    'bid_hold_time': 0.0,
                    'bid_volume_resistance': 0.0,
                    'bid_turnover_rate': 0.0,
                    'ask_hold_time': 0.0,
                    'ask_volume_resistance': 0.0,
                    'ask_turnover_rate': 0.0
                }
            
            # Bid/Ask değişimlerini takip et
            bid_changes = []
            ask_changes = []
            bid_volumes = []
            ask_volumes = []
            
            current_bid = snapshot.get('bid')
            current_ask = snapshot.get('ask')
            
            # Bid/ask None kontrolü
            if current_bid is None:
                current_bid = 0.0
            if current_ask is None:
                current_ask = 0.0
            
            last_bid_change_time = None
            last_ask_change_time = None
            
            for tick in ticks:
                tick_bid = tick.get('bid')
                tick_ask = tick.get('ask')
                tick_time = tick.get('timestamp')
                tick_size = tick.get('size', 0)
                
                if tick_bid and tick_bid != current_bid:
                    # Bid değişti
                    if last_bid_change_time:
                        hold_time = (datetime.fromisoformat(tick_time.replace('Z', '+00:00')) - 
                                   datetime.fromisoformat(last_bid_change_time.replace('Z', '+00:00'))).total_seconds() / 60.0
                        bid_changes.append(hold_time)
                    
                    # Bid'e vurulan volume'u hesapla
                    if tick_size > 0:
                        print_side = self.classify_print_side(tick.get('price', 0), current_bid, current_ask, ticks=ticks)
                        if print_side == 'bid':
                            bid_volumes.append(tick_size)
                    
                    current_bid = tick_bid
                    last_bid_change_time = tick_time
                
                if tick_ask and tick_ask != current_ask:
                    # Ask değişti
                    if last_ask_change_time:
                        hold_time = (datetime.fromisoformat(tick_time.replace('Z', '+00:00')) - 
                                   datetime.fromisoformat(last_ask_change_time.replace('Z', '+00:00'))).total_seconds() / 60.0
                        ask_changes.append(hold_time)
                    
                    # Ask'e vurulan volume'u hesapla
                    if tick_size > 0:
                        print_side = self.classify_print_side(tick.get('price', 0), current_bid, current_ask, ticks=ticks)
                        if print_side == 'ask':
                            ask_volumes.append(tick_size)
                    
                    current_ask = tick_ask
                    last_ask_change_time = tick_time
            
            # Metrikleri hesapla
            bid_hold_time = sum(bid_changes) / len(bid_changes) if bid_changes else 0.0
            ask_hold_time = sum(ask_changes) / len(ask_changes) if ask_changes else 0.0
            
            bid_volume_resistance = sum(bid_volumes) / len(bid_changes) if bid_changes and bid_volumes else 0.0
            ask_volume_resistance = sum(ask_volumes) / len(ask_changes) if ask_changes and ask_volumes else 0.0
            
            bid_turnover_rate = len(bid_changes) / time_window_minutes if time_window_minutes > 0 else 0.0
            ask_turnover_rate = len(ask_changes) / time_window_minutes if time_window_minutes > 0 else 0.0
            
            return {
                'bid_hold_time': bid_hold_time,
                'bid_volume_resistance': bid_volume_resistance,
                'bid_turnover_rate': bid_turnover_rate,
                'ask_hold_time': ask_hold_time,
                'ask_volume_resistance': ask_volume_resistance,
                'ask_turnover_rate': ask_turnover_rate
            }
            
        except Exception as e:
            print(f"[PRESSURE] ❌ Bid/Ask dayanıklılık analizi hatası: {e}")
            return {
                'bid_hold_time': 0.0,
                'bid_volume_resistance': 0.0,
                'bid_turnover_rate': 0.0,
                'ask_hold_time': 0.0,
                'ask_volume_resistance': 0.0,
                'ask_turnover_rate': 0.0
            }
    
    def analyze_print_pattern(self, ticks, snapshot):
        """
        Ağırlıklı print pattern analizi
        
        Args:
            ticks: Tick verileri listesi
            snapshot: Symbol snapshot verileri
            
        Returns:
            dict: Print pattern metrikleri
        """
        try:
            if not ticks or not snapshot:
                return {
                    'bid_print_ratio': 0.0,
                    'ask_print_ratio': 0.0,
                    'weighted_bid_volume': 0.0,
                    'weighted_ask_volume': 0.0,
                    'total_weighted_volume': 0.0
                }
            
            bid = snapshot.get('bid')
            ask = snapshot.get('ask')
            
            # Bid/ask None kontrolü
            if bid is None:
                bid = 0.0
            if ask is None:
                ask = 0.0
            
            weighted_bid_prints = 0.0
            weighted_ask_prints = 0.0
            total_weighted_volume = 0.0
            
            for tick in ticks:
                tick_price = tick.get('price', 0)
                tick_size = tick.get('size', 0)
                
                if tick_size <= 0:
                    continue
                
                # Print ağırlığı
                weight = self.get_print_weight(tick_size)
                if weight == 0.0:
                    continue
                
                # Print tarafı (bid/ask yoksa tick verilerinden tahmin et)
                print_side = self.classify_print_side(tick_price, bid, ask, ticks=ticks)
                
                weighted_volume = weight * tick_size
                total_weighted_volume += weighted_volume
                
                if print_side == 'bid':
                    weighted_bid_prints += weighted_volume
                elif print_side == 'ask':
                    weighted_ask_prints += weighted_volume
                # print_side None ise (bid/ask yok ve tahmin edilemedi), volume'u toplam volume'e ekle ama bid/ask'a ekleme
            
            bid_print_ratio = weighted_bid_prints / total_weighted_volume if total_weighted_volume > 0 else 0.0
            ask_print_ratio = weighted_ask_prints / total_weighted_volume if total_weighted_volume > 0 else 0.0
            
            return {
                'bid_print_ratio': bid_print_ratio,
                'ask_print_ratio': ask_print_ratio,
                'weighted_bid_volume': weighted_bid_prints,
                'weighted_ask_volume': weighted_ask_prints,
                'total_weighted_volume': total_weighted_volume
            }
            
        except Exception as e:
            print(f"[PRESSURE] ❌ Print pattern analizi hatası: {e}")
            return {
                'bid_print_ratio': 0.0,
                'ask_print_ratio': 0.0,
                'weighted_bid_volume': 0.0,
                'weighted_ask_volume': 0.0,
                'total_weighted_volume': 0.0
            }
    
    def analyze_price_trend(self, ticks):
        """
        Fiyat trend analizi - EN ÖNEMLİ METRİK
        Fiyat zamanla artıyor mu azalıyor mu?
        
        Args:
            ticks: Tick verileri listesi (zaman sıralı)
            
        Returns:
            dict: Trend metrikleri
        """
        try:
            if not ticks or len(ticks) < 2:
                return {
                    'price_trend_score': 0.0,  # 0 = dengeli, >0 = yükseliş (alış), <0 = düşüş (satış)
                    'trend_strength': 0.0
                }
            
            # Fiyatları zaman sırasına göre al
            prices = []
            for tick in ticks:
                price = tick.get('price', 0)
                if price > 0:
                    prices.append(price)
            
            if len(prices) < 2:
                return {
                    'price_trend_score': 0.0,
                    'trend_strength': 0.0
                }
            
            # İlk ve son fiyat
            first_price = prices[0]
            last_price = prices[-1]
            
            # Fiyat değişimi (yüzde)
            price_change_pct = ((last_price - first_price) / first_price) * 100 if first_price > 0 else 0.0
            
            # Trend skoru: -1.0 (güçlü düşüş) ile +1.0 (güçlü yükseliş) arası
            # Normalize et: -100% değişim = -1.0, +100% değişim = +1.0
            # Ama gerçekçi değişimler genelde %0-5 arası, o yüzden tanh kullan
            import math
            trend_score = math.tanh(price_change_pct / 5.0)  # %5 değişim = ~0.76 skor
            
            # Trend gücü: Fiyat değişiminin tutarlılığı (varyans)
            if len(prices) > 2:
                price_changes = []
                for i in range(1, len(prices)):
                    change = prices[i] - prices[i-1]
                    if prices[i-1] > 0:
                        price_changes.append(change / prices[i-1])
                
                if price_changes:
                    # Pozitif değişimlerin oranı
                    positive_changes = sum(1 for c in price_changes if c > 0)
                    trend_strength = positive_changes / len(price_changes) if price_changes else 0.5
                    # Trend skorunu güç ile çarp
                    trend_score = trend_score * (2 * trend_strength - 1)  # 0.5 = dengeli, 1.0 = güçlü trend
            else:
                trend_strength = 0.5
            
            return {
                'price_trend_score': trend_score,  # >0 = alış baskısı, <0 = satış baskısı
                'trend_strength': abs(trend_score),
                'price_change_pct': price_change_pct
            }
            
        except Exception as e:
            print(f"[PRESSURE] ❌ Fiyat trend analizi hatası: {e}")
            return {
                'price_trend_score': 0.0,
                'trend_strength': 0.0,
                'price_change_pct': 0.0
            }
    
    def analyze_price_position(self, snapshot, ticks=None):
        """
        Fiyat konumu analizi
        - Bid last print'e yakınsa → Satış baskısı
        - Ask last print'e yakınsa → Alış baskısı
        
        Args:
            snapshot: Symbol snapshot verileri
            ticks: Tick verileri (opsiyonel)
            
        Returns:
            dict: Fiyat konumu metrikleri
        """
        try:
            if not snapshot:
                return {
                    'bid_distance_score': 0.0,
                    'ask_distance_score': 0.0
                }
            
            bid = snapshot.get('bid')
            ask = snapshot.get('ask')
            last = snapshot.get('last', 0)
            spread = snapshot.get('spread', 0)
            
            # Bid/ask yoksa N/A döndür (varsayılan değer kullanma)
            if bid is None or ask is None or bid <= 0 or ask <= 0:
                return {
                    'bid_distance_score': None,  # N/A
                    'ask_distance_score': None   # N/A
                }
            
            if last <= 0 or spread <= 0:
                return {
                    'bid_distance_score': 0.0,
                    'ask_distance_score': 0.0
                }
            
            # Last Print'in bid/ask'e uzaklığı
            last_to_bid_distance = abs(last - bid)
            last_to_ask_distance = abs(ask - last)
            
            # Normalize et (spread'e göre)
            bid_distance_score = last_to_bid_distance / spread if spread > 0 else 0.0
            ask_distance_score = last_to_ask_distance / spread if spread > 0 else 0.0
            
            # Bid'e yakınsa (düşük distance) → Yüksek satış baskısı skoru
            # Ask'e yakınsa (düşük distance) → Yüksek alış baskısı skoru
            # Tersine çevir: düşük distance = yüksek skor
            bid_pressure_score = 1.0 - min(bid_distance_score, 1.0)  # 0-1 arası, bid'e yakınsa yüksek
            ask_pressure_score = 1.0 - min(ask_distance_score, 1.0)  # 0-1 arası, ask'e yakınsa yüksek
            
            return {
                'bid_distance_score': bid_pressure_score,  # Yüksek = bid'e yakın = satış baskısı
                'ask_distance_score': ask_pressure_score   # Yüksek = ask'e yakın = alış baskısı
            }
            
        except Exception as e:
            print(f"[PRESSURE] ❌ Fiyat konumu analizi hatası: {e}")
            return {
                'bid_distance_score': 0.0,
                'ask_distance_score': 0.0
            }
    
    def get_avg_adv(self, symbol):
        """
        AVG_ADV değerini al (CSV'den veya main_window'dan)
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            float: AVG_ADV değeri
        """
        try:
            # Önce main_window'dan al
            if self.main_window and hasattr(self.main_window, 'df'):
                df = self.main_window.df
                if df is not None and not df.empty:
                    symbol_row = df[df['Symbol'] == symbol]
                    if not symbol_row.empty:
                        avg_adv = symbol_row.iloc[0].get('AVG_ADV', 0)
                        if pd.notna(avg_adv) and avg_adv > 0:
                            return float(avg_adv)
            
            # Fallback: CSV'den oku
            csv_file = "mini450.csv"
            if os.path.exists(csv_file):
                df = pd.read_csv(csv_file, encoding='utf-8-sig')
                symbol_row = df[df['Symbol'] == symbol]
                if not symbol_row.empty:
                    avg_adv = symbol_row.iloc[0].get('AVG_ADV', 0)
                    if pd.notna(avg_adv) and avg_adv > 0:
                        return float(avg_adv)
            
            return 0.0
            
        except Exception as e:
            print(f"[PRESSURE] ⚠️ {symbol} AVG_ADV alma hatası: {e}")
            return 0.0
    
    def calculate_pressure_scores(self, symbol, grpan_price=None):
        """
        Alış/Satış baskısı skorlarını hesapla
        
        Args:
            symbol: Hisse sembolü
            grpan_price: GRPAN fiyatı (opsiyonel)
            
        Returns:
            dict: Pressure skorları ve detaylar
        """
        try:
            print(f"[PRESSURE] 🔄 {symbol} baskı analizi başlatılıyor...")
            
            # AVG_ADV al
            avg_adv = self.get_avg_adv(symbol)
            
            # Zaman dilimlerine göre skorlar
            time_weighted_buy_pressure = 0.0
            time_weighted_sell_pressure = 0.0
            
            all_metrics = {}
            
            # İlk önce tüm tick verilerini topla (snapshot için)
            all_ticks = []
            for window_name, window_config in self.time_windows.items():
                minutes = window_config['minutes']
                ticks = self.get_ticks_for_symbol(symbol, minutes_back=minutes)
                all_ticks.extend(ticks)
            
            # Snapshot al (tick verileriyle birlikte, bid/ask yoksa None döner)
            snapshot = self.get_symbol_snapshot(symbol, ticks=all_ticks if all_ticks else None)
            if not snapshot:
                snapshot = {
                    'bid': None,
                    'ask': None,
                    'last': None,
                    'prevClose': None,
                    'spread': None
                }
            
            for window_name, window_config in self.time_windows.items():
                minutes = window_config['minutes']
                weight = window_config['weight']
                
                print(f"[PRESSURE] 📊 {symbol} {window_name} analizi ({minutes} dakika)...")
                
                # Tick verilerini al
                ticks = self.get_ticks_for_symbol(symbol, minutes_back=minutes)
                
                if not ticks:
                    print(f"[PRESSURE] ⚠️ {symbol} {window_name} için tick verisi yok")
                    continue
                
                # 1. EN ÖNEMLİ: Fiyat trend analizi (50% ağırlık)
                price_trend = self.analyze_price_trend(ticks)
                trend_score = price_trend.get('price_trend_score', 0.0)  # >0 = alış, <0 = satış
                
                # 2. İKİNCİ ÖNEMLİ: Volume/AVG_ADV oranı (30% ağırlık)
                print_pattern = self.analyze_print_pattern(ticks, snapshot)
                total_weighted_volume = print_pattern.get('total_weighted_volume', 0.0)
                time_window_ratio = minutes / 390.0  # Trading day = 390 minutes
                volume_ratio = total_weighted_volume / (avg_adv * time_window_ratio) if avg_adv > 0 and time_window_ratio > 0 else 0.0
                # Volume ratio'yu normalize et (0-1 arası)
                normalized_volume_ratio = min(volume_ratio / 2.0, 1.0) if volume_ratio > 0 else 0.0  # 2x AVG_ADV = 1.0
                
                # 3. Bid/Ask distance analizi (20% ağırlık) - Bid/ask yoksa N/A
                price_position = self.analyze_price_position(snapshot, ticks=ticks)
                bid_distance_score = price_position.get('bid_distance_score')
                ask_distance_score = price_position.get('ask_distance_score')
                
                # Bid/ask yoksa (N/A), sadece trend ve volume kullan
                has_bid_ask = bid_distance_score is not None and ask_distance_score is not None
                
                if has_bid_ask:
                    # Bid/ask varsa: Trend (50%) + Volume (30%) + Bid/Ask Distance (20%)
                    # Alış baskısı: trend pozitifse + ask'e yakınsa
                    buy_pressure = (
                        max(trend_score, 0.0) * 0.50 +  # Fiyat artıyorsa alış baskısı
                        normalized_volume_ratio * 0.30 +  # Yüksek volume = yüksek baskı
                        (ask_distance_score or 0.0) * 0.20  # Ask'e yakınsa alış baskısı
                    )
                    
                    # Satış baskısı: trend negatifse + bid'e yakınsa
                    sell_pressure = (
                        abs(min(trend_score, 0.0)) * 0.50 +  # Fiyat düşüyorsa satış baskısı
                        normalized_volume_ratio * 0.30 +  # Yüksek volume = yüksek baskı
                        (bid_distance_score or 0.0) * 0.20  # Bid'e yakınsa satış baskısı
                    )
                else:
                    # Bid/ask yoksa: Sadece Trend (70%) + Volume (30%)
                    print(f"[PRESSURE] ⚠️ {symbol} bid/ask yok, sadece trend ve volume kullanılıyor")
                    buy_pressure = (
                        max(trend_score, 0.0) * 0.70 +  # Fiyat artıyorsa alış baskısı
                        normalized_volume_ratio * 0.30  # Yüksek volume = yüksek baskı
                    )
                    
                    sell_pressure = (
                        abs(min(trend_score, 0.0)) * 0.70 +  # Fiyat düşüyorsa satış baskısı
                        normalized_volume_ratio * 0.30  # Yüksek volume = yüksek baskı
                    )
                
                # Zaman ağırlıklı toplam
                time_weighted_buy_pressure += buy_pressure * weight
                time_weighted_sell_pressure += sell_pressure * weight
                
                # Metrikleri kaydet
                all_metrics[window_name] = {
                    'buy_pressure': buy_pressure,
                    'sell_pressure': sell_pressure,
                    'price_trend': price_trend,
                    'volume_ratio': volume_ratio,
                    'normalized_volume_ratio': normalized_volume_ratio,
                    'price_position': price_position,
                    'has_bid_ask': has_bid_ask,
                    'print_pattern': print_pattern
                }
            
            # Net baskı skoru
            net_pressure = time_weighted_buy_pressure - time_weighted_sell_pressure
            
            # Sınıflandırma
            if net_pressure > 0.6:
                pressure_class = "Güçlü Alış Baskısı"
            elif net_pressure > 0.3:
                pressure_class = "Orta Alış Baskısı"
            elif net_pressure > -0.3:
                pressure_class = "Dengeli"
            elif net_pressure > -0.6:
                pressure_class = "Orta Satış Baskısı"
            else:
                pressure_class = "Güçlü Satış Baskısı"
            
            result = {
                'symbol': symbol,
                'buy_pressure': time_weighted_buy_pressure,  # main_window'da buy_pressure kullanılıyor
                'sell_pressure': time_weighted_sell_pressure,  # main_window'da sell_pressure kullanılıyor
                'buy_pressure_score': time_weighted_buy_pressure,
                'sell_pressure_score': time_weighted_sell_pressure,
                'net_pressure': net_pressure,
                'pressure_class': pressure_class,
                'snapshot': snapshot,
                'grpan': grpan_price if grpan_price else 'N/A',  # main_window'da grpan kullanılıyor
                'grpan_price': grpan_price,
                'bid': snapshot.get('bid'),  # main_window'da bid kullanılıyor
                'ask': snapshot.get('ask'),  # main_window'da ask kullanılıyor
                'spread': snapshot.get('spread'),  # main_window'da spread kullanılıyor
                'last': snapshot.get('last'),  # main_window'da last kullanılıyor
                'avg_adv': avg_adv,
                'time_window_metrics': all_metrics
            }
            
            print(f"[PRESSURE] ✅ {symbol} analiz tamamlandı:")
            print(f"  Buy Pressure: {time_weighted_buy_pressure:.3f}")
            print(f"  Sell Pressure: {time_weighted_sell_pressure:.3f}")
            print(f"  Net Pressure: {net_pressure:.3f} ({pressure_class})")
            
            return result
            
        except Exception as e:
            print(f"[PRESSURE] ❌ {symbol} baskı analizi hatası: {e}")
            import traceback
            traceback.print_exc()
            return None

