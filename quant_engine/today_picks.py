"""
BUGUN icin en iyi 5 LONG + en iyi 5 SHORT
==========================================
Tarih: 2026-02-16

Mantik:
- v5_summary.csv'den pattern/sharpe/winrate bilgisi
- janalldata.csv'den baz ex-div -> sonraki ex-div projeksiyonu
- Entry penceresi BUGUN acik olan veya yaklasan hisseler
- Score = sharpe * 0.4 + win_rate * 0.3 + ret * 0.3
"""
import sys, os, calendar
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(r'c:\StockTracker\quant_engine')
sys.path.insert(0, '.')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TODAY = datetime(2026, 2, 16)
STOCKTRACKER = r'c:\StockTracker'
DRIFT_TOLERANCE = 4

# ── janalldata baz tarihler ──
base_map = {}
jdf = pd.read_csv(os.path.join(STOCKTRACKER, 'janalldata.csv'), encoding='latin-1')
for _, row in jdf.iterrows():
    tk = str(row.get('PREF IBKR', '')).strip()
    exd = row.get('EX-DIV DATE', '')
    if tk and pd.notna(exd) and str(exd).strip():
        for fmt in ['%m/%d/%Y', '%Y-%m-%d']:
            try:
                base_map[tk] = pd.to_datetime(str(exd).strip(), format=fmt)
                break
            except:
                pass

def next_exdiv(tk):
    if tk not in base_map:
        return None, None
    bd = base_map[tk]
    for n in range(1, 30):
        tm = bd.month + 3 * n
        ty = bd.year + (tm - 1) // 12
        tm = ((tm - 1) % 12) + 1
        md = calendar.monthrange(ty, tm)[1]
        ad = min(bd.day, md)
        p = pd.Timestamp(ty, tm, ad)
        if p + timedelta(days=DRIFT_TOLERANCE) >= TODAY:
            return p, (p - TODAY).days
    return None, None

# ── Pipeline sonuclari ──
sdf = pd.read_csv('output/exdiv_v5/v5_summary.csv')

print("=" * 90)
print(f"  BUGUNUN TRADE PLANI - {TODAY.strftime('%Y-%m-%d')} (Pazartesi)")
print("=" * 90)

# ── LONG adaylari ──
long_candidates = []
short_candidates = []

for _, row in sdf.iterrows():
    tk = row['ticker']
    nxt, days = next_exdiv(tk)
    if nxt is None:
        continue
    
    # LONG
    if pd.notna(row.get('best_long_sharpe')) and row['best_long_sharpe'] > 0.5:
        entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
        exit_off = int(row['best_long_exit']) if pd.notna(row.get('best_long_exit')) else 0
        
        # Entry ve exit gunleri
        entry_day = days + entry_off  # bugundan kac gun sonra entry
        exit_day = days + exit_off
        
        # Entry penceresi: bugun ± 2 gun icerisinde mi?
        entry_window = abs(entry_day)
        
        sharpe = float(row.get('best_long_sharpe', 0))
        win = float(row.get('best_long_win', 0))
        ret = float(row.get('best_long_ret', 0))
        pval = float(row.get('best_long_pval', 1))
        n_ex = int(row.get('n_exdivs', 0))
        yld = float(row.get('yield_pct', 0))
        strat = str(row.get('best_long_name', ''))
        
        # Score
        score = sharpe * 0.4 + win * 10 * 0.3 + ret * 0.3
        
        long_candidates.append({
            'ticker': tk,
            'strategy': strat,
            'next_exdiv': nxt.strftime('%Y-%m-%d'),
            'days_to_exdiv': days,
            'entry_offset': entry_off,
            'exit_offset': exit_off,
            'entry_in_days': entry_day,  # negatif = gecmis, 0 = bugun
            'exit_in_days': exit_day,
            'sharpe': sharpe,
            'win_rate': win,
            'avg_ret': ret,
            'pval': pval,
            'n_trades': n_ex,
            'yield_pct': yld,
            'score': round(score, 2),
            'phase': 'ENTRY_NOW' if -2 <= entry_day <= 2 else 
                     'HOLDING' if entry_day < -2 and exit_day >= 0 else
                     'UPCOMING' if entry_day > 2 else 'MISSED',
        })
    
    # SHORT
    if pd.notna(row.get('best_short_sharpe')) and row['best_short_sharpe'] > 0.5:
        short_entry = days  # short genelde ex-div gununde
        
        sharpe = float(row.get('best_short_sharpe', 0))
        ret = float(row.get('best_short_ret', 0))
        
        score = sharpe * 0.5 + ret * 0.5
        
        short_candidates.append({
            'ticker': tk,
            'next_exdiv': nxt.strftime('%Y-%m-%d'),
            'days_to_exdiv': days,
            'entry_in_days': short_entry,
            'sharpe': sharpe,
            'avg_ret': ret,
            'yield_pct': float(row.get('yield_pct', 0)),
            'score': round(score, 2),
            'phase': 'SHORT_NOW' if -2 <= short_entry <= 2 else
                     'UPCOMING' if short_entry > 2 else 'MISSED',
        })

# ══════════════════════════════════════════════════════
# BUGUN ENTRY PENCERESI ACIK (entry_in_days -2..+2 arasi)
# ══════════════════════════════════════════════════════
active_longs = [c for c in long_candidates if c['phase'] == 'ENTRY_NOW']
active_longs.sort(key=lambda x: x['score'], reverse=True)

active_shorts = [c for c in short_candidates if c['phase'] == 'SHORT_NOW']
active_shorts.sort(key=lambda x: x['score'], reverse=True)

