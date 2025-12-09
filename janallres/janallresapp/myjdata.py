"""
jdata Analiz Modülü
- Fill verilerini jdatalog.csv'den okuma
- ETF combined değerlerini hesaplama
- Performans analizi ve outperformans takibi

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janallres/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu dosyada özellikle:
✅ DOĞRU: JDATA_FILE = "jdatalog.csv" (StockTracker dizininde)
❌ YANLIŞ: JDATA_FILE = "janallresres/jdatalog.csv"
=================================
"""

from __future__ import annotations

import os
import csv
import time
from datetime import datetime
from typing import Callable, Dict, List, Any

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd

JDATA_FILE = "jdatalog.csv"  # Ana dizindeki jdatalog.csv dosyasını kullan

# Global olarak Final jdata sonuçlarını sakla
FINAL_JDATA_RESULTS = {}

def get_final_jdata_for_symbol(symbol: str) -> dict:
    """Bir symbol için Final jdata sonuçlarını döndür"""
    return FINAL_JDATA_RESULTS.get(symbol, {})

def get_symbol_performance_summary(symbol: str) -> str:
    """Bir symbol için performans özetini string olarak döndür (Take Profit pencerelerinde kullanım için)"""
    data = get_final_jdata_for_symbol(symbol)
    if not data:
        return f"{symbol}: Final jdata verisi bulunamadı"
    
    summary = f"{symbol} Performans:\n"
    summary += f"  Outperf Chg%: {data.get('outperf_chg_pct', 'N/A')}%\n"
    summary += f"  Timebased Bench Chg: ${data.get('timebased_bench_chg', 'N/A')}\n"
    summary += f"  Stock Chg%: {data.get('stock_chg_pct', 'N/A')}%\n"
    summary += f"  Bench Chg%: {data.get('bench_chg_pct', 'N/A')}%\n"
    summary += f"  Avg Cost: ${data.get('avg_cost', 'N/A')}\n"
    summary += f"  Current Price: ${data.get('current_price', 'N/A')}"
    
    return summary

# Benchmark coefficient map (absolute level calculation).
# Keys align with MainWindow.benchmark_formulas keys.
# NOT: Bu weights artık kullanılmıyor, main_window.benchmark_formulas kullanılıyor
# BENCHMARK_WEIGHTS: Dict[str, Dict[str, float]] = {
#     'DEFAULT': {'PFF': 1.04, 'TLT': -0.08, 'IEF': 0.0, 'IEI': 0.0},
#     'C400': {'PFF': 0.36, 'TLT': 0.36, 'IEF': 0.08, 'IEI': 0.0},
#     'C425': {'PFF': 0.368, 'TLT': 0.34, 'IEF': 0.092, 'IEI': 0.0},
#     'C450': {'PFF': 0.376, 'TLT': 0.32, 'IEF': 0.104, 'IEI': 0.0},
#     'C475': {'PFF': 0.384, 'TLT': 0.30, 'IEF': 0.116, 'IEI': 0.0},
#     'C500': {'PFF': 0.392, 'TLT': 0.28, 'IEF': 0.128, 'IEI': 0.0},
#     'C525': {'PFF': 0.40, 'TLT': 0.24, 'IEF': 0.14, 'IEI': 0.02},
#     'C550': {'PFF': 0.408, 'TLT': 0.20, 'IEF': 0.152, 'IEI': 0.04},
#     'C575': {'PFF': 0.416, 'TLT': 0.16, 'IEF': 0.164, 'IEI': 0.06},
#     'C600': {'PFF': 0.432, 'TLT': 0.12, 'IEF': 0.168, 'IEI': 0.08},
#     'C625': {'PFF': 0.448, 'TLT': 0.08, 'IEF': 0.172, 'IEI': 0.10},
#     'C650': {'PFF': 0.464, 'TLT': 0.04, 'IEF': 0.156, 'IEI': 0.14},
#     'C675': {'PFF': 0.480, 'TLT': 0.00, 'IEF': 0.140, 'IEI': 0.18},
#     'C700': {'PFF': 0.512, 'TLT': 0.00, 'IEF': 0.120, 'IEI': 0.168},
#     'C725': {'PFF': 0.544, 'TLT': 0.00, 'IEF': 0.100, 'IEI': 0.156},
#     'C750': {'PFF': 0.576, 'TLT': 0.00, 'IEF': 0.000, 'IEI': 0.224},
#     'C775': {'PFF': 0.608, 'TLT': 0.00, 'IEF': 0.000, 'IEI': 0.192},
#     'C800': {'PFF': 0.640, 'TLT': 0.00, 'IEF': 0.000, 'IEI': 0.160},
# }

PriceProvider = Callable[[str], float]


def get_pref_ibkr_symbol_from_hammer(hammer_symbol: str) -> str:
    """Hammer Pro formatındaki symbol'ü PREF IBKR formatına çevir"""
    # Eğer zaten PREF IBKR formatındaysa (örn: "EQH PRA", "PSA PRM") olduğu gibi döndür
    if " PR" in hammer_symbol:
        return hammer_symbol
    
    # Örnek: "EQH-A" -> "EQH PRA", "USB-H" -> "USB PRH"
    if "-" in hammer_symbol and len(hammer_symbol.split("-")) == 2:
        parts = hammer_symbol.split("-")
        if len(parts) == 2:
            base_symbol = parts[0]
            suffix = parts[1]
            # Tek karakterli suffix'i PR formatına çevir
            return f"{base_symbol} PR{suffix}"
    
    # Normal hisse senedi ise olduğu gibi döndür
    return hammer_symbol


def get_hammer_symbol_from_pref_ibkr(pref_ibkr_symbol: str) -> str:
    """PREF IBKR formatındaki symbol'ü Hammer Pro formatına çevir"""
    # Eğer zaten Hammer Pro formatındaysa (örn: "EQH-C", "PSA-P") olduğu gibi döndür
    if "-" in pref_ibkr_symbol and len(pref_ibkr_symbol.split("-")) == 2:
        return pref_ibkr_symbol
    
    # Örnek: "EQH PRA" -> "EQH-A", "USB PRH" -> "USB-H"
    if " PR" in pref_ibkr_symbol:
        parts = pref_ibkr_symbol.split(" PR")
        if len(parts) == 2:
            base_symbol = parts[0]
            suffix = parts[1]
            # Suffix'i tek karaktere çevir
            if suffix == "A":
                return f"{base_symbol}-A"
            elif suffix == "B":
                return f"{base_symbol}-B"
            elif suffix == "C":
                return f"{base_symbol}-C"
            elif suffix == "D":
                return f"{base_symbol}-D"
            elif suffix == "E":
                return f"{base_symbol}-E"
            elif suffix == "F":
                return f"{base_symbol}-F"
            elif suffix == "G":
                return f"{base_symbol}-G"
            elif suffix == "H":
                return f"{base_symbol}-H"
            elif suffix == "I":
                return f"{base_symbol}-I"
            elif suffix == "J":
                return f"{base_symbol}-J"
            elif suffix == "K":
                return f"{base_symbol}-K"
            elif suffix == "L":
                return f"{base_symbol}-L"
            elif suffix == "M":
                return f"{base_symbol}-M"
            elif suffix == "N":
                return f"{base_symbol}-N"
            elif suffix == "O":
                return f"{base_symbol}-O"
            elif suffix == "P":
                return f"{base_symbol}-P"
            elif suffix == "Q":
                return f"{base_symbol}-Q"
            elif suffix == "R":
                return f"{base_symbol}-R"
            elif suffix == "S":
                return f"{base_symbol}-S"
            elif suffix == "T":
                return f"{base_symbol}-T"
            elif suffix == "U":
                return f"{base_symbol}-U"
            elif suffix == "V":
                return f"{base_symbol}-V"
            elif suffix == "W":
                return f"{base_symbol}-W"
            elif suffix == "X":
                return f"{base_symbol}-X"
            elif suffix == "Y":
                return f"{base_symbol}-Y"
            elif suffix == "Z":
                return f"{base_symbol}-Z"
            else:
                # Sayısal suffix için
                return f"{base_symbol}-{suffix}"
    
    # PREF IBKR formatı değilse olduğu gibi döndür
    return pref_ibkr_symbol


