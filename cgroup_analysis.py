import pandas as pd
import numpy as np

def analyze_cgroup_final_thg():
    """finekheldkuponlu.csv dosyasını CGRUP bazında analiz et"""
    
    # Dosyayı yükle
    try:
        df = pd.read_csv('finekheldkuponlu.csv')
        print(f"✓ finekheldkuponlu.csv yüklendi: {len(df)} satır")
    except FileNotFoundError:
        print("❌ finekheldkuponlu.csv dosyası bulunamadı")
        return
    
    # Gerekli sütunları kontrol et
    required_columns = ['CGRUP', 'CMON', 'PREF IBKR', 'FINAL_THG']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"❌ Eksik sütunlar: {missing_columns}")
        return
    
    # FINAL_THG'yi numeric yap
    df['FINAL_THG'] = pd.to_numeric(df['FINAL_THG'], errors='coerce')
    
    # Boş değerleri temizle
    df_clean = df.dropna(subset=['FINAL_THG', 'CGRUP', 'CMON'])
    print(f"✓ Temizlenmiş veri: {len(df_clean)} satır")
    
    # CGRUP'ları bul
    cgroups = sorted(df_clean['CGRUP'].unique())
    print(f"✓ Bulunan CGRUP sayısı: {len(cgroups)}")
    print()
    
    print("=== CGRUP BAZINDA FINAL THG ANALİZİ ===")
    print("Her CGRUP için:")
    print("- En yüksek 2 FINAL THG (farklı CMON)")
    print("- En düşük 2 FINAL THG (farklı CMON)")
    print("- Yüzdesel farklar")
    print("=" * 80)
    
    all_results = []
    
    for cgroup in cgroups:
        cgroup_data = df_clean[df_clean['CGRUP'] == cgroup].copy()
        
        if len(cgroup_data) < 2:
            print(f"⚠️  CGRUP {cgroup}: Yetersiz veri ({len(cgroup_data)} satır)")
            continue
        
        print(f"\n📊 CGRUP {cgroup} ({len(cgroup_data)} hisse):")
        
        # En yüksek FINAL THG'li hisseler (farklı CMON)
        # Önce her CMON için en yüksek olanı bul
        top_by_cmon = cgroup_data.loc[cgroup_data.groupby('CMON')['FINAL_THG'].idxmax()]
        top_2_different_cmon = top_by_cmon.nlargest(2, 'FINAL_THG').to_dict('records')
        
        # En düşük FINAL THG'li hisseler (farklı CMON)
        # Önce her CMON için en düşük olanı bul
        bottom_by_cmon = cgroup_data.loc[cgroup_data.groupby('CMON')['FINAL_THG'].idxmin()]
        bottom_2_different_cmon = bottom_by_cmon.nsmallest(2, 'FINAL_THG').to_dict('records')
        
        # Sonuçları göster
        if len(top_2_different_cmon) >= 1 and len(bottom_2_different_cmon) >= 1:
            print(f"   🔥 En Yüksek FINAL THG (Farklı CMON):")
            for i, stock in enumerate(top_2_different_cmon, 1):
                print(f"      {i}. {stock['PREF IBKR']} ({stock['CMON']}): {stock['FINAL_THG']:.2f}")
            
            print(f"   📉 En Düşük FINAL THG (Farklı CMON):")
            for i, stock in enumerate(bottom_2_different_cmon, 1):
                print(f"      {i}. {stock['PREF IBKR']} ({stock['CMON']}): {stock['FINAL_THG']:.2f}")
            
            # Yüzdesel farkları hesapla
            if len(top_2_different_cmon) >= 1 and len(bottom_2_different_cmon) >= 1:
                highest = top_2_different_cmon[0]['FINAL_THG']
                lowest = bottom_2_different_cmon[0]['FINAL_THG']
                
                # Yüzdesel fark hesaplama
                if lowest > 0:
                    percentage_diff = ((highest - lowest) / lowest) * 100
                    print(f"   📈 Fark: {top_2_different_cmon[0]['PREF IBKR']} vs {bottom_2_different_cmon[0]['PREF IBKR']}")
                    print(f"      {highest:.2f} vs {lowest:.2f} = %{percentage_diff:.1f} fark")
                else:
                    print(f"   ⚠️  Sıfır değer nedeniyle yüzde hesaplanamadı")
            
            # Sonuçları kaydet
            result = {
                'CGRUP': cgroup,
                'Top_1': top_2_different_cmon[0]['PREF IBKR'] if len(top_2_different_cmon) >= 1 else None,
                'Top_1_CMON': top_2_different_cmon[0]['CMON'] if len(top_2_different_cmon) >= 1 else None,
                'Top_1_FINAL_THG': top_2_different_cmon[0]['FINAL_THG'] if len(top_2_different_cmon) >= 1 else None,
                'Top_2': top_2_different_cmon[1]['PREF IBKR'] if len(top_2_different_cmon) >= 2 else None,
                'Top_2_CMON': top_2_different_cmon[1]['CMON'] if len(top_2_different_cmon) >= 2 else None,
                'Top_2_FINAL_THG': top_2_different_cmon[1]['FINAL_THG'] if len(top_2_different_cmon) >= 2 else None,
                'Bottom_1': bottom_2_different_cmon[0]['PREF IBKR'] if len(bottom_2_different_cmon) >= 1 else None,
                'Bottom_1_CMON': bottom_2_different_cmon[0]['CMON'] if len(bottom_2_different_cmon) >= 1 else None,
                'Bottom_1_FINAL_THG': bottom_2_different_cmon[0]['FINAL_THG'] if len(bottom_2_different_cmon) >= 1 else None,
                'Bottom_2': bottom_2_different_cmon[1]['PREF IBKR'] if len(bottom_2_different_cmon) >= 2 else None,
                'Bottom_2_CMON': bottom_2_different_cmon[1]['CMON'] if len(bottom_2_different_cmon) >= 2 else None,
                'Bottom_2_FINAL_THG': bottom_2_different_cmon[1]['FINAL_THG'] if len(bottom_2_different_cmon) >= 2 else None,
                'Percentage_Diff': percentage_diff if 'percentage_diff' in locals() else None
            }
            all_results.append(result)
        else:
            print(f"   ⚠️  Yeterli farklı CMON bulunamadı")
    
    # Sonuçları DataFrame'e çevir
    if all_results:
        results_df = pd.DataFrame(all_results)
        
        print("\n" + "=" * 80)
        print("📊 ÖZET TABLO")
        print("=" * 80)
        
        # Özet tablo göster
        summary_columns = ['CGRUP', 'Top_1', 'Top_1_FINAL_THG', 'Bottom_1', 'Bottom_1_FINAL_THG', 'Percentage_Diff']
        print(results_df[summary_columns].to_string(index=False))
        
        # En yüksek farklı olan CGRUP'ları göster
        print("\n" + "=" * 80)
        print("🏆 EN YÜKSEK FARKLI CGRUP'LAR")
        print("=" * 80)
        
        sorted_results = results_df.sort_values('Percentage_Diff', ascending=False)
        for _, row in sorted_results.head(10).iterrows():
            print(f"CGRUP {row['CGRUP']}: {row['Top_1']} ({row['Top_1_FINAL_THG']:.2f}) vs {row['Bottom_1']} ({row['Bottom_1_FINAL_THG']:.2f}) = %{row['Percentage_Diff']:.1f}")
        
        # CSV olarak kaydet
        results_df.to_csv('cgroup_analysis_results.csv', index=False)
        print(f"\n💾 Sonuçlar 'cgroup_analysis_results.csv' dosyasına kaydedildi")
        
        # İstatistikler
        print("\n" + "=" * 80)
        print("📈 İSTATİSTİKLER")
        print("=" * 80)
        print(f"Toplam analiz edilen CGRUP: {len(results_df)}")
        print(f"Ortalama yüzdesel fark: %{results_df['Percentage_Diff'].mean():.1f}")
        print(f"En yüksek yüzdesel fark: %{results_df['Percentage_Diff'].max():.1f}")
        print(f"En düşük yüzdesel fark: %{results_df['Percentage_Diff'].min():.1f}")
        
    else:
        print("❌ Analiz edilebilir sonuç bulunamadı")

if __name__ == "__main__":
    analyze_cgroup_final_thg() 