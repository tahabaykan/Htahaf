#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FINAL THG Hesaplama Scripti - Sıfırdan Yazılmış
COUPON ve DIV AMOUNT değerleri hiç değiştirilmez!
"""

import pandas as pd
import numpy as np
import glob
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

def get_market_weights():
    """Piyasa koşullarına göre ağırlıkları belirler"""
    try:
        # market_weights.csv dosyasını oku
        print("Piyasa ağırlıkları market_weights.csv'den alınıyor...")
        df = pd.read_csv('market_weights.csv')
        if len(df) > 0:
            weights = {
                'solidity_weight': df['solidity_weight'].iloc[0],
                'yield_weight': df['yield_weight'].iloc[0],
                'adv_weight': df['adv_weight'].iloc[0] if 'adv_weight' in df.columns else 0.00080,
                'adj_risk_premium_weight': df.get('adj_risk_premium_weight', 1350).iloc[0],
                'solcall_score_weight': df.get('solcall_score_weight', 4).iloc[0],
                'credit_score_norm_weight': df.get('credit_score_norm_weight', 2).iloc[0],
                'exp_return_weight': 800,  # EXP_RETURN ağırlığı (Maturlular için)
                'ytc_weight': 600,         # YTC ağırlığı (Maturlular için)
                'ytm_weight': 600,         # YTM ağırlığı (Maturlular için)
            }
            print(f"✓ Piyasa ağırlıkları yüklendi: {weights}")
            return weights
        
    except FileNotFoundError:
        print("⚠️ market_weights.csv bulunamadı, varsayılan ağırlıklar kullanılıyor")
    except Exception as e:
        print(f"⚠️ Ağırlık yükleme hatası: {e}, varsayılan ağırlıklar kullanılıyor")
    
    # Varsayılan ağırlıklar
    return {
        'solidity_weight': 2.4,    # Solidity ağırlığı (0.8-4 arası)
        'yield_weight': 24,        # Yield ağırlığı (8-40 arası)
        'exp_return_weight': 800,  # EXP_RETURN ağırlığı (Maturlular için)
        'ytc_weight': 600,         # YTC ağırlığı (Maturlular için)
        'ytm_weight': 600,         # YTM ağırlığı (Maturlular için)
        'adv_weight': 0.00080,     # ADV ağırlığı
        'adj_risk_premium_weight': 1100,  # Adj Risk Premium ağırlığı (500-1700 arası)
        'solcall_score_weight': 3.5,      # SOLCALL Score ağırlığı (1-7 arası)
        'credit_score_norm_weight': 2     # Credit Score Norm ağırlığı (0.5-3.5 arası)
    }

def get_csv_files(target_file=None):
    """İşlenecek CSV dosyalarını bul"""
    if target_file and target_file.startswith('finek'):
        # Sadece belirtilen dosyayı yükle
        adv_file = target_file.replace('finek', 'advek')
        if os.path.exists(adv_file):
            adv_files = [adv_file]
            print(f"Sadece {adv_file} dosyası işlenecek")
        else:
            print(f"HATA: {adv_file} bulunamadı!")
            return [], []
    else:
        # Tüm ADV dosyalarını bul
        adv_files = glob.glob('advek*.csv')
    
    # SEK dosyalarını bul
    sek_files = glob.glob('sek*.csv')
    
    return adv_files, sek_files

def load_single_adv_file(adv_file):
    """Tek bir ADV dosyasını yükle"""
    try:
        df = pd.read_csv(adv_file, encoding='utf-8-sig')
        df['source_file'] = adv_file
        print(f"✓ {adv_file} yüklendi: {len(df)} satır")
        return df
    except Exception as e:
        print(f"✗ {adv_file} yüklenirken hata: {e}")
        return None

def load_solidity_data():
    """Solidity verilerini yükle"""
    try:
        solidity_df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
        print(f"✓ allcomek_sld.csv yüklendi: {len(solidity_df)} satır")
        return solidity_df
    except Exception as e:
        print(f"✗ allcomek_sld.csv yüklenirken hata: {e}")
        return None

def load_sek_data():
    """SEK ve YEK verilerini yükle (Adj risk premium sadece YEK'den alınır)"""
    try:
        # Tüm CSV dosyalarını bul
        all_files = glob.glob('*.csv')
        sek_files = [f for f in all_files if 'sek' in f.lower()]
        yek_files = [f for f in all_files if 'yek' in f.lower()]
        
        print(f"Bulunan SEK dosyaları: {sek_files}")
        print(f"Bulunan YEK dosyaları: {yek_files[:5]}... (toplam {len(yek_files)})")
        
        all_sek_data = []
        
        # SEK dosyalarını yükle
        for file in sek_files:
            df = pd.read_csv(file, encoding='utf-8-sig')
            df['source_file'] = file
            all_sek_data.append(df)
            print(f"✓ {file} yüklendi: {len(df)} satır")
        
        # YEK dosyalarını yükle (Adj risk premium için)
        yek_data_list = []
        for file in yek_files:
            df = pd.read_csv(file, encoding='utf-8-sig')
            df['source_file'] = file
            
            # YEK dosyalarında Adj Risk Premium kolonunu kontrol et
            if 'Adj Risk Premium' in df.columns:
                print(f"✓ {file} yüklendi: {len(df)} satır (Adj Risk Premium mevcut)")
                # Sadece geçerli Adj Risk Premium değerleri olan satırları al
                valid_data = df[df['Adj Risk Premium'].notna()].copy()
                if len(valid_data) > 0:
                    yek_data_list.append(valid_data)
                    print(f"  - Geçerli Adj Risk Premium değeri: {len(valid_data)} satır")
                else:
                    print(f"  - Geçerli Adj Risk Premium değeri yok")
            else:
                print(f"⚠️ {file} yüklendi: {len(df)} satır (Adj Risk Premium yok)")
            
            all_sek_data.append(df)
        
        # YEK verilerini birleştir ve duplicate'leri kaldır
        if yek_data_list:
            combined_yek = pd.concat(yek_data_list, ignore_index=True)
            # Aynı hisse için en yüksek Adj Risk Premium değerini al
            combined_yek = combined_yek.sort_values('Adj Risk Premium', ascending=False).drop_duplicates(subset=['PREF IBKR'], keep='first')
            print(f"YEK verileri birleştirildi: {len(combined_yek)} benzersiz hisse")
            print(f"Adj Risk Premium örnek değerler: {combined_yek['Adj Risk Premium'].head().tolist()}")
        
        if all_sek_data:
            ibkr_df = pd.concat(all_sek_data, ignore_index=True)
            print(f"Toplam SEK/YEK verisi: {len(ibkr_df)} satır")
            return ibkr_df
        else:
            print("HATA: Hiç SEK/YEK dosyası bulunamadı!")
            return None
            
    except Exception as e:
        print(f"SEK/YEK veri yükleme hatası: {e}")
        return None

def prepare_data_for_calculation(adv_df, solidity_df, ibkr_df):
    """Verileri hesaplama için hazırla"""
    try:
        print(f"\nVeri hazırlama başlıyor...")
        print(f"ADV verisi: {len(adv_df)} satır")
        print(f"Solidity verisi: {len(solidity_df)} satır")
        print(f"SEK/YEK verisi: {len(ibkr_df)} satır")
        
        # COUPON ve DIV AMOUNT değerlerini KORU - hiç değiştirme!
        print("\nCOUPON ve DIV AMOUNT değerleri korunuyor...")
        print("Örnek COUPON değerleri:")
        print(adv_df[['PREF IBKR', 'COUPON', 'DIV AMOUNT']].head())
        
        # SOLIDITY_SCORE_NORM için birleştir
        df = adv_df.merge(
            solidity_df[['PREF IBKR', 'SOLIDITY_SCORE_NORM']], 
            on='PREF IBKR',
            how='left'
        )
        
        # Birleştirme sonuçlarını kontrol et
        merge_success = df['SOLIDITY_SCORE_NORM'].notna().sum()
        print(f"SOLIDITY_SCORE_NORM birleştirildi: {merge_success}/{len(df)} hisse")
        
        # GÜNCEL LAST PRICE VE DIV ADJ PRICE'LARI SEK DOSYALARINDAN AL
        print("\n=== GÜNCEL LAST PRICE VE DIV ADJ PRICE SEK DOSYALARINDAN ALINIYOR ===")
        
        # SEK dosyalarını bul ve oku
        sek_files = glob.glob('sek*.csv')
        print(f"Bulunan SEK dosyaları: {sek_files}")
        
        current_price_data = {}
        
        for sek_file in sek_files:
            try:
                sek_df = pd.read_csv(sek_file, encoding='utf-8-sig')
                print(f"✓ {sek_file} okundu: {len(sek_df)} satır")
                
                if 'Last Price' in sek_df.columns and 'Div adj.price' in sek_df.columns:
                    # Sadece geçerli Last Price ve Div adj.price değerleri olan satırları al
                    valid_data = sek_df[sek_df['Last Price'].notna()][['PREF IBKR', 'Last Price', 'Div adj.price']]
                    print(f"  - Geçerli Last Price ve Div adj.price: {len(valid_data)} satır")
                    
                    for _, row in valid_data.iterrows():
                        pref = row['PREF IBKR']
                        last_price = row['Last Price']
                        div_adj_price = row['Div adj.price']
                        
                        # Aynı hisse için en güncel değerleri al (son dosyadan)
                        current_price_data[pref] = {
                            'Last Price': last_price,
                            'Div adj.price': div_adj_price
                        }
                else:
                    print(f"  - Last Price veya Div adj.price kolonu yok")
                    
            except Exception as e:
                print(f"✗ {sek_file} okunurken hata: {e}")
        
        print(f"SEK dosyalarından toplam {len(current_price_data)} hisse için güncel fiyat verisi bulundu")
        
        # Güncel Last Price ve Div adj.price kolonlarını oluştur
        df['Last Price'] = df['PREF IBKR'].map(lambda x: current_price_data.get(x, {}).get('Last Price', df.loc[df['PREF IBKR'] == x, 'Last Price'].iloc[0] if len(df.loc[df['PREF IBKR'] == x]) > 0 else None))
        df['Div adj.price'] = df['PREF IBKR'].map(lambda x: current_price_data.get(x, {}).get('Div adj.price', df.loc[df['PREF IBKR'] == x, 'Div adj.price'].iloc[0] if len(df.loc[df['PREF IBKR'] == x]) > 0 else None))
        
        # Güncel fiyat istatistikleri
        current_price_success = df['Last Price'].notna().sum()
        current_div_adj_success = df['Div adj.price'].notna().sum()
        print(f"Güncel Last Price eklendi: {current_price_success}/{len(df)} hisse")
        print(f"Güncel Div adj.price eklendi: {current_div_adj_success}/{len(df)} hisse")
        print(f"Last Price örnek değerler: {df['Last Price'].head().tolist()}")
        print(f"Div adj.price örnek değerler: {df['Div adj.price'].head().tolist()}")
        
        # Adj Risk Premium'u YEK dosyalarından direkt çek
        print("\n=== Adj Risk Premium YEK dosyalarından çekiliyor ===")
        
        # YEK dosyalarını bul ve oku
        yek_files = glob.glob('yek*.csv')
        print(f"Bulunan YEK dosyaları: {yek_files}")
        
        adj_risk_data = {}
        
        for yek_file in yek_files:
            try:
                yek_df = pd.read_csv(yek_file, encoding='utf-8-sig')
                print(f"✓ {yek_file} okundu: {len(yek_df)} satır")
                
                if 'Adj Risk Premium' in yek_df.columns:
                    # Sadece geçerli Adj Risk Premium değerleri olan satırları al
                    valid_data = yek_df[yek_df['Adj Risk Premium'].notna()][['PREF IBKR', 'Adj Risk Premium']]
                    print(f"  - Geçerli Adj Risk Premium: {len(valid_data)} satır")
                    
                    for _, row in valid_data.iterrows():
                        pref = row['PREF IBKR']
                        adj_risk = row['Adj Risk Premium']
                        
                        # Aynı hisse için en yüksek değeri al
                        if pref not in adj_risk_data or adj_risk > adj_risk_data[pref]:
                            adj_risk_data[pref] = adj_risk
                else:
                    print(f"  - Adj Risk Premium kolonu yok")
                    
            except Exception as e:
                print(f"✗ {yek_file} okunurken hata: {e}")
        
        print(f"YEK dosyalarından toplam {len(adj_risk_data)} hisse için Adj Risk Premium bulundu")
        
        # Adj Risk Premium kolonunu oluştur
        df['Adj Risk Premium'] = df['PREF IBKR'].map(adj_risk_data)
        
        # Adj Risk Premium istatistikleri
        adj_risk_success = df['Adj Risk Premium'].notna().sum()
        print(f"Adj Risk Premium eklendi: {adj_risk_success}/{len(df)} hisse")
        print(f"Adj Risk Premium örnek değerler: {df['Adj Risk Premium'].head().tolist()}")
        
        # Numeric kolonları dönüştür
        df['DIV AMOUNT'] = pd.to_numeric(df['DIV AMOUNT'], errors='coerce')
        df['Div adj.price'] = pd.to_numeric(df['Div adj.price'], errors='coerce')
        df['Last Price'] = pd.to_numeric(df['Last Price'], errors='coerce')
        
        # Adj Risk Premium kolonunu güvenli şekilde dönüştür ve 4 ondalık hane ile yuvarla
        df['Adj Risk Premium'] = pd.to_numeric(df['Adj Risk Premium'], errors='coerce').round(4)
        
        # NEK DOSYALARINDAN SMA NORMALIZE DEĞERLERİNİ AL
        print("\n=== NEK DOSYALARINDAN SMA NORMALIZE DEĞERLERİ ALINIYOR ===")
        
        # NEK dosyalarını bul ve oku
        nek_files = glob.glob('nek*.csv')
        print(f"Bulunan NEK dosyaları: {nek_files}")
        
        sma_norm_data = {}
        
        for nek_file in nek_files:
            try:
                nek_df = pd.read_csv(nek_file, encoding='utf-8-sig')
                print(f"✓ {nek_file} okundu: {len(nek_df)} satır")
                
                # SMA normalize değerlerini kontrol et
                sma_cols = ['SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm']
                available_cols = [col for col in sma_cols if col in nek_df.columns]
                
                if available_cols:
                    print(f"  - Mevcut SMA normalize kolonları: {available_cols}")
                    
                    for _, row in nek_df.iterrows():
                        pref = row['PREF IBKR']
                        sma_data = {}
                        
                        for col in available_cols:
                            if pd.notna(row[col]):
                                sma_data[col] = row[col]
                        
                        if sma_data:  # En az bir SMA değeri varsa
                            sma_norm_data[pref] = sma_data
                else:
                    print(f"  - SMA normalize kolonları bulunamadı")
                    
            except Exception as e:
                print(f"✗ {nek_file} okunurken hata: {e}")
        
        print(f"NEK dosyalarından toplam {len(sma_norm_data)} hisse için SMA normalize verisi bulundu")
        
        # SMA normalize kolonlarını oluştur
        for col in ['SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm']:
            df[col] = df['PREF IBKR'].map(lambda x: sma_norm_data.get(x, {}).get(col, np.nan))
        
        # SMA normalize istatistikları
        sma_success = df['SMA63_chg_norm'].notna().sum()
        print(f"SMA normalize değerleri eklendi: {sma_success}/{len(df)} hisse")
        print(f"SMA63_chg_norm örnek değerler: {df['SMA63_chg_norm'].head().tolist()}")
        
        # CUR_YIELD hesapla: COUPON oranını kullan (DIV_AMOUNT'u değiştirme)
        def calc_cur_yield(row):
            price = row['Div adj.price'] if pd.notnull(row['Div adj.price']) and row['Div adj.price'] != 0 else row['Last Price']
            div_amount = row['DIV AMOUNT']
            
            if pd.notnull(div_amount) and price and price != 0:
                # Doğru formül: (DIV_AMOUNT * 4) / price * 100
                base_yield = (div_amount * 4 / price) * 100
                
                # QDI kontrolü - "No" ise %5 düşür
                qdi = row.get('QDI', '')
                if isinstance(qdi, str) and qdi.strip().upper() == 'NO':
                    base_yield = base_yield * 0.95  # %5 düşür
                    print(f"QDI=No için {row['PREF IBKR']}: {base_yield/0.95:.4f} -> {base_yield:.4f}")
                
                return base_yield
            else:
                return np.nan
        
        df['CUR_YIELD'] = df.apply(calc_cur_yield, axis=1)
        df['CUR_YIELD'] = df['CUR_YIELD'].round(4)
        
        print("\n=== CUR_YIELD Hesaplama Detayları ===")
        print("Formül: (DIV_AMOUNT * 4) / price * 100")
        print("QDI=No olan hisseler için %5 düşürülür")
        print(df[['PREF IBKR', 'COUPON', 'DIV AMOUNT', 'Div adj.price', 'Last Price', 'QDI', 'CUR_YIELD']].head().to_string())
        
        return df
        
    except Exception as e:
        print(f"Veri hazırlama hatası: {e}")
        return None

def calculate_expected_annual_return(row):
    """Beklenen yıllık getiri hesapla"""
    try:
        sma63 = row['SMA63']
        last_price = row['Last Price']
        time_to_div = row['TIME TO DIV']
        div_amount = row['DIV AMOUNT']
        
        if pd.isna(sma63) or pd.isna(last_price) or pd.isna(time_to_div) or pd.isna(div_amount):
            return np.nan
        
        if last_price == 0 or time_to_div == 0:
            return np.nan
        
        expected_sale_price = sma63 - (div_amount / 2)
        total_days = time_to_div + 3
        final_value = expected_sale_price + div_amount
        ratio = final_value / last_price
        
        exp_ann_return = ratio ** (365 / total_days) - 1
        return exp_ann_return * 100
        
    except Exception as e:
        return np.nan

def calculate_ytm(row):
    """Yield to Maturity hesapla - MATUR DATE kullanarak"""
    try:
        from datetime import datetime, date
        
        # Gerekli verileri al
        matur_date = row['MATUR DATE']
        div_adj_price = row['Div adj.price']
        last_price = row['Last Price']
        div_amount = row['DIV AMOUNT']
        coupon_rate = row['COUPON']
        
        if pd.isna(matur_date) or pd.isna(div_amount):
            return np.nan
        
        # Div adj.price kullan, yoksa Last Price'a fallback yap
        current_price = div_adj_price if pd.notna(div_adj_price) and div_adj_price != 0 else last_price
        
        if pd.isna(current_price) or current_price == 0:
            return np.nan
    
        # MATUR DATE'i parse et
        try:
            if isinstance(matur_date, str):
                # Farklı tarih formatlarını dene
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d']:
                    try:
                        matur_dt = datetime.strptime(matur_date, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    print(f"MATUR DATE parse edilemedi: {matur_date}")
                    return np.nan
            else:
                matur_dt = matur_date.date() if hasattr(matur_date, 'date') else matur_date
        except Exception as e:
            print(f"MATUR DATE parse hatası: {e}, değer: {matur_date}")
            return np.nan
        
        # Bugünün tarihi
        today = date.today()
        
        # Maturity date'e kalan gün sayısı
        days_to_maturity = (matur_dt - today).days
        
        if days_to_maturity <= 0:
            print(f"Maturity date geçmiş: {matur_date}")
            return np.nan
        
        # Yıllık kupon ödemesi (4 çeyrek)
        annual_coupon = div_amount * 4
        
        # Maturity price (genellikle 25$ veya par value)
        maturity_price = 25.0  # Varsayılan maturity price
        
        # YTM hesaplama: (Annual Coupon + (Maturity Price - Current Price) / Years to Maturity) / Current Price
        years_to_maturity = days_to_maturity / 365.0
        
        if years_to_maturity <= 0:
            return np.nan
        
        # YTM = (Annual Coupon + (Maturity Price - Current Price) / Years to Maturity) / Current Price
        ytm = ((annual_coupon + (maturity_price - current_price) / years_to_maturity) / current_price) * 100
        
        return ytm
        
    except Exception as e:
        print(f"YTM hesaplama hatası: {e}")
        return np.nan

def calculate_ytc(row):
    """Yield to Call hesapla - CALL DATE kullanarak"""
    try:
        from datetime import datetime, date
        
        # Gerekli verileri al
        call_date = row['CALL DATE']
        div_adj_price = row['Div adj.price']
        last_price = row['Last Price']
        div_amount = row['DIV AMOUNT']
        coupon_rate = row['COUPON']
        
        if pd.isna(call_date) or pd.isna(div_amount):
            return np.nan
        
        # Div adj.price kullan, yoksa Last Price'a fallback yap
        current_price = div_adj_price if pd.notna(div_adj_price) and div_adj_price != 0 else last_price
        
        if pd.isna(current_price) or current_price == 0:
            return np.nan
        
        # CALL DATE'i parse et
        try:
            if isinstance(call_date, str):
                # Farklı tarih formatlarını dene
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d']:
                    try:
                        call_dt = datetime.strptime(call_date, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    print(f"CALL DATE parse edilemedi: {call_date}")
                    return np.nan
            else:
                call_dt = call_date.date() if hasattr(call_date, 'date') else call_date
        except Exception as e:
            print(f"CALL DATE parse hatası: {e}, değer: {call_date}")
            return np.nan
        
        # Bugünün tarihi
        today = date.today()
        
        # Call date'e kalan gün sayısı
        days_to_call = (call_dt - today).days
        
        if days_to_call <= 0:
            print(f"Call date geçmiş: {call_date}")
            return np.nan
        
        # Yıllık kupon ödemesi (4 çeyrek)
        annual_coupon = div_amount * 4
        
        # Call price (genellikle 25$ veya par value)
        call_price = 25.0  # Varsayılan call price
        
        # YTC hesaplama: (Annual Coupon + (Call Price - Current Price) / Years to Call) / Current Price
        years_to_call = days_to_call / 365.0
        
        if years_to_call <= 0:
            return np.nan
        
        # YTC = (Annual Coupon + (Call Price - Current Price) / Years to Call) / Current Price
        ytc = ((annual_coupon + (call_price - current_price) / years_to_call) / current_price) * 100
        
        return ytc
        
    except Exception as e:
        print(f"YTC hesaplama hatası: {e}")
        return np.nan

def calculate_gort_for_group(df, group_type, adv_file):
    """Standart gruplar için GORT hesapla"""
    try:
        print(f"\n=== GORT Hesaplama ({group_type}) ===")
        
        # Kuponlu gruplar listesi
        kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
        
        # ADV dosyasını oku (ham SMA değerleri için)
        try:
            adv_df = pd.read_csv(adv_file, encoding='utf-8-sig')
        except Exception as e:
            print(f"⚠️ ADV dosyası okunamadı: {e}")
            return df
        
        # SMA kolon isimleri (farklı formatları kontrol et)
        sma63_col_names = ['SMA63 chg', 'SMA63CHG', 'SMA63_chg', 'SMA 63 CHG']
        sma246_col_names = ['SMA246 chg', 'SMA 246 CHG', 'SMA246CHG', 'SMA246_CHG', 'SMA 246 chg']
        
        # ADV dosyasında hangi kolonlar var?
        sma63_col = None
        sma246_col = None
        
        for col_name in sma63_col_names:
            if col_name in adv_df.columns:
                sma63_col = col_name
                break
        
        for col_name in sma246_col_names:
            if col_name in adv_df.columns:
                sma246_col = col_name
                break
        
        if not sma63_col or not sma246_col:
            print(f"⚠️ SMA63 chg veya SMA246 chg kolonları bulunamadı")
            df['GORT'] = 0.0
            return df
        
        print(f"✓ SMA kolonları bulundu: {sma63_col}, {sma246_col}")
        
        # ADV dosyasından SMA değerlerini al ve df ile birleştir
        sma_data = adv_df[['PREF IBKR', sma63_col, sma246_col]].copy()
        sma_data[sma63_col] = pd.to_numeric(sma_data[sma63_col], errors='coerce')
        sma_data[sma246_col] = pd.to_numeric(sma_data[sma246_col], errors='coerce')
        
        # df ile birleştir
        df = df.merge(sma_data, on='PREF IBKR', how='left', suffixes=('', '_raw'))
        
        # GORT hesapla
        gort_values = []
        
        for idx, row in df.iterrows():
            symbol = row['PREF IBKR']
            sma63chg = row[sma63_col]
            sma246chg = row[sma246_col]
            
            if pd.isna(sma63chg) or pd.isna(sma246chg):
                gort_values.append(np.nan)
                continue
            
            # Grup ortalamalarını hesapla
            if group_type.lower() in kuponlu_groups:
                # Kuponlu gruplar: CGRUP'a göre gruplama
                cgrup = row.get('CGRUP', '')
                if pd.notna(cgrup) and cgrup != '' and cgrup != 'N/A':
                    cgrup_str = str(cgrup).strip()
                    # Aynı CGRUP'taki diğer hisselerin ortalaması
                    cgrup_rows = adv_df[(adv_df['CGRUP'] == cgrup_str) & (adv_df['PREF IBKR'] != symbol)]
                    sma63_values = pd.to_numeric(cgrup_rows[sma63_col], errors='coerce').dropna()
                    sma246_values = pd.to_numeric(cgrup_rows[sma246_col], errors='coerce').dropna()
                else:
                    # CGRUP yoksa grup ortalaması
                    sma63_values = pd.to_numeric(adv_df[sma63_col], errors='coerce').dropna()
                    sma246_values = pd.to_numeric(adv_df[sma246_col], errors='coerce').dropna()
            else:
                # Diğer standart gruplar: Grup içindeki tüm hisselerin ortalaması
                sma63_values = pd.to_numeric(adv_df[sma63_col], errors='coerce').dropna()
                sma246_values = pd.to_numeric(adv_df[sma246_col], errors='coerce').dropna()
            
            # Ortalamaları hesapla
            if len(sma63_values) > 0:
                group_avg_sma63 = sma63_values.mean()
                if group_avg_sma63 == 0:
                    group_avg_sma63 = 0.01
            else:
                group_avg_sma63 = 0.01
            
            if len(sma246_values) > 0:
                group_avg_sma246 = sma246_values.mean()
                if group_avg_sma246 == 0:
                    group_avg_sma246 = 0.01
            else:
                group_avg_sma246 = 0.01
            
            # GORT hesapla: 0.25 * (SMA63chg - group_avg_sma63) + 0.75 * (SMA246chg - group_avg_sma246)
            gort = (0.25 * (sma63chg - group_avg_sma63)) + (0.75 * (sma246chg - group_avg_sma246))
            gort_values.append(gort)
        
        df['GORT'] = gort_values
        df['GORT'] = pd.to_numeric(df['GORT'], errors='coerce')
        
        print(f"✓ GORT hesaplandı: {df['GORT'].notna().sum()}/{len(df)} hisse")
        print(f"GORT istatistikleri: min={df['GORT'].min():.4f}, max={df['GORT'].max():.4f}, mean={df['GORT'].mean():.4f}")
        
        return df
        
    except Exception as e:
        print(f"⚠️ GORT hesaplama hatası: {e}")
        import traceback
        traceback.print_exc()
        df['GORT'] = 0.0
        return df

def normalize_scores(df):
    """Skorları normalize et (5-95 aralığında)"""
    try:
        print("\n=== Skor Normalizasyonu ===")
        
        # EXP_ANN_RETURN normalize et
        if 'EXP_ANN_RETURN' in df.columns:
            exp_values = df['EXP_ANN_RETURN'].dropna()
            if len(exp_values) > 0:
                exp_min, exp_max = exp_values.min(), exp_values.max()
                if exp_max != exp_min:
                    df['EXP_ANN_RETURN_NORM'] = 5 + ((df['EXP_ANN_RETURN'] - exp_min) / (exp_max - exp_min)) * 90
                else:
                    df['EXP_ANN_RETURN_NORM'] = 50
                print(f"EXP_ANN_RETURN: {exp_min:.2f}-{exp_max:.2f} -> 5-95")
        
        # YTM normalize et (özel gruplar için)
        if 'YTM' in df.columns:
            ytm_values = df['YTM'].dropna()
            if len(ytm_values) > 0:
                ytm_min, ytm_max = ytm_values.min(), ytm_values.max()
                if ytm_max != ytm_min:
                    df['YTM_NORM'] = 5 + ((df['YTM'] - ytm_min) / (ytm_max - ytm_min)) * 90
                else:
                    df['YTM_NORM'] = 50
                print(f"YTM: {ytm_min:.2f}-{ytm_max:.2f} -> 5-95")
        
        # YTC normalize et (YTC grupları için)
        if 'YTC' in df.columns:
            ytc_values = df['YTC'].dropna()
            if len(ytc_values) > 0:
                ytc_min, ytc_max = ytc_values.min(), ytc_values.max()
                if ytc_max != ytc_min:
                    df['YTC_NORM'] = 5 + ((df['YTC'] - ytc_min) / (ytc_max - ytc_min)) * 90
                else:
                    df['YTC_NORM'] = 50
                print(f"YTC: {ytc_min:.2f}-{ytc_max:.2f} -> 5-95")
        
        # SMA normalize et
        sma_cols = ['SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm']
        for col in sma_cols:
            if col in df.columns:
                values = df[col].dropna()
                if len(values) > 0:
                    min_val, max_val = values.min(), values.max()
                    if max_val != min_val:
                        df[col] = 5 + ((df[col] - min_val) / (max_val - min_val)) * 90
                    else:
                        df[col] = 50
        
        # High/Low normalize et
        high_low_cols = ['1Y_High_diff_norm', '1Y_Low_diff_norm', 'Aug4_chg_norm', 'Oct19_chg_norm']
        for col in high_low_cols:
            if col in df.columns:
                values = df[col].dropna()
                if len(values) > 0:
                    min_val, max_val = values.min(), values.max()
                    if max_val != min_val:
                        df[col] = 5 + ((df[col] - min_val) / (max_val - min_val)) * 90
                    else:
                        df[col] = 50
        
        # GORT normalize et (standart gruplar için) - TERSİNE ÇEVRİLMİŞ
        # Yüksek GORT = kötü (düşük skor), Düşük GORT = iyi (yüksek skor)
        if 'GORT' in df.columns:
            gort_values = df['GORT'].dropna()
            if len(gort_values) > 0:
                gort_min, gort_max = gort_values.min(), gort_values.max()
                if gort_max != gort_min:
                    # Tersine çevrilmiş normalizasyon: En yüksek GORT → 5, En düşük GORT → 95
                    df['GORT_NORM'] = 5 + ((gort_max - df['GORT']) / (gort_max - gort_min)) * 90
                else:
                    df['GORT_NORM'] = 50
                print(f"GORT (tersine çevrilmiş): {gort_min:.4f}-{gort_max:.4f} -> En yüksek GORT=5, En düşük GORT=95")
            else:
                df['GORT_NORM'] = 50
                print("GORT normalize edilemedi, varsayılan 50 değeri kullanıldı")
        
        print("✓ Tüm skorlar normalize edildi")
        return df
        
    except Exception as e:
        print(f"Normalizasyon hatası: {e}")
        return df

def calculate_final_thg(df, market_weights, group_type=None, adv_file=None):
    """FINAL THG hesapla - Grup tipine göre farklı formüller"""
    try:
        print(f"\n=== FINAL_THG Hesaplama ({group_type}) ===")
        
        # Expected Annual Return hesapla
        print("Expected Annual Return hesaplanıyor...")
        df['EXP_ANN_RETURN'] = df.apply(calculate_expected_annual_return, axis=1)
        
        # YTM hesapla (özel gruplar için)
        if group_type in ['heldbesmaturlu', 'heldhighmatur', 'notbesmatur', 'highmatur']:
            print("YTM hesaplanıyor...")
            df['YTM'] = df.apply(calculate_ytm, axis=1)
        
        # YTC hesapla (YTC grupları için)
        if group_type in ['helddeznff', 'heldnff']:
            print("YTC hesaplanıyor...")
            df['YTC'] = df.apply(calculate_ytc, axis=1)
        
        # Özel formül grupları için kontrol
        special_groups = ['heldbesmaturlu', 'heldhighmatur', 'notbesmatur']
        ytc_groups = ['helddeznff', 'heldnff']
        exp_return_groups = ['heldff', 'heldflr', 'heldsolidbig', 'heldtitrekhc', 'nottitrekhc']
        
        # Standart gruplar için GORT hesapla (özel gruplar hariç)
        is_standard_group = group_type not in special_groups + ytc_groups + exp_return_groups + ['highmatur']
        
        if is_standard_group and adv_file:
            print("Standart grup tespit edildi - GORT hesaplanıyor...")
            df = calculate_gort_for_group(df, group_type, adv_file)
        
        # Skorları normalize et
        df = normalize_scores(df)
        
        # Ağırlıkları al
        solidity_weight = market_weights['solidity_weight']
        yield_weight = market_weights['yield_weight']
        adv_weight = market_weights['adv_weight']
        exp_return_weight = market_weights.get('exp_return_weight', 800)  # Varsayılan değer
        
        print(f"Ağırlıklar: Solidity={solidity_weight:.2f}, Yield={yield_weight:.2f}, ADV={adv_weight:.6f}, EXP_RETURN={exp_return_weight}")
        
        # Özel formül grupları için kontrol
        special_groups = ['heldbesmaturlu', 'heldhighmatur', 'notbesmatur']
        ytc_groups = ['helddeznff', 'heldnff']
        exp_return_groups = ['heldff', 'heldflr', 'heldsolidbig', 'heldtitrekhc', 'nottitrekhc']
        
        if group_type in exp_return_groups:
            print(f"Özel formül kullanılıyor ({group_type}): 2*SOLIDITY_SCORE_NORM + 13*SMA63_chg_norm")
            
            # Gerekli kolonları kontrol et
            required_cols = ['SOLIDITY_SCORE_NORM', 'SMA63_chg_norm']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"Eksik kolonlar: {missing_cols}")
                return df
            
            # Eksik değerleri doldur
            for col in required_cols:
                if df[col].isna().any():
                    quantile_value = df[col].dropna().quantile(0.12)
                    df[col] = df[col].fillna(quantile_value)
                    print(f"{col} eksik değerleri {quantile_value:.4f} ile dolduruldu")
            
            # Özel formül: 2 * SOLIDITY_SCORE_NORM + 13 * SMA63_chg_norm
            df['FINAL_THG'] = (
                df['SOLIDITY_SCORE_NORM'] * 2 +
                df['SMA63_chg_norm'] * 13
            )
            
            print("✓ Özel SMA63_chg_norm formül hesaplama tamamlandı")
            return df
        elif group_type in ytc_groups:
            print(f"Özel formül kullanılıyor ({group_type}): YTC_NORM*3 + SOLIDITY_SCORE_NORM*2 + SMA63_chg_norm*10")
            
            # Gerekli kolonları kontrol et
            required_cols = ['YTC_NORM', 'SOLIDITY_SCORE_NORM', 'SMA63_chg_norm']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"Eksik kolonlar: {missing_cols}")
                return df
            
            # Eksik değerleri doldur
            for col in required_cols:
                if df[col].isna().any():
                    quantile_value = df[col].dropna().quantile(0.12)
                    df[col] = df[col].fillna(quantile_value)
                    print(f"{col} eksik değerleri {quantile_value:.4f} ile dolduruldu")
            
            # Özel formül: YTC_NORM * 3 + SOLIDITY_SCORE_NORM * 2 + SMA63_chg_norm * 10
            df['FINAL_THG'] = (
                df['YTC_NORM'] * 3 +
                df['SOLIDITY_SCORE_NORM'] * 2 +
                df['SMA63_chg_norm'] * 10
            )
            
            print("✓ Özel YTC formül hesaplama tamamlandı")
            return df
        elif group_type in special_groups:
            print(f"Özel formül kullanılıyor ({group_type}): YTM_NORM*4 + SMA63_chg_norm*9 + SOLIDITY_SCORE_NORM*2")
            
            # Gerekli kolonları kontrol et
            required_cols = ['YTM_NORM', 'SMA63_chg_norm', 'SOLIDITY_SCORE_NORM']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"Eksik kolonlar: {missing_cols}")
                return df
            
            # Eksik değerleri doldur
            for col in required_cols:
                if df[col].isna().any():
                    quantile_value = df[col].dropna().quantile(0.12)
                    df[col] = df[col].fillna(quantile_value)
                    print(f"{col} eksik değerleri {quantile_value:.4f} ile dolduruldu")
            
            # Özel formül: YTM_NORM * 4 + SMA63_chg_norm * 9 + SOLIDITY_SCORE_NORM * 2
            df['FINAL_THG'] = (
                df['YTM_NORM'] * 4 +
                df['SMA63_chg_norm'] * 9 +
                df['SOLIDITY_SCORE_NORM'] * 2
            )
            
            print("✓ Özel formül hesaplama tamamlandı")
            return df
        elif group_type == 'highmatur':
            print(f"Özel formül kullanılıyor ({group_type}): YTM_NORM*4 + SMA63_chg_norm*9 + SOLIDITY_SCORE_NORM*2")
            
            # Gerekli kolonları kontrol et
            required_cols = ['YTM_NORM', 'SMA63_chg_norm', 'SOLIDITY_SCORE_NORM']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"Eksik kolonlar: {missing_cols}")
                return df
            
            # Eksik değerleri doldur
            for col in required_cols:
                if df[col].isna().any():
                    quantile_value = df[col].dropna().quantile(0.12)
                    df[col] = df[col].fillna(quantile_value)
                    print(f"{col} eksik değerleri {quantile_value:.4f}")
            
            # Özel formül: YTM_NORM * 4 + SMA63_chg_norm * 9 + SOLIDITY_SCORE_NORM * 2
            df['FINAL_THG'] = (
                df['YTM_NORM'] * 4 +
                df['SMA63_chg_norm'] * 9 +
                df['SOLIDITY_SCORE_NORM'] * 2
            )
            
            print("✓ Özel formül hesaplama tamamlandı")
            return df
        
        # Standart formül için gerekli kolonları kontrol et
        required_cols = [
            'SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm',
            '1Y_High_diff_norm', '1Y_Low_diff_norm',
            'Aug4_chg_norm', 'Oct19_chg_norm',
            'SOLIDITY_SCORE_NORM', 'CUR_YIELD', 'AVG_ADV'
        ]
        
        # Eksik kolonları kontrol et
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"Eksik kolonlar: {missing_cols}")
            return df
        
        # Eksik değerleri doldur
        for col in required_cols:
            if df[col].isna().any():
                quantile_value = df[col].dropna().quantile(0.12)
                df[col] = df[col].fillna(quantile_value)
                print(f"{col} eksik değerleri {quantile_value:.2f} ile dolduruldu")
        
        # Standart formül kullan (Dinamik ağırlıklar)
        print("Standart formül kullanılıyor (Dinamik ağırlıklar)...")
        print(f"Kullanılan ağırlıklar: Solidity={solidity_weight}, Yield={yield_weight}")
        
        # CUR_YIELD değerlerini sınırla (0-10 arası)
        df['CUR_YIELD_LIMITED'] = df['CUR_YIELD'].clip(upper=10.0)
        
        # Adj Risk Premium işlemi - SADECE kuponlu gruplar için
        if group_type in ['heldkuponlu', 'heldkuponlukreorta', 'heldkuponlukreciliz']:
            print(f"\n=== Adj Risk Premium İşlemi ({group_type} grubu için) ===")
            
            # Adj Risk Premium eksik değerleri doldur ve 4 ondalık hane ile yuvarla
            print(f"Adj Risk Premium değerleri: {df['Adj Risk Premium'].describe()}")
            
            if df['Adj Risk Premium'].isna().any():
                if df['Adj Risk Premium'].dropna().empty:
                    print("HATA: Adj Risk Premium değerleri tamamen boş!")
                    df['Adj Risk Premium'] = 0.0
                else:
                    adj_risk_quantile = df['Adj Risk Premium'].dropna().quantile(0.12)
                    df['Adj Risk Premium'] = df['Adj Risk Premium'].fillna(adj_risk_quantile).round(4)
                    print(f"Adj Risk Premium eksik değerleri {adj_risk_quantile:.4f} ile dolduruldu")
            else:
                # Eksik değer yoksa da 4 ondalık hane ile yuvarla
                df['Adj Risk Premium'] = df['Adj Risk Premium'].round(4)
            
            # Kupon oranına göre Adj Risk Premium düşürme
            print("\n=== Kupon Oranına Göre Adj Risk Premium Düşürme ===")
            
            # COUPON kolonunu numeric'e çevir
            df['COUPON_NUMERIC'] = df['COUPON'].str.replace('%', '').astype(float)
            
            # Final Adj Risk Premium kolonunu oluştur
            df['Final Adj Risk Premium'] = df['Adj Risk Premium'].copy()
            
            # Kupon oranına göre düşürme kuralları
            coupon_4_15_below = df['COUPON_NUMERIC'] < 4.16
            coupon_4_16_to_4_54 = (df['COUPON_NUMERIC'] >= 4.16) & (df['COUPON_NUMERIC'] < 4.55)
            coupon_4_55_to_4_84 = (df['COUPON_NUMERIC'] >= 4.55) & (df['COUPON_NUMERIC'] <= 4.84)
            coupon_4_86_to_5_26 = (df['COUPON_NUMERIC'] >= 4.86) & (df['COUPON_NUMERIC'] <= 5.26)
            
            # Düşürme işlemleri (farklı oranlar)
            df.loc[coupon_4_15_below, 'Final Adj Risk Premium'] = df.loc[coupon_4_15_below, 'Final Adj Risk Premium'] - 0.0060
            df.loc[coupon_4_16_to_4_54, 'Final Adj Risk Premium'] = df.loc[coupon_4_16_to_4_54, 'Final Adj Risk Premium'] - 0.0045
            df.loc[coupon_4_55_to_4_84, 'Final Adj Risk Premium'] = df.loc[coupon_4_55_to_4_84, 'Final Adj Risk Premium'] - 0.0030
            df.loc[coupon_4_86_to_5_26, 'Final Adj Risk Premium'] = df.loc[coupon_4_86_to_5_26, 'Final Adj Risk Premium'] - 0.0015
            
            # Negatif değerleri 0 yap
            df['Final Adj Risk Premium'] = df['Final Adj Risk Premium'].clip(lower=0)
            
            # 4 ondalık hane ile yuvarla
            df['Final Adj Risk Premium'] = df['Final Adj Risk Premium'].round(4)
            
            # İstatistikleri göster
            print(f"Kupon < 4.16 olan hisseler: {coupon_4_15_below.sum()} adet (Adj Risk Premium -0.0060)")
            print(f"Kupon 4.16-4.54 arası hisseler: {coupon_4_16_to_4_54.sum()} adet (Adj Risk Premium -0.0045)")
            print(f"Kupon 4.55-4.84 arası hisseler: {coupon_4_55_to_4_84.sum()} adet (Adj Risk Premium -0.0030)")
            print(f"Kupon 4.86-5.26 arası hisseler: {coupon_4_86_to_5_26.sum()} adet (Adj Risk Premium -0.0015)")
            print(f"Kupon > 5.26 olan hisseler: {(df['COUPON_NUMERIC'] > 5.26).sum()} adet (düşürme yok)")
            
            # Örnek değerler göster
            print("\nÖrnek Adj Risk Premium düşürme işlemleri:")
            sample_stocks = df.head(5)
            for _, row in sample_stocks.iterrows():
                coupon_rate = row['COUPON_NUMERIC']
                original_adj_risk = row['Adj Risk Premium']
                final_adj_risk = row['Final Adj Risk Premium']
                print(f"{row['PREF IBKR']}: Kupon={coupon_rate:.2f}%, Adj Risk={original_adj_risk:.4f} -> Final={final_adj_risk:.4f}")
            
            # COUPON_NUMERIC kolonunu kaldır
            df = df.drop(columns=['COUPON_NUMERIC'])
            
            # SOLCALL_SCORE hesapla: (Final Adj Risk Premium * adj_risk_premium_weight) + (SOLIDITY_SCORE_NORM * 0.24)
            print(f"\n=== SOLCALL_SCORE Hesaplama Detayları ===")
            print(f"Formül: (Final Adj Risk Premium * {market_weights['adj_risk_premium_weight']:.0f}) + (SOLIDITY_SCORE_NORM * 0.24)")
            
            # Final Adj Risk Premium değerlerini kontrol et
            print(f"Final Adj Risk Premium istatistikleri:")
            print(df['Final Adj Risk Premium'].describe())
            
            # Örnek hesaplamalar göster
            sample_stocks = df.head(5)
            for _, row in sample_stocks.iterrows():
                final_adj_risk = row['Final Adj Risk Premium']
                solidity = row['SOLIDITY_SCORE_NORM']
                if pd.notna(final_adj_risk) and pd.notna(solidity):
                    solcall = (final_adj_risk * market_weights['adj_risk_premium_weight']) + (solidity * 0.24)
                    print(f"{row['PREF IBKR']}: Final Adj Risk={final_adj_risk:.4f}, Solidity={solidity:.2f}, SOLCALL={solcall:.2f}")
            
            df['SOLCALL_SCORE'] = (df['Final Adj Risk Premium'] * market_weights['adj_risk_premium_weight']) + (df['SOLIDITY_SCORE_NORM'] * 0.24)
        else:
            # Diğer gruplar için Adj Risk Premium = 0
            print(f"\n=== Adj Risk Premium İşlemi ({group_type} grubu için) ===")
            print("Bu grup için Adj Risk Premium kullanılmıyor, 0 olarak ayarlanıyor")
            df['Adj Risk Premium'] = 0.0
            df['Final Adj Risk Premium'] = 0.0
            df['SOLCALL_SCORE'] = df['SOLIDITY_SCORE_NORM'] * 0.24
        
        # SOLCALL_SCORE'u normalize et (5-95 aralığında)
        solcall_values = df['SOLCALL_SCORE'].dropna()
        if len(solcall_values) > 0:
            solcall_min, solcall_max = solcall_values.min(), solcall_values.max()
            if solcall_max != solcall_min:
                df['SOLCALL_SCORE_NORM'] = 5 + ((df['SOLCALL_SCORE'] - solcall_min) / (solcall_max - solcall_min)) * 90
            else:
                df['SOLCALL_SCORE_NORM'] = 50
            print(f"SOLCALL_SCORE normalize edildi: {solcall_min:.2f}-{solcall_max:.2f} -> 5-95")
        else:
            df['SOLCALL_SCORE_NORM'] = 50
            print("SOLCALL_SCORE normalize edilemedi, varsayılan 50 değeri kullanıldı")
        
        # Credit Score Norm hesapla (basit bir örnek - gerçek veriye göre değiştirilebilir)
        # Şimdilik SOLIDITY_SCORE_NORM'u kullanıyoruz, ama ayrı bir credit score hesaplaması yapılabilir
        df['CREDIT_SCORE_NORM'] = df['SOLIDITY_SCORE_NORM']  # Geçici olarak SOLIDITY_SCORE_NORM kullanıyoruz
        
        # EX_FINAL_THG hesapla (eski formül)
        df['EX_FINAL_THG'] = (
            (df['SMA20_chg_norm'] * 0.4 + df['SMA63_chg_norm'] * 0.9 + df['SMA246_chg_norm'] * 1.1) * 2.4 +   # SMA toplamı * 2.4 (SMA20=0.4, SMA63=0.9, SMA246=1.1)
            (df['1Y_High_diff_norm'] + df['1Y_Low_diff_norm']) * 2.2 +                      # High+Low toplamı * 2.2
            df['Aug4_chg_norm'] * 0.50 +                                                     # Aug ağırlığı
            df['Oct19_chg_norm'] * 0.50 +                                                    # Oct ağırlığı
            df['SOLIDITY_SCORE_NORM'] * solidity_weight +                                     # Solidity * solidity_weight
            df['CUR_YIELD_LIMITED'] * yield_weight * 0.75 +                                   # CUR_YIELD (sınırlı) * yield_weight * 0.75 (%25 azaltma)
            df['AVG_ADV'] * adv_weight +                                                      # AVG_ADV * adv_weight
            df['SOLCALL_SCORE_NORM'] * market_weights['solcall_score_weight'] * 0.85 +        # SOLCALL_SCORE * solcall_score_weight * 0.85 (%15 azaltma)
            df['CREDIT_SCORE_NORM'] * market_weights['credit_score_norm_weight']              # CREDIT_SCORE_NORM * credit_score_norm_weight
        )
        
        # GORT hesapla ve normalize et (standart gruplar için)
        # GORT_NORM eksik değerleri doldur
        if 'GORT_NORM' in df.columns:
            if df['GORT_NORM'].isna().any():
                quantile_value = df['GORT_NORM'].dropna().quantile(0.12)
                df['GORT_NORM'] = df['GORT_NORM'].fillna(quantile_value)
                print(f"GORT_NORM eksik değerleri {quantile_value:.2f} ile dolduruldu")
        else:
            # GORT_NORM yoksa varsayılan değer
            df['GORT_NORM'] = 50.0
            print("⚠️ GORT_NORM bulunamadı, varsayılan 50 değeri kullanıldı")
        
        # Yeni FINAL_THG formülü: EX_FINAL_THG * 0.6 + GORT_NORM * 10
        df['FINAL_THG'] = df['EX_FINAL_THG'] * 0.6 + df['GORT_NORM'] * 10
        
        # Kullanılan ağırlıkları kaydet
        df['SOLIDITY_WEIGHT_USED'] = solidity_weight
        df['YIELD_WEIGHT_USED'] = yield_weight * 0.75  # %25 azaltılmış yield ağırlığı
        df['ADV_WEIGHT_USED'] = adv_weight
        df['SOLCALL_SCORE_WEIGHT_USED'] = market_weights['solcall_score_weight'] * 0.85  # %15 azaltılmış solcall ağırlığı
        df['CREDIT_SCORE_NORM_WEIGHT_USED'] = market_weights['credit_score_norm_weight']
        df['ADJ_RISK_PREMIUM_WEIGHT_USED'] = market_weights['adj_risk_premium_weight']
        df['SMA20_WEIGHT_USED'] = 0.4  # SMA20 için özel ağırlık
        
        print("✓ Standart formül hesaplama tamamlandı")
        print(f"Kullanılan ağırlıklar:")
        print(f"  - SMA20 Weight: 0.4 (SMA20 ağırlığı)")
        print(f"  - SMA63 Weight: 0.9 (SMA63 ağırlığı)")
        print(f"  - SMA246 Weight: 1.1 (SMA246 ağırlığı)")
        print(f"  - Yield Weight: {yield_weight * 0.75:.2f} (orijinal {yield_weight} * 0.75)")
        print(f"  - SOLCALL Score Weight: {market_weights['solcall_score_weight'] * 0.85:.2f} (orijinal {market_weights['solcall_score_weight']} * 0.85)")
        print(f"  - Credit Score Norm Weight: {market_weights['credit_score_norm_weight']:.2f}")
        print(f"  - Adj Risk Premium Weight: {market_weights['adj_risk_premium_weight']:.0f}")
        print(f"FINAL_THG örnek değerler: {df['FINAL_THG'].head().tolist()}")
        print(f"FINAL_THG istatistikleri: {df['FINAL_THG'].describe()}")
        return df
        
    except Exception as e:
        print(f"FINAL THG hesaplama hatası: {e}")
        return df

