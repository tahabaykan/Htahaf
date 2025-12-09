#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YIELD Hesaplama ve Treasury Yield'larını Ekleme
"""

import pandas as pd
import numpy as np
import glob
import os
from datetime import datetime
import json

def calculate_yield(settlement_date, maturity_date, coupon_rate, price, redemption=25, frequency=2, basis=0):
    """
    Doğru YIELD TO CALL hesaplama fonksiyonu
    Price = Div adj.price, Redemption = 25
    Cally değerleri %8-10 civarında olmalı (0.08 - 0.10 formatında)
    """
    try:
        if isinstance(settlement_date, str):
            settlement_date = pd.to_datetime(settlement_date)
        if isinstance(maturity_date, str):
            maturity_date = pd.to_datetime(maturity_date)
        
        if isinstance(coupon_rate, str):
            coupon_rate = float(coupon_rate.replace('%', '')) / 100
        
        price = float(price)
        
        days_to_maturity = (maturity_date - settlement_date).days
        years_to_maturity = days_to_maturity / 365.25
        
        if years_to_maturity <= 0:
            return np.nan
        
        # YIELD TO CALL hesaplama - Excel YIELD fonksiyonu benzeri
        # YIELD = (Annual Coupon + (Redemption - Price) / Years) / Price
        
        # Yıllık kupon ödemesi
        annual_coupon = redemption * coupon_rate
        
        # Yield hesaplama
        yield_rate = (annual_coupon + (redemption - price) / years_to_maturity) / price
        
        # Cally değerini decimal formatında döndür (0.08 = %8)
        return yield_rate
        
    except Exception as e:
        return np.nan

def load_treasury_yields(csv_file="treyield.csv"):
    """
    Treasury yield'larını CSV dosyasından yükler
    """
    try:
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            treasury_yields = {}
            
            for _, row in df.iterrows():
                maturity = row['Maturity']
                yield_rate = row['Yield_Rate']  # Zaten decimal formatında
                treasury_yields[maturity] = yield_rate
            
            print(f"Treasury yield'ları {csv_file} dosyasından yüklendi:")
            for maturity, rate in treasury_yields.items():
                print(f"  {maturity}: {rate:.3f}%")
            
            return treasury_yields
        else:
            print(f"{csv_file} dosyası bulunamadı!")
            return None
            
    except Exception as e:
        print(f"Treasury yield yükleme hatası: {e}")
        return None

def check_yek_files():
    """
    YEK dosyalarının varlığını kontrol eder
    """
    try:
        # Treasury yield'larını yükle
        treasury_yields = load_treasury_yields()
        if not treasury_yields:
            print("Treasury yield'ları yüklenemedi!")
            return
        
        # Sadece ana dizindeki YEK dosyalarını bul (alt dizinlerdeki değil)
        yek_files = []
        current_dir = os.getcwd()
        for file in os.listdir(current_dir):
            if file.startswith('yek') and file.endswith('.csv'):
                # Dosya ana dizinde mi kontrol et
                file_path = os.path.join(current_dir, file)
                if os.path.isfile(file_path) and not os.path.dirname(file_path).endswith(('janall', 'janallw', 'janall_backup')):
                    yek_files.append(file)
        
        if not yek_files:
            print("yek*.csv dosyaları bulunamadı!")
            return
        
        print(f"Bulunan YEK dosyaları (sadece ana dizinden): {len(yek_files)} adet")
        
        for yek_file in yek_files:
            try:
                print(f"\nİşleniyor: {yek_file}")
                
                # YEK dosyasını oku
                df = pd.read_csv(yek_file)
                print(f"  {len(df)} satır okundu")
                
                # COUPON kolonunu bul
                coupon_col = None
                for col in df.columns:
                    if 'COUPON' in col.upper() or 'KUPON' in col.upper():
                        coupon_col = col
                        break
                
                if not coupon_col:
                    print(f"  Coupon kolonu bulunamadı: {yek_file}")
                    continue
                
                # YEK dosyası zaten mevcut, herhangi bir işlem yapmaya gerek yok
                # Cally değerleri calculate_cally_values() fonksiyonunda hesaplanacak
                print(f"  {yek_file} hazır, Cally hesaplaması sonra yapılacak")
                
            except Exception as e:
                print(f"  {yek_file} işleme hatası: {e}")
        
        print("Tüm dosyalar işlendi!")
        
    except Exception as e:
        print(f"Genel hata: {e}")

def collect_csv_files():
    """
    Belirtilen CSV dosyalarını tek bir dosyada toplar
    """
    try:
        print("=== CSV Dosyalarını Toplama ===")
        print("⚠️  SADECE ANA DİZİNDEKİ (StockTracker) YEK DOSYALARI KULLANILACAK!")
        
        # Toplanacak CSV dosyaları (sadece ana dizindeki)
        csv_files = [
            'yekheldbesmaturlu.csv',
            'yekheldcilizyeniyedi.csv', 
            'yekheldcommonsuz.csv',
            'yekhelddeznff.csv',
            'yekheldff.csv',
            'yekheldgarabetaltiyedi.csv',
            'yekheldkuponlu.csv',
            'yekheldkuponlukreciliz.csv',
            'yekheldkuponlukreorta.csv',
            'yekheldnff.csv',
            'yekheldotelremorta.csv',
            'yekheldsolidbig.csv',
            'yekheldtitrekhc.csv',
            'yekhighmatur.csv',
            'yeknotbesmaturlu.csv',
            'yeknotcefilliquid.csv',
            'yeknottitrekhc.csv',
            'yekrumoreddanger.csv',
            'yeksalakilliquid.csv',
            'yekshitremhc.csv'
        ]
        
        all_data = []
        unique_tickers = set()
        
        for csv_file in csv_files:
            try:
                if os.path.exists(csv_file):
                    df = pd.read_csv(csv_file)
                    print(f"  {csv_file}: {len(df)} satır okundu")
                    
                    for _, row in df.iterrows():
                        ticker = row.get('PREF IBKR', '')
                        if ticker and ticker not in unique_tickers:
                            unique_tickers.add(ticker)
                            all_data.append(row.to_dict())
                else:
                    print(f"  ERROR: {csv_file} dosyası bulunamadı")
                    
            except Exception as e:
                print(f"  ERROR: {csv_file} okuma hatası: {e}")
        
        if all_data:
            # DataFrame oluştur
            collected_df = pd.DataFrame(all_data)
            
            # ncollected.csv'ye kaydet
            collected_df.to_csv('ncollected.csv', index=False, encoding='utf-8')
            
            print(f"\nSUCCESS: ncollected.csv oluşturuldu!")
            print(f"  Toplam {len(collected_df)} unique hisse")
            print(f"  Toplam {len(collected_df.columns)} kolon")
            
        else:
            print("ERROR: Hiç veri toplanamadı!")
            
    except Exception as e:
        print(f"ERROR: CSV toplama hatası: {e}")

def create_competition_priority():
    """
    Competition priority analizi yapar - 0.2 cent farkı ile
    """
    try:
        print("=== Competition Priority Analizi (0.2 cent farkı) ===")
        
        if not os.path.exists('ncollected.csv'):
            print("ERROR: ncollected.csv dosyası bulunamadı!")
            return
        
        # ncollected.csv'yi oku
        df = pd.read_csv('ncollected.csv')
        
        # Competition priority analizi
        competition_data = []
        
        for _, row in df.iterrows():
            ticker = row.get('PREF IBKR', '')
            cmon = row.get('CMON', '')
            div_amount = row.get('DIV AMOUNT', 0)
            
            if ticker and cmon and pd.notna(div_amount):
                # DIV AMOUNT'u float'a çevir
                try:
                    div_amount_float = float(div_amount)
                except:
                    div_amount_float = 0
                
                # Aynı CMON'dan 0.2 cent daha yüksek div amount ödeyen hisse sayısını hesapla
                higher_payers = 0
                
                for _, other_row in df.iterrows():
                    other_cmon = other_row.get('CMON', '')
                    other_div_amount = other_row.get('DIV AMOUNT', 0)
                    
                    # Other DIV AMOUNT'u float'a çevir
                    try:
                        other_div_amount_float = float(other_div_amount)
                    except:
                        other_div_amount_float = 0
                    
                    if (other_cmon == cmon and 
                        pd.notna(other_div_amount_float) and 
                        other_div_amount_float > div_amount_float + 0.017 and  # 0.017 cent farkı
                        other_div_amount_float != div_amount_float and  # Aynı değil
                        other_row.get('PREF IBKR', '') != ticker):  # Aynı ticker değil
                        higher_payers += 1
                
                competition_data.append({
                    'PREF IBKR': ticker,
                    'CMON': cmon,
                    'DIV AMOUNT': div_amount,
                    'NCOMP Count': higher_payers
                })
        
        if competition_data:
            # DataFrame oluştur
            comp_df = pd.DataFrame(competition_data)
            
            # ncomppriority.csv'ye kaydet
            comp_df.to_csv('ncomppriority.csv', index=False, encoding='utf-8')
            
            print(f"\nSUCCESS: ncomppriority.csv oluşturuldu!")
            print(f"  Toplam {len(comp_df)} hisse analiz edildi")
            print(f"  0.2 cent farkı ile hesaplandı")
            
            # Örnek sonuçları göster
            print("\nÖrnek sonuçlar:")
            sample_df = comp_df.head(10)
            print(sample_df[['PREF IBKR', 'CMON', 'DIV AMOUNT', 'NCOMP Count']].to_string(index=False))
            
        else:
            print("ERROR: Competition analizi yapılamadı!")
            
    except Exception as e:
        print(f"ERROR: Competition priority hatası: {e}")

def add_ncomp_to_yek_files():
    """
    ncomppriority.csv'den NCOMP Count verilerini alıp yek*.csv dosyalarına ekler
    """
    try:
        print("\n=== NCOMP Count Verilerini YEK Dosyalarına Ekleme ===")
        
        if not os.path.exists('ncomppriority.csv'):
            print("ERROR: ncomppriority.csv dosyası bulunamadı!")
            return
        
        # ncomppriority.csv'yi oku
        ncomp_df = pd.read_csv('ncomppriority.csv')
        # Kolon adlarını normalize et
        ncomp_df.columns = [c.strip().lower() for c in ncomp_df.columns]
        # 'ncomp count' kolonunu bul
        ncomp_count_col = [c for c in ncomp_df.columns if c.replace(' ', '') == 'ncompcount']
        if ncomp_count_col:
            ncomp_count_col = ncomp_count_col[0]
        else:
            print('ERROR: ncomppriority.csv dosyasında NCOMP Count kolonu bulunamadı!')
            return
        # PREF IBKR kolonunu da normalize et
        ncomp_df['pref ibkr'] = ncomp_df['pref ibkr'].astype(str).str.strip()
        # YEK dosyalarını bul
        yek_files = glob.glob('yek*.csv')
        print(f"Bulunan YEK dosyaları: {len(yek_files)}")
        for yek_file in yek_files:
            try:
                print(f"\nİşleniyor: {yek_file}")
                yek_df = pd.read_csv(yek_file)
                
                # Eski NCOMP Count kolonlarını temizle
                ncomp_cols = [col for col in yek_df.columns if 'NCOMP Count' in col]
                if ncomp_cols:
                    yek_df = yek_df.drop(columns=ncomp_cols)
                    print(f"  Eski NCOMP Count kolonları temizlendi: {ncomp_cols}")
                
                if 'PREF IBKR' in yek_df.columns:
                    yek_df['PREF IBKR'] = yek_df['PREF IBKR'].astype(str).str.strip()
                # Merge
                yek_df = yek_df.merge(
                    ncomp_df[['pref ibkr', ncomp_count_col]].rename(columns={'pref ibkr': 'PREF IBKR', ncomp_count_col: 'NCOMP Count'}),
                    on='PREF IBKR', how='left')
                # Eğer 'NCOMP Count' kolonu oluşmadıysa elle ekle
                if 'NCOMP Count' not in yek_df.columns:
                    yek_df['NCOMP Count'] = 0
                yek_df['NCOMP Count'] = pd.to_numeric(yek_df['NCOMP Count'], errors='coerce').fillna(0).astype(int)
                yek_df.to_csv(yek_file, index=False, encoding='utf-8')
                print(f"  SUCCESS: {yek_file} güncellendi")
                print(f"  NCOMP Count eklendi: {yek_df['NCOMP Count'].notna().sum()}/{len(yek_df)} hisse")
            except Exception as e:
                print(f"  ERROR: {yek_file} işleme hatası: {e}")
        
        print(f"\nSUCCESS: Tüm YEK dosyaları güncellendi!")
        
    except Exception as e:
        print(f"ERROR: NCOMP ekleme hatası: {e}")

def calculate_cally_values():
    """
    Yek dosyalarında Cally değerlerini hesaplar
    Div adj.price kolonunu kullanır
    """
    try:
        print("\n=== Cally Değerleri Hesaplama ===")
        
        # Sadece ana dizindeki yek dosyalarını bul (alt dizinlerdeki değil)
        yek_files = []
        current_dir = os.getcwd()
        for file in os.listdir(current_dir):
            if file.startswith('yek') and file.endswith('.csv'):
                # Dosya ana dizinde mi kontrol et
                file_path = os.path.join(current_dir, file)
                if os.path.isfile(file_path) and not os.path.dirname(file_path).endswith(('janall', 'janallw', 'janall_backup')):
                    yek_files.append(file)
        
        print(f"Bulunan yek dosyaları (sadece ana dizinden): {len(yek_files)} adet")
        
        for yek_file in yek_files:
            try:
                print(f"\n=== {yek_file} işleniyor ===")
                
                # Dosyayı oku
                df = pd.read_csv(yek_file)
                print(f"✓ {yek_file} yüklendi: {len(df)} satır")
                
                # Kolon isimlerini kontrol et
                print(f"Mevcut kolonlar: {list(df.columns)}")
                
                # Gerekli kolonları bul
                coupon_col = None
                div_adj_price_col = None
                
                # Coupon kolonunu bul
                for col in df.columns:
                    if 'coupon' in col.lower():
                        coupon_col = col
                        break
                
                # Div adj.price kolonunu bul
                for col in df.columns:
                    if 'div' in col.lower() and 'adj' in col.lower() and 'price' in col.lower():
                        div_adj_price_col = col
                        break
                
                print(f"Coupon kolonu: {coupon_col}")
                print(f"Div adj.price kolonu: {div_adj_price_col}")
                
                if coupon_col and div_adj_price_col:
                    # Settlement date olarak bugün kullan, maturity date olarak farklı vadeler
                    settlement_date = datetime.now()
                    maturity_date_2y = settlement_date.replace(year=settlement_date.year + 2)
                    maturity_date_5y = settlement_date.replace(year=settlement_date.year + 5)
                    maturity_date_7y = settlement_date.replace(year=settlement_date.year + 7)
                    maturity_date_10y = settlement_date.replace(year=settlement_date.year + 10)
                    maturity_date_15y = settlement_date.replace(year=settlement_date.year + 15)
                    maturity_date_20y = settlement_date.replace(year=settlement_date.year + 20)
                    maturity_date_30y = settlement_date.replace(year=settlement_date.year + 30)
                    
                    print(f"Settlement date (bugün): {settlement_date.strftime('%Y-%m-%d')}")
                    print(f"Maturity dates: 2Y={maturity_date_2y.strftime('%Y-%m-%d')}, 5Y={maturity_date_5y.strftime('%Y-%m-%d')}, 7Y={maturity_date_7y.strftime('%Y-%m-%d')}, 10Y={maturity_date_10y.strftime('%Y-%m-%d')}, 15Y={maturity_date_15y.strftime('%Y-%m-%d')}, 20Y={maturity_date_20y.strftime('%Y-%m-%d')}, 30Y={maturity_date_30y.strftime('%Y-%m-%d')}")
                    
                    # Her hisse için YIELD hesapla
                    for idx, row in df.iterrows():
                        try:
                            coupon_rate = row[coupon_col]
                            div_adj_price = row[div_adj_price_col]
                            
                            # 2Y Cally hesapla
                            yield_2y = calculate_yield(settlement_date, maturity_date_2y, coupon_rate, div_adj_price)
                            df.at[idx, '2Y Cally'] = yield_2y if not pd.isna(yield_2y) else ''
                            
                            # 5Y Cally hesapla
                            yield_5y = calculate_yield(settlement_date, maturity_date_5y, coupon_rate, div_adj_price)
                            df.at[idx, '5Y Cally'] = yield_5y if not pd.isna(yield_5y) else ''
                            
                            # 7Y Cally hesapla
                            yield_7y = calculate_yield(settlement_date, maturity_date_7y, coupon_rate, div_adj_price)
                            df.at[idx, '7Y Cally'] = yield_7y if not pd.isna(yield_7y) else ''
                            
                            # 10Y Cally hesapla
                            yield_10y = calculate_yield(settlement_date, maturity_date_10y, coupon_rate, div_adj_price)
                            df.at[idx, '10Y Cally'] = yield_10y if not pd.isna(yield_10y) else ''
                            
                            # 15Y Cally hesapla
                            yield_15y = calculate_yield(settlement_date, maturity_date_15y, coupon_rate, div_adj_price)
                            df.at[idx, '15Y Cally'] = yield_15y if not pd.isna(yield_15y) else ''
                            
                            # 20Y Cally hesapla
                            yield_20y = calculate_yield(settlement_date, maturity_date_20y, coupon_rate, div_adj_price)
                            df.at[idx, '20Y Cally'] = yield_20y if not pd.isna(yield_20y) else ''
                            
                            # 30Y Cally hesapla
                            yield_30y = calculate_yield(settlement_date, maturity_date_30y, coupon_rate, div_adj_price)
                            df.at[idx, '30Y Cally'] = yield_30y if not pd.isna(yield_30y) else ''
                                
                            print(f"  {row.get('PREF IBKR', f'Row {idx}')}: 2Y={yield_2y if not pd.isna(yield_2y) else 'N/A'}, 5Y={yield_5y if not pd.isna(yield_5y) else 'N/A'}, 7Y={yield_7y if not pd.isna(yield_7y) else 'N/A'}, 10Y={yield_10y if not pd.isna(yield_10y) else 'N/A'}, 15Y={yield_15y if not pd.isna(yield_15y) else 'N/A'}, 20Y={yield_20y if not pd.isna(yield_20y) else 'N/A'}, 30Y={yield_30y if not pd.isna(yield_30y) else 'N/A'}")
                            
                        except Exception as e:
                            print(f"  Hata (Row {idx}): {e}")
                    
                    # Dosyayı kaydet
                    df.to_csv(yek_file, index=False, encoding='utf-8-sig')
                    print(f"✓ {yek_file} güncellendi")
                    
                else:
                    print(f"! Gerekli kolonlar bulunamadı")
                
            except Exception as e:
                print(f"! {yek_file} işlenirken hata: {e}")
        
        print(f"\n✓ Tüm yek dosyaları işlendi!")
        
    except Exception as e:
        print(f"Genel hata: {e}")

def main():
    """Ana fonksiyon"""
    print("=== YIELD HESAPLAMA VE TREASURY YIELD EKLEME ===")
    print("⚠️  SADECE ANA DİZİNDEKİ (StockTracker) DOSYALAR KULLANILACAK!")
    print("⚠️  Alt dizinlerdeki (janall, janallw, vb.) dosyalar kullanılmayacak!")
    
    check_yek_files()
    collect_csv_files()
    create_competition_priority()
    add_ncomp_to_yek_files()
    calculate_cally_values()  # Cally değerlerini hesapla

if __name__ == '__main__':
    main() 