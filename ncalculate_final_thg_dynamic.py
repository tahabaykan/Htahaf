import pandas as pd
import numpy as np
import os
import market_risk_analyzer as mra
from datetime import datetime
import glob



def get_market_weights():
    # Piyasa koşullarına göre ağırlıkları belirler
    weights_file = 'market_weights.csv'
    
    # Dosya varsa ve bugüne aitse kullan
    if os.path.exists(weights_file):
        try:
            df = pd.read_csv(weights_file)
            if len(df) > 0:
                today = datetime.now().strftime('%Y-%m-%d')
                if 'date' in df.columns and df['date'].iloc[0] == today:
                    weights = {
                        'solidity_weight': df['solidity_weight'].iloc[0],
                        'yield_weight': df['yield_weight'].iloc[0]
                    }
                    print(f"\nBugünün piyasa ağırlıkları kullanılıyor: Solidity={weights['solidity_weight']:.2f}, Yield={weights['yield_weight']:.2f}")
                    return weights
        except Exception as e:
            print(f"Kaydedilmiş ağırlıkları yüklerken hata: {e}")
    
    # IBKR'den güncel piyasa koşullarını analiz et
    try:
        print("\nPiyasa koşulları analiz ediliyor...")
        market_weights = mra.main()
        return market_weights
    except Exception as e:
        print(f"Piyasa analizi yapılamadı: {e}")
        # Varsayılan ağırlıkları döndür
        return {'solidity_weight': 2.5, 'yield_weight': 3}  # Başlangıç değeri 3

def get_csv_files(target_file=None):
    """İşlenecek CSV dosyalarını bul"""
    # Eğer target_file belirtilmişse, sadece o dosyayı döndür
    if target_file and target_file.startswith('finek'):
        adv_file = target_file.replace('finek', 'advek')
        if os.path.exists(adv_file):
            adv_files = [adv_file]
            print(f"Sadece {adv_file} dosyası işlenecek")
        else:
            print(f"UYARI: {adv_file} bulunamadı, tüm ADV dosyaları işlenecek")
            adv_files = glob.glob('advek*.csv')
    else:
    # ADV ile başlayan dosyalar (normalize_data_with_adv.csv yerine)
    adv_files = glob.glob('advek*.csv')
    
    # SEK ile başlayan dosyalar (sma_results.csv yerine)
    sek_files = glob.glob('sek*.csv')
    
    return adv_files, sek_files

def load_required_data(target_file=None):
    """Load data from all required sources"""
    try:
        # CSV dosyalarını bul
        adv_files, sek_files = get_csv_files(target_file)
        
        print(f"Bulunan ADV dosyaları: {adv_files}")
        print(f"Bulunan SEK dosyaları: {sek_files}")
        
        # Eğer target_file belirtilmişse, sadece o dosyayı yükle
        if target_file:
            # target_file'dan ADV dosyasını belirle
            # Örnek: finekheldkuponlu.csv -> advekheldkuponlu.csv
            if target_file.startswith('finek'):
                adv_file = target_file.replace('finek', 'advek')
                if adv_file in adv_files:
                    adv_files = [adv_file]
                    print(f"Sadece {adv_file} dosyası yüklenecek")
                else:
                    print(f"UYARI: {adv_file} bulunamadı, tüm ADV dosyaları yüklenecek")
                    adv_files = glob.glob('advek*.csv')
            else:
                # target_file belirtilmiş ama finek ile başlamıyorsa, tüm dosyaları yükle
                adv_files = glob.glob('advek*.csv')
        
        # Tüm ADV dosyalarını birleştir
        all_adv_data = []
        for file in adv_files:
            try:
                df = pd.read_csv(file, encoding='utf-8-sig')
                df['source_file'] = file  # Hangi dosyadan geldiğini takip et
                all_adv_data.append(df)
                print(f"✓ {file} yüklendi: {len(df)} satır")
            except Exception as e:
                print(f"✗ {file} yüklenirken hata: {e}")
        
        if all_adv_data:
            normalized_df = pd.concat(all_adv_data, ignore_index=True)
            print(f"Toplam ADV verisi: {len(normalized_df)} satır")
            
            # Duplicate kontrolü
            before_dedup = len(normalized_df)
            normalized_df = normalized_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
            after_dedup = len(normalized_df)
            if before_dedup != after_dedup:
                print(f"UYARI: {before_dedup - after_dedup} duplicate hisse temizlendi")
        else:
            print("HATA: Hiç ADV dosyası bulunamadı!")
            return None, None, None
        
        # allcomek_sld.csv dosyasından solidity verilerini yükle
        print("allcomek_sld.csv dosyası yükleniyor...")
        try:
            solidity_df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
            print(f"✓ allcomek_sld.csv yüklendi: {len(solidity_df)} satır")
        except Exception as e:
            print(f"✗ allcomek_sld.csv yüklenirken hata: {e}")
            return None, None, None
        
        # Tüm SEK dosyalarını birleştir
        all_sek_data = []
        for file in sek_files:
            try:
                df = pd.read_csv(file, encoding='utf-8-sig')
                df['source_file'] = file  # Hangi dosyadan geldiğini takip et
                all_sek_data.append(df)
                print(f"✓ {file} yüklendi: {len(df)} satır")
            except Exception as e:
                print(f"✗ {file} yüklenirken hata: {e}")
        
        if all_sek_data:
            ibkr_df = pd.concat(all_sek_data, ignore_index=True)
            print(f"Toplam SEK verisi: {len(ibkr_df)} satır")
        else:
            print("HATA: Hiç SEK dosyası bulunamadı!")
            return None, None, None
        
        print("\nTüm veri dosyaları başarıyla yüklendi!")
        
        # Bilgi yazdır
        print(f"ADV dosyaları: {len(adv_files)} adet, toplam {len(normalized_df)} satır")
        print(f"allcomek_sld.csv: {len(solidity_df)} satır")
        print(f"SEK dosyaları: {len(sek_files)} adet, toplam {len(ibkr_df)} satır")
        
        # SOLIDITY_SCORE_NORM kontrolü
        missing_solidity = solidity_df['SOLIDITY_SCORE_NORM'].isna().sum()
        if missing_solidity > 0:
            print(f"UYARI: allcomek_sld.csv'de hala {missing_solidity} eksik SOLIDITY_SCORE_NORM var!")
        else:
            print("allcomek_sld.csv'de tüm SOLIDITY_SCORE_NORM değerleri mevcut.")
        
        # ADV değerleri kontrolü
        if 'AVG_ADV' in normalized_df.columns:
            missing_adv = normalized_df['AVG_ADV'].isna().sum()
            print(f"AVG_ADV değerleri kontrolü: {len(normalized_df) - missing_adv}/{len(normalized_df)} hisse için mevcut")
        else:
            print("UYARI: ADV dosyalarında AVG_ADV kolonu bulunamadı!")
        
        return normalized_df, solidity_df, ibkr_df
    
    except Exception as e:
        print(f"Veri yükleme hatası: {e}")
        return None, None, None

