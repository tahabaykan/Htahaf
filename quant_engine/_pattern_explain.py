#!/usr/bin/env python3
"""
Temettü Pattern Açıklama Raporu
================================
Seçilen her hisse için:
  - Önceki cycle'lardaki gerçek fiyat hareketleri (tarih + % değişim)
  - Neden bu entry/exit öneriliyor
  - Backtest kanıtları
  
Çıktı: _pattern_explain.txt
"""
import sys, os, calendar
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from run_30day_plan import load_data, build_plan, find_next_exdiv, DRIFT_TOLERANCE
from app.agent.exdiv_pipeline import load_stock_df, load_div_info

STOCKTRACKER = os.path.join(os.path.dirname(os.path.abspath('.')))
if not os.path.exists(os.path.join(STOCKTRACKER, 'janalldata.csv')):
    STOCKTRACKER = r'c:\StockTracker'

out = open('_pattern_explain.txt', 'w', encoding='utf-8')
def p(s=""): out.write(s + "\n")

# ═══════════ Veri Yükle ═══════════
summary, base_exdiv_map, held_tickers = load_data()
div_info = load_div_info()

# Plan oluştur (50/50/50/50)
plan = build_plan(summary, base_exdiv_map, 50, 50, 50, 50, held_tickers)
selected = plan['selected_longs'] + plan['selected_shorts']

p("═" * 100)
p(f"  TEMETTÜ PATTERN DETAYLİ AÇIKLAMA RAPORU — {datetime.now().strftime('%Y-%m-%d')}")
p(f"  {len(plan['selected_longs'])} Long + {len(plan['selected_shorts'])} Short = {len(selected)} hisse")
p("═" * 100)


def project_all_exdivs_from_base(base_dt, data_start, data_end):
    """BAZ tarihten 3'er ay ekleyerek tüm ex-div tarihlerini üret."""
    base_day = base_dt.day
    base_month = base_dt.month
    base_year = base_dt.year
    all_dates = []
    for n in range(-20, 25):
        if n == 0:
            all_dates.append(base_dt)
            continue
        tm = base_month + 3 * n
        ty = base_year + (tm - 1) // 12
        tm = ((tm - 1) % 12) + 1
        max_d = calendar.monthrange(ty, tm)[1]
        actual_day = min(base_day, max_d)
        try:
            projected = pd.Timestamp(ty, tm, actual_day)
        except:
            continue
        if projected >= data_start - pd.Timedelta(days=30) and projected <= data_end + pd.Timedelta(days=30):
            all_dates.append(projected)
    all_dates.sort()
    return all_dates


