import pandas as pd
import numpy as np
import time
import os

def normalize_values(series, lower_bound=-15, upper_bound=15, max_score=90, score_range=80):
    """
    Excel formülünü taklit eden normalize fonksiyonu
    
    Parameters:
    -----------
    series : pd.Series
        Normalize edilecek veri serisi
    lower_bound : float
        Alt sınır (default: -15)
    upper_bound : float
        Üst sınır (default: 15)
    max_score : float
        En yüksek puan (default: 90)
    score_range : float
        Puan aralığı (default: 80)
    """
    # -15 ile 15 arasındaki değerleri filtrele
    mask = (series >= lower_bound) & (series < upper_bound)
    filtered_series = series[mask]
    
    if filtered_series.empty:
        return pd.Series(index=series.index)
    
    # Min ve max değerleri bul
    min_val = filtered_series.min()
    max_val = filtered_series.max()
    
    # Normalize et (en negatif değer en yüksek puanı alacak)
    normalized = pd.Series(index=series.index)
    normalized[mask] = max_score - (
        (series[mask] - min_val) / (max_val - min_val) * score_range
    )
    
    return normalized

def normalize_6m_values(series, lower_bound=-8, upper_bound=15, max_score=90, score_range=80):
    """
    6 aylık değişimler için özel normalize fonksiyonu
    
    Parameters:
    -----------
    series : pd.Series
        Normalize edilecek veri serisi
    lower_bound : float
        Alt sınır (default: -8)
    upper_bound : float
        Üst sınır (default: 15)
    max_score : float
        En yüksek puan (default: 90)
    score_range : float
        Puan aralığı (default: 80)
    """
    # -8 ile 15 arasındaki değerleri filtrele
    mask = (series >= lower_bound) & (series < upper_bound)
    filtered_series = series[mask]
    
    if filtered_series.empty:
        return pd.Series(index=series.index)
    
    # Min ve max değerleri bul
    min_val = filtered_series.min()
    max_val = filtered_series.max()
    
    # Normalize et (en negatif değer en yüksek puanı alacak)
    normalized = pd.Series(index=series.index)
    normalized[mask] = max_score - (
        (series[mask] - min_val) / (max_val - min_val) * score_range
    )
    
    return normalized

def fill_missing_values_with_mean(df, column_name):
    """
    Boş değerleri ortalama ile doldur
    
    Parameters:
    -----------
    df : pd.DataFrame
        Veri çerçevesi
    column_name : str
        Doldurulacak kolon adı
    
    Returns:
    --------
    pd.DataFrame
        Doldurulmuş veri çerçevesi
    """
    if column_name not in df.columns:
        print(f"! {column_name} kolonu bulunamadı")
        return df
    
    # Boş değerleri bul
    missing_mask = df[column_name].isna() | (df[column_name] == '')
    missing_count = missing_mask.sum()
    
    if missing_count == 0:
        return df
    
    # Dolu değerlerin ortalamasını hesapla
    non_missing = df[~missing_mask][column_name]
    if len(non_missing) > 0:
        try:
            # Sayısal değerlere çevir
            numeric_values = pd.to_numeric(non_missing, errors='coerce')
            numeric_values = numeric_values.dropna()
            
            if len(numeric_values) > 0:
                mean_value = numeric_values.mean()
                print(f"  {column_name}: {missing_count} boş değer {mean_value:.2f} ortalaması ile dolduruldu")
                
                # Boş değerleri ortalama ile doldur
                df.loc[missing_mask, column_name] = mean_value
            else:
                print(f"  {column_name}: Sayısal değer bulunamadı")
        except Exception as e:
            print(f"  {column_name}: Ortalama hesaplama hatası - {e}")
    
    return df

