#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
15 Aralık 2024 Manuel Yield Veri Girişi
CNBC'den çekilemeyen yield verilerini manuel olarak girmek için
"""

import pandas as pd
import json
import os

def get_manual_yields():
    """Manuel yield verilerini al"""
    
    # Mevcut yield dosyasını kontrol et
    yield_file = 'manual_yields_dec15_2024.json'
    
    if os.path.exists(yield_file):
        print(f"📁 Mevcut yield dosyası bulundu: {yield_file}")
        with open(yield_file, 'r') as f:
            manual_yields = json.load(f)
        print(f"📊 {len(manual_yields)} hisse için yield verisi mevcut")
        return manual_yields
    
    print("🎯 15 Aralık 2024 için manuel yield verilerini girin")
    print("CNBC'den çekilemeyen yield verilerini manuel olarak gireceksiniz")
    print("Çıkmak için 'q' yazın")
    print("-" * 50)
    
    manual_yields = {}
    
    # Örnek hisseler
    sample_stocks = [
        'FCNCP', 'AFGB', 'SOJD', 'PRS', 'CFG PRE',
        'BAC PRS', 'PSA PRS', 'USB PRS', 'NRUC', 'GL PRD'
    ]
    
    print("📋 Örnek hisseler:")
    for i, stock in enumerate(sample_stocks, 1):
        print(f"  {i}. {stock}")
    
    print("\n💡 Yield değerlerini % cinsinden girin (örn: 6.67)")
    
    while True:
        ticker = input("\n🎯 Hisse kodu (q=çıkış): ").strip().upper()
        
        if ticker == 'Q':
            break
            
        if not ticker:
            print("❌ Geçersiz hisse kodu!")
            continue
            
        try:
            yield_value = float(input(f"📊 {ticker} yield değeri (%): "))
            manual_yields[ticker] = yield_value
            print(f"✅ {ticker}: {yield_value}% kaydedildi")
        except ValueError:
            print("❌ Geçersiz yield değeri!")
            continue
    
    # Verileri kaydet
    if manual_yields:
        with open(yield_file, 'w') as f:
            json.dump(manual_yields, f, indent=2)
        print(f"\n💾 {len(manual_yields)} hisse için yield verileri kaydedildi: {yield_file}")
    
    return manual_yields

def update_csv_with_manual_yields():
    """CSV dosyalarını manuel yield verileriyle güncelle"""
    
    manual_yields = get_manual_yields()
    if not manual_yields:
        print("❌ Manuel yield verisi bulunamadı!")
        return
    
    # CSV dosyalarını bul
    csv_files = [f for f in os.listdir('.') if f.startswith('advek') and f.endswith('.csv')]
    
    print(f"\n📁 {len(csv_files)} CSV dosyası güncellenecek...")
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            updated_count = 0
            
            for ticker, yield_value in manual_yields.items():
                # Hisseyi bul ve yield'i güncelle
                mask = df['PREF IBKR'].str.contains(ticker, case=False, na=False)
                if mask.any():
                    df.loc[mask, 'CUR_YIELD'] = yield_value
                    updated_count += mask.sum()
                    print(f"  ✅ {csv_file}: {ticker} yield {yield_value}% olarak güncellendi")
            
            if updated_count > 0:
                df.to_csv(csv_file, index=False)
                print(f"  💾 {csv_file} kaydedildi ({updated_count} satır güncellendi)")
            
        except Exception as e:
            print(f"❌ {csv_file} güncellenirken hata: {e}")
    
    print("\n🎉 Manuel yield güncellemesi tamamlandı!")

def show_current_yields():
    """Mevcut yield verilerini göster"""
    
    manual_yields = get_manual_yields()
    if not manual_yields:
        print("❌ Manuel yield verisi bulunamadı!")
        return
    
    print("\n📊 15 Aralık 2024 Manuel Yield Verileri:")
    print("-" * 40)
    
    for ticker, yield_value in sorted(manual_yields.items()):
        print(f"  {ticker}: {yield_value}%")
    
    print(f"\n📈 Toplam {len(manual_yields)} hisse için yield verisi mevcut")

if __name__ == "__main__":
    print("🎯 15 Aralık 2024 Manuel Yield Veri Yöneticisi")
    print("=" * 50)
    
    while True:
        print("\n📋 Seçenekler:")
        print("  1. Manuel yield verilerini gir/güncelle")
        print("  2. CSV dosyalarını manuel yield ile güncelle")
        print("  3. Mevcut yield verilerini göster")
        print("  4. Çıkış")
        
        choice = input("\n🎯 Seçiminiz (1-4): ").strip()
        
        if choice == '1':
            get_manual_yields()
        elif choice == '2':
            update_csv_with_manual_yields()
        elif choice == '3':
            show_current_yields()
        elif choice == '4':
            print("👋 Çıkılıyor...")
            break
        else:
            print("❌ Geçersiz seçim!") 