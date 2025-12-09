import json
from ib_insync import IB, Stock
import pandas as pd
import time
from ibkrtry_checkpoint import CheckpointManager
from datetime import datetime, timedelta
import math
import os

def normalize_time_to_div(time_to_div):
    """
    TIME TO DIV değerini 90 günlük mod sistemi ile normalize eder
    0-90 arası çıktı verir, 0 yerine 90 yazar
    """
    if pd.isna(time_to_div) or time_to_div == '':
        return 90
    
    try:
        time_to_div = float(time_to_div)
        
        # 90 günlük mod al
        normalized = time_to_div % 90
        
        # 0 ise 90 yap
        if normalized == 0:
            return 90
        
        return normalized
        
    except (ValueError, TypeError):
        return 90

def load_csv_files():
    """Belirtilen CSV dosyalarını yükle"""
    csv_files = [
        'ekheldbesmaturlu.csv',
        'ekheldcilizyeniyedi.csv', 
        'ekheldcommonsuz.csv',
        'ekhelddeznff.csv',
        'ekheldff.csv',
        'ekheldflr.csv',
        'ekheldgarabetaltiyedi.csv',
        'ekheldkuponlu.csv',
        'ekheldkuponlukreciliz.csv',
        'ekheldkuponlukreorta.csv',
        'ekheldnff.csv',
        'ekheldotelremorta.csv',
        'ekheldsolidbig.csv',
        'ekheldtitrekhc.csv',
        'ekhighmatur.csv',
        'eknotbesmaturlu.csv',
        'eknotcefilliquid.csv',
        'eknottitrekhc.csv',
        'ekrumoreddanger.csv',
        
        'eksalakilliquid.csv',
        'ekshitremhc.csv'
    ]
    
    loaded_files = {}
    
    for csv_file in csv_files:
        try:
            if os.path.exists(csv_file):
                df = pd.read_csv(csv_file)
                print(f"✓ {csv_file} yüklendi: {len(df)} satır")
                loaded_files[csv_file] = df
            else:
                print(f"! {csv_file} dosyası bulunamadı")
        except Exception as e:
            print(f"! {csv_file} yüklenirken hata: {e}")
    
    return loaded_files

def get_qualified_contract(ticker, ib):
    """Otomatik exchange tanımı yapan fonksiyon"""
    try:
        base_contract = Stock(symbol=ticker, exchange='SMART', currency='USD')
        details = ib.reqContractDetails(base_contract)
        time.sleep(1.0)  # API rate limiting
        if details:
            return details[0].contract
        else:
            print(f"{ticker}: Contract details alınamadı")
            return None
    except Exception as e:
        print(f"{ticker} için hata: {e}")
        return None

