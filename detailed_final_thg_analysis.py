import pandas as pd
import os
import numpy as np

def detailed_final_thg_analysis():
    """Detailed analysis of FINAL THG scores for each CSV file"""
    
    # List of files to analyze
    files_to_analyze = [
        'ekheldbesmaturlu.csv',
        'finekheldcilizyeniyedi.csv', 
        'finekheldcommonsuz.csv',
        'finekhelddeznff.csv',
        'finekheldff.csv',
        'finekheldflr.csv',
        'finekheldgarabetaltiyedi.csv',
        'finekheldkuponlu.csv',
        'finekheldkuponlukreciliz.csv',
        'finekheldkuponlukreorta.csv',
        'finekheldnff.csv',
        'finekheldotelremorta.csv',
        'finekheldsolidbig.csv',
        'finekheldtitrekhc.csv',
        'finekhighmatur.csv',
        'fineknotbesmaturlu.csv',
        'fineknotcefilliquid.csv',
        'fineknottitrekhc.csv',
        'finekrumoreddanger.csv',
        'fineksalakilliquid.csv',
        'finekshitremhc.csv'
    ]
    
    print("=" * 100)
    print("DETAYLI FINAL THG ANALİZ RAPORU - HER DOSYA İÇİN AYRINTILI SONUÇLAR")
    print("=" * 100)
    
    for i, filename in enumerate(files_to_analyze, 1):
        print(f"\n{'='*80}")
        print(f"📁 DOSYA {i}: {filename}")
        print(f"{'='*80}")
        
        if not os.path.exists(filename):
            print(f"❌ Dosya bulunamadı: {filename}")
            continue
            
        try:
            # Read CSV file
            df = pd.read_csv(filename)
            
            # Check if FINAL_THG column exists
            if 'FINAL_THG' not in df.columns:
                print(f"⚠️  FINAL_THG sütunu bulunamadı!")
                print(f"   Mevcut sütunlar: {list(df.columns)}")
                print(f"   Bu dosyada FINAL THG hesaplaması yapılmamış.")
                continue
            
            # Filter out rows where FINAL_THG is NaN or empty
            df_clean = df.dropna(subset=['FINAL_THG'])
            df_clean = df_clean[df_clean['FINAL_THG'] != '']
            
            if len(df_clean) == 0:
                print(f"⚠️  FINAL_THG verisi bulunamadı (tüm değerler boş)")
                print(f"   Bu dosyada FINAL THG hesaplaması yapılmış ama veriler boş.")
                continue
            
            # Convert FINAL_THG to numeric, handling any string values
            df_clean['FINAL_THG'] = pd.to_numeric(df_clean['FINAL_THG'], errors='coerce')
            df_clean = df_clean.dropna(subset=['FINAL_THG'])
            
            if len(df_clean) == 0:
                print(f"⚠️  Geçerli FINAL_THG sayısal verisi bulunamadı")
                continue
            
            # Get stock identifier (PREF IBKR or first column)
            stock_id_col = df_clean.columns[0] if len(df_clean.columns) > 0 else 'Unknown'
            
            # Sort by FINAL_THG
            df_sorted = df_clean.sort_values('FINAL_THG', ascending=False)
            
            # Get best 5 and worst 5
            best_5 = df_sorted.head(5)
            worst_5 = df_sorted.tail(5)
            
            print(f"✅ FINAL_THG verisi bulundu - {len(df_clean)} geçerli kayıt")
            print(f"📊 FINAL_THG aralığı: {df_clean['FINAL_THG'].min():.2f} - {df_clean['FINAL_THG'].max():.2f}")
            print(f"📊 FINAL_THG ortalaması: {df_clean['FINAL_THG'].mean():.2f}")
            print(f"📊 FINAL_THG medyanı: {df_clean['FINAL_THG'].median():.2f}")
            
            print(f"\n🏆 EN İYİ 5 FINAL THG SKORU:")
            print("-" * 60)
            print(f"{'Sıra':<4} {'Hisse Kodu':<15} {'FINAL THG':<12} {'Sektör':<15} {'Kredi Skoru':<12}")
            print("-" * 60)
            for idx, row in best_5.iterrows():
                rank = idx + 1
                stock_id = row[stock_id_col] if stock_id_col in row else f"Row {idx}"
                final_thg = row['FINAL_THG']
                sector = row.get('Sector', 'N/A') if 'Sector' in row else 'N/A'
                credit_score = row.get('CRDT_SCORE', 'N/A') if 'CRDT_SCORE' in row else 'N/A'
                print(f"{rank:<4} {stock_id:<15} {final_thg:<12.2f} {sector:<15} {credit_score:<12}")
            
            print(f"\n📉 EN KÖTÜ 5 FINAL THG SKORU:")
            print("-" * 60)
            print(f"{'Sıra':<4} {'Hisse Kodu':<15} {'FINAL THG':<12} {'Sektör':<15} {'Kredi Skoru':<12}")
            print("-" * 60)
            for idx, row in worst_5.iterrows():
                rank = len(df_sorted) - 4 + (idx - len(df_sorted) + 5)
                stock_id = row[stock_id_col] if stock_id_col in row else f"Row {idx}"
                final_thg = row['FINAL_THG']
                sector = row.get('Sector', 'N/A') if 'Sector' in row else 'N/A'
                credit_score = row.get('CRDT_SCORE', 'N/A') if 'CRDT_SCORE' in row else 'N/A'
                print(f"{rank:<4} {stock_id:<15} {final_thg:<12.2f} {sector:<15} {credit_score:<12}")
            
            # Additional statistics
            print(f"\n📈 İSTATİSTİKLER:")
            print(f"   • Toplam hisse sayısı: {len(df_clean)}")
            print(f"   • En yüksek FINAL THG: {df_clean['FINAL_THG'].max():.2f}")
            print(f"   • En düşük FINAL THG: {df_clean['FINAL_THG'].min():.2f}")
            print(f"   • Ortalama: {df_clean['FINAL_THG'].mean():.2f}")
            print(f"   • Standart sapma: {df_clean['FINAL_THG'].std():.2f}")
            
            # Show distribution
            print(f"\n📊 DAĞILIM:")
            q25 = df_clean['FINAL_THG'].quantile(0.25)
            q50 = df_clean['FINAL_THG'].quantile(0.50)
            q75 = df_clean['FINAL_THG'].quantile(0.75)
            print(f"   • 25. persentil: {q25:.2f}")
            print(f"   • 50. persentil (medyan): {q50:.2f}")
            print(f"   • 75. persentil: {q75:.2f}")
            
        except Exception as e:
            print(f"❌ Hata: {str(e)}")
    
    print(f"\n{'='*100}")
    print("ANALİZ TAMAMLANDI")
    print(f"{'='*100}")

if __name__ == "__main__":
    detailed_final_thg_analysis() 