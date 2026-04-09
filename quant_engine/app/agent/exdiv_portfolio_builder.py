#!/usr/bin/env python3
"""
Ex-Div Portfolio Builder — Interactive
=======================================

Run: python -m app.agent.exdiv_portfolio_builder

Adım adım input alarak optimal portföy oluşturur:
  1) Long/Short oranı (default 50/50)
  2) Long'da held tutma oranı (default %100)   → en iyi N long seçilir
  3) Short'ta held tutma oranı (default %100)   → en iyi N short seçilir

Pipeline v5 sonuçlarını kullanır:
  - output/exdiv_v5/v5_summary.csv   → stratejiler ve Sharpe
  - output/exdiv_v5/v5_exdiv_dates.csv → ex-div tarihleri

Çıktılar:
  - output/portfolio/held_long.csv
  - output/portfolio/held_short.csv
  - output/portfolio/portfolio_plan.csv
  - output/portfolio/summary.json
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# =====================================================================
# PATHS
# =====================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIPELINE_DIR = os.path.join(BASE_DIR, "output", "exdiv_v5")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "portfolio")
STOCKTRACKER_ROOT = r"C:\StockTracker"

TODAY = datetime.now().strftime('%Y-%m-%d')
PORTFOLIO_SIZE = 1_000_000  # $1M
MAX_POS_PCT = 0.03          # Max 3% per position
LOOKAHEAD_DAYS = 180        # 6 ay


# =====================================================================
# DATA LOADING
# =====================================================================

def load_pipeline_results() -> pd.DataFrame:
    """V5 pipeline sonuçlarını yükle."""
    sp = os.path.join(PIPELINE_DIR, "v5_summary.csv")
    if not os.path.exists(sp):
        print(f"  ❌ Pipeline sonuçları bulunamadı: {sp}")
        print(f"  Önce pipeline'ı çalıştır: python run_full_pipeline.py")
        sys.exit(1)
    
    df = pd.read_csv(sp)
    print(f"  ✅ Pipeline sonuçları yüklendi: {len(df)} hisse")
    return df


def load_exdiv_dates() -> Dict[str, List[str]]:
    """Her hissenin tespit edilen ex-div tarihlerini yükle."""
    ep = os.path.join(PIPELINE_DIR, "v5_exdiv_dates.csv")
    if not os.path.exists(ep):
        return {}
    
    edf = pd.read_csv(ep)
    result = {}
    for _, row in edf.iterrows():
        tk = row['ticker']
        if tk not in result:
            result[tk] = []
        if row.get('confidence', '') in ('HIGH', 'MEDIUM', 'LOW'):
            result[tk].append(row['detected_date'])
    
    return result


# =====================================================================
# INTERACTIVE INPUT
# =====================================================================

def get_user_input():
    """Kullanıcıdan adım adım input al."""
    
    print()
    print("=" * 65)
    print("  🔧 EX-DIV PORTFÖY OPTİMİZASYONU — AYARLAR")
    print("=" * 65)
    print()
    
    # Adım 1: Long/Short oranı
    print("  ADIM 1: Long / Short Oranı")
    print("  ─────────────────────────────")
    print("  Portföyün yüzde kaçı LONG, kaçı SHORT olacak?")
    print("  Örnekler: 50/50, 70/30, 30/70, 100/0")
    print()
    
    while True:
        raw = input("  Long % (default=50): ").strip()
        if not raw:
            long_pct = 50
        else:
            try:
                long_pct = int(raw)
            except ValueError:
                print("  ⚠ Sayı girin (0-100)")
                continue
        
        if 0 <= long_pct <= 100:
            short_pct = 100 - long_pct
            print(f"  → Long: {long_pct}% | Short: {short_pct}%")
            break
        else:
            print("  ⚠ 0-100 arası olmalı")
    
    print()
    
    # Adım 2: Long'da held tutma oranı
    print("  ADIM 2: Long'da Held Tutma Oranı")
    print("  ──────────────────────────────────")
    print("  Seçilen long hisselerin yüzde kaçını portföyde tutalım?")
    print("  100% = hepsini tut | 50% = en iyi yarısını tut")
    print()
    
    while True:
        raw = input("  Long held % (default=100): ").strip()
        if not raw:
            long_held_pct = 100
        else:
            try:
                long_held_pct = int(raw)
            except ValueError:
                print("  ⚠ Sayı girin (1-100)")
                continue
        
        if 1 <= long_held_pct <= 100:
            print(f"  → Long pozisyonların {long_held_pct}%'i held kalacak")
            break
        else:
            print("  ⚠ 1-100 arası olmalı")
    
    print()
    
    # Adım 3: Short'ta held tutma oranı
    print("  ADIM 3: Short'ta Held Tutma Oranı")
    print("  ──────────────────────────────────")
    print("  Seçilen short hisselerin yüzde kaçını portföyde tutalım?")
    print("  100% = hepsini tut | 50% = en iyi yarısını tut")
    print()
    
    while True:
        raw = input("  Short held % (default=100): ").strip()
        if not raw:
            short_held_pct = 100
        else:
            try:
                short_held_pct = int(raw)
            except ValueError:
                print("  ⚠ Sayı girin (1-100)")
                continue
        
        if 1 <= short_held_pct <= 100:
            print(f"  → Short pozisyonların {short_held_pct}%'i held kalacak")
            break
        else:
            print("  ⚠ 1-100 arası olmalı")
    
    print()
    
    # Adım 4: Portföy büyüklüğü
    print("  ADIM 4: Portföy Büyüklüğü")
    print("  ──────────────────────────")
    while True:
        raw = input(f"  Portföy ($, default={PORTFOLIO_SIZE:,}): ").strip()
        if not raw:
            port_size = PORTFOLIO_SIZE
        else:
            try:
                port_size = int(raw.replace(',', '').replace('$', ''))
            except ValueError:
                print("  ⚠ Geçersiz")
                continue
        if port_size > 0:
            print(f"  → Portföy: ${port_size:,}")
            break
    
    print()
    
    # Adım 5: Strictness (filtre katılığı)
    print("  ADIM 5: Filtre Katılığı")
    print("  ────────────────────────")
    print("  1 = Çok gevşek (daha fazla hisse, daha az güvenilir)")
    print("  5 = Orta        (dengeli)")
    print("  7 = Katı        (daha az hisse, daha güvenilir)")
    print("  10 = Ultra katı (sadece en iyiler)")
    print()
    
    while True:
        raw = input("  Strictness (1-10, default=5): ").strip()
        if not raw:
            strictness = 5
        else:
            try:
                strictness = int(raw)
            except ValueError:
                print("  ⚠ 1-10 arası sayı")
                continue
        if 1 <= strictness <= 10:
            break
    
    # Strictness konfigürasyonu
    configs = {
        10: (0.01, 0.70, 8, 0.50, 'Ultra katı'),
         9: (0.02, 0.65, 7, 0.30, 'Çok katı'),
         8: (0.03, 0.62, 6, 0.15, 'Katı+'),
         7: (0.05, 0.60, 5, 0.10, 'Katı'),
         6: (0.07, 0.58, 5, 0.08, 'Katı-'),
         5: (0.08, 0.55, 4, 0.05, 'Orta'),
         4: (0.10, 0.52, 4, 0.03, 'Orta-'),
         3: (0.15, 0.48, 3, 0.01, 'Gevşek'),
         2: (0.20, 0.45, 3, 0.005, 'Gevşek-'),
         1: (0.25, 0.40, 3, 0.001, 'Çok gevşek'),
    }
    max_pval, min_winrate, min_cycles, min_ret, desc = configs[strictness]
    print(f"  → {desc}: p<{max_pval}, win>{min_winrate:.0%}, cycles>={min_cycles}, ret>{min_ret}%")
    
    print()
    print("  " + "─" * 50)
    print(f"  ÖZET: {long_pct}L/{short_pct}S | LongHeld={long_held_pct}% | " 
          f"ShortHeld={short_held_pct}% | ${port_size:,} | Strict={strictness}")
    print("  " + "─" * 50)
    
    conf = input("\n  Bu ayarlarla devam edilsin mi? (E/h): ").strip().lower()
    if conf == 'h':
        print("  İptal edildi.")
        sys.exit(0)
    
    return {
        'long_pct': long_pct,
        'short_pct': short_pct,
        'long_held_pct': long_held_pct,
        'short_held_pct': short_held_pct,
        'portfolio_size': port_size,
        'strictness': strictness,
        'max_pval': max_pval,
        'min_winrate': min_winrate,
        'min_cycles': min_cycles,
        'min_return': min_ret,
    }


# =====================================================================
# PORTFOLIO BUILDING
# =====================================================================

def project_next_exdiv(last_dates: List[str], n_forward: int = 4) -> List[str]:
    """Son ex-div tarihlerinden ileriye doğru projekte et (+3 ay)."""
    if not last_dates:
        return []
    
    last = pd.to_datetime(sorted(last_dates)[-1])
    projected = []
    for i in range(1, n_forward + 1):
        pdt = last + pd.DateOffset(months=3 * i)
        projected.append(pdt.strftime('%Y-%m-%d'))
    return projected


def build_portfolio(summary_df: pd.DataFrame, exdiv_dates: Dict,
                    settings: Dict) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    """
    Optimal portföy oluştur.
    
    Returns: (long_held, short_held, all_trades, summary_stats)
    """
    today = pd.to_datetime(TODAY)
    end_dt = today + timedelta(days=LOOKAHEAD_DAYS)
    
    long_pct = settings['long_pct'] / 100
    short_pct = settings['short_pct'] / 100
    long_held_pct = settings['long_held_pct'] / 100
    short_held_pct = settings['short_held_pct'] / 100
    port_size = settings['portfolio_size']
    max_pval = settings['max_pval']
    min_winrate = settings['min_winrate']
    min_cycles = settings['min_cycles']
    min_return = settings['min_return']
    
    max_per_pos = port_size * MAX_POS_PCT
    max_long_cap = port_size * long_pct
    max_short_cap = port_size * short_pct
    
    # ===== LONG CANDIDATES =====
    long_candidates = summary_df[
        (summary_df['best_long_pval'].notna()) &
        (summary_df['best_long_pval'] < max_pval) &
        (summary_df['best_long_win'].notna()) &
        (summary_df['best_long_win'] >= min_winrate) &
        (summary_df['n_exdivs'] >= min_cycles) &
        (summary_df['best_long_ret'].notna()) &
        (summary_df['best_long_ret'] > min_return)
    ].copy()
    
    if len(long_candidates) > 0:
        long_candidates['long_score'] = (
            long_candidates['best_long_sharpe'].fillna(0) * 0.40 +
            long_candidates['best_long_win'].fillna(0) * 20 * 0.30 +
            (1 - long_candidates['best_long_pval'].fillna(1)) * 10 * 0.20 +
            long_candidates['pattern_strength'].fillna(0) / 10 * 0.10
        )
        long_candidates = long_candidates.sort_values('long_score', ascending=False)
    
    # ===== SHORT CANDIDATES =====
    # Short: WASHOUT_SHORT veya negatif RECOVERY
    short_candidates = summary_df[
        (summary_df['best_short_sharpe'].notna()) &
        (summary_df['best_short_sharpe'] > 0.5) &
        (summary_df['n_exdivs'] >= min_cycles)
    ].copy()
    
    # Ayrıca long stratejisi olmasa da, RECOVERY stratejisi negatif olanlar short'tur
    # (pipeline'da recovery negatifse, ex-div sonrası düşüyor demek)
    
    if len(short_candidates) > 0:
        short_candidates['short_score'] = (
            short_candidates['best_short_sharpe'].fillna(0) * 0.50 +
            short_candidates['best_short_ret'].fillna(0) * 5 * 0.30 +
            short_candidates['pattern_strength'].fillna(0) / 10 * 0.20
        )
        short_candidates = short_candidates.sort_values('short_score', ascending=False)
    
    # ===== TRADE PLANNING =====
    trades = []
    
    # Long trades
    max_long_positions = int(max_long_cap / max_per_pos)
    n_long_total = min(len(long_candidates), max_long_positions)
    n_long_held = max(1, int(n_long_total * long_held_pct))
    
    long_selected = long_candidates.head(n_long_total)
    long_held = long_candidates.head(n_long_held)
    
    for _, row in long_selected.iterrows():
        tk = row['ticker']
        dates = exdiv_dates.get(tk, [])
        projected = project_next_exdiv(dates, n_forward=6)
        
        entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
        exit_off = int(row['best_long_exit']) if pd.notna(row.get('best_long_exit')) else 0
        
        for proj in projected:
            pdt = pd.to_datetime(proj)
            entry_dt = pdt + timedelta(days=int(entry_off * 7/5))
            exit_dt = pdt + timedelta(days=int(exit_off * 7/5))
            
            # Weekend skip
            while entry_dt.weekday() >= 5:
                entry_dt += timedelta(days=1)
            while exit_dt.weekday() >= 5:
                exit_dt += timedelta(days=1)
            
            if exit_dt <= entry_dt:
                exit_dt = entry_dt + timedelta(days=3)
            
            if entry_dt > today and exit_dt <= end_dt:
                holding = max(1, (exit_dt - entry_dt).days)
                trades.append({
                    'ticker': tk,
                    'direction': 'LONG',
                    'entry_date': entry_dt.strftime('%Y-%m-%d'),
                    'exit_date': exit_dt.strftime('%Y-%m-%d'),
                    'exdiv_date': proj,
                    'entry_offset': entry_off,
                    'exit_offset': exit_off,
                    'strategy': row.get('best_long_name', 'LONG'),
                    'expected_return': round(float(row.get('best_long_ret', 0)), 3),
                    'win_rate': round(float(row.get('best_long_win', 0)), 3),
                    'sharpe': round(float(row.get('best_long_sharpe', 0)), 2),
                    'p_value': round(float(row.get('best_long_pval', 1)), 4),
                    'holding_days': holding,
                    'capital': max_per_pos,
                    'is_held': tk in long_held['ticker'].values,
                    'yield_pct': round(float(row.get('yield_pct', 0)), 1),
                })
    
    # Short trades
    max_short_positions = int(max_short_cap / max_per_pos) if max_short_cap > 0 else 0
    n_short_total = min(len(short_candidates), max_short_positions)
    n_short_held = max(1, int(n_short_total * short_held_pct)) if n_short_total > 0 else 0
    
    short_selected = short_candidates.head(n_short_total)
    short_held = short_candidates.head(n_short_held) if n_short_total > 0 else pd.DataFrame()
    
    for _, row in short_selected.iterrows():
        tk = row['ticker']
        dates = exdiv_dates.get(tk, [])
        projected = project_next_exdiv(dates, n_forward=6)
        
        for proj in projected:
            pdt = pd.to_datetime(proj)
            # Short: ex-div günü aç, 5-10 gün sonra kapat
            entry_dt = pdt
            exit_dt = pdt + timedelta(days=7)
            
            while entry_dt.weekday() >= 5:
                entry_dt += timedelta(days=1)
            while exit_dt.weekday() >= 5:
                exit_dt += timedelta(days=1)
            
            if entry_dt > today and exit_dt <= end_dt:
                holding = max(1, (exit_dt - entry_dt).days)
                trades.append({
                    'ticker': tk,
                    'direction': 'SHORT',
                    'entry_date': entry_dt.strftime('%Y-%m-%d'),
                    'exit_date': exit_dt.strftime('%Y-%m-%d'),
                    'exdiv_date': proj,
                    'entry_offset': 0,
                    'exit_offset': 5,
                    'strategy': row.get('best_short_name', 'SHORT'),
                    'expected_return': round(float(row.get('best_short_ret', 0)), 3),
                    'win_rate': 0.65,  # estimated
                    'sharpe': round(float(row.get('best_short_sharpe', 0)), 2),
                    'p_value': 0.05,
                    'holding_days': holding,
                    'capital': max_per_pos,
                    'is_held': tk in (short_held['ticker'].values if len(short_held) > 0 else []),
                    'yield_pct': round(float(row.get('yield_pct', 0)), 1),
                })
    
    trades_df = pd.DataFrame(trades)
    
    # Summary stats
    longs_df = trades_df[trades_df['direction'] == 'LONG'] if len(trades_df) > 0 else pd.DataFrame()
    shorts_df = trades_df[trades_df['direction'] == 'SHORT'] if len(trades_df) > 0 else pd.DataFrame()
    
    summary_stats = {
        'date': TODAY,
        'portfolio_size': port_size,
        'long_pct': settings['long_pct'],
        'short_pct': settings['short_pct'],
        'long_held_pct': settings['long_held_pct'],
        'short_held_pct': settings['short_held_pct'],
        'strictness': settings['strictness'],
        'total_long_candidates': len(long_candidates),
        'total_short_candidates': len(short_candidates),
        'selected_long': n_long_total,
        'selected_short': n_short_total,
        'held_long': n_long_held,
        'held_short': n_short_held,
        'planned_trades': len(trades_df),
        'long_trades': len(longs_df),
        'short_trades': len(shorts_df),
        'avg_long_return': round(float(longs_df['expected_return'].mean()), 3) if len(longs_df) > 0 else 0,
        'avg_short_return': round(float(shorts_df['expected_return'].mean()), 3) if len(shorts_df) > 0 else 0,
        'avg_long_sharpe': round(float(longs_df['sharpe'].mean()), 2) if len(longs_df) > 0 else 0,
        'avg_short_sharpe': round(float(shorts_df['sharpe'].mean()), 2) if len(shorts_df) > 0 else 0,
        'long_capital': round(float(max_long_cap), 0),
        'short_capital': round(float(max_short_cap), 0),
        'max_per_position': round(float(max_per_pos), 0),
    }
    
    return long_held, short_held, trades_df, summary_stats


# =====================================================================
# EXPORT & REPORTING
# =====================================================================

def export_portfolio(long_held: pd.DataFrame, short_held: pd.DataFrame,
                     trades_df: pd.DataFrame, summary: Dict, settings: Dict):
    """Sonuçları dosyalara kaydet."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # held_long.csv
    if len(long_held) > 0:
        lh = long_held[['ticker', 'div_amount', 'yield_pct', 'avg_price', 'n_exdivs',
                         'quality', 'pattern_strength', 'best_long_name', 
                         'best_long_entry', 'best_long_exit', 'best_long_ret',
                         'best_long_sharpe', 'best_long_win', 'best_long_pval']].copy()
        lh.to_csv(os.path.join(OUTPUT_DIR, "held_long.csv"), index=False)
    
    # held_short.csv
    if len(short_held) > 0:
        cols = [c for c in ['ticker', 'div_amount', 'yield_pct', 'avg_price', 'n_exdivs',
                            'quality', 'pattern_strength', 'best_short_name',
                            'best_short_ret', 'best_short_sharpe'] if c in short_held.columns]
        sh = short_held[cols].copy()
        sh.to_csv(os.path.join(OUTPUT_DIR, "held_short.csv"), index=False)
    
    # portfolio_plan.csv (tüm trade'ler)
    if len(trades_df) > 0:
        trades_df.to_csv(os.path.join(OUTPUT_DIR, "portfolio_plan.csv"), index=False)
    
    # summary.json
    with open(os.path.join(OUTPUT_DIR, "summary.json"), 'w') as f:
        json.dump(summary, f, indent=2)
    
    # settings.json
    with open(os.path.join(OUTPUT_DIR, "settings.json"), 'w') as f:
        json.dump(settings, f, indent=2)


