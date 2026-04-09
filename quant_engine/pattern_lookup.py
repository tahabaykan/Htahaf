#!/usr/bin/env python3
"""
Pattern Lookup — İnteraktif Hisse Temettü Pattern Raporu
═══════════════════════════════════════════════════════════
Kullanım: python pattern_lookup.py
  → Hisse ismi girin (ör: JSM, RF PRF, ATHS)
  → O hissenin LONG ve SHORT backtest sonuçlarını gösterir
  → Başka hisse girmek için tekrar yazın
  → Çıkmak için X
"""
import sys, os, calendar
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', buffering=1, closefd=False)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════
# VERİ YÜKLEME (tek sefer)
# ═══════════════════════════════════════════════════════════

STOCKTRACKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
if not os.path.exists(os.path.join(STOCKTRACKER, 'janalldata.csv')):
    STOCKTRACKER = r'c:\StockTracker'

PIPELINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output', 'exdiv_v5')
DRIFT_TOLERANCE = 4
TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def load_all():
    """Tüm verileri yükle — bir kere çalışır."""
    print("  Veriler yükleniyor...")

    # 1) v5_summary
    sp = os.path.join(PIPELINE_DIR, "v5_summary.csv")
    if not os.path.exists(sp):
        print("  ⚠ v5_summary.csv bulunamadı! Önce pipeline çalıştırın.")
        sys.exit(1)
    summary = pd.read_csv(sp)

    # 2) Baz ex-div tarihleri
    base_exdiv_map = {}
    janall_path = os.path.join(STOCKTRACKER, "janalldata.csv")
    if os.path.exists(janall_path):
        jdf = pd.read_csv(janall_path, encoding='latin-1')
        for _, row in jdf.iterrows():
            tk = str(row.get('PREF IBKR', '')).strip()
            exd = row.get('EX-DIV DATE', '')
            if tk and pd.notna(exd) and str(exd).strip():
                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y']:
                    try:
                        base_exdiv_map[tk] = pd.to_datetime(str(exd).strip(), format=fmt)
                        break
                    except Exception:
                        pass
                if tk not in base_exdiv_map:
                    try:
                        base_exdiv_map[tk] = pd.to_datetime(str(exd).strip())
                    except Exception:
                        pass

    # ekheld fallback
    for ef in os.listdir(STOCKTRACKER):
        if ef.startswith('ekheld') and ef.endswith('.csv') and 'backup' not in ef and 'lowest' not in ef:
            fp = os.path.join(STOCKTRACKER, ef)
            try:
                edf = pd.read_csv(fp, encoding='utf-8-sig')
                exdiv_col = tk_col = None
                for c in edf.columns:
                    if 'ex' in c.lower() and 'div' in c.lower():
                        exdiv_col = c
                    if 'pref' in c.lower() and 'ibkr' in c.lower():
                        tk_col = c
                if exdiv_col and tk_col:
                    for _, row in edf.iterrows():
                        tk = str(row.get(tk_col, '')).strip()
                        if tk and tk != 'nan' and tk not in base_exdiv_map:
                            exd = row.get(exdiv_col, '')
                            if pd.notna(exd) and str(exd).strip():
                                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y']:
                                    try:
                                        base_exdiv_map[tk] = pd.to_datetime(str(exd).strip(), format=fmt)
                                        break
                                    except Exception:
                                        pass
            except Exception:
                pass

    # 3) Held tickers
    held_tickers = set()
    for ef in os.listdir(STOCKTRACKER):
        if ef.startswith('ekheld') and ef.endswith('.csv') and 'backup' not in ef and 'lowest' not in ef:
            fp = os.path.join(STOCKTRACKER, ef)
            try:
                edf = pd.read_csv(fp, encoding='utf-8-sig')
                for c in edf.columns:
                    if 'pref' in c.lower() and 'ibkr' in c.lower():
                        vals = edf[c].dropna().astype(str).str.strip()
                        held_tickers.update(v for v in vals if v and v != 'nan')
                        break
            except Exception:
                pass

    # 4) Tüm ticker listesi (summary + base_exdiv)
    all_tickers = sorted(set(summary['ticker'].tolist()) | set(base_exdiv_map.keys()))

    # 5) Div info
    div_info = {}
    if os.path.exists(janall_path):
        jdf = pd.read_csv(janall_path, encoding='latin-1')
        for _, row in jdf.iterrows():
            tk = str(row.get('PREF IBKR', '')).strip()
            da = row.get('DIV AMOUNT', 0)
            if tk and pd.notna(da) and float(da) > 0:
                div_info[tk] = float(da)
    # ek CSV'lerden de
    for ef in os.listdir(STOCKTRACKER):
        if ef.startswith('ek') and ef.endswith('.csv') and 'curdata' not in ef and 'backup' not in ef and 'lowest' not in ef:
            fp = os.path.join(STOCKTRACKER, ef)
            try:
                edf = pd.read_csv(fp, encoding='utf-8-sig')
                tk_col = da_col = None
                for c in edf.columns:
                    if 'pref' in c.lower() and 'ibkr' in c.lower():
                        tk_col = c
                    if 'div' in c.lower() and 'amount' in c.lower():
                        da_col = c
                if tk_col and da_col:
                    for _, row in edf.iterrows():
                        tk = str(row.get(tk_col, '')).strip()
                        da = row.get(da_col, 0)
                        if tk and tk != 'nan' and tk not in div_info and pd.notna(da) and float(da) > 0:
                            div_info[tk] = float(da)
            except Exception:
                pass

    print(f"  ✅ {len(summary)} hisse (v5_summary), {len(base_exdiv_map)} baz ex-div,")
    print(f"     {len(held_tickers)} held ticker, {len(div_info)} div bilgisi")
    print(f"     Toplam aranabilir: {len(all_tickers)} hisse")

    return summary, base_exdiv_map, held_tickers, all_tickers, div_info