def process_single_file(adv_file, market_weights):
    """Tek bir dosyayı işle"""
    try:
        print(f"\n=== {adv_file} işleniyor ===")
        
        # Dosya adından FINE dosyası adını oluştur
        fine_file = adv_file.replace('advek', 'finek')
        
        # Grup tipini belirle
        group_type = None
        if 'heldbesmaturlu' in adv_file:
            group_type = 'heldbesmaturlu'
            print("Heldbesmaturlu grubu tespit edildi - Özel formül kullanılacak")
        elif 'heldhighmatur' in adv_file:
            group_type = 'heldhighmatur'
            print("Heldhighmatur grubu tespit edildi - Özel formül kullanılacak")
        elif 'highmatur' in adv_file:
            group_type = 'highmatur'
            print("Highmatur grubu tespit edildi - Özel formül kullanılacak")
        elif 'notbesmatur' in adv_file:
            group_type = 'notbesmatur'
            print("Notbesmatur grubu tespit edildi - Özel formül kullanılacak")
        elif 'helddeznff' in adv_file:
            group_type = 'helddeznff'
            print("Helddeznff grubu tespit edildi - Özel YTC formül kullanılacak")
        elif 'heldnff' in adv_file:
            group_type = 'heldnff'
            print("Heldnff grubu tespit edildi - Özel YTC formül kullanılacak")
        elif 'heldff' in adv_file:
            group_type = 'heldff'
            print("Heldff grubu tespit edildi - Özel EXP_RETURN formül kullanılacak")
        elif 'heldflr' in adv_file:
            group_type = 'heldflr'
            print("Heldflr grubu tespit edildi - Özel EXP_RETURN formül kullanılacak")
        elif 'heldsolidbig' in adv_file:
            group_type = 'heldsolidbig'
            print("Heldsolidbig grubu tespit edildi - Özel EXP_RETURN formül kullanılacak")
        elif 'heldtitrekhc' in adv_file:
            group_type = 'heldtitrekhc'
            print("Heldtitrekhc grubu tespit edildi - Özel EXP_RETURN formül kullanılacak")
        elif 'nottitrekhc' in adv_file:
            group_type = 'nottitrekhc'
            print("Nottitrekhc grubu tespit edildi - Özel EXP_RETURN formül kullanılacak")
        elif 'heldkuponlu' in adv_file and not any(x in adv_file for x in ['heldkuponlukreorta', 'heldkuponlukreciliz']):
            group_type = 'heldkuponlu'
            print("Heldkuponlu grubu tespit edildi - Adj Risk Premium kullanılacak")
        elif 'heldkuponlukreorta' in adv_file:
            group_type = 'heldkuponlukreorta'
            print("Heldkuponlukreorta grubu tespit edildi - Adj Risk Premium kullanılacak")
        elif 'heldkuponlukreciliz' in adv_file:
            group_type = 'heldkuponlukreciliz'
            print("Heldkuponlukreciliz grubu tespit edildi - Adj Risk Premium kullanılacak")
        else:
            print("Standart grup - Adj Risk Premium 0 yapılacak")
        
        # Verileri yükle
        adv_df = load_single_adv_file(adv_file)
        if adv_df is None:
            return None
            
        solidity_df = load_solidity_data()
        if solidity_df is None:
            return None
            
        ibkr_df = load_sek_data()
        if ibkr_df is None:
            return None
        
        # Verileri hazırla
        df = prepare_data_for_calculation(adv_df, solidity_df, ibkr_df)
        if df is None:
            return None
        
        # FINAL_THG hesapla - Grup tipine göre (adv_file parametresi ile)
        df = calculate_final_thg(df, market_weights, group_type, adv_file)
        
        # Last Price eksik olan hisseleri filtrele (PRS ve PRH hariç)
        last_price_missing = df['Last Price'].isna() | (df['Last Price'] == 0)
        contains_prs_prh = df['PREF IBKR'].str.contains('PRS|PRH', na=False)
        rows_to_remove = last_price_missing & ~contains_prs_prh
        df = df[~rows_to_remove].copy()
        
        # source_file kolonunu kaldır
        if 'source_file' in df.columns:
            df = df.drop(columns=['source_file'])
        
        # Duplicate satırları temizle - PREF IBKR'e göre
        before_dedup = len(df)
        df = df.drop_duplicates(subset=['PREF IBKR'], keep='first')
        after_dedup = len(df)
        if before_dedup != after_dedup:
            print(f"⚠️  {before_dedup - after_dedup} adet duplicate satır temizlendi")
        
        # CSV dosyasını oluştur - Adj Risk Premium için 4 ondalık hane, diğerleri 2 hane
        # Adj Risk Premium kolonunu 4 ondalık hane ile formatla
        if 'Adj Risk Premium' in df.columns:
            df['Adj Risk Premium'] = df['Adj Risk Premium'].round(4)
        
        # Önce tüm sayısal kolonları 2 ondalık hane ile yuvarla
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        for col in numeric_columns:
            if col != 'Adj Risk Premium':  # Adj Risk Premium hariç
                df[col] = df[col].round(2)
        
        df.to_csv(fine_file, 
                  index=False,
                  float_format='%.2f',  # Genel olarak 2 ondalık hane
                  sep=',',
                  encoding='utf-8-sig',
                  lineterminator='\n',
                  quoting=1)
        
        print(f"✓ Sonuçlar '{fine_file}' dosyasına kaydedildi: {len(df)} satır")
        
        # Top 10 skorları göster
        print(f"\n=== {fine_file} - Top 10 FINAL THG Skorları ===")
        if group_type in ['highmatur', 'heldbesmaturlu', 'heldhighmatur', 'notbesmatur', 'helddeznff', 'heldnff', 'heldff', 'heldflr', 'heldsolidbig', 'heldtitrekhc', 'nottitrekhc']:
            top_10 = df.nlargest(10, 'FINAL_THG')[['PREF IBKR', 'SOLIDITY_SCORE_NORM', 'Adj Risk Premium', 'FINAL_THG']]
        else:
            top_10 = df.nlargest(10, 'FINAL_THG')[['PREF IBKR', 'SOLIDITY_SCORE_NORM', 'CUR_YIELD', 'FINAL_THG']]
        print(top_10.round(2).to_string(index=False))
        
        return df
        
    except Exception as e:
        print(f"! {adv_file} işlenirken hata: {e}")
        return None