def print_results(long_held: pd.DataFrame, short_held: pd.DataFrame,
                  trades_df: pd.DataFrame, summary: Dict):
    """Sonuçları yazdır."""
    
    print()
    print("=" * 80)
    print("  📊 PORTFÖY OPTİMİZASYONU — SONUÇLAR")
    print(f"  Tarih: {TODAY} | Sermaye: ${summary['portfolio_size']:,}")
    print(f"  Long: {summary['long_pct']}% | Short: {summary['short_pct']}%")
    print("=" * 80)
    
    # Genel özet
    print()
    print("  📈 ÖZET İSTATİSTİKLER")
    print("  ─────────────────────")
    print(f"  Long adayları:  {summary['total_long_candidates']:>4d}  →  Seçilen: {summary['selected_long']:>4d}  →  Held: {summary['held_long']:>4d}")
    print(f"  Short adayları: {summary['total_short_candidates']:>4d}  →  Seçilen: {summary['selected_short']:>4d}  →  Held: {summary['held_short']:>4d}")
    print(f"  Planlanan trade: {summary['planned_trades']}")
    print(f"  Ort. Long return:  {summary['avg_long_return']:+.3f}% (Sharpe: {summary['avg_long_sharpe']:.2f})")
    print(f"  Ort. Short return: {summary['avg_short_return']:+.3f}% (Sharpe: {summary['avg_short_sharpe']:.2f})")
    
    # HELD LONG listesi
    print()
    print(f"  📗 HELD LONG — {len(long_held)} hisse")
    print(f"  {'Ticker':14s} {'Strateji':16s} {'d_In':>5s} {'d_Out':>5s} "
          f"{'Ret%':>6s} {'Win%':>5s} {'Sharpe':>7s} {'Yield':>5s}")
    print("  " + "─" * 70)
    
    if len(long_held) > 0:
        for _, r in long_held.iterrows():
            print(f"  {r['ticker']:14s} {str(r.get('best_long_name','')):16s} "
                  f"d{int(r.get('best_long_entry',0)):+3d}  "
                  f"d{int(r.get('best_long_exit',0)):+3d}  "
                  f"{r.get('best_long_ret',0):+5.2f}% "
                  f"{r.get('best_long_win',0):4.0%} "
                  f"{r.get('best_long_sharpe',0):+6.2f} "
                  f"{r.get('yield_pct',0):4.1f}%")
    
    # HELD SHORT listesi
    print()
    print(f"  📕 HELD SHORT — {len(short_held)} hisse")
    if len(short_held) > 0:
        print(f"  {'Ticker':14s} {'Strateji':16s} {'Ret%':>6s} {'Sharpe':>7s} {'Yield':>5s}")
        print("  " + "─" * 50)
        for _, r in short_held.iterrows():
            print(f"  {r['ticker']:14s} {str(r.get('best_short_name','')):16s} "
                  f"{r.get('best_short_ret',0):+5.2f}% "
                  f"{r.get('best_short_sharpe',0):+6.2f} "
                  f"{r.get('yield_pct',0):4.1f}%")
    else:
        print("  (Short aday yok veya short oranı 0%)")
    
    # Yakın gelecek trade'leri
    if len(trades_df) > 0:
        print()
        print("  📅 YAKIN GELECEK TRADE'LER (önümüzdeki 30 gün)")
        print("  " + "─" * 75)
        
        cutoff = (pd.to_datetime(TODAY) + timedelta(days=30)).strftime('%Y-%m-%d')
        near = trades_df[trades_df['entry_date'] <= cutoff].sort_values('entry_date')
        
        if len(near) > 0:
            print(f"  {'Dir':5s} {'Ticker':14s} {'Entry':>10s} {'Exit':>10s} {'ExDiv':>10s} "
                  f"{'Ret%':>6s} {'Held':>4s}")
            for _, t in near.head(30).iterrows():
                held_mark = "✅" if t.get('is_held', False) else "  "
                print(f"  {t['direction']:5s} {t['ticker']:14s} {t['entry_date']:>10s} "
                      f"{t['exit_date']:>10s} {t['exdiv_date']:>10s} "
                      f"{t['expected_return']:+5.2f}% {held_mark}")
        else:
            print("  (Yakın gelecekte trade yok)")
    
    print()
    print("=" * 80)
    print(f"  Dosyalar: {OUTPUT_DIR}")
    print(f"    held_long.csv  ({len(long_held)} hisse)")
    print(f"    held_short.csv ({len(short_held)} hisse)")
    print(f"    portfolio_plan.csv ({len(trades_df)} trade)")
    print(f"    summary.json")
    print("=" * 80)


# =====================================================================
# MAIN
# =====================================================================

def main():
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  EX-DIV PORTFÖY BUILDER v5                         ║")
    print("║  Temettü döngüsü bazlı optimal portföy oluşturucu  ║")
    print("╚══════════════════════════════════════════════════════╝")
    
    # 1) Pipeline sonuçlarını yükle
    print()
    print("  📁 Pipeline sonuçları yükleniyor...")
    summary_df = load_pipeline_results()
    exdiv_dates = load_exdiv_dates()
    print(f"  Ex-div tarihleri: {len(exdiv_dates)} hisse")
    
    # 2) Kullanıcıdan ayarları al
    settings = get_user_input()
    
    # 3) Portföy oluştur
    print()
    print("  ⚙️ Portföy optimizasyonu çalışıyor...")
    long_held, short_held, trades_df, summary_stats = build_portfolio(
        summary_df, exdiv_dates, settings
    )
    
    # 4) Raporla
    print_results(long_held, short_held, trades_df, summary_stats)
    
    # 5) Kaydet
    export_portfolio(long_held, short_held, trades_df, summary_stats, settings)
    
    print("\n  ✅ Tamamlandı!")


if __name__ == '__main__':
    main()