def project_all_exdivs(base_dt, data_start, data_end):
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
        except Exception:
            continue
        if projected >= data_start - pd.Timedelta(days=30) and projected <= data_end + pd.Timedelta(days=30):
            all_dates.append(projected)
    all_dates.sort()
    return all_dates


def find_next_exdiv(tk, base_exdiv_map):
    """Bir sonraki ex-div tarihini projekte et."""
    if tk not in base_exdiv_map:
        return None, None
    base_dt = base_exdiv_map[tk]
    base_day = base_dt.day
    for n in range(1, 30):
        tm = base_dt.month + 3 * n
        ty = base_dt.year + (tm - 1) // 12
        tm = ((tm - 1) % 12) + 1
        max_d = calendar.monthrange(ty, tm)[1]
        ad = min(base_day, max_d)
        p = pd.Timestamp(ty, tm, ad)
        if p + timedelta(days=DRIFT_TOLERANCE) >= TODAY:
            return p, (p - TODAY).days
    return None, None


def load_price_data(ticker):
    """Hissenin fiyat verisini yükle."""
    safe = ticker.replace(" ", "_")
    fpath = os.path.join(STOCKTRACKER, "UTALLDATA", f"{safe}22exdata.csv")
    if not os.path.exists(fpath):
        return None
    try:
        df = pd.read_csv(fpath)
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    except Exception:
        return None


def calc_cycle_returns(df, exdiv_dates, entry_off, exit_off, div_amt, is_short=False):
    """Her cycle'daki gerçek fiyat değişimlerini hesapla."""
    close = df['Close'].values
    results = []

    for ci, exdiv_dt in enumerate(exdiv_dates, 1):
        diffs = abs(df['Date'] - exdiv_dt)
        closest_idx = diffs.idxmin()
        if abs((df.loc[closest_idx, 'Date'] - exdiv_dt).days) > 5:
            continue

        ex_idx = closest_idx
        entry_idx = ex_idx + entry_off
        exit_idx = ex_idx + exit_off

        if entry_idx < 0 or exit_idx < 0 or entry_idx >= len(df) or exit_idx >= len(df):
            continue

        entry_price = df.loc[entry_idx, 'Close']
        exit_price = df.loc[exit_idx, 'Close']
        entry_date = df.loc[entry_idx, 'Date']
        exit_date = df.loc[exit_idx, 'Date']
        actual_exdiv = df.loc[ex_idx, 'Date']

        if entry_price <= 0 or np.isnan(entry_price) or np.isnan(exit_price):
            continue

        div_in_window = entry_idx < ex_idx <= exit_idx

        if is_short:
            if div_in_window:
                ret = (entry_price - exit_price - div_amt) / entry_price * 100
            else:
                ret = (entry_price - exit_price) / entry_price * 100
            div_included = -div_amt if div_in_window else 0
        else:
            if div_in_window:
                ret = (exit_price + div_amt - entry_price) / entry_price * 100
            else:
                ret = (exit_price - entry_price) / entry_price * 100
            div_included = div_amt if div_in_window else 0

        results.append({
            'cycle': ci,
            'exdiv_date': actual_exdiv,
            'entry_date': entry_date,
            'exit_date': exit_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'div_included': div_included,
            'ret': ret,
            'win': ret > 0,
        })

    return results