def main():
    """Ana fonksiyon"""
    try:
        print("=== FINAL THG Hesaplama Scripti - Sıfırdan Yazılmış ===")
        print("COUPON ve DIV AMOUNT değerleri hiç değiştirilmez!")
        
        # Piyasa ağırlıklarını al
        market_weights = get_market_weights()
        print(f"Piyasa ağırlıkları: {market_weights}")
        
        # ADV dosyalarını bul
        adv_files, sek_files = get_csv_files()
        
        if not adv_files:
            print("HATA: Hiç ADV dosyası bulunamadı!")
            return
        
        print(f"Bulunan ADV dosyaları: {len(adv_files)} adet")
        print(f"Bulunan SEK dosyaları: {len(sek_files)} adet")
        
        # Her dosyayı ayrı ayrı işle
        all_results = []
        for adv_file in adv_files:
            result_df = process_single_file(adv_file, market_weights)
            if result_df is not None:
                all_results.append(result_df)
        
        # Genel istatistikler
        if all_results:
            print("\n=== GENEL İSTATİSTİKLER ===")
            total_stocks = sum(len(df) for df in all_results)
            print(f"Toplam işlenen hisse sayısı: {total_stocks}")
            
            # Tüm sonuçları birleştir
            combined_df = pd.concat(all_results, ignore_index=True)
            
            # Genel duplicate kontrolü
            before_combined_dedup = len(combined_df)
            combined_df = combined_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
            after_combined_dedup = len(combined_df)
            if before_combined_dedup != after_combined_dedup:
                print(f"⚠️  Genel olarak {before_combined_dedup - after_combined_dedup} adet duplicate satır temizlendi")
            
            print(f"Ortalama FINAL_THG: {combined_df['FINAL_THG'].mean():.2f}")
            print(f"En yüksek FINAL_THG: {combined_df['FINAL_THG'].max():.2f}")
            print(f"En düşük FINAL_THG: {combined_df['FINAL_THG'].min():.2f}")
        
        print("\n✓ Tüm işlemler tamamlandı!")
        
    except Exception as e:
        print(f"Ana hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main() 