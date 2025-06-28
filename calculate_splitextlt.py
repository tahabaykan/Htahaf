import pandas as pd
import numpy as np
from datetime import datetime

def load_required_data():
    """Load data from all required sources"""
    try:
        # Normalize edilmiş verileri ADV bilgisiyle yükle
        normalized_df = pd.read_csv('normalize_extlt_with_adv.csv')
        
        # Yeni solidity skorlarını yükle - extlt versiyonu kullan
        solidity_df = pd.read_csv('scored_extlt.csv')  # scored_stocks.csv yerine extlt versiyonu
        print("Doldurulmuş SOLIDITY skorları 'scored_extlt.csv' dosyasından yüklendi")
        
        # IBKR verilerini yükle (CUR_YIELD için)
        ibkr_df = pd.read_csv('sma_results.csv')
        
        # Common stock performans verilerini yükle
        common_stock_df = pd.read_csv('common_stock_results.csv')
        print("Common stock performans verileri 'common_stock_results.csv' dosyasından yüklendi")
        
        print("Tüm veri dosyaları başarıyla yüklendi!")
        
        # Bilgi yazdır
        print(f"normalize_extlt_with_adv.csv: {len(normalized_df)} satır")
        print(f"scored_extlt.csv: {len(solidity_df)} satır")
        print(f"extlt_results.csv: {len(ibkr_df)} satır")
        print(f"common_stock_results.csv: {len(common_stock_df)} satır")
        
        # SOLIDITY_SCORE kontrolü
        missing_solidity = solidity_df['SOLIDITY_SCORE'].isna().sum()
        if missing_solidity > 0:
            print(f"UYARI: scored_extlt.csv'de hala {missing_solidity} eksik SOLIDITY_SCORE var!")
        else:
            print("scored_extlt.csv'de tüm SOLIDITY_SCORE değerleri mevcut.")
        
        # ADV değerleri kontrolü
        if 'AVG_ADV' in normalized_df.columns:
            missing_adv = normalized_df['AVG_ADV'].isna().sum()
            print(f"AVG_ADV değerleri kontrolü: {len(normalized_df) - missing_adv}/{len(normalized_df)} hisse için mevcut")
        else:
            print("UYARI: normalize_extlt_with_adv.csv dosyasında AVG_ADV kolonu bulunamadı!")
        
        return normalized_df, solidity_df, ibkr_df, common_stock_df
    
    except Exception as e:
        print(f"Veri yükleme hatası: {e}")
        return None, None, None, None

def prepare_data_for_calculation(normalized_df, solidity_df, ibkr_df, common_stock_df):
    """Prepare and merge all required data"""
    try:
        # Print column names for debugging
        print("\nAvailable columns in normalized_df:")
        print(sorted(normalized_df.columns.tolist()))
        
        # Duplike satırları temizle
        normalized_df = normalized_df.drop_duplicates(subset=['PREF IBKR'])
        
        # Yeni SOLIDITY skorları için birleştir
        df = normalized_df.merge(
            solidity_df[['PREF IBKR', 'SOLIDITY_SCORE']], 
            on='PREF IBKR',
            how='left'
        )
        
        # Birleştirme sonuçlarını kontrol et
        merge_success = df['SOLIDITY_SCORE'].notna().sum()
        print(f"\nSOLIDITY_SCORE birleştirildi: {merge_success}/{len(df)} hisse")
        
        # Common stock performans verilerini birleştir
        # CMON sütunu üzerinden birleştir
        df = df.merge(
            common_stock_df[['CMON', 'Normalized_COM_6M', 'Normalized_COM_3M', 'Normalized_52W_LOW']], 
            left_on='CMON',
            right_on='CMON',
            how='left'
        )
        
        # Common stock birleştirme sonuçlarını kontrol et
        common_merge_success = df['Normalized_COM_6M'].notna().sum()
        print(f"Common stock verileri birleştirildi: {common_merge_success}/{len(df)} hisse")
        
        # Not: CUR_YIELD artık kullanılmadığı için hesaplanmayacak
        
        # Tüm numeric kolonları 2 ondalık basamağa yuvarla
        numeric_cols = df.select_dtypes(include=['float64']).columns
        for col in numeric_cols:
            df[col] = df[col].round(2)
            
        return df
        
    except Exception as e:
        print(f"\nVeri hazırlama hatası: {e}")
        print("Hata detayı:", str(e))
        return None

