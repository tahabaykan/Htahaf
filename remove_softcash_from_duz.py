import pandas as pd

def remove_softcash_from_duz():
    """nallsoftcash.csv dosyasındaki hisseleri nallsmaduz.csv dosyasından çıkar"""
    
    try:
        # nallsmaduz.csv dosyasını yükle
        duz_df = pd.read_csv('nallsmaduz.csv')
        print(f"nallsmaduz.csv yüklendi: {len(duz_df)} hisse")
        
        # nallsoftcash.csv dosyasını yükle
        softcash_df = pd.read_csv('nallsoftcash.csv')
        print(f"nallsoftcash.csv yüklendi: {len(softcash_df)} hisse")
        
        # nallsoftcash.csv'deki hisseleri al
        softcash_tickers = softcash_df['PREF IBKR'].tolist()
        print(f"\nnallsoftcash.csv'deki hisseler:")
        for i, ticker in enumerate(softcash_tickers, 1):
            print(f"{i:2d}. {ticker}")
        
        # Debug: nallsmaduz.csv'deki ilk birkaç hisseyi göster
        print(f"\nnallsmaduz.csv'deki ilk 5 hisse:")
        for i, ticker in enumerate(duz_df['PREF IBKR'].head(), 1):
            print(f"{i:2d}. {ticker}")
        
        # Her softcash hissesini nallsmaduz.csv'de ara
        found_tickers = []
        for ticker in softcash_tickers:
            if ticker in duz_df['PREF IBKR'].values:
                found_tickers.append(ticker)
                print(f"✓ {ticker} bulundu")
            else:
                print(f"✗ {ticker} bulunamadı")
        
        print(f"\nBulunan hisse sayısı: {len(found_tickers)}")
        
        if found_tickers:
            # nallsmaduz.csv'den bu hisseleri çıkar
            before_removal = len(duz_df)
            duz_df = duz_df[~duz_df['PREF IBKR'].isin(found_tickers)]
            after_removal = len(duz_df)
            
            removed_count = before_removal - after_removal
            print(f"\nÇıkarılan hisse sayısı: {removed_count}")
            print(f"Kalan hisse sayısı: {after_removal}")
            
            print(f"\nÇıkarılan hisseler:")
            for i, ticker in enumerate(found_tickers, 1):
                print(f"{i:2d}. {ticker}")
            
            # Güncellenmiş dosyayı kaydet
            duz_df.to_csv('nallsmaduz.csv', index=False, encoding='utf-8-sig')
            print(f"\n✓ nallsmaduz.csv dosyası güncellendi ({after_removal} hisse)")
        else:
            print("\nHiçbir softcash hissesi nallsmaduz.csv'de bulunamadı!")
        
        return True
        
    except Exception as e:
        print(f"Hata oluştu: {e}")
        return False

if __name__ == "__main__":
    remove_softcash_from_duz() 