import pandas as pd
import numpy as np
import glob
import os

def merge_comek_files():
    """Tüm comek ile başlayan CSV dosyalarını birleştir"""
    comek_files = glob.glob('comek*.csv')
    
    print(f"Bulunan comek dosyaları: {len(comek_files)}")
    for file in comek_files:
        print(f"  - {file}")
    
    if not comek_files:
        print("Hiç comek dosyası bulunamadı!")
        return None
    
    all_dataframes = []
    
    for file in comek_files:
        try:
            print(f"\n{file} dosyası okunuyor...")
            df = pd.read_csv(file, encoding='utf-8-sig')
            df['SOURCE_FILE'] = file
            print(f"  - {len(df)} satır okundu")
            all_dataframes.append(df)
        except Exception as e:
            print(f"Hata: {file} dosyası okunamadı - {e}")
    
    if not all_dataframes:
        print("Hiç dosya okunamadı!")
        return None
    
    print(f"\nTüm dosyalar birleştiriliyor...")
    merged_df = pd.concat(all_dataframes, ignore_index=True)
    
    print(f"Toplam {len(merged_df)} satır birleştirildi")
    print(f"Benzersiz PREF IBKR sayısı: {merged_df['PREF IBKR'].nunique()}")
    
    # Tekrar eden hisseleri göster
    duplicates = merged_df[merged_df.duplicated(subset=['PREF IBKR'], keep=False)]
    if not duplicates.empty:
        print(f"\nTekrar eden hisseler ({len(duplicates)} adet):")
        duplicate_counts = duplicates['PREF IBKR'].value_counts()
        print(duplicate_counts.head(10))
    
    # GOOGL TVE/TVC gibi hisseleri filtrele
    print(f"\nGOOGL TVE/TVC gibi hisseler filtreleniyor...")
    filtered_df = merged_df[~merged_df['PREF IBKR'].isin(['TVE', 'TVC'])]
    
    print(f"Filtreleme öncesi: {len(merged_df)} satır")
    print(f"Filtreleme sonrası: {len(filtered_df)} satır")
    print(f"Çıkarılan hisseler: {len(merged_df) - len(filtered_df)} adet")
    
    # Birleştirilmiş dosyayı kaydet
    output_file = 'allcomek.csv'
    filtered_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    print(f"\nBirleştirilmiş dosya '{output_file}' olarak kaydedildi")
    print(f"Toplam {len(filtered_df)} satır, {filtered_df['PREF IBKR'].nunique()} benzersiz hisse")
    
    return filtered_df

def merge_ek_files_with_crdt_scores():
    """ek dosyalarından CRDT_SCORE verilerini al ve allcomek.csv ile birleştir"""
    print("\n=== EK DOSYALARINDAN CRDT_SCORE VERİLERİ ALINIYOR ===")
    
    # allcomek.csv dosyasını oku
    try:
        allcomek_df = pd.read_csv('allcomek.csv', encoding='utf-8-sig')
        print(f"allcomek.csv okundu: {len(allcomek_df)} satır")
    except FileNotFoundError:
        print("allcomek.csv dosyası bulunamadı! Önce comek dosyalarını birleştirin.")
        return None
    
    # ek dosyalarını bul
    ek_files = glob.glob('ek*.csv')
    print(f"Bulunan ek dosyaları: {len(ek_files)}")
    
    # CRDT_SCORE verilerini topla
    crdt_data = {}
    
    for file in ek_files:
        try:
            df = pd.read_csv(file, encoding='utf-8-sig')
            if 'PREF IBKR' in df.columns and 'CRDT_SCORE' in df.columns:
                for _, row in df.iterrows():
                    ticker = row['PREF IBKR']
                    crdt_score = row['CRDT_SCORE']
                    if pd.notna(crdt_score):
                        crdt_data[ticker] = crdt_score
                print(f"  {file}: {len(df)} satır, {df['CRDT_SCORE'].notna().sum()} CRDT_SCORE")
        except Exception as e:
            print(f"Hata: {file} dosyası okunamadı - {e}")
    
    print(f"\nToplam {len(crdt_data)} benzersiz CRDT_SCORE verisi toplandı")
    
    # allcomek.csv'ye CRDT_SCORE ekle
    allcomek_df['CRDT_SCORE'] = allcomek_df['PREF IBKR'].map(crdt_data)
    
    # Eksik CRDT_SCORE değerlerini 40 ile doldur
    missing_count = allcomek_df['CRDT_SCORE'].isna().sum()
    allcomek_df['CRDT_SCORE'] = allcomek_df['CRDT_SCORE'].fillna(40)
    
    print(f"CRDT_SCORE eklendi: {len(crdt_data)} mevcut, {missing_count} eksik (40 ile dolduruldu)")
    
    # Güncellenmiş dosyayı kaydet
    allcomek_df.to_csv('allcomek.csv', index=False, encoding='utf-8-sig')
    print("allcomek.csv güncellendi")
    
    return allcomek_df

