#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOLCALL_SCORE Debug Script - Detaylı Analiz
"""

import pandas as pd
import numpy as np
import glob
import os

def load_yek_data():
    """YEK dosyalarından Adj Risk Premium verilerini yükle"""
    print("=== YEK Dosyalarından Adj Risk Premium Yükleme ===")
    
    yek_files = glob.glob('yek*.csv')
    print(f"Bulunan YEK dosyaları: {yek_files}")
    
    all_adj_risk_data = {}
    
    for yek_file in yek_files:
        try:
            df = pd.read_csv(yek_file, encoding='utf-8-sig')
            print(f"\n✓ {yek_file} okundu: {len(df)} satır")
            
            if 'Adj Risk Premium' in df.columns:
                # Sadece geçerli Adj Risk Premium değerleri olan satırları al
                valid_data = df[df['Adj Risk Premium'].notna()][['PREF IBKR', 'Adj Risk Premium']]
                print(f"  - Geçerli Adj Risk Premium: {len(valid_data)} satır")
                
                for _, row in valid_data.iterrows():
                    pref = row['PREF IBKR']
                    adj_risk = row['Adj Risk Premium']
                    
                    # Aynı hisse için en yüksek değeri al ve 4 ondalık hane ile yuvarla
                    if pref not in all_adj_risk_data or adj_risk > all_adj_risk_data[pref]:
                        all_adj_risk_data[pref] = round(adj_risk, 4)
                        print(f"    {pref}: {round(adj_risk, 4):.4f}")
            else:
                print(f"  - Adj Risk Premium kolonu yok")
                
        except Exception as e:
            print(f"✗ {yek_file} okunurken hata: {e}")
    
    print(f"\nToplam {len(all_adj_risk_data)} hisse için Adj Risk Premium bulundu")
    return all_adj_risk_data

def analyze_finekheldkuponlu():
    """finekheldkuponlu.csv dosyasını analiz et"""
    print("\n=== finekheldkuponlu.csv Analizi ===")
    
    try:
        df = pd.read_csv('finekheldkuponlu.csv', encoding='utf-8-sig')
        print(f"Dosya yüklendi: {len(df)} satır")
        
        # AFGB ve SOJE hisselerini bul
        afgb_row = df[df['PREF IBKR'] == 'AFGB']
        soje_row = df[df['PREF IBKR'] == 'SOJE']
        
        print("\n=== AFGB Analizi ===")
        if not afgb_row.empty:
            afgb = afgb_row.iloc[0]
            print(f"AFGB verileri:")
            print(f"  - Adj Risk Premium: {afgb.get('Adj Risk Premium', 'YOK')}")
            print(f"  - Final Adj Risk Premium: {afgb.get('Final Adj Risk Premium', 'YOK')}")
            print(f"  - SOLIDITY_SCORE_NORM: {afgb.get('SOLIDITY_SCORE_NORM', 'YOK')}")
            print(f"  - SOLCALL_SCORE: {afgb.get('SOLCALL_SCORE', 'YOK')}")
            print(f"  - SOLCALL_SCORE_NORM: {afgb.get('SOLCALL_SCORE_NORM', 'YOK')}")
            print(f"  - QDI: {afgb.get('QDI', 'YOK')}")
            print(f"  - CUR_YIELD: {afgb.get('CUR_YIELD', 'YOK')}")
        else:
            print("AFGB bulunamadı!")
        
        print("\n=== SOJE Analizi ===")
        if not soje_row.empty:
            soje = soje_row.iloc[0]
            print(f"SOJE verileri:")
            print(f"  - Adj Risk Premium: {soje.get('Adj Risk Premium', 'YOK')}")
            print(f"  - Final Adj Risk Premium: {soje.get('Final Adj Risk Premium', 'YOK')}")
            print(f"  - SOLIDITY_SCORE_NORM: {soje.get('SOLIDITY_SCORE_NORM', 'YOK')}")
            print(f"  - SOLCALL_SCORE: {soje.get('SOLCALL_SCORE', 'YOK')}")
            print(f"  - SOLCALL_SCORE_NORM: {soje.get('SOLCALL_SCORE_NORM', 'YOK')}")
            print(f"  - QDI: {soje.get('QDI', 'YOK')}")
            print(f"  - CUR_YIELD: {soje.get('CUR_YIELD', 'YOK')}")
        else:
            print("SOJE bulunamadı!")
        
        # SOLCALL_SCORE_NORM istatistikleri
        print("\n=== SOLCALL_SCORE_NORM İstatistikleri ===")
        if 'SOLCALL_SCORE_NORM' in df.columns:
            print(df['SOLCALL_SCORE_NORM'].describe())
            print(f"En yüksek 5 SOLCALL_SCORE_NORM:")
            top_5 = df.nlargest(5, 'SOLCALL_SCORE_NORM')[['PREF IBKR', 'SOLCALL_SCORE_NORM']]
            print(top_5.to_string(index=False))
        
        return df
        
    except Exception as e:
        print(f"finekheldkuponlu.csv okuma hatası: {e}")
        return None

def test_solcall_calculation():
    """SOLCALL_SCORE hesaplamasını test et"""
    print("\n=== SOLCALL_SCORE Hesaplama Testi ===")
    
    # YEK verilerini yükle
    adj_risk_data = load_yek_data()
    
    # finekheldkuponlu.csv'yi yükle
    df = analyze_finekheldkuponlu()
    if df is None:
        return
    
    # AFGB ve SOJE için manuel hesaplama
    print("\n=== Manuel SOLCALL_SCORE Hesaplama ===")
    
    for stock in ['AFGB', 'SOJE']:
        stock_row = df[df['PREF IBKR'] == stock]
        if not stock_row.empty:
            row = stock_row.iloc[0]
            
            # YEK'den Adj Risk Premium al
            adj_risk_yek = adj_risk_data.get(stock, None)
            solidity = row.get('SOLIDITY_SCORE_NORM', 0)
            
            print(f"\n{stock} Analizi:")
            print(f"  - YEK'den Adj Risk Premium: {adj_risk_yek}")
            print(f"  - CSV'den Adj Risk Premium: {row.get('Adj Risk Premium', 'YOK')}")
            print(f"  - SOLIDITY_SCORE_NORM: {solidity}")
            
            if adj_risk_yek is not None:
                # Manuel hesaplama - yeni formül
                manual_solcall = (adj_risk_yek * 1525) + (solidity * 0.24)
                print(f"  - Manuel SOLCALL_SCORE: {manual_solcall:.2f}")
                print(f"  - CSV'den SOLCALL_SCORE: {row.get('SOLCALL_SCORE', 'YOK')}")
                print(f"  - CSV'den SOLCALL_SCORE_NORM: {row.get('SOLCALL_SCORE_NORM', 'YOK')}")
            else:
                print(f"  - YEK'de {stock} bulunamadı!")

def main():
    """Ana fonksiyon"""
    print("=== SOLCALL_SCORE Detaylı Debug ===")
    
    # YEK verilerini yükle
    adj_risk_data = load_yek_data()
    
    # finekheldkuponlu.csv'yi analiz et
    df = analyze_finekheldkuponlu()
    
    # SOLCALL_SCORE hesaplamasını test et
    test_solcall_calculation()
    
    print("\n=== Debug Tamamlandı ===")

if __name__ == '__main__':
    main() 