#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AFGB Debug Scripti
AFGB'nin TIME TO DIV hesaplama sorununu analiz eder
"""

import pandas as pd
from datetime import datetime

def debug_afgb():
    """AFGB'nin TIME TO DIV hesaplama sorununu analiz eder"""
    print("🔍 AFGB Debug Analizi")
    print("=" * 40)
    
    # janalldata.csv'yi oku
    df = pd.read_csv('janalldata.csv')
    
    # AFGB'yi bul
    afgb_mask = df['PREF IBKR'] == 'AFGB'
    afgb_row = df[afgb_mask]
    
    if afgb_row.empty:
        print("❌ AFGB bulunamadı!")
        return
    
    row = afgb_row.iloc[0]
    
    print(f"📊 AFGB Mevcut Veriler:")
    print(f"   PREF IBKR: {row['PREF IBKR']}")
    print(f"   Last Price: {row['Last Price']}")
    print(f"   DIV AMOUNT: {row['DIV AMOUNT']}")
    print(f"   EX-DIV DATE: {row['EX-DIV DATE']}")
    print(f"   TIME TO DIV: {row['TIME TO DIV']}")
    print(f"   Div adj.price: {row['Div adj.price']}")
    
    # TIME TO DIV hesaplama analizi
    print(f"\n🧮 TIME TO DIV Hesaplama Analizi:")
    
    ex_div_date_str = row['EX-DIV DATE']
    if pd.notna(ex_div_date_str) and ex_div_date_str != '':
        print(f"   Mevcut EX-DIV DATE: {ex_div_date_str}")
        
        # Tarih parse et
        if '/' in str(ex_div_date_str):
            parts = str(ex_div_date_str).split('/')
            if len(parts) == 3:
                month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                ex_div_date = datetime(year, month, day)
                
                current_date = datetime.now()
                days_diff = (ex_div_date - current_date).days
                
                print(f"   📅 Ex-Div Date: {ex_div_date.strftime('%Y-%m-%d')}")
                print(f"   📅 Bugün: {current_date.strftime('%Y-%m-%d')}")
                print(f"   📅 Gün farkı: {days_diff}")
                
                # TIME TO DIV hesapla
                if days_diff <= 0:
                    time_to_div = 90 + days_diff
                    print(f"   📊 Ex-div date geçmiş, TIME TO DIV = 90 + {days_diff} = {time_to_div}")
                else:
                    time_to_div = days_diff
                    print(f"   📊 Ex-div date gelecekte, TIME TO DIV = {days_diff}")
                
                print(f"   📊 Hesaplanan TIME TO DIV: {time_to_div}")
                print(f"   📊 Mevcut TIME TO DIV: {row['TIME TO DIV']}")
                
                if time_to_div != row['TIME TO DIV']:
                    print(f"   ❌ TIME TO DIV uyumsuzluğu!")
                    print(f"   ❌ Hesaplanan: {time_to_div}, Mevcut: {row['TIME TO DIV']}")
                else:
                    print(f"   ✅ TIME TO DIV doğru")
                
                # Div adj.price hesapla
                if time_to_div >= 0:
                    last_price = row['Last Price']
                    div_amount = row['DIV AMOUNT']
                    
                    if not pd.isna(last_price) and not pd.isna(div_amount):
                        div_adj_price = last_price - (((90 - time_to_div) / 90) * div_amount)
                        
                        print(f"\n💰 Div adj.price Hesaplama:")
                        print(f"   Last Price: {last_price}")
                        print(f"   TIME TO DIV: {time_to_div}")
                        print(f"   DIV AMOUNT: {div_amount}")
                        print(f"   Formül: {last_price} - (((90-{time_to_div})/90) * {div_amount})")
                        print(f"   Hesaplanan Div adj.price: {div_adj_price:.2f}")
                        print(f"   Mevcut Div adj.price: {row['Div adj.price']}")
                        
                        if abs(div_adj_price - row['Div adj.price']) > 0.01:
                            print(f"   ❌ Div adj.price uyumsuzluğu!")
                        else:
                            print(f"   ✅ Div adj.price doğru")
                    else:
                        print(f"   ❌ Last Price veya DIV AMOUNT eksik!")
                else:
                    print(f"   ❌ TIME TO DIV negatif: {time_to_div}")
            else:
                print(f"   ❌ EX-DIV DATE formatı hatalı: {ex_div_date_str}")
        else:
            print(f"   ❌ EX-DIV DATE formatı hatalı: {ex_div_date_str}")
    else:
        print(f"   ❌ EX-DIV DATE eksik veya boş!")

if __name__ == "__main__":
    debug_afgb()