def prepare_data_for_calculation(normalized_df, solidity_df, ibkr_df, market_weights=None):
    """Prepare and merge all required data"""
    try:
        # Print column names for debugging
        print("\nAvailable columns in normalized_df:")
        print(sorted(normalized_df.columns.tolist()))
        
        # Duplike satırları temizle
        normalized_df = normalized_df.drop_duplicates(subset=['PREF IBKR'])
        
        # SOLIDITY_SCORE_NORM için birleştir
        df = normalized_df.merge(
            solidity_df[['PREF IBKR', 'SOLIDITY_SCORE_NORM']], 
            on='PREF IBKR',
            how='left'
        )
        
        # Birleştirme sonuçlarını kontrol et
        merge_success = df['SOLIDITY_SCORE_NORM'].notna().sum()
        print(f"\nSOLIDITY_SCORE_NORM birleştirildi: {merge_success}/{len(df)} hisse")
        
        # CUR_YIELD hesaplama
        try:
            # Veri tiplerini kontrol et
            print("\nCOUPON örnek veriler:")
            print(normalized_df[['PREF IBKR', 'COUPON']].head())
            
            # COUPON'u hiç değiştirme, orijinal veriyi koru
            df['COUPON'] = normalized_df['COUPON']  # ADVEK'ten gelen veri aynen kalır
            # DIV AMOUNT'u sayısala çevir
            df['DIV AMOUNT'] = pd.to_numeric(normalized_df['DIV AMOUNT'], errors='coerce')
            df['Div adj.price'] = pd.to_numeric(normalized_df['Div adj.price'], errors='coerce')
            df['Last Price'] = pd.to_numeric(normalized_df['Last Price'], errors='coerce')
            
            # CUR_YIELD hesapla: COUPON oranını kullan (DIV_AMOUNT'u değiştirme)
            def calc_cur_yield(row):
                price = row['Div adj.price'] if pd.notnull(row['Div adj.price']) and row['Div adj.price'] != 0 else row['Last Price']
                coupon_str = str(row['COUPON']) if pd.notna(row['COUPON']) else '0'
                coupon_rate = float(coupon_str.replace('%', '')) if '%' in coupon_str else float(coupon_str)
                if pd.notnull(coupon_rate) and price and price != 0:
                    # COUPON oranını kullan (DIV_AMOUNT'u değiştirme)
                    return (coupon_rate / 100) / (price / 25) * 100
                else:
                    return np.nan
            df['CUR_YIELD'] = df.apply(calc_cur_yield, axis=1)
            
            # Tüm numeric kolonları 2 ondalık basamağa yuvarla, CUR_YIELD hariç
            numeric_cols = df.select_dtypes(include=['float64']).columns
            for col in numeric_cols:
                if col != 'CUR_YIELD':  # CUR_YIELD'i atla
                    df[col] = df[col].round(2)
            
            # CUR_YIELD'i 4 ondalık basamağa yuvarla
            df['CUR_YIELD'] = df['CUR_YIELD'].round(4)
            
            # Debug bilgisi
            print("\n=== CUR_YIELD Hesaplama Detayları ===")
            print("Formül: (COUPON/100) / (price/25) * 100")
            print(df[['PREF IBKR', 'COUPON', 'DIV AMOUNT', 'Div adj.price', 'Last Price', 'CUR_YIELD']].head().to_string())
            
            return df
            
        except Exception as e:
            print(f"\nCUR_YIELD hesaplama hatası: {e}")
            print("\nKolon değerleri:")
            print("COUPON değerleri:", normalized_df['COUPON'].unique()[:5])
            print("Div adj.price değerleri:", normalized_df['Div adj.price'].unique()[:5])
            print("Last Price değerleri:", normalized_df['Last Price'].unique()[:5])
            raise
        
    except Exception as e:
        print(f"\nVeri hazırlama hatası: {e}")
        print("Hata detayı:", str(e))
        return None

def calculate_ytc(row):
    """Yield to Call hesapla"""
    try:
        # Gerekli değerleri al
        coupon_str = str(row['COUPON']) if pd.notna(row['COUPON']) else '0'
        coupon = float(coupon_str.replace('%', '')) if '%' in coupon_str else float(coupon_str)
        current_price = float(row['Div adj.price']) if pd.notna(row['Div adj.price']) else float(row['Last Price'])
        par_value = 25.0  # Preferred stock için standart değer
        
        # Call date'i parse et
        if pd.notna(row['CALL DATE']):
            try:
                call_date = pd.to_datetime(row['CALL DATE'])
                today = pd.to_datetime(datetime.now())
                days_to_call = (call_date - today).days
                years_to_call = days_to_call / 365.25
            except:
                years_to_call = 3.0  # Varsayılan değer
        else:
            years_to_call = 3.0  # Varsayılan değer
        
        # YTC hesapla
        if current_price > 0 and years_to_call > 0:
            # Yıllık kupon ödemesi
            annual_coupon = (coupon / 100) * par_value
            
            # YTC formülü: (Kupon + (Par - Fiyat) / Süre) / Fiyat
            ytc = (annual_coupon + (par_value - current_price) / years_to_call) / current_price
            return ytc * 100  # Yüzde olarak döndür
        else:
            return np.nan
            
    except Exception as e:
        print(f"YTC hesaplama hatası ({row.get('PREF IBKR', 'Bilinmeyen')}): {e}")
        return np.nan

def calculate_ytm(row):
    """Yield to Maturity hesapla"""
    try:
        # Gerekli değerleri al
        coupon_str = str(row['COUPON']) if pd.notna(row['COUPON']) else '0'
        coupon = float(coupon_str.replace('%', '')) if '%' in coupon_str else float(coupon_str)
        current_price = float(row['Div adj.price']) if pd.notna(row['Div adj.price']) else float(row['Last Price'])
        par_value = 25.0  # Preferred stock için standart değer
        
        # Maturity date'i parse et
        if pd.notna(row['MATUR DATE']):
            try:
                maturity_date = pd.to_datetime(row['MATUR DATE'])
                today = pd.to_datetime(datetime.now())
                days_to_maturity = (maturity_date - today).days
                years_to_maturity = days_to_maturity / 365.25
            except:
                years_to_maturity = 5.0  # Varsayılan değer
        else:
            years_to_maturity = 5.0  # Varsayılan değer
        
        # YTM hesapla
        if current_price > 0 and years_to_maturity > 0:
            # Yıllık kupon ödemesi
            annual_coupon = (coupon / 100) * par_value
            
            # YTM formülü: (Kupon + (Par - Fiyat) / Süre) / Fiyat
            ytm = (annual_coupon + (par_value - current_price) / years_to_maturity) / current_price
            return ytm * 100  # Yüzde olarak döndür
        else:
            return np.nan
            
    except Exception as e:
        print(f"YTM hesaplama hatası ({row.get('PREF IBKR', 'Bilinmeyen')}): {e}")
        return np.nan

