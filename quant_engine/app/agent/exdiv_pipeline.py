"""
Ex-Dividend Full Pipeline
==========================

ADIM 1: Tüm hisselerin ex-div tarihlerini algoritmik olarak düzelt
       (peer divergence + 3 aylık periyodisite)
ADIM 2: Düzeltilmiş tarihlerle daily excess return pattern hesapla
ADIM 3: Gemini Flash'a gönder — optimal trading stratejisi bulsun
       (Sharpe ratio, en iyi alım-satım günleri)

Kullanım:
  python -m app.agent.exdiv_pipeline              # Tüm pipeline
  python -m app.agent.exdiv_pipeline --detect-only # Sadece tarih tespiti
  python -m app.agent.exdiv_pipeline --single "F PRB"  # Tek hisse
"""

import os
import sys
import json
import glob
import asyncio
import random
import time
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from math import erfc, sqrt
from dataclasses import dataclass

warnings.filterwarnings('ignore')

# =====================================================================
# CONFIG
# =====================================================================

STOCKTRACKER_ROOT = r"C:\StockTracker"
UTALLDATA_DIR = os.path.join(STOCKTRACKER_ROOT, "UTALLDATA")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                          "..", "..", "output", "exdiv_v5")

PATTERN_WINDOW = 20  # ±20 iş günü (ex-div etrafında)
MIN_CYCLES = 3
N_PEERS = 5          # Cross-check için peer sayısı


# =====================================================================
# ADIM 0: VERİ YÜKLEME
# =====================================================================

_ALL_DFS: Dict[str, pd.DataFrame] = {}
_DIV_INFO: Dict[str, Dict] = {}


def load_stock_df(ticker: str) -> Optional[pd.DataFrame]:
    if ticker in _ALL_DFS:
        return _ALL_DFS[ticker]
    safe = ticker.replace(" ", "_")
    fpath = os.path.join(UTALLDATA_DIR, f"{safe}22exdata.csv")
    if not os.path.exists(fpath):
        return None
    try:
        df = pd.read_csv(fpath)
        df['Date'] = pd.to_datetime(df['Date'])
        _ALL_DFS[ticker] = df
        return df
    except Exception:
        return None


def get_all_tickers() -> List[str]:
    files = glob.glob(os.path.join(UTALLDATA_DIR, "*22exdata.csv"))
    tickers = []
    for fp in files:
        bn = os.path.basename(fp)
        tk = bn.replace("22exdata.csv", "").replace("_", " ").strip()
        if not tk.startswith("PFF"):
            tickers.append(tk)
    return sorted(tickers)


def load_div_info() -> Dict[str, Dict]:
    global _DIV_INFO
    if _DIV_INFO:
        return _DIV_INFO

    # janalldata.csv
    jpath = os.path.join(STOCKTRACKER_ROOT, "janalldata.csv")
    if os.path.exists(jpath):
        jdf = pd.read_csv(jpath, encoding='latin-1')
        for _, row in jdf.iterrows():
            tk = str(row.get('PREF IBKR', '')).strip()
            if not tk or pd.isna(row.get('DIV AMOUNT')) or row['DIV AMOUNT'] <= 0:
                continue
            ed = str(row.get('EX-DIV DATE', '')) if pd.notna(row.get('EX-DIV DATE')) else ''
            _DIV_INFO[tk] = {
                'div_amount': float(row['DIV AMOUNT']),
                'anchor_date': ed,
            }

    # Ek CSV'ler
    ek_files = [
        'ekheldbesmaturlu.csv', 'ekheldcilizyeniyedi.csv', 'ekheldcommonsuz.csv',
        'ekhelddeznff.csv', 'ekheldff.csv', 'ekheldflr.csv', 'ekheldgarabetaltiyedi.csv',
        'ekheldkuponlu.csv', 'ekheldkuponlukreciliz.csv', 'ekheldkuponlukreorta.csv',
        'ekheldnff.csv', 'ekheldotelremorta.csv', 'ekheldsolidbig.csv',
        'ekheldtitrekhc.csv', 'ekhighmatur.csv', 'eknotbesmaturlu.csv',
        'eknotcefilliquid.csv', 'eknottitrekhc.csv', 'ekrumoreddanger.csv',
        'eksalakilliquid.csv', 'ekshitremhc.csv',
    ]
    for f in ek_files:
        fp = os.path.join(STOCKTRACKER_ROOT, f)
        if os.path.exists(fp):
            try:
                edf = pd.read_csv(fp, encoding='latin-1')
                if 'PREF IBKR' in edf.columns and 'DIV AMOUNT' in edf.columns:
                    for _, row in edf.iterrows():
                        t = str(row['PREF IBKR']).strip()
                        d = row.get('DIV AMOUNT', 0)
                        if pd.notna(t) and t and pd.notna(d) and d > 0 and t not in _DIV_INFO:
                            _DIV_INFO[t] = {'div_amount': float(d), 'anchor_date': ''}
            except Exception:
                pass

    return _DIV_INFO


