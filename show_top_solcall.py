#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
En Yüksek SOLCALL_SCORE'lu Hisseleri Göster
Tüm finek*.csv dosyalarından en yüksek SOLCALL_SCORE'lu hisseleri listeler
"""

import pandas as pd
import glob
import os

def load_and_show_top_solcall():
    """Tüm finek dosyalarından en yüksek SOLCALL_SCORE'lu hisseleri göster"""
    
    # Tüm finek dosyalarını bul
    finek_files = glob.glob('finek*.csv')
    
    if not finek_files:
        print("HATA: Hiç finek*.csv dosyası bulunamadı!")
        return
    
    print("=== EN YÜKSEK SOLCALL_SCORE'LU HİSSELER ===\n")
    
    for file in sorted(finek_files):
        try:
            # Dosyayı yükle
            df = pd.read_csv(file, encoding='utf-8-sig')
            
            # SOLCALL_SCORE kolonu var mı kontrol et
            if 'SOLCALL_SCORE' not in df.columns:
                print(f"⚠️ {file}: SOLCALL_SCORE kolonu bulunamadı!")
                continue
            
            # NaN değerleri filtrele
            df_clean = df.dropna(subset=['SOLCALL_SCORE'])
            
            if len(df_clean) == 0:
                print(f"⚠️ {file}: Geçerli SOLCALL_SCORE değeri bulunamadı!")
                continue
            
            # En yüksek 10 SOLCALL_SCORE'lu hisseyi al
            top_10 = df_clean.nlargest(10, 'SOLCALL_SCORE')
            
            print(f"📊 {file} - Top 10 SOLCALL_SCORE")
            print("=" * 80)
            
            # Gerekli kolonları seç
            display_cols = ['PREF IBKR', 'SOLCALL_SCORE']
            
            # Eğer varsa diğer önemli kolonları da ekle
            optional_cols = ['SOLIDITY_SCORE_NORM', 'Adj risk premium', 'CUR_YIELD', 'FINAL_THG']
            for col in optional_cols:
                if col in df.columns:
                    display_cols.append(col)
            
            # Sonuçları göster
            result_df = top_10[display_cols].round(2)
            print(result_df.to_string(index=False))
            
            # İstatistikler
            print(f"\n📈 İstatistikler:")
            print(f"   Toplam hisse sayısı: {len(df)}")
            print(f"   Geçerli SOLCALL_SCORE sayısı: {len(df_clean)}")
            print(f"   En yüksek SOLCALL_SCORE: {df_clean['SOLCALL_SCORE'].max():.2f}")
            print(f"   En düşük SOLCALL_SCORE: {df_clean['SOLCALL_SCORE'].min():.2f}")
            print(f"   Ortalama SOLCALL_SCORE: {df_clean['SOLCALL_SCORE'].mean():.2f}")
            
            print("\n" + "=" * 80 + "\n")
            
        except Exception as e:
            print(f"❌ {file} okunurken hata: {e}")
            print("=" * 80 + "\n")

def show_specific_file(file_name):
    """Belirli bir dosyayı detaylı göster"""
    try:
        if not os.path.exists(file_name):
            print(f"HATA: {file_name} dosyası bulunamadı!")
            return
        
        df = pd.read_csv(file_name, encoding='utf-8-sig')
        
        if 'SOLCALL_SCORE' not in df.columns:
            print(f"⚠️ {file_name}: SOLCALL_SCORE kolonu bulunamadı!")
            print(f"Mevcut kolonlar: {list(df.columns)}")
            return
        
        # NaN değerleri filtrele
        df_clean = df.dropna(subset=['SOLCALL_SCORE'])
        
        print(f"🎯 {file_name} - DETAYLI SOLCALL_SCORE ANALİZİ")
        print("=" * 100)
        
        # En yüksek 20 SOLCALL_SCORE'lu hisseyi al
        top_20 = df_clean.nlargest(20, 'SOLCALL_SCORE')
        
        # Gerekli kolonları seç
        display_cols = ['PREF IBKR', 'SOLCALL_SCORE']
        optional_cols = ['SOLIDITY_SCORE_NORM', 'Adj risk premium', 'CUR_YIELD', 'FINAL_THG', 'Last Price']
        
        for col in optional_cols:
            if col in df.columns:
                display_cols.append(col)
        
        # Sonuçları göster
        result_df = top_20[display_cols].round(2)
        print(result_df.to_string(index=False))
        
        # Detaylı istatistikler
        print(f"\n📊 DETAYLI İSTATİSTİKLER:")
        print(f"   Toplam hisse sayısı: {len(df)}")
        print(f"   Geçerli SOLCALL_SCORE sayısı: {len(df_clean)}")
        print(f"   NaN SOLCALL_SCORE sayısı: {len(df) - len(df_clean)}")
        print(f"   En yüksek SOLCALL_SCORE: {df_clean['SOLCALL_SCORE'].max():.2f}")
        print(f"   En düşük SOLCALL_SCORE: {df_clean['SOLCALL_SCORE'].min():.2f}")
        print(f"   Ortalama SOLCALL_SCORE: {df_clean['SOLCALL_SCORE'].mean():.2f}")
        print(f"   Medyan SOLCALL_SCORE: {df_clean['SOLCALL_SCORE'].median():.2f}")
        print(f"   Standart sapma: {df_clean['SOLCALL_SCORE'].std():.2f}")
        
        # SOLCALL_SCORE dağılımı
        print(f"\n📈 SOLCALL_SCORE DAĞILIMI:")
        percentiles = [10, 25, 50, 75, 90, 95, 99]
        for p in percentiles:
            value = df_clean['SOLCALL_SCORE'].quantile(p/100)
            print(f"   %{p}: {value:.2f}")
        
    except Exception as e:
        print(f"❌ {file_name} okunurken hata: {e}")

def main():
    """Ana fonksiyon"""
    print("🔍 SOLCALL_SCORE ANALİZ SCRIPTİ")
    print("=" * 50)
    
    # 1. Tüm dosyaları göster
    print("\n1️⃣ TÜM DOSYALAR - TOP 10 SOLCALL_SCORE")
    load_and_show_top_solcall()
    
    # 2. Özel dosya göster
    print("\n2️⃣ ÖZEL DOSYA - finekheldkuponlu.csv")
    show_specific_file('finekheldkuponlu.csv')

if __name__ == '__main__':
    main() 