def print_strategy_report(label, direction, strat_name, entry_off, exit_off, 
                          is_short, results, div_amt, sharpe, pval, win_rate_v5):
    """Bir strateji için detaylı rapor yazdır."""
    if not results:
        print(f"\n  ⚠ {label}: Yeterli cycle verisi yok!")
        return

    arr = np.array([r['ret'] for r in results])

    print()
    print(f"  ┌─ {label} ─────────────────────────────────────────────────────────────────────")
    print(f"  │ Strateji: {strat_name}  (entry=d{entry_off:+d}, exit=d{exit_off:+d})")
    print(f"  │ Sharpe: {sharpe:.1f}  |  p-value: {pval:.4f}  |  Win Rate (v5): {win_rate_v5:.0%}")
    print(f"  │")
    print(f"  │ {'Cycle':>5s}  {'Ex-Div Tarihi':>13s}  {'Entry Tarihi':>13s}  "
          f"{'Exit Tarihi':>13s}  {'Entry$':>8s}  {'Exit$':>8s}  {'Div$':>7s}  "
          f"{'Return%':>8s}  {'Sonuç':>6s}")
    print(f"  │ {'─' * 95}")

    for r in results:
        div_str = f"${r['div_included']:.3f}" if r['div_included'] else "   —  "
        result = "✅ WIN" if r['win'] else "❌ LOSS"
        print(f"  │ {r['cycle']:>5d}  {r['exdiv_date'].strftime('%Y-%m-%d'):>13s}  "
              f"{r['entry_date'].strftime('%Y-%m-%d'):>13s}  {r['exit_date'].strftime('%Y-%m-%d'):>13s}  "
              f"${r['entry_price']:>7.2f}  ${r['exit_price']:>7.2f}  "
              f"{div_str:>7s}  {r['ret']:>+7.2f}%  {result}")

    print(f"  │ {'─' * 95}")
    wins = sum(1 for r in results if r['win'])
    print(f"  │ TOPLAM  {len(results):>3d} cycle  "
          f"Ort: {np.mean(arr):+.2f}%  Std: {np.std(arr):.2f}%  "
          f"Win: {wins}/{len(results)} ({wins/len(results):.0%})  "
          f"Min: {arr.min():+.2f}%  Max: {arr.max():+.2f}%")

    # Neden?
    print(f"  │")
    wr = wins / len(results)
    avg = np.mean(arr)
    if not is_short:
        print(f"  │ 📊 NEDEN BUY?")
        print(f"  │    → Son {len(results)} ex-div cycle'ında, d{entry_off:+d}'de alıp d{exit_off:+d}'de sattığında")
        print(f"  │      %{wr*100:.0f} oranında para kazandırmış (ortalama {avg:+.2f}%)")
        if div_amt > 0 and entry_off < 0 and exit_off >= 0:
            print(f"  │    → Temettü dahil: her cycle'da ${div_amt:.3f} temettü gelir")
        if wr >= 0.8:
            print(f"  │    → ⭐ Güçlü pattern: {len(results)} cycle'ın {wins}'inde pozitif dönüş")
    else:
        print(f"  │ 📊 NEDEN SHORT?")
        print(f"  │    → Son {len(results)} ex-div cycle'ında, exdiv {'günü' if entry_off==0 else f'd{entry_off:+d}'} "
              f"short açıp {exit_off} gün sonra cover'ında")
        print(f"  │    → %{wr*100:.0f} oranında para kazandırmış (ortalama {avg:+.2f}%)")
        print(f"  │    → Ex-div sonrası fiyat düşüşü + washout etkisi short'a avantaj sağlıyor")
        if wr >= 0.8:
            print(f"  │    → ⭐ Güçlü pattern: {len(results)} cycle'ın {wins}'inde pozitif dönüş")

    print(f"  └{'─' * 90}")


