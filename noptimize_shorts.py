import pandas as pd
import numpy as np
import os

def find_lowest_short_final_stocks():
    """
    EKHELD dosyalarını kopyalar, SMI verilerini ekler ve SHORT_FINAL hesaplar
    Her dosya için "ss" ön eki ile yeni dosyalar oluşturur
    """
    print("FINEK DOSYALARINI KOPYALAYIP SHORT_FINAL HESAPLIYOR...")
    print("=" * 80)
    
    # SMI verilerini yükle
    try:
        smi_df = pd.read_csv("nsmiall.csv")
        print(f"✅ SMI verileri yüklendi: {len(smi_df)} satır")
    except Exception as e:
        print(f"❌ SMI verileri yüklenemedi: {e}")
        print("💡 Önce nget_short_fee_rates.py çalıştırılmalı!")
        return None
    
    # FINEK dosya listesi
    finek_files = [
        'finekheldkuponlu.csv',
        'finekheldbesmaturlu.csv',
        'finekheldcilizyeniyedi.csv', 
        'finekheldcommonsuz.csv',
        'finekhelddeznff.csv',
        'finekheldff.csv',
        'finekheldflr.csv',
        'finekheldgarabetaltiyedi.csv',
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
    
    all_lowest_stocks = []
    
    for file_name in finek_files:
        print(f"\n📁 İşleniyor: {file_name}")
        
        try:
            # Dosyayı oku
            if not os.path.exists(file_name):
                print(f"   ❌ Dosya bulunamadı: {file_name}")
                continue
                
            df = pd.read_csv(file_name)
            print(f"   ✅ Dosya okundu: {len(df)} satır")
            
            # SMI verilerini merge et
            df = df.merge(smi_df[['PREF IBKR', 'SMI']], on='PREF IBKR', how='left')
            missing_smi = df['SMI'].isna().sum()
            if missing_smi > 0:
                print(f"   ⚠️ {missing_smi} hisse için SMI değeri bulunamadı! Ortalama ile doldurulacak.")
                mean_smi = df['SMI'].mean()
                df['SMI'].fillna(mean_smi, inplace=True)
            
            # SHORT_FINAL hesapla
            df['SHORT_FINAL'] = df['FINAL_THG'] + (df['SMI'] * 1000)
            print(f"   ✅ SHORT_FINAL hesaplandı (FINAL_THG + SMI*1000)")
            
            # En düşük SHORT_FINAL skoruna sahip hisseyi bul
            # NaN değerleri filtrele
            df_clean = df.dropna(subset=['SHORT_FINAL'])
            
            if len(df_clean) == 0:
                print(f"   ❌ Tüm SHORT_FINAL değerleri NaN! Dosya atlanıyor.")
                continue
                
            lowest_stock = df_clean.loc[df_clean['SHORT_FINAL'].idxmin()]
            
            # Sonuç bilgilerini hazırla
            stock_info = {
                'DOSYA': file_name,
                'PREF_IBKR': lowest_stock.get('PREF IBKR', 'N/A'),
                'SHORT_FINAL': lowest_stock['SHORT_FINAL'],
                'FINAL_THG': lowest_stock.get('FINAL_THG', 'N/A'),
                'SMI': lowest_stock.get('SMI', 'N/A'),
                'CGRUP': lowest_stock.get('CGRUP', 'N/A'),
                'CMON': lowest_stock.get('CMON', 'N/A')
            }
            
            all_lowest_stocks.append(stock_info)
            
            # Detayları göster
            print(f"   🎯 En düşük SHORT_FINAL: {lowest_stock.get('PREF IBKR', 'N/A')}")
            print(f"      SHORT_FINAL: {lowest_stock['SHORT_FINAL']:.4f}")
            print(f"      FINAL_THG: {lowest_stock.get('FINAL_THG', 'N/A')}")
            print(f"      SMI: {lowest_stock.get('SMI', 'N/A')}")
            
            # "ss" ön eki ile yeni dosya oluştur
            ss_file_name = f"ss{file_name}"
            print(f"   💾 {ss_file_name} dosyası oluşturuluyor...")
            
            # Tüm verileri yeni dosyaya kaydet (orijinal dosyayı bozmadan)
            df.to_csv(ss_file_name, index=False)
            print(f"   ✅ {ss_file_name} dosyası kaydedildi ({len(df)} satır)")
            
        except Exception as e:
            print(f"   ❌ Hata oluştu: {e}")
            continue
    
    # Sonuçları DataFrame'e çevir
    if all_lowest_stocks:
        result_df = pd.DataFrame(all_lowest_stocks)
        
        # SHORT_FINAL'a göre sırala
        result_df = result_df.sort_values('SHORT_FINAL')
        
        print(f"\n{'='*80}")
        print("📊 TÜM DOSYALARIN EN DÜŞÜK SHORT_FINAL HİSSELERİ")
        print(f"{'='*80}")
        
        # Sonuçları göster
        for idx, row in result_df.iterrows():
            print(f"{idx+1:2d}. {row['DOSYA']:<25} | {row['PREF_IBKR']:<10} | "
                  f"SHORT_FINAL: {row['SHORT_FINAL']:.4f} | "
                  f"FINAL_THG: {row['FINAL_THG']} | SMI: {row['SMI']}")
        
        # Dosyaya kaydet
        output_file = "ekheld_lowest_short_final_stocks.csv"
        result_df.to_csv(output_file, index=False)
        print(f"\n💾 Sonuçlar '{output_file}' dosyasına kaydedildi.")
        
        # İstatistikler
        print(f"\n📈 İSTATİSTİKLER:")
        print(f"   Toplam dosya sayısı: {len(result_df)}")
        print(f"   En düşük SHORT_FINAL: {result_df['SHORT_FINAL'].min():.4f}")
        print(f"   En yüksek SHORT_FINAL: {result_df['SHORT_FINAL'].max():.4f}")
        print(f"   Ortalama SHORT_FINAL: {result_df['SHORT_FINAL'].mean():.4f}")
        
        return result_df
    else:
        print("❌ Hiç sonuç bulunamadı!")
        return None

def analyze_short_final_distribution():
    """
    SHORT_FINAL skorlarının dağılımını analiz eder
    """
    print(f"\n{'='*80}")
    print("📊 SHORT_FINAL DAĞILIM ANALİZİ")
    print(f"{'='*80}")
    
    try:
        df = pd.read_csv("ekheld_lowest_short_final_stocks.csv")
        
        # Percentile'ları hesapla
        percentiles = [10, 25, 50, 75, 90]
        print("\n📊 Percentile Dağılımı:")
        for p in percentiles:
            value = df['SHORT_FINAL'].quantile(p/100)
            print(f"   {p}%: {value:.4f}")
        
        # En iyi 5 hisse
        print(f"\n🏆 EN İYİ 5 SHORT ADAYI (En düşük SHORT_FINAL):")
        top_5 = df.head(5)
        for idx, row in top_5.iterrows():
            print(f"   {idx+1}. {row['PREF_IBKR']} ({row['DOSYA']}) - SHORT_FINAL: {row['SHORT_FINAL']:.4f}")
        
        # En kötü 5 hisse
        print(f"\n⚠️ EN KÖTÜ 5 SHORT ADAYI (En yüksek SHORT_FINAL):")
        bottom_5 = df.tail(5)
        for idx, row in bottom_5.iterrows():
            print(f"   {idx+1}. {row['PREF_IBKR']} ({row['DOSYA']}) - SHORT_FINAL: {row['SHORT_FINAL']:.4f}")
            
    except Exception as e:
        print(f"❌ Dağılım analizi yapılamadı: {e}")

def main():
    print("🚀 EKHELD DOSYALARINDAN EN DÜŞÜK SHORT_FINAL HİSSELERİ BULUNUYOR...")
    print("=" * 80)
    
    # Ana analizi yap
    result = find_lowest_short_final_stocks()
    
    if result is not None:
        # Dağılım analizini yap
        analyze_short_final_distribution()
        
        print(f"\n✅ Tüm işlemler tamamlandı!")
        print(f"📁 Sonuç dosyası: ekheld_lowest_short_final_stocks.csv")
    else:
        print(f"\n❌ İşlem başarısız!")

if __name__ == "__main__":
    main() 