def calculate_expected_annual_return(row):
    """
    Her hisse için beklenen yıllık getiri hesapla
    
    Formül:
    - Expected sale price = SMA63 - (div_amount / 2)
    - Total days = time_to_div + 3
    - Final value = expected_sale_price + div_amount
    - Ratio = final_value / last_price
    - Expected annual return = ratio^(365/total_days) - 1
    """
    try:
        # Değerleri al
        sma63 = row['SMA63']
        last_price = row['Last Price']
        time_to_div = row['TIME TO DIV']
        div_amount = row['DIV AMOUNT']
        
        # NaN kontrolü
        if pd.isna(sma63) or pd.isna(last_price) or pd.isna(time_to_div) or pd.isna(div_amount):
            return np.nan
        
        # Sıfır kontrolü
        if last_price == 0 or time_to_div == 0:
            return np.nan
        
        # Formülü uygula
        expected_sale_price = sma63 - (div_amount / 2)
        total_days = time_to_div + 3
        final_value = expected_sale_price + div_amount
        ratio = final_value / last_price
        
        # Yıllık getiri hesapla
        exp_ann_return = ratio ** (365 / total_days) - 1
        
        # Yüzdeye çevir
        exp_ann_return_percent = exp_ann_return * 100
        
        return exp_ann_return_percent
        
    except Exception as e:
        print(f"Expected Return hesaplama hatası ({row.get('PREF IBKR', 'Bilinmeyen')}): {e}")
        return np.nan

def normalize_group_scores(df):
    """Grup bazlı skorları normalize et (5-95 aralığında)"""
    try:
        print("\n=== Grup Bazlı Normalizasyon ===")
        
        # source_file kolonunu kontrol et
        if 'source_file' not in df.columns:
            print("! source_file kolonu bulunamadı, grup bazlı normalizasyon yapılamıyor")
            return df
        
        # Her grup için ayrı ayrı normalize et
        unique_groups = df['source_file'].unique()
        print(f"Toplam {len(unique_groups)} grup bulundu:")
        for group in unique_groups:
            print(f"  - {group}")
        
        for group_file in unique_groups:
            group_mask = df['source_file'] == group_file
            group_df = df[group_mask].copy()
            
            if len(group_df) == 0:
                continue
                
            print(f"\n--- {group_file} grubu normalize ediliyor ({len(group_df)} hisse) ---")
            
            # EXP_ANN_RETURN_NORM hesapla
            if 'EXP_ANN_RETURN' in group_df.columns:
                exp_values = group_df['EXP_ANN_RETURN'].dropna()
                if len(exp_values) > 0:
                    exp_min, exp_max = exp_values.min(), exp_values.max()
                    if exp_max != exp_min:
                        group_df['EXP_ANN_RETURN_NORM'] = 5 + ((group_df['EXP_ANN_RETURN'] - exp_min) / (exp_max - exp_min)) * 90
                    else:
                        group_df['EXP_ANN_RETURN_NORM'] = 50
                    print(f"  EXP_ANN_RETURN: {exp_min:.2f}-{exp_max:.2f} -> 5-95 aralığında")
                else:
                    group_df['EXP_ANN_RETURN_NORM'] = 50
                    print(f"  EXP_ANN_RETURN: Veri yok, varsayılan 50")
            
            # YTC_NORM hesapla (callable hisseler için)
            if 'YTC' in group_df.columns:
                ytc_values = group_df['YTC'].dropna()
                if len(ytc_values) > 0:
                    ytc_min, ytc_max = ytc_values.min(), ytc_values.max()
                    if ytc_max != ytc_min:
                        group_df['YTC_NORM'] = 5 + ((group_df['YTC'] - ytc_min) / (ytc_max - ytc_min)) * 90
                    else:
                        group_df['YTC_NORM'] = 50
                    print(f"  YTC: {ytc_min:.2f}-{ytc_max:.2f} -> 5-95 aralığında")
                else:
                    group_df['YTC_NORM'] = 50
                    print(f"  YTC: Veri yok, varsayılan 50")
            
            # YTM_NORM hesapla (maturity hisseler için)
            if 'YTM' in group_df.columns:
                ytm_values = group_df['YTM'].dropna()
                if len(ytm_values) > 0:
                    ytm_min, ytm_max = ytm_values.min(), ytm_values.max()
                    if ytm_max != ytm_min:
                        group_df['YTM_NORM'] = 5 + ((group_df['YTM'] - ytm_min) / (ytm_max - ytm_min)) * 90
                    else:
                        group_df['YTM_NORM'] = 50
                    print(f"  YTM: {ytm_min:.2f}-{ytm_max:.2f} -> 5-95 aralığında")
                else:
                    group_df['YTM_NORM'] = 50
                    print(f"  YTM: Veri yok, varsayılan 50")
            

            
            # Normalize edilmiş değerleri ana dataframe'e geri yükle
            for col in ['EXP_ANN_RETURN_NORM', 'YTC_NORM', 'YTM_NORM']:
                if col in group_df.columns:
                    df.loc[group_mask, col] = group_df[col]
        
        print(f"\n✓ Tüm gruplar için normalizasyon tamamlandı")
        
        # Normalize edilmiş kolonların özetini göster
        norm_cols = ['EXP_ANN_RETURN_NORM', 'YTC_NORM', 'YTM_NORM']
        for col in norm_cols:
            if col in df.columns:
                non_null_count = df[col].notna().sum()
                print(f"  {col}: {non_null_count}/{len(df)} hisse için mevcut")
        
        return df
        
    except Exception as e:
        print(f"Grup normalizasyon hatası: {e}")
        return df

