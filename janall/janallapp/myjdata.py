"""
jdata Analiz Modülü
- Fill verilerini jdata.csv'ye kaydetme
- ETF combined değerlerini hesaplama
- Performans analizi ve outperformans takibi
"""

from __future__ import annotations

import os
import csv
from datetime import datetime
from typing import Callable, Dict, List, Any

import tkinter as tk
from tkinter import ttk

JDATA_FILE = "jdata.csv"

# Benchmark coefficient map (absolute level calculation).
# Keys align with MainWindow.benchmark_formulas keys.
BENCHMARK_WEIGHTS: Dict[str, Dict[str, float]] = {
    'DEFAULT': {'PFF': 1.04, 'TLT': -0.08, 'IEF': 0.0, 'IEI': 0.0},
    'C400': {'PFF': 0.36, 'TLT': 0.36, 'IEF': 0.08, 'IEI': 0.0},
    'C425': {'PFF': 0.368, 'TLT': 0.34, 'IEF': 0.092, 'IEI': 0.0},
    'C450': {'PFF': 0.376, 'TLT': 0.32, 'IEF': 0.104, 'IEI': 0.0},
    'C475': {'PFF': 0.384, 'TLT': 0.30, 'IEF': 0.116, 'IEI': 0.0},
    'C500': {'PFF': 0.392, 'TLT': 0.28, 'IEF': 0.128, 'IEI': 0.0},
    'C525': {'PFF': 0.40, 'TLT': 0.24, 'IEF': 0.14, 'IEI': 0.02},
    'C550': {'PFF': 0.408, 'TLT': 0.20, 'IEF': 0.152, 'IEI': 0.04},
    'C575': {'PFF': 0.416, 'TLT': 0.16, 'IEF': 0.164, 'IEI': 0.06},
    'C600': {'PFF': 0.432, 'TLT': 0.12, 'IEF': 0.168, 'IEI': 0.08},
    'C625': {'PFF': 0.448, 'TLT': 0.08, 'IEF': 0.172, 'IEI': 0.10},
    'C650': {'PFF': 0.464, 'TLT': 0.04, 'IEF': 0.156, 'IEI': 0.14},
    'C675': {'PFF': 0.480, 'TLT': 0.00, 'IEF': 0.140, 'IEI': 0.18},
    'C700': {'PFF': 0.512, 'TLT': 0.00, 'IEF': 0.120, 'IEI': 0.168},
    'C725': {'PFF': 0.544, 'TLT': 0.00, 'IEF': 0.100, 'IEI': 0.156},
    'C750': {'PFF': 0.576, 'TLT': 0.00, 'IEF': 0.000, 'IEI': 0.224},
    'C775': {'PFF': 0.608, 'TLT': 0.00, 'IEF': 0.000, 'IEI': 0.192},
    'C800': {'PFF': 0.640, 'TLT': 0.00, 'IEF': 0.000, 'IEI': 0.160},
}

PriceProvider = Callable[[str], float]


def compute_combined_level(benchmark_key: str, get_last: PriceProvider) -> float:
    """ETF combined level hesapla"""
    weights = BENCHMARK_WEIGHTS.get(benchmark_key.upper(), BENCHMARK_WEIGHTS['DEFAULT'])
    total = 0.0
    for etf, w in weights.items():
        if w == 0:
            continue
        px = float(get_last(etf) or 0.0)
        total += w * px
    return round(total, 4)


def get_benchmark_type_for_symbol(symbol: str, main_window=None) -> str:
    """Symbol'e göre benchmark tipini belirle"""
    if main_window and hasattr(main_window, 'get_benchmark_type_for_ticker'):
        return main_window.get_benchmark_type_for_ticker(symbol)
    
    # Fallback: PREF IBKR hisseleri için default
    if " PR" in symbol:
        return 'C400'  # Default
    return 'DEFAULT'


def append_fill(symbol: str,
                side: str,
                qty: float,
                price: float,
                fill_time: str,
                get_last: PriceProvider,
                main_window=None,
                benchmark_key: str = None,
                combined_override: float = None) -> None:
    """Fill verilerini jdata.csv'ye kaydet"""
    os.makedirs(os.path.dirname(JDATA_FILE) or '.', exist_ok=True)
    
    # Benchmark key'i belirle
    if benchmark_key is None:
        benchmark_key = get_benchmark_type_for_symbol(symbol, main_window)
    
    # ETF combined değerini hesapla
    combined = float(combined_override) if combined_override is not None else compute_combined_level(benchmark_key, get_last)
    
    # Individual ETF fiyatları (audit için)
    pff = float(get_last('PFF') or 0.0)
    tlt = float(get_last('TLT') or 0.0)
    ief = float(get_last('IEF') or 0.0)
    iei = float(get_last('IEI') or 0.0)
    
    is_buy = 1 if side.lower() in ('buy', 'long') else -1
    
    row = {
        'time': fill_time,
        'symbol': symbol,
        'side': 'BUY' if is_buy == 1 else 'SELL',
        'qty': float(qty) * is_buy,  # signed
        'price': float(price),
        'benchmark_key': benchmark_key.upper(),
        'PFF': pff,
        'TLT': tlt,
        'IEF': ief,
        'IEI': iei,
        'combined_at_fill': combined,
    }
    
    write_header = not os.path.exists(JDATA_FILE)
    with open(JDATA_FILE, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)
    
    print(f"[JDATA] ✅ Fill kaydedildi: {symbol} {qty} lot @ ${price:.2f} - ETF Combined: {combined:.4f}")


