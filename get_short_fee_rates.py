import pandas as pd
import numpy as np
import time
import os
from ib_insync import IB, Stock, util
import sys
import datetime

def connect_to_ibkr():
    """IBKR'ye bağlanır"""
    print("IBKR bağlantısı kuruluyor...")
    ib = IB()
    
    # TWS ve Gateway portlarını dene, öncelik TWS'de olsun
    ports = [7496, 4001]  # TWS ve Gateway portları
    connected = False
    
    for port in ports:
        try:
            service_name = "TWS" if port == 7496 else "Gateway"
            print(f"{service_name} ({port}) bağlantı deneniyor...")
            
            ib.connect('127.0.0.1', port, clientId=1, readonly=True, timeout=20)
            connected = True
            print(f"{service_name} ({port}) ile bağlantı başarılı!")
            break
        except Exception as e:
            print(f"{service_name} ({port}) bağlantı hatası: {e}")
    
    if not connected:
        print("IBKR bağlantısı kurulamadı! TWS veya Gateway çalışıyor mu?")
        sys.exit(1)
    
    return ib

def get_fee_rate(ib, symbol):
    """Bir hisse için fee rate (SMI) değerini alır"""
    try:
        contract = Stock(symbol, 'SMART', 'USD')
        
        # Sözleşmeyi detaylandır
        qualified_contracts = ib.qualifyContracts(contract)
        if not qualified_contracts:
            print(f"⚠️ {symbol} için kontrat detaylandırılamadı")
            return np.nan
        
        contract = qualified_contracts[0]
        
        # YÖNTEM 0: reqHistoricalData ile FEE_RATE verisi çekme (Birincil Yöntem)
        try:
            # Gecikmeli veri isteği
            ib.reqMarketDataType(3)  # Delayed data
            
            # FEE_RATE verisi çek
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',  # Bugün
                durationStr='1 W',  # Son 1 hafta
                barSizeSetting='4 hours',  # 4 saatlik çubuklar
                whatToShow='FEE_RATE',  # Fee Rate verisi
                useRTH=True  # Regular Trading Hours
            )
            
            # Veriyi pandas df'e dönüştür
            if bars and len(bars) > 0:
                df = util.df(bars)
                # En son fee rate değerini al
                fee_rate = df.tail(1)["close"].reset_index(drop=True)[0]
                if not np.isnan(fee_rate) and fee_rate > 0:
                    return fee_rate
        except Exception as e:
            print(f"Yöntem 0 (FEE_RATE) hata: {e}")
        
        # YÖNTEM 1: SecDefOptParams kullanarak fee rate alma
        try:
            short_info = ib.reqSecDefOptParams(
                underlyingSymbol=contract.symbol,
                futFopExchange='',
                underlyingSecType=contract.secType,
                underlyingConId=contract.conId
            )
            
            if short_info and len(short_info) > 0:
                fee_rate = short_info[0].stockType
                
                if isinstance(fee_rate, str) and fee_rate.strip():
                    # Rakamsal olmayan karakterleri kaldır (%, bps gibi)
                    fee_rate = ''.join(c for c in fee_rate if c.isdigit() or c in '.-')
                    if fee_rate:
                        return float(fee_rate)
        except Exception as e:
            print(f"Yöntem 1 hata: {e}")
        
        # YÖNTEM 2: reqContractDetails kullanarak fee rate alma
        try:
            details = ib.reqContractDetails(contract)
            if details and len(details) > 0:
                # shortableShares özelliği ile ilgili bilgiyi kontrol et
                shortable = details[0].shortableShares
                if shortable is not None and shortable > 0:
                    # shortableShares miktarını bir değere dönüştür
                    # 0-100 arasında bir değere normalize et
                    shortable_pct = min(100, max(0, shortable / 10000))
                    # Düşük shortable = yüksek fee rate ilişkisi
                    return 3.0 * (1.0 - shortable_pct/100)  # 0-3% arasında bir değer
        except Exception as e:
            print(f"Yöntem 2 hata: {e}")
            
        # YÖNTEM 3: Sözleşme piyasa verilerini kullan
        try:
            ib.reqMarketDataType(3)  # Delayed data
            ticker = ib.reqMktData(contract, '', False, False)
            time.sleep(1)  # Verilerin gelmesi için bekle
            
            # shortableShares veya shortableLastPrice verilerini kontrol et
            if hasattr(ticker, 'shortableShares') and ticker.shortableShares > 0:
                shortable_pct = min(100, max(0, ticker.shortableShares / 10000))
                return 3.0 * (1.0 - shortable_pct/100)
        except Exception as e:
            print(f"Yöntem 3 hata: {e}")
        
        print(f"⚠️ {symbol} için fee rate bilgisi alınamadı")
        return np.nan
    
    except Exception as e:
        print(f"❌ {symbol} fee rate hatası: {e}")
        return np.nan

