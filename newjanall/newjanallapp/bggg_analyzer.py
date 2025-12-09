"""
BGGG Analyzer - Bugünün GRPAN Grup Analizi
Her hisse için bugünün printlerinden BGRPAN hesaplar ve grup sapmalarını analiz eder
"""

import pandas as pd
import os
from datetime import datetime, timedelta
from collections import defaultdict

class BGGGAnalyzer:
    def __init__(self, hammer_client, main_window=None):
        """
        BGGG Analyzer başlatıcı
        
        Args:
            hammer_client: HammerClient instance
            main_window: MainWindow instance (Previous Close ve CGRUP için)
        """
        self.hammer = hammer_client
        self.main_window = main_window
    
    def get_bgrpan_price(self, symbol):
        """
        Bugünün printlerinden BGRPAN (Bugünün GRPAN) hesapla
        Sadece bugünün printlerini kullanır
        
        Args:
            symbol: Hisse sembolü (örn: "GS PRA")
            
        Returns:
            float: BGRPAN fiyatı veya None
        """
        try:
            if not self.hammer or not self.hammer.is_connected():
                return None
            
            # Sembol formatını düzelt ("GS PRA" -> "GS-A")
            formatted_symbol = symbol
            if " PR" in symbol:
                parts = symbol.split(" PR")
                if len(parts) == 2:
                    base_symbol = parts[0]
                    suffix = parts[1]
                    formatted_symbol = f"{base_symbol}-{suffix}"
            
            # Bugünün tarihi
            today = datetime.now().date()
            
            # HammerClient'ın get_ticks metodunu kullan (daha fazla tick al)
            result = self.hammer.get_ticks(formatted_symbol, lastFew=2000, tradesOnly=False, regHoursOnly=True)
            
            if not result or not isinstance(result, dict):
                return None
            
            ticks = result.get('data', [])
            
            # Bugünün printlerini filtrele
            today_ticks = []
            for tick in ticks:
                try:
                    tick_time_str = tick.get('t', '')
                    if not tick_time_str:
                        # Timestamp yoksa, tick'i ekle (fallback - bugünün printi olarak kabul et)
                        today_ticks.append(tick)
                        continue
                    
                    # ISO formatını parse et
                    tick_time_str_clean = tick_time_str.replace('Z', '').replace('+00:00', '')
                    if 'T' in tick_time_str_clean:
                        try:
                            tick_time = datetime.fromisoformat(tick_time_str_clean)
                            # Timezone bilgisi yoksa naive datetime olarak kabul et
                            if tick_time.tzinfo is None:
                                # Bugünün printleri (bugünün tarihinde)
                                if tick_time.date() == today:
                                    today_ticks.append(tick)
                            else:
                                # Timezone var, bugünün tarihine çevir ve kontrol et
                                # Local timezone'a çevir
                                from datetime import timezone
                                if tick_time.tzinfo:
                                    tick_time_local = tick_time.astimezone()
                                else:
                                    tick_time_local = tick_time
                                if tick_time_local.date() == today:
                                    today_ticks.append(tick)
                        except (ValueError, AttributeError):
                            # Parse edilemezse, tick'i ekle (fallback - bugünün printi olarak kabul et)
                            today_ticks.append(tick)
                    else:
                        # Format yoksa, tick'i ekle (fallback)
                        today_ticks.append(tick)
                except Exception:
                    continue
            
            if len(today_ticks) == 0:
                print(f"[BGGG] ⚠️ {symbol}: Bugün için tick verisi yok")
                return None
            
            # 9 lot ve altındaki print'leri IGNORE et
            filtered_ticks = [tick for tick in today_ticks if tick.get('s', 0) > 9]
            
            if len(filtered_ticks) < 5:
                print(f"[BGGG] ⚠️ {symbol}: Yetersiz bugünün tick verisi ({len(filtered_ticks)} tick, 10+ lot)")
                return None
            
            # Son 15 tick'i al (bugünün printleri içinden)
            last_15_ticks = filtered_ticks[-15:] if len(filtered_ticks) >= 15 else filtered_ticks
            
            # Fiyatları ve ağırlıkları topla
            weighted_prices = []
            
            for tick in last_15_ticks:
                price = tick.get('p', 0)
                size = tick.get('s', 0)
                
                if price > 0:
                    price = round(price, 2)
                    
                    # Ağırlık belirleme: 100/200/300 lot = 1.00, diğer = 0.25
                    if size in [100, 200, 300]:
                        weight = 1.00
                    else:
                        weight = 0.25
                    
                    weighted_prices.append((price, weight))
            
            if len(weighted_prices) < 3:
                return None
            
            # Ağırlıklı MOD hesapla
            price_weights = defaultdict(float)
            
            for price, weight in weighted_prices:
                price_weights[price] += weight
            
            # En yüksek ağırlıklı fiyatı bul (MOD)
            mode_price = max(price_weights.keys(), key=lambda p: price_weights[p])
            
            return mode_price
            
        except Exception as e:
            print(f"[BGGG] ❌ {symbol} BGRPAN hesaplama hatası: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_previous_close(self, symbol):
        """
        Hisse için Previous Close değerini al
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            float: Previous Close değeri veya None
        """
        try:
            # Önce main_window'dan al
            if self.main_window and hasattr(self.main_window, 'df'):
                df = self.main_window.df
                if df is not None and not df.empty:
                    # 'PREF IBKR' kolonunu kullan (mini450 için)
                    if 'PREF IBKR' in df.columns:
                        symbol_row = df[df['PREF IBKR'] == symbol]
                    elif 'Symbol' in df.columns:
                        symbol_row = df[df['Symbol'] == symbol]
                    else:
                        symbol_row = pd.DataFrame()
                    
                    if not symbol_row.empty:
                        prev_close = symbol_row.iloc[0].get('prev_close') or symbol_row.iloc[0].get('Previous Close') or symbol_row.iloc[0].get('Prev Close')
                        if pd.notna(prev_close) and prev_close > 0:
                            return float(prev_close)
            
            # Fallback: Market data'dan al
            if self.hammer and self.hammer.is_connected():
                market_data = self.hammer.get_market_data(symbol)
                if market_data:
                    prev_close = market_data.get('prevClose') or market_data.get('prev_close')
                    if prev_close and prev_close > 0:
                        return float(prev_close)
            
            return None
            
        except Exception as e:
            print(f"[BGGG] ⚠️ {symbol} Previous Close alma hatası: {e}")
            return None
    
    def get_last_print(self, symbol):
        """
        Hisse için son print fiyatını al
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            float: Son print fiyatı veya None
        """
        try:
            if not self.hammer or not self.hammer.is_connected():
                return None
            
            # Sembol formatını düzelt
            formatted_symbol = symbol
            if " PR" in symbol:
                parts = symbol.split(" PR")
                if len(parts) == 2:
                    base_symbol = parts[0]
                    suffix = parts[1]
                    formatted_symbol = f"{base_symbol}-{suffix}"
            
            # Son tick'i al
            result = self.hammer.get_ticks(formatted_symbol, lastFew=1, tradesOnly=True, regHoursOnly=True)
            
            if result and isinstance(result, dict):
                ticks = result.get('data', [])
                if ticks and len(ticks) > 0:
                    last_tick = ticks[-1]
                    price = last_tick.get('p', 0)
                    if price > 0:
                        return float(price)
            
            # Fallback: Market data'dan last price
            market_data = self.hammer.get_market_data(symbol)
            if market_data:
                last = market_data.get('last') or market_data.get('price')
                if last and last > 0:
                    return float(last)
            
            return None
            
        except Exception as e:
            print(f"[BGGG] ⚠️ {symbol} Last Print alma hatası: {e}")
            return None
    
    def get_cgrup(self, symbol):
        """
        Hisse için CGRUP değerini al
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            str: CGRUP değeri (örn: "c400", "c425", "c450") veya None
        """
        try:
            if self.main_window and hasattr(self.main_window, 'df'):
                df = self.main_window.df
                if df is not None and not df.empty:
                    # 'PREF IBKR' kolonunu kullan
                    if 'PREF IBKR' in df.columns:
                        symbol_row = df[df['PREF IBKR'] == symbol]
                    elif 'Symbol' in df.columns:
                        symbol_row = df[df['Symbol'] == symbol]
                    else:
                        return None
                    
                    if not symbol_row.empty:
                        cgrup = symbol_row.iloc[0].get('CGRUP')
                        if pd.notna(cgrup) and cgrup != '':
                            return str(cgrup).upper()
            
            return None
            
        except Exception as e:
            print(f"[BGGG] ⚠️ {symbol} CGRUP alma hatası: {e}")
            return None
    
    def get_symbol_group(self, symbol):
        """
        Hisse için dosya grubunu bul
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            str: Grup adı (örn: "heldff", "heldkuponlu") veya None
        """
        try:
            # Grup dosya eşleşmesi
            group_file_map = {
                'heldff': 'ssfinekheldff.csv',
                'helddeznff': 'ssfinekhelddeznff.csv', 
                'heldkuponlu': 'ssfinekheldkuponlu.csv',
                'heldnff': 'ssfinekheldnff.csv',
                'heldflr': 'ssfinekheldflr.csv',
                'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
                'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
                'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
                'heldotelremorta': 'ssfinekheldotelremorta.csv',
                'heldsolidbig': 'ssfinekheldsolidbig.csv',
                'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
                'highmatur': 'ssfinekhighmatur.csv',
                'notcefilliquid': 'ssfineknotcefilliquid.csv',
                'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
                'nottitrekhc': 'ssfineknottitrekhc.csv',
                'salakilliquid': 'ssfineksalakilliquid.csv',
                'shitremhc': 'ssfinekshitremhc.csv'
            }
            
            # Her grup dosyasını kontrol et
            for group, file_name in group_file_map.items():
                if os.path.exists(file_name):
                    try:
                        df = pd.read_csv(file_name, encoding='utf-8-sig')
                        if 'PREF IBKR' in df.columns:
                            group_symbols = df['PREF IBKR'].tolist()
                            
                            # Tam eşleşme kontrol et
                            if symbol in group_symbols:
                                return group
                            
                            # Esnek eşleşme kontrol et
                            symbol_upper = symbol.upper().strip()
                            for group_symbol in group_symbols:
                                if group_symbol and isinstance(group_symbol, str):
                                    group_symbol_upper = group_symbol.upper().strip()
                                    if symbol_upper == group_symbol_upper:
                                        return group
                    except Exception as e:
                        continue
            
            return None
            
        except Exception as e:
            print(f"[BGGG] ⚠️ {symbol} grup bulma hatası: {e}")
            return None
    
    def get_group_symbols(self, group_name):
        """
        Belirli bir grubun tüm hisselerini al
        
        Args:
            group_name: Grup adı
            
        Returns:
            list: Grup içindeki hisse listesi
        """
        try:
            group_file_map = {
                'heldff': 'ssfinekheldff.csv',
                'helddeznff': 'ssfinekhelddeznff.csv', 
                'heldkuponlu': 'ssfinekheldkuponlu.csv',
                'heldnff': 'ssfinekheldnff.csv',
                'heldflr': 'ssfinekheldflr.csv',
                'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
                'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
                'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
                'heldotelremorta': 'ssfinekheldotelremorta.csv',
                'heldsolidbig': 'ssfinekheldsolidbig.csv',
                'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
                'highmatur': 'ssfinekhighmatur.csv',
                'notcefilliquid': 'ssfineknotcefilliquid.csv',
                'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
                'nottitrekhc': 'ssfineknottitrekhc.csv',
                'salakilliquid': 'ssfineksalakilliquid.csv',
                'shitremhc': 'ssfinekshitremhc.csv'
            }
            
            file_name = group_file_map.get(group_name.lower())
            if not file_name or not os.path.exists(file_name):
                return []
            
            df = pd.read_csv(file_name, encoding='utf-8-sig')
            if 'PREF IBKR' in df.columns:
                return df['PREF IBKR'].dropna().tolist()
            
            return []
            
        except Exception as e:
            print(f"[BGGG] ⚠️ {group_name} grup hisseleri alma hatası: {e}")
            return []
    
    def analyze_bggg(self, symbols, group_name, is_mini450=False):
        """
        BGGG analizi yap
        
        Args:
            symbols: Analiz edilecek hisse listesi
            group_name: Dosya grubu adı (örn: "heldkuponlu", "heldff", "mini450")
            is_mini450: Mini450 modunda mı? (Her hisse kendi grubunda analiz edilir)
            
        Returns:
            list: BGGG analiz sonuçları
        """
        try:
            print(f"[BGGG] 🔄 BGGG analizi başlatılıyor: {len(symbols)} hisse, grup: {group_name}, mini450: {is_mini450}")
            
            results = []
            
            # Mini450 modunda: Her hisse için kendi grubunu bul ve o grubun tüm hisselerini al
            if is_mini450:
                print(f"[BGGG] 📊 Mini450 modu: Her hisse kendi grubunda analiz edilecek")
                
                # ÖNCE: Tüm gruplar için grup ortalamalarını hesapla (cache için)
                # Bu sayede her hisse için tekrar tekrar aynı grubu hesaplamayız
                group_avg_cache = {}  # (group_name, cgrup) -> grup_ort_sapma
                
                # Tüm sembolleri gruplara ayır
                symbols_by_group = defaultdict(list)  # (group_name, cgrup) -> [symbols]
                for symbol in symbols:
                    symbol_group = self.get_symbol_group(symbol)
                    if symbol_group:
                        cgrup = self.get_cgrup(symbol) if symbol_group.lower() == 'heldkuponlu' else None
                        group_key = (symbol_group, cgrup)
                        symbols_by_group[group_key].append(symbol)
                
                # Her grup için bir kez grup ortalamasını hesapla
                print(f"[BGGG] 📊 {len(symbols_by_group)} farklı grup bulundu, grup ortalamaları hesaplanıyor...")
                for (group_name, cgrup), group_symbols in symbols_by_group.items():
                    # Grup içindeki tüm hisseler için BGRPAN sapmalarını hesapla
                    group_sapmalar = []
                    for group_symbol in group_symbols:
                        group_bgrpan = self.get_bgrpan_price(group_symbol)
                        group_prev_close = self.get_previous_close(group_symbol)
                        if group_bgrpan is not None and group_prev_close is not None:
                            group_sapma = group_bgrpan - group_prev_close
                            group_sapmalar.append(group_sapma)
                    
                    # GRUP ORT BGRPAN Sapması
                    grup_ort_sapma = sum(group_sapmalar) / len(group_sapmalar) if len(group_sapmalar) > 0 else None
                    group_avg_cache[(group_name, cgrup)] = grup_ort_sapma
                    print(f"[BGGG] 📊 Grup {group_name}" + (f" ({cgrup})" if cgrup else "") + f": {len(group_sapmalar)} hisse, ort sapma: {grup_ort_sapma:.4f}" if grup_ort_sapma else f": {len(group_sapmalar)} hisse, ort sapma: N/A")
                
                # Şimdi her hisse için analiz yap (grup ortalaması cache'den alınacak)
                for symbol in symbols:
                    print(f"[BGGG] 📊 {symbol} analiz ediliyor...")
                    
                    # Hisse için kendi grubunu bul
                    symbol_group = self.get_symbol_group(symbol)
                    
                    if not symbol_group:
                        print(f"[BGGG] ⚠️ {symbol} için grup bulunamadı, atlanıyor")
                        continue
                    
                    # CGRUP al
                    cgrup = self.get_cgrup(symbol) if symbol_group.lower() == 'heldkuponlu' else None
                    
                    # Bu hisse için BGRPAN ve sapmaları hesapla
                    bgrpan = self.get_bgrpan_price(symbol)
                    prev_close = self.get_previous_close(symbol)
                    last_print = self.get_last_print(symbol)
                    market_data = self.hammer.get_market_data(symbol) if self.hammer and self.hammer.is_connected() else {}
                    bid = market_data.get('bid') if market_data else None
                    ask = market_data.get('ask') if market_data else None
                    
                    # BGRPAN Sapması
                    bgrpan_sapma = None
                    if bgrpan is not None and prev_close is not None:
                        bgrpan_sapma = bgrpan - prev_close
                    
                    # BGRPAN - Bid/Ask
                    bgrpan_bid_diff = None
                    if bgrpan is not None and bid is not None and bid > 0:
                        bgrpan_bid_diff = bgrpan - bid
                    
                    bgrpan_ask_diff = None
                    if bgrpan is not None and ask is not None and ask > 0:
                        bgrpan_ask_diff = bgrpan - ask
                    
                    # GRUP ORT BGRPAN Sapması (cache'den al)
                    grup_ort_sapma = group_avg_cache.get((symbol_group, cgrup))
                    
                    # BGGG AYRISMA
                    bggg_ayrisma = None
                    if bgrpan_sapma is not None and grup_ort_sapma is not None:
                        bggg_ayrisma = bgrpan_sapma - grup_ort_sapma
                    
                    # Dos Grup string'i oluştur
                    dos_grup = symbol_group
                    if symbol_group.lower() == 'heldkuponlu' and cgrup:
                        dos_grup = f"{symbol_group} ({cgrup})"
                    
                    results.append({
                        'symbol': symbol,
                        'dos_grup': dos_grup,
                        'last_print': last_print,
                        'bgrpan': bgrpan,
                        'bgrpan_sapma': bgrpan_sapma,
                        'bgrpan_bid_diff': bgrpan_bid_diff,
                        'bgrpan_ask_diff': bgrpan_ask_diff,
                        'prev_close': prev_close,
                        'bid': bid,
                        'ask': ask,
                        'cgrup': cgrup,
                        'grup_ort_bgrpan_sapma': grup_ort_sapma,
                        'bggg_ayrisma': bggg_ayrisma
                    })
            else:
                # Normal mod: Tüm hisseler aynı grupta
                # Her hisse için BGRPAN ve sapmaları hesapla
                for symbol in symbols:
                    print(f"[BGGG] 📊 {symbol} analiz ediliyor...")
                    
                    # BGRPAN hesapla
                    bgrpan = self.get_bgrpan_price(symbol)
                    
                    # Previous Close al
                    prev_close = self.get_previous_close(symbol)
                    
                    # Last Print al
                    last_print = self.get_last_print(symbol)
                    
                    # Bid/Ask al
                    market_data = self.hammer.get_market_data(symbol) if self.hammer and self.hammer.is_connected() else {}
                    bid = market_data.get('bid') if market_data else None
                    ask = market_data.get('ask') if market_data else None
                    
                    # CGRUP al (heldkuponlu için)
                    cgrup = self.get_cgrup(symbol)
                    
                    # BGRPAN Sapması = BGRPAN - Previous Close
                    bgrpan_sapma = None
                    if bgrpan is not None and prev_close is not None:
                        bgrpan_sapma = bgrpan - prev_close
                    
                    # BGRPAN - Bid
                    bgrpan_bid_diff = None
                    if bgrpan is not None and bid is not None and bid > 0:
                        bgrpan_bid_diff = bgrpan - bid
                    
                    # BGRPAN - Ask
                    bgrpan_ask_diff = None
                    if bgrpan is not None and ask is not None and ask > 0:
                        bgrpan_ask_diff = bgrpan - ask
                    
                    # Dos Grup string'i oluştur
                    dos_grup = group_name
                    if group_name.lower() == 'heldkuponlu' and cgrup:
                        dos_grup = f"{group_name} ({cgrup})"
                    
                    results.append({
                        'symbol': symbol,
                        'dos_grup': dos_grup,
                        'last_print': last_print,
                        'bgrpan': bgrpan,
                        'bgrpan_sapma': bgrpan_sapma,
                        'bgrpan_bid_diff': bgrpan_bid_diff,
                        'bgrpan_ask_diff': bgrpan_ask_diff,
                        'prev_close': prev_close,
                        'bid': bid,
                        'ask': ask,
                        'cgrup': cgrup
                    })
                
                # Grup mantığı: heldkuponlu ise CGRUP'a göre, değilse tüm grup
                if group_name.lower() == 'heldkuponlu':
                    # CGRUP'a göre gruplar oluştur
                    cgrup_groups = defaultdict(list)
                    for result in results:
                        cgrup = result.get('cgrup')
                        if cgrup:
                            cgrup_groups[cgrup].append(result)
                        else:
                            # CGRUP yoksa ayrı bir grup
                            cgrup_groups['NO_CGRUP'].append(result)
                    
                    # Her CGRUP grubu için grup ortalaması hesapla
                    for cgrup, group_results in cgrup_groups.items():
                        # GRUP ORT BGRPAN Sapması = Gruptaki tüm hisselerin (BGRPAN - Previous Close) ortalaması
                        sapmalar = []
                        for result in group_results:
                            if result.get('bgrpan_sapma') is not None:
                                sapmalar.append(result['bgrpan_sapma'])
                        
                        grup_ort_sapma = sum(sapmalar) / len(sapmalar) if len(sapmalar) > 0 else None
                        
                        # Her hisse için BGGG AYRISMA hesapla
                        for result in group_results:
                            result['grup_ort_bgrpan_sapma'] = grup_ort_sapma
                            if result.get('bgrpan_sapma') is not None and grup_ort_sapma is not None:
                                result['bggg_ayrisma'] = result['bgrpan_sapma'] - grup_ort_sapma
                            else:
                                result['bggg_ayrisma'] = None
                else:
                    # Normal dosya grupları: Tüm grup bir arada
                    # GRUP ORT BGRPAN Sapması = Tüm gruptaki hisselerin (BGRPAN - Previous Close) ortalaması
                    sapmalar = []
                    for result in results:
                        if result.get('bgrpan_sapma') is not None:
                            sapmalar.append(result['bgrpan_sapma'])
                    
                    grup_ort_sapma = sum(sapmalar) / len(sapmalar) if len(sapmalar) > 0 else None
                    
                    # Her hisse için BGGG AYRISMA hesapla
                    for result in results:
                        result['grup_ort_bgrpan_sapma'] = grup_ort_sapma
                        if result.get('bgrpan_sapma') is not None and grup_ort_sapma is not None:
                            result['bggg_ayrisma'] = result['bgrpan_sapma'] - grup_ort_sapma
                        else:
                            result['bggg_ayrisma'] = None
            
            print(f"[BGGG] ✅ BGGG analizi tamamlandı: {len(results)} hisse")
            return results
            
        except Exception as e:
            print(f"[BGGG] ❌ BGGG analiz hatası: {e}")
            import traceback
            traceback.print_exc()
            return []

