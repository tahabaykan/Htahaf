import pandas as pd
import numpy as np
import os

def analyze_long_short_positions_new():
    """Her CSV dosyası için long ve short pozisyonları analiz et - Yeni threshold'lar"""
    
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
    
    all_long_positions = []
    all_short_positions = []
    files_without_final_thg = []
    files_with_empty_final_thg = []
    
    print("=== LONG & SHORT POZİSYON ANALİZİ (GÜNCELLENMİŞ THRESHOLD'LAR) ===")
    print("LONG: Top %30 + Ortalama * 1.28'den büyük")
    print("SHORT: Bottom %30 + Ortalama * 0.4'ten küçük")
    print("=" * 60)
    
    for filename in files_to_analyze:
        if not os.path.exists(filename):
            print(f"❌ {filename} bulunamadı")
            continue
            
        try:
            df = pd.read_csv(filename)
            
            # FINAL_THG sütunu kontrolü
            if 'FINAL_THG' not in df.columns:
                files_without_final_thg.append(filename)
                print(f"❌ {filename}: FINAL_THG sütunu yok")
                continue
            
            # FINAL_THG değerlerini numeric yap
            df['FINAL_THG'] = pd.to_numeric(df['FINAL_THG'], errors='coerce')
            
            # Boş değerleri kontrol et
            valid_final_thg = df['FINAL_THG'].dropna()
            if len(valid_final_thg) == 0:
                files_with_empty_final_thg.append(filename)
                print(f"⚠️  {filename}: FINAL_THG değerleri boş")
                continue
            
            # Ortalama hesapla
            avg_final_thg = valid_final_thg.mean()
            
            # Threshold'ları hesapla
            long_threshold = avg_final_thg * 1.28
            short_threshold = avg_final_thg * 0.4
            
            # Top %30 ve Bottom %30 hesapla
            top_30_percentile = valid_final_thg.quantile(0.70)  # Top %30 = 70. percentile'dan büyük
            bottom_30_percentile = valid_final_thg.quantile(0.30)  # Bottom %30 = 30. percentile'dan küçük
            
            # LONG pozisyonları: Top %30 + threshold'dan büyük
            long_candidates = df[
                (df['FINAL_THG'] >= top_30_percentile) & 
                (df['FINAL_THG'] > long_threshold)
            ].copy()
            
            # SHORT pozisyonları: Bottom %30 + threshold'dan küçük
            short_candidates = df[
                (df['FINAL_THG'] <= bottom_30_percentile) & 
                (df['FINAL_THG'] < short_threshold)
            ].copy()
            
            # Sonuçları kaydet
            if len(long_candidates) > 0:
                long_candidates['source_file'] = filename
                long_candidates['avg_final_thg'] = avg_final_thg
                long_candidates['long_threshold'] = long_threshold
                long_candidates['percentile_70'] = top_30_percentile
                all_long_positions.append(long_candidates)
            
            if len(short_candidates) > 0:
                short_candidates['source_file'] = filename
                short_candidates['avg_final_thg'] = avg_final_thg
                short_candidates['short_threshold'] = short_threshold
                all_short_positions.append(short_candidates)
            
            print(f"📊 {filename}:")
            print(f"   Ortalama FINAL_THG: {avg_final_thg:.2f}")
            print(f"   LONG threshold: {long_threshold:.2f} (Ortalama * 1.28)")
            print(f"   SHORT threshold: {short_threshold:.2f} (Ortalama * 0.4)")
            print(f"   Top %30 threshold: {top_30_percentile:.2f}")
            print(f"   Bottom %30 threshold: {bottom_30_percentile:.2f}")
            print(f"   LONG pozisyonlar: {len(long_candidates)}")
            print(f"   SHORT pozisyonlar: {len(short_candidates)}")
            print()
            
        except Exception as e:
            print(f"❌ {filename} işlenirken hata: {str(e)}")
            continue
    
    # Sonuçları birleştir
    if all_long_positions:
        combined_long = pd.concat(all_long_positions, ignore_index=True)
        combined_long = combined_long.sort_values('FINAL_THG', ascending=False)
        
        # Duplicate kontrolü
        before_dedup = len(combined_long)
        combined_long = combined_long.drop_duplicates(subset=['PREF IBKR'], keep='first')
        after_dedup = len(combined_long)
        
        print("=" * 60)
        print("🏆 LONG LİSTESİ (Top %30 + Ortalama * 1.28'den büyük)")
        print("=" * 60)
        print(f"Toplam LONG pozisyon: {len(combined_long)}")
        if before_dedup != after_dedup:
            print(f"⚠️  {before_dedup - after_dedup} adet duplicate temizlendi")
        print()
        
        # Her dosya için ayrı ayrı göster
        for filename in files_to_analyze:
            file_long = combined_long[combined_long['source_file'] == filename]
            if len(file_long) > 0:
                print(f"📁 {filename} ({len(file_long)} LONG):")
                for _, row in file_long.head(10).iterrows():
                    print(f"   {row['PREF IBKR']}: {row['FINAL_THG']:.2f} "
                          f"(Ort: {row['avg_final_thg']:.2f}, Thr: {row['long_threshold']:.2f})")
                print()
        
        # En yüksek 10 LONG pozisyon
        print("🔥 EN YÜKSEK 10 LONG POZİSYON:")
        for _, row in combined_long.head(10).iterrows():
            print(f"   {row['PREF IBKR']} ({row['source_file']}): {row['FINAL_THG']:.2f}")
        print()
        
        # CSV olarak kaydet
        combined_long.to_csv('long_positions_new.csv', index=False)
        print("💾 LONG pozisyonlar 'long_positions_new.csv' dosyasına kaydedildi")
    
    if all_short_positions:
        combined_short = pd.concat(all_short_positions, ignore_index=True)
        combined_short = combined_short.sort_values('FINAL_THG', ascending=True)
        
        # Duplicate kontrolü
        before_dedup = len(combined_short)
        combined_short = combined_short.drop_duplicates(subset=['PREF IBKR'], keep='first')
        after_dedup = len(combined_short)
        
        print("=" * 60)
        print("📉 SHORT LİSTESİ (Bottom %30 + Ortalama * 0.4'ten küçük)")
        print("=" * 60)
        print(f"Toplam SHORT pozisyon: {len(combined_short)}")
        if before_dedup != after_dedup:
            print(f"⚠️  {before_dedup - after_dedup} adet duplicate temizlendi")
        print()
        
        # Her dosya için ayrı ayrı göster
        for filename in files_to_analyze:
            file_short = combined_short[combined_short['source_file'] == filename]
            if len(file_short) > 0:
                print(f"📁 {filename} ({len(file_short)} SHORT):")
                for _, row in file_short.head(10).iterrows():
                    print(f"   {row['PREF IBKR']}: {row['FINAL_THG']:.2f} "
                          f"(Ort: {row['avg_final_thg']:.2f}, Thr: {row['short_threshold']:.2f})")
                print()
        
        # En düşük 10 SHORT pozisyon
        print("💀 EN DÜŞÜK 10 SHORT POZİSYON:")
        for _, row in combined_short.head(10).iterrows():
            print(f"   {row['PREF IBKR']} ({row['source_file']}): {row['FINAL_THG']:.2f}")
        print()
        
        # CSV olarak kaydet
        combined_short.to_csv('short_positions_new.csv', index=False)
        print("💾 SHORT pozisyonlar 'short_positions_new.csv' dosyasına kaydedildi")
    
    # Özet istatistikler
    print("=" * 60)
    print("📊 ÖZET İSTATİSTİKLER")
    print("=" * 60)
    print(f"✅ FINAL THG verisi olan dosyalar: {len(files_to_analyze) - len(files_without_final_thg) - len(files_with_empty_final_thg)}")
    print(f"❌ FINAL THG sütunu olmayan dosyalar: {len(files_without_final_thg)}")
    print(f"⚠️  FINAL THG verisi boş olan dosyalar: {len(files_with_empty_final_thg)}")
    
    if all_long_positions:
        print(f"🏆 Toplam LONG pozisyon: {len(combined_long)}")
    if all_short_positions:
        print(f"📉 Toplam SHORT pozisyon: {len(combined_short)}")
    
    if all_long_positions and all_short_positions:
        long_short_ratio = len(combined_long) / len(combined_short)
        print(f"📈 LONG/SHORT oranı: {long_short_ratio:.2f}:1")
    
    print()
    print("🎯 GÜNCELLENMİŞ THRESHOLD'LAR:")
    print("   LONG: Top %30 + Ortalama * 1.28'den büyük")
    print("   SHORT: Bottom %30 + Ortalama * 0.4'ten küçük")
    print("   Bu ayarlar daha dengeli LONG/SHORT pozisyonları üretir")

if __name__ == "__main__":
    analyze_long_short_positions_new() 