def calculate_final_thg(df):
    """Calculate FINAL THG score based on Excel formula"""
    try:
        # Gerekli kolonları kontrol et
        required_cols = [
            'SMA88_chg_norm',           # O2 - Normalized CHG88
            'SMA268_chg_norm',          # Q2 - Normalized CHG 268
            '6M_High_diff_norm',        # S2 - Normalized 6M H
            '6M_Low_diff_norm',         # U2 - Normalized 6M L
            '1Y_High_diff_norm',        # W2 - Normalized 52HOP (52 Week High)
            '1Y_Low_diff_norm',         # Y2 - Normalized 52LOP (52 Week Low)
            'SOLIDITY_SCORE',           # M2 - Solidity Test
            'AVG_ADV'                   # Average Daily Volume
        ]
        
        # ADV için varsayılan ağırlık
        adv_weight = 0.00025
        
        # AVG_ADV için opsiyonel kontrol - yoksa formülden çıkar
        use_adv = 'AVG_ADV' in df.columns
        if not use_adv:
            print("AVG_ADV kolonu bulunamadı. Volume bilgisi olmadan hesaplamaya devam ediliyor.")
            required_cols.remove('AVG_ADV')
        else:
            print(f"AVG_ADV verileri bulundu, ağırlık: {adv_weight:.6f}")
        
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"Eksik kolonlar: {missing_cols}")
            return df
        
        # Eksik değerleri raporla
        for col in required_cols:
            missing_count = df[col].isna().sum()
            if missing_count > 0:
                print(f"{col} için {missing_count} eksik değer var")
        
        # Eksik değerleri en kötü %12'lik değerlerle doldur
        for col in required_cols:
            if df[col].isna().any():
                quantile_value = df[col].dropna().quantile(0.12).round(2)
                print(f"{col} eksik değerleri en alt %12'lik dilim değeri {quantile_value} ile dolduruluyor")
                df[col] = df[col].fillna(quantile_value)
        
        # ADV değeri varsa formüle ekle, yoksa eski formülü kullan
        if use_adv:
            df['FINAL_THG'] = (
                # SMA değişimleri - Etkisi azaltıldı
                (df['SMA88_chg_norm'] * 1.8 + 
                 df['SMA268_chg_norm'] * 1.4) +
                
                # Normalized değerler grubu - Etkisi daha da azaltıldı
                (df['6M_High_diff_norm'] + 
                 df['6M_Low_diff_norm'] + 
                 df['1Y_High_diff_norm'] + 
                 df['1Y_Low_diff_norm'] * 1.2) * 0.15 +
                
                # Solidity Score * 3.5 (önemi artırıldı)
                df['SOLIDITY_SCORE'] * 3.5 +
                
                # AVG_ADV * ağırlık
                df['AVG_ADV'] * adv_weight
            )
        else:
            df['FINAL_THG'] = (
                # SMA değişimleri - Etkisi azaltıldı
                (df['SMA88_chg_norm'] * 1.8 + 
                 df['SMA268_chg_norm'] * 1.4) +
                
                # Normalized değerler grubu - Etkisi daha da azaltıldı
                (df['6M_High_diff_norm'] + 
                 df['6M_Low_diff_norm'] + 
                 df['1Y_High_diff_norm'] + 
                 df['1Y_Low_diff_norm'] * 1.2) * 0.15 +
                
                # Solidity Score * 3.5 (önemi artırıldı)
                df['SOLIDITY_SCORE'] * 3.5
            )
        
        # FINAL_THG değerini 2 ondalık basamağa yuvarla
        df['FINAL_THG'] = df['FINAL_THG'].round(2)
        
        # Common Stock Performansı Düzeltmesi
        # Problemli şirketleri tanımla 
        problem_companies = ['RC', 'HFRO', 'EIX', 'PEB', 'INN', 'HPP',]  # HPP eklendi
        
        # Common Stock performansına göre düzeltme faktörü
        print("\nCommon Stock performansı düzeltmeleri uygulanıyor...")
        
        # Common stock performans düzeltme faktörü
        df['CS_FACTOR'] = 1.0  # Varsayılan değer: 1.0 (düzeltme yok)
        
        # Şirketlere özel düzeltmeler
        for company in problem_companies:
            mask = df['CMON'] == company
            if mask.any():
                # Eğer bu şirket tüm şirketlerin %n'sini oluşturuyorsa, onlara özel indirim uygula
                discount = 0.75  # %25 indirim
                df.loc[mask, 'CS_FACTOR'] = discount
                print(f"  {company} için common stock performans faktörü: {discount:.2f} (%{(1-discount)*100:.0f} indirim)")
        
        # Diğer common stock performans değerlendirmeleri
        # COM_6M ve COM_3M değerlerine göre değerlendirme
        if 'Normalized_COM_6M' in df.columns and 'Normalized_COM_3M' in df.columns:
            # Common stock performansı kötü olan ancak henüz belirli bir şirket listesinde olmayan hisseleri bul
            com_perf_mask = ((df['Normalized_COM_6M'] < 30) & (df['Normalized_COM_3M'] < 25)) & (df['CS_FACTOR'] == 1.0)
            df.loc[com_perf_mask, 'CS_FACTOR'] = 0.85  # %15 indirim
            print(f"  Common stock son 6 ay ve 3 ay performansı kötü olan {com_perf_mask.sum()} hisse için %15 indirim")
            
            # Daha az kötü performans için daha az indirim
            mild_perf_mask = ((df['Normalized_COM_6M'] < 40) & (df['Normalized_COM_3M'] < 35)) & (df['CS_FACTOR'] == 1.0)
            df.loc[mild_perf_mask, 'CS_FACTOR'] = 0.92  # %8 indirim
            print(f"  Common stock performansı sınırda olan {mild_perf_mask.sum()} hisse için %8 indirim")
            
        # FINAL_THG skorunu common stock faktörüyle çarp
        df['FINAL_THG'] = df['FINAL_THG'] * df['CS_FACTOR']
        df['FINAL_THG'] = df['FINAL_THG'].round(2)  # Tekrar yuvarlama
        
        # Debug bilgisi
        print("\n=== FINAL THG Bileşen Katkıları ===")
        component_cols = [
            'PREF IBKR',
            'SMA88_chg_norm', 'SMA268_chg_norm',
            '6M_High_diff_norm', '6M_Low_diff_norm',
            '1Y_High_diff_norm', '1Y_Low_diff_norm',
            'SOLIDITY_SCORE',
            'CS_FACTOR', 'FINAL_THG'
        ]
        print(df[component_cols].head().round(2))
        
        return df
        
    except Exception as e:
        print(f"FINAL THG hesaplama hatası: {e}")
        return df