def process_csv_file(input_file, output_file):
    """Tek bir CSV dosyasını işle"""
    try:
        print(f"\n=== {input_file} işleniyor ===")
        
        # CSV dosyasını oku
        df = pd.read_csv(input_file, sep=',')
        print(f"✓ {input_file} yüklendi: {len(df)} satır")
        
        # Div adj.price kolonunun varlığını kontrol et
        if 'Div adj.price' not in df.columns:
            print("! Uyarı: 'Div adj.price' kolonu bulunamadı, 'Last Price' kullanılacak.")
            price_column = 'Last Price'
        else:
            # Div adj.price kolonunu numeric hale getir
            df['Div adj.price'] = pd.to_numeric(df['Div adj.price'], errors='coerce')
            # NaN değerleri Last Price ile doldur
            df.loc[df['Div adj.price'].isna(), 'Div adj.price'] = df['Last Price']
            price_column = 'Div adj.price'
            print(f"✓ Hesaplamalarda '{price_column}' kullanılıyor.")
        
        # Aug2022_Price ve Oct19_Price kolonlarını numeric hale getir
        df['Aug2022_Price'] = pd.to_numeric(df['Aug2022_Price'], errors='coerce')
        df['Oct19_Price'] = pd.to_numeric(df['Oct19_Price'], errors='coerce')
        
        # Mevcut normalize işlemleri
        df['6M_Low_diff'] = df[price_column] - df['6M Low']
        df['6M_High_diff'] = df[price_column] - df['6M High']
        df['3M_Low_diff'] = df[price_column] - df['3M Low']
        df['3M_High_diff'] = df[price_column] - df['3M High']
        df['SMA20_chg_norm'] = normalize_values(df['SMA20 chg'])
        df['SMA63_chg_norm'] = normalize_values(df['SMA63 chg'])
        df['SMA246_chg_norm'] = normalize_values(df['SMA246 chg'])
        df['6M_Low_diff_norm'] = normalize_6m_values(df['6M_Low_diff'])
        df['6M_High_diff_norm'] = normalize_6m_values(df['6M_High_diff'])
        df['3M_Low_diff_norm'] = normalize_6m_values(df['3M_Low_diff'])
        df['3M_High_diff_norm'] = normalize_6m_values(df['3M_High_diff'])

        # Aug4 ve Oct19 için normalize işlemleri ekle
        # Önce fark hesapla
        df['Aug4_chg'] = df[price_column] - df['Aug2022_Price']
        df['Oct19_chg'] = df[price_column] - df['Oct19_Price']
        
        # Sonra normalize et (-8 ile 15 arası için)
        df['Aug4_chg_norm'] = normalize_6m_values(df['Aug4_chg'])
        df['Oct19_chg_norm'] = normalize_6m_values(df['Oct19_chg'])
        
        # 1Y High ve Low diff'leri hesapla
        df['1Y_High_diff'] = df[price_column] - df['1Y High']
        df['1Y_Low_diff'] = df[price_column] - df['1Y Low']
        
        # 1Y değerleri için normalize (-8 ile 15 arası)
        df['1Y_High_diff_norm'] = normalize_6m_values(df['1Y_High_diff'])
        df['1Y_Low_diff_norm'] = normalize_6m_values(df['1Y_Low_diff'])

        # Normalize edilmiş kolonlardaki boş değerleri doldur
        norm_columns = [
            'SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm',
            '6M_Low_diff_norm', '6M_High_diff_norm', 
            '3M_Low_diff_norm', '3M_High_diff_norm',
            'Aug4_chg_norm', 'Oct19_chg_norm',
            '1Y_High_diff_norm', '1Y_Low_diff_norm'
        ]
        
        print("Normalize edilmiş kolonlardaki boş değerler ortalama ile dolduruluyor...")
        for col in norm_columns:
            df = fill_missing_values_with_mean(df, col)

        # TLT içeren satırları filtrele
        before_filter = len(df)
        df = df[~df['PREF IBKR'].str.contains('TLT', na=False)]
        removed = before_filter - len(df)
        if removed > 0:
            print(f"Uyarı: {removed} adet TLT satırı çıkarıldı.")
        
        # Sayısal kolonları float'a çevir
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        for col in numeric_columns:
            df[col] = df[col].astype(float)

        # CSV dosyasını oluştur
        # Tüm orijinal kolonlar korunuyor (Last Price, Div adj.price, vb.)
        print(f"Kaydedilen kolonlar: {list(df.columns)}")
        df.to_csv(output_file, 
                 index=False,
                 float_format='%.6f',
                 sep=',',                
                 encoding='utf-8-sig',   
                 lineterminator='\n',    
                 quoting=1)              # Tüm değerleri tırnak içine al

        print(f"✓ {output_file} dosyasına kaydedildi ({len(df)} satır)")
        
    except Exception as e:
        print(f"! {input_file} işlenirken hata: {e}")

def main():
    """Ana işlem fonksiyonu"""
    
    # nibkrtry.py'den çıkan CSV dosyaları
    input_files = [
        'sekheldbesmaturlu.csv',
        'sekheldcilizyeniyedi.csv',
        'sekheldcommonsuz.csv',
        'sekhelddeznff.csv',
        'sekheldff.csv',
        'sekheldflr.csv',
        'sekheldgarabetaltiyedi.csv',
        'sekheldkuponlu.csv',
        'sekheldkuponlukreciliz.csv',
        'sekheldkuponlukreorta.csv',
        'sekheldnff.csv',
        'sekheldotelremorta.csv',
        'sekheldsolidbig.csv',
        'sekheldtitrekhc.csv',
        'sekhighmatur.csv',
        'seknotbesmaturlu.csv',
        'seknotcefilliquid.csv',
        'seknottitrekhc.csv',
        'sekrumoreddanger.csv',
        'seksalakilliquid.csv',
        'sekshitremhc.csv'
    ]
    
    print("nnormalize_data.py başlatılıyor...")
    print("nibkrtry.py'den çıkan CSV dosyaları normalize edilecek...")
    
    processed_count = 0
    
    for input_file in input_files:
        if os.path.exists(input_file):
            # Çıktı dosya adını oluştur (başına 'n' ekle)
            output_file = 'n' + input_file[1:]  # 's' harfini çıkar, 'n' ekle
            
            try:
                process_csv_file(input_file, output_file)
                processed_count += 1
            except Exception as e:
                print(f"! {input_file} işlenirken hata: {e}")
        else:
            print(f"! {input_file} dosyası bulunamadı, atlanıyor...")
    
    print(f"\n✓ İşlem tamamlandı! {processed_count} dosya normalize edildi.")
    print("Çıktı dosyaları 'n' harfi ile başlıyor (örn: nsekheldbesmaturlu.csv)")

if __name__ == "__main__":
    main()