def clean_numeric_data(df):
    """Sayısal verileri temizle ve düzelt"""
    numeric_columns = [
        'COM_LAST_PRICE', 'COM_52W_LOW', 'COM_52W_HIGH',
        'COM_6M_PRICE', 'COM_3M_PRICE', 'COM_5Y_LOW',
        'COM_5Y_HIGH', 'COM_MKTCAP', 'CRDT_SCORE',
        'COM_FEB2020_PRICE', 'COM_MAR2020_PRICE'
    ]
    
    for col in numeric_columns:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(',', '')
                .str.replace('$', '')
                .str.replace('B', '')
            )
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df

def normalize_custom(series):
    """Excel'deki özel normalizasyon formülü"""
    valid_series = series[pd.notnull(series)]
    if valid_series.empty:
        return pd.Series(1, index=series.index)
    max_val = valid_series.max()
    min_val = valid_series.min()
    if max_val == min_val:
        return pd.Series(1, index=series.index)
    return 1 + ((series - min_val) / (max_val - min_val)) * 99

def normalize_score(series):
    """Skorları 10-90 arasında normalize et"""
    valid_series = series.dropna()
    if valid_series.empty:
        return pd.Series(10, index=series.index)
    min_val = valid_series.min()
    max_val = valid_series.max()
    if min_val == max_val:
        return pd.Series(10, index=series.index)
    normalized = 10 + ((series - min_val) / (max_val - min_val)) * 80
    return normalized.clip(lower=10, upper=90)

def normalize_market_cap(series):
    """Market Cap için yumuşak logaritmik normalizasyon (milyar dolar bazında)"""
    def score_market_cap(x):
        if pd.isna(x):
            return 35
        billions = float(x)
        if billions >= 500:
            return 95
        elif billions >= 200:
            return 90 + ((billions - 200) / 300) * 5
        elif billions >= 100:
            return 85 + ((billions - 100) / 100) * 5
        elif billions >= 50:
            return 77 + ((billions - 50) / 50) * 8
        elif billions >= 10:
            return 60 + ((billions - 10) / 40) * 17
        elif billions >= 5:
            return 50 + ((billions - 5) / 5) * 10
        elif billions >= 1:
            return 40 + ((billions - 1) / 4) * 10
        else:
            return max(35, 35 + (billions * 5))
    return series.apply(score_market_cap)

