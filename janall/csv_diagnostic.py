#!/usr/bin/env python3
"""
CSV Diagnostic Tool for JanAll Application
Bu araç janalldata.csv dosyasının yapısını analiz eder ve olası sorunları tespit eder.
"""

import pandas as pd
import os

def analyze_csv_structure():
    """janalldata.csv dosyasının yapısını analiz et"""
    csv_file = 'janalldata.csv'
    
    print("🔍 JANALL CSV DIAGNOSTIC TOOL")
    print("=" * 50)
    
    if not os.path.exists(csv_file):
        print(f"❌ HATA: {csv_file} dosyası bulunamadı!")
        return
    
    try:
        # CSV'yi oku
        df = pd.read_csv(csv_file)
        
        print(f"✅ Dosya başarıyla okundu: {csv_file}")
        print(f"📊 Toplam satır sayısı: {len(df)}")
        print(f"📋 Toplam kolon sayısı: {len(df.columns)}")
        print()
        
        # Kolon isimlerini listele
        print("📋 MEVCUT KOLONLAR:")
        print("-" * 30)
        for i, col in enumerate(df.columns):
            print(f"{i+1:2d}. {col}")
        print()
        
        # JanAll uygulamasının beklediği kolonları kontrol et
        expected_columns = [
            'PREF IBKR', 'CMON', 'CGRUP', 'FINAL_THG', 'AVG_ADV', 'SMI', 'SHORT_FINAL'
        ]
        
        print("🎯 BEKLENEN KOLONLAR:")
        print("-" * 30)
        missing_columns = []
        for col in expected_columns:
            if col in df.columns:
                print(f"✅ {col}")
            else:
                print(f"❌ {col} - BULUNAMADI!")
                missing_columns.append(col)
        print()
        
        if missing_columns:
            print("⚠️  EKSIK KOLONLAR BULUNDU!")
            print(f"Eksik kolonlar: {', '.join(missing_columns)}")
            print()
        
        # Skor kolonlarını kontrol et
        score_columns = [
            'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
            'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
            'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor', 'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor',
            'Spread'
        ]
        
        print("🏆 SKOR KOLONLARI:")
        print("-" * 30)
        missing_score_columns = []
        for col in score_columns:
            if col in df.columns:
                print(f"✅ {col}")
            else:
                print(f"❌ {col} - BULUNAMADI!")
                missing_score_columns.append(col)
        print()
        
        if missing_score_columns:
            print("⚠️  EKSIK SKOR KOLONLARI BULUNDU!")
            print(f"Eksik skor kolonları: {', '.join(missing_score_columns)}")
            print("💡 update_janalldata_with_scores.py çalıştırmalısınız.")
            print()
        
        # Benchmark kolonlarını kontrol et
        benchmark_columns = ['Benchmark_Type', 'Benchmark_Chg']
        
        print("📈 BENCHMARK KOLONLARI:")
        print("-" * 30)
        missing_benchmark_columns = []
        for col in benchmark_columns:
            if col in df.columns:
                print(f"✅ {col}")
            else:
                print(f"❌ {col} - BULUNAMADI!")
                missing_benchmark_columns.append(col)
        print()
        
        if missing_benchmark_columns:
            print("⚠️  EKSIK BENCHMARK KOLONLARI BULUNDU!")
            print(f"Eksik benchmark kolonları: {', '.join(missing_benchmark_columns)}")
            print("💡 update_janalldata_with_scores.py çalıştırmalısınız.")
            print()
        
        # İlk 5 satırı göster
        print("📄 İLK 5 SATIR ÖNİZLEMESİ:")
        print("-" * 50)
        print(df.head().to_string())
        print()
        
        # Veri tiplerini kontrol et
        print("🔍 VERİ TİPLERİ:")
        print("-" * 30)
        for col in expected_columns:
            if col in df.columns:
                dtype = df[col].dtype
                null_count = df[col].isnull().sum()
                print(f"{col:15s} | {str(dtype):10s} | Null: {null_count}")
        print()
        
        # PREF IBKR kolonunda duplikasyon kontrolü
        if 'PREF IBKR' in df.columns:
            duplicates = df['PREF IBKR'].duplicated().sum()
            if duplicates > 0:
                print(f"⚠️  DUPLIKASYON BULUNDU: {duplicates} adet tekrarlanan ticker!")
                print("Tekrarlanan ticker'lar:")
                duplicated_tickers = df[df['PREF IBKR'].duplicated()]['PREF IBKR'].tolist()
                for ticker in duplicated_tickers:
                    print(f"  - {ticker}")
                print()
            else:
                print("✅ PREF IBKR kolonunda duplikasyon yok.")
                print()
        
        # Özet
        print("📋 ÖZET:")
        print("-" * 20)
        print(f"Toplam ticker sayısı: {len(df) if 'PREF IBKR' in df.columns else 'Bilinmiyor'}")
        print(f"Beklenen kolonların tamamı mevcut: {'✅ Evet' if not missing_columns else '❌ Hayır'}")
        print(f"Skor kolonları mevcut: {'✅ Evet' if not missing_score_columns else '❌ Hayır'}")
        print(f"Benchmark kolonları mevcut: {'✅ Evet' if not missing_benchmark_columns else '❌ Hayır'}")
        
        if missing_columns or missing_score_columns or missing_benchmark_columns:
            print()
            print("🔧 ÖNERİLEN ÇÖZÜMLER:")
            if missing_score_columns or missing_benchmark_columns:
                print("1. janall/update_janalldata_with_scores.py dosyasını çalıştırın")
            if missing_columns:
                print("2. CSV birleştirme işlemini yeniden yapın (merge_csvs.py)")
            print("3. JanAll uygulamasını yeniden başlatın")
        
    except Exception as e:
        print(f"❌ HATA: CSV analizi sırasında hata oluştu: {e}")

if __name__ == "__main__":
    analyze_csv_structure()