def calculate_final_thg(df, market_weights=None):
    """Calculate FINAL THG score based on Excel formula"""
    try:
        # Expected Annual Return hesapla
        print("Expected Annual Return hesaplanıyor...")
        df['EXP_ANN_RETURN'] = df.apply(calculate_expected_annual_return, axis=1)
        
        # YTM hesapla (maturity hisseleri için)
        print("Yield to Maturity (YTM) hesaplanıyor...")
        df['YTM'] = df.apply(calculate_ytm, axis=1)
        
        # YTC hesapla (callable hisseleri için)
        print("Yield to Call (YTC) hesaplanıyor...")
        df['YTC'] = df.apply(calculate_ytc, axis=1)
        
        # Grup skorlarını normalize et
        df = normalize_group_scores(df)
        
        # Gerekli kolonları kontrol et
        required_cols = [
            'SMA20_chg_norm',           # SMA20 değişimi
            'SMA63_chg_norm',           # SMA63 değişimi  
            'SMA246_chg_norm',          # SMA246 değişimi
            '6M_High_diff_norm',        # Normalized 6M H
            '6M_Low_diff_norm',         # Normalized 6M L
            '3M_High_diff_norm',        # Normalized 3M H
            '3M_Low_diff_norm',         # Normalized 3M L
            '1Y_High_diff_norm',        # Normalized 52HOP (52 Week High)
            '1Y_Low_diff_norm',         # Normalized 52LOP (52 Week Low)
            'Aug4_chg_norm',            # Normalized ORH
            'Oct19_chg_norm',           # Normalized OSL
            'SOLIDITY_SCORE_NORM',      # Solidity Test (Normalized)
            'EXP_ANN_RETURN',           # Expected Annual Return
            'AVG_ADV'                   # Average Daily Volume
        ]
        
        # Piyasa koşullarına göre ağırlıkları belirle (varsayılan değerleri kullan veya piyasa koşullarına göre)
        if market_weights is None:
            solidity_weight = 2.4    # Varsayılan Solidity ağırlığı (0.8-4 arası ortası)
            yield_weight = 1200      # Yield ağırlığı (400-2000 arası ortası)
            adv_weight = 0.00025     # Varsayılan AVG_ADV ağırlığı
            print("\nVarsayılan ağırlıklar kullanılıyor: Solidity=2.4, Yield=1200, ADV=0.00025")
        else:
            solidity_weight = market_weights['solidity_weight']
            yield_weight = market_weights.get('yield_weight', 1200)
            adv_weight = market_weights.get('adv_weight', 0.00025)  # Varsayılan değer sağla
            print(f"\nPiyasa koşullarına göre ağırlıklar: Solidity={solidity_weight:.2f}, Yield={yield_weight:.2f}, ADV={adv_weight:.6f}")
        
        # AVG_ADV için opsiyonel kontrol - yoksa formülden çıkar
        use_adv = 'AVG_ADV' in df.columns
        if not use_adv:
            print("AVG_ADV kolonu bulunamadı. Volume bilgisi olmadan hesaplamaya devam ediliyor.")
            required_cols.remove('AVG_ADV')
        
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"Eksik kolonlar: {missing_cols}")
            return df
        
        # Eksik değerleri raporla
        for col in required_cols:
            missing_count = df[col].isna().sum()
            if missing_count > 0:
                print(f"{col} için {missing_count} eksik değer var")
        
        # Eksik değerleri en kötü %12'lik değerlerle doldur (güncellendi: %20'den %12'ye)
        for col in required_cols:
            if df[col].isna().any():
                # %12'lik dilime denk gelen değeri hesapla
                quantile_value = df[col].dropna().quantile(0.12).round(2)
                print(f"{col} eksik değerleri en alt %12'lik dilim değeri {quantile_value} ile dolduruluyor")
                df[col] = df[col].fillna(quantile_value)
            
        # Grup tipini belirle (callable vs maturity)
        is_callable_group = 'YTC' in df.columns and 'YTC_NORM' in df.columns
        is_maturity_group = 'YTM' in df.columns and 'YTM_NORM' in df.columns
        
        print(f"Grup tipi: Callable={is_callable_group}, Maturity={is_maturity_group}")
        
        # Grup bazlı FINAL THG hesaplama
        # source_file kolonunu kontrol et
        if 'source_file' in df.columns:
            # HELDBESMATURLU, NOTBESMATURLU ve HIGHMATUR grupları için özel formül
            heldbesmaturlu_mask = df['source_file'].str.contains('heldbesmaturlu', na=False)
            notbesmaturlu_mask = df['source_file'].str.contains('notbesmaturlu', na=False)
            highmatur_mask = df['source_file'].str.contains('highmatur', na=False)
            
            # HELDNFF ve HELDDEZNFF grupları için özel formül
            heldnff_mask = df['source_file'].str.contains('heldnff', na=False)
            helddeznff_mask = df['source_file'].str.contains('helddeznff', na=False)
            

            
            # HELDFF, HELDFLR, HELDTITREKHC, NOTTITREKHC grupları için basit formül
            heldff_mask = df['source_file'].str.contains('heldff', na=False)
            heldflr_mask = df['source_file'].str.contains('heldflr', na=False)
            heldtitrekhc_mask = df['source_file'].str.contains('heldtitrekhc', na=False)
            nottitrekhc_mask = df['source_file'].str.contains('nottitrekhc', na=False)
            
            # HELDBESMATURLU, NOTBESMATURLU ve HIGHMATUR için özel formül
            if heldbesmaturlu_mask.any() or notbesmaturlu_mask.any() or highmatur_mask.any():
                print("HELDBESMATURLU/NOTBESMATURLU/HIGHMATUR grubu için özel formül kullanılıyor...")
                print("Formül: (EXP_ANN_RETURN_NORM × 7) + (SOLIDITY_SCORE_NORM × 1) + (YTM_NORM × 5)")
                
                # Bu gruplar için normalize edilmiş değerleri kullan
                maturity_groups = ['advekheldbesmaturlu.csv', 'adveknotbesmaturlu.csv', 'advekhighmatur.csv']
                for group_file in maturity_groups:
                    group_mask = df['source_file'] == group_file
                    if group_mask.any():
                        group_df = df[group_mask].copy()
                        print(f"\n{group_file} grubu için FINAL_THG hesaplanıyor...")
                        
                        # Normalize edilmiş değerlerle formül hesapla
                        group_df['FINAL_THG'] = (
                            group_df['EXP_ANN_RETURN_NORM'].fillna(50) * 7 +
                            group_df['SOLIDITY_SCORE_NORM'].fillna(50) * 1 +
                            group_df['YTM_NORM'].fillna(50) * 5
                        )
                        
                        # Ana dataframe'e geri yükle
                        df.loc[group_mask, 'FINAL_THG'] = group_df['FINAL_THG']
            
            # HELDNFF için özel formül
            if heldnff_mask.any():
                print("HELDNFF grubu için özel formül kullanılıyor...")
                print("Formül: (EXP_ANN_RETURN_NORM × 3) + (SOLIDITY_SCORE_NORM × 2) + (YTC_NORM × 8)")
                
                # HELDNFF için normalize edilmiş değerleri kullan
                group_mask = df['source_file'] == 'advekheldnff.csv'
                if group_mask.any():
                    group_df = df[group_mask].copy()
                    print(f"\nadvekheldnff.csv grubu için FINAL_THG hesaplanıyor...")
                    
                    # Normalize edilmiş değerlerle formül hesapla
                    group_df['FINAL_THG'] = (
                        group_df['EXP_ANN_RETURN_NORM'].fillna(50) * 3 +
                        group_df['SOLIDITY_SCORE_NORM'].fillna(50) * 2 +
                        group_df['YTC_NORM'].fillna(50) * 8
                    )
                    
                    # Ana dataframe'e geri yükle
                    df.loc[group_mask, 'FINAL_THG'] = group_df['FINAL_THG']
            
            # HELDDEZNFF için özel formül
            if helddeznff_mask.any():
                print("HELDDEZNFF grubu için özel formül kullanılıyor...")
                print("Formül: (SOLIDITY_SCORE_NORM × 2) + (YTC_NORM × 4) + (EXP_ANN_RETURN_NORM × 7)")
                
                # HELDDEZNFF için normalize edilmiş değerleri kullan
                group_mask = df['source_file'] == 'advekhelddeznff.csv'
                if group_mask.any():
                    group_df = df[group_mask].copy()
                    print(f"\nadvekhelddeznff.csv grubu için FINAL_THG hesaplanıyor...")
                    
                    # Normalize edilmiş değerlerle formül hesapla
                    group_df['FINAL_THG'] = (
                        group_df['SOLIDITY_SCORE_NORM'].fillna(50) * 2 +
                        group_df['YTC_NORM'].fillna(50) * 4 +
                        group_df['EXP_ANN_RETURN_NORM'].fillna(50) * 7
                    )
                    
                    # Ana dataframe'e geri yükle
                    df.loc[group_mask, 'FINAL_THG'] = group_df['FINAL_THG']
                
                # HELDTITREKHC ve NOTTITREKHC için özel formül
                if heldtitrekhc_mask.any() or nottitrekhc_mask.any():
                    print("HELDTITREKHC/NOTTITREKHC grubu için özel formül kullanılıyor...")
                    print("Formül: (Solidity score norm × 1) + (Exp ann return norm × 12)")
                    
                    # Bu gruplar için ayrı ayrı normalize et
                    titrekhc_groups = ['advekheldtitrekhc.csv', 'adveknottitrekhc.csv']
                    for group_file in titrekhc_groups:
                        group_mask = df['source_file'] == group_file
                        if group_mask.any():
                            group_df = df[group_mask].copy()
                            print(f"\n{group_file} grubu için normalize ediliyor...")
                            
                            # Her grup için kendi içinde normalize et
                            if 'EXP_ANN_RETURN' in group_df.columns:
                                exp_values = group_df['EXP_ANN_RETURN'].dropna()
                                if len(exp_values) > 0:
                                    exp_min, exp_max = exp_values.min(), exp_values.max()
                                    if exp_max != exp_min:
                                        group_df['EXP_ANN_RETURN_NORM'] = 5 + ((group_df['EXP_ANN_RETURN'] - exp_min) / (exp_max - exp_min)) * 90
                                    else:
                                        group_df['EXP_ANN_RETURN_NORM'] = 50
                                    print(f"  Exp Ann Return: {exp_min:.2f}-{exp_max:.2f} -> 5-95")
                            
                            # Normalize edilmiş değerlerle formül hesapla
                            group_df['FINAL_THG'] = (
                                group_df['SOLIDITY_SCORE_NORM'].fillna(50) * 1 +
                                group_df['EXP_ANN_RETURN_NORM'].fillna(50) * 12
                            )
                            
                            # Ana dataframe'e geri yükle
                            df.loc[group_mask, 'EXP_ANN_RETURN_NORM'] = group_df['EXP_ANN_RETURN_NORM']
                            df.loc[group_mask, 'FINAL_THG'] = group_df['FINAL_THG']
                
                # HELDFF için özel formül
                if heldff_mask.any():
                    print("HELDFF grubu için özel formül kullanılıyor...")
                    print("Formül: (Solidity score norm × 1) + (Exp ann return norm × 12)")
                    
                    # HELDFF için normalize et
                    group_mask = df['source_file'] == 'advekheldff.csv'
                    if group_mask.any():
                        group_df = df[group_mask].copy()
                        print(f"\nadvekheldff.csv grubu için normalize ediliyor...")
                        
                        # Her grup için kendi içinde normalize et
                        if 'EXP_ANN_RETURN' in group_df.columns:
                            exp_values = group_df['EXP_ANN_RETURN'].dropna()
                            if len(exp_values) > 0:
                                exp_min, exp_max = exp_values.min(), exp_values.max()
                                if exp_max != exp_min:
                                    group_df['EXP_ANN_RETURN_NORM'] = 5 + ((group_df['EXP_ANN_RETURN'] - exp_min) / (exp_max - exp_min)) * 90
                                else:
                                    group_df['EXP_ANN_RETURN_NORM'] = 50
                                print(f"  Exp Ann Return: {exp_min:.2f}-{exp_max:.2f} -> 5-95")
                        
                        # Normalize edilmiş değerlerle formül hesapla
                        group_df['FINAL_THG'] = (
                            group_df['SOLIDITY_SCORE_NORM'].fillna(50) * 1 +
                            group_df['EXP_ANN_RETURN_NORM'].fillna(50) * 12
                        )
                        
                        # Ana dataframe'e geri yükle
                        df.loc[group_mask, 'EXP_ANN_RETURN_NORM'] = group_df['EXP_ANN_RETURN_NORM']
                        df.loc[group_mask, 'FINAL_THG'] = group_df['FINAL_THG']
                
                # HELDFLR için özel formül
                if heldflr_mask.any():
                    print("HELDFLR grubu için özel formül kullanılıyor...")
                    print("Formül: (Solidity score norm × 1) + (Exp ann return norm × 12)")
                    
                    # HELDFLR için normalize et
                    group_mask = df['source_file'] == 'advekheldflr.csv'
                    if group_mask.any():
                        group_df = df[group_mask].copy()
                        print(f"\nadvekheldflr.csv grubu için normalize ediliyor...")
                        
                        # Her grup için kendi içinde normalize et
                        if 'EXP_ANN_RETURN' in group_df.columns:
                            exp_values = group_df['EXP_ANN_RETURN'].dropna()
                            if len(exp_values) > 0:
                                exp_min, exp_max = exp_values.min(), exp_values.max()
                                if exp_max != exp_min:
                                    group_df['EXP_ANN_RETURN_NORM'] = 5 + ((group_df['EXP_ANN_RETURN'] - exp_min) / (exp_max - exp_min)) * 90
                                else:
                                    group_df['EXP_ANN_RETURN_NORM'] = 50
                                print(f"  Exp Ann Return: {exp_min:.2f}-{exp_max:.2f} -> 5-95")
                        
                        # Normalize edilmiş değerlerle formül hesapla
                        group_df['FINAL_THG'] = (
                            group_df['SOLIDITY_SCORE_NORM'].fillna(50) * 1 +
                            group_df['EXP_ANN_RETURN_NORM'].fillna(50) * 12
                        )
                        
                        # Ana dataframe'e geri yükle
                        df.loc[group_mask, 'EXP_ANN_RETURN_NORM'] = group_df['EXP_ANN_RETURN_NORM']
                        df.loc[group_mask, 'FINAL_THG'] = group_df['FINAL_THG']
                
                # Diğer gruplar için standart formül
                other_groups_mask = ~(heldbesmaturlu_mask | notbesmaturlu_mask | highmatur_mask | heldnff_mask | helddeznff_mask | heldff_mask | heldflr_mask | heldtitrekhc_mask | nottitrekhc_mask)
                if other_groups_mask.any():
                    print("Diğer gruplar için standart formül kullanılıyor...")
                    
                    # Diğer gruplar için CUR_YIELD normalize et
                    other_groups = df[other_groups_mask]['source_file'].unique()
                    for group_file in other_groups:
                        group_mask = df['source_file'] == group_file
                        if group_mask.any():
                            group_df = df[group_mask].copy()
                            print(f"\n{group_file} grubu için CUR_YIELD normalize ediliyor...")
                            # Artık normalize işlemi yapılmıyor, bu blok kaldırıldı
                    
                    # ADV değeri varsa formüle ekle, yoksa eski formülü kullan
                    if use_adv:
                        # SMA ağırlıklarını dinamik belirle
                        sma20 = df.loc[other_groups_mask, 'SMA20_chg_norm']
                        sma63 = df.loc[other_groups_mask, 'SMA63_chg_norm']
                        sma246 = df.loc[other_groups_mask, 'SMA246_chg_norm']
                        # Eğer SMA63 ve SMA246 NaN ise, ağırlık 1.0 ile sadece SMA20'yi kullan
                        only_sma20 = sma63.isna() & sma246.isna()
                        sma_part = (
                            sma20 * only_sma20.astype(float) +
                            (sma20 * 0.3 + sma63 * 0.3 + sma246 * 0.4) * (~only_sma20).astype(float)
                        )
                        df.loc[other_groups_mask, 'FINAL_THG'] = (
                            # SMA değişimleri
                            sma_part * 3 +
                            # Normalize değerler grubu (0.7 ağırlık)
                            (df.loc[other_groups_mask, '6M_High_diff_norm'] + 
                             df.loc[other_groups_mask, '6M_Low_diff_norm'] + 
                             df.loc[other_groups_mask, '3M_High_diff_norm'] + 
                             df.loc[other_groups_mask, '3M_Low_diff_norm'] + 
                             df.loc[other_groups_mask, '1Y_High_diff_norm'] + 
                             df.loc[other_groups_mask, '1Y_Low_diff_norm']) * 0.7 +
                            # Aug4 ve Oct19 değerleri * 0.25
                            (df.loc[other_groups_mask, 'Aug4_chg_norm'] * 0.7 + 
                             df.loc[other_groups_mask, 'Oct19_chg_norm'] * 1.3) * 0.25 +
                            # Solidity Score * piyasa koşullarına göre ağırlık
                            df.loc[other_groups_mask, 'SOLIDITY_SCORE_NORM'] * solidity_weight +
                            # CUR_YIELD * piyasa koşullarına göre ağırlık
                            df.loc[other_groups_mask, 'CUR_YIELD'] * yield_weight
                        )
                    else:
                        sma20 = df.loc[other_groups_mask, 'SMA20_chg_norm']
                        sma63 = df.loc[other_groups_mask, 'SMA63_chg_norm']
                        sma246 = df.loc[other_groups_mask, 'SMA246_chg_norm']
                        only_sma20 = sma63.isna() & sma246.isna()
                        sma_part = (
                            sma20 * only_sma20.astype(float) +
                            (sma20 * 0.3 + sma63 * 0.3 + sma246 * 0.4) * (~only_sma20).astype(float)
                        )
                        df.loc[other_groups_mask, 'FINAL_THG'] = (
                            sma_part * 3 +
                            (df.loc[other_groups_mask, '6M_High_diff_norm'] + 
                             df.loc[other_groups_mask, '6M_Low_diff_norm'] + 
                             df.loc[other_groups_mask, '3M_High_diff_norm'] + 
                             df.loc[other_groups_mask, '3M_Low_diff_norm'] + 
                             df.loc[other_groups_mask, '1Y_High_diff_norm'] + 
                             df.loc[other_groups_mask, '1Y_Low_diff_norm']) * 0.7 +
                            (df.loc[other_groups_mask, 'Aug4_chg_norm'] * 0.7 + 
                             df.loc[other_groups_mask, 'Oct19_chg_norm'] * 1.3) * 0.25 +
                            df.loc[other_groups_mask, 'SOLIDITY_SCORE_NORM'] * solidity_weight +
                            # CUR_YIELD * piyasa koşullarına göre ağırlık
                            df.loc[other_groups_mask, 'CUR_YIELD'] * yield_weight
                        )
            else:
                # Tüm gruplar için standart formül (source_file yoksa)
                print("Standart formül kullanılıyor...")
                
                # ADV değeri varsa formüle ekle, yoksa eski formülü kullan
                if use_adv:
                    df['FINAL_THG'] = (
                        # SMA değişimleri (0.3 + 0.3 + 0.4 ağırlık) - 3 ile çarpılıyor
                        (df['SMA20_chg_norm'] * 0.3 + 
                         df['SMA63_chg_norm'] * 0.3 + 
                         df['SMA246_chg_norm'] * 0.4) * 3 +
                        
                        # Normalize değerler grubu (0.7 ağırlık)
                        (df['6M_High_diff_norm'] + 
                         df['6M_Low_diff_norm'] + 
                         df['3M_High_diff_norm'] + 
                         df['3M_Low_diff_norm'] + 
                         df['1Y_High_diff_norm'] + 
                         df['1Y_Low_diff_norm']) * 0.7 +
                        
                        # Aug4 ve Oct19 değerleri * 0.25
                        (df['Aug4_chg_norm'] * 0.7 + 
                         df['Oct19_chg_norm'] * 1.3) * 0.25 +
                        
                        # Solidity Score * piyasa koşullarına göre ağırlık
                        df['SOLIDITY_SCORE_NORM'] * solidity_weight +
                        
                        # CUR_YIELD * yield_weight (piyasa koşullarına göre)
                        df['CUR_YIELD'] * yield_weight
                    )
                else:
                    df['FINAL_THG'] = (
                        # SMA değişimleri (0.3 + 0.3 + 0.4 ağırlık) - 3 ile çarpılıyor
                        (df['SMA20_chg_norm'] * 0.3 + 
                         df['SMA63_chg_norm'] * 0.3 + 
                         df['SMA246_chg_norm'] * 0.4) * 3 +
                        
                        # Normalize değerler grubu (0.7 ağırlık)
                        (df['6M_High_diff_norm'] + 
                         df['6M_Low_diff_norm'] + 
                         df['3M_High_diff_norm'] + 
                         df['3M_Low_diff_norm'] + 
                         df['1Y_High_diff_norm'] + 
                         df['1Y_Low_diff_norm']) * 0.7 +
                        
                        # Aug4 ve Oct19 değerleri * 0.25
                        (df['Aug4_chg_norm'] * 0.7 + 
                         df['Oct19_chg_norm'] * 1.3) * 0.25 +
                        
                        # Solidity Score * piyasa koşullarına göre ağırlık
                        df['SOLIDITY_SCORE_NORM'] * solidity_weight +
                        
                        # CUR_YIELD * yield_weight (piyasa koşullarına göre)
                        df['CUR_YIELD'] * yield_weight
                    )
        else:
            # source_file kolonu yoksa standart formül kullan
            print("source_file kolonu bulunamadı, standart formül kullanılıyor...")
            
            # ADV değeri varsa formüle ekle, yoksa eski formülü kullan
            if use_adv:
                df['FINAL_THG'] = (
                    # SMA değişimleri (0.3 + 0.3 + 0.4 ağırlık) - 3 ile çarpılıyor
                    (df['SMA20_chg_norm'] * 0.3 + 
                     df['SMA63_chg_norm'] * 0.3 + 
                     df['SMA246_chg_norm'] * 0.4) * 3 +
                    
                    # Normalize değerler grubu (0.7 ağırlık)
                    (df['6M_High_diff_norm'] + 
                     df['6M_Low_diff_norm'] + 
                     df['3M_High_diff_norm'] + 
                     df['3M_Low_diff_norm'] + 
                     df['1Y_High_diff_norm'] + 
                     df['1Y_Low_diff_norm']) * 0.7 +
                    
                    # Aug4 ve Oct19 değerleri * 0.25
                    (df['Aug4_chg_norm'] * 0.7 + 
                     df['Oct19_chg_norm'] * 1.3) * 0.25 +
                    
                    # Solidity Score * piyasa koşullarına göre ağırlık
                    df['SOLIDITY_SCORE_NORM'] * solidity_weight +
                    
                    # CUR_YIELD * yield_weight (piyasa koşullarına göre)
                    df['CUR_YIELD'] * yield_weight
                )
            else:
                df['FINAL_THG'] = (
                    # SMA değişimleri (0.3 + 0.3 + 0.4 ağırlık) - 3 ile çarpılıyor
                    (df['SMA20_chg_norm'] * 0.3 + 
                     df['SMA63_chg_norm'] * 0.3 + 
                     df['SMA246_chg_norm'] * 0.4) * 3 +
                    
                    # Normalize değerler grubu (0.7 ağırlık)
                    (df['6M_High_diff_norm'] + 
                     df['6M_Low_diff_norm'] + 
                     df['3M_High_diff_norm'] + 
                     df['3M_Low_diff_norm'] + 
                     df['1Y_High_diff_norm'] + 
                     df['1Y_Low_diff_norm']) * 0.7 +
                    
                    # Aug4 ve Oct19 değerleri * 0.25
                    (df['Aug4_chg_norm'] * 0.7 + 
                     df['Oct19_chg_norm'] * 1.3) * 0.25 +
                    
                    # Solidity Score * piyasa koşullarına göre ağırlık
                    df['SOLIDITY_SCORE_NORM'] * solidity_weight +
                    
                    # CUR_YIELD * yield_weight (piyasa koşullarına göre)
                    df['CUR_YIELD'] * yield_weight
                )
        
        # FINAL_THG değerini 2 ondalık basamağa yuvarla
        df['FINAL_THG'] = df['FINAL_THG'].round(2)
        
        # CUR_YIELD'i 4 ondalık basamağa yuvarla (tekrar kontrol)
        df['CUR_YIELD'] = df['CUR_YIELD'].round(4)
        
        # Debug bilgisi
        print("\n=== FINAL THG Bileşen Katkıları ===")
        component_cols = [
            'PREF IBKR',
            'SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm',
            '6M_High_diff_norm', '6M_Low_diff_norm',
            '3M_High_diff_norm', '3M_Low_diff_norm',
            '1Y_High_diff_norm', '1Y_Low_diff_norm',
            'Aug4_chg_norm', 'Oct19_chg_norm',
            'SOLIDITY_SCORE_NORM', 'EXP_ANN_RETURN_NORM'
        ]
        
        # Grup tipine göre ek kolonlar ekle
        if is_callable_group:
            component_cols.append('YTC_NORM')
        if is_maturity_group:
            component_cols.append('YTM_NORM')
        
        component_cols.append('FINAL_THG')
        print(df[component_cols].head().round(2))
        
        # Kullanılan ağırlıkları kaydet
        df['SOLIDITY_WEIGHT_USED'] = solidity_weight
        df['YIELD_WEIGHT_USED'] = yield_weight  # Standart formülde yield_weight kullanılır
        
        return df
        
    except Exception as e:
        print(f"FINAL THG hesaplama hatası: {e}")
        return df