def calculate_yield_to_call(df):
    try:
        today = datetime.now()
        df['CALL_DATE'] = pd.to_datetime(df['CALL DATE'], errors='coerce')
        df['DAYS_TO_CALL'] = (df['CALL_DATE'] - today).dt.days

        # Bir sonraki temettü tarihini hesapla
        df['NEXT_EX_DIV'] = pd.to_datetime(df['EX-DIV DATE'], errors='coerce')
        df['NEXT_EX_DIV'] = df['NEXT_EX_DIV'] + pd.DateOffset(months=3)

        # Call Date'e kadar olan süreyi 3 aylık periyotlara böl
        df['PERIODS_TO_CALL'] = (df['DAYS_TO_CALL'] / 90).round()

        # Toplam temettü hesaplama
        df['TOTAL_DIVIDENDS'] = df['DIV AMOUNT'] * df['PERIODS_TO_CALL']

        # Div adj.price'ı kullanarak Yield to Call hesaplama
        df['YIELD_TO_CALL'] = ((25 + df['TOTAL_DIVIDENDS']) / df['Div adj.price'] - 1) / (df['DAYS_TO_CALL'] / 365)
        df['YIELD_TO_CALL'] = df['YIELD_TO_CALL'].round(4)  # 4 ondalık basamağa yuvarla

        # Debug: VLYPP ve WTFCP için detaylı hesaplama adımlarını yazdır
        debug_stocks = ['VLYPP', 'WTFCP']
        for stock in debug_stocks:
            stock_data = df[df['PREF IBKR'] == stock].iloc[0]
            print(f"\nDetaylı hesaplama adımları - {stock}:")
            print(f"Call Date: {stock_data['CALL_DATE']}")
            print(f"Days to Call: {stock_data['DAYS_TO_CALL']}")
            print(f"Next Ex-Div: {stock_data['NEXT_EX_DIV']}")
            print(f"Periods to Call: {stock_data['PERIODS_TO_CALL']}")
            print(f"Div Amount: {stock_data['DIV AMOUNT']}")
            print(f"Total Dividends: {stock_data['TOTAL_DIVIDENDS']}")
            print(f"Div adj.price: {stock_data['Div adj.price']}")
            print(f"Yield to Call: {stock_data['YIELD_TO_CALL']}")

        return df
    except Exception as e:
        print(f"Yield to Call hesaplama hatası: {e}")
        return df