def update_price_data(df, ib):
    """Son fiyatları ve tüm teknik verileri güncelle"""
    
    # Gerekli kolonları kontrol et ve yoksa oluştur
    required_columns = [
        'Last Price', 'Oct19_diff', 'Aug2022_diff',
        'SMA20', 'SMA63', 'SMA246', 'SMA20 chg', 'SMA63 chg', 'SMA246 chg',
        '3M Low', '3M High', '6M Low', '6M High', '1Y Low', '1Y High'
    ]
    
    for col in required_columns:
        if col not in df.columns:
            df[col] = None
            print(f"'{col}' kolonu oluşturuldu")
    
    print(f"Toplam {len(df)} hisse işlenecek...")
    
    for idx, row in df.iterrows():
        ticker = row['PREF IBKR']
        print(f"\n[{idx+1}/{len(df)}] {ticker} işleniyor...")
        
        try:
            contract = get_qualified_contract(ticker, ib)
            if contract is None:
                print(f"! {ticker} için contract alınamadı, atlanıyor...")
                continue

            print(f"  Contract alındı: {contract}")
            
            # Historical data çek - timeout ve duration ayarları
            try:
                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr='2 Y',  # 2 yıllık veri (SMA246 için gerekli)
                    barSizeSetting='1 day',
                    whatToShow='TRADES',
                    useRTH=True,
                    timeout=20  # 20 saniye timeout
                )
                print(f"  Historical data çekildi: {len(bars) if bars else 0} bar")
            except Exception as hist_error:
                print(f"! {ticker} historical data hatası: {hist_error}")
                time.sleep(2.0)  # Hatalarda daha uzun bekle
                continue
            
            if bars and len(bars) > 0:
                # DataFrame'e çevir ve close değerlerini numeric yap
                bars_df = pd.DataFrame(bars)
                bars_df['close'] = pd.to_numeric(bars_df['close'], errors='coerce')
                
                last_price = float(bars_df['close'].iloc[-1])
                df.at[idx, 'Last Price'] = f"{last_price:.2f}"
                print(f"  Last Price: {last_price:.2f}")
                
                # SMA hesaplamaları - yeni değerler: 20, 63, 246
                if len(bars_df) >= 246:  # En az 246 gün veri gerekli
                    try:
                        # SMA değerlerini hesapla
                        sma20 = float(bars_df['close'].rolling(window=20).mean().iloc[-1])
                        sma63 = float(bars_df['close'].rolling(window=63).mean().iloc[-1])
                        sma246 = float(bars_df['close'].rolling(window=246).mean().iloc[-1])
                        
                        # SMA değerlerini kaydet
                        df.at[idx, 'SMA20'] = f"{sma20:.2f}"
                        df.at[idx, 'SMA63'] = f"{sma63:.2f}"
                        df.at[idx, 'SMA246'] = f"{sma246:.2f}"
                        
                        # Div adj.price hesapla (eğer temettü bilgisi varsa)
                        div_adj_price = last_price  # Varsayılan olarak last_price
                        if pd.notnull(row.get('DIV AMOUNT')) and pd.notnull(row.get('EX-DIV DATE')):
                            try:
                                # Ex-Div tarihini parse et
                                ex_div_date = datetime.strptime(row['EX-DIV DATE'], '%m/%d/%Y')
                                today = datetime.now()
                                
                                # 90 günlük döngüleri ekleyerek bir sonraki ex-div tarihini bul
                                next_div_date = ex_div_date
                                while next_div_date <= today:
                                    next_div_date += timedelta(days=90)
                                    
                                # Kalan gün sayısını hesapla
                                days_until_div = (next_div_date - today).days
                                
                                # TIME TO DIV'i 90 günlük mod sistemi ile normalize et
                                normalized_time_to_div = days_until_div % 90
                                if normalized_time_to_div == 0:
                                    normalized_time_to_div = 90
                                
                                # TIME TO DIV kolonunu güncelle
                                df.at[idx, 'TIME TO DIV'] = normalized_time_to_div
                                
                                # Div adj.price hesapla (normalize edilmiş TIME TO DIV ile)
                                div_amount = float(row['DIV AMOUNT'])
                                days_factor = (90 - normalized_time_to_div) / 90
                                div_adj_price = last_price - (days_factor * div_amount)
                                
                                # Div adj.price kolonunu güncelle
                                df.at[idx, 'Div adj.price'] = f"{div_adj_price:.2f}"
                                
                                print(f"  TIME TO DIV: {days_until_div} → {normalized_time_to_div} (mod 90)")
                                print(f"  Div adj.price hesaplandı: {div_adj_price:.2f} (Last: {last_price:.2f})")
                            except Exception as e:
                                print(f"  ! Div adj.price hesaplama hatası: {str(e)}")
                        
                        # SMA değişim yüzdelerini div adj.price ile hesapla
                        sma20_chg = ((div_adj_price - sma20) / sma20) * 100
                        sma63_chg = ((div_adj_price - sma63) / sma63) * 100
                        sma246_chg = ((div_adj_price - sma246) / sma246) * 100
                        
                        df.at[idx, 'SMA20 chg'] = f"{sma20_chg:.2f}"
                        df.at[idx, 'SMA63 chg'] = f"{sma63_chg:.2f}"
                        df.at[idx, 'SMA246 chg'] = f"{sma246_chg:.2f}"
                        
                        print(f"  ✓ SMA değerleri (div adj): SMA20={sma20:.2f}, SMA63={sma63:.2f}, SMA246={sma246:.2f}")
                        print(f"  ✓ SMA değişimleri div adj.price ile hesaplandı")
                    except Exception as e:
                        print(f"  ! SMA hesaplama hatası: {str(e)}")
                else:
                    print(f"  ! Yeterli veri yok (Mevcut: {len(bars_df)}, Gerekli: 246)")
                
                # 6 aylık high/low hesaplamaları
                six_month_data = bars_df.tail(180)  # Son 6 ay
                if not six_month_data.empty:
                    six_month_high = six_month_data['high'].max()
                    six_month_low = six_month_data['low'].min()
                    df.at[idx, '6M High'] = f"{six_month_high:.2f}"
                    df.at[idx, '6M Low'] = f"{six_month_low:.2f}"
                    print(f"  6M High/Low: {six_month_high:.2f}/{six_month_low:.2f}")
                
                # 3 aylık high/low hesaplamaları
                three_month_data = bars_df.tail(90)  # Son 3 ay
                if not three_month_data.empty:
                    three_month_high = three_month_data['high'].max()
                    three_month_low = three_month_data['low'].min()
                    df.at[idx, '3M High'] = f"{three_month_high:.2f}"
                    df.at[idx, '3M Low'] = f"{three_month_low:.2f}"
                    print(f"  3M High/Low: {three_month_high:.2f}/{three_month_low:.2f}")
                
                # 1 yıllık high/low hesaplamaları
                year_high = bars_df['high'].max()
                year_low = bars_df['low'].min()
                df.at[idx, '1Y High'] = f"{year_high:.2f}"
                df.at[idx, '1Y Low'] = f"{year_low:.2f}"
                print(f"  1Y High/Low: {year_high:.2f}/{year_low:.2f}")
                
                # Aug2022 ve Oct19 farkları
                if pd.notnull(row.get('Aug2022_Price')):
                    df.at[idx, 'Aug2022_diff'] = f"{(last_price - float(row['Aug2022_Price'])):.2f}"
                if pd.notnull(row.get('Oct19_Price')):
                    df.at[idx, 'Oct19_diff'] = f"{(last_price - float(row['Oct19_Price'])):.2f}"
                
                print(f"  ✓ {ticker} için tüm veriler güncellendi")
            else:
                print(f"  ! {ticker} için veri alınamadı")
            
            # Her hisse sonrası uzun bekle
            time.sleep(2.0)  # Rate limiting artırıldı
            
        except Exception as e:
            print(f"  ! {ticker} için genel hata: {str(e)}")
            time.sleep(3.0)  # Hatalarda daha uzun bekle
            continue
    
    return df