# Holding (zaten icerideyiz, exit bekleniyor)
holding_longs = [c for c in long_candidates if c['phase'] == 'HOLDING']
holding_longs.sort(key=lambda x: x['score'], reverse=True)

# Yaklasan (1-7 gun icinde entry)
upcoming_longs = [c for c in long_candidates if c['phase'] == 'UPCOMING' and c['entry_in_days'] <= 7]
upcoming_longs.sort(key=lambda x: (x['entry_in_days'], -x['score']))

upcoming_shorts = [c for c in short_candidates if c['phase'] == 'UPCOMING' and c['days_to_exdiv'] <= 14]
upcoming_shorts.sort(key=lambda x: (x['days_to_exdiv'], -x['score']))

print()
print(f"  BUGUN ENTRY PENCERESI ACIK - TOP 5 LONG")
print(f"  " + "-" * 85)
print(f"  {'#':>2} {'Ticker':14s} {'Strateji':16s} {'ExDiv':>10s} {'Ent':>4s} {'Ext':>4s} "
      f"{'Ret%':>6s} {'Win':>5s} {'Shrp':>6s} {'pVal':>6s} {'n':>3s} {'Yld':>5s} {'Score':>6s}")
print(f"  " + "-" * 85)
if active_longs:
    for i, c in enumerate(active_longs[:5], 1):
        print(f"  {i:>2} {c['ticker']:14s} {c['strategy']:16s} {c['next_exdiv']:>10s} "
              f"d{c['entry_offset']:+3d} d{c['exit_offset']:+3d} "
              f"{c['avg_ret']:+5.2f}% {c['win_rate']:4.0%} {c['sharpe']:+5.1f} "
              f"{c['pval']:5.3f} {c['n_trades']:>3d} {c['yield_pct']:4.1f}% {c['score']:5.1f}")
else:
    print("  (Bugun long entry penceresi acik hisse yok)")

print()
print(f"  BUGUN ENTRY PENCERESI ACIK - TOP 5 SHORT")
print(f"  " + "-" * 85)
if active_shorts:
    for i, c in enumerate(active_shorts[:5], 1):
        print(f"  {i:>2} {c['ticker']:14s} ExDiv={c['next_exdiv']:>10s} "
              f"ret={c['avg_ret']:+5.2f}%  shrp={c['sharpe']:+5.1f}  "
              f"yld={c['yield_pct']:4.1f}%  score={c['score']:5.1f}")
else:
    print("  (Bugun short entry penceresi acik hisse yok)")

# ── HOLDING (icerideyiz) ──
print()
print(f"  HOLDING - Zaten Pozisyon Acik Olmasi Gereken (entry gecmis, exit gelecek)")
print(f"  " + "-" * 85)
if holding_longs:
    for i, c in enumerate(holding_longs[:10], 1):
        days_in = abs(c['entry_in_days'])
        days_to_exit = c['exit_in_days']
        print(f"  {i:>2} {c['ticker']:14s} {c['strategy']:16s} ExDiv={c['next_exdiv']}  "
              f"{days_in}d once girilmeli | exit {days_to_exit}d sonra  "
              f"ret={c['avg_ret']:+5.2f}%  shrp={c['sharpe']:+5.1f}")
else:
    print("  (Holding yok)")

# ── YAKLASAN ──
print()
print(f"  BU HAFTA YAKLASAN LONG FIRSATLARI (7 gun icerisinde entry)")
print(f"  " + "-" * 85)
print(f"  {'#':>2} {'Ticker':14s} {'Strateji':16s} {'ExDiv':>10s} {'Entry':>8s} {'Ent':>4s} "
      f"{'Ret%':>6s} {'Win':>5s} {'Shrp':>6s} {'Score':>6s}")
print(f"  " + "-" * 85)
if upcoming_longs:
    for i, c in enumerate(upcoming_longs[:10], 1):
        entry_date = (TODAY + timedelta(days=c['entry_in_days'])).strftime('%m/%d')
        print(f"  {i:>2} {c['ticker']:14s} {c['strategy']:16s} {c['next_exdiv']:>10s} "
              f"{entry_date:>8s} {c['entry_in_days']:+3d}d "
              f"{c['avg_ret']:+5.2f}% {c['win_rate']:4.0%} {c['sharpe']:+5.1f} {c['score']:5.1f}")
else:
    print("  (Bu hafta yaklasan long yok)")

print()
print(f"  YAKLASAN SHORT FIRSATLARI (14 gun icerisinde exdiv)")
print(f"  " + "-" * 85)
if upcoming_shorts:
    for i, c in enumerate(upcoming_shorts[:10], 1):
        print(f"  {i:>2} {c['ticker']:14s} ExDiv={c['next_exdiv']:>10s}  {c['days_to_exdiv']:+3d}d  "
              f"ret={c['avg_ret']:+5.2f}%  shrp={c['sharpe']:+5.1f}  score={c['score']:5.1f}")
else:
    print("  (Yaklasan short yok)")

# ── GENEL ISTATISTIK ──
print()
print("=" * 90)
print(f"  OZET")
print(f"  Toplam hisse: {len(sdf)}")
print(f"  Long aday: {len(long_candidates)} | Short aday: {len(short_candidates)}")
print(f"  Bugun entry acik: {len(active_longs)} long, {len(active_shorts)} short")
print(f"  Holding: {len(holding_longs)} long")
print(f"  Bu hafta yaklasan: {len(upcoming_longs)} long, {len(upcoming_shorts)} short")
print("=" * 90)