# =====================================================================
# ADIM 1: EX-DIV TARİH TESPİTİ (Peer Divergence)
# =====================================================================

def detect_exdiv_dates(ticker: str, div_amount: float, anchor_date: str,
                       all_tickers: List[str] = None) -> Dict:
    """
    Bir hissenin tüm ex-div tarihlerini tespit et.
    
    Yöntem: Anchor'dan 3'er aylık periyotlarla ilerle/gerile.
    Her pencerede (ayın 10-20'si): Open-PrevClose gap'i ve 
    5 peer'ın aynı gündeki gap'ini karşılaştır.
    En negatif divergence = ex-div.
    """
    df = load_stock_df(ticker)
    if df is None or len(df) < 50:
        return {'ticker': ticker, 'error': 'no_data', 'dates': []}

    # Anchor'ı parse et
    anchor_ts = None
    if anchor_date and anchor_date != 'nan':
        for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y']:
            try:
                anchor_ts = pd.to_datetime(anchor_date, format=fmt)
                break
            except Exception:
                pass
        if anchor_ts is None:
            try:
                anchor_ts = pd.to_datetime(anchor_date)
            except Exception:
                pass

    # Anchor yoksa: verideki en büyük gap-down'u bul
    if anchor_ts is None:
        gaps = []
        for idx in range(1, len(df)):
            pc = df.loc[idx - 1, 'Close']
            if pc > 0:
                gap = (df.loc[idx, 'Open'] - pc) / pc * 100
                gaps.append((idx, gap, df.loc[idx, 'Date']))
        gaps.sort(key=lambda x: x[1])
        if gaps and gaps[0][1] < -0.3:
            anchor_ts = gaps[0][2]
        else:
            return {'ticker': ticker, 'error': 'no_anchor', 'dates': []}

    # Random peers seç
    if all_tickers is None:
        all_tickers = get_all_tickers()
    peer_tickers = random.sample([t for t in all_tickers if t != ticker],
                                  min(N_PEERS, len(all_tickers) - 1))
    peer_dfs = {}
    for p in peer_tickers:
        pdf = load_stock_df(p)
        if pdf is not None and len(pdf) > 50:
            peer_dfs[p] = pdf

    # 3'er aylık pencereler project et
    data_start = df['Date'].iloc[0]
    data_end = df['Date'].iloc[-1]

    results = []
    for q in range(-20, 20):
        expected = anchor_ts + pd.DateOffset(months=3 * q)
        if expected < data_start - pd.Timedelta(days=30):
            continue
        if expected > data_end + pd.Timedelta(days=10):
            continue

        # Ayın 10-20'si arasında bak
        month_start = expected.replace(day=10) if expected.day <= 20 else expected.replace(day=10)
        try:
            d10 = expected.replace(day=10)
            d20 = expected.replace(day=20)
        except Exception:
            continue

        window = df[(df['Date'] >= d10) & (df['Date'] <= d20)]
        if len(window) == 0:
            # Belki 8-22'ye genişlet
            try:
                d8 = expected.replace(day=8)
                d22 = expected.replace(day=22)
            except Exception:
                continue
            window = df[(df['Date'] >= d8) & (df['Date'] <= d22)]
            if len(window) == 0:
                continue

        # Her gün için divergence hesapla
        candidates = []
        for idx in window.index:
            if idx <= 0 or (idx - 1) not in df.index:
                continue
            r = df.loc[idx]
            pc = df.loc[idx - 1, 'Close']
            if pc <= 0 or np.isnan(pc) or np.isnan(r['Open']):
                continue

            stock_gap = (r['Open'] - pc) / pc * 100

            # Peer gaps
            peer_gaps = []
            for pn, pdf in peer_dfs.items():
                prow = pdf[pdf['Date'] == r['Date']]
                if len(prow) > 0:
                    pidx = prow.index[0]
                    if pidx > 0 and (pidx - 1) in pdf.index:
                        ppc = pdf.loc[pidx - 1, 'Close']
                        if ppc > 0 and not np.isnan(ppc):
                            pgap = (prow.iloc[0]['Open'] - ppc) / ppc * 100
                            peer_gaps.append(pgap)

            peer_med = float(np.median(peer_gaps)) if peer_gaps else 0
            divergence = stock_gap - peer_med

            candidates.append({
                'date': r['Date'].strftime('%Y-%m-%d'),
                'date_ts': r['Date'],
                'stock_gap': round(stock_gap, 3),
                'peer_med': round(peer_med, 3),
                'divergence': round(divergence, 3),
                'gap_dollar': round(r['Open'] - pc, 3),
                'idx': idx,
            })

        if not candidates:
            continue

        # En negatif divergence = ex-div
        candidates.sort(key=lambda x: x['divergence'])
        best = candidates[0]

        if best['divergence'] < -0.2:
            confidence = 'HIGH' if best['divergence'] < -0.8 else \
                         'MEDIUM' if best['divergence'] < -0.4 else 'LOW'
        else:
            confidence = 'NONE'

        results.append({
            'expected_month': expected.strftime('%Y-%m'),
            'detected_date': best['date'],
            'stock_gap_pct': best['stock_gap'],
            'peer_median_pct': best['peer_med'],
            'divergence_pct': best['divergence'],
            'gap_dollar': best['gap_dollar'],
            'confidence': confidence,
            'idx': best['idx'],
        })

    # Deduplicate (aynı ay birden fazla gelmiş olabilir)
    seen_months = set()
    unique = []
    for r in results:
        m = r['expected_month']
        if m not in seen_months:
            seen_months.add(m)
            unique.append(r)
    results = unique

    # Sonuç
    confirmed = [r for r in results if r['confidence'] in ('HIGH', 'MEDIUM')]
    all_dates = [r['detected_date'] for r in results if r['confidence'] != 'NONE']

    # Cycle istatistikleri
    if len(all_dates) >= 2:
        dts = sorted(pd.to_datetime(all_dates))
        gaps = [(dts[i] - dts[i-1]).days for i in range(1, len(dts))]
        avg_cycle = np.mean(gaps)
        std_cycle = np.std(gaps)
        quality = 'good' if std_cycle < 10 and len(all_dates) >= 6 else \
                  'fair' if std_cycle < 15 and len(all_dates) >= 4 else 'poor'
    else:
        avg_cycle = 91
        std_cycle = 99
        quality = 'poor'

    return {
        'ticker': ticker,
        'div_amount': div_amount,
        'n_detected': len(results),
        'n_confirmed': len(confirmed),
        'quality': quality,
        'avg_cycle_days': round(avg_cycle, 1),
        'cycle_std': round(std_cycle, 1),
        'exdiv_dates': all_dates,
        'all_windows': results,
        'peers_used': list(peer_dfs.keys()),
    }


