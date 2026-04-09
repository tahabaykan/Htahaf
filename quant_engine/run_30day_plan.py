#!/usr/bin/env python3
"""
Günlük Ex-Div Trading Planı
=============================

Çalıştır: python run_30day_plan.py

Her çalıştırıldığında O GÜNÜN tarihine göre:
- Hangi hisselerin alım penceresi BUGÜN açık?
- Hangi hisselerin short penceresi BUGÜN açık?
- Bu hafta / gelecek hafta neler olacak?
- 30 günlük tam aksiyon planı

INPUT:
  1) Long/Short oranı (%)
  2) Long held tutma oranı (%)
  3) Short held tutma oranı (%)
"""

import os
import sys
import json
import calendar
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.insert(0, '.')

# =====================================================================
# CONFIG
# =====================================================================

TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
TODAY_STR = TODAY.strftime('%Y-%m-%d')
PLAN_DAYS = 30
END_DATE = TODAY + timedelta(days=PLAN_DAYS)
PORTFOLIO_SIZE = 1_000_000
MAX_POS_PCT = 0.03

PIPELINE_DIR = os.path.join("output", "exdiv_v5")
OUTPUT_DIR = os.path.join("output", "plan30")


# =====================================================================
# VERİ YÜKLEME
# =====================================================================

STOCKTRACKER = os.path.dirname(os.path.abspath('.'))
DRIFT_TOLERANCE = 4  # baz gunden max kayma

def _get_tickers_from_csv(filepath):
    """CSV'den ticker listesini oku (BOM-safe)."""
    tickers = set()
    try:
        df = pd.read_csv(filepath, encoding='utf-8-sig')
        for c in df.columns:
            if 'pref' in c.lower() and 'ibkr' in c.lower():
                vals = df[c].dropna().astype(str).str.strip()
                tickers = set(v for v in vals if v and v != 'nan')
                break
    except Exception:
        pass
    return tickers


def load_data():
    sp = os.path.join(PIPELINE_DIR, "v5_summary.csv")
    if not os.path.exists(sp):
        print("  Pipeline sonuclari bulunamadi!")
        print("  Once calistir: python run_full_pipeline.py")
        sys.exit(1)
    summary = pd.read_csv(sp)

    # ══════════════════════════════════════════════
    # BAZ EX-DIV: janalldata.csv (TEK DOGRU KAYNAK)
    # ══════════════════════════════════════════════
    base_exdiv_map = {}  # ticker -> base datetime

    # 1) janalldata.csv
    janall_path = os.path.join(STOCKTRACKER, "janalldata.csv")
    if os.path.exists(janall_path):
        jdf = pd.read_csv(janall_path)
        for _, row in jdf.iterrows():
            tk = str(row.get('PREF IBKR', '')).strip()
            exd = row.get('EX-DIV DATE', '')
            if tk and pd.notna(exd) and str(exd).strip():
                try:
                    dt = pd.to_datetime(str(exd).strip(), format='%m/%d/%Y')
                    base_exdiv_map[tk] = dt
                except Exception:
                    try:
                        dt = pd.to_datetime(str(exd).strip())
                        base_exdiv_map[tk] = dt
                    except Exception:
                        pass

    # 2) Fallback: ekheld CSV'leri (ex-div tarih icin)
    all_ekheld_files = [
        f for f in os.listdir(STOCKTRACKER)
        if f.startswith('ekheld') and f.endswith('.csv')
        and 'backup' not in f and 'lowest' not in f
    ]
    for ef in all_ekheld_files:
        fp = os.path.join(STOCKTRACKER, ef)
        if os.path.exists(fp):
            try:
                edf = pd.read_csv(fp, encoding='utf-8-sig')
                exdiv_col = None
                for c in edf.columns:
                    if 'ex' in c.lower() and 'div' in c.lower():
                        exdiv_col = c
                        break
                tk_col = None
                for c in edf.columns:
                    if 'pref' in c.lower() and 'ibkr' in c.lower():
                        tk_col = c
                        break
                if exdiv_col and tk_col:
                    for _, row in edf.iterrows():
                        tk = str(row.get(tk_col, '')).strip()
                        if tk and tk != 'nan' and tk not in base_exdiv_map:
                            exd = row.get(exdiv_col, '')
                            if pd.notna(exd) and str(exd).strip():
                                try:
                                    dt = pd.to_datetime(str(exd).strip(), format='%m/%d/%Y')
                                    base_exdiv_map[tk] = dt
                                except Exception:
                                    try:
                                        dt = pd.to_datetime(str(exd).strip())
                                        base_exdiv_map[tk] = dt
                                    except Exception:
                                        pass
            except Exception:
                pass

    # ══════════════════════════════════════════════
    # HELD TICKER SET: ekheld*.csv dosya isimlerinden
    # "ekheld" ile baslayan CSV = HELD grubu
    # Diger "ek" ile baslayan CSV = NOT-HELD grubu
    # ══════════════════════════════════════════════
    held_tickers = set()
    for ef in all_ekheld_files:
        fp = os.path.join(STOCKTRACKER, ef)
        held_tickers.update(_get_tickers_from_csv(fp))

    return summary, base_exdiv_map, held_tickers


