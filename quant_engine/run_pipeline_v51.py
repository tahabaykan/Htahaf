"""
Pipeline v5.1 - janalldata.csv BAZ EX-DIV ile Pattern Analiz
=============================================================
Adim 1: janalldata.csv'den BAZ tarih al
Adim 2: 3'er ay ekleyerek TUM ex-div tarihlerini projekte et  
        (kayma yok, her zaman baz gunden)
Adim 3: Bu tarihlerle pattern hesapla (compute_excess_patterns)
Adim 4: Export
"""
import sys, os, time, calendar
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.agent.exdiv_pipeline import (
    load_stock_df, get_all_tickers, load_div_info,
    compute_excess_patterns, export_results, print_top_results,
    OUTPUT_DIR
)

STOCKTRACKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
if not os.path.exists(os.path.join(STOCKTRACKER, 'janalldata.csv')):
    STOCKTRACKER = r'c:\StockTracker'

DRIFT_TOLERANCE = 4
TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# =====================================================================
# ADIM 1: janalldata.csv BAZ EX-DIV YUKLE
# =====================================================================

def load_base_exdiv():
    """janalldata.csv + ekheld fallback ile BAZ ex-div tarihlerini yukle."""
    base_map = {}  # ticker -> base_dt
    
    # 1) janalldata.csv
    jp = os.path.join(STOCKTRACKER, 'janalldata.csv')
    if os.path.exists(jp):
        jdf = pd.read_csv(jp, encoding='latin-1')
        for _, row in jdf.iterrows():
            tk = str(row.get('PREF IBKR', '')).strip()
            exd = row.get('EX-DIV DATE', '')
            if tk and pd.notna(exd) and str(exd).strip():
                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y']:
                    try:
                        base_map[tk] = pd.to_datetime(str(exd).strip(), format=fmt)
                        break
                    except:
                        pass
                if tk not in base_map:
                    try:
                        base_map[tk] = pd.to_datetime(str(exd).strip())
                    except:
                        pass
    
    # 2) ekheld fallback
    ek_files = [
        'ekheldkuponlu.csv', 'ekheldff.csv', 'ekheldnff.csv',
        'ekheldcommonsuz.csv', 'ekheldflr.csv', 'ekheldsolidbig.csv',
        'ekheldbesmaturlu.csv', 'ekheldtitrekhc.csv',
        'ekheldkuponlukreciliz.csv', 'ekheldkuponlukreorta.csv',
        'ekheldgarabetaltiyedi.csv', 'ekheldotelremorta.csv',
        'ekhelddeznff.csv', 'ekheldcilizyeniyedi.csv',
    ]
    for ef in ek_files:
        fp = os.path.join(STOCKTRACKER, ef)
        if os.path.exists(fp):
            try:
                edf = pd.read_csv(fp, encoding='latin-1')
                exdcol = 'EX-DIV DATE'
                if exdcol not in edf.columns:
                    for c in edf.columns:
                        if 'ex' in c.lower() and 'div' in c.lower():
                            exdcol = c; break
                if exdcol in edf.columns:
                    for _, row in edf.iterrows():
                        tk = str(row.get('PREF IBKR', '')).strip()
                        if tk and tk not in base_map:
                            exd = row.get(exdcol, '')
                            if pd.notna(exd) and str(exd).strip():
                                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y']:
                                    try:
                                        base_map[tk] = pd.to_datetime(str(exd).strip(), format=fmt)
                                        break
                                    except:
                                        pass
            except:
                pass
    
    return base_map


# =====================================================================
# ADIM 2: BAZ tarihten 3'er ay ekleyerek TUM ex-div tarihlerini bul
# =====================================================================

def project_all_exdivs(base_dt, data_start, data_end):
    """
    BAZ tarihten 3'er ay ekleyerek veri araligi icerisindeki
    TUM ex-div tarihlerini uret.
    
    Kural: Her zaman BAZ gunden hesapla. ASLA kayma yok.
    """
    base_day = base_dt.day
    base_month = base_dt.month
    base_year = base_dt.year
    
    all_dates = []
    
    # Geriye git (-20 ceyrek) + ileriye git (+20 ceyrek)
    for n in range(-20, 25):
        if n == 0:
            # Baz tarihin kendisi
            all_dates.append(base_dt)
            continue
            
        target_month = base_month + 3 * n
        target_year = base_year + (target_month - 1) // 12
        target_month = ((target_month - 1) % 12) + 1
        
        max_d = calendar.monthrange(target_year, target_month)[1]
        actual_day = min(base_day, max_d)
        
        try:
            projected = pd.Timestamp(target_year, target_month, actual_day)
        except:
            continue
        
        # Veri araligi icerisinde mi? (biraz toleransla)
        if projected >= data_start - pd.Timedelta(days=30) and \
           projected <= data_end + pd.Timedelta(days=30):
            all_dates.append(projected)
    
    all_dates.sort()
    return all_dates


