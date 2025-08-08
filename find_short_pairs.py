import pandas as pd
import numpy as np
import itertools

def find_short_pairs():
    """
    ssfinekheldkuponlu.csv dosyasından CGRUP bazında karşılaştırma yaparak
    belirli kriterlere uyan hisse çiftlerini bulur
    """
    print("SSFINEKHELDKUPONLU DOSYASINDAN SHORT PAIR'LER BULUNUYOR...")
    print("=" * 80)
    
    try:
        # Dosyayı oku
        df = pd.read_csv("ssfinekheldkuponlu.csv")
        print(f"✅ Dosya okundu: {len(df)} satır")
        
        # Gerekli kolonları kontrol et
        required_columns = ['PREF IBKR', 'CGRUP', 'FINAL_THG', 'SHORT_FINAL', 'SMI']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"❌ Eksik kolonlar: {missing_columns}")
            print("💡 Önce noptimize_shorts.py çalıştırılmalı!")
            return None
        
        print(f"✅ Tüm gerekli kolonlar mevcut")
        
        # Kriterler
        FINAL_THG_MIN_DIFF = 500
        SHORT_FINAL_MIN_DIFF = 400
        SMI_MAX_RATE = 0.20
        
        print(f"\n📊 ARAMA KRİTERLERİ:")
        print(f"   FINAL_THG farkı: ≥ {FINAL_THG_MIN_DIFF}")
        print(f"   SHORT_FINAL farkı: ≥ {SHORT_FINAL_MIN_DIFF}")
        print(f"   SMI oranı (düşük SHORT_FINAL için): ≤ {SMI_MAX_RATE}")
        
        # CGRUP bazında grupla
        cgrup_groups = df.groupby('CGRUP')
        print(f"\n📁 Toplam {len(cgrup_groups)} CGRUP bulundu")
        
        valid_pairs = []
        
        for cgrup, group_data in cgrup_groups:
            if len(group_data) < 2:
                continue
                
            print(f"\n🔍 CGRUP {cgrup} analiz ediliyor ({len(group_data)} hisse)")
            
            # Tüm hisse çiftlerini oluştur
            pairs = list(itertools.combinations(group_data.index, 2))
            
            for idx1, idx2 in pairs:
                stock1 = group_data.loc[idx1]
                stock2 = group_data.loc[idx2]
                
                # FINAL_THG farkını hesapla
                final_thg_diff = abs(stock1['FINAL_THG'] - stock2['FINAL_THG'])
                
                # SHORT_FINAL farkını hesapla
                short_final_diff = abs(stock1['SHORT_FINAL'] - stock2['SHORT_FINAL'])
                
                # Düşük SHORT_FINAL'lı hisseyi belirle
                if stock1['SHORT_FINAL'] < stock2['SHORT_FINAL']:
                    lower_short_stock = stock1
                    higher_short_stock = stock2
                else:
                    lower_short_stock = stock2
                    higher_short_stock = stock1
                
                # Kriterleri kontrol et
                if (final_thg_diff >= FINAL_THG_MIN_DIFF and 
                    short_final_diff >= SHORT_FINAL_MIN_DIFF and
                    lower_short_stock['SMI'] <= SMI_MAX_RATE):
                    
                    pair_info = {
                        'CGRUP': cgrup,
                        'STOCK1_PREF': stock1['PREF IBKR'],
                        'STOCK1_FINAL_THG': stock1['FINAL_THG'],
                        'STOCK1_SHORT_FINAL': stock1['SHORT_FINAL'],
                        'STOCK1_SMI': stock1['SMI'],
                        'STOCK2_PREF': stock2['PREF IBKR'],
                        'STOCK2_FINAL_THG': stock2['FINAL_THG'],
                        'STOCK2_SHORT_FINAL': stock2['SHORT_FINAL'],
                        'STOCK2_SMI': stock2['SMI'],
                        'FINAL_THG_DIFF': final_thg_diff,
                        'SHORT_FINAL_DIFF': short_final_diff,
                        'LOWER_SHORT_STOCK': lower_short_stock['PREF IBKR'],
                        'LOWER_SHORT_SMI': lower_short_stock['SMI']
                    }
                    
                    valid_pairs.append(pair_info)
                    
                    print(f"   ✅ Uygun çift bulundu:")
                    print(f"      {stock1['PREF IBKR']} vs {stock2['PREF IBKR']}")
                    print(f"      FINAL_THG farkı: {final_thg_diff:.2f}")
                    print(f"      SHORT_FINAL farkı: {short_final_diff:.2f}")
                    print(f"      Düşük SHORT_FINAL: {lower_short_stock['PREF IBKR']} (SMI: {lower_short_stock['SMI']:.4f})")
        
        # Sonuçları DataFrame'e çevir
        if valid_pairs:
            result_df = pd.DataFrame(valid_pairs)
            
            # SHORT_FINAL farkına göre sırala
            result_df = result_df.sort_values('SHORT_FINAL_DIFF', ascending=False)
            
            print(f"\n{'='*80}")
            print(f"📊 BULUNAN UYGUN ÇİFTLER: {len(result_df)} adet")
            print(f"{'='*80}")
            
            # Sonuçları göster
            for idx, row in result_df.iterrows():
                print(f"\n{idx+1}. CGRUP {row['CGRUP']}:")
                print(f"   {row['STOCK1_PREF']} vs {row['STOCK2_PREF']}")
                print(f"   FINAL_THG: {row['STOCK1_FINAL_THG']:.2f} vs {row['STOCK2_FINAL_THG']:.2f} (Fark: {row['FINAL_THG_DIFF']:.2f})")
                print(f"   SHORT_FINAL: {row['STOCK1_SHORT_FINAL']:.2f} vs {row['STOCK2_SHORT_FINAL']:.2f} (Fark: {row['SHORT_FINAL_DIFF']:.2f})")
                print(f"   Düşük SHORT_FINAL: {row['LOWER_SHORT_STOCK']} (SMI: {row['LOWER_SHORT_SMI']:.4f})")
            
            # Dosyaya kaydet
            output_file = "short_pairs_ssfinekheldkuponlu.csv"
            result_df.to_csv(output_file, index=False)
            print(f"\n💾 Sonuçlar '{output_file}' dosyasına kaydedildi.")
            
            # İstatistikler
            print(f"\n📈 İSTATİSTİKLER:")
            print(f"   Toplam uygun çift: {len(result_df)}")
            print(f"   En yüksek FINAL_THG farkı: {result_df['FINAL_THG_DIFF'].max():.2f}")
            print(f"   En yüksek SHORT_FINAL farkı: {result_df['SHORT_FINAL_DIFF'].max():.2f}")
            print(f"   Ortalama FINAL_THG farkı: {result_df['FINAL_THG_DIFF'].mean():.2f}")
            print(f"   Ortalama SHORT_FINAL farkı: {result_df['SHORT_FINAL_DIFF'].mean():.2f}")
            
            # CGRUP bazında dağılım
            print(f"\n📊 CGRUP BAZINDA DAĞILIM:")
            cgrup_counts = result_df['CGRUP'].value_counts()
            for cgrup, count in cgrup_counts.items():
                print(f"   CGRUP {cgrup}: {count} çift")
            
            return result_df
        else:
            print("❌ Hiç uygun çift bulunamadı!")
            return None
            
    except Exception as e:
        print(f"❌ Hata oluştu: {e}")
        return None

