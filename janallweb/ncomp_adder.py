import pandas as pd
import glob
import os

def add_ncomp_to_yek_files():
    """
    ncomppriority.csv'den NCOMP Count verilerini alıp YEK dosyalarına ekler
    """
    print("=== NCOMP Count Verilerini YEK Dosyalarına Ekleme ===")
    
    # ncomppriority.csv'yi oku
    try:
        ncomp_df = pd.read_csv('ncomppriority.csv')
        print(f"ncomppriority.csv okundu: {len(ncomp_df)} hisse")
        print("Örnek veriler:")
        print(ncomp_df[['PREF IBKR', 'CMON', 'DIV AMOUNT', 'NCOMP Count']].head())
    except Exception as e:
        print(f"❌ ncomppriority.csv okuma hatası: {e}")
        return
    
    # YEK dosyalarını bul
    yek_files = glob.glob('yek*.csv')
    print(f"\nBulunan YEK dosyaları: {len(yek_files)}")
    
    for yek_file in yek_files:
        try:
            print(f"\nİşleniyor: {yek_file}")
            
            # YEK dosyasını oku
            yek_df = pd.read_csv(yek_file)
            print(f"  {len(yek_df)} satır okundu")
            
            # Eski NCOMP Count kolonlarını temizle
            ncomp_cols = [col for col in yek_df.columns if 'NCOMP Count' in col]
            if ncomp_cols:
                yek_df = yek_df.drop(columns=ncomp_cols)
                print(f"  Eski NCOMP Count kolonları temizlendi: {ncomp_cols}")
            
            # Merge işlemi
            merged_df = yek_df.merge(
                ncomp_df[['PREF IBKR', 'NCOMP Count']], 
                on='PREF IBKR', 
                how='left'
            )
            
            # Eksik değerleri 0 ile doldur
            merged_df['NCOMP Count'] = merged_df['NCOMP Count'].fillna(0).astype(int)
            
            # Dosyayı kaydet
            merged_df.to_csv(yek_file, index=False, encoding='utf-8')
            
            # Sonuçları göster
            print(f"  ✅ {yek_file} güncellendi")
            print(f"  NCOMP Count eklendi: {merged_df['NCOMP Count'].notna().sum()}/{len(merged_df)} hisse")
            
            # HBAN hisselerini kontrol et
            if 'HBAN' in merged_df['CMON'].values:
                hban_data = merged_df[merged_df['CMON'] == 'HBAN']
                print(f"  HBAN hisseleri:")
                for _, row in hban_data.iterrows():
                    print(f"    {row['PREF IBKR']}: NCOMP Count = {row['NCOMP Count']}")
            
        except Exception as e:
            print(f"  ❌ {yek_file} işleme hatası: {e}")

if __name__ == "__main__":
    add_ncomp_to_yek_files() 