def process_csv_group(adv_files, sldf_files, sek_files, market_weights, target_file=None):
    """Her CSV grubunu işle"""
    try:
        # Verileri yükle
        normalized_df, solidity_df, ibkr_df = load_required_data(target_file)
        
        if normalized_df is None or solidity_df is None or ibkr_df is None:
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
        merged_df = prepare_data_for_calculation(normalized_df, solidity_df, ibkr_df, market_weights)
        
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
        
        # FINAL_THG değerlerini hesapla
        result_df = calculate_final_thg(merged_df, market_weights)
        
        # Last Price değeri eksik olan hisseleri filtrele (PRS ve PRH hariç)
        last_price_missing = result_df['Last Price'].isna() | (result_df['Last Price'] == 0)
        contains_prs_prh = result_df['PREF IBKR'].str.contains('PRS|PRH', na=False)
        
        # Last Price eksik olan hisseleri listele
        missing_price_stocks = result_df[last_price_missing]
        print("\nLast Price değeri eksik olan hisseler:")
        print("PREF IBKR\tLast Price\tCMON")
        print("-" * 50)
        for _, row in missing_price_stocks.iterrows():
            print(f"{row['PREF IBKR']}\t{row['Last Price']}\t{row.get('CMON', 'N/A')}")
        
        # Last Price eksik veya sıfır OLAN VE aynı zamanda PRS veya PRH içermeyen hisseleri çıkar
        rows_to_remove = last_price_missing & ~contains_prs_prh
        filtered_df = result_df[~rows_to_remove].copy()
        
        # Çıkarılan hisseler hakkında bilgi ver
        removed_count = rows_to_remove.sum()
        print(f"\nLast Price değeri eksik/sıfır olan hisse sayısı: {last_price_missing.sum()}")
        print(f"Bunların içinden PRS veya PRH içeren ve korunan hisse sayısı: {(last_price_missing & contains_prs_prh).sum()}")
        print(f"Çıkarılan hisse sayısı: {removed_count}")
        print(f"Son hisse sayısı: {len(filtered_df)} (Orijinal: {len(result_df)})")
        
        # Korunan PRS/PRH hisselerini listele
        kept_prs_prh = filtered_df[filtered_df['PREF IBKR'].str.contains('PRS|PRH', na=False) & 
                                  (filtered_df['Last Price'].isna() | (filtered_df['Last Price'] == 0))]
        if len(kept_prs_prh) > 0:
            print("\nLast Price eksik olmasına rağmen korunan PRS/PRH hisseleri:")
            for _, row in kept_prs_prh.iterrows():
                print(f"  {row['PREF IBKR']} ({row['CMON']})")
        
        # Eğer target_file belirtilmişse, sadece o dosyayı oluştur
        if target_file:
            try:
                # source_file kolonunu kaldır
                filtered_df = filtered_df.drop(columns=['source_file'])
                
                # CSV dosyasını oluştur
                filtered_df.to_csv(target_file, 
                          index=False,
                          float_format='%.2f',  # Tüm float değerler için 2 ondalık basamak
                          sep=',',              # Virgül ayracını belirt
                          encoding='utf-8-sig', # Excel için BOM ekle
                          lineterminator='\n',  # Windows satır sonu
                          quoting=1)            # Excel için tüm değerleri tırnak içine al
            
                print(f"\nSonuçlar '{target_file}' dosyasına kaydedildi: {len(filtered_df)} satır")
                
                # Top 10 skorları göster
                print(f"\n=== {target_file} - Top 10 FINAL THG Skorları ===")
                top_10 = filtered_df.nlargest(10, 'FINAL_THG')[['PREF IBKR', 'SOLIDITY_SCORE_NORM', 'EXP_ANN_RETURN', 'FINAL_THG']]
                print(top_10.round(2).to_string(index=False))
                
            except Exception as e:
                print(f"! {target_file} oluşturulurken hata: {e}")
        else:
        # Her ADV dosyası için ayrı çıktı oluştur
        for adv_file in adv_files:
            try:
                # Dosya adından grup adını çıkar
                group_name = adv_file.replace('advek', '').replace('.csv', '')
                output_filename = f"finek{group_name}.csv"
                
                # Bu gruba ait verileri filtrele
                group_data = filtered_df[filtered_df['source_file'] == adv_file]
                
                if len(group_data) > 0:
                    # source_file kolonunu kaldır
                    group_data = group_data.drop(columns=['source_file'])
                    
                    # CSV dosyasını oluştur
                    group_data.to_csv(output_filename, 
                              index=False,
                              float_format='%.2f',  # Tüm float değerler için 2 ondalık basamak
                              sep=',',              # Virgül ayracını belirt
                              encoding='utf-8-sig', # Excel için BOM ekle
                              lineterminator='\n',  # Windows satır sonu
                              quoting=1)            # Excel için tüm değerleri tırnak içine al
                
                    print(f"\nSonuçlar '{output_filename}' dosyasına kaydedildi: {len(group_data)} satır")
                    
                    # Top 10 skorları göster
                    print(f"\n=== {output_filename} - Top 10 FINAL THG Skorları ===")
                    top_10 = group_data.nlargest(10, 'FINAL_THG')[['PREF IBKR', 'SOLIDITY_SCORE_NORM', 'EXP_ANN_RETURN', 'FINAL_THG']]
                    print(top_10.round(2).to_string(index=False))
                    
                else:
                    print(f"! {adv_file} için veri bulunamadı, {output_filename} oluşturulamadı.")
                    
            except Exception as e:
                print(f"! {adv_file} işlenirken hata: {e}")
        
        return filtered_df
        
    except Exception as e:
        print(f"CSV grubu işlenirken hata: {e}")
        return None