def calculate_expannr(df):
    # Expannr = ((SMA88 - DIV AMOUNT / 2) - Div adj.price) / 25) * 24
    try:
        df['Expannr'] = (((df['SMA88_chg_norm'] - df['DIV AMOUNT'] / 2) - df['Div adj.price']) / 25) * 12
        df['Expannr'] = df['Expannr'].round(4)  # 4 ondalık basamağa yuvarla
        return df
    except Exception as e:
        print(f"Expannr hesaplama hatası: {e}")
        return df

def calculate_yield_to_maturity(df):
    try:
        today = datetime.now()
        df['MATUR_DATE'] = pd.to_datetime(df['MATUR DATE'], errors='coerce')
        df['DAYS_TO_MATUR'] = (df['MATUR_DATE'] - today).dt.days

        # Bir sonraki temettü tarihini hesapla
        df['NEXT_EX_DIV'] = pd.to_datetime(df['EX-DIV DATE'], errors='coerce')
        df['NEXT_EX_DIV'] = df['NEXT_EX_DIV'] + pd.DateOffset(months=3)

        # Maturity Date'e kadar olan süreyi 3 aylık periyotlara böl
        df['PERIODS_TO_MATUR'] = (df['DAYS_TO_MATUR'] / 90).round()

        # Toplam temettü hesaplama
        df['TOTAL_DIVIDENDS'] = df['DIV AMOUNT'] * df['PERIODS_TO_MATUR']

        # Div adj.price'ı kullanarak Yield to Maturity hesaplama
        df['YIELD_TO_MATUR'] = ((25 + df['TOTAL_DIVIDENDS']) / df['Div adj.price'] - 1) / (df['DAYS_TO_MATUR'] / 365)
        df['YIELD_TO_MATUR'] = df['YIELD_TO_MATUR'].round(4)  # 4 ondalık basamağa yuvarla

        return df
    except Exception as e:
        print(f"Yield to Maturity hesaplama hatası: {e}")
        return df