def get_current_benchmark_value(benchmark_key: str, main_window=None) -> float:
    """Main window'daki benchmark formüllerini kullanarak current benchmark değerini hesapla - SADECE Hammer Pro"""
    try:
        print(f"[JDATA] 🔍 get_current_benchmark_value çağrıldı: '{benchmark_key}'")
        
        if not main_window:
            print(f"[JDATA] ❌ main_window yok")
            return 0.0
            
        if not hasattr(main_window, 'benchmark_formulas'):
            print(f"[JDATA] ❌ benchmark_formulas yok")
            return 0.0
        
        # Main window'daki benchmark formülünü al
        formula = main_window.benchmark_formulas.get(benchmark_key.upper(), main_window.benchmark_formulas['DEFAULT'])
        print(f"[JDATA] 🔍 {benchmark_key} formülü: {formula}")
        
        total = 0.0
        
        # SADECE Hammer Pro'dan ETF fiyatlarını al
        print(f"[JDATA] 🔍 Hammer bağlantısı kontrol ediliyor...")
        print(f"[JDATA] 🔍 hammer var: {hasattr(main_window, 'hammer')}")
        print(f"[JDATA] 🔍 hammer connected: {main_window.hammer.connected if hasattr(main_window, 'hammer') and main_window.hammer else False}")
        
        if hasattr(main_window, 'hammer') and main_window.hammer and main_window.hammer.connected:
            print(f"[JDATA] ✅ Hammer Pro bağlantısı var, ETF fiyatları alınıyor...")
            for etf, coefficient in formula.items():
                if coefficient == 0:
                    continue
                
                print(f"[JDATA] 🔍 {etf} için fiyat alınıyor (coefficient: {coefficient})")
                
                # Önce cached market data'dan al
                if hasattr(main_window, 'get_cached_market_data'):
                    cached_data = main_window.get_cached_market_data(etf)
                    if cached_data and 'last' in cached_data:
                        etf_price = float(cached_data['last'])
                        contribution = coefficient * etf_price
                        total += contribution
                        print(f"[JDATA] ✅ {etf} (cached): ${etf_price:.4f} * {coefficient} = ${contribution:.4f}")
                        continue
                
                # ETF fiyatını al
                if main_window:
                    etf_price = get_last_price_for_symbol(etf, main_window)
                else:
                    etf_price = float(get_last(etf) or 0.0)
                
                if etf_price > 0:
                    contribution = coefficient * etf_price
                    total += contribution
                    print(f"[JDATA] 🔍 {etf}: ${etf_price:.4f} * {coefficient} = ${contribution:.4f} (Hammer Pro)")
                else:
                    # Hammer Pro'dan alınamadıysa ETF Panel'den prev_close dene
                    if hasattr(main_window, 'etf_panel') and main_window.etf_panel:
                        try:
                            prev_close = main_window.etf_panel.get_etf_prev_close(etf)
                            if prev_close and prev_close > 0:
                                contribution = coefficient * prev_close
                                total += contribution
                                print(f"[JDATA] 🔍 {etf}: ${prev_close:.4f} * {coefficient} = ${contribution:.4f} (ETF Panel - Prev Close)")
                            else:
                                print(f"[JDATA] ❌ {etf} fiyatı ETF Panel'den de alınamadı (prev_close: {prev_close})")
                        except Exception as e:
                            print(f"[JDATA] ❌ ETF Panel'den {etf} prev_close alınırken hata: {e}")
                    else:
                        print(f"[JDATA] ❌ {etf} fiyatı alınamadı (Hammer Pro: 0, ETF Panel yok)")
        else:
            print(f"[JDATA] ❌ Hammer Pro bağlantısı yok - benchmark hesaplanamıyor")
            return 0.0
        
        final_total = round(total, 4)
        print(f"[JDATA] 🎯 {benchmark_key} benchmark toplam: ${final_total:.4f}")
        print(f"[JDATA] 🔍 Formül detayları:")
        for etf, coefficient in formula.items():
            if coefficient != 0:
                print(f"   {etf}: coefficient = {coefficient}")
        print(f"[JDATA] 🔍 Toplam: {final_total:.4f}")
        
        return final_total
        
    except Exception as e:
        print(f"[JDATA] ❌ Benchmark hesaplama hatası: {e}")
        import traceback
        traceback.print_exc()
        return 0.0


def get_last_price_for_symbol(symbol: str, main_window=None) -> float:
    """Symbol için son fiyatı döndür - PREF IBKR formatını Hammer Pro formatına çevirerek"""
    try:
        print(f"[JDATA] 🔍 get_last_price_for_symbol çağrıldı: '{symbol}'")
        
        # PREF IBKR formatını Hammer Pro formatına çevir
        hammer_symbol = get_hammer_symbol_from_pref_ibkr(symbol)
        print(f"[JDATA] 🔍 Conversion: '{symbol}' -> '{hammer_symbol}'")
        
        # 1. İLK DENEME: Hammer Pro'dan çek (convert edilmiş symbol ile)
        if main_window and hasattr(main_window, 'hammer') and main_window.hammer:
            market_data = main_window.hammer.get_market_data(hammer_symbol)
            if market_data and 'last' in market_data:
                last_price = float(market_data['last'])
                print(f"[JDATA] ✅ {symbol} -> {hammer_symbol}: ${last_price:.2f}")
                return last_price
        
        # 2. İKİNCİ DENEME: Mini450'deki DataFrame'den PREF IBKR formatında ara
        if main_window and hasattr(main_window, 'df') and not main_window.df.empty:
            # DataFrame'de PREF IBKR kolonunda symbol'ü ara
            if 'PREF IBKR' in main_window.df.columns:
                # Symbol'ü PREF IBKR formatında ara (örn: "EQH PRA")
                matching_rows = main_window.df[main_window.df['PREF IBKR'] == symbol]
                if not matching_rows.empty:
                    # Last kolonundaki değeri al
                    if 'Last' in matching_rows.columns:
                        last_price = matching_rows.iloc[0]['Last']
                        if pd.notna(last_price) and last_price != 'N/A':
                            try:
                                last_price = float(last_price)
                                print(f"[JDATA] ✅ {symbol} (Mini450 Last): ${last_price:.2f}")
                                return last_price
                            except (ValueError, TypeError):
                                pass
        
        # 3. ÜÇÜNCÜ DENEME: Cached market data'dan al (PREF IBKR formatında ara!)
        if main_window and hasattr(main_window, 'get_cached_market_data'):
            # Cache'de PREF IBKR formatında ara (örn: "EQH PRA")
            cached_data = main_window.get_cached_market_data(symbol)  # symbol zaten PREF IBKR formatında
            if cached_data and 'last' in cached_data:
                last_price = float(cached_data['last'])
                print(f"[JDATA] ✅ {symbol} (Cached): ${last_price:.2f}")
                return last_price
        
        # 4. SON DENEME: ETF Panel'den al
        if main_window and hasattr(main_window, 'etf_panel') and main_window.etf_panel:
            if symbol in main_window.etf_panel.etf_data:
                last_price = float(main_window.etf_panel.etf_data[symbol].get('last', 0))
                if last_price > 0:
                    print(f"[JDATA] ✅ {symbol} (ETF Panel): ${last_price:.2f}")
                    return last_price
                else:
                    # Last price yoksa prev_close dene
                    prev_close = main_window.etf_panel.get_etf_prev_close(symbol)
                    if prev_close and prev_close > 0:
                        print(f"[JDATA] ✅ {symbol} (ETF Panel - Prev Close): ${prev_close:.2f}")
                        return prev_close
                    else:
                        print(f"[JDATA] ❌ {symbol} fiyatı ETF Panel'den de alınamadı (last: {last_price}, prev_close: {prev_close})")
        
        return 0.0
    except Exception as e:
        print(f"[JDATA] ❌ {symbol} fiyat alma hatası: {e}")
        return 0.0


def get_benchmark_type_for_symbol(symbol: str, main_window=None) -> str:
    """Symbol'e göre benchmark tipini belirle"""
    if main_window and hasattr(main_window, 'get_benchmark_type_for_ticker'):
        return main_window.get_benchmark_type_for_ticker(symbol)
    
    # Fallback: PREF IBKR hisseleri için default
    if " PR" in symbol:
        return 'C400'  # Default
    return 'DEFAULT'


