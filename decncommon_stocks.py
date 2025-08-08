from ib_insync import IB, Stock
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import os
import sys
# yfinance import removed - using IBKR for prices and Finviz for market cap
import requests
from bs4 import BeautifulSoup
from simulation_helper import get_simulation_filename, is_simulation_mode

# IBKR TWS API'ye bağlan
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=189)  # Farklı bir clientId kullan

# Gecikmeli veri modunu etkinleştir
ib.reqMarketDataType(3)

# İşlenecek CSV dosyaları - nibkrtry.py'den alınan liste
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

print(f"İşlenecek CSV dosyaları: {csv_files}")

def get_qualified_contract(ticker):
    try:
        # Mevcut bağlantıları temizle
        ib.reqGlobalCancel()
        time.sleep(0.5)  # Temizleme için kısa bekleme
        
        base_contract = Stock(symbol=ticker, exchange='SMART', currency='USD')
        details = ib.reqContractDetails(base_contract)
        time.sleep(1)
        if details:
            return details[0].contract
        return None
    except Exception as e:
        print(f"{ticker} için hata: {e}")
        return None

def get_historical_data(contract, duration, endDateTime=''):
    try:
        # Her istek öncesi bekleyen istekleri temizle
        ib.reqGlobalCancel()
        time.sleep(0.5)
        
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=endDateTime,
            durationStr=duration,
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            timeout=5  # Timeout ekle
        )
        return pd.DataFrame(bars) if bars else None
    except Exception as e:
        print(f"Veri çekme hatası: {e}")
        # Hata durumunda tekrar bağlan
        if not ib.isConnected():
            print("Bağlantı koptu, yeniden bağlanılıyor...")
            ib.connect('127.0.0.1', 4001, clientId=189)
            time.sleep(1)
        return None

def get_historical_data_for_date(contract, date_str):
    """Belirli bir tarih için veri çek"""
    try:
        ib.reqGlobalCancel()
        time.sleep(0.5)
        
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=date_str,
            durationStr='1 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            timeout=5
        )
        if bars:
            return bars[0].close
        return None
    except Exception as e:
        print(f"Tarih verisi çekme hatası: {e}")
        return None

def get_market_cap_from_finviz(ticker):
    """Finviz.com'dan market cap değerini çek"""
    try:
        # Finviz URL'si
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        
        # HTTP isteği gönder
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"! {ticker}: Finviz'den veri alınamadı (HTTP {response.status_code})")
            return None
            
        # HTML içeriğini parse et
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Market Cap değerini bul (snapshot tablosunda)
        for table_row in soup.select('table.snapshot-table2 tr'):
            cells = table_row.find_all('td')
            if len(cells) >= 2:
                if "Market Cap" in cells[0].text:
                    market_cap_text = cells[1].text.strip()
                    
                    # Değeri sayısal formata çevir
                    if 'B' in market_cap_text:
                        market_cap = float(market_cap_text.replace('B', ''))
                    elif 'M' in market_cap_text:
                        market_cap = float(market_cap_text.replace('M', '')) / 1000
                    else:
                        try:
                            market_cap = float(market_cap_text) / 1000000000  # Milyar dolara çevir
                        except ValueError:
                            print(f"! {ticker}: Finviz market cap değeri dönüştürülemedi: {market_cap_text}")
                            return None
                            
                    print(f"OK Market Cap bulundu ({ticker}): {market_cap:.2f}B")
                    return market_cap
        
        print(f"! {ticker}: Finviz'de Market Cap bulunamadı")
        return None
        
    except Exception as e:
        print(f"! {ticker} için Finviz market cap verisi alma hatası: {str(e)}")
        return None

def get_last_price_from_ibkr(ticker, contract=None):
    """IBKR Gateway'den last price değerini çek"""
    try:
        # Eğer kontrat verilmediyse yeni bir kontrat oluştur
        if contract is None:
            contract = get_qualified_contract(ticker)
            if not contract:
                print(f"! {ticker}: IBKR kontrat bulunamadı")
                return None
        
        # IBKR'den market verisi iste
        ib.reqMarketDataType(3)  # 3 = Delayed
        
        # Market verisi talebi
        ib.reqMktData(contract, '', False, False)
        
        # Veri gelmesini bekle
        start_time = time.time()
        max_wait = 10  # Maksimum 10 saniye bekle
        
        while time.time() - start_time < max_wait:
            ib.sleep(0.5)  # 0.5 saniye aralıklarla kontrol et
            
            # Veri geldi mi?
            ticker_data = ib.ticker(contract)
            
            # Farklı fiyat kaynaklarını kontrol et
            if ticker_data.last and ticker_data.last > 0:
                price = ticker_data.last
                ib.cancelMktData(contract)
                print(f"OK {ticker}: ${price:.2f} (last)")
                return price
            elif ticker_data.close and ticker_data.close > 0:
                price = ticker_data.close
                ib.cancelMktData(contract)
                print(f"OK {ticker}: ${price:.2f} (close)")
                return price
            
        # Süre doldu, veri alınamadı
        ib.cancelMktData(contract)
        print(f"! {ticker}: IBKR'den fiyat alınamadı (timeout)")
        return None
        
    except Exception as e:
        try:
            ib.cancelMktData(contract)
        except:
            pass
        print(f"! {ticker} için IBKR fiyat verisi alma hatası: {str(e)}")
        return None