def analyze_specific_pairs():
    """
    Belirli hisse çiftlerini detaylı analiz eder
    """
    print(f"\n{'='*80}")
    print("🔍 BELİRLİ HİSSE ÇİFTLERİ ANALİZİ")
    print(f"{'='*80}")
    
    try:
        df = pd.read_csv("ssfinekheldkuponlu.csv")
        
        # AFGB ve MS PRK örneği
        target_pairs = [
            ('AFGB', 'MS PRK'),
            # Diğer çiftler buraya eklenebilir
        ]
        
        for stock1_name, stock2_name in target_pairs:
            stock1 = df[df['PREF IBKR'] == stock1_name]
            stock2 = df[df['PREF IBKR'] == stock2_name]
            
            if len(stock1) > 0 and len(stock2) > 0:
                stock1_data = stock1.iloc[0]
                stock2_data = stock2.iloc[0]
                
                print(f"\n📊 {stock1_name} vs {stock2_name}:")
                print(f"   CGRUP: {stock1_data['CGRUP']} vs {stock2_data['CGRUP']}")
                print(f"   FINAL_THG: {stock1_data['FINAL_THG']:.2f} vs {stock2_data['FINAL_THG']:.2f}")
                print(f"   SHORT_FINAL: {stock1_data['SHORT_FINAL']:.2f} vs {stock2_data['SHORT_FINAL']:.2f}")
                print(f"   SMI: {stock1_data['SMI']:.4f} vs {stock2_data['SMI']:.4f}")
                
                final_thg_diff = abs(stock1_data['FINAL_THG'] - stock2_data['FINAL_THG'])
                short_final_diff = abs(stock1_data['SHORT_FINAL'] - stock2_data['SHORT_FINAL'])
                
                print(f"   FINAL_THG farkı: {final_thg_diff:.2f}")
                print(f"   SHORT_FINAL farkı: {short_final_diff:.2f}")
                
                # Kriterleri kontrol et
                criteria_met = []
                if final_thg_diff >= 500:
                    criteria_met.append("✅ FINAL_THG farkı ≥ 500")
                else:
                    criteria_met.append("❌ FINAL_THG farkı < 500")
                
                if short_final_diff >= 400:
                    criteria_met.append("✅ SHORT_FINAL farkı ≥ 400")
                else:
                    criteria_met.append("❌ SHORT_FINAL farkı < 400")
                
                lower_smi = min(stock1_data['SMI'], stock2_data['SMI'])
                if lower_smi <= 0.20:
                    criteria_met.append("✅ Düşük SMI ≤ 0.20")
                else:
                    criteria_met.append("❌ Düşük SMI > 0.20")
                
                print(f"   Kriterler: {' | '.join(criteria_met)}")
            else:
                print(f"❌ {stock1_name} veya {stock2_name} bulunamadı!")
                
    except Exception as e:
        print(f"❌ Analiz hatası: {e}")

def main():
    print("🚀 SSFINEKHELDKUPONLU DOSYASINDAN SHORT PAIR'LER ARANIYOR...")
    print("=" * 80)
    
    # Ana analizi yap
    result = find_short_pairs()
    
    if result is not None:
        # Belirli çiftleri analiz et
        analyze_specific_pairs()
        
        print(f"\n✅ Tüm işlemler tamamlandı!")
        print(f"📁 Sonuç dosyası: short_pairs_ssfinekheldkuponlu.csv")
    else:
        print(f"\n❌ İşlem başarısız!")

if __name__ == "__main__":
    main() 