# =====================================================================
# INPUT
# =====================================================================

def get_inputs():
    print()
    print("╔══════════════════════════════════════════════╗")
    print(f"║  📅 GÜNLÜK TRADİNG PLANI                    ║")
    print(f"║  Tarih: {TODAY_STR}                          ║")
    print(f"║  30 gün: {TODAY_STR} → {END_DATE.strftime('%Y-%m-%d')}          ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    # Long/Short Oranı
    print("  ┌─ ADIM 1: Long / Short Oranı ──────────────┐")
    print("  │  Örnekler: 50, 70, 30, 100                │")
    print("  └───────────────────────────────────────────┘")
    while True:
        raw = input("  Long %  [default=50]: ").strip()
        long_pct = int(raw) if raw else 50
        if 0 <= long_pct <= 100:
            short_pct = 100 - long_pct
            print(f"  ✓ Long: {long_pct}%  |  Short: {short_pct}%")
            break
        print("  ⚠ 0-100 arası gir")
    print()

    # Long Held
    print("  ┌─ ADIM 2: Long Held Oranı ─────────────────┐")
    print("  │  100 = hepsi  |  50 = en iyi yarısı       │")
    print("  └───────────────────────────────────────────┘")
    while True:
        raw = input("  Long held %  [default=100]: ").strip()
        long_held = int(raw) if raw else 100
        if 1 <= long_held <= 100:
            print(f"  ✓ Long'ların {long_held}%'i held")
            break
        print("  ⚠ 1-100 arası gir")
    print()

    # Short Held
    print("  ┌─ ADIM 3: Short Held Oranı ────────────────┐")
    print("  │  100 = hepsi  |  50 = en iyi yarısı       │")
    print("  └───────────────────────────────────────────┘")
    while True:
        raw = input("  Short held %  [default=100]: ").strip()
        short_held = int(raw) if raw else 100
        if 1 <= short_held <= 100:
            print(f"  ✓ Short'ların {short_held}%'i held")
            break
        print("  ⚠ 1-100 arası gir")
    print()

    print("  ═══════════════════════════════════════════")
    print(f"  AYARLAR: {long_pct}L/{short_pct}S  "
          f"| L-Held={long_held}%  | S-Held={short_held}%")
    print("  ═══════════════════════════════════════════")

    ok = input("\n  Devam? (E/h): ").strip().lower()
    if ok == 'h':
        sys.exit(0)

    return long_pct, short_pct, long_held, short_held


# =====================================================================
# DÖNGÜ HESAPLAMA
# =====================================================================

def find_next_exdiv(ticker, base_exdiv_map):
    """
    janalldata.csv'deki BAZ ex-div tarihinden 3'er ay ekleyerek
    bir sonraki ex-div'i bulur. Baz gun ASLA kaymaz.
    
    Ornek: BAZ = 11/29/2024 (gun=29)
    Projeksiyonlar: 02/28/2025, 05/29/2025, 08/29/2025...
    Pencere: gun +/- 4 = 25-33 arasi beklenir
    """
    if ticker not in base_exdiv_map:
        return None, None, None

    base_dt = base_exdiv_map[ticker]
    base_day = base_dt.day
    base_month = base_dt.month
    base_year = base_dt.year

    # 3'er ay ekleyerek projekte et (bazdan, kayan tarihten degil)
    for n in range(1, 30):  # max 7.5 yil ileri
        target_month = base_month + 3 * n
        target_year = base_year + (target_month - 1) // 12
        target_month = ((target_month - 1) % 12) + 1

        # Baz gununu kullan, ayin max gununu asma
        max_d = calendar.monthrange(target_year, target_month)[1]
        actual_day = min(base_day, max_d)

        projected = pd.Timestamp(target_year, target_month, actual_day)

        # Pencere: baz_gun +/- DRIFT_TOLERANCE
        window_end = projected + timedelta(days=DRIFT_TOLERANCE)

        if window_end >= TODAY:
            days_until = (projected - TODAY).days
            return projected, days_until, base_day

    return None, None, None


def biz_day(base_dt, offset):
    """İş günü offset."""
    dt = base_dt + timedelta(days=int(offset * 7 / 5))
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt


# =====================================================================
# PLAN OLUŞTURMA
# =====================================================================

def _select_held_split(candidates, max_n, held_pct, held_tickers):
    """
    Portföy seçimi: HELD / NOT-HELD oranına göre slot dağıtımı.
    
    held_pct=80, max_n=16 → 13 HELD, 3 NOT-HELD
    held_pct=50, max_n=16 → 8 HELD, 8 NOT-HELD
    
    Her grup kendi içinde score'a göre sıralanır.
    Bir grup yeterli aday sunamazsa, kalan slotlar diğer gruba kayar.
    """
    if max_n <= 0 or not candidates:
        return [], [], []
    
    # HELD ve NOT-HELD olarak ayır (score sıralı)
    held_pool = sorted([c for c in candidates if c['ticker'] in held_tickers],
                       key=lambda x: x['score'], reverse=True)
    notheld_pool = sorted([c for c in candidates if c['ticker'] not in held_tickers],
                          key=lambda x: x['score'], reverse=True)
    
    # Slot dağılımı
    n_held_slots = int(round(max_n * held_pct / 100))
    n_notheld_slots = max_n - n_held_slots
    
    # Seç (yeterli aday yoksa kalan slotlar diğer gruba kayar)
    from_held = held_pool[:n_held_slots]
    from_notheld = notheld_pool[:n_notheld_slots]
    
    # Kalan slot varsa doldur
    leftover_held = n_held_slots - len(from_held)
    leftover_notheld = n_notheld_slots - len(from_notheld)
    
    if leftover_held > 0 and len(from_notheld) < len(notheld_pool):
        extra = notheld_pool[n_notheld_slots : n_notheld_slots + leftover_held]
        from_notheld.extend(extra)
    if leftover_notheld > 0 and len(from_held) < len(held_pool):
        extra = held_pool[n_held_slots : n_held_slots + leftover_notheld]
        from_held.extend(extra)
    
    selected = from_held + from_notheld
    selected.sort(key=lambda x: x['score'], reverse=True)
    
    return selected, from_held, from_notheld


def build_plan(summary, base_exdiv_map, long_pct, short_pct, long_held_pct, short_held_pct, held_tickers=None):

    if held_tickers is None:
        held_tickers = set()

    max_per_pos = PORTFOLIO_SIZE * MAX_POS_PCT
    max_long_n = int(long_pct / 100 / MAX_POS_PCT) if long_pct > 0 else 0
    max_short_n = int(short_pct / 100 / MAX_POS_PCT) if short_pct > 0 else 0

    # ─── Dongu bilgilerini hesapla ───
    stock_cycles = []
    for _, row in summary.iterrows():
        tk = row['ticker']
        next_exdiv, days_until, base_day = find_next_exdiv(tk, base_exdiv_map)
        if next_exdiv is None:
            continue
        cycle_day = -days_until
        stock_cycles.append({
            'ticker': tk, 'row': row,
            'next_exdiv': next_exdiv, 'days_until': days_until,
            'cycle_day': cycle_day,
        })

    # ─── LONG SİNYALLER ───
    active_buys = []
    upcoming_buys = []

    for sc in stock_cycles:
        row = sc['row']
        tk = sc['ticker']
        next_exdiv = sc['next_exdiv']
        days_until = sc['days_until']

        if pd.isna(row.get('best_long_sharpe')) or row['best_long_sharpe'] < 0.3:
            continue
        if pd.isna(row.get('best_long_pval')) or row['best_long_pval'] > 0.15:
            continue

        entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
        exit_off = int(row['best_long_exit']) if pd.notna(row.get('best_long_exit')) else 0

        entry_dt = biz_day(next_exdiv, entry_off)
        exit_dt = biz_day(next_exdiv, exit_off)
        if exit_dt <= entry_dt:
            exit_dt = entry_dt + timedelta(days=2)
            while exit_dt.weekday() >= 5:
                exit_dt += timedelta(days=1)

        holding = max(1, (exit_dt - entry_dt).days)

        # SCORE: pattern gücü × zaman-normalize return bileşik skoru
        NORM_DAYS = 30
        _wr = float(row.get('best_long_win', 0))
        _sh = float(row.get('best_long_sharpe', 0))
        _pv = float(row.get('best_long_pval', 1))
        _nc = int(row.get('n_exdivs', 0))
        _rt = float(row.get('best_long_ret', 0))
        _norm_rt = _rt / max(3, exit_off - entry_off) * NORM_DAYS  # 30 günlük normalize
        _conf = min(100, max(0,
            _wr * 35 + (1 - min(_pv, 1)) * 25 +
            min(_nc, 10) / 10 * 20 + min(_sh, 5) / 5 * 20
        ))
        score = round(_conf / 10 * (1 + abs(_norm_rt) / 3), 3)

        item = {
            'ticker': tk,
            'direction': 'LONG',
            'is_held': tk in held_tickers,
            'strategy': str(row.get('best_long_name', '')),
            'entry_date': entry_dt.strftime('%Y-%m-%d'),
            'exit_date': exit_dt.strftime('%Y-%m-%d'),
            'exdiv_date': next_exdiv.strftime('%Y-%m-%d'),
            'days_until_exdiv': days_until,
            'cycle_day': sc['cycle_day'],
            'entry_offset': entry_off,
            'exit_offset': exit_off,
            'holding_days': holding,
            'raw_return': round(_rt, 3),
            'expected_return': round(_norm_rt, 3),
            'win_rate': round(float(row.get('best_long_win', 0)), 3),
            'sharpe': round(float(row.get('best_long_sharpe', 0)), 2),
            'p_value': round(float(row.get('best_long_pval', 1)), 4),
            'yield_pct': round(float(row.get('yield_pct', 0)), 1),
            'score': round(score, 3),
        }

        # Bugün pencere açık mı?
        win_start = entry_dt - timedelta(days=1)
        win_end = entry_dt + timedelta(days=1)
        if win_start <= TODAY <= win_end:
            item['signal'] = 'BUY_NOW'
            active_buys.append(item)
        elif entry_dt > TODAY and entry_dt <= END_DATE:
            item['days_to_entry'] = (entry_dt - TODAY).days
            upcoming_buys.append(item)

    active_buys.sort(key=lambda x: x['score'], reverse=True)
    upcoming_buys.sort(key=lambda x: (x.get('days_to_entry', 999), -x['score']))

    # ─── SHORT SİNYALLER ───
    active_shorts = []
    upcoming_shorts = []

    for sc in stock_cycles:
        row = sc['row']
        tk = sc['ticker']
        next_exdiv = sc['next_exdiv']
        days_until = sc['days_until']

        if pd.isna(row.get('best_short_sharpe')) or row['best_short_sharpe'] < 0.3:
            continue
        if pd.isna(row.get('best_short_pval')) or row['best_short_pval'] > 0.15:
            continue

        entry_off = int(row['best_short_entry']) if pd.notna(row.get('best_short_entry')) else 0
        exit_off = int(row['best_short_exit']) if pd.notna(row.get('best_short_exit')) else 5

        entry_dt = biz_day(next_exdiv, entry_off)
        exit_dt = biz_day(next_exdiv, exit_off)
        if exit_dt <= entry_dt:
            exit_dt = entry_dt + timedelta(days=2)
            while exit_dt.weekday() >= 5:
                exit_dt += timedelta(days=1)

        holding = max(1, (exit_dt - entry_dt).days)

        # SCORE: pattern gücü × zaman-normalize return bileşik skoru
        NORM_DAYS = 30
        _wr = float(row.get('best_short_win', 0))
        _sh = float(row.get('best_short_sharpe', 0))
        _pv = float(row.get('best_short_pval', 1))
        _nc = int(row.get('n_exdivs', 0))
        _rt = float(row.get('best_short_ret', 0))
        _norm_rt = _rt / max(3, exit_off - entry_off) * NORM_DAYS  # 30 günlük normalize
        _conf = min(100, max(0,
            _wr * 35 + (1 - min(_pv, 1)) * 25 +
            min(_nc, 10) / 10 * 20 + min(_sh, 5) / 5 * 20
        ))
        score = round(_conf / 10 * (1 + abs(_norm_rt) / 3), 3)

        item = {
            'ticker': tk,
            'direction': 'SHORT',
            'is_held': tk in held_tickers,
            'strategy': str(row.get('best_short_name', 'WASHOUT')),
            'entry_date': entry_dt.strftime('%Y-%m-%d'),
            'exit_date': exit_dt.strftime('%Y-%m-%d'),
            'exdiv_date': next_exdiv.strftime('%Y-%m-%d'),
            'days_until_exdiv': days_until,
            'cycle_day': sc['cycle_day'],
            'entry_offset': entry_off,
            'exit_offset': exit_off,
            'holding_days': holding,
            'raw_return': round(_rt, 3),
            'expected_return': round(_norm_rt, 3),
            'win_rate': round(float(row.get('best_short_win', 0)), 3),
            'sharpe': round(float(row.get('best_short_sharpe', 0)), 2),
            'p_value': round(float(row.get('best_short_pval', 1)), 4),
            'yield_pct': round(float(row.get('yield_pct', 0)), 1),
            'score': round(score, 3),
        }

        win_start = entry_dt - timedelta(days=1)
        win_end = entry_dt + timedelta(days=1)
        if win_start <= TODAY <= win_end:
            item['signal'] = 'SHORT_NOW'
            active_shorts.append(item)
        elif entry_dt > TODAY and entry_dt <= END_DATE:
            item['days_to_entry'] = (entry_dt - TODAY).days
            upcoming_shorts.append(item)

    active_shorts.sort(key=lambda x: x['score'], reverse=True)
    upcoming_shorts.sort(key=lambda x: (x.get('days_to_entry', 999), -x['score']))

    # ─── Haftalık gruplama ───
    week_end = TODAY + timedelta(days=(4 - TODAY.weekday()) % 7 + 1)
    next_week_end = week_end + timedelta(days=7)
    we_s = week_end.strftime('%Y-%m-%d')
    nwe_s = next_week_end.strftime('%Y-%m-%d')

    this_week_buys = [b for b in upcoming_buys if b['entry_date'] <= we_s]
    this_week_shorts = [s for s in upcoming_shorts if s['entry_date'] <= we_s]
    next_week_buys = [b for b in upcoming_buys if we_s < b['entry_date'] <= nwe_s]
    next_week_shorts = [s for s in upcoming_shorts if we_s < s['entry_date'] <= nwe_s]

    # ─── Portföy seçimi: HELD / NOT-HELD oranına göre ───
    all_longs = active_buys + upcoming_buys
    all_shorts = active_shorts + upcoming_shorts

    selected_longs, held_longs, notheld_longs = _select_held_split(
        all_longs, max_long_n, long_held_pct, held_tickers)
    selected_shorts, held_shorts, notheld_shorts = _select_held_split(
        all_shorts, max_short_n, short_held_pct, held_tickers)

    # Günlük aksiyon takvimi
    actions = []
    for t in selected_longs:
        actions.append({'date': t['entry_date'], 'action': 'BUY', 'ticker': t['ticker'], **t})
        actions.append({'date': t['exit_date'], 'action': 'SELL', 'ticker': t['ticker'], **t})
    for t in selected_shorts:
        actions.append({'date': t['entry_date'], 'action': 'SHORT', 'ticker': t['ticker'], **t})
        actions.append({'date': t['exit_date'], 'action': 'COVER', 'ticker': t['ticker'], **t})
    actions.sort(key=lambda x: (x['date'], x['action']))

    return {
        'active_buys': active_buys,
        'active_shorts': active_shorts,
        'this_week_buys': this_week_buys,
        'this_week_shorts': this_week_shorts,
        'next_week_buys': next_week_buys,
        'next_week_shorts': next_week_shorts,
        'selected_longs': selected_longs,
        'selected_shorts': selected_shorts,
        'held_longs': held_longs,
        'held_shorts': held_shorts,
        'notheld_longs': notheld_longs,
        'notheld_shorts': notheld_shorts,
        'all_longs_n': len(all_longs),
        'all_shorts_n': len(all_shorts),
        'actions': actions,
    }


# =====================================================================
# RAPOR
# =====================================================================

def print_and_save(plan, long_pct, short_pct, long_held_pct, short_held_pct):

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    lines = []
    def p(s=""): print(s); lines.append(s)

    p()
    p("═" * 80)
    p(f"  📅 GÜNLÜK TRADİNG PLANI — {TODAY_STR}")
    p(f"  30 gün: {TODAY_STR} → {END_DATE.strftime('%Y-%m-%d')}")
    p(f"  Sermaye: ${PORTFOLIO_SIZE:,}  |  Pos: ${int(PORTFOLIO_SIZE * MAX_POS_PCT):,}")
    p(f"  {long_pct}L/{short_pct}S | L-Held={long_held_pct}% | S-Held={short_held_pct}%")
    p("═" * 80)

    # ─── BUGÜN AKTİF SİNYALLER ───
    p()
    ab = plan['active_buys']
    ash = plan['active_shorts']
    if ab or ash:
        p(f"  ⚡ BUGÜN AKTİF SİNYALLER ({TODAY_STR})")
        p("  " + "─" * 70)
        for t in ab[:5]:
            p(f"  🟢 BUY  {t['ticker']:14s} [{t['strategy']:16s}] "
              f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  "
              f"win={t['win_rate']:.0%}  exdiv={t['exdiv_date']}")
        for t in ash[:5]:
            p(f"  🔴 SHORT {t['ticker']:14s} [{t['strategy']:16s}] "
              f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  "
              f"exdiv={t['exdiv_date']}")
    else:
        p(f"  ℹ️  Bugün ({TODAY_STR}) aktif sinyal yok")

    # ─── TOP 5 ───
    p()
    p(f"  🟢 TOP 5 BEST BUY (pencere açık: {len(ab)})")
    p(f"  {'#':>3s} {'Ticker':14s} {'Strateji':16s} {'Entry':>10s} {'ExDiv':>10s} "
      f"{'Ret%':>7s} {'Win':>5s} {'Shrp':>5s} {'Yld':>5s}")
    p("  " + "─" * 80)
    for i, t in enumerate(ab[:5], 1):
        p(f"  {i:>3d} {t['ticker']:14s} {t['strategy']:16s} {t['entry_date']:>10s} "
          f"{t['exdiv_date']:>10s} {t['expected_return']:+6.2f}% "
          f"{t['win_rate']:4.0%} {t['sharpe']:+5.1f} {t['yield_pct']:4.1f}%")
    if not ab:
        p("  (Bugün alım penceresi açık hisse yok)")

    p()
    p(f"  🔴 TOP 5 BEST SHORT (pencere açık: {len(ash)})")
    p(f"  {'#':>3s} {'Ticker':14s} {'Strateji':16s} {'Entry':>10s} {'ExDiv':>10s} "
      f"{'Ret%':>7s} {'Shrp':>5s} {'Yld':>5s}")
    p("  " + "─" * 80)
    for i, t in enumerate(ash[:5], 1):
        p(f"  {i:>3d} {t['ticker']:14s} {t['strategy']:16s} {t['entry_date']:>10s} "
          f"{t['exdiv_date']:>10s} {t['expected_return']:+6.2f}% "
          f"{t['sharpe']:+5.1f} {t['yield_pct']:4.1f}%")
    if not ash:
        p("  (Bugün short penceresi açık hisse yok)")

    # ─── BU HAFTA ───
    p()
    p(f"  📆 BU HAFTA GELECEK FIRSATLAR")
    p("  " + "─" * 60)
    for t in plan['this_week_buys'][:8]:
        p(f"  🟢 {t['ticker']:14s} entry={t['entry_date']}  "
          f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  "
          f"({t.get('days_to_entry','-')}d)")
    for t in plan['this_week_shorts'][:8]:
        p(f"  🔴 {t['ticker']:14s} entry={t['entry_date']}  "
          f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  "
          f"({t.get('days_to_entry','-')}d)")
    if not plan['this_week_buys'] and not plan['this_week_shorts']:
        p("  Bu hafta yeni sinyal yok")

    # ─── GELECEK HAFTA ───
    p()
    p(f"  📆 GELECEK HAFTA")
    p("  " + "─" * 60)
    for t in plan['next_week_buys'][:8]:
        p(f"  🟢 {t['ticker']:14s} entry={t['entry_date']}  "
          f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}")
    for t in plan['next_week_shorts'][:8]:
        p(f"  🔴 {t['ticker']:14s} entry={t['entry_date']}  "
          f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}")
    if not plan['next_week_buys'] and not plan['next_week_shorts']:
        p("  Gelecek hafta yeni sinyal yok")

    # ─── GÜNLÜK TAKVİM ───
    p()
    p("  📋 30 GÜNLÜK AKSİYON TAKVİMİ")
    p("  " + "─" * 70)
    current_date = None
    for a in plan['actions']:
        if a['date'] != current_date:
            current_date = a['date']
            is_today = current_date == TODAY_STR
            dt = pd.to_datetime(current_date)
            mark = " ⚡ BUGÜN" if is_today else ""
            p()
            p(f"  📌 {current_date} ({dt.strftime('%a')}){mark}")
        emoji = '🟢' if a['action'] == 'BUY' else '🔴' if a['action'] == 'SHORT' else '📤' if a['action'] == 'SELL' else '📥'
        p(f"     {emoji} {a['action']:6s} {a['ticker']:14s} "
          f"[{a['strategy']:16s}] ret={a['expected_return']:+.2f}% shrp={a['sharpe']:.1f}")

    # ─── İSTATİSTİKLER ───
    p()
    p("  📊 ÖZET")
    p("  " + "─" * 40)
    p(f"  Toplam Long aday:  {plan['all_longs_n']}")
    p(f"  Toplam Short aday: {plan['all_shorts_n']}")
    p(f"  Seçilen Long:  {len(plan['selected_longs'])}  "
      f"(HELD: {len(plan['held_longs'])} / NOT-HELD: {len(plan.get('notheld_longs', []))})")
    p(f"  Seçilen Short: {len(plan['selected_shorts'])}  "
      f"(HELD: {len(plan['held_shorts'])} / NOT-HELD: {len(plan.get('notheld_shorts', []))})")
    if plan['selected_longs']:
        avg_lr = np.mean([t['expected_return'] for t in plan['selected_longs']])
        avg_ls = np.mean([t['sharpe'] for t in plan['selected_longs']])
        p(f"  Long ort. ret: {avg_lr:+.2f}%  ort. sharpe: {avg_ls:.2f}")
    if plan['selected_shorts']:
        avg_sr = np.mean([t['expected_return'] for t in plan['selected_shorts']])
        avg_ss = np.mean([t['sharpe'] for t in plan['selected_shorts']])
        p(f"  Short ort. ret: {avg_sr:+.2f}%  ort. sharpe: {avg_ss:.2f}")
    p()
    p("═" * 80)

    # ─── DOSYALARA KAYDET ───
    if plan['held_longs']:
        pd.DataFrame(plan['held_longs']).to_csv(os.path.join(OUTPUT_DIR, "held_long.csv"), index=False)
    if plan['held_shorts']:
        pd.DataFrame(plan['held_shorts']).to_csv(os.path.join(OUTPUT_DIR, "held_short.csv"), index=False)
    if plan['actions']:
        pd.DataFrame(plan['actions']).to_csv(os.path.join(OUTPUT_DIR, "daily_actions.csv"), index=False)

    with open(os.path.join(OUTPUT_DIR, "plan_summary.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    with open(os.path.join(OUTPUT_DIR, "settings.json"), 'w') as f:
        json.dump({
            'date': TODAY_STR,
            'end_date': END_DATE.strftime('%Y-%m-%d'),
            'long_pct': long_pct, 'short_pct': short_pct,
            'long_held_pct': long_held_pct, 'short_held_pct': short_held_pct,
            'active_buys_today': len(plan['active_buys']),
            'active_shorts_today': len(plan['active_shorts']),
            'n_long_selected': len(plan['selected_longs']),
            'n_short_selected': len(plan['selected_shorts']),
        }, f, indent=2)

    p()
    p(f"  📁 Dosyalar: {OUTPUT_DIR}/")
    p(f"     held_long.csv     ({len(plan['held_longs'])} hisse)")
    p(f"     held_short.csv    ({len(plan['held_shorts'])} hisse)")
    p(f"     daily_actions.csv ({len(plan['actions'])} aksiyon)")
    p(f"     plan_summary.txt")
    p(f"     settings.json")
    p()
    p("  ✅ Plan hazır!")


# =====================================================================
# MAIN
# =====================================================================

def main():
    print()
    print("  Veriler yukleniyor...")
    summary, base_exdiv_map, held_tickers = load_data()
    print(f"  {len(summary)} hisse, {len(base_exdiv_map)} baz ex-div, {len(held_tickers)} held ticker")

    long_pct, short_pct, long_held_pct, short_held_pct = get_inputs()

    print()
    print("  Plan hesaplaniyor...")
    plan = build_plan(summary, base_exdiv_map, long_pct, short_pct, long_held_pct, short_held_pct, held_tickers)

    print_and_save(plan, long_pct, short_pct, long_held_pct, short_held_pct)


if __name__ == '__main__':
    main()
