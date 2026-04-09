"""
Ex-Dividend Pattern Analyzer — Gemini Flash Enhanced
=====================================================

QAgentV1'in veri altyapısını (UTALLDATA, janalldata.csv) + Gemini Flash'ı birleştirir.

AKIŞ:
1. UTALLDATA'dan tüm preferred stock CSV'lerini oku
2. janalldata.csv + ek CSV'lerden div_amount bilgisini yükle
3. Her hisse için:
   a) Ex-div tarihlerini tespit et (cross-sectional divergence)
   b) Günlük excess return pattern hesapla
   c) İstatistiksel sinyalleri bul (LONG/SHORT/CAPTURE/WASHOUT/RECOVERY)
   d) Tüm bu verileri Gemini Flash'a gönder — derin analiz iste
4. Flash çıktısı: Pattern yorumu, long/short fırsatları, sonraki ex-div tahmini
5. Sonuçları Redis'e kaydet — UI'dan görülebilir

KULLANIM:
  analyzer = ExDivFlashAnalyzer(gemini_api_key="...")
  await analyzer.analyze_all()        # Tüm hisseler
  await analyzer.analyze_single("F PRB")  # Tek hisse
"""

import os
import glob
import json
import asyncio
import numpy as np
import pandas as pd
import warnings
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple, Any
from collections import deque
from math import erfc, sqrt

warnings.filterwarnings('ignore')

from app.core.logger import logger

# =====================================================================
# CONFIG
# =====================================================================

STOCKTRACKER_ROOT = r"C:\StockTracker"
UTALLDATA_DIR = os.path.join(STOCKTRACKER_ROOT, "UTALLDATA")
QAGENTV1_DIR = os.path.join(STOCKTRACKER_ROOT, "qagentv1")
BASELINE_FILE = os.path.join(QAGENTV1_DIR, "data", "market_baseline.pkl")

CYCLE_TRADING_DAYS = 63
EXPECT_START = 57
EXPECT_END = 75
PATTERN_WINDOW = 20        # Günlük pattern penceresi (exdiv etrafında)
MIN_CYCLES = 3             # Minimum exdiv cycle sayısı
MIN_VOLUME = 300


# =====================================================================
# MARKET BASELINE (cross-sectional)
# =====================================================================

_BASELINE = None
_MARKET_DAILY_RET = None


def _load_baseline() -> Dict:
    global _BASELINE
    if _BASELINE is not None:
        return _BASELINE
    
    import pickle
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE, 'rb') as f:
            _BASELINE = pickle.load(f)
    else:
        _BASELINE = {}
    return _BASELINE


def _load_market_daily_returns() -> Dict[str, float]:
    """Tüm hisselerin günlük close-to-close return medyanı."""
    global _MARKET_DAILY_RET
    if _MARKET_DAILY_RET is not None:
        return _MARKET_DAILY_RET
    
    files = sorted(glob.glob(os.path.join(UTALLDATA_DIR, "*22exdata.csv")))
    daily_rets = {}
    
    for fp in files:
        try:
            df = pd.read_csv(fp)
            if 'Date' not in df.columns or 'Close' not in df.columns:
                continue
            close = df['Close'].values
            dates = df['Date'].astype(str).str[:10].values
            for i in range(1, len(df)):
                if close[i-1] > 0 and not np.isnan(close[i-1]) and not np.isnan(close[i]):
                    ret = (close[i] - close[i-1]) / close[i-1] * 100
                    ds = dates[i]
                    if ds not in daily_rets:
                        daily_rets[ds] = []
                    daily_rets[ds].append(ret)
        except Exception:
            pass
    
    _MARKET_DAILY_RET = {}
    for ds, rets in daily_rets.items():
        if len(rets) >= 10:
            _MARKET_DAILY_RET[ds] = float(np.median(rets))
    
    logger.info(f"[EXDIV] Market daily returns loaded: {len(_MARKET_DAILY_RET)} days")
    return _MARKET_DAILY_RET


# =====================================================================
# EX-DIV DETECTION (from QAgentV1 exdiv_detector logic)
# =====================================================================

