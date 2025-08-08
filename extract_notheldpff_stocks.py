import pandas as pd
import numpy as np

def extract_notheldpff_stocks():
    """
    nalltogether.csv dosyasından belirtilen hisseleri çıkarır
    ve nnotheldpff.csv dosyasına kaydeder
    """
    print("Notheldpff hisseleri çıkarılıyor...")
    
    # Çıkarılacak hisseler listesi
    stocks_to_extract = [
        'ACP PRA', 'AGM PRE', 'BCV PRA', 'BWBBP', 'EFSCP', 'ETI PR', 'ENJ', 'ECF PRA', 'CUBB',
        'GAB PRH', 'GAB PRG', 'GAB PRK', 'GDV PRH', 'GDV PRK', 'GGN PRB', 'GGT PRE', 'GGT PRG',
        'GNT PRA', 'GRBK PRA', 'GUT PRC', 'NCV PRA', 'NCZ PRA', 'OPP PRA', 'OPP PRB', 'RIV PRA',
        'REXR PRB', 'REXR PRC', 'TRTN PRA', 'ALTG PRA', 'AOMN', 'ATLCP', 'BANFP', 'CGBDL', 'CCIA',
        'CHMI PRA', 'CHMI PRB', 'CIMN', 'CIMO', 'CMRE PRB', 'CMRE PRC', 'CMRE PRD', 'CSWCZ',
        'CUBI PRF', 'DSX PRB', 'DX PRC', 'ECC PRD', 'ECCC', 'ECCF', 'ECCU', 'ECCV', 'ECCW', 'ECCX',
        'EFC PRD', 'EICA', 'EICB', 'EICC', 'EIIA', 'ET PRI', 'FHN PRC', 'FRMEP', 'GAINL', 'GAM PRB',
        'GECCH', 'GECCI', 'GECCO', 'GECCZ', 'GLADZ', 'GMRE PRA', 'HCXY', 'HOVNP', 'HNNAZ', 'HROWL',
        'HROWM', 'HTFB', 'HTFC', 'INBKZ', 'METCL', 'METCZ', 'MFAO', 'MFICL', 'MITN', 'MITP',
        'MITT PRA', 'MITT PRB', 'MITT PRC', 'NEWTG', 'NEWTH', 'NEWTI', 'NYMTZ', 'NYMTG', 'NYMTI',
        'OCCIM', 'OCCIN', 'OCCIO', 'OFSSH', 'OXLCG', 'OXLCI', 'OXLCL', 'OXLCN', 'OXLCO', 'OXLCP',
        'OXLCZ', 'OXSQG', 'OXSQZ', 'PDPA', 'PMTU', 'PRIF PRD', 'PRIF PRJ', 'PRIF PRK', 'PRIF PRL',
        'RWAYL', 'RWAYZ', 'RWT PRA', 'RWTN', 'RWTP', 'RWTO', 'SAJ', 'SAY', 'SAZ', 'SB PRC', 'SB PRD',
        'SPMA', 'SSSSL', 'SWKHL', 'TFINP', 'UCB PRI', 'WHFCL', 'XFLT PRA', 'XOMAO', 'XOMAP',
        'AOMD', 'MBNKO'
    ]
    
    try:
        # Dosyayı oku
        df = pd.read_csv('nalltogether.csv')
        print(f"Orijinal dosya: {len(df)} satır, {len(df.columns)} sütun")
        
        # Çıkarılacak hisseleri bul
        extracted_stocks = df[df['PREF IBKR'].isin(stocks_to_extract)].copy()
        remaining_stocks = df[~df['PREF IBKR'].isin(stocks_to_extract)].copy()
        
        print(f"\nÇıkarılan hisseler: {len(extracted_stocks)} adet")
        print(f"Kalan hisseler: {len(remaining_stocks)} adet")
        
        # Çıkarılan hisseleri listele
        print("\nÇıkarılan hisseler:")
        for stock in extracted_stocks['PREF IBKR']:
            print(f"  - {stock}")
        
        # Notheldpff dosyasını kaydet
        extracted_stocks.to_csv('nnotheldpff.csv', index=False)
        print(f"\n✅ nnotheldpff.csv dosyası oluşturuldu ({len(extracted_stocks)} satır)")
        
        # Ana dosyayı güncelle
        remaining_stocks.to_csv('nalltogether.csv', index=False)
        print(f"✅ nalltogether.csv dosyası güncellendi ({len(remaining_stocks)} satır)")
        
        # Özet
        print(f"\n📊 ÖZET:")
        print(f"  Orijinal: {len(df)} satır")
        print(f"  Çıkarılan: {len(extracted_stocks)} satır")
        print(f"  Kalan: {len(remaining_stocks)} satır")
        
        return True
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        return False

if __name__ == "__main__":
    extract_notheldpff_stocks() 