def load_summary(get_last: PriceProvider, main_window=None) -> List[Dict[str, Any]]:
    """jdata.csv'den pozisyon özetini yükle"""
    if not os.path.exists(JDATA_FILE):
        return []
    
    rows: List[Dict[str, Any]] = []
    with open(JDATA_FILE, 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    'symbol': r['symbol'],
                    'qty': float(r['qty']),
                    'price': float(r['price']),
                    'combined_at_fill': float(r.get('combined_at_fill', 0) or 0.0),
                    'benchmark_key': r.get('benchmark_key', 'DEFAULT'),
                    'time': r.get('time', '')
                })
            except Exception:
                continue
    
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
        s['bench_sum'] += r['combined_at_fill'] * r['qty']
        s['benchmark_key'] = r['benchmark_key'] or s['benchmark_key']
        s['fills'].append({
            'time': r['time'],
            'qty': r['qty'],
            'price': r['price'],
            'combined_at_fill': r['combined_at_fill']
        })
    
    # Finalize
    out: List[Dict[str, Any]] = []
    for sym, s in summary.items():
        if s['qty'] == 0:
            continue
        
        avg_cost = s['cost_sum'] / s['qty']
        etf_combined_avg = s['bench_sum'] / s['qty']
        
        # Current values
        current_px = float(get_last(sym) or 0.0)
        current_combined = compute_combined_level(s['benchmark_key'], get_last)
        
        # Performance calculation
        price_change = current_px - avg_cost
        etf_change = current_combined - etf_combined_avg
        outperformance = price_change - etf_change
        
        out.append({
            'symbol': sym,
            'qty': s['qty'],
            'avg_cost': round(avg_cost, 4),
            'current_price': round(current_px, 4),
            'etf_combined_avg': round(etf_combined_avg, 4),
            'etf_combined_now': round(current_combined, 4),
            'etf_diff': round(etf_change, 4),
            'pnl_vs_cost': round(price_change, 4),
            'outperformance': round(outperformance, 4),
            'benchmark_key': s['benchmark_key'],
            'fills': s['fills']
        })
    
    return out


def show_jdata_window(parent, get_last: PriceProvider):
    """jdata.csv analiz penceresi"""
    data = load_summary(get_last, parent)
    
    win = tk.Toplevel(parent)
    win.title("jdata Analiz - Fill Geçmişi ve Performans")
    win.geometry("1200x600")
    
    # Notebook (tabbed interface)
    notebook = ttk.Notebook(win)
    notebook.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Tab 1: Özet Tablosu
    summary_frame = ttk.Frame(notebook)
    notebook.add(summary_frame, text="Özet")
    
    cols = ['symbol', 'qty', 'avg_cost', 'current_price', 'etf_combined_avg', 'etf_combined_now', 'etf_diff', 'pnl_vs_cost', 'outperformance']
    headers = ['Symbol', 'Qty', 'Avg Cost', 'Current', 'ETF Avg', 'ETF Now', 'ETF Δ', 'PnL', 'Outperf']
    
    tree = ttk.Treeview(summary_frame, columns=cols, show='headings', height=15)
    for c, h in zip(cols, headers):
        tree.heading(c, text=h)
        tree.column(c, width=120, anchor='center')
    
    tree.pack(fill='both', expand=True, padx=5, pady=5)
    
    for r in data:
        vals = [r[c] for c in cols]
        tree.insert('', 'end', values=vals)
    
    # Tab 2: Fill Detayları
    detail_frame = ttk.Frame(notebook)
    notebook.add(detail_frame, text="Fill Detayları")
    
    detail_cols = ['symbol', 'time', 'qty', 'price', 'combined_at_fill', 'benchmark_key']
    detail_headers = ['Symbol', 'Time', 'Qty', 'Price', 'ETF Combined', 'Benchmark']
    
    detail_tree = ttk.Treeview(detail_frame, columns=detail_cols, show='headings', height=20)
    for c, h in zip(detail_cols, detail_headers):
        detail_tree.heading(c, text=h)
        detail_tree.column(c, width=150, anchor='center')
    
    detail_tree.pack(fill='both', expand=True, padx=5, pady=5)
    
    # Tüm fill'leri yükle
    if os.path.exists(JDATA_FILE):
        with open(JDATA_FILE, 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                try:
                    vals = [
                        r['symbol'],
                        r['time'],
                        r['qty'],
                        r['price'],
                        r.get('combined_at_fill', '0'),
                        r.get('benchmark_key', 'DEFAULT')
                    ]
                    detail_tree.insert('', 'end', values=vals)
                except Exception:
                    continue
    
    # Refresh button
    def do_refresh():
        # Summary tab'ını yenile
        for item in tree.get_children():
            tree.delete(item)
        for r in load_summary(get_last, parent):
            tree.insert('', 'end', values=[r[c] for c in cols])
        
        # Detail tab'ını yenile
        for item in detail_tree.get_children():
            detail_tree.delete(item)
        if os.path.exists(JDATA_FILE):
            with open(JDATA_FILE, 'r', encoding='utf-8') as f:
                for r in csv.DictReader(f):
                    try:
                        vals = [
                            r['symbol'],
                            r['time'],
                            r['qty'],
                            r['price'],
                            r.get('combined_at_fill', '0'),
                            r.get('benchmark_key', 'DEFAULT')
                        ]
                        detail_tree.insert('', 'end', values=vals)
                    except Exception:
                        continue
    
    ttk.Button(win, text='Yenile', command=do_refresh).pack(pady=6)
