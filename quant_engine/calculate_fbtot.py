#!/usr/bin/env python3
"""
Fbtot/SFStot/GORT hesaplama modülü - Simülasyon için
Dosya grubundaki tüm hisselerin Final_BB/Final_FB/Final_SAS/Final_SFS skorlarını hesaplar
ve bunlardan Plagr (sıralama) + Ratgr (ortalamaya oran) ile Fbtot/SFStot üretir.
"""
import csv
import os
from pathlib import Path
from collections import defaultdict

JANALL_DIR = Path(r"C:\StockTracker\janall")

# Dosya grupları (janek_ dosyaları)
GROUP_FILES = {
    'ff': 'janek_ssfinekheldff.csv',
    'besmaturlu': 'janek_ssfineknotbesmaturlu.csv',
    'solidbig': 'janek_ssfinekheldsolidbig.csv',
    'kuponlu': 'janek_ssfinekheldkuponlu.csv',
    'flr': 'janek_ssfinekheldflr.csv',
    'nff': 'janek_ssfinekheldnff.csv',
    'deznff': 'janek_ssfinekhelddeznff.csv',
    'kuponlukreciliz': 'janek_ssfinekheldkuponlukreciliz.csv',
    'kuponlukreorta': 'janek_ssfinekheldkuponlukreorta.csv',
    'otelremorta': 'janek_ssfinekheldotelremorta.csv',
    'titrekhc': 'janek_ssfinekheldtitrekhc.csv',
    'highmatur': 'janek_ssfinekhighmatur.csv',
    'notcefilliquid': 'janek_ssfineknotcefilliquid.csv',
    'nottitrekhc': 'janek_ssfineknottitrekhc.csv',
    'salakilliquid': 'janek_ssfineksalakilliquid.csv',
    'shitremhc': 'janek_ssfinekshitremhc.csv',
    'garabetaltiyedi': 'janek_ssfinekheldgarabetaltiyedi.csv',
}


def load_group_stocks():
    """Tüm dosya gruplarındaki hisseleri ve FINAL_THG/SHORT_FINAL değerlerini yükle."""
    # symbol -> {group, FINAL_THG, SHORT_FINAL, prev_close, ...}
    symbol_data = {}
    # group -> [symbols]
    group_members = defaultdict(list)
    
    for group_name, file_name in GROUP_FILES.items():
        fpath = JANALL_DIR / file_name
        if not fpath.exists():
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sym = row.get('PREF IBKR', '').strip()
                    if not sym:
                        continue
                    
                    final_thg = float(row.get('FINAL_THG', 0) or 0)
                    short_final = float(row.get('SHORT_FINAL', 0) or 0)
                    prev_close = float(row.get('prev_close', 0) or 0)
                    sma63_chg = float(row.get('SMA63 chg', 0) or 0)
                    
                    entry = {
                        'group': group_name,
                        'FINAL_THG': final_thg,
                        'SHORT_FINAL': short_final,
                        'prev_close': prev_close,
                        'SMA63_chg': sma63_chg,
                    }
                    
                    # İlk karşılaşılan grup kazanır (ya da daha yüksek FINAL_THG olan)
                    if sym not in symbol_data or final_thg > symbol_data[sym]['FINAL_THG']:
                        symbol_data[sym] = entry
                    
                    group_members[group_name].append(sym)
        except Exception as e:
            print(f"  ⚠️ {file_name}: {e}")
    
    return symbol_data, group_members


def calculate_scores_for_symbol(sym, prev_close, bid, ask, last_price, benchmark_chg=0):
    """Tek bir sembol için ucuzluk/pahalilik skorlarını hesapla."""
    if prev_close <= 0:
        return None
    
    spread = ask - bid if ask > 0 and bid > 0 else 0
    
    # Passive fiyatlar
    pf_bid_buy = bid + (spread * 0.15) if bid > 0 else 0
    pf_front_buy = last_price + 0.01 if last_price > 0 else 0
    pf_ask_sell = ask - (spread * 0.15) if ask > 0 else 0
    pf_front_sell = last_price - 0.01 if last_price > 0 else 0
    
    # Değişimler
    pf_bid_buy_chg = pf_bid_buy - prev_close
    pf_front_buy_chg = pf_front_buy - prev_close
    pf_ask_sell_chg = pf_ask_sell - prev_close
    pf_front_sell_chg = pf_front_sell - prev_close
    
    # Ucuzluk/Pahalilik
    bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
    front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
    ask_sell_pahalilik = pf_ask_sell_chg - benchmark_chg
    front_sell_pahalilik = pf_front_sell_chg - benchmark_chg
    
    return {
        'bid_buy_ucuzluk': bid_buy_ucuzluk,
        'front_buy_ucuzluk': front_buy_ucuzluk,
        'ask_sell_pahalilik': ask_sell_pahalilik,
        'front_sell_pahalilik': front_sell_pahalilik,
    }