def calculate_div_metrics(df):
    """Temettü gününe kalan süreyi ve düzeltilmiş fiyatı hesapla"""
    # Gerekli kolonları kontrol et ve yoksa oluştur
    if 'TIME TO DIV' not in df.columns:
        df['TIME TO DIV'] = None
    if 'Div adj.price' not in df.columns:
        df['Div adj.price'] = None
    
    # Bugünün tarihi
    today = datetime.now()
    
    for idx, row in df.iterrows():
        try:
            # EX-DIV DATE kolonunu kontrol et
            if pd.isna(row['EX-DIV DATE']) or not row['EX-DIV DATE']:
                continue
            
            # DIV AMOUNT kontrolü
            if pd.isna(row.get('DIV AMOUNT')) or not row.get('DIV AMOUNT'):
                continue
                
            # Last Price kontrolü
            if pd.isna(row.get('Last Price')) or not row.get('Last Price'):
                continue
                
            # Ex-Div tarihini parse et
            try:
                ex_div_date = datetime.strptime(row['EX-DIV DATE'], '%m/%d/%Y')
            except ValueError:
                print(f"! Tarih format hatası: {row['EX-DIV DATE']} (hisse: {row['PREF IBKR']})")
                continue
                
            # 90 günlük döngüleri ekleyerek bir sonraki ex-div tarihini bul
            next_div_date = ex_div_date
            while next_div_date <= today:
                next_div_date += timedelta(days=90)
                
            # Kalan gün sayısını hesapla
            days_until_div = (next_div_date - today).days
            
            # TIME TO DIV değerini 90 günlük mod sistemi ile normalize et
            normalized_days = normalize_time_to_div(days_until_div)
            df.at[idx, 'TIME TO DIV'] = normalized_days
            
            # Div adj.price hesapla (normalize edilmiş TIME TO DIV ile)
            # Div adj.price = Last price - (((90-Time to Div)/90)*DIV AMOUNT)
            try:
                last_price = float(row['Last Price'])
                div_amount = float(row['DIV AMOUNT'])
                
                days_factor = (90 - normalized_days) / 90
                div_adj_price = last_price - (days_factor * div_amount)
                df.at[idx, 'Div adj.price'] = f"{div_adj_price:.2f}"
                
                if days_until_div != normalized_days:
                    print(f"✓ {row['PREF IBKR']} için temettü hesaplandı: TIME TO DIV={days_until_div}→{normalized_days}, Div adj.price={div_adj_price:.2f}")
                else:
                    print(f"✓ {row['PREF IBKR']} için temettü hesaplandı: TIME TO DIV={normalized_days}, Div adj.price={div_adj_price:.2f}")
            except Exception as e:
                print(f"! {row['PREF IBKR']} için div_adj_price hesaplama hatası: {str(e)}")
        except Exception as e:
            print(f"! {row.get('PREF IBKR', 'Bilinmeyen hisse')} temettü hesaplama hatası: {str(e)}")
    
    return df