def calculate_solidity_scores(df):
    """Solidity skorlarını hesapla - Yeni formül (market cap ile ağırlıklı)"""
    print("\n=== Solidity Skorları Hesaplanıyor ===")
    
    # Market Cap norm
    df['MKTCAP_NORM'] = normalize_market_cap(df['COM_MKTCAP'])
    print(f"Market Cap normalizasyonu tamamlandı")
    
    # Credit Score norm - YENİ CRDT_SCORE KULLANIMI
    df['CRDT_NORM'] = normalize_custom(df['CRDT_SCORE'])
    print(f"Credit Score normalizasyonu tamamlandı (Yeni CRDT_SCORE kullanılıyor)")
    
    # TOTAL_SCORE_NORM hesaplama (YENİ MANTIK - Fiyat değişimleri)
    # LAST_PRICE ile diğer fiyat noktaları arasındaki % değişimleri hesapla
    price_points = ['COM_52W_LOW', 'COM_52W_HIGH', 'COM_6M_PRICE', 'COM_3M_PRICE', 
                   'COM_5Y_LOW', 'COM_5Y_HIGH', 'COM_FEB2020_PRICE', 'COM_MAR2020_PRICE']
    
    for point in price_points:
        if point in df.columns and 'COM_LAST_PRICE' in df.columns:
            # % değişim hesapla: (LAST_PRICE - POINT_PRICE) / POINT_PRICE * 100
            change_col = f'CHANGE_{point}'
            df[change_col] = ((df['COM_LAST_PRICE'] - df[point]) / df[point]) * 100
    
    # Değişim sütunlarını normalize et
    change_columns = [col for col in df.columns if col.startswith('CHANGE_')]
    for col in change_columns:
        norm_col = col + '_NORM'
        df[norm_col] = normalize_custom(df[col])
    
    # Normalize edilmiş değişimlerin ortalamasını al
    norm_change_columns = [col for col in df.columns if col.endswith('_NORM') and col.startswith('CHANGE_')]
    df['TOTAL_SCORE'] = df[norm_change_columns].fillna(0).mean(axis=1)
    
    # Toplam skoru normalize et
    df['TOTAL_SCORE_NORM'] = normalize_custom(df['TOTAL_SCORE'])
    print(f"Total Score normalizasyonu tamamlandı")
    
    def calc_solidity(row):
        try:
            market_cap = row['COM_MKTCAP']
            mktcap_norm = row['MKTCAP_NORM']
            
            # Market Cap bazlı ağırlıklandırma - KAREKÖK FORMÜLÜ - FINAL AĞIRLIKLAR
            if pd.isna(market_cap):
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.40 +
                    row['MKTCAP_NORM'] * 0.35 +
                    row['CRDT_NORM'] * 0.25
                )
            elif market_cap >= 1 and market_cap < 3:
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.40 +
                    row['MKTCAP_NORM'] * 0.45 +
                    row['CRDT_NORM'] * 0.15
                )
            elif market_cap >= 3 and market_cap < 7:
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.30 +
                    row['MKTCAP_NORM'] * 0.40 +
                    row['CRDT_NORM'] * 0.30
                )
            elif market_cap >= 7 and market_cap < 12:
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.25 +
                    row['MKTCAP_NORM'] * 0.35 +
                    row['CRDT_NORM'] * 0.40
                )
            elif market_cap >= 12 and market_cap < 20:
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.20 +
                    row['MKTCAP_NORM'] * 0.30 +
                    row['CRDT_NORM'] * 0.50
                )
            elif market_cap >= 20 and market_cap < 35:
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.15 +
                    row['MKTCAP_NORM'] * 0.30 +
                    row['CRDT_NORM'] * 0.55
                )
            elif market_cap >= 35 and market_cap < 75:
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.10 +
                    row['MKTCAP_NORM'] * 0.30 +
                    row['CRDT_NORM'] * 0.60
                )
            elif market_cap >= 75 and market_cap < 200:
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.05 +
                    row['MKTCAP_NORM'] * 0.30 +
                    row['CRDT_NORM'] * 0.65
                )
            elif market_cap >= 200:
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.05 +
                    row['MKTCAP_NORM'] * 0.30 +
                    row['CRDT_NORM'] * 0.65
                )
            else:
                # 1B altı
                solidity = np.sqrt(mktcap_norm) * (
                    row['TOTAL_SCORE_NORM'] * 0.40 +
                    row['MKTCAP_NORM'] * 0.50 +
                    row['CRDT_NORM'] * 0.10
                )
            
            # BB bond kontrolü - Type kolonu varsa kontrol et
            try:
                if 'Type' in row and str(row['Type']).strip() == 'BB':
                    solidity *= 1.02
            except:
                pass
            
            return solidity
            
        except Exception as e:
            print(f"Satır hesaplama hatası: {e}")
            return 0.0
    
    # Solidity skorlarını hesapla
    df['SOLIDITY_SCORE'] = df.apply(calc_solidity, axis=1)
    df['SOLIDITY_SCORE'] = pd.to_numeric(df['SOLIDITY_SCORE'], errors='coerce')
    
    # Normalize solidity (10-90 arası)
    df['SOLIDITY_SCORE_NORM'] = normalize_score(df['SOLIDITY_SCORE'])
    
    # SOLIDITY_SCORE_NORM'i 2 ondalık basamağa yuvarla
    df['SOLIDITY_SCORE_NORM'] = df['SOLIDITY_SCORE_NORM'].round(2)
    
    print(f"Solidity skorları hesaplandı")
    print(f"Toplam {len(df)} hisse için solidity skorları oluşturuldu")
    
    return df