def _score_day(df: pd.DataFrame, idx: int, div_amount: float):
    """Ex-div olma olasılığını skorla."""
    close = df['Close'].values
    open_p = df['Open'].values
    date_strs = df['Date'].astype(str).str[:10].values
    
    if idx <= 0 or idx >= len(df):
        return (0, 0, 0, 0)
    
    prev_close = close[idx - 1]
    curr_open = open_p[idx]
    
    if prev_close <= 0 or np.isnan(prev_close) or np.isnan(curr_open):
        return (0, 0, 0, 0)
    
    gap_dollar = curr_open - prev_close
    stock_gap_pct = gap_dollar / prev_close
    
    bl = _load_baseline()
    baseline = bl.get(date_strs[idx], None)
    expected_div_pct = div_amount / prev_close if prev_close > 0 else 0
    
    if baseline is None:
        if gap_dollar < -0.02 and div_amount > 0:
            ratio = abs(gap_dollar) / div_amount
            if 0.50 <= ratio <= 1.50:
                conf = (1.0 - abs(ratio - 1.0)) * 0.6
                return (conf, gap_dollar, stock_gap_pct, expected_div_pct)
        return (0, gap_dollar, 0, expected_div_pct)
    
    market_gap_pct = baseline.get('median_gap', 0) / 100
    divergence = stock_gap_pct - market_gap_pct
    
    confidence = 0
    if expected_div_pct > 0 and divergence < 0:
        ratio = abs(divergence) / expected_div_pct
        if 0.45 <= ratio <= 1.55:
            closeness = 1.0 - abs(ratio - 1.0)
            confidence = closeness * 0.70
            if gap_dollar < -0.02:
                raw_ratio = abs(gap_dollar) / div_amount
                if 0.50 <= raw_ratio <= 1.50:
                    confidence += (1.0 - abs(raw_ratio - 1.0)) * 0.20
            curr_close = close[idx]
            if not np.isnan(curr_close):
                close_change = (curr_close - prev_close) / prev_close
                if close_change < -expected_div_pct * 0.3:
                    confidence += 0.10
    
    return (min(confidence, 1.0), gap_dollar, divergence, expected_div_pct)


def detect_exdivs(df: pd.DataFrame, div_amount: float, 
                  anchor_date: str = "") -> Dict[str, Any]:
    """Ex-div tarihlerini tespit et, sonuçları dict olarak dön."""
    dates = pd.to_datetime(df['Date'])
    date_strs = df['Date'].astype(str).str[:10].values
    n = len(df)
    
    events = []
    data_gaps = []
    
    # Data gaps
    for i in range(1, n):
        cal_diff = (dates.iloc[i] - dates.iloc[i-1]).days
        if cal_diff > 20:
            data_gaps.append((i-1, i, cal_diff))
    
    # Anchor seed
    anchor_idx = None
    if anchor_date and anchor_date != 'nan':
        try:
            anchor_ts = pd.to_datetime(anchor_date)
            diffs = abs(dates - anchor_ts)
            closest = diffs.idxmin()
            if abs((dates.iloc[closest] - anchor_ts).days) <= 5:
                anchor_idx = closest
                conf, gap_d, div_pct, exp_pct = _score_day(df, closest, div_amount)
                events.append({
                    'idx': closest,
                    'date': dates.iloc[closest].strftime('%Y-%m-%d'),
                    'gap_dollar': round(gap_d, 3),
                    'confidence': round(max(conf, 0.8), 3),
                    'method': 'anchor_seed'
                })
        except Exception:
            pass
    
    # Forward scan
    existing = {e['idx'] for e in events}
    last_idx = max(existing) if existing else -CYCLE_TRADING_DAYS
    days_since = 0
    
    for idx in range(max(1, last_idx + 1), n):
        cal_diff = (dates.iloc[idx] - dates.iloc[idx-1]).days
        if cal_diff > 20:
            est_days = int(cal_diff * 5 / 7)
            days_since = (days_since + est_days) % CYCLE_TRADING_DAYS
        else:
            days_since += 1
        
        if idx in existing:
            days_since = 0
            continue
        
        if days_since >= EXPECT_START:
            conf, gap_d, div_pct, exp_pct = _score_day(df, idx, div_amount)
            threshold = 0.50 if days_since < EXPECT_END else 0.30
            
            if conf >= threshold:
                events.append({
                    'idx': idx,
                    'date': dates.iloc[idx].strftime('%Y-%m-%d'),
                    'gap_dollar': round(gap_d, 3),
                    'confidence': round(conf, 3),
                    'method': 'divergence' if conf >= 0.50 else 'gap_only'
                })
                existing.add(idx)
                days_since = 0
    
    # Backward scan from anchor
    if anchor_idx is not None:
        days_back = 0
        for idx in range(anchor_idx - 1, 0, -1):
            cal_diff = (dates.iloc[idx + 1] - dates.iloc[idx]).days
            if cal_diff > 20:
                est_days = int(cal_diff * 5 / 7)
                days_back = (days_back + est_days) % CYCLE_TRADING_DAYS
            else:
                days_back += 1
            
            if days_back >= EXPECT_START and idx not in existing:
                conf, gap_d, div_pct, exp_pct = _score_day(df, idx, div_amount)
                threshold = 0.50 if days_back <= EXPECT_END else 0.30
                if conf >= threshold:
                    events.append({
                        'idx': idx,
                        'date': dates.iloc[idx].strftime('%Y-%m-%d'),
                        'gap_dollar': round(gap_d, 3),
                        'confidence': round(conf, 3),
                        'method': 'divergence'
                    })
                    existing.add(idx)
                    days_back = 0
    
    # Deduplicate + sort
    seen = set()
    unique = []
    for e in sorted(events, key=lambda x: x['idx']):
        if e['idx'] not in seen:
            seen.add(e['idx'])
            unique.append(e)
    events = unique
    
    # Cycle quality
    if len(events) >= 2:
        valid_cycles = []
        for i in range(1, len(events)):
            gap = events[i]['idx'] - events[i-1]['idx']
            has_data_gap = any(
                events[i-1]['idx'] <= dg[0] and events[i]['idx'] >= dg[1]
                for dg in data_gaps
            )
            if not has_data_gap:
                valid_cycles.append(gap)
        avg_cycle = float(np.mean(valid_cycles)) if valid_cycles else 63.0
        cycle_std = float(np.std(valid_cycles)) if valid_cycles else 99.0
        quality = 'good' if cycle_std < 5 and len(events) >= 6 else \
                  'fair' if cycle_std < 10 and len(events) >= 4 else 'poor'
    else:
        avg_cycle = 63.0
        cycle_std = 99.0
        quality = 'poor'
    
    return {
        'events': events,
        'n_cycles': len(events),
        'avg_cycle_len': round(avg_cycle, 1),
        'cycle_std': round(cycle_std, 1),
        'quality': quality,
        'data_gaps': len(data_gaps),
        'exdiv_dates': [e['date'] for e in events]
    }