# =====================================================================
# ADIM 2: PATTERN HESAPLAMA (düzeltilmiş tarihlerle)
# =====================================================================

def compute_excess_patterns(ticker: str, div_amount: float,
                            exdiv_dates: List[str]) -> Dict:
    """Düzeltilmiş ex-div tarihleriyle daily excess return pattern hesapla."""
    df = load_stock_df(ticker)
    if df is None:
        return {}

    # Ex-div tarihlerini index'e çevir
    exdiv_indices = []
    for ds in exdiv_dates:
        dt = pd.to_datetime(ds)
        matches = df[df['Date'] == dt]
        if len(matches) > 0:
            exdiv_indices.append(matches.index[0])
        else:
            # En yakın tarihi bul
            diffs = abs(df['Date'] - dt)
            closest = diffs.idxmin()
            if abs((df.loc[closest, 'Date'] - dt).days) <= 3:
                exdiv_indices.append(closest)

    if len(exdiv_indices) < MIN_CYCLES:
        return {}

    close = df['Close'].values
    date_strs = df['Date'].astype(str).str[:10].values

    # Market daily returns (basit median)
    # Her peer'ın daily return'ünü hesapla
    all_tickers = get_all_tickers()
    sample_peers = random.sample([t for t in all_tickers if t != ticker],
                                  min(20, len(all_tickers) - 1))
    market_rets = {}
    for p in sample_peers:
        pdf = load_stock_df(p)
        if pdf is not None:
            pc = pdf['Close'].values
            pds = pdf['Date'].astype(str).str[:10].values
            for i in range(1, len(pdf)):
                if pc[i-1] > 0 and not np.isnan(pc[i-1]) and not np.isnan(pc[i]):
                    ret = (pc[i] - pc[i-1]) / pc[i-1] * 100
                    d = pds[i]
                    if d not in market_rets:
                        market_rets[d] = []
                    market_rets[d].append(ret)

    mkt_med = {d: float(np.median(v)) for d, v in market_rets.items() if len(v) >= 5}

    # Daily pattern hesapla
    daily_data = {o: [] for o in range(-PATTERN_WINDOW, PATTERN_WINDOW + 1)}

    for ex_idx in exdiv_indices:
        for offset in range(-PATTERN_WINDOW, PATTERN_WINDOW + 1):
            t = ex_idx + offset
            p = t - 1
            if p < 0 or t >= len(close):
                continue
            if close[p] <= 0 or np.isnan(close[p]) or np.isnan(close[t]):
                continue

            stock_ret = (close[t] - close[p]) / close[p] * 100
            if offset == 0 and div_amount > 0:
                stock_ret = (close[t] + div_amount - close[p]) / close[p] * 100

            mkt_ret = mkt_med.get(date_strs[t], 0.0)
            excess_ret = stock_ret - mkt_ret
            daily_data[offset].append(excess_ret)

    # İstatistikler
    daily_stats = []
    cum = 0.0
    for offset in range(-PATTERN_WINDOW, PATTERN_WINDOW + 1):
        rets = daily_data[offset]
        n = len(rets)
        if n < MIN_CYCLES:
            daily_stats.append({'day': offset, 'avg': 0, 'cum': round(cum, 4),
                               'pos': 0.5, 'n': n, 'std': 0, 'tstat': 0, 'pval': 1})
            continue
        arr = np.array(rets)
        avg = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if n > 1 else 0
        pos = float((arr > 0).mean())
        tstat = avg / (std / np.sqrt(n)) if std > 0 else 0
        pval = erfc(abs(tstat) / sqrt(2)) if tstat != 0 else 1.0
        cum += avg
        daily_stats.append({
            'day': offset, 'avg': round(avg, 4), 'cum': round(cum, 4),
            'pos': round(pos, 3), 'n': n, 'std': round(std, 4),
            'tstat': round(tstat, 2), 'pval': round(pval, 4),
        })

    # Trade signal tespiti: tüm olası entry-exit kombinasyonları
    def calc_trade(entry_off, exit_off, is_short=False):
        rets = []
        for ei in exdiv_indices:
            e_i = ei + entry_off
            x_i = ei + exit_off
            if e_i < 0 or x_i < 0 or e_i >= len(close) or x_i >= len(close):
                continue
            if close[e_i] <= 0:
                continue
            divs = sum(div_amount for oi in exdiv_indices
                       if e_i < oi <= x_i) if div_amount > 0 else 0
            if is_short:
                sr = (close[e_i] - close[x_i] - divs) / close[e_i] * 100
            else:
                sr = (close[x_i] + divs - close[e_i]) / close[e_i] * 100
            mc = sum(mkt_med.get(date_strs[di], 0) for di in range(min(e_i, x_i)+1, max(e_i, x_i)+1)
                     if di < len(date_strs))
            rets.append(sr - mc)
        return rets

    # ─── Referans stratejiler (isimlendirme için) ───
    strategies = []
    strat_configs = [
        ('CAPTURE_PRE', -7, -1, False, 'Buy 7d before, sell 1d before exdiv'),
        ('CAPTURE_HOLD', -5, 0, False, 'Buy 5d before, hold through exdiv'),
        ('DIV_HOLD', -2, 2, False, 'Buy 2d before, sell 2d after'),
        ('RECOVERY', 0, 10, False, 'Buy on exdiv, sell 10d later'),
        ('RECOVERY_LATE', 3, 15, False, 'Buy 3d after, sell 15d later'),
        ('WASHOUT_SHORT', 0, 5, True, 'Short on exdiv, cover 5d later'),
        ('FULL_CYCLE', -10, 20, False, 'Buy 10d before, sell 20d after'),
        ('QUICK_FLIP', -3, 3, False, 'Buy 3d before, sell 3d after'),
    ]

    def _eval_strat(name, entry, exit_, is_short, desc):
        rets = calc_trade(entry, exit_, is_short)
        if len(rets) < MIN_CYCLES:
            return None
        arr = np.array(rets)
        avg = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.001
        wr = float((arr > 0).mean())
        n = len(arr)
        tstat = avg / (std / np.sqrt(n)) if std > 0 else 0
        pval = erfc(abs(tstat) / sqrt(2)) if tstat != 0 else 1.0
        sharpe = avg / std * np.sqrt(4) if std > 0 else 0
        return {
            'name': name, 'desc': desc,
            'entry_day': entry, 'exit_day': exit_,
            'is_short': is_short,
            'avg_ret': round(avg, 3), 'std': round(std, 3),
            'win_rate': round(wr, 3), 'sharpe': round(sharpe, 2),
            'tstat': round(tstat, 2), 'pval': round(pval, 4),
            'n_trades': n, 'significant': pval < 0.10,
        }

    for name, entry, exit_, is_short, desc in strat_configs:
        s = _eval_strat(name, entry, exit_, is_short, desc)
        if s:
            strategies.append(s)

    # ─── EXHAUSTIVE SEARCH: tüm entry/exit kombinasyonları ───
    # LONG ve SHORT için ayrı ayrı en iyi pencereyi bul
    # Entry: d-20 → d+15,  Exit: entry+3 → entry+10  (min 3, max 10 gün holding)
    SEARCH_MIN = -PATTERN_WINDOW  # -20
    SEARCH_MAX = PATTERN_WINDOW   # +20
    MIN_HOLD = 3   # minimum tutma süresi (gün)
    MAX_HOLD = 10  # maksimum tutma süresi (gün)

    best_long_sharpe = -999
    best_long = None
    best_short_sharpe = -999
    best_short = None

    for entry_off in range(SEARCH_MIN, SEARCH_MAX - MIN_HOLD + 1):
        for exit_off in range(entry_off + MIN_HOLD, min(entry_off + MAX_HOLD + 1, SEARCH_MAX + 1)):
            # LONG
            rets_l = calc_trade(entry_off, exit_off, False)
            if len(rets_l) >= MIN_CYCLES:
                arr = np.array(rets_l)
                avg = float(np.mean(arr))
                std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.001
                sharpe = avg / std * np.sqrt(4) if std > 0 else 0
                if sharpe > best_long_sharpe:
                    best_long_sharpe = sharpe
                    best_long = (entry_off, exit_off, arr, avg, std, sharpe)

            # SHORT
            rets_s = calc_trade(entry_off, exit_off, True)
            if len(rets_s) >= MIN_CYCLES:
                arr = np.array(rets_s)
                avg = float(np.mean(arr))
                std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.001
                sharpe = avg / std * np.sqrt(4) if std > 0 else 0
                if sharpe > best_short_sharpe:
                    best_short_sharpe = sharpe
                    best_short = (entry_off, exit_off, arr, avg, std, sharpe)

    # OPTIMAL_LONG ekle (exhaustive search sonucu)
    if best_long and best_long_sharpe > 0:
        e, x, arr, avg, std, sharpe = best_long
        wr = float((arr > 0).mean())
        n = len(arr)
        tstat = avg / (std / np.sqrt(n)) if std > 0 else 0
        pval = erfc(abs(tstat) / sqrt(2)) if tstat != 0 else 1.0
        # Daha önce aynı entry/exit ile eklenmemişse ekle
        exists = any(s['entry_day'] == e and s['exit_day'] == x and not s['is_short'] for s in strategies)
        if not exists:
            strategies.append({
                'name': 'OPTIMAL_LONG',
                'desc': f'Buy day{e:+d}, sell day{x:+d} (exhaustive)',
                'entry_day': e, 'exit_day': x, 'is_short': False,
                'avg_ret': round(avg, 3), 'std': round(std, 3),
                'win_rate': round(wr, 3), 'sharpe': round(sharpe, 2),
                'tstat': round(tstat, 2), 'pval': round(pval, 4),
                'n_trades': n, 'significant': pval < 0.10,
            })

    # OPTIMAL_SHORT ekle (exhaustive search sonucu)
    if best_short and best_short_sharpe > 0:
        e, x, arr, avg, std, sharpe = best_short
        wr = float((arr > 0).mean())
        n = len(arr)
        tstat = avg / (std / np.sqrt(n)) if std > 0 else 0
        pval = erfc(abs(tstat) / sqrt(2)) if tstat != 0 else 1.0
        exists = any(s['entry_day'] == e and s['exit_day'] == x and s['is_short'] for s in strategies)
        if not exists:
            strategies.append({
                'name': 'OPTIMAL_SHORT',
                'desc': f'Short day{e:+d}, cover day{x:+d} (exhaustive)',
                'entry_day': e, 'exit_day': x, 'is_short': True,
                'avg_ret': round(avg, 3), 'std': round(std, 3),
                'win_rate': round(wr, 3), 'sharpe': round(sharpe, 2),
                'tstat': round(tstat, 2), 'pval': round(pval, 4),
                'n_trades': n, 'significant': pval < 0.10,
            })

    # Pattern strength
    n_sig = sum(1 for d in daily_stats if d['pval'] < 0.10 and d['n'] >= MIN_CYCLES)
    n_test = sum(1 for d in daily_stats if d['n'] >= MIN_CYCLES)
    strength = round((n_sig / n_test * 100), 1) if n_test > 0 else 0

    return {
        'daily_stats': daily_stats,
        'strategies': strategies,
        'pattern_strength': strength,
        'n_exdiv_used': len(exdiv_indices),
    }