for rank, item in enumerate(selected, 1):
    tk = item['ticker']
    direction = item['direction']
    is_held = item.get('is_held', False)
    
    p()
    p("─" * 100)
    h_tag = "HELD" if is_held else "NOT-HELD"
    p(f"  #{rank}  {tk}  [{direction}]  [{h_tag}]")
    p("─" * 100)
    
    # Summary bilgileri
    row = summary[summary['ticker'] == tk]
    if len(row) == 0:
        p("  v5_summary'de bulunamadı!")
        continue
    row = row.iloc[0]
    
    div_amt = row.get('div_amount', 0)
    yield_pct = row.get('yield_pct', 0)
    avg_price = row.get('avg_price', 0)
    
    p(f"  Temettü: ${div_amt:.4f}/çeyrek  |  Yield: {yield_pct:.1f}%  |  Ort. Fiy: ${avg_price:.2f}")
    p(f"  Önerilen: entry={item['entry_date']}  exit={item['exit_date']}  exdiv={item['exdiv_date']}")
    p(f"  Beklenen Return: {item['expected_return']:+.2f}%  |  Sharpe: {item['sharpe']:.1f}")
    if direction == 'LONG':
        p(f"  Win Rate: {item.get('win_rate', 0):.0%}  |  p-value: {item.get('p_value', 1):.4f}")
    
    # Strateji bilgisi
    if direction == 'LONG':
        strat_name = row.get('best_long_name', '?')
        entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
        exit_off = int(row['best_long_exit']) if pd.notna(row.get('best_long_exit')) else 0
    else:
        strat_name = row.get('best_short_name', '?')
        entry_off = 0
        exit_off = 5
    
    p(f"  Strateji: {strat_name}  (entry=d{entry_off:+d}, exit=d{exit_off:+d})")
    p()
    
    # Fiyat verisini yükle
    df = load_stock_df(tk)
    if df is None or len(df) < 50:
        p("  ⚠ Fiyat verisi bulunamadı!")
        continue
    
    # Ex-div tarihlerini bul
    if tk in base_exdiv_map:
        base_dt = base_exdiv_map[tk]
        data_start = df['Date'].iloc[0]
        data_end = df['Date'].iloc[-1]
        exdiv_dates = project_all_exdivs_from_base(base_dt, data_start, data_end)
    else:
        p("  ⚠ Baz ex-div tarihi bulunamadı!")
        continue
    
    p(f"  Baz Ex-Div: {base_dt.strftime('%Y-%m-%d')} (gün={base_dt.day})")
    p(f"  Toplam Cycle Sayısı: {len(exdiv_dates)} (veri aralığı: {data_start.strftime('%Y-%m-%d')} → {data_end.strftime('%Y-%m-%d')})")
    p()
    
    # Her cycle'daki gerçek fiyat hareketlerini göster
    p(f"  {'Cycle':>5s}  {'Ex-Div Tarihi':>13s}  {'Entry Tarihi':>13s}  {'Exit Tarihi':>13s}  "
      f"{'Entry$':>8s}  {'Exit$':>8s}  {'Div$':>7s}  {'Return%':>8s}  {'Sonuç':>6s}")
    p("  " + "─" * 95)
    
    returns = []
    for ci, exdiv_dt in enumerate(exdiv_dates, 1):
        # Ex-div'e en yakın veri gününü bul
        diffs = abs(df['Date'] - exdiv_dt)
        closest_idx = diffs.idxmin()
        if abs((df.loc[closest_idx, 'Date'] - exdiv_dt).days) > 5:
            continue
        
        ex_idx = closest_idx
        
        # Entry ve exit indekslerini hesapla
        entry_idx = ex_idx + entry_off
        exit_idx = ex_idx + exit_off
        
        if entry_idx < 0 or exit_idx < 0 or entry_idx >= len(df) or exit_idx >= len(df):
            continue
        
        entry_price = df.loc[entry_idx, 'Close']
        exit_price = df.loc[exit_idx, 'Close']
        entry_date = df.loc[entry_idx, 'Date']
        exit_date = df.loc[exit_idx, 'Date']
        actual_exdiv = df.loc[ex_idx, 'Date']
        
        if entry_price <= 0:
            continue
        
        # Return hesapla (temettü dahil/hariç)
        # Eğer exdiv entry ile exit arasındaysa, temettü dahil et
        if direction == 'LONG':
            if entry_idx < ex_idx <= exit_idx:
                ret = (exit_price + div_amt - entry_price) / entry_price * 100
            else:
                ret = (exit_price - entry_price) / entry_price * 100
            div_included = div_amt if (entry_idx < ex_idx <= exit_idx) else 0
        else:  # SHORT
            if entry_idx < ex_idx <= exit_idx:
                ret = (entry_price - exit_price - div_amt) / entry_price * 100
            else:
                ret = (entry_price - exit_price) / entry_price * 100
            div_included = -div_amt if (entry_idx < ex_idx <= exit_idx) else 0
        
        returns.append(ret)
        result = "✅ WIN" if ret > 0 else "❌ LOSS"
        
        p(f"  {ci:>5d}  {actual_exdiv.strftime('%Y-%m-%d'):>13s}  "
          f"{entry_date.strftime('%Y-%m-%d'):>13s}  {exit_date.strftime('%Y-%m-%d'):>13s}  "
          f"${entry_price:>7.2f}  ${exit_price:>7.2f}  "
          f"{'$'+f'{div_included:.3f}' if div_included else '   —  ':>7s}  "
          f"{ret:>+7.2f}%  {result}")
    
    if returns:
        arr = np.array(returns)
        p("  " + "─" * 95)
        p(f"  {'TOPLAM':>5s}  {len(returns):>3d} cycle  "
          f"Ort: {np.mean(arr):+.2f}%  "
          f"Std: {np.std(arr):.2f}%  "
          f"Win: {(arr > 0).sum()}/{len(arr)} ({(arr > 0).mean():.0%})  "
          f"Min: {arr.min():+.2f}%  Max: {arr.max():+.2f}%")
        
        # Neden bu strateji öneriliyor - açıklama
        p()
        win_rate = (arr > 0).mean()
        avg_ret = np.mean(arr) 
        
        if direction == 'LONG':
            p(f"  📊 NEDEN BUY?")
            p(f"     → Son {len(returns)} ex-div cycle'ında, d{entry_off:+d}'de alıp d{exit_off:+d}'de sattığında")
            p(f"       %{win_rate*100:.0f} oranında para kazandırmış (ortalama {avg_ret:+.2f}%)")
            if div_amt > 0 and entry_off < 0 and exit_off >= 0:
                p(f"     → Temettü dahil: her cycle'da ${div_amt:.3f} temettü gelir")
            if win_rate >= 0.8:
                p(f"     → ⭐ Çok güçlü pattern: {len(returns)} cycle'ın {int(win_rate*len(returns))}'inde pozitif dönüş")
        else:
            p(f"  📊 NEDEN SHORT?")
            p(f"     → Son {len(returns)} ex-div cycle'ında, exdiv gününde short açıp {exit_off} gün sonra cover'ında")
            p(f"       %{win_rate*100:.0f} oranında para kazandırmış (ortalama {avg_ret:+.2f}%)")
            p(f"     → Ex-div sonrası temettü düşüşü + washout etkisi short'a avantaj sağlıyor")
    else:
        p("  ⚠ Yeterli cycle verisi yok!")
    
    p()

p()
p("═" * 100)
p("  RAPOR SONU")
p("═" * 100)

out.close()
print("Done -> _pattern_explain.txt")