# =====================================================================
# PATTERN COMPUTATION (excess return based)
# =====================================================================

def compute_patterns(df: pd.DataFrame, exdiv_indices: List[int], 
                     div_amount: float) -> Dict[str, Any]:
    """Her ex-div etrafında daily excess return pattern hesapla."""
    close = df['Close'].values
    date_strs = df['Date'].astype(str).str[:10].values
    market_rets = _load_market_daily_returns()
    
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
            
            mkt_ret = market_rets.get(date_strs[t], 0.0)
            excess_ret = stock_ret - mkt_ret
            daily_data[offset].append(excess_ret)
    
    # Compute daily stats
    daily_stats = []
    cum = 0.0
    for offset in range(-PATTERN_WINDOW, PATTERN_WINDOW + 1):
        rets = daily_data[offset]
        n = len(rets)
        if n < MIN_CYCLES:
            daily_stats.append({
                'day': offset, 'avg_ret': 0, 'cum_ret': round(cum, 4),
                'pos_rate': 0.5, 'n': n, 'std': 0
            })
            continue
        arr = np.array(rets)
        avg = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if n > 1 else 0
        pos = float((arr > 0).mean())
        cum += avg
        
        # T-test for significance
        t_stat = avg / (std / np.sqrt(n)) if std > 0 and n > 1 else 0
        p_val = erfc(abs(t_stat) / sqrt(2)) if t_stat != 0 else 1.0
        
        daily_stats.append({
            'day': offset,
            'avg_ret': round(avg, 4),
            'cum_ret': round(cum, 4),
            'pos_rate': round(pos, 3),
            'n': n,
            'std': round(std, 4),
            't_stat': round(t_stat, 2),
            'p_value': round(p_val, 4)
        })
    
    # Window summaries
    windows = {}
    for name, start, end in [
        ('pre_capture_5d', -5, -1),
        ('exdiv_day', 0, 0),
        ('washout_5d', 1, 5),
        ('post_10d', 5, 10),
        ('recovery_20d', 10, 20),
    ]:
        w_rets = []
        for offset in range(start, end + 1):
            for r in daily_data.get(offset, []):
                pass  # Individual trade returns would go here
        w_avg = sum(d['avg_ret'] for d in daily_stats if start <= d['day'] <= end)
        w_pos = np.mean([d['pos_rate'] for d in daily_stats 
                        if start <= d['day'] <= end and d['n'] >= MIN_CYCLES]) \
                if any(d['n'] >= MIN_CYCLES for d in daily_stats if start <= d['day'] <= end) else 0.5
        windows[name] = {
            'total_ret': round(w_avg, 4),
            'avg_pos_rate': round(float(w_pos), 3)
        }
    
    # Trade signal detection
    signals = _detect_trade_signals(df, exdiv_indices, div_amount, daily_stats)
    
    # Overall pattern strength (istatistiksel olarak anlamlı günlerin oranı)
    n_sig = sum(1 for d in daily_stats if d.get('p_value', 1) < 0.10 and d['n'] >= MIN_CYCLES)
    n_test = sum(1 for d in daily_stats if d['n'] >= MIN_CYCLES)
    strength = round((n_sig / n_test * 100), 1) if n_test > 0 else 0
    
    return {
        'daily_stats': daily_stats,
        'windows': windows,
        'signals': signals,
        'pattern_strength': strength,
    }