def main():
    try:
        # Piyasa koşullarını analiz et
        market_weights = get_market_weights()
        
        # CSV dosyalarını bul
        adv_files, sek_files = get_csv_files()
        sldf_files = ['allcomek_sld.csv']  # SLD dosyası sabit
        
        if not adv_files:
            print("HATA: Hiç ADV dosyası bulunamadı!")
            return
        
        if not sldf_files:
            print("HATA: Hiç SLDF dosyası bulunamadı!")
            return
        
        if not sek_files:
            print("HATA: Hiç SEK dosyası bulunamadı!")
            return
        
        # Her ADV dosyası için ayrı ayrı işle
        all_results = []
        for adv_file in adv_files:
            print(f"\n=== {adv_file} işleniyor ===")
            # ADV dosyasından FINE dosyası adını oluştur
            fine_file = adv_file.replace('advek', 'finek')
            result_df = process_csv_group([adv_file], sldf_files, sek_files, market_weights, fine_file)
            if result_df is not None:
                all_results.append(result_df)
        
        # Tüm sonuçları birleştir
        if all_results:
            result_df = pd.concat(all_results, ignore_index=True)
        else:
            result_df = None
        
        if result_df is not None:
            # Genel istatistikler
            print("\n=== GENEL İSTATİSTİKLER ===")
            print(f"Toplam işlenen hisse sayısı: {len(result_df)}")
            print(f"Ortalama FINAL_THG: {result_df['FINAL_THG'].mean():.2f}")
            print(f"En yüksek FINAL_THG: {result_df['FINAL_THG'].max():.2f}")
            print(f"En düşük FINAL_THG: {result_df['FINAL_THG'].min():.2f}")
            
            # Top 20 ve Bottom 20 FINAL THG skorlarını göster
            print("\n=== En Yüksek FINAL THG Skorları (Top 20) ===")
            print("PREF IBKR  SOLIDITY  EXP_RETURN  FINAL_THG   SMA20   SMA63   SMA246   1Y_HIGH   1Y_LOW")
            print("-" * 90)
            
            top_20 = result_df.nlargest(20, 'FINAL_THG')[
                ['PREF IBKR', 'SOLIDITY_SCORE_NORM', 'EXP_ANN_RETURN', 'FINAL_THG',
                 'SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm', 
                 '1Y_High_diff_norm', '1Y_Low_diff_norm']
            ]
            
            for _, row in top_20.iterrows():
                print(f"{row['PREF IBKR']:<10} {row['SOLIDITY_SCORE_NORM']:>8.2f} {row['EXP_ANN_RETURN']:>10.2f} {row['FINAL_THG']:>10.2f} "
                      f"{row['SMA20_chg_norm']:>7.2f} {row['SMA63_chg_norm']:>7.2f} {row['SMA246_chg_norm']:>7.2f} "
                      f"{row['1Y_High_diff_norm']:>7.2f} {row['1Y_Low_diff_norm']:>7.2f}")
            
            # Bottom 20 FINAL THG skorlarını göster
            print("\n=== En Düşük FINAL THG Skorları (Bottom 20) ===")
            print("PREF IBKR  SOLIDITY  EXP_RETURN  FINAL_THG   SMA20   SMA63   SMA246   1Y_HIGH   1Y_LOW")
            print("-" * 90)
            
            bottom_20 = result_df.nsmallest(20, 'FINAL_THG')[
                ['PREF IBKR', 'SOLIDITY_SCORE_NORM', 'EXP_ANN_RETURN', 'FINAL_THG',
                 'SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm', 
                 '1Y_High_diff_norm', '1Y_Low_diff_norm']
            ]
            
            for _, row in bottom_20.iterrows():
                print(f"{row['PREF IBKR']:<10} {row['SOLIDITY_SCORE_NORM']:>8.2f} {row['EXP_ANN_RETURN']:>10.2f} {row['FINAL_THG']:>10.2f} "
                      f"{row['SMA20_chg_norm']:>7.2f} {row['SMA63_chg_norm']:>7.2f} {row['SMA246_chg_norm']:>7.2f} "
                      f"{row['1Y_High_diff_norm']:>7.2f} {row['1Y_Low_diff_norm']:>7.2f}")
                
    except Exception as e:
        print(f"Bir hata oluştu: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()