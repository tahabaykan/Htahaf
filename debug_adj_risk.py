#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug script for Adj Risk Premium calculation
"""

import pandas as pd

def debug_adj_risk_premium():
    """CFG PRE hissesi için Adj Risk Premium hesaplamasını debug et"""
    
    print("=== ADJ RISK PREMIUM DEBUG ===")
    
    # 1. Treasury yield'larını oku
    print("\n1. Treasury yield'ları:")
    try:
        treasury_df = pd.read_csv('treyield.csv')
        print(treasury_df)
        
        treasury_yields = {}
        for _, row in treasury_df.iterrows():
            treasury_yields[row['Treasury']] = row['Yield']
        
        print(f"\nTreasury yield dict: {treasury_yields}")
        
    except Exception as e:
        print(f"❌ Treasury yield okuma hatası: {e}")
        return
    
    # 2. CFG PRE hissesini bul
    print("\n2. CFG PRE hissesi:")
    try:
        df = pd.read_csv('finekheldkuponlu.csv')
        cfg_row = df[df['PREF IBKR'] == 'CFG PRE']
        
        if cfg_row.empty:
            print("❌ CFG PRE hissesi bulunamadı!")
            return
        
        print(f"CFG PRE bulundu: {len(cfg_row)} satır")
        
        # Gerekli kolonları göster
        cfg_data = cfg_row.iloc[0]
        print(f"Adj Treasury Bench: {cfg_data.get('Adj Treasury Bench', 'YOK')}")
        print(f"2Y Cally: {cfg_data.get('2Y Cally', 'YOK')}")
        print(f"5Y Cally: {cfg_data.get('5Y Cally', 'YOK')}")
        print(f"7Y Cally: {cfg_data.get('7Y Cally', 'YOK')}")
        print(f"10Y Cally: {cfg_data.get('10Y Cally', 'YOK')}")
        print(f"15Y Cally: {cfg_data.get('15Y Cally', 'YOK')}")
        print(f"20Y Cally: {cfg_data.get('20Y Cally', 'YOK')}")
        print(f"30Y Cally: {cfg_data.get('30Y Cally', 'YOK')}")
        
    except Exception as e:
        print(f"❌ CSV okuma hatası: {e}")
        return
    
    # 3. Adj Risk Premium hesapla
    print("\n3. Adj Risk Premium hesaplama:")
    
    adj_bench = cfg_data.get('Adj Treasury Bench', 'US30Y')
    print(f"Adj Treasury Bench: {adj_bench}")
    
    # Cally değerini al
    if adj_bench == 'US2Y':
        cally_value = cfg_data.get('2Y Cally', 0)
    elif adj_bench == 'US5Y':
        cally_value = cfg_data.get('5Y Cally', 0)
    elif adj_bench == 'US7Y':
        cally_value = cfg_data.get('7Y Cally', 0)
    elif adj_bench == 'US10Y':
        cally_value = cfg_data.get('10Y Cally', 0)
    elif adj_bench == 'US15Y':
        cally_value = cfg_data.get('15Y Cally', 0)
    elif adj_bench == 'US20Y':
        cally_value = cfg_data.get('20Y Cally', 0)
    elif adj_bench == 'US30Y':
        cally_value = cfg_data.get('30Y Cally', 0)
    else:
        cally_value = cfg_data.get('30Y Cally', 0)
    
    print(f"Cally değeri ({adj_bench}): {cally_value}")
    print(f"Cally değeri tipi: {type(cally_value)}")
    
    # Treasury yield'ı al
    yield_value = treasury_yields.get(adj_bench, 0)
    print(f"Treasury yield ({adj_bench}): {yield_value}")
    print(f"Treasury yield tipi: {type(yield_value)}")
    
    # Treasury yield'ı float'a çevir
    if isinstance(yield_value, str):
        yield_value_clean = float(yield_value.replace('%', '')) / 100
    else:
        yield_value_clean = float(yield_value) / 100
    
    print(f"Treasury yield (float): {yield_value_clean}")
    
    # Cally değerini float'a çevir
    if isinstance(cally_value, str):
        if cally_value == '':
            cally_value_clean = 0
        else:
            cally_value_clean = float(cally_value)
    else:
        cally_value_clean = float(cally_value) if cally_value else 0
    
    print(f"Cally değeri (float): {cally_value_clean}")
    
    # Koşul kontrolü
    print(f"\nKoşul kontrolü:")
    print(f"cally_value > 0: {cally_value_clean > 0}")
    print(f"yield_value > 0: {yield_value_clean > 0}")
    print(f"cally_value > 0 and yield_value > 0: {cally_value_clean > 0 and yield_value_clean > 0}")
    
    # Adj Risk Premium hesapla
    if cally_value_clean > 0 and yield_value_clean > 0:
        adj_risk_premium = cally_value_clean - yield_value_clean
        print(f"\n✅ Adj Risk Premium hesaplandı: {adj_risk_premium:.6f}")
        print(f"Adj Risk Premium (4 ondalık): {round(adj_risk_premium, 4)}")
    else:
        print(f"\n❌ Adj Risk Premium hesaplanamadı!")
        print(f"Cally değeri: {cally_value_clean}")
        print(f"Yield değeri: {yield_value_clean}")

if __name__ == "__main__":
    debug_adj_risk_premium()