# =====================================================================
# ADIM 3: GEMINI FLASH ANALİZ
# =====================================================================

def build_flash_prompt(ticker: str, detection: Dict, patterns: Dict,
                       price_info: Dict) -> str:
    """Gemini Flash'a gönderilecek analiz promptu."""

    # Ex-div tarihleri
    dates_str = ", ".join(detection.get('exdiv_dates', [])[-8:])

    # En iyi stratejiler
    strats = patterns.get('strategies', [])
    strats_sorted = sorted(strats, key=lambda s: s.get('sharpe', 0), reverse=True)
    strat_lines = []
    for s in strats_sorted[:6]:
        sig = '***' if s['pval'] < 0.05 else '**' if s['pval'] < 0.10 else ''
        strat_lines.append(
            f"  {s['name']:16s} day{s['entry_day']:+3d}→{s['exit_day']:+3d} "
            f"ret={s['avg_ret']:+.2f}% win={s['win_rate']:.0%} "
            f"sharpe={s['sharpe']:+.2f} p={s['pval']:.3f} n={s['n_trades']} {sig}"
        )
    strat_str = "\n".join(strat_lines) if strat_lines else "  Yeterli veri yok"

    # Günlük pattern (önemli günler)
    daily = patterns.get('daily_stats', [])
    day_lines = []
    for d in daily:
        if abs(d['day']) <= 10 or d['day'] % 5 == 0:
            sig = '*' if d['pval'] < 0.10 else ''
            day_lines.append(
                f"  Day{d['day']:+3d}: avg={d['avg']:+.3f}% cum={d['cum']:+.3f}% "
                f"pos={d['pos']:.0%} n={d['n']} {sig}"
            )
    daily_str = "\n".join(day_lines)

    yield_pct = price_info.get('yield_pct', 0)

    prompt = f"""
{ticker} — EX-DIV DÖNGÜ ANALİZİ
Div=${detection['div_amount']:.4f} | Yield={yield_pct:.1f}% | Fiyat~${price_info.get('avg_price',0):.1f}
ExDiv sayısı: {detection['n_confirmed']} (kalite: {detection['quality']})
Ort. cycle: {detection['avg_cycle_days']:.0f} gün (std={detection['cycle_std']:.0f})
Son ex-divler: {dates_str}

GÜNLÜK EXCESS RETURN PATTERNİ (piyasa medyanına göre):
{daily_str}

EN İYİ STRATEJİLER (Sharpe'a göre sıralı):
{strat_str}

Pattern gücü: {patterns.get('pattern_strength', 0):.1f}%

LÜTFEN BU HİSSE İÇİN:
1. En karlı alım-satım zamanlamasını belirle (giriş günü, çıkış günü)
2. Long mu short mu daha mantıklı?
3. Tahmini Sharpe ratio
4. Güven seviyesi
"""
    return prompt