def show_top_bottom_cmon_scores(df):
    """CMON bazında en yüksek ve en düşük skorları göster"""
    print("\n=== CMON BAZINDA ANALİZ ===")
    
    # CMON bazında gruplandır ve ortalama değerleri al
    cmon_stats = df.groupby('CMON').agg({
        'PREF IBKR': 'first',
        'COM_MKTCAP': 'mean',
        'MKTCAP_NORM': 'mean',
        'SOLIDITY_SCORE': 'mean',
        'SOLIDITY_SCORE_NORM': 'mean'
    }).reset_index()
    
    print(f"\nToplam CMON sayısı: {len(cmon_stats)}")
    print(f"Toplam hisse sayısı: {len(df)}")
    print(f"CMON başına ortalama hisse sayısı: {len(df) / len(cmon_stats):.1f}")
    
    print("\n=== MARKET CAP NORM - EN YÜKSEK 10 CMON ===")
    top_mktcap = cmon_stats.nlargest(10, 'MKTCAP_NORM')[['CMON', 'PREF IBKR', 'COM_MKTCAP', 'MKTCAP_NORM']]
    print(top_mktcap.round(2).to_string(index=False))
    
    print("\n=== SOLIDITY SCORE NORM - EN YÜKSEK 10 CMON ===")
    top_solidity = cmon_stats.nlargest(10, 'SOLIDITY_SCORE_NORM')[['CMON', 'PREF IBKR', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
    print(top_solidity.round(2).to_string(index=False))
    
    print("\n=== SOLIDITY SCORE NORM - EN DÜŞÜK 10 CMON ===")
    bottom_solidity = cmon_stats.nsmallest(10, 'SOLIDITY_SCORE_NORM')[['CMON', 'PREF IBKR', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
    print(bottom_solidity.round(2).to_string(index=False))

def main():
    """Ana işlem akışı"""
    print("=== TÜM HİSSELER İÇİN SOLIDITY SKOR HESAPLAMA ===")
    
    # 1. Tüm comek dosyalarını birleştir
    print("\n1. Adım: Tüm comek dosyaları birleştiriliyor...")
    merged_df = merge_comek_files()
    
    if merged_df is None:
        print("Birleştirme işlemi başarısız!")
        return
    
    # 2. EK dosyalarından CRDT_SCORE verilerini al ve birleştir
    print("\n2. Adım: EK dosyalarından CRDT_SCORE verileri alınıyor...")
    merged_df = merge_ek_files_with_crdt_scores()
    
    if merged_df is None:
        print("CRDT_SCORE verileri alınamadı!")
        return
    
    # 3. Veri temizleme
    print("\n3. Adım: Veri temizleniyor...")
    merged_df = clean_numeric_data(merged_df)
    
    # 4. Solidity skorlarını hesapla
    print("\n4. Adım: Solidity skorları hesaplanıyor...")
    merged_df = calculate_solidity_scores(merged_df)
    
    # 5. Sonuçları kaydet
    print("\n5. Adım: Sonuçlar kaydediliyor...")
    output_file = 'allcomek_sld.csv'
    merged_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"Sonuçlar '{output_file}' dosyasına kaydedildi")
    
    # 6. Analiz göster
    show_top_bottom_cmon_scores(merged_df)
    
    print("\n=== İŞLEM TAMAMLANDI ===")
    print(f"Toplam {len(merged_df)} hisse işlendi")
    print(f"Sonuç dosyası: {output_file}")

if __name__ == "__main__":
    main()