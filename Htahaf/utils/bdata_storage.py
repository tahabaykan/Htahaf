import json
import os
import pandas as pd
from datetime import datetime, date, timedelta

BDATA_FILE = 'bdata_fills.json'
SNAPSHOT_FILE = 'bdata_snapshot.json'

class BDataStorage:
    def __init__(self, filename=BDATA_FILE):
        self.filename = filename
        self.snapshot_file = SNAPSHOT_FILE
        self.data = self._load()
        self.snapshots = self._load_snapshots()

    def _load(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def _load_snapshots(self):
        if os.path.exists(self.snapshot_file):
            with open(self.snapshot_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)

    def _save_snapshots(self):
        with open(self.snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(self.snapshots, f, ensure_ascii=False, indent=2, default=str)

    def _polygonize_ticker(self, symbol):
        """Ticker'ı Polygon formatına çevir"""
        if symbol.endswith('-P'):
            return symbol.replace('-P', '.PR')
        return symbol

    def load_ibkr_positions(self, market_data_manager, benchmark_calculator=None):
        """IBKR'den mevcut pozisyonları yükle ve BDATA'ya milat olarak kaydet"""
        print("[IBKR LOAD] IBKR pozisyonları BDATA'ya yükleniyor...")
        
        # IBKR bağlantısını kontrol et
        if not hasattr(market_data_manager, 'ib') or not market_data_manager.ib:
            print("[IBKR LOAD] ❌ IBKR objesi yok")
            return False
            
        if not market_data_manager.ib.isConnected():
            print("[IBKR LOAD] ❌ IBKR bağlantısı kapalı")
            return False
        
        # IBKR'den pozisyonları al
        positions = market_data_manager.get_positions()
        
        if not positions:
            print("[IBKR LOAD] ❌ IBKR'de pozisyon bulunamadı")
            return False
            
        print(f"[IBKR LOAD] {len(positions)} pozisyon bulundu")
        
        # Mevcut BDATA'yı temizle (yeni milat başlangıcı)
        self.data = []
        self.snapshots = {}
        
        today_str = date.today().strftime('%Y-%m-%d')
        today_datetime = datetime.now()
        
        loaded_count = 0
        
        for pos in positions:
            ticker = pos['symbol']
            quantity = pos['quantity']
            avg_cost = pos['avgCost']
            
            # Sıfır pozisyonları atla
            if abs(quantity) < 1:
                continue
                
            # Pozisyon yönünü belirle
            direction = 'long' if quantity > 0 else 'short'
            abs_quantity = abs(quantity)
            
            # Gerçek market verilerini al (Polygon'dan)
            poly_ticker = self._polygonize_ticker(ticker)
            if hasattr(market_data_manager, 'get_market_data'):
                try:
                    market_data = market_data_manager.get_market_data([poly_ticker])
                    md = market_data.get(poly_ticker, {})
                    current_price = float(md.get('last', 0))
                    
                    # Last price = 0 veya N/A ise fallback kullan
                    if current_price <= 0:
                        prev_close = md.get('prev_close', 0)
                        if prev_close and prev_close > 0:
                            current_price = float(prev_close)
                        else:
                            current_price = float(avg_cost)  # Son çare olarak avg_cost
                            print(f"[IBKR LOAD] {ticker}: Market data bulunamadı, avg_cost kullanılıyor")
                except Exception as e:
                    current_price = float(avg_cost)
                    print(f"[IBKR LOAD] {ticker}: Market data alma hatası: {e}")
            else:
                current_price = float(avg_cost)
                print(f"[IBKR LOAD] {ticker}: Market data manager yok, avg_cost kullanılıyor")
            
            # Benchmark hesapla
            current_benchmark = self._calculate_current_benchmark(ticker, benchmark_calculator)
            
            # Milat için avg_benchmark hesapla (avg_outperformance = 0 olacak şekilde)
            # avg_outperformance = (current_price - avg_cost) - (current_benchmark - avg_benchmark) = 0
            # avg_benchmark = current_benchmark - (current_price - avg_cost)
            if current_benchmark is not None:
                avg_benchmark = current_benchmark - (current_price - avg_cost)
            else:
                avg_benchmark = 0.0  # Fallback
                print(f"[IBKR LOAD] {ticker}: Current benchmark hesaplanamadı, avg_benchmark=0 yapıldı")
            
            # BDATA'ya milat fill'i olarak ekle
            self.add_fill(
                ticker=ticker,
                direction=direction,
                fill_price=avg_cost,  # Milat için avg_cost'u fill_price olarak kullan
                fill_size=abs_quantity,
                fill_time=datetime.now(),
                benchmark_at_fill=avg_benchmark,  # Hesaplanan avg_benchmark
                is_position_increase=True
            )
            
            print(f"[IBKR LOAD] {ticker} milat fill'i eklendi: {direction} {abs_quantity}@{avg_cost:.4f}, "
                  f"current_price={current_price:.4f}, current_benchmark={current_benchmark:.4f}, "
                  f"avg_benchmark={avg_benchmark:.4f}")
            
            # Snapshot oluştur
            if today_str not in self.snapshots:
                self.snapshots[today_str] = {}
                
            self.snapshots[today_str][ticker] = {
                'snapshot_date': today_str,
                'snapshot_price': current_price,
                'snapshot_benchmark': current_benchmark,
                'total_size': abs_quantity,
                'avg_cost': avg_cost,
                'avg_benchmark': avg_benchmark,
                'created_at': today_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'ibkr_import': True
            }
            
            loaded_count += 1
            
            print(f"[IBKR LOAD] {ticker}: {direction} {abs_quantity}@{avg_cost:.4f}, "
                  f"current={current_price:.4f}, avg_benchmark={avg_benchmark:.4f}")
        
        # Kaydet
        self._save()
        self._save_snapshots()
        
        print(f"[IBKR LOAD] ✅ {loaded_count} pozisyon BDATA'ya milat olarak eklendi")
        
        # CSV'yi güncelle
        self.update_csv()
        
        return True

    def _calculate_current_benchmark(self, ticker, benchmark_calculator=None):
        """Ticker için mevcut benchmark değerini hesapla"""
        if benchmark_calculator and hasattr(benchmark_calculator, 'get_benchmark_for_ticker'):
            try:
                benchmark_value = benchmark_calculator.get_benchmark_for_ticker(ticker)
                if benchmark_value is not None:
                    return benchmark_value
            except Exception as e:
                print(f"[BDATA BENCHMARK] {ticker} benchmark hesaplama hatası: {e}")
        
        # Fallback: mock benchmark (sadece test için)
        return self.get_mock_benchmark(ticker)

    def update_with_ibkr_fills(self, market_data_manager, benchmark_calculator=None, hours_back=24):
        """IBKR'den son fill'leri al ve BDATA'yı güncelle"""
        print(f"[IBKR FILLS] Son {hours_back} saatteki fill'ler kontrol ediliyor...")
        
        try:
            # IBKR bağlantısını kontrol et
            if not hasattr(market_data_manager, 'ib') or not market_data_manager.ib:
                print("[IBKR FILLS] ❌ IBKR objesi yok")
                return False
                
            if not market_data_manager.ib.isConnected():
                print("[IBKR FILLS] ❌ IBKR bağlantısı kapalı")
                return False
            
            # Önce offline fill'leri tespit et ve işle
            offline_success = self.detect_and_process_offline_fills(market_data_manager, benchmark_calculator)
            
            # IBKR'den recent fill'leri al
            if hasattr(market_data_manager, 'ib') and market_data_manager.ib:
                if market_data_manager.ib.isConnected():
                    # IBKR'den tüm fill'leri al
                    all_ibkr_fills = market_data_manager.ib.fills()
                    
                    # Son X saatteki fill'leri filtrele
                    cutoff_time = datetime.now() - timedelta(hours=hours_back)
                    recent_fills = []
                    
                    for fill in all_ibkr_fills:
                        fill_time = fill.time
                        if isinstance(fill_time, str):
                            try:
                                fill_time = datetime.fromisoformat(fill_time.replace('Z', '+00:00'))
                            except:
                                continue
                        
                        if fill_time >= cutoff_time:
                            recent_fills.append({
                                'symbol': fill.contract.symbol,
                                'side': fill.execution.side,
                                'price': fill.execution.price,
                                'quantity': fill.execution.shares,
                                'time': fill_time,
                                'execId': fill.execution.execId
                            })
                else:
                    print("[IBKR FILLS] IBKR bağlantısı kapalı")
                    recent_fills = []
            else:
                print("[IBKR FILLS] ⚠️ IBKR objesi bulunamadı")
                return offline_success
            
            if not recent_fills:
                print("[IBKR FILLS] ✅ Yeni recent fill bulunamadı")
                return offline_success
            
            print(f"[IBKR FILLS] {len(recent_fills)} recent fill bulundu")
            
            new_fills_count = 0
            
            for fill in recent_fills:
                # Bu fill daha önce işlendi mi kontrol et
                if self._is_fill_already_processed(fill):
                    continue
                
                ticker = fill['symbol']
                side = fill['side']  # 'BOT' or 'SLD'
                price = float(fill['price'])
                quantity = float(fill['quantity'])
                fill_time = fill['time']
                
                # Side'ı normalize et
                direction = 'long' if side.upper() in ['BOT', 'BUY'] else 'short'
                
                # Fill zamanındaki benchmark'ı hesapla
                fill_benchmark = self._calculate_fill_time_benchmark(ticker, fill_time, benchmark_calculator)
                
                # Mevcut pozisyon durumunu kontrol et
                current_total_size = self.get_current_position_size(ticker)
                is_increase = self._is_position_increase(ticker, direction, quantity, current_total_size)
                
                # BDATA'ya ekle
                self.add_fill(ticker, direction, price, quantity, fill_time, fill_benchmark, is_increase)
                
                new_fills_count += 1
                
                print(f"[IBKR FILLS] {ticker}: {direction} {quantity}@{price:.4f}, "
                      f"benchmark={fill_benchmark:.4f}, increase={is_increase}")
            
            print(f"[IBKR FILLS] ✅ {new_fills_count} yeni fill BDATA'ya eklendi")
            return True
            
        except Exception as e:
            print(f"[IBKR FILLS] ❌ Fill güncelleme hatası: {e}")
            return False

    def _calculate_fill_time_benchmark(self, ticker, fill_time, benchmark_calculator=None):
        """Fill zamanındaki benchmark değerini hesapla"""
        # TODO: Fill zamanındaki PFF/TLT değerlerini kullanarak benchmark hesapla
        # Şimdilik mevcut benchmark'ı kullan
        return self._calculate_current_benchmark(ticker, benchmark_calculator)

    def get_mock_price(self, ticker):
        """Test amaçlı mock fiyatlar - gerçek sistem için external API bağlanabilir"""
        mock_prices = {
            'SREA': 20.7567,
            'JAGX': 2.7976,
            'TSLA': 327.9000,
            'AAPL': 150.00,
            'GOOGL': 2500.00,
            'MSFT': 300.00
        }
        return mock_prices.get(ticker, 100.0)

    def get_mock_benchmark(self, ticker):
        """Test amaçlı mock benchmark'lar"""
        mock_benchmarks = {
            'SREA': 29.4059,
            'JAGX': 3.4500,
            'TSLA': 327.9000,
            'AAPL': 155.00,
            'GOOGL': 2520.00,
            'MSFT': 305.00
        }
        return mock_benchmarks.get(ticker, 100.0)

    def create_snapshot_for_current_positions(self):
        """Mevcut pozisyonlar için snapshot oluştur - milat başlangıcı"""
        today_str = date.today().strftime('%Y-%m-%d')
        
        if today_str not in self.snapshots:
            self.snapshots[today_str] = {}
        
        # Mevcut pozisyonları al
        summary = self.get_position_summary_with_snapshot()
        snapshot_count = 0
        
        for (ticker, direction), data in summary.items():
            current_price = self.get_mock_price(ticker)
            current_benchmark = self.get_mock_benchmark(ticker)
            
            self.snapshots[today_str][ticker] = {
                'snapshot_date': today_str,
                'snapshot_price': current_price,
                'snapshot_benchmark': current_benchmark,
                'total_size': data['total_size'],
                'avg_cost': data['avg_cost'],
                'avg_benchmark': data['avg_benchmark'],
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            snapshot_count += 1
            
            print(f"[BDATA SNAPSHOT] {ticker} milat oluşturuldu: price={current_price:.4f}, "
                  f"benchmark={current_benchmark:.4f}, avg_cost={data['avg_cost']:.4f}")
        
        if snapshot_count > 0:
            self._save_snapshots()
            print(f"[BDATA SNAPSHOT] ✅ {snapshot_count} pozisyon için milat (snapshot) oluşturuldu")
            
            # Snapshot sonrası CSV'yi güncelle
            self.update_csv()
        else:
            print("[BDATA SNAPSHOT] ⚠️ Snapshot oluşturulacak pozisyon bulunamadı")

    def reset_all_snapshots_to_today(self):
        """Tüm snapshot'ları bugüne sıfırla - yeni milat başlangıcı"""
        today_str = date.today().strftime('%Y-%m-%d')
        
        # Eski snapshot'ları temizle
        self.snapshots = {today_str: {}}
        
        # Mevcut pozisyonlar için yeni snapshot'lar oluştur
        summary = self.get_position_summary_with_snapshot()
        reset_count = 0
        
        for (ticker, direction), data in summary.items():
            current_price = self.get_mock_price(ticker)
            current_benchmark = self.get_mock_benchmark(ticker)
            
            self.snapshots[today_str][ticker] = {
                'snapshot_date': today_str,
                'snapshot_price': current_price,
                'snapshot_benchmark': current_benchmark,
                'total_size': data['total_size'],
                'avg_cost': data['avg_cost'],
                'avg_benchmark': data['avg_benchmark'],
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            reset_count += 1
            
            print(f"[BDATA RESET] {ticker} yeni milat: price={current_price:.4f}, "
                  f"benchmark={current_benchmark:.4f}")
        
        if reset_count > 0:
            self._save_snapshots()
            print(f"[BDATA RESET] ✅ {reset_count} pozisyon için snapshot sıfırlandı")
            
            # Reset sonrası CSV'yi güncelle
            self.update_csv()
        else:
            print("[BDATA RESET] ⚠️ Sıfırlanacak pozisyon bulunamadı")

    def create_snapshot(self, ticker, current_price, current_benchmark, total_size, avg_cost, avg_benchmark):
        """Bugünkü değerleri snapshot olarak kaydet"""
        today_str = date.today().strftime('%Y-%m-%d')
        
        if today_str not in self.snapshots:
            self.snapshots[today_str] = {}
            
        self.snapshots[today_str][ticker] = {
            'snapshot_date': today_str,
            'snapshot_price': current_price,
            'snapshot_benchmark': current_benchmark,
            'total_size': total_size,
            'avg_cost': avg_cost,
            'avg_benchmark': avg_benchmark,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        self._save_snapshots()
        print(f"[BDATA SNAPSHOT] {ticker} snapshot oluşturuldu: price={current_price:.4f}, benchmark={current_benchmark:.4f}")

    def get_latest_snapshot(self, ticker):
        """En son snapshot'ı al"""
        if not self.snapshots:
            return None
            
        # En son tarihi bul
        latest_date = max(self.snapshots.keys())
        
        if ticker in self.snapshots[latest_date]:
            return self.snapshots[latest_date][ticker]
        
        return None

    def add_fill(self, ticker, direction, fill_price, fill_size, fill_time, benchmark_at_fill, is_position_increase=True):
        """Fill ekle - pozisyon arttırma/azaltma kontrolü ile"""
        fill_data = {
            'ticker': ticker,
            'direction': direction,
            'fill_price': fill_price,
            'fill_size': fill_size,
            'fill_time': fill_time.strftime('%Y-%m-%d %H:%M:%S') if isinstance(fill_time, datetime) else str(fill_time),
            'benchmark_at_fill': benchmark_at_fill,
            'is_position_increase': is_position_increase
        }
        
        self.data.append(fill_data)
        self._save()
        
        print(f"[BDATA FILL] {ticker} fill eklendi: {direction} {fill_size}@{fill_price:.4f}, "
              f"benchmark={benchmark_at_fill:.4f}, increase={is_position_increase}")
        
        # Fill sonrası CSV'yi otomatik güncelle
        self.update_csv()

    def add_manual_fill(self, ticker, direction, fill_price, fill_size, benchmark_at_fill=None):
        """Manuel fill ekleme - GUI'den kullanılacak"""
        if benchmark_at_fill is None:
            benchmark_at_fill = self.get_mock_benchmark(ticker)
        
        # Mevcut pozisyon durumunu kontrol et
        current_total_size = self.get_current_position_size(ticker)
        
        # Pozisyon artırma/azaltma kontrolü
        is_increase = self._is_position_increase(ticker, direction, fill_size, current_total_size)
        
        # Fill'i ekle
        self.add_fill(
            ticker=ticker,
            direction=direction,
            fill_price=float(fill_price),
            fill_size=int(fill_size),
            fill_time=datetime.now(),
            benchmark_at_fill=float(benchmark_at_fill),
            is_position_increase=is_increase
        )
        
        print(f"[BDATA MANUAL] {ticker} manuel fill eklendi: {direction} {fill_size}@{fill_price}")
        return True

    def get_current_position_size(self, ticker):
        """Ticker için mevcut pozisyon boyutunu hesapla"""
        total_long = 0
        total_short = 0
        
        for fill in self.data:
            if fill['ticker'] == ticker:
                if fill['direction'] == 'long':
                    total_long += fill['fill_size']
                elif fill['direction'] == 'short':
                    total_short += fill['fill_size']
        
        return total_long - total_short

    def reduce_position(self, ticker, direction, reduce_size):
        # Pozisyon azaltılırken, FIFO/LIFO yok, sadece toplam size azaltılır
        # Fill kayıtları silinmez, sadece toplam size hesaplamada dikkate alınır
        # (Kullanıcıya gösterimde total size azaltılır)
        # Bu fonksiyon ileride kullanılabilir, şimdilik pasif bırakıyoruz
        pass

    def get_all_fills(self):
        return self.data

    def get_fills_by_ticker(self, ticker, direction=None):
        return [f for f in self.data if f['ticker'] == ticker and (direction is None or f['direction'] == direction)]

    def get_position_summary_with_snapshot(self):
        """Snapshot tabanlı pozisyon özeti - sadece pozisyon arttıran fill'leri kullan"""
        summary = {}
        
        for f in self.data:
            # Sadece pozisyon arttıran fill'leri kullan
            if not f.get('is_position_increase', True):
                continue
                
            ticker = f['ticker']
            direction = f['direction']
            key = (ticker, direction)
            
            if key not in summary:
                summary[key] = {
                    'total_size': 0, 
                    'total_cost': 0, 
                    'total_bench': 0, 
                    'fills': []
                }
            
            size = f['fill_size']
            summary[key]['total_size'] += size
            summary[key]['total_cost'] += f['fill_price'] * size
            summary[key]['total_bench'] += f['benchmark_at_fill'] * size
            summary[key]['fills'].append(f)
        
        # Avg hesaplamalar
        for key, val in summary.items():
            if val['total_size'] > 0:
                val['avg_cost'] = val['total_cost'] / val['total_size']
                val['avg_benchmark'] = val['total_bench'] / val['total_size']
            else:
                val['avg_cost'] = 0
                val['avg_benchmark'] = 0
                
        return summary 

    def calculate_avg_outperformance(self, ticker, current_price, current_benchmark):
        """Snapshot'tan sonraki avg outperformance hesapla"""
        snapshot = self.get_latest_snapshot(ticker)
        
        if not snapshot:
            # Snapshot yoksa MİLAT durumu - avg_outperformance = 0 olmalı
            summary = self.get_position_summary_with_snapshot()
            
            # Ticker için pozisyon var mı?
            position_found = False
            for (pos_ticker, direction), data in summary.items():
                if pos_ticker == ticker:
                    position_found = True
                    avg_cost = data['avg_cost']
                    
                    # MİLAT için avg_benchmark'ı hesapla
                    # avg_outperformance = (current_price - avg_cost) - (current_benchmark - avg_benchmark) = 0
                    # avg_benchmark = current_benchmark - (current_price - avg_cost)
                    calculated_avg_benchmark = current_benchmark - (current_price - avg_cost)
                    
                    # Hesaplanan avg_benchmark'ı data'ya kaydet (milat için)
                    data['avg_benchmark'] = calculated_avg_benchmark
                    
                    # Avg outperformance = 0 (milat)
                    avg_outperformance = 0.0
                    
                    print(f"[BDATA MILAT] {ticker} milat hesaplaması: "
                          f"avg_cost={avg_cost:.4f}, current_price={current_price:.4f}, "
                          f"current_benchmark={current_benchmark:.4f}, "
                          f"calculated_avg_benchmark={calculated_avg_benchmark:.4f}, "
                          f"avg_outperformance={avg_outperformance:.4f}")
                    
                    return avg_outperformance
                    
            if not position_found:
                print(f"[BDATA OUTPERF] {ticker} için pozisyon bulunamadı, 0 döndürülüyor")
                return 0.0
            
        # Snapshot varsa normal hesaplama
        snapshot_price = snapshot['snapshot_price']
        snapshot_benchmark = snapshot['snapshot_benchmark']
        avg_cost = snapshot['avg_cost']
        avg_benchmark = snapshot['avg_benchmark']
        
        # Performans hesaplama
        # (current_price - avg_cost) - (current_benchmark - avg_benchmark)
        price_performance = current_price - avg_cost
        benchmark_performance = current_benchmark - avg_benchmark
        avg_outperformance = price_performance - benchmark_performance
        
        print(f"[BDATA OUTPERF] {ticker} snapshot tabanlı: "
              f"price_perf={price_performance:.4f}, bench_perf={benchmark_performance:.4f}, "
              f"outperf={avg_outperformance:.4f}")
        
        return avg_outperformance

    def get_open_position_summary(self):
        """Eski sistem ile uyumluluk için"""
        return self.get_position_summary_with_snapshot()

    def update_position_on_fill(self, ticker, direction, fill_price, fill_size, benchmark_at_fill, current_total_size):
        """Fill geldiğinde pozisyon güncelleme mantığı"""
        
        # Pozisyon arttırma mı azaltma mı?
        is_increase = self._is_position_increase(ticker, direction, fill_size, current_total_size)
        
        # Fill'i ekle
        self.add_fill(
            ticker=ticker,
            direction=direction, 
            fill_price=fill_price,
            fill_size=fill_size,
            fill_time=datetime.now(),
            benchmark_at_fill=benchmark_at_fill,
            is_position_increase=is_increase
        )
        
        return is_increase

    def _is_position_increase(self, ticker, direction, fill_size, current_total_size):
        """Pozisyon artırma mı azaltma mı kontrol et"""
        
        # Mevcut pozisyon yönü
        if current_total_size > 0:
            current_direction = 'long'
        elif current_total_size < 0:
            current_direction = 'short'
        else:
            current_direction = None
            
        # Pozisyon yoksa her zaman artırma
        if current_direction is None:
            return True
            
        # Aynı yönde fill ise artırma
        if direction == current_direction:
            return True
            
        # Ters yönde fill ise azaltma
        if direction != current_direction:
            return False
            
        return True

    def update_csv(self):
        """CSV dosyasını güncelle - PSFAlgo'dan bağımsız"""
        try:
            # Pozisyon özetini al
            summary = self.get_position_summary_with_snapshot()
            
            # CSV için satırları hazırla
            rows = []
            total_positions = 0
            
            for (ticker, direction), data in summary.items():
                total_positions += 1
                
                # Mock fiyat ve benchmark al
                current_price = self.get_mock_price(ticker)
                current_benchmark = self.get_mock_benchmark(ticker)
                
                # Snapshot tabanlı avg outperformance hesapla
                avg_outperformance = self.calculate_avg_outperformance(
                    ticker, current_price, current_benchmark
                )
                
                # Diğer hesaplamalar
                total_size = data['total_size']
                avg_cost = data['avg_cost']
                avg_benchmark = data['avg_benchmark']
                
                # Market value ve PnL
                market_value = current_price * abs(total_size)
                cost_basis = avg_cost * abs(total_size)
                unrealized_pnl = (current_price - avg_cost) * total_size
                
                # Yüzde hesaplamaları
                pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost != 0 else 0
                
                row = {
                    'Ticker': ticker,
                    'Direction': direction,
                    'Size': total_size,
                    'Avg Cost': round(avg_cost, 4),
                    'Current Price': round(current_price, 4),
                    'Avg Benchmark': round(avg_benchmark, 4),
                    'Current Benchmark': round(current_benchmark, 4),
                    'Market Value': round(market_value, 2),
                    'Cost Basis': round(cost_basis, 2),
                    'Unrealized PnL': round(unrealized_pnl, 2),
                    'PnL %': round(pnl_pct, 2),
                    'Avg Outperformance': round(avg_outperformance, 4),
                    'Fills Count': len(data['fills']),
                    'Last Updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                rows.append(row)
                
                print(f"[BDATA CSV] {ticker}: size={total_size}, avg_cost={avg_cost:.4f}, "
                      f"current={current_price:.4f}, avg_outperf={avg_outperformance:.4f}")
            
            # DataFrame oluştur ve CSV'ye kaydet
            if rows:
                df = pd.DataFrame(rows)
                csv_path = 'bdata_positions.csv'
                df.to_csv(csv_path, index=False, encoding='utf-8')
                print(f"[BDATA CSV] ✅ {total_positions} pozisyon CSV'ye kaydedildi: {csv_path}")
                return True
            else:
                print("[BDATA CSV] ⚠️ Kaydedilecek pozisyon bulunamadı")
                return False
                
        except Exception as e:
            print(f"[BDATA CSV] ❌ CSV güncelleme hatası: {e}")
            import traceback
            traceback.print_exc()
            return False

    def detect_and_process_offline_fills(self, market_data_manager, benchmark_calculator=None):
        """Offline iken alınan fill'leri tespit et ve BDATA'yı güncelle"""
        print("[OFFLINE FILLS] Offline fill detection başlıyor...")
        
        try:
            # IBKR bağlantısını kontrol et
            if not hasattr(market_data_manager, 'ib') or not market_data_manager.ib:
                print("[OFFLINE FILLS] ❌ IBKR objesi yok")
                return False
                
            if not market_data_manager.ib.isConnected():
                print("[OFFLINE FILLS] ❌ IBKR bağlantısı kapalı")
                return False
            
            # Mevcut BDATA pozisyonları
            bdata_summary = self.get_position_summary_with_snapshot()
            bdata_positions = {}
            
            for (ticker, direction), data in bdata_summary.items():
                net_size = data['total_size'] if direction == 'long' else -data['total_size']
                bdata_positions[ticker] = net_size
            
            print(f"[OFFLINE FILLS] BDATA'da {len(bdata_positions)} pozisyon var")
            
            # IBKR'deki mevcut pozisyonları al
            ibkr_positions = market_data_manager.get_positions()
            ibkr_position_dict = {}
            
            for pos in ibkr_positions:
                ticker = pos['symbol']
                quantity = pos['quantity']
                if abs(quantity) >= 1:  # Minimum 1 lot
                    ibkr_position_dict[ticker] = quantity
            
            print(f"[OFFLINE FILLS] IBKR'de {len(ibkr_position_dict)} pozisyon var")
            
            # Farkları tespit et
            all_tickers = set(bdata_positions.keys()) | set(ibkr_position_dict.keys())
            changed_positions = {}
            
            for ticker in all_tickers:
                bdata_size = bdata_positions.get(ticker, 0)
                ibkr_size = ibkr_position_dict.get(ticker, 0)
                
                if abs(bdata_size - ibkr_size) >= 1:  # 1 lot'tan fazla fark
                    changed_positions[ticker] = {
                        'bdata_size': bdata_size,
                        'ibkr_size': ibkr_size,
                        'difference': ibkr_size - bdata_size
                    }
                    print(f"[OFFLINE FILLS] {ticker}: BDATA={bdata_size}, IBKR={ibkr_size}, fark={ibkr_size - bdata_size}")
            
            if not changed_positions:
                print("[OFFLINE FILLS] ✅ Offline fill bulunamadı, pozisyonlar senkron")
                return True
            
            # Son BDATA update zamanını bul
            last_fill_time = self._get_last_fill_time()
            if not last_fill_time:
                # BDATA boşsa, en son 24 saat içinde bak
                from datetime import timedelta
                last_fill_time = datetime.now() - timedelta(days=1)
            
            print(f"[OFFLINE FILLS] Son fill zamanı: {last_fill_time}")
            
            # IBKR'den bu zamandan sonraki fill'leri al
            fills_to_process = self._get_ibkr_fills_since(
                market_data_manager, last_fill_time, changed_positions.keys()
            )
            
            if not fills_to_process:
                print("[OFFLINE FILLS] ⚠️ IBKR'de yeni fill bulunamadı ama pozisyon farkı var")
                return False
            
            print(f"[OFFLINE FILLS] {len(fills_to_process)} offline fill bulundu")
            
            # Fill'leri işle
            processed_count = 0
            for fill_data in fills_to_process:
                success = self._process_offline_fill(fill_data, benchmark_calculator)
                if success:
                    processed_count += 1
            
            print(f"[OFFLINE FILLS] ✅ {processed_count} offline fill işlendi")
            
            # CSV'yi güncelle
            self.update_csv()
            
            return True
            
        except Exception as e:
            print(f"[OFFLINE FILLS] ❌ Offline fill detection hatası: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _get_last_fill_time(self):
        """Son fill zamanını bul"""
        if not self.data:
            return None
        
        last_time = None
        for fill in self.data:
            fill_time_str = fill.get('fill_time', '')
            try:
                fill_time = datetime.strptime(fill_time_str, '%Y-%m-%d %H:%M:%S')
                if last_time is None or fill_time > last_time:
                    last_time = fill_time
            except:
                continue
        
        return last_time

    def _get_ibkr_fills_since(self, market_data_manager, since_time, target_tickers):
        """IBKR'den belirli zamandan sonraki fill'leri al"""
        try:
            # IBKR'den tüm fill'leri al
            if hasattr(market_data_manager, 'ib') and market_data_manager.ib:
                if not market_data_manager.ib.isConnected():
                    print("[OFFLINE FILLS] IBKR bağlantısı kapalı")
                    return []
                
                # IBKR'den fill'leri al
                all_ibkr_fills = market_data_manager.ib.fills()
                
                target_fills = []
                for fill in all_ibkr_fills:
                    # Ticker kontrolü
                    if fill.contract.symbol not in target_tickers:
                        continue
                    
                    # Zaman kontrolü
                    fill_time = fill.time
                    if isinstance(fill_time, str):
                        try:
                            fill_time = datetime.fromisoformat(fill_time.replace('Z', '+00:00'))
                        except:
                            continue
                    
                    if fill_time >= since_time:
                        target_fills.append({
                            'symbol': fill.contract.symbol,
                            'side': fill.execution.side,
                            'price': fill.execution.price,
                            'quantity': fill.execution.shares,
                            'time': fill_time,
                            'execId': fill.execution.execId
                        })
                
                return target_fills
            else:
                print("[OFFLINE FILLS] IBKR objesi bulunamadı")
                return []
            
        except Exception as e:
            print(f"[OFFLINE FILLS] IBKR fill history hatası: {e}")
            return []

    def _process_offline_fill(self, fill_data, benchmark_calculator):
        """Offline fill'i işle ve BDATA'ya ekle"""
        try:
            ticker = fill_data['symbol']
            side = fill_data['side']
            price = float(fill_data['price'])
            quantity = float(fill_data['quantity'])
            fill_time = fill_data['time']
            
            # Side'ı normalize et
            direction = 'long' if side.upper() in ['BOT', 'BUY'] else 'short'
            
            # Fill zamanındaki benchmark'ı hesapla
            fill_benchmark = self._calculate_historical_benchmark(
                ticker, fill_time, benchmark_calculator
            )
            
            # Mevcut pozisyon durumunu kontrol et (fill öncesi)
            current_total_size = self.get_current_position_size(ticker)
            is_increase = self._is_position_increase(ticker, direction, quantity, current_total_size)
            
            # Fill'i BDATA'ya ekle
            self.add_fill(ticker, direction, price, quantity, fill_time, fill_benchmark, is_increase)
            
            print(f"[OFFLINE FILLS] {ticker} offline fill işlendi: {direction} {quantity}@{price:.4f}, "
                  f"benchmark={fill_benchmark:.4f}, time={fill_time}")
            
            return True
            
        except Exception as e:
            print(f"[OFFLINE FILLS] Fill işleme hatası: {e}")
            return False

    def _calculate_historical_benchmark(self, ticker, fill_time, benchmark_calculator):
        """Fill zamanındaki benchmark değerini hesapla"""
        try:
            # TODO: Fill zamanındaki gerçek PFF/TLT değerlerini al
            # Şimdilik mevcut benchmark'ı kullan ama ileride historical API eklenebilir
            
            if benchmark_calculator:
                return benchmark_calculator.get_fill_time_benchmark(ticker, fill_time)
            else:
                return self.get_mock_benchmark(ticker)
                
        except Exception as e:
            print(f"[OFFLINE FILLS] Historical benchmark hesaplama hatası: {e}")
            return self.get_mock_benchmark(ticker)

    def enable_auto_fill_monitoring(self, market_data_manager, benchmark_calculator=None):
        """Otomatik fill monitoring'i etkinleştir"""
        print("[AUTO MONITOR] Otomatik fill monitoring etkinleştiriliyor...")
        
        # Market data manager'a callback ayarla
        if hasattr(market_data_manager, 'set_fill_callback'):
            def on_new_fill(fill_data):
                self._handle_realtime_fill(fill_data, benchmark_calculator)
            
            market_data_manager.set_fill_callback(on_new_fill)
            print("[AUTO MONITOR] ✅ Realtime fill callback ayarlandı")
        else:
            print("[AUTO MONITOR] ⚠️ Market data manager'da fill callback desteği yok")

    def _handle_realtime_fill(self, fill_data, benchmark_calculator):
        """Realtime fill geldiğinde işle"""
        try:
            ticker = fill_data['symbol']
            side = fill_data['side']
            price = float(fill_data['price'])
            quantity = float(fill_data['quantity'])
            fill_time = fill_data.get('time', datetime.now())
            
            # Side'ı normalize et
            direction = 'long' if side.upper() in ['BOT', 'BUY'] else 'short'
            
            # Mevcut benchmark'ı hesapla
            current_benchmark = self._calculate_current_benchmark(ticker, benchmark_calculator)
            
            # Pozisyon durumunu kontrol et
            current_total_size = self.get_current_position_size(ticker)
            is_increase = self._is_position_increase(ticker, direction, quantity, current_total_size)
            
            # Fill'i ekle
            self.add_fill(ticker, direction, price, quantity, fill_time, current_benchmark, is_increase)
            
            print(f"[REALTIME FILL] {ticker} canlı fill işlendi: {direction} {quantity}@{price:.4f}")
            
        except Exception as e:
            print(f"[REALTIME FILL] Canlı fill işleme hatası: {e}")

    def _is_fill_already_processed(self, fill_data):
        """Fill daha önce işlendi mi kontrol et"""
        try:
            fill_id = f"{fill_data['symbol']}_{fill_data.get('execId', '')}"
            fill_time = fill_data['time']
            
            # Zaman ve ticker bazında benzer fill var mı bak
            for existing_fill in self.data:
                if (existing_fill['ticker'] == fill_data['symbol'] and
                    abs(existing_fill['fill_price'] - float(fill_data['price'])) < 0.01 and
                    existing_fill['fill_size'] == float(fill_data['quantity'])):
                    
                    # Zaman yakınlığı kontrol et (5 dakika tolerans)
                    try:
                        existing_time = datetime.strptime(existing_fill['fill_time'], '%Y-%m-%d %H:%M:%S')
                        if isinstance(fill_time, str):
                            new_time = datetime.fromisoformat(fill_time.replace('Z', '+00:00'))
                        else:
                            new_time = fill_time
                        
                        time_diff = abs((existing_time - new_time).total_seconds())
                        if time_diff < 300:  # 5 dakika
                            return True
                    except:
                        pass
            
            return False
            
        except Exception as e:
            print(f"[FILL CHECK] Fill kontrol hatası: {e}")
            return False 