def build_batch_prompt(stocks_data: List[Dict]) -> str:
    """Birden fazla hisseyi tek promptta gönder."""
    
    sections = []
    for sd in stocks_data:
        tk = sd['ticker']
        det = sd['detection']
        pat = sd['patterns']
        pi = sd['price_info']
        
        strats = pat.get('strategies', [])
        best = sorted(strats, key=lambda s: s.get('sharpe', 0), reverse=True)
        
        best_str = "N/A"
        if best:
            b = best[0]
            best_str = (f"{b['name']} day{b['entry_day']:+d}→{b['exit_day']:+d} "
                       f"ret={b['avg_ret']:+.2f}% sharpe={b['sharpe']:.2f} "
                       f"win={b['win_rate']:.0%} p={b['pval']:.3f}")
        
        # Top 3 significant daily patterns
        sig_days = [d for d in pat.get('daily_stats', []) 
                   if d['pval'] < 0.10 and d['n'] >= MIN_CYCLES]
        sig_str = ", ".join(f"d{d['day']:+d}={d['avg']:+.3f}%" for d in sig_days[:5])
        
        sections.append(
            f"  {tk:14s} div=${det['div_amount']:.3f} yld={pi.get('yield_pct',0):.1f}% "
            f"cyc={det['n_confirmed']} q={det['quality']} "
            f"str={pat.get('pattern_strength',0):.0f}%\n"
            f"    Best: {best_str}\n"
            f"    Sig days: {sig_str or 'none'}"
        )
    
    stocks_str = "\n".join(sections)
    
    prompt = f"""
═══════════════════════════════════════════════════
PREFERRED STOCK EX-DIV DÖNGÜ ANALİZİ — {len(stocks_data)} HİSSE
═══════════════════════════════════════════════════

Her hissenin 3 aylık temettu döngüsündeki fiyat davranışı analiz edildi.
Excess return (piyasa medyanına göre) bazında pattern ve stratejiler:

{stocks_str}

═══════════════════════════════════════════════════
GÖREV:
1. Bu hisseler arasından EN İYİ 10 trading fırsatını seç
2. Her fırsat için: ticker, strateji (long/short), giriş/çıkış günü, 
   beklenen return, Sharpe, güven seviyesi
3. Genel piyasa insight'ı: Preferred stocklarda ex-div döngüsü 
   ne kadar exploitable?

JSON formatında cevapla:
```json
{{
  "top_opportunities": [
    {{
      "ticker": "XXX",
      "strategy": "LONG/SHORT",
      "entry_day": -5,
      "exit_day": +3,
      "expected_return_pct": 0.5,
      "sharpe": 1.2,
      "win_rate": 0.7,
      "confidence": "HIGH/MEDIUM/LOW",
      "reasoning": "kısa açıklama"
    }}
  ],
  "market_insight": "genel yorum",
  "exploitability_score": 7
}}
```
"""
    return prompt


