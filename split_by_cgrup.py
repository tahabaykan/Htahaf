import pandas as pd
import os

def split_by_cgrup():
    """nalltogether.csv dosyasını CGRUP değerlerine göre ayır"""
    
    # Dosyayı oku
    print("nalltogether.csv dosyası okunuyor...")
    df = pd.read_csv('nalltogether.csv')
    
    print(f"Toplam satır sayısı: {len(df)}")
    print(f"Kolonlar: {df.columns.tolist()}")
    
    # CGRUP değerlerini al (NaN olmayanlar)
    cgrup_values = df['CGRUP'].dropna().unique()
    print(f"\nBulunan CGRUP değerleri: {sorted(cgrup_values)}")
    
    # CGRUP değeri olmayan satırları da işle
    no_cgrup_df = df[df['CGRUP'].isna()].copy()
    if len(no_cgrup_df) > 0:
        no_cgrup_df.to_csv('nc_none.csv', index=False, encoding='utf-8-sig')
        print(f"✓ nc_none.csv oluşturuldu - {len(no_cgrup_df)} hisse (CGRUP değeri olmayan)")
        stocks = no_cgrup_df['PREF IBKR'].tolist()
        print(f"  Örnek hisseler: {stocks[:5]}")
        if len(stocks) > 5:
            print(f"  ... ve {len(stocks)-5} hisse daha")
        print()
    
    # Her CGRUP değeri için ayrı dosya oluştur
    for cgrup in cgrup_values:
        if pd.isna(cgrup) or cgrup == '':
            continue
            
        # Bu CGRUP değerine sahip satırları filtrele
        filtered_df = df[df['CGRUP'] == cgrup].copy()
        
        if len(filtered_df) > 0:
            # Dosya adını oluştur (nc400, nc425, vb.)
            filename = f"nc{cgrup[1:]}.csv"  # c400 -> nc400
            
            # Dosyayı kaydet
            filtered_df.to_csv(filename, index=False, encoding='utf-8-sig')
            
            print(f"✓ {filename} oluşturuldu - {len(filtered_df)} hisse")
            
            # İlk birkaç hisseyi göster
            stocks = filtered_df['PREF IBKR'].tolist()
            print(f"  Örnek hisseler: {stocks[:5]}")
            if len(stocks) > 5:
                print(f"  ... ve {len(stocks)-5} hisse daha")
            print()
    
    print("Tüm dosyalar başarıyla oluşturuldu!")
    print("\nOluşturulan dosyalar:")
    
    # Oluşturulan dosyaları listele
    all_files = []
    
    # nc_none.csv dosyasını kontrol et
    if os.path.exists('nc_none.csv'):
        file_size = os.path.getsize('nc_none.csv')
        print(f"  nc_none.csv ({file_size} bytes)")
        all_files.append('nc_none.csv')
    
    for cgrup in sorted(cgrup_values):
        if pd.isna(cgrup) or cgrup == '':
            continue
        filename = f"nc{cgrup[1:]}.csv"
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            print(f"  {filename} ({file_size} bytes)")
            all_files.append(filename)
    
    print(f"\nToplam {len(all_files)} dosya oluşturuldu.")

if __name__ == "__main__":
    split_by_cgrup() 