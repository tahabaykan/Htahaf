"""
═══════════════════════════════════════════════════════════════════════════════
DUAL PROCESS SİMÜLASYON — "Yarın Çalıştırsak Ne Olur?" v3.0
═══════════════════════════════════════════════════════════════════════════════

Varsayımlar:
  - bid = prev_close - $0.10
  - ask = prev_close + $0.10
  - last = prev_close
  - spread = $0.20
  - ucuzluk = (bid + spread*0.15 - prev_close) = (pc-0.10 + 0.03 - pc) = -0.07
  - pahalilik= (ask - spread*0.15 - prev_close) = (pc+0.10 - 0.03 - pc) = +0.07
  - FBTOT/SFSTOT: FORMÜLDEN HESAPLANIYOR (dosya gruplarından)

v3.0: Fbtot/SFStot/GORT direkt formülden hesaplanıyor
      + PATADD sinyalleri (v5_summary.csv + janalldata exdiv dates)

Tarih: 2026-03-02
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import os
import csv
import glob
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import pandas as pd
except ImportError:
    pd = None

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
JANALL_DIR = Path(r"C:\StockTracker\janall")
BEFDAY_DIR = Path(r"C:\StockTracker\quant_engine\befday")
NEWJANALL_DIR = Path(r"C:\StockTracker\newjanall")
EXPOSURE_CONFIG = Path(r"C:\StockTracker\quant_engine\config\exposure_thresholds_v2.json")
V5_SUMMARY = Path(r"C:\StockTracker\quant_engine\output\exdiv_v5\v5_summary.csv")
JANALLDATA = Path(r"C:\StockTracker\janalldata.csv")
FINAL_FB_LONG = JANALL_DIR / "final_fb_sfs_tumcsv_long_stocks.csv"
FINAL_FB_SHORT = JANALL_DIR / "final_fb_sfs_tumcsv_short_stocks.csv"

# ─────────────────────────────────────────────────────────────────────────────
# SİMÜLASYON PARAMETRELERİ
# ─────────────────────────────────────────────────────────────────────────────
BID_OFFSET = -0.10       # bid = prev_close - $0.10
ASK_OFFSET = +0.10       # ask = prev_close + $0.10
SPREAD = 0.20            # ask - bid = $0.20
UCUZLUK_SIM = BID_OFFSET + SPREAD * 0.15    # -0.10 + 0.03 = -0.07
PAHALILIK_SIM = ASK_OFFSET - SPREAD * 0.15  # +0.10 - 0.03 = +0.07

DRIFT_TOLERANCE = 4
NORM_DAYS = 30

# PATADD thresholds (from patadd_settings.py defaults)
PATADD_UCUZLUK_THRESHOLD = 0.05     # bid_buy_ucuzluk < 0.05 (tolerant)
PATADD_PAHALILIK_THRESHOLD = -0.05  # ask_sell_pahalilik > -0.05 (tolerant)
PATADD_FBTOT_GT = 1.10
PATADD_SFSTOT_LT = 1.50
PATADD_LPAT_THRESHOLD = 45.0
PATADD_SPAT_THRESHOLD = 30.0
PATADD_MIN_HOLDING_DAYS = 2

# ADDNEWPOS thresholds
ADDNEWPOS_UCUZLUK_THRESHOLD = -0.06
ADDNEWPOS_PAHALILIK_THRESHOLD = 0.06

# ─────────────────────────────────────────────────────────────────────────────
# 1. PREV_CLOSE VERİLERİNİ TOPLA
# ─────────────────────────────────────────────────────────────────────────────
def load_prev_close_map():
    """Tüm janek_ dosyalarından prev_close değerlerini topla."""
    prev_close_map = {}
    
    janek_files = list(JANALL_DIR.glob("janek_ssfin*.csv"))
    print(f"\n📁 {len(janek_files)} janek_ dosyası bulundu")
    
    for fpath in janek_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if 'prev_close' not in (reader.fieldnames or []):
                    continue
                for row in reader:
                    sym = row.get('PREF IBKR', '').strip()
                    pc = row.get('prev_close', '')
                    if sym and pc:
                        try:
                            prev_close_map[sym] = float(pc)
                        except ValueError:
                            pass
        except Exception as e:
            print(f"  ⚠️ {fpath.name}: {e}")
    
    print(f"  → {len(prev_close_map)} sembol için prev_close yüklendi")
    return prev_close_map


# ─────────────────────────────────────────────────────────────────────────────
# 2. BEFDAY POZİSYONLARINI OKU
# ─────────────────────────────────────────────────────────────────────────────
def load_ibkr_ped_positions():
    """En güncel befibped CSV dosyasından pozisyonları oku."""
    csv_files = sorted(BEFDAY_DIR.glob("befibped_*.csv"), reverse=True)
    if not csv_files:
        print("  ⚠️ befibped CSV bulunamadı!")
        return {}, "N/A"
    
    latest = csv_files[0]
    date_str = latest.stem.split('_')[-1]
    positions = {}
    
    with open(latest, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get('Symbol', '').strip()
            qty = float(row.get('Quantity', 0))
            if sym and qty != 0:
                positions[sym] = {
                    'qty': qty,
                    'side': 'SHORT' if qty < 0 else 'LONG',
                    'avg_cost': float(row.get('Avg_Cost', 0)),
                }
    
    print(f"  📂 IBKR_PED: {latest.name} → {len(positions)} pozisyon (tarih: {date_str})")
    return positions, date_str


def load_hampro_positions():
    """HAMPRO pozisyonlarını newjanall/befday.csv'den oku."""
    befday_path = NEWJANALL_DIR / "befday.csv"
    if not befday_path.exists():
        print("  ⚠️ HAMPRO befday.csv bulunamadı!")
        return {}, "N/A"
    
    positions = {}
    with open(befday_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get('Symbol', '').strip()
            qty_str = row.get('Quantity', '0')
            try:
                qty = float(qty_str)
            except ValueError:
                continue
            if sym and qty != 0:
                avg_cost_str = row.get('AvgCost', '0')
                try:
                    avg_cost = float(avg_cost_str)
                except ValueError:
                    avg_cost = 0.0
                positions[sym] = {
                    'qty': qty,
                    'side': 'SHORT' if qty < 0 else 'LONG',
                    'avg_cost': avg_cost,
                }
    
    print(f"  📂 HAMPRO: befday.csv → {len(positions)} pozisyon")
    return positions, "befday"


# ─────────────────────────────────────────────────────────────────────────────
# 3. EXPOSURE HESAPLA
# ─────────────────────────────────────────────────────────────────────────────
def calculate_exposure(positions, prev_close_map, account_name):
    """Pozisyonlar × prev_close ile exposure hesapla."""
    long_exposure = 0.0
    short_exposure = 0.0
    long_lots = 0
    short_lots = 0
    missing_price = []
    position_details = []
    
    for sym, pos in sorted(positions.items(), key=lambda x: abs(x[1]['qty']), reverse=True):
        qty = pos['qty']
        abs_qty = abs(qty)
        
        price = prev_close_map.get(sym)
        if price is None or price <= 0:
            price = pos['avg_cost'] if pos['avg_cost'] > 0 else 20.0
            if sym not in prev_close_map:
                missing_price.append(sym)
        
        value = abs_qty * price
        
        if qty > 0:
            long_exposure += value
            long_lots += abs_qty
        else:
            short_exposure += value
            short_lots += abs_qty
        
        position_details.append({
            'symbol': sym, 'qty': qty, 'price': price,
            'value': value, 'side': pos['side'],
        })
    
    total_exposure = long_exposure + short_exposure
    
    if missing_price:
        print(f"  ⚠️ {len(missing_price)} sembol için prev_close bulunamadı (avg_cost/$20 kullanıldı)")
    
    return {
        'account': account_name,
        'long_exposure': long_exposure, 'short_exposure': short_exposure,
        'total_exposure': total_exposure,
        'long_lots': long_lots, 'short_lots': short_lots,
        'total_lots': long_lots + short_lots,
        'position_count': len(positions),
        'details': position_details, 'missing_price': missing_price,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. EXPOSURE CONFIG OKU
# ─────────────────────────────────────────────────────────────────────────────
def load_exposure_config():
    if not EXPOSURE_CONFIG.exists():
        return {'HAMPRO': {'pot_max': 1_400_000}, 'IBKR_PED': {'pot_max': 1_400_000}}
    with open(EXPOSURE_CONFIG, 'r') as f:
        data = json.load(f)
    return data.get('accounts', {})


# ─────────────────────────────────────────────────────────────────────────────
# 5. TUMCSV OKU
# ─────────────────────────────────────────────────────────────────────────────
def load_tumcsv():
    long_stocks = []
    short_stocks = []
    
    long_path = JANALL_DIR / "tumcsvlong.csv"
    if long_path.exists():
        with open(long_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get('PREF_IBKR', '').strip()
                if not sym:
                    continue
                long_stocks.append({
                    'symbol': sym,
                    'FINAL_THG': float(row.get('FINAL_THG', 0) or 0),
                    'SHORT_FINAL': float(row.get('SHORT_FINAL', 0) or 0),
                    'RECSIZE': int(float(row.get('RECSIZE', 200) or 200)),
                    'AVG_ADV': float(row.get('AVG_ADV', 0) or 0),
                    'KUME_PREM': float(row.get('KUME_PREM', 0) or 0),
                    'CGRUP': row.get('CGRUP', ''),
                    'CMON': row.get('CMON', ''),
                    'DOSYA': row.get('DOSYA', ''),
                    'TIP': row.get('TIP', ''),
                    'SMI': float(row.get('SMI', 0) or 0),
                })
        long_stocks.sort(key=lambda x: x['FINAL_THG'], reverse=True)
    
    short_path = JANALL_DIR / "tumcsvshort.csv"
    if short_path.exists():
        with open(short_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get('PREF_IBKR', '').strip()
                if not sym:
                    continue
                short_stocks.append({
                    'symbol': sym,
                    'FINAL_THG': float(row.get('FINAL_THG', 0) or 0),
                    'SHORT_FINAL': float(row.get('SHORT_FINAL', 0) or 0),
                    'RECSIZE': int(float(row.get('RECSIZE', 200) or 200)),
                    'AVG_ADV': float(row.get('AVG_ADV', 0) or 0),
                    'KUME_PREM': float(row.get('KUME_PREM', 0) or 0),
                    'CGRUP': row.get('CGRUP', ''),
                    'CMON': row.get('CMON', ''),
                    'DOSYA': row.get('DOSYA', ''),
                    'TIP': row.get('TIP', ''),
                    'SMI': float(row.get('SMI', 0) or 0),
                })
        short_stocks.sort(key=lambda x: x['SHORT_FINAL'])
    
    print(f"\n📊 TUMCSV: {len(long_stocks)} LONG adayı, {len(short_stocks)} SHORT adayı")
    return long_stocks, short_stocks


# ─────────────────────────────────────────────────────────────────────────────
# 5b. GERÇEK Fbtot/SFStot DEĞERLERİNİ YÜKLe (final_fb_sfs_tumcsv dosyalarından)
# ─────────────────────────────────────────────────────────────────────────────
def load_fbtot_sfstot_map():
    """final_fb_sfs_tumcsv_long/short_stocks.csv'den gerçek Fbtot/SFStot değerlerini oku."""
    fbtot_map = {}  # symbol -> {'Fbtot': x, 'SFStot': y, 'ucuzluk': z, 'pahalilik': w}
    
    for fpath in [FINAL_FB_LONG, FINAL_FB_SHORT]:
        if not fpath.exists():
            print(f"  ⚠️ {fpath.name} bulunamadı!")
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sym = row.get('PREF IBKR', '').strip()
                    if not sym:
                        continue
                    try:
                        entry = {
                            'Fbtot': float(row.get('Fbtot', 0) or 0),
                            'SFStot': float(row.get('SFStot', 0) or 0),
                            'ucuzluk': float(row.get('Bid_buy_ucuzluk_skoru', 0) or 0),
                            'pahalilik': float(row.get('Ask_sell_pahalilik_skoru', 0) or 0),
                            'Final_BB': float(row.get('Final_BB_skor', 0) or 0),
                            'Final_FB': float(row.get('Final_FB_skor', 0) or 0),
                            'Final_SAS': float(row.get('Final_SAS_skor', 0) or 0),
                            'Final_SFS': float(row.get('Final_SFS_skor', 0) or 0),
                            'GORT': float(row.get('GORT', 0) or 0),
                        }
                        # Sadece en yüksek Fbtot'u sakla (aynı sembol birden fazla dosyada olabilir)
                        if sym not in fbtot_map or entry['Fbtot'] > fbtot_map[sym]['Fbtot']:
                            fbtot_map[sym] = entry
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            print(f"  ⚠️ {fpath.name}: {e}")
    
    # Stats
    fbtot_vals = [v['Fbtot'] for v in fbtot_map.values() if v['Fbtot'] > 0]
    sfstot_vals = [v['SFStot'] for v in fbtot_map.values() if v['SFStot'] > 0]
    print(f"\n📊 Fbtot/SFStot: {len(fbtot_map)} sembol yüklendi")
    if fbtot_vals:
        print(f"   Fbtot  → min={min(fbtot_vals):.4f} max={max(fbtot_vals):.4f} avg={sum(fbtot_vals)/len(fbtot_vals):.4f}")
    if sfstot_vals:
        print(f"   SFStot → min={min(sfstot_vals):.4f} max={max(sfstot_vals):.4f} avg={sum(sfstot_vals)/len(sfstot_vals):.4f}")
    
    return fbtot_map


# ─────────────────────────────────────────────────────────────────────────────
# 6. PATADD SİNYALLERİNİ OKU (v5_summary.csv + janalldata exdiv)
# ─────────────────────────────────────────────────────────────────────────────
def _next_exdiv(ticker, base_map, today):
    raw = base_map.get(ticker)
    if raw is None:
        return None, None
    try:
        base = pd.Timestamp(raw)
    except:
        return None, None
    if pd.isna(base):
        return None, None
    
    candidate = base
    while candidate < today - timedelta(days=DRIFT_TOLERANCE):
        candidate += pd.DateOffset(months=3)
    
    days_until = (candidate - today).days
    return candidate, days_until


def _biz_day_offset(base_dt, offset):
    return base_dt + pd.offsets.BDay(offset)


def load_patadd_signals(target_date=None):
    """v5_summary.csv'den BUY_NOW/SHORT_NOW sinyallerini oku."""
    if pd is None:
        print("  ⚠️ pandas yüklü değil, PATADD atlanıyor")
        return [], []
    
    if not V5_SUMMARY.exists():
        print("  ⚠️ v5_summary.csv bulunamadı!")
        return [], []
    
    if target_date is None:
        # Yarın (2026-03-03 = Pazartesi)
        now = datetime.now()
        target_date = pd.Timestamp(now.replace(hour=0, minute=0, second=0, microsecond=0))
        target_date += timedelta(days=1)
        if target_date.weekday() >= 5:
            target_date += timedelta(days=(7 - target_date.weekday()))
    else:
        target_date = pd.Timestamp(target_date)
    
    # Load base exdiv dates
    base_map = {}
    if JANALLDATA.exists():
        jd = pd.read_csv(JANALLDATA)
        for _, row in jd.iterrows():
            tk = str(row.get('PREF IBKR', '')).strip()
            exdiv = row.get('EX-DIV DATE', '')
            if tk and pd.notna(exdiv) and exdiv:
                base_map[tk] = exdiv
    
    summary = pd.read_csv(V5_SUMMARY)
    
    active_longs = []
    active_shorts = []
    
    for _, row in summary.iterrows():
        tk = row['ticker']
        nxt, days_until = _next_exdiv(tk, base_map, target_date)
        if nxt is None:
            continue
        
        # LONG
        if pd.notna(row.get('best_long_sharpe')) and row['best_long_sharpe'] > 0.3:
            if pd.notna(row.get('best_long_pval')) and row['best_long_pval'] <= 0.15:
                entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
                exit_off = int(row['best_long_exit']) if pd.notna(row.get('best_long_exit')) else 0
                entry_dt = _biz_day_offset(nxt, entry_off)
                exit_dt = _biz_day_offset(nxt, exit_off)
                if exit_dt <= entry_dt:
                    exit_dt = entry_dt + timedelta(days=2)
                
                win_start = entry_dt - timedelta(days=1)
                win_end = entry_dt + timedelta(days=1)
                
                if win_start <= target_date <= win_end:
                    _wr = float(row.get('best_long_win', 0))
                    _sh = float(row.get('best_long_sharpe', 0))
                    _rt = float(row.get('best_long_ret', 0))
                    _pv = float(row.get('best_long_pval', 1))
                    _nc = int(row.get('n_exdivs', 0))
                    _hold = max(3, exit_off - entry_off)
                    _norm_rt = _rt / _hold * NORM_DAYS
                    
                    _conf = min(100, max(0,
                        _wr * 35 + (1 - min(_pv, 1)) * 25 +
                        min(_nc, 10) / 10 * 20 + min(_sh, 5) / 5 * 20
                    ))
                    score = round(_conf / 10 * (1 + abs(_norm_rt) / 3), 3)
                    
                    remaining_days = (exit_dt - target_date).days
                    
                    active_longs.append({
                        'ticker': tk, 'signal': 'BUY_NOW', 'score': score,
                        'entry_date': entry_dt.strftime('%Y-%m-%d'),
                        'exit_date': exit_dt.strftime('%Y-%m-%d'),
                        'exdiv_date': nxt.strftime('%Y-%m-%d'),
                        'win_rate': _wr, 'sharpe': _sh, 'norm_return': _norm_rt,
                        'holding_days': _hold, 'remaining_days': remaining_days,
                        'strategy': str(row.get('best_long_name', '')),
                    })
        
        # SHORT
        if pd.notna(row.get('best_short_sharpe')) and row['best_short_sharpe'] > 0.3:
            if pd.notna(row.get('best_short_pval')) and row['best_short_pval'] <= 0.15:
                entry_off = int(row['best_short_entry']) if pd.notna(row.get('best_short_entry')) else -3
                exit_off = int(row['best_short_exit']) if pd.notna(row.get('best_short_exit')) else 0
                entry_dt = _biz_day_offset(nxt, entry_off)
                exit_dt = _biz_day_offset(nxt, exit_off)
                if exit_dt <= entry_dt:
                    exit_dt = entry_dt + timedelta(days=2)
                
                win_start = entry_dt - timedelta(days=1)
                win_end = entry_dt + timedelta(days=1)
                
                if win_start <= target_date <= win_end:
                    _wr = float(row.get('best_short_win', 0))
                    _sh = float(row.get('best_short_sharpe', 0))
                    _rt = float(row.get('best_short_ret', 0))
                    _pv = float(row.get('best_short_pval', 1))
                    _nc = int(row.get('n_exdivs', 0))
                    _hold = max(3, exit_off - entry_off)
                    _norm_rt = _rt / _hold * NORM_DAYS
                    
                    _conf = min(100, max(0,
                        _wr * 35 + (1 - min(_pv, 1)) * 25 +
                        min(_nc, 10) / 10 * 20 + min(_sh, 5) / 5 * 20
                    ))
                    score = round(_conf / 10 * (1 + abs(_norm_rt) / 3), 3)
                    remaining_days = (exit_dt - target_date).days
                    
                    active_shorts.append({
                        'ticker': tk, 'signal': 'SHORT_NOW', 'score': score,
                        'entry_date': entry_dt.strftime('%Y-%m-%d'),
                        'exit_date': exit_dt.strftime('%Y-%m-%d'),
                        'exdiv_date': nxt.strftime('%Y-%m-%d'),
                        'win_rate': _wr, 'sharpe': _sh, 'norm_return': _norm_rt,
                        'holding_days': _hold, 'remaining_days': remaining_days,
                        'strategy': str(row.get('best_short_name', '')),
                    })
    
    print(f"\n🎯 PATADD Sinyalleri ({target_date.strftime('%Y-%m-%d')}): "
          f"{len(active_longs)} BUY_NOW, {len(active_shorts)} SHORT_NOW")
    return active_longs, active_shorts


# ─────────────────────────────────────────────────────────────────────────────
# 7. ADDNEWPOS SİMÜLASYONU (v2: bid/ask offset)
# ─────────────────────────────────────────────────────────────────────────────
def simulate_addnewpos(tumcsv_stocks, side, existing_positions, prev_close_map, exposure_info, config, fbtot_map=None):
    pot_max = config.get('pot_max', 1_400_000)
    pot_total = exposure_info['total_exposure']
    exposure_pct = (pot_total / pot_max) * 100.0 if pot_max > 0 else 100.0
    
    if exposure_pct >= 92.0:
        regime = 'HARD'; add_intent = 0; pick_count = 0
    elif exposure_pct >= 85.0:
        pct_through = (exposure_pct - 85.0) / (92.0 - 85.0)
        add_intent = max(0, 70.0 * (1.0 - pct_through))
        regime = 'SOFT'
        if add_intent >= 70: pick_count = 5
        elif add_intent >= 40: pick_count = 3
        elif add_intent >= 20: pick_count = 1
        else: pick_count = 0
    else:
        regime = 'NORMAL'; add_intent = 70.0; pick_count = 5
    
    remaining_exposure = (pot_max - pot_total) * 0.70
    
    results = {
        'side': side, 'exposure_pct': exposure_pct, 'regime': regime,
        'add_intent': add_intent, 'pick_count': pick_count,
        'remaining_exposure': remaining_exposure, 'pot_max': pot_max,
        'pot_total': pot_total, 'candidates': [],
        'blocked_by_filter': [], 'blocked_by_exposure': False,
        'orders': [],
    }
    
    if regime == 'HARD' or pick_count == 0:
        results['blocked_by_exposure'] = True
        return results
    
    stocks_to_process = tumcsv_stocks[:pick_count]
    
    for stock in stocks_to_process:
        symbol = stock['symbol']
        recsize = stock['RECSIZE']
        final_thg = stock['FINAL_THG']
        short_final = stock['SHORT_FINAL']
        dosya = stock['DOSYA']
        avg_adv = stock['AVG_ADV']
        smi = stock['SMI']
        
        price = prev_close_map.get(symbol, 0)
        existing_qty = existing_positions.get(symbol, {}).get('qty', 0)
        
        # v3: Gerçek Fbtot/SFStot değerleri + bid/ask offset simülasyonu
        fb_data = (fbtot_map or {}).get(symbol, {})
        fbtot_real = fb_data.get('Fbtot', 0)
        sfstot_real = fb_data.get('SFStot', 0)
        # Ucuzluk/Pahalilik: gerçek değer varsa kullan, yoksa bid/ask offset simülasyonu
        ucuzluk = fb_data.get('ucuzluk', UCUZLUK_SIM) if fb_data else UCUZLUK_SIM
        pahalilik = fb_data.get('pahalilik', PAHALILIK_SIM) if fb_data else PAHALILIK_SIM
        
        candidate = {
            'symbol': symbol, 'price': price,
            'FINAL_THG': final_thg, 'SHORT_FINAL': short_final,
            'RECSIZE': recsize, 'AVG_ADV': avg_adv,
            'ucuzluk': ucuzluk, 'pahalilik': pahalilik,
            'Fbtot': fbtot_real, 'SFStot': sfstot_real,
            'existing_qty': existing_qty, 'dosya': dosya,
            'SMI': smi, 'CGRUP': stock['CGRUP'], 'CMON': stock['CMON'],
        }
        results['candidates'].append(candidate)
        
        # ADDNEWPOS filtre mantığı
        filter_reason = None
        if side == "LONG":
            if ucuzluk >= ADDNEWPOS_UCUZLUK_THRESHOLD:
                filter_reason = f"Ucuzluk={ucuzluk:.4f} >= {ADDNEWPOS_UCUZLUK_THRESHOLD}"
            elif fbtot_real > 0 and fbtot_real <= 1.10:
                filter_reason = f"Fbtot={fbtot_real:.4f} <= 1.10 (grupta ucuz değil)"
            elif fbtot_real == 0:
                filter_reason = f"Fbtot=N/A (final_fb_sfs dosyasında yok)"
        else:
            if pahalilik <= ADDNEWPOS_PAHALILIK_THRESHOLD:
                filter_reason = f"Pahalilik={pahalilik:.4f} <= {ADDNEWPOS_PAHALILIK_THRESHOLD}"
            elif sfstot_real > 0 and sfstot_real >= 1.10:
                filter_reason = f"SFStot={sfstot_real:.4f} >= 1.10 (grupta pahalı değil)"
        
        if filter_reason:
            results['blocked_by_filter'].append({**candidate, 'reason': filter_reason})
        else:
            lot = max(200, (recsize // 100) * 100)
            action = 'BUY' if side == "LONG" else 'SHORT_SELL'
            if side == "LONG" and existing_qty > 0:
                action = 'ADDNEWPOS_ADD'
            elif side == "SHORT" and existing_qty < 0:
                action = 'ADDNEWPOS_ADD_SHORT'
            
            order_value = lot * price if price else 0
            results['orders'].append({
                **candidate, 'lot': lot, 'order_value': order_value,
                'action': action, 'engine': 'ADDNEWPOS',
            })
    
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 8. PATADD SİMÜLASYONU (v2: pattern signals + bid/ask offset)
# ─────────────────────────────────────────────────────────────────────────────
def simulate_patadd(signals, direction, existing_positions, prev_close_map, exposure_info, config, fbtot_map=None):
    """PATADD motorunu simüle et."""
    pot_max = config.get('pot_max', 1_400_000)
    pot_total = exposure_info['total_exposure']
    exposure_pct = (pot_total / pot_max) * 100.0 if pot_max > 0 else 100.0
    
    results = {
        'direction': direction, 'exposure_pct': exposure_pct,
        'blocked_by_exposure': exposure_pct >= 92.0,
        'orders': [], 'filtered': [], 'signal_count': len(signals),
    }
    
    if results['blocked_by_exposure']:
        return results
    
    scored = []
    
    for sig in signals:
        ticker = sig['ticker']
        pattern_score = sig['score']
        win_rate = sig['win_rate']
        sharpe = sig['sharpe']
        remaining_days = sig.get('remaining_days', 99)
        
        price = prev_close_map.get(ticker, 0)
        existing_qty = existing_positions.get(ticker, {}).get('qty', 0)
        
        # v3: Gerçek Fbtot/SFStot değerleri
        fb_data = (fbtot_map or {}).get(ticker, {})
        fbtot_real = fb_data.get('Fbtot', 0)
        sfstot_real = fb_data.get('SFStot', 0)
        ucuzluk = fb_data.get('ucuzluk', UCUZLUK_SIM) if fb_data else UCUZLUK_SIM
        pahalilik = fb_data.get('pahalilik', PAHALILIK_SIM) if fb_data else PAHALILIK_SIM
        
        info = {
            'ticker': ticker, 'price': price, 'pattern_score': pattern_score,
            'win_rate': win_rate, 'sharpe': sharpe,
            'entry_date': sig['entry_date'], 'exit_date': sig['exit_date'],
            'exdiv_date': sig['exdiv_date'], 'remaining_days': remaining_days,
            'strategy': sig['strategy'], 'existing_qty': existing_qty,
            'Fbtot': fbtot_real, 'SFStot': sfstot_real,
            'ucuzluk': ucuzluk, 'pahalilik': pahalilik,
        }
        
        # FILTER 0: Min holding days
        if remaining_days < PATADD_MIN_HOLDING_DAYS:
            results['filtered'].append({**info, 'reason': f"Remaining {remaining_days}d < min {PATADD_MIN_HOLDING_DAYS}d"})
            continue
        
        # FILTER 2a: Fbtot/SFStot (gerçek değerler)
        if direction == 'LONG':
            if fbtot_real > 0 and fbtot_real <= PATADD_FBTOT_GT:
                results['filtered'].append({**info, 'reason': f"Fbtot={fbtot_real:.4f} <= {PATADD_FBTOT_GT}"})
                continue
            # Fbtot=0 (dosyada yok) → PATADD toleranslı: pattern score yeterince yüksekse geç
            # (Preferred stocklar genelde final_fb_sfs dosyasında olmaz)
        if direction == 'SHORT':
            if sfstot_real > 0 and sfstot_real >= PATADD_SFSTOT_LT:
                results['filtered'].append({**info, 'reason': f"SFStot={sfstot_real:.4f} >= {PATADD_SFSTOT_LT}"})
                continue
            # SFStot=0 (yok) → geç (toleranslı)
        
        # FILTER 2b: Ucuzluk/Pahalilik (PATADD toleranslı)
        if direction == 'LONG':
            if ucuzluk >= PATADD_UCUZLUK_THRESHOLD:
                results['filtered'].append({**info, 'reason': f"Ucuzluk={ucuzluk:.4f} >= {PATADD_UCUZLUK_THRESHOLD}"})
                continue
        else:
            if pahalilik <= PATADD_PAHALILIK_THRESHOLD:
                results['filtered'].append({**info, 'reason': f"Pahalilik={pahalilik:.4f} <= {PATADD_PAHALILIK_THRESHOLD}"})
                continue
        
        # LPAT/SPAT composite score (gerçek Fbtot/SFStot ile)
        if direction == 'LONG':
            qe_factor = fbtot_real if fbtot_real > 0 else 1.0
            pat_score = pattern_score * qe_factor
        else:
            qe_factor = sfstot_real if sfstot_real > 0 else 1.0
            pat_score = pattern_score / max(qe_factor, 0.01)
        
        threshold = PATADD_LPAT_THRESHOLD if direction == 'LONG' else PATADD_SPAT_THRESHOLD
        if pat_score < threshold:
            results['filtered'].append({**info, 'pat_score': pat_score,
                'reason': f"{'LPAT' if direction=='LONG' else 'SPAT'}={pat_score:.1f} < {threshold:.0f}"})
            continue
        
        # LOT (simplified — MAXALW × 0.50 for new positions)
        lot = 200  # Min lot for PATADD
        
        # Action
        if direction == 'LONG':
            action = 'PATADD_ADD' if existing_qty > 0 else 'PATADD_BUY'
        else:
            action = 'PATADD_ADD_SHORT' if existing_qty < 0 else 'PATADD_SHORT'
        
        order_value = lot * price if price else 0
        
        scored.append((pat_score, {
            **info, 'pat_score': pat_score, 'lot': lot,
            'order_value': order_value, 'action': action, 'engine': 'PATADD',
        }))
    
    # Rank by score
    scored.sort(key=lambda x: x[0], reverse=True)
    results['orders'] = [s[1] for s in scored[:20]]  # max 20 per side
    
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 9. RAPOR OLUŞTUR
# ─────────────────────────────────────────────────────────────────────────────
def format_money(val):
    if abs(val) >= 1_000_000: return f"${val:,.0f}"
    elif abs(val) >= 1000: return f"${val:,.0f}"
    else: return f"${val:.2f}"


def print_header(text, char='═', width=90):
    print()
    print(char * width)
    print(f"  {text}")
    print(char * width)


def print_exposure_report(exp_info, config, label):
    pot_max = config.get('pot_max', 1_400_000)
    total = exp_info['total_exposure']
    exposure_pct = (total / pot_max * 100) if pot_max > 0 else 0
    free_exposure = pot_max - total
    free_pct = 100.0 - exposure_pct
    
    if exposure_pct >= 95.5: regime = "🔴 DEFANSIF"
    elif exposure_pct >= 92.7: regime = "🟠 GEÇİŞ"
    elif exposure_pct >= 92.0: regime = "🟡 HARD RISK"
    elif exposure_pct >= 84.9: regime = "🟡 SOFT THROTTLE"
    else: regime = "🟢 OFANSİF"
    
    hard_risk_active = exposure_pct >= 92.0
    
    print(f"\n  {'─'*70}")
    print(f"  📊 {label}")
    print(f"  {'─'*70}")
    print(f"  POT_MAX              : {format_money(pot_max)}")
    print(f"  Current Exposure     : {format_money(total)} ({exposure_pct:.1f}%)")
    print(f"  Free Exposure        : {format_money(free_exposure)} ({free_pct:.1f}%)")
    print(f"  Long  Exposure       : {format_money(exp_info['long_exposure'])} ({exp_info['long_lots']:,.0f} lot)")
    print(f"  Short Exposure       : {format_money(exp_info['short_exposure'])} ({exp_info['short_lots']:,.0f} lot)")
    print(f"  Pozisyon Sayısı      : {exp_info['position_count']}")
    print(f"  Rejim                : {regime}")
    print(f"  Hard Risk Aktif?     : {'❌ EVET' if hard_risk_active else '✅ Hayır'}")


def print_orders(results, engine_label, account):
    side = results.get('side', results.get('direction', '?'))
    side_emoji = "📈" if side == "LONG" else "📉"
    
    print(f"\n  {side_emoji} {engine_label} — {side} ({account})")
    
    if results.get('blocked_by_exposure'):
        print(f"  🚫 EXPOSURE ENGEL! ({results.get('exposure_pct', 0):.1f}% ≥ 92%) — Emir yok!")
        return
    
    # Filtreler
    blocked = results.get('blocked_by_filter', results.get('filtered', []))
    orders = results.get('orders', [])
    
    if blocked:
        print(f"  ⚠️  {len(blocked)} aday filtrelendi:")
        for b in blocked[:5]:
            sym = b.get('symbol', b.get('ticker', '?'))
            reason = b.get('reason', '')
            print(f"     {sym:15s} → {reason}")
        if len(blocked) > 5:
            print(f"     ... ve {len(blocked)-5} daha")
    
    if orders:
        total_lots = sum(o['lot'] for o in orders)
        total_value = sum(o.get('order_value', 0) for o in orders)
        
        print(f"\n  ✅ {len(orders)} emir oluşturulacak (Toplam: {total_lots} lot, {format_money(total_value)}):")
        print(f"  {'#':<4} {'Symbol':<14} {'Action':<20} {'Lot':>6} {'Price':>8} {'Value':>10} ", end="")
        
        if engine_label.startswith('PATADD'):
            print(f"{'PatScore':>8} {'WR':>6} {'Sharpe':>7} Strategy")
        else:
            print(f"{'FTHG':>8} {'SF':>8} {'SMI':>6} {'CGRUP':<8} Dosya")
        
        print(f"  {'─'*120}")
        
        for i, o in enumerate(orders, 1):
            sym = o.get('symbol', o.get('ticker', '?'))
            action = o.get('action', '?')
            lot = o.get('lot', 0)
            price = o.get('price', 0)
            ov = o.get('order_value', 0)
            
            if engine_label.startswith('PATADD'):
                ps = o.get('pat_score', o.get('pattern_score', 0))
                wr = o.get('win_rate', 0)
                sh = o.get('sharpe', 0)
                strat = o.get('strategy', '')[:25]
                print(f"  {i:<4} {sym:<14} {action:<20} {lot:>6} ${price:>7.2f} {format_money(ov):>10} {ps:>8.1f} {wr:>5.0%} {sh:>7.2f} {strat}")
            else:
                fthg = o.get('FINAL_THG', 0)
                sf = o.get('SHORT_FINAL', 0)
                smi_val = o.get('SMI', 0)
                cgrp = o.get('CGRUP', '')
                dosya = o.get('dosya', '').replace('ssfinekheld', '').replace('.csv', '')
                print(f"  {i:<4} {sym:<14} {action:<20} {lot:>6} ${price:>7.2f} {format_money(ov):>10} {fthg:>8.0f} {sf:>8.0f} {smi_val:>6.2f} {cgrp:<8} {dosya}")
    else:
        if not blocked:
            print(f"  → Sinyal yok veya tümü filtrelendi")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print_header("DUAL PROCESS SİMÜLASYON v3.0", '█', 90)
    print(f"  Tarih      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Varsayım   : bid = prev_close - $0.10, ask = prev_close + $0.10")
    print(f"  Spread     : $0.20")
    print(f"  Ucuzluk    : {UCUZLUK_SIM:+.4f} (bid+spread*0.15-pc)")
    print(f"  Pahalilik  : {PAHALILIK_SIM:+.4f} (ask-spread*0.15-pc)")
    print(f"  FBTOT/SFSTOT: GERÇEK DEĞERLER (final_fb_sfs dosyalarından)")
    
    # ─── STEP 1: Prev close
    print_header("1. PREV_CLOSE VERİLERİ", '─')
    prev_close_map = load_prev_close_map()
    
    # ─── STEP 2: Pozisyonlar
    print_header("2. BEFDAY POZİSYONLARI", '─')
    ibkr_positions, ibkr_date = load_ibkr_ped_positions()
    ham_positions, ham_date = load_hampro_positions()
    
    # ─── STEP 3: Exposure
    print_header("3. EXPOSURE", '─')
    exp_config = load_exposure_config()
    ibkr_exp = calculate_exposure(ibkr_positions, prev_close_map, "IBKR_PED")
    ham_exp = calculate_exposure(ham_positions, prev_close_map, "HAMPRO")
    
    ibkr_config = exp_config.get('IBKR_PED', {'pot_max': 1_400_000, 'current_threshold': 92.0})
    ham_config = exp_config.get('HAMPRO', {'pot_max': 1_400_000, 'current_threshold': 92.0})
    
    print_exposure_report(ibkr_exp, ibkr_config, f"IBKR_PED (BEFDAY: {ibkr_date})")
    print_exposure_report(ham_exp, ham_config, f"HAMPRO (BEFDAY: {ham_date})")
    
    # ─── STEP 4: TUMCSV
    print_header("4. ADDNEWPOS ADAYLARI (tumcsv)", '─')
    long_stocks, short_stocks = load_tumcsv()
    
    # ─── STEP 4b: Fbtot/SFStot FORMÜLDEN HESAPLA
    print_header("4b. HESAPLANAN Fbtot/SFStot/GORT (formülden)", '─')
    # Tüm hedef sembolleri topla
    all_target_syms = set()
    for s in long_stocks: all_target_syms.add(s['symbol'])
    for s in short_stocks: all_target_syms.add(s['symbol'])
    # PATADD sinyalleri de eklenecek (aşağıda yüklendikten sonra)
    # Şimdilik tüm dosya gruplarını hesapla
    from calculate_fbtot import calculate_fbtot_sfstot_gort
    fbtot_map = calculate_fbtot_sfstot_gort(list(all_target_syms), prev_close_map, BID_OFFSET, ASK_OFFSET)
    
    # ─── STEP 5: PATADD SİNYALLERİ
    print_header("5. PATADD SİNYALLERİ (Pattern Suggestions)", '─')
    patadd_longs, patadd_shorts = load_patadd_signals()
    
    if patadd_longs:
        print(f"\n  🟢 BUY_NOW Sinyalleri:")
        for s in patadd_longs:
            fb = fbtot_map.get(s['ticker'], {})
            fb_val = fb.get('Fbtot', 0)
            fb_str = f"Fbtot={fb_val:.2f}" if fb_val > 0 else "Fbtot=N/A"
            print(f"     {s['ticker']:15s} Score={s['score']:.1f} WR={s['win_rate']:.0%} "
                  f"Sharpe={s['sharpe']:.2f} {fb_str} Entry={s['entry_date']} Exit={s['exit_date']}")
    if patadd_shorts:
        print(f"\n  🔴 SHORT_NOW Sinyalleri:")
        for s in patadd_shorts:
            fb = fbtot_map.get(s['ticker'], {})
            sf_val = fb.get('SFStot', 0)
            sf_str = f"SFStot={sf_val:.2f}" if sf_val > 0 else "SFStot=N/A"
            print(f"     {s['ticker']:15s} Score={s['score']:.1f} WR={s['win_rate']:.0%} "
                  f"Sharpe={s['sharpe']:.2f} {sf_str} Entry={s['entry_date']} Exit={s['exit_date']}")
    
    # ═══════════════════════════════════════════════════════════════════
    # IBKR_PED SİMÜLASYONU
    # ═══════════════════════════════════════════════════════════════════
    print_header("6. IBKR_PED — EMİR SİMÜLASYONU", '█')
    
    ibkr_long = simulate_addnewpos(long_stocks, "LONG", ibkr_positions, prev_close_map, ibkr_exp, ibkr_config, fbtot_map)
    ibkr_short = simulate_addnewpos(short_stocks, "SHORT", ibkr_positions, prev_close_map, ibkr_exp, ibkr_config, fbtot_map)
    ibkr_patadd_long = simulate_patadd(patadd_longs, "LONG", ibkr_positions, prev_close_map, ibkr_exp, ibkr_config, fbtot_map)
    ibkr_patadd_short = simulate_patadd(patadd_shorts, "SHORT", ibkr_positions, prev_close_map, ibkr_exp, ibkr_config, fbtot_map)
    
    print_orders(ibkr_long, "ADDNEWPOS", "IBKR_PED")
    print_orders(ibkr_short, "ADDNEWPOS", "IBKR_PED")
    print_orders(ibkr_patadd_long, "PATADD LPAT", "IBKR_PED")
    print_orders(ibkr_patadd_short, "PATADD SPAT", "IBKR_PED")
    
    # ═══════════════════════════════════════════════════════════════════
    # HAMPRO SİMÜLASYONU
    # ═══════════════════════════════════════════════════════════════════
    print_header("7. HAMPRO — EMİR SİMÜLASYONU", '█')
    
    ham_long = simulate_addnewpos(long_stocks, "LONG", ham_positions, prev_close_map, ham_exp, ham_config, fbtot_map)
    ham_short = simulate_addnewpos(short_stocks, "SHORT", ham_positions, prev_close_map, ham_exp, ham_config, fbtot_map)
    ham_patadd_long = simulate_patadd(patadd_longs, "LONG", ham_positions, prev_close_map, ham_exp, ham_config, fbtot_map)
    ham_patadd_short = simulate_patadd(patadd_shorts, "SHORT", ham_positions, prev_close_map, ham_exp, ham_config, fbtot_map)
    
    print_orders(ham_long, "ADDNEWPOS", "HAMPRO")
    print_orders(ham_short, "ADDNEWPOS", "HAMPRO")
    print_orders(ham_patadd_long, "PATADD LPAT", "HAMPRO")
    print_orders(ham_patadd_short, "PATADD SPAT", "HAMPRO")
    
    # ═══════════════════════════════════════════════════════════════════
    # SONUÇ ÖZETİ
    # ═══════════════════════════════════════════════════════════════════
    print_header("8. SONUÇ ÖZETİ", '█')
    
    def count_orders(r): return len(r.get('orders', []))
    def count_filtered(r): return len(r.get('blocked_by_filter', r.get('filtered', [])))
    
    ibkr_pct = ibkr_exp['total_exposure']/ibkr_config.get('pot_max', 1400000)*100
    ham_pct = ham_exp['total_exposure']/ham_config.get('pot_max', 1400000)*100
    
    print(f"""
  ╔══════════════════════════════╦═══════════════════╦═══════════════════╗
  ║ Metrik                       ║ IBKR_PED          ║ HAMPRO            ║
  ╠══════════════════════════════╬═══════════════════╬═══════════════════╣
  ║ POT_MAX                      ║ {format_money(ibkr_config.get('pot_max',1400000)):>17} ║ {format_money(ham_config.get('pot_max',1400000)):>17} ║
  ║ Current Exposure             ║ {format_money(ibkr_exp['total_exposure']):>17} ║ {format_money(ham_exp['total_exposure']):>17} ║
  ║ Exposure %                   ║ {ibkr_pct:>16.1f}% ║ {ham_pct:>16.1f}% ║
  ║ Free Exposure                ║ {format_money(ibkr_config.get('pot_max',1400000)-ibkr_exp['total_exposure']):>17} ║ {format_money(ham_config.get('pot_max',1400000)-ham_exp['total_exposure']):>17} ║
  ║ Rejim                        ║ {'HARD RISK' if ibkr_pct>=92 else 'SOFT' if ibkr_pct>=84.9 else 'OFANSIF':>17} ║ {'HARD RISK' if ham_pct>=92 else 'SOFT' if ham_pct>=84.9 else 'OFANSIF':>17} ║
  ╠══════════════════════════════╬═══════════════════╬═══════════════════╣
  ║ ADDNEWPOS LONG               ║ {count_orders(ibkr_long):>14} emir ║ {count_orders(ham_long):>14} emir ║
  ║ ADDNEWPOS SHORT              ║ {count_orders(ibkr_short):>14} emir ║ {count_orders(ham_short):>14} emir ║
  ║ PATADD LONG  (LPAT)          ║ {count_orders(ibkr_patadd_long):>14} emir ║ {count_orders(ham_patadd_long):>14} emir ║
  ║ PATADD SHORT (SPAT)          ║ {count_orders(ibkr_patadd_short):>14} emir ║ {count_orders(ham_patadd_short):>14} emir ║
  ╠══════════════════════════════╬═══════════════════╬═══════════════════╣
  ║ TOPLAM EMİR                  ║ {count_orders(ibkr_long)+count_orders(ibkr_short)+count_orders(ibkr_patadd_long)+count_orders(ibkr_patadd_short):>14} emir ║ {count_orders(ham_long)+count_orders(ham_short)+count_orders(ham_patadd_long)+count_orders(ham_patadd_short):>14} emir ║
  ╚══════════════════════════════╩═══════════════════╩═══════════════════╝

  📝 Varsayımlar:
      bid = prev_close - $0.10, ask = prev_close + $0.10
      → Ucuzluk SIM = {UCUZLUK_SIM:+.4f}  (ADDNEWPOS eşik: {ADDNEWPOS_UCUZLUK_THRESHOLD})
      → Pahalilik SIM = {PAHALILIK_SIM:+.4f} (ADDNEWPOS eşik: {ADDNEWPOS_PAHALILIK_THRESHOLD})
      → FBTOT/SFSTOT: GERÇEK DEĞERLER (final_fb_sfs dosyalarından)
      → fb_sfs'de bulunan semboller: gerçek ucuzluk/pahalilik kullanılır
      → fb_sfs'de OLMAYAN semboller: simülasyon değerleri kullanılır
      → PATADD LONG: Fbtot N/A → toleranslı geçiş (preferred stocklar)
      → PATADD SHORT: SFStot N/A → toleranslı geçiş

  💡 SONUÇ:
      IBKR_PED: {ibkr_pct:.1f}% exposure → {'HARD RISK — tüm emirler engelli ❌' if ibkr_pct >= 92 else 'OFANSİF — tam emir üretimi ✅'}
      HAMPRO:   {ham_pct:.1f}% exposure → {'HARD RISK — tüm emirler engelli ❌' if ham_pct >= 92 else 'OFANSİF — tam emir üretimi ✅'}
      IBKR_PED toplam: {count_orders(ibkr_long)+count_orders(ibkr_short)+count_orders(ibkr_patadd_long)+count_orders(ibkr_patadd_short)} emir
      HAMPRO   toplam: {count_orders(ham_long)+count_orders(ham_short)+count_orders(ham_patadd_long)+count_orders(ham_patadd_short)} emir

""")


if __name__ == "__main__":
    main()