def main():
    try:
        # Verileri yükle
        normalized_df, solidity_df, ibkr_df, common_stock_df = load_required_data()
        
        if normalized_df is None or solidity_df is None or ibkr_df is None or common_stock_df is None:
            print("Veri yükleme başarısız!")
            return
        
        # TLT ile ilgili satırları filtrele
        if 'PREF IBKR' in normalized_df.columns:
            before_filter = len(normalized_df)
            normalized_df = normalized_df[~normalized_df['PREF IBKR'].str.contains('TLT', na=False)]
            removed = before_filter - len(normalized_df)
            if removed > 0:
                print(f"Normalize edilmiş veriden {removed} adet TLT satırı çıkarıldı.")
        
        # Verileri hazırla
        merged_df = prepare_data_for_calculation(normalized_df, solidity_df, ibkr_df, common_stock_df)
        
        if merged_df is None:
            print("Veri hazırlama başarısız!")
            return
        
        # TLT ile ilgili satırları tekrar kontrol et ve filtrele
        if 'PREF IBKR' in merged_df.columns:
            before_filter = len(merged_df)
            merged_df = merged_df[~merged_df['PREF IBKR'].str.contains('TLT', na=False)]
            removed = before_filter - len(merged_df)
            if removed > 0:
                print(f"Birleştirilmiş veriden {removed} adet TLT satırı çıkarıldı.")
        
        # Duplike satırları temizle (PREF IBKR kolonuna göre)
        before_dedup = len(merged_df)
        merged_df = merged_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
        removed_dups = before_dedup - len(merged_df)
        if removed_dups > 0:
            print(f"\nDuplike satırlar temizlendi: {removed_dups} adet tekrar eden kayıt kaldırıldı.")
        
        # FINAL_THG değerlerini hesapla
        result_df = calculate_final_thg(merged_df)
        
        # Expannr hesapla
        result_df = calculate_expannr(result_df)
        
        # Yield to Call hesapla
        result_df = calculate_yield_to_call(result_df)
        
        # Yield to Maturity hesapla
        result_df = calculate_yield_to_maturity(result_df)
        
        # Hisseleri kategorilerine göre ayır
        # FF-FR_ kolonundaki değerlere göre tam eşleşme yaparak ayır
        ff_mask = result_df['FF-FR_'].astype(str).str.strip().str.upper() == 'FF'
        flr_mask = result_df['FF-FR_'].astype(str).str.strip().str.upper() == 'FLR'
        nff_mask = result_df['FF-FR_'].astype(str).str.strip().str.upper() == 'NFF'
        
        # Maturity Date'e göre Matur hisseleri belirle (2033'ten küçük olanlar)
        result_df['MATUR_YEAR'] = pd.to_datetime(result_df['MATUR DATE'], errors='coerce').dt.year
        matur_mask = result_df['MATUR_YEAR'].notna() & (result_df['MATUR_YEAR'] < 2033)
        
        # Her kategori için LFINAL_THG hesapla
        result_df['LFINAL_THG'] = result_df['FINAL_THG']  # Varsayılan değer (normal hisseler için)
        
        # FF hisseleri için hesaplama
        result_df.loc[ff_mask, 'LFINAL_THG'] = (
            result_df.loc[ff_mask, 'FINAL_THG'] * 0.6 +  # FINAL_THG'yi 0.6 ile çarp
            result_df.loc[ff_mask, 'Expannr'] * 15  # Expannr'ı 15 ile çarp
        ).round(4)
        
        # FLR hisseleri için hesaplama
        result_df.loc[flr_mask, 'LFINAL_THG'] = (
            result_df.loc[flr_mask, 'Expannr'] * 20 +  # Expannr'ı 20 ile çarp
            result_df.loc[flr_mask, 'FINAL_THG'] * 0.12  # FINAL_THG'yi 0.12 ile çarp
        ).round(4)
        
        # NFF hisseleri için hesaplama
        result_df.loc[nff_mask, 'LFINAL_THG'] = (
            result_df.loc[nff_mask, 'YIELD_TO_CALL'] * 600 +  # Yield to Call'ı 600 ile çarp
            result_df.loc[nff_mask, 'FINAL_THG'] * 0.3 +  # FINAL_THG'yi 0.3 ile çarp
            result_df.loc[nff_mask, 'Expannr'] * 16  # Expannr'ı 16 ile çarp
        ).round(4)
        
        # Matur hisseleri için hesaplama
        result_df.loc[matur_mask, 'LFINAL_THG'] = (
            result_df.loc[matur_mask, 'YIELD_TO_MATUR'] * 600 +  # Yield to Maturity'yi 600 ile çarp
            result_df.loc[matur_mask, 'FINAL_THG'] * 0.2 +  # FINAL_THG'yi 0.2 ile çarp
            result_df.loc[matur_mask, 'Expannr'] * 14  # Expannr'ı 14 ile çarp
        ).round(4)
        
        # Normal hisseler için hesaplama
        normal_mask = ~(ff_mask | flr_mask | matur_mask | nff_mask)
        result_df.loc[normal_mask, 'LFINAL_THG'] = (
            result_df.loc[normal_mask, 'FINAL_THG'] * 0.6 +  # FINAL_THG'yi 0.6 ile çarp
            result_df.loc[normal_mask, 'Expannr'] * 6  # Expannr'ı 6 ile çarp
        ).round(4)
        
        # Her kategori için ayrı CSV dosyaları oluştur
        # FF hisseleri
        ff_df = result_df[ff_mask].copy()
        ff_df = ff_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
        ff_df = ff_df.rename(columns={"FINAL_THG": "LFINAL_THG", "LFINAL_THG": "FINAL_THG"})
        ff_df.to_csv('ffextlt.csv', index=False, float_format='%.4f', encoding='utf-8-sig')
        print(f"\nFF hisseleri 'ffextlt.csv' dosyasına kaydedildi. ({len(ff_df)} hisse)")
        
        # FLR hisseleri
        flr_df = result_df[flr_mask].copy()
        flr_df = flr_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
        flr_df = flr_df.rename(columns={"FINAL_THG": "LFINAL_THG", "LFINAL_THG": "FINAL_THG"})
        flr_df.to_csv('flrextlt.csv', index=False, float_format='%.4f', encoding='utf-8-sig')
        print(f"FLR hisseleri 'flrextlt.csv' dosyasına kaydedildi. ({len(flr_df)} hisse)")
        
        # NFF hisseleri
        nff_df = result_df[nff_mask].copy()
        nff_df = nff_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
        nff_df = nff_df.rename(columns={"FINAL_THG": "LFINAL_THG", "LFINAL_THG": "FINAL_THG"})
        nff_df.to_csv('nffextlt.csv', index=False, float_format='%.4f', encoding='utf-8-sig')
        print(f"NFF hisseleri 'nffextlt.csv' dosyasına kaydedildi. ({len(nff_df)} hisse)")
        
        # Matur hisseleri
        matur_df = result_df[matur_mask].copy()
        matur_df = matur_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
        matur_df = matur_df.rename(columns={"FINAL_THG": "LFINAL_THG", "LFINAL_THG": "FINAL_THG"})
        matur_df.to_csv('maturextlt.csv', index=False, float_format='%.4f', encoding='utf-8-sig')
        print(f"Matur hisseleri 'maturextlt.csv' dosyasına kaydedildi. ({len(matur_df)} hisse)")
        
        # Normal hisseler (hiçbir kategoriye girmeyenler)
        normal_mask = ~(ff_mask | flr_mask | matur_mask | nff_mask)
        normal_df = result_df[normal_mask].copy()
        normal_df = normal_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
        normal_df.to_csv('duzextlt.csv', index=False, float_format='%.4f', encoding='utf-8-sig')
        print(f"Normal hisseler 'duzextlt.csv' dosyasına kaydedildi. ({len(normal_df)} hisse)")
        
        # Her kategori için en yüksek ve en düşük LFINAL_THG skorlarını göster
        categories = {
            'FF': ff_df,
            'FLR': flr_df,
            'NFF': nff_df,
            'Matur': matur_df,
            'Normal': normal_df
        }
        
        for category, df in categories.items():
            if len(df) > 0:
                print(f"\n=== {category} Hisseleri - En Yüksek LFINAL_THG Skorları (Top 5) ===")
                if category == 'Matur':
                    print("PREF IBKR  LFINAL_THG  FINAL_THG  Expannr  YIELD_TO_MATUR")
                elif category == 'NFF':
                    print("PREF IBKR  LFINAL_THG  FINAL_THG  Expannr  YIELD_TO_CALL")
                else:  # FF, FLR ve Normal hisseler için
                    print("PREF IBKR  LFINAL_THG  FINAL_THG  Expannr")
                print("-" * 70)
                
                if category == 'Matur':
                    top_5 = df.nlargest(5, 'LFINAL_THG')[
                        ['PREF IBKR', 'LFINAL_THG', 'FINAL_THG', 'Expannr', 'YIELD_TO_MATUR']
                    ]
                    for _, row in top_5.iterrows():
                        print(f"{row['PREF IBKR']:<10} {row['LFINAL_THG']:>10.4f} {row['FINAL_THG']:>10.4f} "
                              f"{row['Expannr']:>8.4f} {row['YIELD_TO_MATUR']:>12.4f}")
                elif category == 'NFF':
                    top_5 = df.nlargest(5, 'LFINAL_THG')[
                        ['PREF IBKR', 'LFINAL_THG', 'FINAL_THG', 'Expannr', 'YIELD_TO_CALL']
                    ]
                    for _, row in top_5.iterrows():
                        print(f"{row['PREF IBKR']:<10} {row['LFINAL_THG']:>10.4f} {row['FINAL_THG']:>10.4f} "
                              f"{row['Expannr']:>8.4f} {row['YIELD_TO_CALL']:>12.4f}")
                else:  # FF, FLR ve Normal hisseler için
                    top_5 = df.nlargest(5, 'LFINAL_THG')[
                        ['PREF IBKR', 'LFINAL_THG', 'FINAL_THG', 'Expannr']
                    ]
                    for _, row in top_5.iterrows():
                        print(f"{row['PREF IBKR']:<10} {row['LFINAL_THG']:>10.4f} {row['FINAL_THG']:>10.4f} "
                              f"{row['Expannr']:>8.4f}")
                
    except Exception as e:
        print(f"Bir hata oluştu: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()