def process_csv_file(csv_file):
    """Her CSV dosyasını işle"""
    print(f"\n=== {csv_file} dosyası işleniyor ===")
    
    try:
        # CSV dosyasını oku
        df_main = pd.read_csv(get_simulation_filename(csv_file), encoding='utf-8-sig')
        
        # CMON kolonu var mı kontrol et
        if 'CMON' not in df_main.columns:
            print(f"! {csv_file}: CMON kolonu bulunamadı!")
            return None
        
        # Boş olmayan CMON değerlerini al
        common_tickers = df_main['CMON'].dropna().unique().tolist()
        
        print(f"Toplam {len(common_tickers)} adet common stock bulundu.")
        print("İlk 5 ticker:", common_tickers[:5])
        
        # Sonuçları saklamak için liste
        common_stock_results = []
        
        for idx, ticker in enumerate(common_tickers):
            try:
                print(f"İşleniyor: {ticker} ({idx+1}/{len(common_tickers)})")
                
                # Her 50 işlemde bir bağlantıyı yenile
                if idx > 0 and idx % 50 == 0:
                    print("\nBağlantı yenileniyor...")
                    ib.disconnect()
                    time.sleep(2)
                    ib.connect('127.0.0.1', 4001, clientId=189)
                    time.sleep(1)
                    print("Bağlantı yenilendi.\n")
                
                contract = get_qualified_contract(ticker)
                if not contract:
                    continue
                
                # Son fiyatı IBKR'den, Market Cap'i Finviz'den al
                com_last_price = get_last_price_from_ibkr(ticker, contract)
                market_cap = get_market_cap_from_finviz(ticker)
                
                if com_last_price is None:
                    print(f"! {ticker} için last price alınamadı")
                    continue

                # 1 yıllık veri - IBKR'den
                df_1y = get_historical_data(contract, '1 Y')
                if df_1y is not None:
                    com_52week_low = df_1y['low'].min()
                    com_52week_high = df_1y['high'].max()
                else:
                    com_52week_low = com_52week_high = None

                # 6 ay önceki fiyat - IBKR'den
                six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d 23:59:59')
                df_6m = get_historical_data(contract, '1 D', endDateTime=six_months_ago)
                com_6m_price = df_6m['close'].iloc[0] if df_6m is not None else None

                # 3 ay önceki fiyat - IBKR'den
                three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d 23:59:59')
                df_3m = get_historical_data(contract, '1 D', endDateTime=three_months_ago)
                com_3m_price = df_3m['close'].iloc[0] if df_3m is not None else None

                # 5 yıllık veri - IBKR'den
                df_5y = get_historical_data(contract, '5 Y')
                if df_5y is not None:
                    com_5year_low = df_5y['low'].min()
                    com_5year_high = df_5y['high'].max()
                else:
                    com_5year_low = com_5year_high = None

                # 10 Şubat 2020 fiyatı
                feb_2020_price = get_historical_data_for_date(contract, '20200210 23:59:59')
                
                # 20 Mart 2020 fiyatı
                mar_2020_price = get_historical_data_for_date(contract, '20200320 23:59:59')
                
                # CRDT SCORE'u ana DataFrame'den al
                crdt_score = df_main.loc[df_main['CMON'] == ticker, 'CRDT_SCORE'].iloc[0] if not df_main.empty else None

                # Sonuçları kaydet
                common_stock_results.append({
                    'CMON': ticker,
                    'COM_LAST_PRICE': com_last_price,  # IBKR'den
                    'COM_52W_LOW': com_52week_low,     # IBKR'den
                    'COM_52W_HIGH': com_52week_high,   # IBKR'den
                    'COM_6M_PRICE': com_6m_price,      # IBKR'den
                    'COM_3M_PRICE': com_3m_price,      # IBKR'den
                    'COM_5Y_LOW': com_5year_low,       # IBKR'den
                    'COM_5Y_HIGH': com_5year_high,     # IBKR'den
                    'COM_MKTCAP': market_cap,          # Finviz'den
                    'CRDT_SCORE': crdt_score,          # Ana CSV'den
                    'COM_FEB2020_PRICE': feb_2020_price,
                    'COM_MAR2020_PRICE': mar_2020_price
                })

                time.sleep(1)  # Rate limiting için kısa bekleme

            except Exception as e:
                print(f"{ticker} için hata oluştu: {e}")
                common_stock_results.append({
                    'CMON': ticker,
                    'COM_LAST_PRICE': None,
                    'COM_52W_LOW': None,
                    'COM_52W_HIGH': None,
                    'COM_6M_PRICE': None,
                    'COM_3M_PRICE': None,
                    'COM_5Y_LOW': None,
                    'COM_5Y_HIGH': None,
                    'COM_MKTCAP': None,
                    'CRDT_SCORE': None,
                    'COM_FEB2020_PRICE': None,
                    'COM_MAR2020_PRICE': None
                })
        
        # Sonuçları DataFrame'e çevir
        df_common = pd.DataFrame(common_stock_results)
        
        # Ana DataFrame ile birleştir
        df_final = df_main.merge(df_common, on='CMON', how='left')
        
        # Çıktı dosya adını oluştur (başına "com" ekle)
        output_filename = get_simulation_filename(f"com{csv_file}")
        
        # Sonuçları kaydet
        df_final.to_csv(output_filename, 
                        index=False,
                        sep=',',
                        encoding='utf-8-sig',
                        float_format='%.6f',
                        lineterminator='\n',    
                        quoting=1)  # Tüm değerleri tırnak içine al

        print(f"\nSonuçlar '{output_filename}' dosyasına kaydedildi.")
        
        return df_final
        
    except Exception as e:
        print(f"{csv_file} dosyası işlenirken hata oluştu: {e}")
        return None

# Her CSV dosyasını işle
for csv_file in csv_files:
    process_csv_file(csv_file)

print("\n=== Tüm CSV dosyaları işlendi ===")

# Bağlantıyı kapat
ib.disconnect()