def lookup_ticker(tk, summary, base_exdiv_map, held_tickers, div_info):
    """Tek bir hisse için tam pattern raporu."""

    # Held durumu
    is_held = tk in held_tickers
    h_tag = "HELD" if is_held else "NOT-HELD"

    print()
    print("═" * 100)
    print(f"  📊  {tk}  [{h_tag}]")
    print("═" * 100)

    # Summary bilgisi
    row = summary[summary['ticker'] == tk]
    has_summary = len(row) > 0

    # Div amount
    div_amt = div_info.get(tk, 0)

    # Fiyat verisi
    df = load_price_data(tk)
    if df is None:
        print(f"  ⚠ Fiyat verisi bulunamadı! (UTALLDATA/{tk.replace(' ','_')}22exdata.csv)")
        return

    avg_price = float(df['Close'].mean())
    yield_pct = (div_amt * 4 / avg_price * 100) if avg_price > 0 and div_amt > 0 else 0

    print(f"  Temettü: ${div_amt:.4f}/çeyrek  |  Yield: {yield_pct:.1f}%  |  Ort. Fiy: ${avg_price:.2f}")
    print(f"  Fiyat Verisi: {df['Date'].iloc[0].strftime('%Y-%m-%d')} → {df['Date'].iloc[-1].strftime('%Y-%m-%d')} ({len(df)} gün)")

    # Ex-div tarihleri
    if tk not in base_exdiv_map:
        print(f"  ⚠ Baz ex-div tarihi bulunamadı!")
        print(f"     (janalldata.csv veya ekheld CSV'lerinde {tk} yok)")
        return

    base_dt = base_exdiv_map[tk]
    data_start = df['Date'].iloc[0]
    data_end = df['Date'].iloc[-1]
    exdiv_dates = project_all_exdivs(base_dt, data_start, data_end)

    print(f"  Baz Ex-Div: {base_dt.strftime('%Y-%m-%d')} (gün={base_dt.day})")
    print(f"  Projekte Cycle: {len(exdiv_dates)}")

    # Sonraki ex-div
    next_exdiv, days_until = find_next_exdiv(tk, base_exdiv_map)
    if next_exdiv:
        print(f"  Sonraki Ex-Div: {next_exdiv.strftime('%Y-%m-%d')} ({days_until} gün sonra)")

    # ─── v5_summary bilgileri ───
    if has_summary:
        r = row.iloc[0]
        print(f"\n  ─── v5 Pipeline Sonuçları ───")
        print(f"  Pattern Strength: {r.get('pattern_strength', 0):.1f}%  |  n_exdivs: {r.get('n_exdivs', 0)}")

        # ── BEST LONG ──
        if pd.notna(r.get('best_long_sharpe')) and r['best_long_sharpe'] > 0:
            entry_off = int(r['best_long_entry']) if pd.notna(r.get('best_long_entry')) else -5
            exit_off = int(r['best_long_exit']) if pd.notna(r.get('best_long_exit')) else 0
            strat_name = str(r.get('best_long_name', '?'))
            sharpe = float(r.get('best_long_sharpe', 0))
            pval = float(r.get('best_long_pval', 1))
            wr_v5 = float(r.get('best_long_win', 0))

            results = calc_cycle_returns(df, exdiv_dates, entry_off, exit_off, div_amt, is_short=False)
            print_strategy_report(
                f"BEST LONG — {strat_name}", "LONG", strat_name,
                entry_off, exit_off, False, results, div_amt, sharpe, pval, wr_v5
            )
        else:
            print(f"\n  ⚠ LONG: İstatistiksel olarak anlamlı long sinyali yok (sharpe yetersiz)")

        # ── BEST SHORT ──
        if pd.notna(r.get('best_short_sharpe')) and r['best_short_sharpe'] > 0:
            entry_off_s = int(r.get('best_short_entry', 0)) if pd.notna(r.get('best_short_entry')) else 0
            exit_off_s = int(r.get('best_short_exit', 5)) if pd.notna(r.get('best_short_exit')) else 5
            strat_name_s = str(r.get('best_short_name', 'WASHOUT_SHORT'))
            sharpe_s = float(r.get('best_short_sharpe', 0))
            pval_s = float(r.get('best_short_pval', 1))
            wr_s = float(r.get('best_short_win', 0))

            results_s = calc_cycle_returns(df, exdiv_dates, entry_off_s, exit_off_s, div_amt, is_short=True)
            print_strategy_report(
                f"BEST SHORT — {strat_name_s}", "SHORT", strat_name_s,
                entry_off_s, exit_off_s, True, results_s, div_amt, sharpe_s, pval_s, wr_s
            )
        else:
            print(f"\n  ⚠ SHORT: İstatistiksel olarak anlamlı short sinyali yok (sharpe yetersiz)")

    else:
        # v5_summary'de yok ama yine de tüm standart stratejileri test et
        print(f"\n  ⚠ v5_summary'de bu hisse yok — standart stratejiler test ediliyor...")

        strat_configs = [
            ('CAPTURE_PRE',   -7, -1, False),
            ('CAPTURE_HOLD',  -5,  0, False),
            ('DIV_HOLD',      -2,  2, False),
            ('QUICK_FLIP',    -3,  3, False),
            ('RECOVERY',       0, 10, False),
            ('RECOVERY_LATE',  3, 15, False),
            ('FULL_CYCLE',   -10, 20, False),
            ('WASHOUT_SHORT',  0,  5, True),
        ]

        best_long = None
        best_short = None

        for name, entry, exit_, is_short in strat_configs:
            results = calc_cycle_returns(df, exdiv_dates, entry, exit_, div_amt, is_short)
            if len(results) < 3:
                continue
            arr = np.array([r['ret'] for r in results])
            avg = np.mean(arr)
            std = np.std(arr, ddof=1) if len(arr) > 1 else 0.001
            wr = (arr > 0).mean()
            sharpe = avg / std * np.sqrt(4) if std > 0 else 0

            item = (name, entry, exit_, is_short, results, sharpe, wr)

            if not is_short:
                if best_long is None or sharpe > best_long[5]:
                    best_long = item
            else:
                if best_short is None or sharpe > best_short[5]:
                    best_short = item

        if best_long:
            name, entry, exit_, _, results, sharpe, wr = best_long
            print_strategy_report(
                f"BEST LONG — {name}", "LONG", name,
                entry, exit_, False, results, div_amt, sharpe, 0, wr
            )
        else:
            print(f"\n  ⚠ LONG: Hiçbir long strateji anlamlı sonuç vermedi")

        if best_short:
            name, entry, exit_, _, results, sharpe, wr = best_short
            print_strategy_report(
                f"BEST SHORT — {name}", "SHORT", name,
                entry, exit_, True, results, div_amt, sharpe, 0, wr
            )
        else:
            print(f"\n  ⚠ SHORT: Hiçbir short strateji anlamlı sonuç vermedi")

    print()