def _detect_trade_signals(df, exdiv_indices, div_amount, daily_stats):
    """LONG/SHORT sinyalleri tespit et."""
    close = df['Close'].values
    date_strs = df['Date'].astype(str).str[:10].values
    market_rets = _load_market_daily_returns()
    
    signals = []
    
    def calc_trade_returns(entry_off, exit_off, is_short):
        rets = []
        for ei in exdiv_indices:
            e = ei + entry_off
            x = ei + exit_off
            if e < 0 or x < 0 or e >= len(close) or x >= len(close) or close[e] <= 0:
                continue
            divs = sum(div_amount for oi in exdiv_indices if e < oi <= x) if div_amount > 0 else 0
            if is_short:
                stock_ret = (close[e] - close[x] - divs) / close[e] * 100
            else:
                stock_ret = (close[x] + divs - close[e]) / close[e] * 100
            mkt_cum = sum(market_rets.get(date_strs[di], 0.0) 
                         for di in range(min(e,x)+1, max(e,x)+1) if di < len(date_strs))
            rets.append(stock_ret - mkt_cum)
        return rets
    
    def make_signal(action, rets, entry_day, exit_day):
        if len(rets) < MIN_CYCLES:
            return None
        arr = np.array(rets)
        m = float(np.mean(arr))
        s = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0
        t = m / (s / np.sqrt(len(arr))) if s > 0 else 0
        pv = erfc(abs(t) / sqrt(2)) if t != 0 else 1.0
        wr = float((arr > 0).mean())
        return {
            'action': action,
            'entry_day': entry_day,
            'exit_day': exit_day,
            'expected_return': round(m, 3),
            'win_rate': round(wr, 3),
            't_stat': round(t, 2),
            'p_value': round(pv, 4),
            'n_trades': len(arr),
            'significant': pv < 0.10
        }
    
    # Cumulative return'lerin min/max noktalarını bul
    cum_vals = [(d['day'], d['cum_ret']) for d in daily_stats if d['n'] >= MIN_CYCLES]
    if len(cum_vals) >= 10:
        min_pt = min(cum_vals, key=lambda x: x[1])
        max_pt = max(cum_vals, key=lambda x: x[1])
        swing = max_pt[1] - min_pt[1]
        
        if swing > 0.15:
            # Optimal LONG: buy at min, sell at max
            lr = calc_trade_returns(min_pt[0], max_pt[0], False)
            sig = make_signal('LONG', lr, min_pt[0], max_pt[0])
            if sig and sig['expected_return'] > 0.05:
                signals.append(sig)
            
            # Optimal SHORT: short at max, cover at min
            sr = calc_trade_returns(max_pt[0], min_pt[0], True)
            sig = make_signal('SHORT', sr, max_pt[0], min_pt[0])
            if sig and sig['expected_return'] > 0.05:
                signals.append(sig)
    
    # Pre-div CAPTURE: buy -7, sell -1 (temettu öncesi yükseliş yakalama)
    cr = calc_trade_returns(-7, -1, False)
    sig = make_signal('CAPTURE', cr, -7, -1)
    if sig and abs(sig['expected_return']) > 0.03:
        signals.append(sig)
    
    # WASHOUT: short 0, cover +5 (temettu sonrası düşüşten kazanç)
    wr = calc_trade_returns(0, 5, True)
    sig = make_signal('WASHOUT', wr, 0, 5)
    if sig and abs(sig['expected_return']) > 0.03:
        signals.append(sig)
    
    # RECOVERY: buy +5, sell +15 (dipten toparlanmayı yakala)
    rr = calc_trade_returns(5, 15, False)
    sig = make_signal('RECOVERY', rr, 5, 15)
    if sig and abs(sig['expected_return']) > 0.03:
        signals.append(sig)
    
    # Dividend CAPTURE: buy -2, hold through ex-div, sell +2
    dc = calc_trade_returns(-2, 2, False)
    sig = make_signal('DIV_HOLD', dc, -2, 2)
    if sig:
        signals.append(sig)
    
    return signals


# =====================================================================
# NEXT EX-DIV PREDICTION
# =====================================================================

def predict_next_exdiv(exdiv_dates: List[str], avg_cycle_days: float) -> Dict[str, Any]:
    """Sonraki ex-div tarihini tahmin et."""
    if not exdiv_dates:
        return {'predicted_date': None, 'confidence': 0}
    
    last_date = pd.to_datetime(exdiv_dates[-1])
    # Trading days → calendar days (approx)
    cal_days = int(avg_cycle_days * 7 / 5)
    predicted = last_date + timedelta(days=cal_days)
    
    today = pd.Timestamp.now().normalize()
    days_away = (predicted - today).days
    
    return {
        'last_exdiv': exdiv_dates[-1],
        'predicted_date': predicted.strftime('%Y-%m-%d'),
        'days_away': days_away,
        'status': 'YAKLAŞIYOR' if 0 < days_away <= 14 else 
                  'GEÇMİŞ OLABILIR' if days_away <= 0 else 'UZAKTA',
        'avg_cycle_calendar_days': cal_days
    }


