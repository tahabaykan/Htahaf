import pandas as pd
import numpy as np
import os

def analyze_long_short_positions():
    """Her CSV dosyası için long ve short pozisyonları analiz et"""
    
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
    
    all_results = {}
    
    print("=" * 100)
    print("LONG & SHORT POZİSYON ANALİZİ - FINAL THG SKORUNA GÖRE")
    print("=" * 100)
    print("📊 LONG LIST: Top %35 (Ortalama * 1.75'ten büyük)")
    print("📉 SHORT LIST: Bottom %30 (Ortalama * 0.6'dan küçük)")
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
                continue
            
            # Filter out rows where FINAL_THG is NaN or empty
            df_clean = df.dropna(subset=['FINAL_THG'])
            df_clean = df_clean[df_clean['FINAL_THG'] != '']
            
            if len(df_clean) == 0:
                print(f"⚠️  FINAL_THG verisi bulunamadı")
                continue
            
            # Convert FINAL_THG to numeric
            df_clean['FINAL_THG'] = pd.to_numeric(df_clean['FINAL_THG'], errors='coerce')
            df_clean = df_clean.dropna(subset=['FINAL_THG'])
            
            if len(df_clean) == 0:
                print(f"⚠️  Geçerli FINAL_THG sayısal verisi bulunamadı")
                continue
            
            # Get stock identifier
            stock_id_col = df_clean.columns[0] if len(df_clean.columns) > 0 else 'Unknown'
            
            # Calculate statistics
            avg_final_thg = df_clean['FINAL_THG'].mean()
            min_final_thg = df_clean['FINAL_THG'].min()
            max_final_thg = df_clean['FINAL_THG'].max()
            total_stocks = len(df_clean)
            
            print(f"✅ FINAL_THG verisi bulundu - {total_stocks} geçerli hisse")
            print(f"📊 Ortalama FINAL_THG: {avg_final_thg:.2f}")
            print(f"📊 FINAL_THG aralığı: {min_final_thg:.2f} - {max_final_thg:.2f}")
            
            # Calculate thresholds
            long_threshold = avg_final_thg * 1.75
            short_threshold = avg_final_thg * 0.6
            
            print(f"🎯 LONG threshold (Ortalama * 1.75): {long_threshold:.2f}")
            print(f"🎯 SHORT threshold (Ortalama * 0.6): {short_threshold:.2f}")
            
            # Calculate percentiles
            top_35_count = max(1, int(total_stocks * 0.35))  # En az 1 hisse
            bottom_30_count = max(1, int(total_stocks * 0.30))  # En az 1 hisse
            
            print(f"📈 Top %35 hisse sayısı: {top_35_count}")
            print(f"📉 Bottom %30 hisse sayısı: {bottom_30_count}")
            
            # Sort by FINAL_THG
            df_sorted = df_clean.sort_values('FINAL_THG', ascending=False)
            
            # Get top 35% candidates
            top_35_candidates = df_sorted.head(top_35_count)
            
            # Get bottom 30% candidates
            bottom_30_candidates = df_sorted.tail(bottom_30_count)
            
            # Filter LONG list (top 35% AND above threshold)
            long_list = top_35_candidates[top_35_candidates['FINAL_THG'] > long_threshold]
            
            # Filter SHORT list (bottom 30% AND below threshold)
            short_list = bottom_30_candidates[bottom_30_candidates['FINAL_THG'] < short_threshold]
            
            print(f"\n🏆 LONG LIST (Top %35 + Ortalama * 1.75'ten büyük):")
            print("-" * 70)
            if len(long_list) > 0:
                print(f"{'Sıra':<4} {'Hisse Kodu':<15} {'FINAL THG':<12} {'Sektör':<15} {'Kredi Skoru':<12}")
                print("-" * 70)
                for idx, row in long_list.iterrows():
                    rank = idx + 1
                    stock_id = row[stock_id_col] if stock_id_col in row else f"Row {idx}"
                    final_thg = row['FINAL_THG']
                    sector = row.get('Sector', 'N/A') if 'Sector' in row else 'N/A'
                    credit_score = row.get('CRDT_SCORE', 'N/A') if 'CRDT_SCORE' in row else 'N/A'
                    print(f"{rank:<4} {stock_id:<15} {final_thg:<12.2f} {sector:<15} {credit_score:<12}")
            else:
                print("❌ LONG list için uygun hisse bulunamadı")
            
            print(f"\n📉 SHORT LIST (Bottom %30 + Ortalama * 0.6'dan küçük):")
            print("-" * 70)
            if len(short_list) > 0:
                print(f"{'Sıra':<4} {'Hisse Kodu':<15} {'FINAL THG':<12} {'Sektör':<15} {'Kredi Skoru':<12}")
                print("-" * 70)
                for idx, row in short_list.iterrows():
                    rank = total_stocks - len(short_list) + (idx - short_list.index[0] + 1)
                    stock_id = row[stock_id_col] if stock_id_col in row else f"Row {idx}"
                    final_thg = row['FINAL_THG']
                    sector = row.get('Sector', 'N/A') if 'Sector' in row else 'N/A'
                    credit_score = row.get('CRDT_SCORE', 'N/A') if 'CRDT_SCORE' in row else 'N/A'
                    print(f"{rank:<4} {stock_id:<15} {final_thg:<12.2f} {sector:<15} {credit_score:<12}")
            else:
                print("❌ SHORT list için uygun hisse bulunamadı")
            
            # Summary statistics
            print(f"\n📊 ÖZET:")
            print(f"   • Toplam hisse: {total_stocks}")
            print(f"   • LONG list: {len(long_list)} hisse")
            print(f"   • SHORT list: {len(short_list)} hisse")
            print(f"   • LONG/SHORT oranı: {len(long_list)}/{len(short_list)}")
            
            # Store results
            all_results[filename] = {
                'total_stocks': total_stocks,
                'avg_final_thg': avg_final_thg,
                'long_threshold': long_threshold,
                'short_threshold': short_threshold,
                'long_list': long_list[[stock_id_col, 'FINAL_THG']].to_dict('records') if len(long_list) > 0 else [],
                'short_list': short_list[[stock_id_col, 'FINAL_THG']].to_dict('records') if len(short_list) > 0 else [],
                'long_count': len(long_list),
                'short_count': len(short_list)
            }
            
        except Exception as e:
            print(f"❌ Hata: {str(e)}")
    
    # Overall summary
    print(f"\n{'='*100}")
    print("GENEL ÖZET RAPOR")
    print(f"{'='*100}")
    
    total_long = sum(result['long_count'] for result in all_results.values())
    total_short = sum(result['short_count'] for result in all_results.values())
    total_stocks_all = sum(result['total_stocks'] for result in all_results.values())
    
    print(f"📊 GENEL İSTATİSTİKLER:")
    print(f"   • Toplam dosya sayısı: {len(all_results)}")
    print(f"   • Toplam hisse sayısı: {total_stocks_all}")
    print(f"   • Toplam LONG pozisyon: {total_long}")
    print(f"   • Toplam SHORT pozisyon: {total_short}")
    print(f"   • Genel LONG/SHORT oranı: {total_long}/{total_short}")
    
    # Best performing files
    print(f"\n🏆 EN İYİ LONG/SHORT ORANINA SAHİP DOSYALAR:")
    print("-" * 60)
    sorted_files = sorted(all_results.items(), key=lambda x: x[1]['long_count'] / max(x[1]['short_count'], 1), reverse=True)
    for filename, result in sorted_files[:5]:
        ratio = result['long_count'] / max(result['short_count'], 1)
        print(f"   • {filename}: {result['long_count']}/{result['short_count']} (Oran: {ratio:.2f})")
    
    # Files with most opportunities
    print(f"\n📈 EN FAZLA FIRSAT SUNAN DOSYALAR:")
    print("-" * 60)
    sorted_by_total = sorted(all_results.items(), key=lambda x: x[1]['long_count'] + x[1]['short_count'], reverse=True)
    for filename, result in sorted_by_total[:5]:
        total_opps = result['long_count'] + result['short_count']
        print(f"   • {filename}: {total_opps} fırsat ({result['long_count']} LONG + {result['short_count']} SHORT)")
    
    return all_results

if __name__ == "__main__":
    results = analyze_long_short_positions() 