def calculate_fbtot_sfstot_gort(target_symbols, prev_close_map, bid_offset=-0.10, ask_offset=0.10):
    """
    Hedef semboller için Fbtot/SFStot/GORT hesapla.
    
    Formüller:
    - Final_BB = FINAL_THG - 800 × bid_buy_ucuzluk
    - Final_FB = FINAL_THG - 800 × front_buy_ucuzluk  
    - Final_SAS = SHORT_FINAL - 800 × ask_sell_pahalilik
    - Final_SFS = SHORT_FINAL - 800 × front_sell_pahalilik
    - FBPlagr = rank(Final_FB asc) / total_in_group 
    - FBRatgr = symbol_Final_FB / avg_Final_FB_in_group
    - Fbtot = FBPlagr + FBRatgr
    - SFSPlagr = rank(Final_SFS asc) / total_in_group
    - SFSRatgr = symbol_Final_SFS / avg_Final_SFS_in_group  
    - SFStot = SFSPlagr + SFSRatgr
    - GORT = FINAL_THG (simplification)
    """
    symbol_data, group_members = load_group_stocks()
    
    print(f"\n  📊 Dosya gruplarından {len(symbol_data)} sembol yüklendi ({len(group_members)} grup)")
    
    # Her sembol için bid/ask simülasyonu ile skorları hesapla
    all_scores = {}  # sym -> {Final_BB, Final_FB, Final_SAS, Final_SFS, group, ...}
    
    for sym, data in symbol_data.items():
        pc = prev_close_map.get(sym, data['prev_close'])
        if pc <= 0:
            continue
        
        bid = pc + bid_offset
        ask = pc + ask_offset
        last = pc  # last = prev_close
        
        scores = calculate_scores_for_symbol(sym, pc, bid, ask, last, benchmark_chg=0)
        if scores is None:
            continue
        
        final_thg = data['FINAL_THG']
        short_final = data['SHORT_FINAL']
        
        final_bb = final_thg - 800 * scores['bid_buy_ucuzluk'] if final_thg > 0 else 0
        final_fb = final_thg - 800 * scores['front_buy_ucuzluk'] if final_thg > 0 else 0  
        final_sas = short_final - 800 * scores['ask_sell_pahalilik'] if short_final > 0 else 0
        final_sfs = short_final - 800 * scores['front_sell_pahalilik'] if short_final > 0 else 0
        
        all_scores[sym] = {
            'group': data['group'],
            'FINAL_THG': final_thg,
            'SHORT_FINAL': short_final,
            'Final_BB': final_bb,
            'Final_FB': final_fb,
            'Final_SAS': final_sas,
            'Final_SFS': final_sfs,
            'bid_buy_ucuzluk': scores['bid_buy_ucuzluk'],
            'ask_sell_pahalilik': scores['ask_sell_pahalilik'],
        }
    
    # Grup bazında Plagr ve Ratgr hesapla
    # Step 1: Grup bazında Final_FB ve Final_SFS ortalamaları
    group_fb_values = defaultdict(list)  # group -> [(sym, Final_FB)]
    group_sfs_values = defaultdict(list)  # group -> [(sym, Final_SFS)]
    
    for sym, sc in all_scores.items():
        grp = sc['group']
        if sc['Final_FB'] > 0:
            group_fb_values[grp].append((sym, sc['Final_FB']))
        if sc['Final_SFS'] > 0:
            group_sfs_values[grp].append((sym, sc['Final_SFS']))
    
    # Step 2: Her grup için sıralama ve ortalama
    result_map = {}  # sym -> {Fbtot, SFStot, GORT, ucuzluk, pahalilik, ...}
    
    for sym in all_scores:
        sc = all_scores[sym]
        grp = sc['group']
        
        # FBPlagr + FBRatgr
        fb_list = group_fb_values.get(grp, [])
        fbtot = 0.0
        if fb_list and sc['Final_FB'] > 0:
            # Sort ascending (en düşük = rank 1)
            sorted_fb = sorted(fb_list, key=lambda x: x[1])
            total_count = len(sorted_fb)
            rank = next((i+1 for i, (s, _) in enumerate(sorted_fb) if s == sym), 0)
            fbplagr = rank / total_count if total_count > 0 else 0
            
            avg_fb = sum(v for _, v in fb_list) / len(fb_list)
            fbratgr = sc['Final_FB'] / avg_fb if avg_fb > 0 else 0
            
            fbtot = fbplagr + fbratgr
        
        # SFSPlagr + SFSRatgr
        sfs_list = group_sfs_values.get(grp, [])
        sfstot = 0.0
        if sfs_list and sc['Final_SFS'] > 0:
            sorted_sfs = sorted(sfs_list, key=lambda x: x[1])
            total_count = len(sorted_sfs)
            rank = next((i+1 for i, (s, _) in enumerate(sorted_sfs) if s == sym), 0)
            sfsplagr = rank / total_count if total_count > 0 else 0
            
            avg_sfs = sum(v for _, v in sfs_list) / len(sfs_list)
            sfsratgr = sc['Final_SFS'] / avg_sfs if avg_sfs > 0 else 0
            
            sfstot = sfsplagr + sfsratgr
        
        # GORT = FINAL_THG (basitleştirilmiş)
        gort = sc['FINAL_THG']
        
        result_map[sym] = {
            'Fbtot': round(fbtot, 4),
            'SFStot': round(sfstot, 4),
            'GORT': round(gort, 2),
            'ucuzluk': round(sc['bid_buy_ucuzluk'], 4),
            'pahalilik': round(sc['ask_sell_pahalilik'], 4),
            'Final_BB': round(sc['Final_BB'], 2),
            'Final_FB': round(sc['Final_FB'], 2),
            'Final_SAS': round(sc['Final_SAS'], 2),
            'Final_SFS': round(sc['Final_SFS'], 2),
            'group': grp,
        }
    
    # Hedef semboller için rapor 
    found = 0
    not_found = []
    for sym in target_symbols:
        if sym in result_map:
            found += 1
        else:
            not_found.append(sym)
    
    print(f"  ✅ Hedef {len(target_symbols)} sembolden {found} tanesi hesaplandı")
    if not_found:
        print(f"  ⚠️ {len(not_found)} sembol dosya gruplarında bulunamadı: {not_found[:10]}")
    
    # Fbtot istatistikleri
    fbtot_vals = [v['Fbtot'] for v in result_map.values() if v['Fbtot'] > 0]
    sfstot_vals = [v['SFStot'] for v in result_map.values() if v['SFStot'] > 0]
    if fbtot_vals:
        print(f"  📈 Fbtot → min={min(fbtot_vals):.4f} max={max(fbtot_vals):.4f} avg={sum(fbtot_vals)/len(fbtot_vals):.4f} ({len(fbtot_vals)} sembol)")
    if sfstot_vals:
        print(f"  📉 SFStot → min={min(sfstot_vals):.4f} max={max(sfstot_vals):.4f} avg={sum(sfstot_vals)/len(sfstot_vals):.4f} ({len(sfstot_vals)} sembol)")
    
    return result_map


