"""
BDATA Storage modülü - Hammer Pro için pozisyon takibi
"""

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

    def add_fill(self, ticker, direction, fill_price, fill_size, fill_time, benchmark_at_fill, is_position_increase=True):
        """Yeni fill ekle"""
        self.data.append({
            'ticker': ticker,
            'direction': direction,
            'fill_price': fill_price,
            'fill_size': fill_size,
            'fill_time': fill_time.strftime('%Y-%m-%d %H:%M:%S') if isinstance(fill_time, datetime) else str(fill_time),
            'benchmark_at_fill': benchmark_at_fill,
            'is_position_increase': is_position_increase
        })
        self._save()
        print(f"[BDATA FILL] {ticker} fill eklendi: {direction} {fill_size}@{fill_price:.4f}, "
              f"benchmark={benchmark_at_fill:.4f}")

    def add_manual_fill(self, ticker, direction, fill_price, fill_size, benchmark_at_fill=None):
        """Manuel fill ekle"""
        if benchmark_at_fill is None:
            # Benchmark hesaplama (basit)
            benchmark_at_fill = fill_price + 0.5  # Varsayılan benchmark
        
        self.add_fill(
            ticker=ticker,
            direction=direction,
            fill_price=fill_price,
            fill_size=fill_size,
            fill_time=datetime.now(),
            benchmark_at_fill=benchmark_at_fill,
            is_position_increase=True
        )
        print(f"[BDATA MANUAL] {ticker} manuel fill eklendi: {direction} {fill_size}@{fill_price}")

    def get_current_position_size(self, ticker):
        """Belirli ticker için mevcut pozisyon büyüklüğünü hesapla"""
        total_size = 0
        for fill in self.data:
            if fill['ticker'] == ticker:
                if fill['direction'] == 'long':
                    total_size += fill['fill_size']
                else:  # short
                    total_size -= fill['fill_size']
        return total_size

    def get_position_summary_with_snapshot(self):
        """Pozisyon özetini snapshot ile birlikte döndür"""
        summary = {}
        
        # Her ticker için pozisyon hesapla
        for fill in self.data:
            ticker = fill['ticker']
            if ticker not in summary:
                summary[ticker] = {
                    'total_size': 0,
                    'total_cost': 0,
                    'total_bench': 0,
                    'fills': [],
                    'avg_cost': 0,
                    'avg_benchmark': 0,
                    'current_price': 0,
                    'current_benchmark': 0,
                    'unrealized_pnl': 0,
                    'outperformance': 0
                }
            
            size = fill['fill_size']
            if fill['direction'] == 'long':
                summary[ticker]['total_size'] += size
                summary[ticker]['total_cost'] += fill['fill_price'] * size
                summary[ticker]['total_bench'] += fill['benchmark_at_fill'] * size
            else:  # short
                summary[ticker]['total_size'] -= size
                summary[ticker]['total_cost'] -= fill['fill_price'] * size
                summary[ticker]['total_bench'] -= fill['benchmark_at_fill'] * size
            
            summary[ticker]['fills'].append(fill)
        
        # Ortalama hesaplamaları
        for ticker, data in summary.items():
            if data['total_size'] != 0:
                data['avg_cost'] = data['total_cost'] / abs(data['total_size'])
                data['avg_benchmark'] = data['total_bench'] / abs(data['total_size'])
        
        return summary

    def create_snapshot(self, ticker, current_price, current_benchmark, total_size, avg_cost, avg_benchmark):
        """Snapshot oluştur"""
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
        for date_str in sorted(self.snapshots.keys(), reverse=True):
            if ticker in self.snapshots[date_str]:
                return self.snapshots[date_str][ticker]
        return None

    def update_csv(self):
        """BDATA verilerini CSV'ye kaydet"""
        try:
            summary = self.get_position_summary_with_snapshot()
            csv_data = []
            
            for ticker, data in summary.items():
                if data['total_size'] != 0:  # Sadece açık pozisyonlar
                    # Snapshot'tan benchmark bilgisini al
                    snapshot = self.get_latest_snapshot(ticker)
                    current_benchmark = snapshot['snapshot_benchmark'] if snapshot else data['avg_benchmark']
                    
                    csv_data.append({
                        'Ticker': ticker,
                        'Poly': ticker,  # Hammer Pro için aynı
                        'Total Size': abs(data['total_size']),
                        'Avg Cost': data['avg_cost'],
                        'Avg Benchmark': data['avg_benchmark'],
                        'Bench Type': 'T-c400',  # Varsayılan
                        'Current Price': 0,  # Hammer Pro'dan alınacak
                        'Current Benchmark': current_benchmark,
                        'Fills': f"{data['avg_cost']:.2f}/{abs(data['total_size']):.1f}/{data['avg_benchmark']:.2f}"
                    })
            
            if csv_data:
                df = pd.DataFrame(csv_data)
                csv_path = 'bdata.csv'
                df.to_csv(csv_path, index=False)
                print(f"[BDATA CSV] ✅ {len(csv_data)} pozisyon CSV'ye kaydedildi: {csv_path}")
                return True
            else:
                print("[BDATA CSV] ⚠️ Kaydedilecek pozisyon bulunamadı")
                return False
                
        except Exception as e:
            print(f"[BDATA CSV] ❌ CSV güncelleme hatası: {e}")
            return False

    def create_befday_csv(self, positions_data):
        """BEFDAY CSV dosyasını oluştur"""
        try:
            befday_data = []
            
            for ticker, data in positions_data.items():
                if data['total_size'] != 0:  # Sadece açık pozisyonlar
                    befday_data.append({
                        'Symbol': ticker,
                        'Quantity': data['total_size'],
                        'AvgCost': data['avg_cost'],
                        'Market Price': 0,  # Hammer Pro'dan alınacak
                        'Market Value': 0,  # Hesaplanacak
                        'Unrealized PnL': 0,  # Hesaplanacak
                        'Account': 'U11745411'  # Varsayılan hesap
                    })
            
            if befday_data:
                df = pd.DataFrame(befday_data)
                csv_path = 'befday.csv'
                df.to_csv(csv_path, index=False)
                print(f"[BEFDAY CSV] ✅ {len(befday_data)} pozisyon BEFDAY CSV'ye kaydedildi: {csv_path}")
                return True
            else:
                print("[BEFDAY CSV] ⚠️ Kaydedilecek pozisyon bulunamadı")
                return False
                
        except Exception as e:
            print(f"[BEFDAY CSV] ❌ CSV güncelleme hatası: {e}")
            return False

    def get_all_fills(self):
        """Tüm fill'leri döndür"""
        return self.data

    def get_fills_by_ticker(self, ticker, direction=None):
        """Belirli ticker için fill'leri döndür"""
        return [f for f in self.data if f['ticker'] == ticker and (direction is None or f['direction'] == direction)]

    def clear_all_data(self):
        """Tüm verileri temizle"""
        self.data = []
        self.snapshots = {}
        self._save()
        self._save_snapshots()
        print("[BDATA] ✅ Tüm veriler temizlendi")

    def export_to_csv(self):
        """BDATA ve BEFDAY CSV'lerini oluştur"""
        summary = self.get_position_summary_with_snapshot()
        
        # BDATA CSV
        self.update_csv()
        
        # BEFDAY CSV
        self.create_befday_csv(summary)
        
        print("[BDATA EXPORT] ✅ BDATA ve BEFDAY CSV'leri oluşturuldu") 