# =====================================================================
# GEMINI FLASH PROMPT BUILDER
# =====================================================================

def build_exdiv_prompt(ticker: str, div_amount: float, 
                       exdiv_result: Dict, pattern_result: Dict,
                       prediction: Dict, price_summary: Dict) -> str:
    """Gemini Flash'a gönderilecek analiz promptu."""
    
    exdiv_dates_str = ", ".join(exdiv_result.get('exdiv_dates', []))
    
    # Günlük pattern tablosu (önemli günler)
    daily_table = []
    for d in pattern_result.get('daily_stats', []):
        if abs(d['day']) <= 10 or d['day'] % 5 == 0:
            sig_mark = " *" if d.get('p_value', 1) < 0.10 else ""
            daily_table.append(
                f"  Day {d['day']:+3d}: avg={d['avg_ret']:+.3f}% cum={d['cum_ret']:+.3f}% "
                f"pos={d['pos_rate']:.0%} n={d['n']}{sig_mark}"
            )
    daily_str = "\n".join(daily_table)
    
    # Sinyaller
    signals_str = "Yok"
    signals = pattern_result.get('signals', [])
    if signals:
        sig_lines = []
        for s in signals:
            star = "***" if s.get('p_value', 1) < 0.05 else "**" if s.get('p_value', 1) < 0.10 else ""
            sig_lines.append(
                f"  {s['action']}: giriş=day{s['entry_day']:+d} çıkış=day{s['exit_day']:+d} "
                f"beklenen={s['expected_return']:+.2f}% win={s['win_rate']:.0%} "
                f"p={s.get('p_value', 'N/A')} {star}"
            )
        signals_str = "\n".join(sig_lines)
    
    # Windows
    windows = pattern_result.get('windows', {})
    windows_str = "\n".join([
        f"  {k}: toplam_ret={v['total_ret']:+.3f}% avg_pos={v['avg_pos_rate']:.0%}"
        for k, v in windows.items()
    ])
    
    prompt = f"""
═══════════════════════════════════════════════════
PREFERRED STOCK EX-DIV PATTERN ANALİZİ: {ticker}
═══════════════════════════════════════════════════

TEMEL BİLGİ:
- Ticker: {ticker}
- Çeyreklik temettü: ${div_amount:.4f}
- Tespit edilen ex-div sayısı: {exdiv_result['n_cycles']}
- Ortalama cycle: {exdiv_result['avg_cycle_len']:.1f} iş günü (std={exdiv_result['cycle_std']:.1f})
- Tespit kalitesi: {exdiv_result['quality']}
- Veri aralığı: {price_summary.get('date_range', 'N/A')}
- Ortalama fiyat: ${price_summary.get('avg_price', 0):.2f}
- Ortalama hacim: {price_summary.get('avg_volume', 0):,.0f}
- Temettü verimi (yıllık tahmini): {price_summary.get('yield_pct', 0):.1f}%

EX-DIV TARİHLERİ:
{exdiv_dates_str}

GÜNLÜK EXCESS RETURN PATTERNİ (piyasa medyanına göre):
(* = istatistiksel olarak anlamlı, p<0.10)
{daily_str}

PENCERE ÖZETLERİ:
{windows_str}

TESPİT EDİLEN SİNYALLER:
{signals_str}

Pattern gücü: {pattern_result.get('pattern_strength', 0):.1f}%

SONRAKİ EX-DIV TAHMİNİ:
- Son ex-div: {prediction.get('last_exdiv', 'N/A')}
- Tahmini sonraki: {prediction.get('predicted_date', 'N/A')}
- Durum: {prediction.get('status', 'N/A')}

═══════════════════════════════════════════════════
GÖREV:
Bu hissenin ex-div döngüsündeki fiyat davranışını DETAYLI analiz et.

LÜTFEN ŞU KONULARI CEVAPLA:
1. PATTERN DEĞERLENDİRMESİ: Bu hissede tutarlı bir ex-div pattern'i var mı?
2. LONG FIRSATI: Ex-div döngüsü etrafında LONG pozisyon fırsatı var mı? 
   (ör. temettu öncesi yükseliş yakalama, temettu sonrası dip alma)
3. SHORT FIRSATI: Ex-div sonrası kısa vadeli SHORT fırsatı var mı?
   (ör. temettu düşüşü temettu miktarından fazlaysa)
4. ÖNERİLEN STRATEJİ: Bu hisse için optimal ex-div stratejisi nedir?
5. RİSK: Dikkat edilmesi gereken riskler neler?
6. SONRAKİ EX-DIV İÇİN AKSİYON: Sonraki ex-div'e kadar ne yapılmalı?

CEVAP formatı — MUTLAKA aşağıdaki JSON yapısında:
```json
{{
  "ticker": "{ticker}",
  "pattern_assessment": "GÜÇLÜ / ORTA / ZAYIF / YOK",
  "pattern_description": "2-3 cümle pattern açıklaması",
  "long_opportunity": {{
    "exists": true/false,
    "strategy": "kısa açıklama",
    "entry_timing": "hangi gün",
    "exit_timing": "hangi gün",
    "expected_return_pct": 0.0,
    "confidence": "YÜKSEK / ORTA / DÜŞÜK"
  }},
  "short_opportunity": {{
    "exists": true/false,
    "strategy": "kısa açıklama",
    "entry_timing": "hangi gün",
    "exit_timing": "hangi gün",
    "expected_return_pct": 0.0,
    "confidence": "YÜKSEK / ORTA / DÜŞÜK"
  }},
  "recommended_strategy": "optimal strateji açıklaması",
  "risk_notes": "risk uyarıları",
  "next_exdiv_action": "sonraki ex-div için plan",
  "overall_score": 0
}}
```
"""
    return prompt