if __name__ == "__main__":
    # Test: belirli semboller için hesapla
    test_symbols = ['PRIF PRJ', 'VNO PRN', 'PSA PRS', 'CUBB', 'DUKB', 'ASB PRE',
                     'RF PRE', 'KEY PRK', 'KEY PRJ', 'STT PRG', 'MHLA', 'HWCPZ',
                     'CIM PRD', 'NLY PRF', 'SCHW PRD', 'PSA PRF', 'DLR PRJ']
    
    # prev_close_map yükle (basit versiyon)
    from simulate_dual_process import load_prev_close_map
    pc_map = load_prev_close_map()
    
    result = calculate_fbtot_sfstot_gort(test_symbols, pc_map)
    
    print("\n" + "="*80)
    print("HEDEF SEMBOLLER - HESAPLANAN Fbtot/SFStot:")
    print("="*80)
    for sym in test_symbols:
        if sym in result:
            r = result[sym]
            print(f"  {sym:15s}  Fbtot={r['Fbtot']:.4f}  SFStot={r['SFStot']:.4f}  GORT={r['GORT']:.0f}  "
                  f"ucuz={r['ucuzluk']:+.4f}  pahal={r['pahalilik']:+.4f}  grup={r['group']}")
        else:
            print(f"  {sym:15s}  ❌ Dosya gruplarında bulunamadı")
