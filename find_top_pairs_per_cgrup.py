import pandas as pd
import numpy as np
import itertools

def find_top_pairs_per_cgrup():
    """
    Her CGRUP için en yüksek farklı 3 çift bulur
    Her hisse sadece bir kez kullanılır
    """
    print("HER CGRUP İÇİN EN YÜKSEK FARKLI 3 ÇİFT BULUNUYOR...")
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
        FINAL_THG_MIN_DIFF = 350
        SHORT_FINAL_MIN_DIFF = 250
        SMI_MAX_RATE = 0.20
        PAIRS_PER_CGRUP = 3
        
        print(f"\n📊 ARAMA KRİTERLERİ:")
        print(f"   FINAL_THG farkı: ≥ {FINAL_THG_MIN_DIFF}")
        print(f"   SHORT_FINAL farkı: ≥ {SHORT_FINAL_MIN_DIFF}")
        print(f"   SMI oranı (düşük SHORT_FINAL için): ≤ {SMI_MAX_RATE}")
        print(f"   Her CGRUP için: {PAIRS_PER_CGRUP} çift")
        print(f"   Her hisse sadece bir kez kullanılacak")
        print(f"   Sıralama: SHORT_FINAL'a %70, FINAL_THG'ye %30 ağırlık")
        
        # CGRUP bazında grupla
        cgrup_groups = df.groupby('CGRUP')
        print(f"\n📁 Toplam {len(cgrup_groups)} CGRUP bulundu")
        
        all_selected_pairs = []
        used_stocks = set()  # Kullanılan hisseleri takip et
        
        for cgrup, group_data in cgrup_groups:
            if len(group_data) < 2:
                continue
                
            print(f"\n🔍 CGRUP {cgrup} analiz ediliyor ({len(group_data)} hisse)")
            
            # Kullanılmamış hisseleri filtrele
            available_stocks = group_data[~group_data['PREF IBKR'].isin(used_stocks)]
            
            if len(available_stocks) < 2:
                print(f"   ⚠️ Yeterli kullanılmamış hisse yok")
                continue
            
            # Tüm hisse çiftlerini oluştur
            pairs = list(itertools.combinations(available_stocks.index, 2))
            
            valid_pairs = []
            
            for idx1, idx2 in pairs:
                stock1 = available_stocks.loc[idx1]
                stock2 = available_stocks.loc[idx2]
                
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
                        'LOWER_SHORT_SMI': lower_short_stock['SMI'],
                        'TOTAL_DIFF': (final_thg_diff * 0.3) + (short_final_diff * 0.7)  # SHORT_FINAL'a daha fazla ağırlık
                    }
                    
                    valid_pairs.append(pair_info)
            
            # En yüksek toplam farka sahip çiftleri seç
            if valid_pairs:
                valid_pairs.sort(key=lambda x: x['TOTAL_DIFF'], reverse=True)
                selected_pairs = valid_pairs[:PAIRS_PER_CGRUP]
                
                print(f"   ✅ {len(selected_pairs)} çift seçildi")
                
                for i, pair in enumerate(selected_pairs, 1):
                    print(f"      {i}. {pair['STOCK1_PREF']} vs {pair['STOCK2_PREF']}")
                    print(f"         FINAL_THG farkı: {pair['FINAL_THG_DIFF']:.2f}")
                    print(f"         SHORT_FINAL farkı: {pair['SHORT_FINAL_DIFF']:.2f}")
                    print(f"         Ağırlıklı skor: {pair['TOTAL_DIFF']:.2f} (SHORT_FINAL öncelikli)")
                    print(f"         Düşük SHORT_FINAL: {pair['LOWER_SHORT_STOCK']} (SMI: {pair['LOWER_SHORT_SMI']:.4f})")
                    
                    # Kullanılan hisseleri işaretle
                    used_stocks.add(pair['STOCK1_PREF'])
                    used_stocks.add(pair['STOCK2_PREF'])
                
                all_selected_pairs.extend(selected_pairs)
            else:
                print(f"   ❌ Uygun çift bulunamadı")
        
        # Sonuçları DataFrame'e çevir
        if all_selected_pairs:
            result_df = pd.DataFrame(all_selected_pairs)
            
            # CGRUP ve toplam farka göre sırala
            result_df = result_df.sort_values(['CGRUP', 'TOTAL_DIFF'], ascending=[True, False])
            
            print(f"\n{'='*80}")
            print(f"📊 SEÇİLEN ÇİFTLER: {len(result_df)} adet")
            print(f"{'='*80}")
            
            # CGRUP bazında sonuçları göster
            for cgrup in result_df['CGRUP'].unique():
                cgrup_pairs = result_df[result_df['CGRUP'] == cgrup]
                print(f"\n🏢 CGRUP {cgrup} ({len(cgrup_pairs)} çift):")
                
                for idx, row in cgrup_pairs.iterrows():
                    print(f"   {row['STOCK1_PREF']} vs {row['STOCK2_PREF']}")
                    print(f"      FINAL_THG: {row['STOCK1_FINAL_THG']:.2f} vs {row['STOCK2_FINAL_THG']:.2f} (Fark: {row['FINAL_THG_DIFF']:.2f})")
                    print(f"      SHORT_FINAL: {row['STOCK1_SHORT_FINAL']:.2f} vs {row['STOCK2_SHORT_FINAL']:.2f} (Fark: {row['SHORT_FINAL_DIFF']:.2f})")
                    print(f"      Ağırlıklı skor: {row['TOTAL_DIFF']:.2f} (SHORT_FINAL öncelikli)")
                    print(f"      Düşük SHORT_FINAL: {row['LOWER_SHORT_STOCK']} (SMI: {row['LOWER_SHORT_SMI']:.4f})")
            
            # Dosyaya kaydet
            output_file = "top_pairs_per_cgrup.csv"
            result_df.to_csv(output_file, index=False)
            print(f"\n💾 Sonuçlar '{output_file}' dosyasına kaydedildi.")
            
            # İstatistikler
            print(f"\n📈 İSTATİSTİKLER:")
            print(f"   Toplam seçilen çift: {len(result_df)}")
            print(f"   Kullanılan unique hisse: {len(used_stocks)}")
            print(f"   En yüksek ağırlıklı skor: {result_df['TOTAL_DIFF'].max():.2f}")
            print(f"   Ortalama ağırlıklı skor: {result_df['TOTAL_DIFF'].mean():.2f}")
            
            # CGRUP bazında dağılım
            print(f"\n📊 CGRUP BAZINDA DAĞILIM:")
            cgrup_counts = result_df['CGRUP'].value_counts()
            for cgrup, count in cgrup_counts.items():
                print(f"   CGRUP {cgrup}: {count} çift")
            
            # Kullanılan hisseleri listele
            print(f"\n📋 KULLANILAN HİSSELER ({len(used_stocks)} adet):")
            used_stocks_list = sorted(list(used_stocks))
            for i, stock in enumerate(used_stocks_list, 1):
                print(f"   {i:2d}. {stock}")
            
            return result_df
        else:
            print("❌ Hiç uygun çift bulunamadı!")
            return None
            
    except Exception as e:
        print(f"❌ Hata oluştu: {e}")
        return None

def main():
    print("🚀 HER CGRUP İÇİN EN YÜKSEK FARKLI 3 ÇİFT ARANIYOR...")
    print("=" * 80)
    
    # Ana analizi yap
    result = find_top_pairs_per_cgrup()
    
    if result is not None:
        print(f"\n✅ Tüm işlemler tamamlandı!")
        print(f"📁 Sonuç dosyası: top_pairs_per_cgrup.csv")
    else:
        print(f"\n❌ İşlem başarısız!")

if __name__ == "__main__":
    main() 