def process_all_symbols(ib, input_files):
    """Tüm sembolleri işler ve SMI değerlerini toplar"""
    print(f"\n{'-'*50}")
    print("TÜM SEMBOLLER İŞLENİYOR")
    print(f"{'-'*50}")
    
    all_symbols = set()
    results = []
    
    # Tüm dosyalardan benzersiz sembolleri topla
    for input_file in input_files:
        try:
            df = pd.read_csv(input_file)
            if "PREF IBKR" in df.columns:
                symbols = df["PREF IBKR"].dropna().unique().tolist()
                all_symbols.update(symbols)
                print(f"{input_file}: {len(symbols)} sembol bulundu")
            else:
                print(f"HATA: {input_file} dosyasında 'PREF IBKR' kolonu bulunamadı!")
        except Exception as e:
            print(f"HATA: {input_file} dosyası okunamadı: {e}")
    
    print(f"\nToplam {len(all_symbols)} benzersiz sembol bulundu")
    
    # API limit aşımını önlemek için batch işlem
    batch_size = 30  # Bir seferde işlenecek hisse sayısı
    delay_seconds = 10  # Her batch sonrası beklenecek süre
    
    for i, symbol in enumerate(sorted(all_symbols)):
        # Batch işlem kontrolü
        if i > 0 and i % batch_size == 0:
            print(f"\nAPI limit aşımını önlemek için {delay_seconds} saniye bekleniyor (Batch: {i//batch_size})...")
            time.sleep(delay_seconds)
        
        print(f"[{i+1}/{len(all_symbols)}] {symbol} işleniyor... ", end="", flush=True)
        fee_rate = get_fee_rate(ib, symbol)
        
        results.append({
            "PREF IBKR": symbol,
            "SMI": fee_rate
        })
        
        # Sonucu yazdır
        if np.isnan(fee_rate):
            print("❌ Alınamadı")
        else:
            print(f"✅ {fee_rate:.2f}%")
        
        # API limit aşımı olmaması için her 5 hissede bir kısa bekleme
        if i % 5 == 0 and i > 0 and i % batch_size != 0:
            print(f"API limit aşımını önlemek için 3 saniye bekleniyor...")
            time.sleep(3)
    
    # Sonuçları DataFrame'e dönüştür
    result_df = pd.DataFrame(results)
    
    # NaN değerlerini işle
    missing_fee_rate = result_df["SMI"].isna().sum()
    if missing_fee_rate > 0:
        print(f"⚠️ {missing_fee_rate} hisse için fee rate bilgisi alınamadı!")
        
        # NaN'ları ortalama ile doldur
        mean_fee_rate = result_df["SMI"].mean()
        if not np.isnan(mean_fee_rate):
            result_df["SMI"].fillna(mean_fee_rate, inplace=True)
            print(f"NaN değerler ortalama değer {mean_fee_rate:.2f}% ile dolduruldu")
        else:
            # Ortalama hesaplanamazsa default değer kullan
            result_df["SMI"].fillna(1.0, inplace=True)  # Tipik fee rate = 1%
            print(f"NaN değerler varsayılan değer 1.00% ile dolduruldu")
    
    # SMI değerlerini özetleyelim
    print("\nFEE RATE İSTATİSTİKLERİ:")
    print(f"Min: {result_df['SMI'].min():.2f}%")
    print(f"Max: {result_df['SMI'].max():.2f}%")
    print(f"Ortalama: {result_df['SMI'].mean():.2f}%")
    print(f"Medyan: {result_df['SMI'].median():.2f}%")
    
    return result_df

def main():
    """Ana program"""
    print("Short fee rate verisi çekme işlemi başlatılıyor...")
    
    # İşlenecek dosyalar
    input_files = [
        "mastermind_histport.csv",
        "mastermind_extltport.csv"
    ]
    
    # İlk önce dosyaların var olduğunu kontrol et
    for input_file in input_files:
        if not os.path.exists(input_file):
            print(f"HATA: {input_file} dosyası bulunamadı!")
            sys.exit(1)
    
    # IBKR'ye bağlan
    ib = connect_to_ibkr()
    
    try:
        # Tüm sembolleri işle
        result_df = process_all_symbols(ib, input_files)
        
        # Sonuçları Smiall.csv'ye kaydet
        output_file = "Smiall.csv"
        result_df.to_csv(output_file, index=False)
        print(f"\nSonuçlar '{output_file}' dosyasına kaydedildi.")
        
    except Exception as e:
        print(f"HATA: İşlem sırasında bir sorun oluştu: {e}")
    finally:
        # IBKR bağlantısını kapat
        if ib.isConnected():
            ib.disconnect()
            print("\nIBKR bağlantısı kapatıldı")
    
    print("\nTüm işlemler tamamlandı!")

if __name__ == "__main__":
    main() 