# =====================================================================
# RUNNER
# =====================================================================

def run_detection(tickers: List[str] = None, verbose: bool = False) -> Dict[str, Dict]:
    """Tüm hisselerde ex-div tarih tespiti."""
    div_info = load_div_info()
    all_tickers = get_all_tickers()

    if tickers is None:
        tickers = all_tickers

    # Sadece div bilgisi olanları al
    tickers = [t for t in tickers if t in div_info]

    print(f"[DETECT] {len(tickers)} hisse taranacak...")
    t0 = time.time()

    results = {}
    ok = skip = 0
    for i, tk in enumerate(tickers):
        info = div_info[tk]
        det = detect_exdiv_dates(tk, info['div_amount'], info['anchor_date'], all_tickers)

        if det.get('error') or det['n_confirmed'] < MIN_CYCLES:
            skip += 1
            if verbose:
                err_msg = det.get('error', '')
                if not err_msg:
                    nc = det.get('n_confirmed', 0)
                    err_msg = f'only {nc} confirmed'
                print(f"  SKIP {tk}: {err_msg}")
            continue

        results[tk] = det
        ok += 1

        if verbose and (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(tickers)} ({ok} ok, {skip} skip)")

    elapsed = time.time() - t0
    print(f"[DETECT] Done: {ok} detected, {skip} skipped in {elapsed:.1f}s")
    return results