def process_csv_files(loaded_files, ib):
    """Tüm CSV dosyalarını işle ve yeni dosyalar oluştur"""
    
    for original_filename, df in loaded_files.items():
        if df.empty:
            print(f"! {original_filename} boş, atlanıyor...")
            continue
            
        print(f"\n=== {original_filename} işleniyor ({len(df)} hisse) ===")
        
        try:
            # Fiyat verilerini güncelle
            df = update_price_data(df, ib)
            
            # Temettü metriklerini hesapla
            df = calculate_div_metrics(df)
            
            # Yeni dosya adını oluştur (başına 's' ekle)
            new_filename = 's' + original_filename
            
            # Dosyayı kaydet
            df.to_csv(new_filename, 
                     index=False,
                     float_format='%.2f',
                     sep=',',
                     encoding='utf-8-sig')
            
            print(f"✓ {new_filename} dosyasına kaydedildi ({len(df)} hisse)")
            
        except Exception as e:
            print(f"! {original_filename} işlenirken hata: {str(e)}")
            continue

def main():
    # IB bağlantı testi
    ib = IB()
    try:
        print("IBKR bağlantı testi başlıyor...")
        ib.connect('127.0.0.1', 4001, clientId=2981, timeout=20)
        print("Bağlantı başarılı!")
        print(f"TWS versiyon: {ib.client.serverVersion()}")
        print(f"Bağlantı durumu: {ib.isConnected()}")
        
        # Market data subscription kontrolü
        print("Market data abonelik durumu kontrol ediliyor...")
        
        # Basit bir API çağrısı yap
        try:
            accounts = ib.reqAccountSummary()
            print(f"Hesap sayısı: {len(accounts)}")
        except Exception as acc_error:
            print(f"Hesap bilgisi hatası: {acc_error}")
        
    except Exception as e:
        print(f"Bağlantı hatası: {e}")
        return
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("Test bağlantısı kapatıldı")
    
    # CSV dosyalarını yükle
    loaded_files = load_csv_files()
    
    if not loaded_files:
        print("Hiçbir CSV dosyası bulunamadı!")
        return
    
    # IB bağlantısı - ana işlem için
    ib = IB()
    try:
        print("\nAna işlem için IBKR'ye bağlanılıyor...")
        ib.connect('127.0.0.1', 4001, clientId=2982, timeout=20)  # Farklı clientId
        ib.reqMarketDataType(1)  # Real-time market data
        print("Ana bağlantı başarılı!")
        
        # Tüm CSV dosyalarını işle
        process_csv_files(loaded_files, ib)
        
        print(f"\n✓ Tüm dosyalar işlendi ve yeni dosyalar oluşturuldu.")
        
    except Exception as e:
        print(f"Ana işlem hatası: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("TWS bağlantısı kapatıldı")

if __name__ == "__main__":
    main()