def load_summary_from_jdatalog(get_last: PriceProvider, main_window=None) -> List[Dict[str, Any]]:
    """jdatalog.csv'den pozisyon özetini yükle"""
    if not os.path.exists(JDATA_FILE):
        print(f"[JDATA] ⚠️ {JDATA_FILE} bulunamadı")
        return []
    
    rows: List[Dict[str, Any]] = []
    with open(JDATA_FILE, 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                # jdatalog.csv kolonları: fill_qty, symbol, fill_price, fill_time, Bench, Bench Val, TLT, IEF, IEI, PFF, SHY
                
                # Bench Val kolonunu formül ile hesapla (CSV'den okuma yerine)
                benchmark_key = r.get('Bench', 'DEFAULT')
                bench_val = 0.0
                
                # Eğer main_window'ta benchmark formülleri varsa hesapla
                if main_window and hasattr(main_window, 'benchmark_formulas'):
                    if benchmark_key in main_window.benchmark_formulas:
                        formula = main_window.benchmark_formulas[benchmark_key]
                        # ETF değerlerini CSV'den al ve formül ile hesapla
                        tlt_price = float(r.get('TLT', 0) or 0.0)
                        ief_price = float(r.get('IEF', 0) or 0.0)
                        iei_price = float(r.get('IEI', 0) or 0.0)
                        pff_price = float(r.get('PFF', 0) or 0.0)
                        
                        # Formül ile hesapla
                        for etf, coefficient in formula.items():
                            if etf == 'TLT' and tlt_price:
                                bench_val += tlt_price * coefficient
                            elif etf == 'IEF' and ief_price:
                                bench_val += ief_price * coefficient
                            elif etf == 'IEI' and iei_price:
                                bench_val += iei_price * coefficient
                            elif etf == 'PFF' and pff_price:
                                bench_val += pff_price * coefficient
                        
                        bench_val = round(bench_val, 4)
                        print(f"[JDATA] 🔍 {r['symbol']} {benchmark_key}: {bench_val:.4f} (formül: {formula})")
                    else:
                        print(f"[JDATA] ⚠️ {r['symbol']} için {benchmark_key} formülü bulunamadı")
                else:
                    print(f"[JDATA] ⚠️ main_window veya benchmark_formulas yok")
                
                rows.append({
                    'symbol': r['symbol'],
                    'qty': float(r['fill_qty']),
                    'price': float(r['fill_price']),
                    'bench_val': bench_val,  # Hesaplanan değer
                    'benchmark_key': benchmark_key,
                    'time': r.get('fill_time', '')
                })
            except Exception:
                continue
    
    print(f"[JDATA] 📊 {len(rows)} fill kaydı yüklendi")
    
    # Symbol'e göre grupla
    summary: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sym = r['symbol']
        if sym not in summary:
            summary[sym] = {
                'symbol': sym,
                'qty': 0.0,
                'cost_sum': 0.0,
                'bench_sum': 0.0,
                'benchmark_key': r['benchmark_key'],
                'fills': []  # Fill detayları
            }
        s = summary[sym]
        s['qty'] += r['qty']
        s['cost_sum'] += r['price'] * r['qty']
        s['bench_sum'] += r['bench_val'] * r['qty']
        s['benchmark_key'] = r['benchmark_key'] or s['benchmark_key']
        s['fills'].append({
            'time': r['time'],
            'qty': r['qty'],
            'price': r['price'],
            'bench_val': r['bench_val']
        })
    
    # Finalize
    out: List[Dict[str, Any]] = []
    for sym, s in summary.items():
        if s['qty'] == 0:
            continue
        
        avg_cost = s['cost_sum'] / s['qty']
        bench_val_avg = s['bench_sum'] / s['qty']
        
        # Current values - PREF IBKR formatını kullan
        current_px = get_last_price_for_symbol(sym, main_window)
        
        # Benchmark last price hesapla - main window'daki formülleri kullan
        current_bench = get_current_benchmark_value(s['benchmark_key'], main_window)
        
        # Performance calculation
        price_change = current_px - avg_cost
        bench_change = current_bench - bench_val_avg
        outperformance = price_change - bench_change
        
        out.append({
            'symbol': sym,
            'qty': s['qty'],
            'avg_cost': round(avg_cost, 4),
            'current_price': round(current_px, 4),
            'bench_val_avg': round(bench_val_avg, 4),
            'bench_val_now': round(current_bench, 4),
            'bench_diff': round(bench_change, 4),
            'pnl_vs_cost': round(price_change, 4),
            'outperformance': round(outperformance, 4),
            'benchmark_key': s['benchmark_key'],
            'fills': s['fills']
        })
    
    print(f"[JDATA] 📊 {len(out)} pozisyon özeti oluşturuldu")
    return out


def convert_jdatalog_to_pref_ibkr():
    """Ana dizindeki jdatalog.csv'deki Hammer Pro formatındaki sembolleri PREF IBKR formatına çevir"""
    # Ana dizindeki jdatalog.csv dosyasının yolu
    main_csv_path = "jdatalog.csv"
    if not os.path.exists(main_csv_path):
        print(f"[JDATA] ⚠️ {main_csv_path} bulunamadı")
        return
    
    try:
        import pandas as pd
        df = pd.read_csv(main_csv_path)
        updated_count = 0
        
        print(f"[JDATA] 🔄 Ana dizindeki jdatalog.csv symbol format conversion başlıyor...")
        
        for index, row in df.iterrows():
            old_symbol = row.get('symbol', '')
            new_symbol = get_pref_ibkr_symbol_from_hammer(old_symbol)
            
            if old_symbol != new_symbol:
                df.at[index, 'symbol'] = new_symbol
                updated_count += 1
                print(f"[JDATA] ✅ {old_symbol} -> {new_symbol}")
        
        if updated_count > 0:
            # Backup oluştur
            backup_file = f"{main_csv_path}.backup"
            df_original = pd.read_csv(main_csv_path)
            df_original.to_csv(backup_file, index=False)
            
            # Güncellenmiş dosyayı kaydet
            df.to_csv(main_csv_path, index=False)
            print(f"[JDATA] ✅ {updated_count} symbol güncellendi, backup: {backup_file}")
        else:
            print(f"[JDATA] ℹ️ Güncellenecek symbol bulunamadı")
            
    except Exception as e:
        print(f"[JDATA] ❌ Conversion hatası: {e}")


def show_jdata_window(parent, get_last: PriceProvider):
    """jdatalog.csv analiz penceresi"""
    data = load_summary_from_jdatalog(get_last, parent)  # parent parametresini geçiyoruz
    
    win = tk.Toplevel(parent)
    win.title("jdata Analiz - Fill Geçmişi ve Performans")
    win.geometry("1400x700")
    
    # Notebook (tabbed interface)
    notebook = ttk.Notebook(win)
    notebook.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Tab 1: Özet Tablosu
    summary_frame = ttk.Frame(notebook)
    notebook.add(summary_frame, text="Özet")
    
    cols = ['symbol', 'qty', 'avg_cost', 'current_price', 'bench_val_avg', 'bench_val_now', 'bench_diff', 'pnl_vs_cost', 'outperformance']
    headers = ['Symbol', 'Qty', 'Avg Cost', 'Current', 'Bench Avg', 'Bench Now', 'Bench Δ', 'PnL', 'Outperf']
    
    tree = ttk.Treeview(summary_frame, columns=cols, show='headings', height=15)
    for c, h in zip(cols, headers):
        tree.heading(c, text=h)
        tree.column(c, width=120, anchor='center')
    
    tree.pack(fill='both', expand=True, padx=5, pady=5)
    
    for r in data:
        vals = [r[c] for c in cols]
        tree.insert('', 'end', values=vals)
    
    # Tab 2: Fill Detayları - Yeni kolonlarla güncellendi
    detail_frame = ttk.Frame(notebook)
    notebook.add(detail_frame, text="Fill Detayları")
    
    # Yeni kolonlar: ETF kolonları yerine performans kolonları + Fill Type
    detail_cols = ['symbol', 'time', 'qty', 'price', 'bench_fill', 'bench_last', 'stock_last', 'bench_chg_pct', 'stock_chg_pct', 'outperf_chg_pct', 'fill_type']
    detail_headers = ['Symbol', 'Time', 'Qty', 'Price', 'Bench Fill', 'Bench Last', 'Stock Last', 'Bench Chg%', 'Stock Chg%', 'Outperf Chg%', 'Fill Type']
    
    detail_tree = ttk.Treeview(detail_frame, columns=detail_cols, show='headings', height=20)
    
    # Kolon genişliklerini ayarla
    for c, h in zip(detail_cols, detail_headers):
        detail_tree.heading(c, text=h)
        if c in ['symbol', 'qty']:
            detail_tree.column(c, width=100, anchor='center')
        elif c == 'price':
            detail_tree.column(c, width=80, anchor='center')
        elif c == 'time':
            detail_tree.column(c, width=150, anchor='center')
        elif c in ['bench_fill', 'bench_last', 'stock_last']:
            detail_tree.column(c, width=90, anchor='center')
        elif c == 'fill_type':
            detail_tree.column(c, width=120, anchor='center')
        else:  # Yüzde kolonları
            detail_tree.column(c, width=100, anchor='center')
    
    detail_tree.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Tüm fill'leri jdatalog.csv'den yükle ve yeni kolonları hesapla
    if os.path.exists(JDATA_FILE):
        with open(JDATA_FILE, 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                try:
                    # Yeni kolonları hesapla
                    symbol = r['symbol']  # CSV'den gelen orijinal symbol (PREF IBKR formatı)
                    side = r.get('side', 'BUY')  # BUY veya SELL
                    quantity = float(r['quantity'])
                    fill_price = float(r['fill_price'])
                    bench_val_from_csv = float(r.get('Bench Val', 0) or 0.0)  # CSV'den gelen benchmark değeri
                    
                    # Fill Type hesapla - mevcut pozisyonu al
                    current_position = get_current_position_for_symbol(symbol, parent)
                    fill_type = calculate_fill_type(symbol, side, quantity, current_position)
                    print(f"[FILL TYPE] {symbol}: {side} {quantity} (Mevcut: {current_position}) -> {fill_type}")
                    
                    # Eğer CSV'den gelen Bench Val 0 ise, sağ taraftaki ETF kolonlarından hesapla
                    if bench_val_from_csv == 0:
                        print(f"[JDATA] 🔍 {symbol} için CSV'de Bench Val 0, ETF kolonlarından hesaplanıyor...")
                        benchmark_key = r.get('Bench', 'DEFAULT')
                        # CSV'deki ETF fiyatlarını al
                        tlt_price = float(r.get('TLT', 0) or 0.0)
                        ief_price = float(r.get('IEF', 0) or 0.0)
                        iei_price = float(r.get('IEI', 0) or 0.0)
                        pff_price = float(r.get('PFF', 0) or 0.0)
                        
                        # Main window'daki benchmark formüllerini kullan
                        if hasattr(parent, 'benchmark_formulas') and benchmark_key in parent.benchmark_formulas:
                            formula = parent.benchmark_formulas[benchmark_key]
                            print(f"[JDATA] 🔍 {symbol} için {benchmark_key} formülü kullanılıyor: {formula}")
                            
                            bench_fill = 0.0
                            for etf, coefficient in formula.items():
                                if etf == 'PFF' and pff_price > 0:
                                    contribution = pff_price * coefficient
                                    bench_fill += contribution
                                    print(f"[JDATA] 🔍 PFF: ${pff_price:.2f} * {coefficient} = ${contribution:.4f}")
                                elif etf == 'TLT' and tlt_price > 0:
                                    contribution = tlt_price * coefficient
                                    bench_fill += contribution
                                    print(f"[JDATA] 🔍 TLT: ${tlt_price:.2f} * {coefficient} = ${contribution:.4f}")
                                elif etf == 'IEF' and ief_price > 0:
                                    contribution = ief_price * coefficient
                                    bench_fill += contribution
                                    print(f"[JDATA] 🔍 IEF: ${ief_price:.2f} * {coefficient} = ${contribution:.4f}")
                                elif etf == 'IEI' and iei_price > 0:
                                    contribution = iei_price * coefficient
                                    bench_fill += contribution
                                    print(f"[JDATA] 🔍 IEI: ${iei_price:.2f} * {coefficient} = ${contribution:.4f}")
                            
                            print(f"[JDATA] ✅ {symbol} {benchmark_key} benchmark (main window formülü): ${bench_fill:.4f}")
                        else:
                            # Fallback: Eski formülleri kullan
                            print(f"[JDATA] ⚠️ {symbol} için {benchmark_key} formülü bulunamadı, eski formül kullanılıyor")
                            if benchmark_key == 'DEFAULT':
                                # DEFAULT formül: PFF * 1.04 + TLT * (-0.08)
                                bench_fill = (pff_price * 1.04) + (tlt_price * (-0.08))
                                print(f"[JDATA] ✅ {symbol} DEFAULT benchmark (eski formül): PFF(${pff_price:.2f} * 1.04) + TLT(${tlt_price:.2f} * -0.08) = ${bench_fill:.4f}")
                            else:
                                # Diğer benchmark'ler için eski formülleri uygula
                                bench_fill = 0.0
                                if benchmark_key == 'C400':
                                    bench_fill = (pff_price * 0.36) + (tlt_price * 0.36) + (ief_price * 0.08)
                                elif benchmark_key == 'C425':
                                    bench_fill = (pff_price * 0.368) + (tlt_price * 0.34) + (ief_price * 0.092)
                                elif benchmark_key == 'C450':
                                    bench_fill = (pff_price * 0.376) + (tlt_price * 0.32) + (ief_price * 0.104)
                                elif benchmark_key == 'C475':
                                    bench_fill = (pff_price * 0.384) + (tlt_price * 0.30) + (ief_price * 0.116)
                                elif benchmark_key == 'C500':
                                    bench_fill = (pff_price * 0.392) + (tlt_price * 0.28) + (ief_price * 0.128)
                                elif benchmark_key == 'C525':
                                    bench_fill = (pff_price * 0.40) + (tlt_price * 0.24) + (ief_price * 0.14) + (iei_price * 0.02)
                                elif benchmark_key == 'C550':
                                    bench_fill = (pff_price * 0.408) + (tlt_price * 0.20) + (ief_price * 0.152) + (iei_price * 0.04)
                                elif benchmark_key == 'C575':
                                    bench_fill = (pff_price * 0.416) + (tlt_price * 0.16) + (ief_price * 0.164) + (iei_price * 0.06)
                                elif benchmark_key == 'C600':
                                    bench_fill = (pff_price * 0.432) + (tlt_price * 0.12) + (ief_price * 0.168) + (iei_price * 0.08)
                                elif benchmark_key == 'C625':
                                    bench_fill = (pff_price * 0.448) + (tlt_price * 0.08) + (ief_price * 0.172) + (iei_price * 0.10)
                                elif benchmark_key == 'C650':
                                    bench_fill = (pff_price * 0.464) + (tlt_price * 0.04) + (ief_price * 0.156) + (iei_price * 0.14)
                                elif benchmark_key == 'C675':
                                    bench_fill = (pff_price * 0.480) + (ief_price * 0.140) + (iei_price * 0.18)
                                elif benchmark_key == 'C700':
                                    bench_fill = (pff_price * 0.512) + (ief_price * 0.120) + (iei_price * 0.168)
                                elif benchmark_key == 'C725':
                                    bench_fill = (pff_price * 0.544) + (ief_price * 0.100) + (iei_price * 0.156)
                                elif benchmark_key == 'C750':
                                    bench_fill = (pff_price * 0.576) + (iei_price * 0.224)
                                elif benchmark_key == 'C775':
                                    bench_fill = (pff_price * 0.608) + (iei_price * 0.192)
                                elif benchmark_key == 'C800':
                                    bench_fill = (pff_price * 0.640) + (iei_price * 0.160)
                                
                                print(f"[JDATA] ✅ {symbol} {benchmark_key} benchmark (eski formül): ${bench_fill:.4f}")
                    else:
                        # CSV'den gelen değer kullan
                        bench_fill = bench_val_from_csv
                        print(f"[JDATA] ✅ {symbol} CSV'den Bench Val: ${bench_fill:.4f}")
                    
                    # Current prices - PREF IBKR formatını kullan (Hammer Pro'ya convert ederek)
                    stock_last = get_last_price_for_symbol(symbol, parent)
                    
                    # Benchmark last price hesapla - main window'daki formülleri kullan
                    benchmark_key = r.get('Bench', 'DEFAULT')
                    bench_last = get_current_benchmark_value(benchmark_key, parent)
                    
                    # Değişim yüzdeleri
                    bench_chg_pct = ((bench_last / bench_fill) - 1) * 100 if bench_fill > 0 else 0
                    stock_chg_pct = ((stock_last / fill_price) - 1) * 100 if fill_price > 0 else 0
                    outperf_chg_pct = stock_chg_pct - bench_chg_pct
                    
                    vals = [
                        symbol,  # Tabloda PREF IBKR formatında göster (örn: "EQH PRC")
                        r['fill_time'],
                        r['fill_qty'],
                        f"${fill_price:.2f}",
                        f"${bench_fill:.4f}",  # Fill anındaki benchmark değeri
                        f"${bench_last:.4f}",  # Şu anki benchmark değeri
                        f"${stock_last:.2f}",
                        f"{bench_chg_pct:+.2f}%",
                        f"{stock_chg_pct:+.2f}%",
                        f"{outperf_chg_pct:+.2f}%",
                        fill_type  # Fill Type kolonu
                    ]
                    detail_tree.insert('', 'end', values=vals)
                except Exception as e:
                    print(f"[JDATA] ⚠️ Fill detayı işlenirken hata: {e}")
                    continue
    
    # Tab 3: Final jdata - Her unique hisse için ağırlıklı ortalama hesaplamaları
    final_frame = ttk.Frame(notebook)
    notebook.add(final_frame, text="Final jdata")
    
    # Final jdata kolonları - PnL ve Outperf yerine yüzdelik değişimler + Mevcut Pozisyon + Yeni kolonlar
    final_cols = ['symbol', 'total_qty', 'current_position', 'avg_cost', 'avg_fill_time', 'avg_bench_cost', 'current_price', 'current_bench', 'timebased_bench_chg', 'bench_chg_pct', 'stock_chg_pct', 'outperf_chg_pct', 'grup', 'final_fb', 'group_avg_final_thg']
    final_headers = ['Symbol', 'Total Qty', 'Mevcut Pozisyon', 'Avg Cost', 'Avg Fill Time', 'Avg Bench Cost', 'Current Price', 'Current Bench', 'Timebased Bench Chg', 'Bench Chg%', 'Stock Chg%', 'Outperf Chg%', 'Grup', 'Final FB', 'Grup Avg Final THG']
    
    final_tree = ttk.Treeview(final_frame, columns=final_cols, show='headings', height=20)
    
    # Font boyutunu küçült
    style = ttk.Style()
    style.configure("Treeview", font=('Arial', 8))
    style.configure("Treeview.Heading", font=('Arial', 8, 'bold'))
    
    # Kolon genişliklerini ayarla - daha küçük boyutlar
    for c, h in zip(final_cols, final_headers):
        final_tree.heading(c, text=h)
        if c in ['symbol']:
            final_tree.column(c, width=80, anchor='center')
        elif c in ['total_qty', 'current_position']:
            final_tree.column(c, width=70, anchor='center')
        elif c in ['avg_cost', 'avg_bench_cost', 'current_price', 'current_bench', 'timebased_bench_chg']:
            final_tree.column(c, width=80, anchor='center')
        elif c == 'avg_fill_time':
            final_tree.column(c, width=100, anchor='center')
        elif c in ['grup']:
            final_tree.column(c, width=90, anchor='center')
        elif c in ['final_fb', 'group_avg_final_thg']:
            final_tree.column(c, width=90, anchor='center')
        else:  # Yüzdelik değişim kolonları
            final_tree.column(c, width=70, anchor='center')
    
    final_tree.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Global olarak Final jdata sonuçlarını sakla
    FINAL_JDATA_RESULTS = {}

    def get_final_jdata_for_symbol(symbol: str) -> dict:
        """Bir symbol için Final jdata sonuçlarını döndür"""
        return FINAL_JDATA_RESULTS.get(symbol, {})

    def get_group_from_symbol(symbol):
        """JFIN emirleriyle aynı mantık: Symbol'ü grup dosyalarında ara"""
        try:
            # Grup dosya eşleşmesi - JFIN emirleriyle aynı
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
                        df = pd.read_csv(file_name)
                        if symbol in df['PREF IBKR'].tolist():
                            print(f"[FINAL JDATA] 🎯 {symbol} -> {group} grubunda bulundu")
                            return group
                    except Exception as e:
                        print(f"[FINAL JDATA] ⚠️ {file_name} okuma hatası: {e}")
                        continue
            
            print(f"[FINAL JDATA] ⚠️ {symbol} hiçbir grup dosyasında bulunamadı")
            return "N/A"
            
        except Exception as e:
            print(f"[FINAL JDATA] ❌ {symbol} grup bulma hatası: {e}")
            return "N/A"

    def get_symbol_performance_summary(symbol: str) -> str:
        """Bir symbol için performans özetini string olarak döndür (Take Profit pencerelerinde kullanım için)"""
        data = get_final_jdata_for_symbol(symbol)
        if not data:
            return f"{symbol}: Final jdata verisi bulunamadı"
        
        summary = f"{symbol} Performans:\n"
        summary += f"  Outperf Chg%: {data.get('outperf_chg_pct', 'N/A')}%\n"
        summary += f"  Timebased Bench Chg: ${data.get('timebased_bench_chg', 'N/A')}\n"
        summary += f"  Stock Chg%: {data.get('stock_chg_pct', 'N/A')}%\n"
        summary += f"  Bench Chg%: {data.get('bench_chg_pct', 'N/A')}%\n"
        summary += f"  Avg Cost: ${data.get('avg_cost', 'N/A')}\n"
        summary += f"  Current Price: ${data.get('current_price', 'N/A')}"
        
        return summary

    def calculate_final_jdata():
        """Final jdata sekmesi için ağırlıklı ortalama hesaplamaları yap"""
        global FINAL_JDATA_RESULTS
        try:
            print("[FINAL JDATA] 🔄 Final jdata hesaplama başlatılıyor...")
            
            # jdatalog.csv'yi oku
            if not os.path.exists(JDATA_FILE):
                print(f"[FINAL JDATA] ❌ {JDATA_FILE} bulunamadı")
                return
            
            print(f"[FINAL JDATA] 📁 {JDATA_FILE} dosyası bulundu")
            
            # CSV'yi oku
            df = pd.read_csv(JDATA_FILE)
            print(f"[FINAL JDATA] 📊 {len(df)} satır okundu")
            print(f"[FINAL JDATA] 🔍 CSV kolonları: {list(df.columns)}")
            
            if df.empty:
                print("[FINAL JDATA] ❌ CSV boş")
                return
            
            # Final FB ve Grup bilgilerini yükle - JFIN emirleriyle aynı mantık
            print("[FINAL JDATA] 🔄 Final FB ve Grup bilgileri JFIN emirleriyle aynı mantıkla yükleniyor...")
            final_fb_data = {}
            group_avg_final_thg = {}
            
            # Parent'tan DataFrame'i al
            if hasattr(parent, 'df') and not parent.df.empty:
                print(f"[FINAL JDATA] 📁 Parent DataFrame bulundu: {len(parent.df)} satır")
                
                # Final FB skorlarını al
                for _, row in parent.df.iterrows():
                    symbol = row.get('PREF IBKR', '')
                    final_fb = row.get('Final_FB_skor', 0)
                    
                    if symbol and pd.notna(final_fb) and final_fb != 0:
                        final_fb_data[symbol] = final_fb
                
                print(f"[FINAL JDATA] ✅ {len(final_fb_data)} hisse için Final FB skoru yüklendi")
                
                # Grup ortalama Final THG hesapla - JFIN emirleriyle aynı mantık
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
                
                for group, file_name in group_file_map.items():
                    if os.path.exists(file_name):
                        try:
                            df = pd.read_csv(file_name)
                            group_symbols = set(df['PREF IBKR'].tolist())
                            
                            # Parent DataFrame'den bu gruba ait hisselerin Final THG değerlerini al
                            group_rows = parent.df[parent.df['PREF IBKR'].isin(group_symbols)]
                            if not group_rows.empty and 'FINAL_THG' in parent.df.columns:
                                final_thg_values = group_rows['FINAL_THG'].dropna()
                                if not final_thg_values.empty:
                                    group_avg_final_thg[group] = final_thg_values.mean()
                                    print(f"[FINAL JDATA] 📊 {group} grubu ortalama Final THG: {group_avg_final_thg[group]:.2f}")
                        except Exception as e:
                            print(f"[FINAL JDATA] ⚠️ {group} grup hesaplama hatası: {e}")
                
                print(f"[FINAL JDATA] ✅ {len(group_avg_final_thg)} grup için ortalama Final THG hesaplandı")
            else:
                print(f"[FINAL JDATA] ⚠️ Parent DataFrame bulunamadı")
            
            # Her unique hisse için grupla
            final_data = {}
            
            for _, row in df.iterrows():
                symbol = row['symbol']
                qty = float(row['fill_qty'])
                price = float(row['fill_price'])
                fill_time = pd.to_datetime(row['fill_time'])
                bench_val = float(row.get('Bench Val', 0) or 0.0)
                
                # Her satır için benchmark key'i al
                benchmark_key = row.get('Bench', 'DEFAULT')
                
                # Eğer benchmark değeri 0 ise, hesapla
                if bench_val == 0:
                    # CSV'deki ETF fiyatlarını al
                    tlt_price = float(row.get('TLT', 0) or 0.0)
                    ief_price = float(row.get('IEF', 0) or 0.0)
                    iei_price = float(row.get('IEI', 0) or 0.0)
                    pff_price = float(row.get('PFF', 0) or 0.0)
                    
                    # Main window'daki benchmark formüllerini kullan
                    if hasattr(parent, 'benchmark_formulas') and benchmark_key in parent.benchmark_formulas:
                        formula = parent.benchmark_formulas[benchmark_key]
                        bench_val = 0.0
                        print(f"[FINAL JDATA] 🔍 Fill anında {symbol} için {benchmark_key} formülü: {formula}")
                        for etf, coefficient in formula.items():
                            if etf == 'PFF' and pff_price > 0:
                                contribution = pff_price * coefficient
                                bench_val += contribution
                                print(f"[FINAL JDATA] 🔍 {etf}: ${pff_price:.2f} * {coefficient} = ${contribution:.4f}")
                            elif etf == 'TLT' and tlt_price > 0:
                                contribution = tlt_price * coefficient
                                bench_val += contribution
                                print(f"[FINAL JDATA] 🔍 {etf}: ${tlt_price:.2f} * {coefficient} = ${contribution:.4f}")
                            elif etf == 'IEF' and ief_price > 0:
                                contribution = ief_price * coefficient
                                bench_val += contribution
                                print(f"[FINAL JDATA] 🔍 {etf}: ${ief_price:.2f} * {coefficient} = ${contribution:.4f}")
                            elif etf == 'IEI' and iei_price > 0:
                                contribution = iei_price * coefficient
                                bench_val += contribution
                                print(f"[FINAL JDATA] 🔍 {etf}: ${iei_price:.2f} * {coefficient} = ${contribution:.4f}")
                        print(f"[FINAL JDATA] 🔍 {symbol} fill anında toplam benchmark: ${bench_val:.4f}")
                
                if symbol not in final_data:
                    final_data[symbol] = {
                        'qty_list': [],
                        'price_list': [],
                        'time_list': [],
                        'bench_list': [],
                        'benchmark_key': benchmark_key  # Benchmark key'i sakla
                    }
                else:
                    # Eğer zaten varsa, benchmark_key'i güncelle (aynı hisse için farklı benchmark olabilir)
                    final_data[symbol]['benchmark_key'] = benchmark_key
                
                final_data[symbol]['qty_list'].append(qty)
                final_data[symbol]['price_list'].append(price)
                final_data[symbol]['time_list'].append(fill_time)
                final_data[symbol]['bench_list'].append(bench_val)
            
            # Her hisse için ağırlıklı ortalamaları hesapla
            final_results = []
            
            for symbol, data in final_data.items():
                qty_list = data['qty_list']
                price_list = data['price_list']
                time_list = data['time_list']
                bench_list = data['bench_list']
                
                total_qty = sum(qty_list)
                
                # Ağırlıklı ortalama maliyet
                weighted_cost = sum(qty * price for qty, price in zip(qty_list, price_list))
                avg_cost = weighted_cost / total_qty if total_qty > 0 else 0
                
                # Ağırlıklı ortalama benchmark maliyeti
                weighted_bench = sum(qty * bench for qty, bench in zip(qty_list, bench_list))
                avg_bench_cost = weighted_bench / total_qty if total_qty > 0 else 0
                
                # Ağırlıklı ortalama fill zamanı
                # Zamanları timestamp'e çevir ve ağırlıklı ortalama hesapla
                time_weights = [qty / total_qty for qty in qty_list]
                weighted_timestamp = sum(weight * time.timestamp() for weight, time in zip(time_weights, time_list))
                avg_timestamp = weighted_timestamp
                avg_fill_time = pd.to_datetime(avg_timestamp, unit='s').strftime('%Y-%m-%d %H:%M')
                
                # Şu anki benchmark değerini hesapla (güncel market data ile - Fill detayları sekmesindeki gibi)
                current_bench = get_current_benchmark_value(data['benchmark_key'], parent)
                
                # Eğer market data alınamıyorsa 0 olmalı
                if current_bench == 0.0:
                    print(f"[FINAL JDATA] ⚠️ {symbol} için güncel benchmark data alınamadı, 0 kullanılıyor")
                
                # Güncel fiyat ve benchmark
                current_price = get_last_price_for_symbol(symbol, parent)
                
                # Timebased Bench Chg hesapla: Current Price - Avg Cost - (Bugün - Avg Fill Time) / 200
                from datetime import datetime
                today = datetime.now()
                avg_fill_datetime = datetime.strptime(avg_fill_time, '%Y-%m-%d %H:%M')
                time_diff_days = (today - avg_fill_datetime).total_seconds() / (24 * 3600)  # Gün cinsinden
                time_penalty = time_diff_days / 200
                timebased_bench_chg = current_price - avg_cost - time_penalty
                
                print(f"[FINAL JDATA] 🔍 {symbol} Timebased Bench Chg: {current_price:.4f} - {avg_cost:.4f} - ({time_diff_days:.2f} gün / 200) = {timebased_bench_chg:.4f}")
                
                # Debug bilgisi - ETF fiyatlarını da göster
                print(f"[FINAL JDATA] 🔍 {symbol}: benchmark_key={data['benchmark_key']}")
                print(f"   Fill anında: avg_bench={avg_bench_cost:.4f}")
                print(f"   Şu anda: current_bench={current_bench:.4f}")
                print(f"   Fark: {abs(current_bench - avg_bench_cost):.4f}")
                
                # Yüzdelik değişim hesaplamaları
                bench_chg_pct = 0.0
                stock_chg_pct = 0.0
                outperf_chg_pct = 0.0
                
                if avg_bench_cost > 0:
                    bench_chg_pct = ((current_bench - avg_bench_cost) / avg_bench_cost) * 100
                
                if avg_cost > 0:
                    stock_chg_pct = ((current_price - avg_cost) / avg_cost) * 100
                
                # Outperformance yüzdesi: Stock değişimi - Benchmark değişimi
                outperf_chg_pct = stock_chg_pct - bench_chg_pct
                
                print(f"   Benchmark değişimi: {bench_chg_pct:.2f}%")
                print(f"   Stock değişimi: {stock_chg_pct:.2f}%")
                print(f"   Outperformance: {outperf_chg_pct:.2f}%")
                
                # ETF fiyatlarını da kontrol et
                if hasattr(parent, 'benchmark_formulas') and data['benchmark_key'] in parent.benchmark_formulas:
                    formula = parent.benchmark_formulas[data['benchmark_key']]
                    print(f"   Formül: {formula}")
                    
                    # Şu anki ETF fiyatlarını al
                    if hasattr(parent, 'hammer') and parent.hammer and parent.hammer.connected:
                        print(f"   🔍 Hammer Pro'dan güncel ETF fiyatları:")
                        for etf, coefficient in formula.items():
                            if coefficient != 0:
                                market_data = parent.hammer.get_market_data(etf)
                                if market_data and 'last' in market_data:
                                    current_etf_price = float(market_data['last'])
                                    contribution = current_etf_price * coefficient
                                    print(f"      {etf}: ${current_etf_price:.4f} * {coefficient} = ${contribution:.4f}")
                                else:
                                    print(f"      {etf}: Fiyat alınamadı")
                    
                    # Fill anındaki ETF fiyatlarını da göster (CSV'den)
                    print(f"   🔍 Fill anındaki ETF fiyatları (CSV'den):")
                    for etf, coefficient in formula.items():
                        if coefficient != 0:
                            if etf == 'PFF':
                                fill_price = float(row.get('PFF', 0) or 0.0)
                            elif etf == 'TLT':
                                fill_price = float(row.get('TLT', 0) or 0.0)
                            elif etf == 'IEF':
                                fill_price = float(row.get('IEF', 0) or 0.0)
                            elif etf == 'IEI':
                                fill_price = float(row.get('IEI', 0) or 0.0)
                            else:
                                fill_price = 0.0
                            
                            if fill_price > 0:
                                contribution = fill_price * coefficient
                                print(f"      {etf}: ${fill_price:.4f} * {coefficient} = ${contribution:.4f}")
                            else:
                                print(f"      {etf}: Fiyat yok veya 0")
                
                # Benchmark farkı çok büyükse uyarı ver
                benchmark_diff = abs(current_bench - avg_bench_cost)
                if benchmark_diff > 1.0:  # 1 puan üzerinde fark varsa
                    print(f"   ⚠️ UYARI: Benchmark farkı çok büyük: {benchmark_diff:.4f}")
                    print(f"      Bu, ETF fiyatlarında büyük değişim veya hesaplama hatası olabilir")
                
                # Mevcut pozisyonu hesapla (Hammer Pro'dan)
                current_position = 0
                if hasattr(parent, 'hammer') and parent.hammer and parent.hammer.connected:
                    try:
                        # Symbol'ü Hammer Pro formatına çevir
                        hammer_symbol = get_hammer_symbol_from_pref_ibkr(symbol)
                        market_data = parent.hammer.get_market_data(hammer_symbol)
                        if market_data and 'position' in market_data:
                            current_position = float(market_data['position'])
                        else:
                            # Position bulunamadıysa 0 kullan
                            current_position = 0
                    except Exception as e:
                        print(f"[FINAL JDATA] ⚠️ {symbol} pozisyon bilgisi alınamadı: {e}")
                        current_position = 0
                
                # Yeni kolonlar için verileri al - JFIN emirleriyle aynı mantık
                final_fb_value = final_fb_data.get(symbol, 0)
                grup_value = "N/A"
                group_avg_final_thg_value = 0
                
                # Grup bilgisini JFIN emirleriyle aynı mantıkla bul
                grup_value = get_group_from_symbol(symbol)
                
                # Final FB skorunu al - parent DataFrame'den
                if hasattr(parent, 'df') and not parent.df.empty:
                    symbol_row = parent.df[parent.df['PREF IBKR'] == symbol]
                    if not symbol_row.empty and 'Final_FB_skor' in parent.df.columns:
                        final_fb_value = symbol_row['Final_FB_skor'].iloc[0]
                        if pd.isna(final_fb_value):
                            final_fb_value = 0
                
                # Grup ortalama Final THG al - JFIN emirleriyle aynı mantık
                if grup_value and grup_value != 'N/A' and grup_value in group_avg_final_thg:
                    group_avg_final_thg_value = group_avg_final_thg[grup_value]
                
                print(f"[FINAL JDATA] ✅ {symbol} -> Grup: {grup_value}, Final FB: {final_fb_value}, Group Avg Final THG: {group_avg_final_thg_value:.2f}")
                
                final_results.append({
                    'symbol': symbol,
                    'total_qty': total_qty,
                    'current_position': current_position,
                    'avg_cost': round(avg_cost, 4),
                    'avg_fill_time': avg_fill_time,
                    'avg_bench_cost': round(avg_bench_cost, 4),
                    'current_price': round(current_price, 4),
                    'current_bench': round(current_bench, 4),
                    'timebased_bench_chg': round(timebased_bench_chg, 4),
                    'bench_chg_pct': round(bench_chg_pct, 2),
                    'stock_chg_pct': round(stock_chg_pct, 2),
                    'outperf_chg_pct': round(outperf_chg_pct, 2),
                    'grup': grup_value,
                    'final_fb': round(final_fb_value, 2) if final_fb_value != 0 else "",
                    'group_avg_final_thg': round(group_avg_final_thg_value, 2) if group_avg_final_thg_value != 0 else ""
                })
                
                # Global olarak sakla - Take Profit pencerelerinde kullanmak için
                FINAL_JDATA_RESULTS[symbol] = {
                    'outperf_chg_pct': round(outperf_chg_pct, 2),
                    'timebased_bench_chg': round(timebased_bench_chg, 4),
                    'avg_cost': round(avg_cost, 4),
                    'current_price': round(current_price, 4),
                    'bench_chg_pct': round(bench_chg_pct, 2),
                    'stock_chg_pct': round(stock_chg_pct, 2),
                    'current_position': current_position
                }
                
                print(f"[FINAL JDATA] 💾 {symbol} verileri global olarak saklandı")
            
            # Final jdata tablosunu güncelle
            for item in final_tree.get_children():
                final_tree.delete(item)
            
            for result in final_results:
                vals = [result[c] for c in final_cols]
                final_tree.insert('', 'end', values=vals)
            
            print(f"[FINAL JDATA] ✅ {len(final_results)} hisse için final hesaplamalar tamamlandı")
            
        except Exception as e:
            print(f"[FINAL JDATA] ❌ Final jdata hesaplama hatası: {e}")
    
    # CSV export fonksiyonu
    def export_final_jdata():
        """Final jdata'yı CSV olarak export et"""
        try:
            # Mevcut final jdata'yı al
            data_to_export = []
            for item in final_tree.get_children():
                values = final_tree.item(item)['values']
                data_to_export.append(dict(zip(final_cols, values)))
            
            if not data_to_export:
                messagebox.showwarning("Uyarı", "Export edilecek veri bulunamadı!")
                return
            
            # CSV olarak kaydet
            filename = f"final_jdata_{time.strftime('%Y%m%d_%H%M%S')}.csv"
            df_export = pd.DataFrame(data_to_export)
            df_export.to_csv(filename, index=False, encoding='utf-8')
            
            messagebox.showinfo("Başarılı", f"Final jdata {filename} dosyasına export edildi!")
            print(f"[FINAL JDATA] 📁 {filename} dosyasına export edildi")
            
        except Exception as e:
            print(f"[FINAL JDATA] ❌ Export hatası: {e}")
            messagebox.showerror("Hata", f"Export hatası: {e}")
    
    # Final jdata hesapla butonu
    final_calc_button = ttk.Button(final_frame, text="Final jdata Hesapla", command=calculate_final_jdata)
    final_calc_button.pack(pady=5)
    
    # Export butonu
    export_button = ttk.Button(final_frame, text="CSV Export", command=export_final_jdata)
    export_button.pack(pady=5)
    
    # İlk hesaplamayı otomatik yap
    print("[JDATA] 🔄 Final jdata sekmesi ilk açılışta hesaplanıyor...")
    calculate_final_jdata()
    
    # Refresh button
    def do_refresh():
        print("[JDATA] 🔄 Refresh başlatılıyor...")
        
        # Summary tab'ını yenile
        for item in tree.get_children():
            tree.delete(item)
        for r in load_summary_from_jdatalog(get_last, parent):  # parent parametresini geçiyoruz
            tree.insert('', 'end', values=[r[c] for c in cols])
        
        # Detail tab'ını yenile
        for item in detail_tree.get_children():
            detail_tree.delete(item)
        if os.path.exists(JDATA_FILE):
            with open(JDATA_FILE, 'r', encoding='utf-8') as f:
                for r in csv.DictReader(f):
                    try:
                        # Yeni kolonları hesapla
                        symbol = r['symbol']  # CSV'den gelen orijinal symbol (PREF IBKR formatı)
                        fill_price = float(r['fill_price'])
                        bench_val_from_csv = float(r.get('Bench Val', 0) or 0.0)  # CSV'den gelen benchmark değeri
                        
                        # Eğer CSV'den gelen Bench Val 0 ise, sağ taraftaki ETF kolonlarından hesapla
                        if bench_val_from_csv == 0:
                            print(f"[JDATA] 🔍 {symbol} için CSV'de Bench Val 0, ETF kolonlarından hesaplanıyor...")
                            benchmark_key = r.get('Bench', 'DEFAULT')
                            # CSV'deki ETF fiyatlarını al
                            tlt_price = float(r.get('TLT', 0) or 0.0)
                            ief_price = float(r.get('IEF', 0) or 0.0)
                            iei_price = float(r.get('IEI', 0) or 0.0)
                            pff_price = float(r.get('PFF', 0) or 0.0)
                            
                            # Main window'daki benchmark formüllerini kullan
                            if hasattr(parent, 'benchmark_formulas') and benchmark_key in parent.benchmark_formulas:
                                formula = parent.benchmark_formulas[benchmark_key]
                                print(f"[JDATA] 🔍 {symbol} için {benchmark_key} formülü kullanılıyor: {formula}")
                                
                                bench_fill = 0.0
                                for etf, coefficient in formula.items():
                                    if etf == 'PFF' and pff_price > 0:
                                        contribution = pff_price * coefficient
                                        bench_fill += contribution
                                        print(f"[JDATA] 🔍 PFF: ${pff_price:.2f} * {coefficient} = ${contribution:.4f}")
                                    elif etf == 'TLT' and tlt_price > 0:
                                        contribution = tlt_price * coefficient
                                        bench_fill += contribution
                                        print(f"[JDATA] 🔍 TLT: ${tlt_price:.2f} * {coefficient} = ${contribution:.4f}")
                                    elif etf == 'IEF' and ief_price > 0:
                                        contribution = ief_price * coefficient
                                        bench_fill += contribution
                                        print(f"[JDATA] 🔍 IEF: ${ief_price:.2f} * {coefficient} = ${contribution:.4f}")
                                    elif etf == 'IEI' and iei_price > 0:
                                        contribution = iei_price * coefficient
                                        bench_fill += contribution
                                        print(f"[JDATA] 🔍 IEI: ${iei_price:.2f} * {coefficient} = ${contribution:.4f}")
                                
                                print(f"[JDATA] ✅ {symbol} {benchmark_key} benchmark (main window formülü): ${bench_fill:.4f}")
                            else:
                                # Fallback: Eski formülleri kullan
                                print(f"[JDATA] ⚠️ {symbol} için {benchmark_key} formülü bulunamadı, eski formül kullanılıyor")
                            if benchmark_key == 'DEFAULT':
                                # DEFAULT formül: PFF * 1.04 + TLT * (-0.08)
                                bench_fill = (pff_price * 1.04) + (tlt_price * (-0.08))
                                print(f"[JDATA] ✅ {symbol} DEFAULT benchmark: PFF(${pff_price:.2f} * 1.04) + TLT(${tlt_price:.2f} * -0.08) = ${bench_fill:.4f}")
                            else:
                                # Diğer benchmark'ler için formülü uygula
                                bench_fill = 0.0
                                if benchmark_key == 'C400':
                                    bench_fill = (pff_price * 0.36) + (tlt_price * 0.36) + (ief_price * 0.08)
                                elif benchmark_key == 'C425':
                                    bench_fill = (pff_price * 0.368) + (tlt_price * 0.34) + (ief_price * 0.092)
                                elif benchmark_key == 'C450':
                                    bench_fill = (pff_price * 0.376) + (tlt_price * 0.32) + (ief_price * 0.104)
                                elif benchmark_key == 'C475':
                                    bench_fill = (pff_price * 0.384) + (tlt_price * 0.30) + (ief_price * 0.116)
                                elif benchmark_key == 'C500':
                                    bench_fill = (pff_price * 0.392) + (tlt_price * 0.28) + (ief_price * 0.128)
                                elif benchmark_key == 'C525':
                                    bench_fill = (pff_price * 0.40) + (tlt_price * 0.24) + (ief_price * 0.14) + (iei_price * 0.02)
                                elif benchmark_key == 'C550':
                                    bench_fill = (pff_price * 0.408) + (tlt_price * 0.20) + (ief_price * 0.152) + (iei_price * 0.04)
                                elif benchmark_key == 'C575':
                                    bench_fill = (pff_price * 0.416) + (tlt_price * 0.16) + (ief_price * 0.164) + (iei_price * 0.06)
                                elif benchmark_key == 'C600':
                                    bench_fill = (pff_price * 0.432) + (tlt_price * 0.12) + (ief_price * 0.168) + (iei_price * 0.08)
                                elif benchmark_key == 'C625':
                                    bench_fill = (pff_price * 0.448) + (tlt_price * 0.08) + (ief_price * 0.172) + (iei_price * 0.10)
                                elif benchmark_key == 'C650':
                                    bench_fill = (pff_price * 0.464) + (tlt_price * 0.04) + (ief_price * 0.156) + (iei_price * 0.14)
                                elif benchmark_key == 'C675':
                                    bench_fill = (pff_price * 0.480) + (ief_price * 0.140) + (iei_price * 0.18)
                                elif benchmark_key == 'C700':
                                    bench_fill = (pff_price * 0.512) + (ief_price * 0.120) + (iei_price * 0.168)
                                elif benchmark_key == 'C725':
                                    bench_fill = (pff_price * 0.544) + (ief_price * 0.100) + (iei_price * 0.156)
                                elif benchmark_key == 'C750':
                                    bench_fill = (pff_price * 0.576) + (ief_price * 0.224)
                                elif benchmark_key == 'C775':
                                    bench_fill = (pff_price * 0.608) + (ief_price * 0.192)
                                elif benchmark_key == 'C800':
                                    bench_fill = (pff_price * 0.640) + (ief_price * 0.160)
                                
                                print(f"[JDATA] ✅ {symbol} {benchmark_key} benchmark: ${bench_fill:.4f}")
                        else:
                            # CSV'den gelen değer kullan
                            bench_fill = bench_val_from_csv
                            print(f"[JDATA] ✅ {symbol} CSV'den Bench Val: ${bench_fill:.4f}")
                        
                        # Current prices - PREF IBKR formatını kullan (Hammer Pro'ya convert ederek)
                        stock_last = get_last_price_for_symbol(symbol, parent)
                        
                        # Benchmark last price hesapla - main window'daki formülleri kullan
                        benchmark_key = r.get('Bench', 'DEFAULT')
                        bench_last = get_current_benchmark_value(benchmark_key, parent)
                        
                        # Değişim yüzdeleri
                        bench_chg_pct = 0.0
                        stock_chg_pct = 0.0
                        outperf_chg_pct = 0.0
                        
                        if bench_fill > 0:
                            bench_chg_pct = ((bench_last - bench_fill) / bench_fill) * 100
                        
                        if fill_price > 0:
                            stock_chg_pct = ((stock_last - fill_price) / fill_price) * 100
                        
                        outperf_chg_pct = stock_chg_pct - bench_chg_pct
                        
                        # Detail tree'ye ekle
                        detail_tree.insert('', 'end', values=[
                            symbol,
                            r.get('fill_time', ''),
                            r.get('fill_qty', ''),
                            f"${fill_price:.2f}",
                            f"${bench_fill:.4f}",
                            f"${bench_last:.4f}",
                            f"${stock_last:.2f}",
                            f"{bench_chg_pct:.2f}%",
                            f"{stock_chg_pct:.2f}%",
                            f"{outperf_chg_pct:.2f}%"
                        ])
                    except Exception as e:
                        print(f"[JDATA] ⚠️ Fill detayı işlenirken hata: {e}")
                        continue
        
        # Final jdata tab'ını da yenile
        print("[JDATA] 🔄 Final jdata sekmesi yenileniyor...")
        calculate_final_jdata()
        
        print("[JDATA] ✅ Tüm sekmeler yenilendi")
    
    ttk.Button(win, text='Yenile', command=do_refresh).pack(pady=6)


def test_take_profit_integration():
    """Take Profit pencerelerinde Final jdata entegrasyonunu test et"""
    print("\n🎯 Take Profit Entegrasyon Testi:")
    print("=" * 50)
    
    # Örnek symbol'ler için test
    test_symbols = ['RWTN', 'F PRB', 'CIM PRD']
    
    for symbol in test_symbols:
        print(f"\n📊 {symbol} için Final jdata:")
        data = get_final_jdata_for_symbol(symbol)
        if data:
            print(f"  Outperf Chg%: {data.get('outperf_chg_pct', 'N/A')}%")
            print(f"  Timebased Bench Chg: ${data.get('timebased_bench_chg', 'N/A')}")
            print(f"  Stock Chg%: {data.get('stock_chg_pct', 'N/A')}%")
            print(f"  Bench Chg%: {data.get('bench_chg_pct', 'N/A')}%")
        else:
            print(f"  ❌ Veri bulunamadı")
    
    print("\n💡 Take Profit pencerelerinde kullanım:")
    print("  1. get_final_jdata_for_symbol('RWTN') -> Dict döner")
    print("  2. get_symbol_performance_summary('RWTN') -> String döner")
    print("  3. Bu verileri Take Profit UI'ında göster")

def calculate_fill_type(symbol, side, quantity, current_position=0):
    """
    Fill Type hesapla: pozisyon değişimini belirle
    
    Args:
        symbol: Hisse senedi sembolü
        side: 'BUY' veya 'SELL'
        quantity: İşlem miktarı
        current_position: Mevcut pozisyon (pozitif=long, negatif=short)
    
    Returns:
        fill_type: "Long Increase", "Long Reduce", "Short Increase", "Short Reduce", "New Long", "New Short", "Close Position"
    """
    try:
        # Quantity'yi float'a çevir
        qty = float(quantity)
        current_pos = float(current_position)
        
        print(f"[FILL TYPE] 🔍 {symbol}: {side} {qty} (Mevcut: {current_pos})")
        
        if side.upper() == 'BUY':
            # BUY işlemi
            if current_pos >= 0:
                # Mevcut pozisyon long veya 0
                new_position = current_pos + qty
                if current_pos == 0:
                    return f"New Long ({qty:.0f})"
                else:
                    return f"Long Increase ({qty:.0f})"
            else:
                # Mevcut pozisyon short (negatif)
                new_position = current_pos + qty
                if new_position >= 0:
                    if new_position == 0:
                        return f"Close Position ({qty:.0f})"
                    else:
                        return f"Short Reduce ({qty:.0f})"
                else:
                    return f"Short Reduce ({qty:.0f})"
        
        elif side.upper() == 'SELL':
            # SELL işlemi
            if current_pos <= 0:
                # Mevcut pozisyon short veya 0
                new_position = current_pos - qty
                if current_pos == 0:
                    return f"New Short ({qty:.0f})"
                else:
                    return f"Short Increase ({qty:.0f})"
            else:
                # Mevcut pozisyon long (pozitif)
                new_position = current_pos - qty
                if new_position <= 0:
                    if new_position == 0:
                        return f"Close Position ({qty:.0f})"
                    else:
                        return f"Long Reduce ({qty:.0f})"
                else:
                    return f"Long Reduce ({qty:.0f})"
        
        return "Unknown"
        
    except Exception as e:
        print(f"[FILL TYPE] ❌ {symbol} fill type hesaplama hatası: {e}")
        return "Error"


def get_current_position_for_symbol(symbol, main_window=None):
    """Symbol için mevcut pozisyonu al (Hammer Pro'dan) - Short pozisyonlar negatif"""
    try:
        if main_window and hasattr(main_window, 'hammer') and main_window.hammer:
            # Symbol'ü Hammer Pro formatına çevir
            hammer_symbol = get_hammer_symbol_from_pref_ibkr(symbol)
            
            # Hammer Pro'dan pozisyon bilgisi al
            positions = main_window.hammer.get_positions()
            if positions:
                for pos in positions:
                    if pos.get('symbol') == hammer_symbol:
                        qty = float(pos.get('qty', 0))
                        # Short pozisyonlar negatif gösterilsin
                        print(f"[FILL TYPE] 📊 {symbol} -> {hammer_symbol}: {qty} (Hammer Pro)")
                        return qty
            
            # Bulamazsa orijinal symbol ile dene
            for pos in positions:
                if pos.get('symbol') == symbol:
                    qty = float(pos.get('qty', 0))
                    print(f"[FILL TYPE] 📊 {symbol}: {qty} (Hammer Pro - orijinal)")
                    return qty
        
        print(f"[FILL TYPE] ⚠️ {symbol} pozisyon bulunamadı, 0 döndürülüyor")
        return 0.0
        
    except Exception as e:
        print(f"[FILL TYPE] ❌ {symbol} pozisyon alma hatası: {e}")
        return 0.0


# Test fonksiyonunu çağır
if __name__ == "__main__":
    test_take_profit_integration()