# =====================================================================
# MAIN ANALYZER CLASS
# =====================================================================

class ExDivFlashAnalyzer:
    """Gemini Flash ile derinleştirilmiş ex-div pattern analyzer."""
    
    def __init__(self, gemini_api_key: str = ""):
        self.api_key = gemini_api_key
        self.gemini = None
        self.div_info: Dict[str, Dict] = {}
        self.results: Dict[str, Dict] = {}
        self._loaded = False
    
    def _ensure_gemini(self):
        if self.gemini is None:
            from app.agent.gemini_client import GeminiFlashClient
            key = self.api_key
            if not key:
                # Try Redis
                try:
                    from app.core.redis_client import get_redis_client
                    rc = get_redis_client()
                    sync = getattr(rc, 'sync', rc)
                    key = sync.get("psfalgo:agent:gemini_api_key")
                    if isinstance(key, bytes):
                        key = key.decode()
                except Exception:
                    pass
            if not key:
                key = os.environ.get('GEMINI_API_KEY', '')
            
            if not key:
                raise ValueError("Gemini API key not found")
            
            self.gemini = GeminiFlashClient(key)
            logger.info("[EXDIV] Gemini Flash client initialized")
    
    def load_data(self):
        """Div bilgilerini ve market baseline'ı yükle."""
        if self._loaded:
            return
        
        # 1. janalldata.csv'den div bilgisi
        jpath = os.path.join(STOCKTRACKER_ROOT, "janalldata.csv")
        if os.path.exists(jpath):
            jdf = pd.read_csv(jpath, encoding='latin-1')
            for _, row in jdf.iterrows():
                tk = str(row.get('PREF IBKR', '')).strip()
                if not tk or pd.isna(row.get('DIV AMOUNT')) or row['DIV AMOUNT'] <= 0:
                    continue
                ed = str(row.get('EX-DIV DATE', '')) if pd.notna(row.get('EX-DIV DATE')) else ''
                self.div_info[tk] = {
                    'div_amount': float(row['DIV AMOUNT']),
                    'exdiv_date': ed,
                    'coupon': str(row.get('COUPON', '')) if pd.notna(row.get('COUPON')) else '',
                }
        
        # 2. Ek CSV'lerden (QAgentV1 ile aynı mantık)
        ek_files = [
            'ekheldbesmaturlu.csv', 'ekheldcilizyeniyedi.csv', 'ekheldcommonsuz.csv',
            'ekhelddeznff.csv', 'ekheldff.csv', 'ekheldflr.csv', 'ekheldgarabetaltiyedi.csv',
            'ekheldkuponlu.csv', 'ekheldkuponlukreciliz.csv', 'ekheldkuponlukreorta.csv',
            'ekheldnff.csv', 'ekheldotelremorta.csv', 'ekheldsolidbig.csv',
            'ekheldtitrekhc.csv', 'ekhighmatur.csv', 'eknotbesmaturlu.csv',
            'eknotcefilliquid.csv', 'eknottitrekhc.csv', 'ekrumoreddanger.csv',
            'eksalakilliquid.csv', 'ekshitremhc.csv'
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
                            if pd.notna(t) and t and pd.notna(d) and d > 0 and t not in self.div_info:
                                self.div_info[t] = {
                                    'div_amount': float(d), 
                                    'exdiv_date': '', 
                                    'coupon': ''
                                }
                except Exception:
                    pass
        
        # 3. Market baseline & daily returns
        _load_baseline()
        _load_market_daily_returns()
        
        self._loaded = True
        logger.info(f"[EXDIV] Data loaded: {len(self.div_info)} stocks with div info")
    
    def get_available_stocks(self) -> List[str]:
        """UTALLDATA'daki mevcut hisse listesi."""
        files = glob.glob(os.path.join(UTALLDATA_DIR, "*22exdata.csv"))
        tickers = []
        for fp in files:
            bn = os.path.basename(fp)
            tk = bn.replace("22exdata.csv", "").replace("_", " ").strip()
            if not tk.startswith("PFF"):  # ETF'leri atla
                tickers.append(tk)
        return sorted(tickers)
    
    def analyze_single_sync(self, ticker: str) -> Optional[Dict]:
        """Tek hisse için pattern analizi (sync, Gemini çağrısız)."""
        self.load_data()
        
        safe = ticker.replace(" ", "_")
        fpath = os.path.join(UTALLDATA_DIR, f"{safe}22exdata.csv")
        if not os.path.exists(fpath):
            logger.warning(f"[EXDIV] No data for {ticker}: {fpath}")
            return None
        
        # Div info
        info = self.div_info.get(ticker)
        if not info or info['div_amount'] <= 0:
            logger.warning(f"[EXDIV] No div info for {ticker} — skipping")
            return None
        
        div_amount = info['div_amount']
        anchor = info.get('exdiv_date', '')
        
        # Load price data
        try:
            df = pd.read_csv(fpath)
            df['Date'] = pd.to_datetime(df['Date'])
        except Exception as e:
            logger.error(f"[EXDIV] Error reading {fpath}: {e}")
            return None
        
        if len(df) < 100:
            return None
        if 'Volume' in df.columns and df['Volume'].mean() < MIN_VOLUME:
            return None
        
        # Price summary
        avg_price = float(df['Close'].mean())
        avg_volume = float(df['Volume'].mean()) if 'Volume' in df.columns else 0
        yield_pct = (div_amount * 4 / avg_price * 100) if avg_price > 0 else 0
        price_summary = {
            'date_range': f"{df['Date'].iloc[0].strftime('%Y-%m-%d')} → {df['Date'].iloc[-1].strftime('%Y-%m-%d')}",
            'n_days': len(df),
            'avg_price': round(avg_price, 2),
            'current_price': round(float(df['Close'].iloc[-1]), 2),
            'avg_volume': round(avg_volume, 0),
            'yield_pct': round(yield_pct, 1),
        }
        
        # Detect ex-divs
        exdiv_result = detect_exdivs(df, div_amount, anchor)
        
        if exdiv_result['n_cycles'] < MIN_CYCLES:
            logger.info(f"[EXDIV] {ticker}: only {exdiv_result['n_cycles']} cycles (need {MIN_CYCLES})")
            return None
        
        # Compute patterns
        exdiv_indices = [e['idx'] for e in exdiv_result['events']]
        pattern_result = compute_patterns(df, exdiv_indices, div_amount)
        
        # Next ex-div prediction
        prediction = predict_next_exdiv(
            exdiv_result['exdiv_dates'], 
            exdiv_result['avg_cycle_len']
        )
        
        result = {
            'ticker': ticker,
            'div_amount': div_amount,
            'yield_pct': yield_pct,
            'price_summary': price_summary,
            'exdiv': exdiv_result,
            'patterns': pattern_result,
            'prediction': prediction,
            'analyzed_at': datetime.now().isoformat(),
        }
        
        self.results[ticker] = result
        return result
    
    async def analyze_single(self, ticker: str) -> Optional[Dict]:
        """Tek hisse — pattern + Gemini Flash analizi."""
        # Sync kısmı (CPU-bound)
        result = await asyncio.get_event_loop().run_in_executor(
            None, self.analyze_single_sync, ticker
        )
        
        if result is None:
            return None
        
        # Gemini Flash analiz
        self._ensure_gemini()
        
        prompt = build_exdiv_prompt(
            ticker=ticker,
            div_amount=result['div_amount'],
            exdiv_result=result['exdiv'],
            pattern_result=result['patterns'],
            prediction=result['prediction'],
            price_summary=result['price_summary']
        )
        
        try:
            from app.agent.observer_prompts import SYSTEM_PROMPT
            raw = await self.gemini.analyze(
                system_prompt="Sen bir preferred stock ex-dividend pattern uzmanısın. "
                             "Verilen istatistiksel verileri yorumlayarak trading fırsatları belirle. "
                             "Cevabını MUTLAKA JSON formatında ver.",
                user_prompt=prompt,
                temperature=0.3,
            )
            
            # Parse JSON from response
            insight = self._parse_flash_response(raw)
            result['flash_insight'] = insight
            result['flash_raw'] = raw
            
            logger.info(f"[EXDIV] {ticker}: Flash analysis complete — "
                        f"pattern={insight.get('pattern_assessment', 'N/A')}, "
                        f"score={insight.get('overall_score', 'N/A')}")
        except Exception as e:
            logger.error(f"[EXDIV] Flash analysis error for {ticker}: {e}")
            result['flash_insight'] = {'error': str(e)}
            result['flash_raw'] = ''
        
        self.results[ticker] = result
        
        # Redis'e kaydet
        try:
            from app.core.redis_client import get_redis_client
            rc = get_redis_client()
            sync_rc = getattr(rc, 'sync', rc)
            # Sadece önemli kısmı kaydet (daily_stats çok büyük)
            save_data = {
                'ticker': ticker,
                'div_amount': result['div_amount'],
                'yield_pct': result.get('yield_pct', 0),
                'exdiv_quality': result['exdiv']['quality'],
                'n_cycles': result['exdiv']['n_cycles'],
                'pattern_strength': result['patterns']['pattern_strength'],
                'signals': result['patterns']['signals'],
                'prediction': result['prediction'],
                'flash_insight': result.get('flash_insight', {}),
                'analyzed_at': result['analyzed_at'],
            }
            sync_rc.set(
                f"psfalgo:exdiv:analysis:{ticker.replace(' ', '_')}",
                json.dumps(save_data, default=str),
                ex=86400 * 7  # 7 gün TTL
            )
        except Exception as e:
            logger.warning(f"[EXDIV] Redis save error: {e}")
        
        return result
    
    async def analyze_batch(self, tickers: List[str] = None, 
                           max_stocks: int = 0,
                           delay_seconds: float = 2.0) -> Dict[str, Dict]:
        """Birden fazla hisse analizi (rate limit'e dikkat)."""
        self.load_data()
        
        if tickers is None:
            tickers = self.get_available_stocks()
        
        if max_stocks > 0:
            tickers = tickers[:max_stocks]
        
        logger.info(f"[EXDIV] Starting batch analysis: {len(tickers)} stocks")
        
        ok = skip = error = 0
        for i, tk in enumerate(tickers):
            try:
                result = await self.analyze_single(tk)
                if result:
                    ok += 1
                else:
                    skip += 1
            except Exception as e:
                logger.error(f"[EXDIV] Error analyzing {tk}: {e}")
                error += 1
            
            if (i + 1) % 10 == 0:
                logger.info(f"[EXDIV] Progress: {i+1}/{len(tickers)} "
                           f"(ok={ok}, skip={skip}, err={error})")
            
            # Rate limit: Gemini Flash free tier = 15 RPM
            await asyncio.sleep(delay_seconds)
        
        logger.info(f"[EXDIV] Batch complete: {ok} analyzed, {skip} skipped, {error} errors")
        return self.results
    
    def get_summary(self) -> List[Dict]:
        """Tüm analiz sonuçlarının özeti."""
        summary = []
        for tk, r in sorted(self.results.items()):
            insight = r.get('flash_insight', {})
            signals = r.get('patterns', {}).get('signals', [])
            
            best_long = max((s['expected_return'] for s in signals 
                           if s['action'] in ('LONG', 'CAPTURE', 'RECOVERY', 'DIV_HOLD')), default=0)
            best_short = max((s['expected_return'] for s in signals 
                            if s['action'] in ('SHORT', 'WASHOUT')), default=0)
            
            summary.append({
                'ticker': tk,
                'div_amount': r['div_amount'],
                'yield_pct': round(r.get('yield_pct', 0), 1),
                'n_cycles': r['exdiv']['n_cycles'],
                'quality': r['exdiv']['quality'],
                'pattern_strength': r['patterns']['pattern_strength'],
                'best_long_ret': round(best_long, 2),
                'best_short_ret': round(best_short, 2),
                'next_exdiv': r.get('prediction', {}).get('predicted_date', ''),
                'next_exdiv_days': r.get('prediction', {}).get('days_away', 999),
                'flash_assessment': insight.get('pattern_assessment', 'N/A'),
                'flash_score': insight.get('overall_score', 0),
                'flash_strategy': insight.get('recommended_strategy', ''),
            })
        
        # Pattern strength'e göre sırala
        summary.sort(key=lambda x: x['pattern_strength'], reverse=True)
        return summary
    
    def _parse_flash_response(self, raw: str) -> Dict:
        """Gemini Flash cevabından JSON çıkar."""
        if not raw:
            return {'error': 'Empty response'}
        
        # JSON bloğunu bul
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Düz JSON dene
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return {
            'pattern_assessment': 'PARSE_ERROR',
            'raw_text': raw[:500],
        }


# =====================================================================
# CONVENIENCE FUNCTIONS
# =====================================================================

_ANALYZER: Optional[ExDivFlashAnalyzer] = None


def get_exdiv_analyzer() -> Optional[ExDivFlashAnalyzer]:
    return _ANALYZER


async def start_exdiv_analysis(
    api_key: str = "",
    tickers: List[str] = None,
    max_stocks: int = 0,
) -> ExDivFlashAnalyzer:
    """Ex-div analizini başlat."""
    global _ANALYZER
    
    _ANALYZER = ExDivFlashAnalyzer(gemini_api_key=api_key)
    _ANALYZER.load_data()
    
    if tickers or max_stocks > 0:
        await _ANALYZER.analyze_batch(tickers=tickers, max_stocks=max_stocks)
    
    return _ANALYZER