def fuzzy_search(query, all_tickers, max_results=10):
    """Yaklaşık eşleşme — giriş yanlışsa öneriler sun."""
    q = query.upper().strip()
    # Tam eşleşme
    if q in all_tickers:
        return [q]
    # Başlangıç eşleşmesi
    starts = [t for t in all_tickers if t.startswith(q)]
    if starts:
        return starts[:max_results]
    # İçerik eşleşmesi
    contains = [t for t in all_tickers if q in t]
    if contains:
        return contains[:max_results]
    return []


# ═══════════════════════════════════════════════════════════
# ANA DÖNGÜ
# ═══════════════════════════════════════════════════════════

def main():
    print()
    print("═" * 70)
    print("  📊 TEMETTÜ PATTERN LOOKUP — İnteraktif Rapor")
    print("═" * 70)
    print()

    summary, base_exdiv_map, held_tickers, all_tickers, div_info = load_all()

    print()
    print("─" * 70)
    print("  Hisse ismi girin (ör: JSM, RF PRF, ATHS)")
    print("  Çıkmak için X yazın")
    print("─" * 70)

    while True:
        print()
        try:
            inp = input("  🔍 Hisse: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not inp:
            continue

        if inp.upper() == 'X':
            print("\n  👋 Çıkış yapılıyor...")
            break

        # Ara
        matches = fuzzy_search(inp, all_tickers)

        if len(matches) == 0:
            print(f"  ⚠ '{inp}' bulunamadı!")
            # Benzer olanları göster
            q = inp.upper()
            similar = [t for t in all_tickers if any(w in t for w in q.split())][:8]
            if similar:
                print(f"     Benzer: {', '.join(similar)}")
            continue

        if len(matches) == 1:
            tk = matches[0]
        else:
            if matches[0] == inp.upper():
                tk = matches[0]
            else:
                print(f"  Birden fazla eşleşme: {', '.join(matches)}")
                print(f"  Tam ismi yazın.")
                continue

        lookup_ticker(tk, summary, base_exdiv_map, held_tickers, div_info)

        print("─" * 70)
        print("  Başka hisse girmek için yazın, çıkmak için X")
        print("─" * 70)


if __name__ == '__main__':
    main()