def run_patterns(detections: Dict[str, Dict], verbose: bool = False) -> Dict[str, Dict]:
    """Tüm hisselerde pattern hesaplama."""
    div_info = load_div_info()
    print(f"[PATTERN] {len(detections)} hisse için pattern hesaplanacak...")
    t0 = time.time()

    results = {}
    for i, (tk, det) in enumerate(detections.items()):
        pat = compute_excess_patterns(tk, det['div_amount'], det['exdiv_dates'])
        if not pat:
            continue

        df = load_stock_df(tk)
        avg_price = float(df['Close'].mean()) if df is not None else 0
        yield_pct = (det['div_amount'] * 4 / avg_price * 100) if avg_price > 0 else 0

        results[tk] = {
            'ticker': tk,
            'detection': det,
            'patterns': pat,
            'price_info': {
                'avg_price': round(avg_price, 2),
                'yield_pct': round(yield_pct, 1),
            },
        }

        if verbose and (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(detections)}")

    elapsed = time.time() - t0
    print(f"[PATTERN] Done: {len(results)} patterns in {elapsed:.1f}s")
    return results


def export_results(all_data: Dict[str, Dict]):
    """Sonuçları CSV'ye kaydet."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Summary CSV
    rows = []
    for tk, d in all_data.items():
        det = d['detection']
        pat = d['patterns']
        pi = d['price_info']

        strats = pat.get('strategies', [])
        best_long = max((s for s in strats if not s['is_short']),
                        key=lambda s: s['sharpe'], default=None)
        best_short = max((s for s in strats if s['is_short']),
                         key=lambda s: s['sharpe'], default=None)

        row = {
            'ticker': tk,
            'div_amount': det['div_amount'],
            'yield_pct': pi['yield_pct'],
            'avg_price': pi['avg_price'],
            'n_exdivs': det['n_confirmed'],
            'quality': det['quality'],
            'avg_cycle': det['avg_cycle_days'],
            'pattern_strength': pat['pattern_strength'],
        }
        if best_long:
            row['best_long_name'] = best_long['name']
            row['best_long_entry'] = best_long['entry_day']
            row['best_long_exit'] = best_long['exit_day']
            row['best_long_ret'] = best_long['avg_ret']
            row['best_long_sharpe'] = best_long['sharpe']
            row['best_long_win'] = best_long['win_rate']
            row['best_long_pval'] = best_long['pval']
        if best_short:
            row['best_short_name'] = best_short['name']
            row['best_short_entry'] = best_short['entry_day']
            row['best_short_exit'] = best_short['exit_day']
            row['best_short_ret'] = best_short['avg_ret']
            row['best_short_sharpe'] = best_short['sharpe']
            row['best_short_win'] = best_short['win_rate']
            row['best_short_pval'] = best_short['pval']

        rows.append(row)

    sdf = pd.DataFrame(rows).sort_values('pattern_strength', ascending=False)
    sp = os.path.join(OUTPUT_DIR, "v5_summary.csv")
    sdf.to_csv(sp, index=False)

    # ExDiv dates CSV
    exdiv_rows = []
    for tk, d in all_data.items():
        det = d['detection']
        for w in det.get('all_windows', []):
            exdiv_rows.append({
                'ticker': tk,
                'expected_month': w['expected_month'],
                'detected_date': w['detected_date'],
                'confidence': w['confidence'],
                'divergence_pct': w['divergence_pct'],
                'stock_gap_pct': w['stock_gap_pct'],
                'peer_median_pct': w['peer_median_pct'],
            })
    pd.DataFrame(exdiv_rows).to_csv(
        os.path.join(OUTPUT_DIR, "v5_exdiv_dates.csv"), index=False)

    print(f"[EXPORT] Saved to {OUTPUT_DIR}")
    print(f"  Summary: {sp} ({len(sdf)} stocks)")
    return sdf


def print_top_results(all_data: Dict[str, Dict], top_n: int = 25):
    """En iyi sonuçları yazdır."""
    ranked = []
    for tk, d in all_data.items():
        pat = d['patterns']
        strats = pat.get('strategies', [])
        best = max(strats, key=lambda s: s.get('sharpe', 0), default=None)
        if best:
            ranked.append((tk, d, best))

    ranked.sort(key=lambda x: x[2]['sharpe'], reverse=True)

    print(f"\n{'='*80}")
    print(f"  TOP {top_n} SHARPE — EX-DIV CYCLE STRATEGIES")
    print(f"{'='*80}")
    print(f"  {'Ticker':14s} {'Strategy':16s} {'Entry':>6s} {'Exit':>5s} "
          f"{'Ret%':>6s} {'Win%':>5s} {'Sharpe':>7s} {'pVal':>6s} {'n':>3s}")
    print(f"  {'-'*72}")

    for tk, d, best in ranked[:top_n]:
        det = d['detection']
        sig = '***' if best['pval'] < 0.05 else '**' if best['pval'] < 0.10 else ''
        print(f"  {tk:14s} {best['name']:16s} "
              f"d{best['entry_day']:+3d}  d{best['exit_day']:+3d} "
              f"{best['avg_ret']:>+5.2f}% {best['win_rate']:>4.0%} "
              f"{best['sharpe']:>+6.2f} {best['pval']:>5.3f} {best['n_trades']:>3d} {sig}")


# =====================================================================
# MAIN
# =====================================================================

def main():
    args = sys.argv[1:]

    single = None
    detect_only = False
    for a in args:
        if a == '--detect-only':
            detect_only = True
        elif a == '--single':
            idx = args.index(a)
            if idx + 1 < len(args):
                single = args[idx + 1]

    if single:
        # Tek hisse modu
        div_info = load_div_info()
        info = div_info.get(single)
        if not info:
            print(f"No div info for {single}")
            return

        print(f"\n{'='*60}")
        print(f"  {single} — SINGLE STOCK ANALYSIS")
        print(f"{'='*60}")

        det = detect_exdiv_dates(single, info['div_amount'], info['anchor_date'])
        print(f"\n  Div: ${info['div_amount']:.4f}")
        print(f"  Detected: {det['n_confirmed']} ex-divs (quality={det['quality']})")
        print(f"  Avg cycle: {det['avg_cycle_days']:.0f} days (std={det['cycle_std']:.0f})")
        print(f"\n  Ex-div windows:")
        for w in det.get('all_windows', []):
            print(f"    {w['expected_month']}: {w['detected_date']} "
                  f"gap={w['stock_gap_pct']:+.1f}% peer={w['peer_median_pct']:+.1f}% "
                  f"div={w['divergence_pct']:+.1f}% [{w['confidence']}]")

        if not detect_only and det['n_confirmed'] >= MIN_CYCLES:
            pat = compute_excess_patterns(single, info['div_amount'], det['exdiv_dates'])
            if pat:
                print(f"\n  Pattern strength: {pat['pattern_strength']}%")
                print(f"\n  Strategies:")
                for s in sorted(pat['strategies'], key=lambda x: x['sharpe'], reverse=True):
                    sig = '***' if s['pval'] < 0.05 else '**' if s['pval'] < 0.10 else ''
                    print(f"    {s['name']:16s} d{s['entry_day']:+3d}→d{s['exit_day']:+3d} "
                          f"ret={s['avg_ret']:+.2f}% win={s['win_rate']:.0%} "
                          f"sharpe={s['sharpe']:+.2f} p={s['pval']:.3f} {sig}")
        return

    # Full pipeline
    print(f"\n{'='*60}")
    print(f"  EX-DIV PIPELINE v5 — FULL RUN")
    print(f"{'='*60}\n")

    # Adım 1: Tarih tespiti
    detections = run_detection(verbose=True)

    if detect_only:
        # Sadece tarih tespiti
        for tk, det in sorted(detections.items()):
            dates = ", ".join(det['exdiv_dates'][-4:])
            print(f"  {tk:14s} n={det['n_confirmed']:>2d} q={det['quality']:5s} "
                  f"cycle={det['avg_cycle_days']:.0f}d  last: {dates}")
        return

    # Adım 2: Pattern hesaplama
    all_data = run_patterns(detections, verbose=True)

    # Adım 3: Sonuçları yazdır ve kaydet
    print_top_results(all_data)
    export_results(all_data)


if __name__ == '__main__':
    main()