def custom_export(all_data):
    """Kendi export - export_results calismazsa fallback."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    rows = []
    for tk, d in all_data.items():
        det = d['detection']
        pat = d['patterns']
        pi = d['price_info']
        
        strats = pat.get('strategies', [])
        best_long = max((s for s in strats if not s.get('is_short', False)),
                        key=lambda s: s.get('sharpe', 0), default=None)
        best_short = max((s for s in strats if s.get('is_short', False)),
                         key=lambda s: s.get('sharpe', 0), default=None)
        
        row = {
            'ticker': tk,
            'div_amount': det['div_amount'],
            'yield_pct': pi['yield_pct'],
            'avg_price': pi['avg_price'],
            'n_exdivs': det['n_confirmed'],
            'quality': det.get('quality', 'HIGH'),
            'avg_cycle': det.get('avg_cycle_days', 91),
            'pattern_strength': pat.get('pattern_strength', 0),
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
                'expected_month': w.get('expected_month', ''),
                'detected_date': w.get('detected_date', ''),
                'confidence': w.get('confidence', 'HIGH'),
                'divergence_pct': w.get('divergence_pct', 0),
                'stock_gap_pct': w.get('stock_gap_pct', 0),
                'peer_median_pct': w.get('peer_median_pct', 0),
            })
    pd.DataFrame(exdiv_rows).to_csv(
        os.path.join(OUTPUT_DIR, "v5_exdiv_dates.csv"), index=False)
    
    print(f"  Saved to {OUTPUT_DIR}")
    print(f"  Summary: {sp} ({len(sdf)} stocks)")
    return sdf


# =====================================================================
# ADIM 3: PATTERN HESAPLAMA
# =====================================================================

def run_pipeline():
    t0 = time.time()
    
    print("=" * 70)
    print("  EX-DIV PIPELINE v5.1 - JANALLDATA BAZ TARIH")
    print(f"  Tarih: {TODAY.strftime('%Y-%m-%d')}")
    print("=" * 70)
    
    # Baz exdiv yukle
    print("\nADIM 1: janalldata.csv'den BAZ ex-div yukle...")
    base_map = load_base_exdiv()
    print(f"  {len(base_map)} ticker icin baz ex-div yuklendi")
    
    # Div bilgileri
    div_info = load_div_info()
    print(f"  {len(div_info)} ticker icin div bilgisi var")
    
    # Her iki kaynakta da olan tickerlar
    valid_tickers = [tk for tk in base_map if tk in div_info]
    print(f"  {len(valid_tickers)} ticker hem baz tarih hem div bilgisi var")
    
    # ADIM 2: Projeksiyon + Pattern
    print(f"\nADIM 2: {len(valid_tickers)} ticker icin exdiv projeksiyon + pattern...")
    
    all_data = {}
    ok = skip = 0
    
    for i, tk in enumerate(valid_tickers):
        base_dt = base_map[tk]
        info = div_info[tk]
        
        # Fiyat verisini yukle
        df = load_stock_df(tk)
        if df is None or len(df) < 50:
            skip += 1
            continue
        
        data_start = df['Date'].iloc[0]
        data_end = df['Date'].iloc[-1]
        
        # BAZ tarihten tum ex-div tarihlerini projekte et
        projected_dates = project_all_exdivs(base_dt, data_start, data_end)
        
        if len(projected_dates) < 3:
            skip += 1
            continue
        
        # String formatina cevir
        date_strs = [d.strftime('%Y-%m-%d') for d in projected_dates]
        
        # Pattern hesapla
        pat = compute_excess_patterns(tk, info['div_amount'], date_strs)
        if not pat:
            skip += 1
            continue
        
        avg_price = float(df['Close'].mean()) if df is not None else 0
        yield_pct = (info['div_amount'] * 4 / avg_price * 100) if avg_price > 0 else 0
        
        # Sonraki ex-div projeksiyonu
        base_day = base_dt.day
        next_proj = None
        for n in range(1, 30):
            tm = base_dt.month + 3 * n
            ty = base_dt.year + (tm - 1) // 12
            tm = ((tm - 1) % 12) + 1
            max_d = calendar.monthrange(ty, tm)[1]
            ad = min(base_day, max_d)
            p = pd.Timestamp(ty, tm, ad)
            if p + timedelta(days=DRIFT_TOLERANCE) >= TODAY:
                next_proj = p
                break
        
        # Detection-uyumlu yapida kaydet (export_results uyumlu)
        # avg_cycle_days hesapla
        if len(projected_dates) >= 2:
            gaps = [(projected_dates[j+1] - projected_dates[j]).days for j in range(len(projected_dates)-1)]
            avg_cycle = round(np.mean(gaps), 1)
        else:
            avg_cycle = 91.0
        
        # all_windows eski format uyumu
        all_windows = []
        for dd in date_strs:
            all_windows.append({
                'expected_month': dd[:7],
                'detected_date': dd,
                'confidence': 'HIGH',
                'divergence_pct': 0,
                'stock_gap_pct': 0,
                'peer_median_pct': 0,
            })
        
        detection = {
            'ticker': tk,
            'div_amount': info['div_amount'],
            'anchor_date': base_dt.strftime('%Y-%m-%d'),
            'base_day': base_day,
            'n_confirmed': len(projected_dates),
            'n_total': len(projected_dates),
            'avg_cycle_days': avg_cycle,
            'exdiv_dates': date_strs,
            'all_windows': all_windows,
            'quality': 'HIGH',
            'method': 'janalldata_base',
            'next_projected': next_proj.strftime('%Y-%m-%d') if next_proj else None,
            'next_days_until': (next_proj - TODAY).days if next_proj else None,
        }
        
        all_data[tk] = {
            'ticker': tk,
            'detection': detection,
            'patterns': pat,
            'price_info': {
                'avg_price': round(avg_price, 2),
                'yield_pct': round(yield_pct, 1),
            },
        }
        
        ok += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(valid_tickers)} ({ok} ok, {skip} skip)")
    
    elapsed2 = time.time() - t0
    print(f"  Tamamlandi: {ok} pattern, {skip} skip ({elapsed2:.1f}s)")
    
    # ADIM 3: Export
    print(f"\nADIM 3: Export...")
    try:
        sdf = export_results(all_data)
    except Exception as e:
        print(f"  export_results hata: {e}")
        print("  Kendi export yapiliyor...")
        sdf = custom_export(all_data)
    
    # TOP 25
    try:
        print_top_results(all_data, top_n=25)
    except Exception as e:
        print(f"  print_top_results hata: {e}")
    
    elapsed = time.time() - t0
    print(f"\nToplam sure: {elapsed:.1f}s")
    
    # Detayli sonuclari dosyaya kaydet
    with open('full_pipeline_results_v51.txt', 'w', encoding='utf-8') as f:
        f.write("EX-DIV PIPELINE v5.1 - JANALLDATA BAZ TARIH\n")
        f.write(f"Total: {len(all_data)} stocks analyzed\n")
        f.write(f"Date: {TODAY.strftime('%Y-%m-%d')}\n")
        f.write(f"Time: {elapsed:.1f}s\n\n")
        
        ranked = []
        for tk, d in all_data.items():
            strats = d['patterns'].get('strategies', [])
            best = max(strats, key=lambda s: s.get('sharpe', 0), default=None)
            if best:
                ranked.append((tk, d, best))
        ranked.sort(key=lambda x: x[2]['sharpe'], reverse=True)
        
        f.write(f"{'Rank':>4s} {'Ticker':14s} {'Strategy':16s} {'Entry':>6s} {'Exit':>5s} "
                f"{'Ret%':>6s} {'Win%':>5s} {'Sharpe':>7s} {'pVal':>6s} {'n':>3s} "
                f"{'Yield':>5s} {'BasDay':>6s} {'NextExDiv':>12s}\n")
        f.write("-" * 110 + "\n")
        
        for i, (tk, d, best) in enumerate(ranked):
            det = d['detection']
            pi = d['price_info']
            sig = '***' if best['pval'] < 0.05 else '**' if best['pval'] < 0.10 else ''
            nxd = det.get('next_projected', '?')
            bd = det.get('base_day', '?')
            f.write(f"{i+1:>4d} {tk:14s} {best['name']:16s} "
                    f"d{best['entry_day']:+3d}  d{best['exit_day']:+3d} "
                    f"{best['avg_ret']:>+5.2f}% {best['win_rate']:>4.0%} "
                    f"{best['sharpe']:>+6.2f} {best['pval']:>5.3f} {best['n_trades']:>3d} "
                    f"{pi['yield_pct']:>4.1f}% {str(bd):>6s} {str(nxd):>12s} {sig}\n")
    
    print(f"Done -> full_pipeline_results_v51.txt")
    print(f"     -> output/exdiv_v5/ (CSV files)")
    return all_data

if __name__ == '__main__':
    run_pipeline()
