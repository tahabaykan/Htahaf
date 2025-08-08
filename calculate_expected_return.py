import pandas as pd
import numpy as np

def calculate_expected_annual_return(row):
    """
    Her hisse için beklenen yıllık getiri hesapla
    
    Formül:
    - Expected sale price = SMA63 - (div_amount / 2)
    - Total days = time_to_div + 10
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
        total_days = time_to_div + 10
        final_value = expected_sale_price + div_amount
        ratio = final_value / last_price
        
        # Yıllık getiri hesapla
        exp_ann_return = ratio ** (365 / total_days) - 1
        
        # Yüzdeye çevir
        exp_ann_return_percent = exp_ann_return * 100
        
        return exp_ann_return_percent
        
    except Exception as e:
        print(f"Hesaplama hatası ({row['PREF IBKR']}): {e}")
        return np.nan

def main():
    try:
        # CSV dosyasını oku
        print("nekheldbesmaturlu.csv dosyası okunuyor...")
        df = pd.read_csv('nekheldbesmaturlu.csv', encoding='utf-8-sig')
        
        print(f"Toplam {len(df)} hisse bulundu.")
        
        # Gerekli kolonları kontrol et
        required_columns = ['SMA63', 'Last Price', 'TIME TO DIV', 'DIV AMOUNT']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"HATA: Eksik kolonlar: {missing_columns}")
            print(f"Mevcut kolonlar: {df.columns.tolist()}")
            return
        
        # Her hisse için beklenen yıllık getiri hesapla
        print("\nBeklenen yıllık getiri hesaplanıyor...")
        df['EXPECTED_ANNUAL_RETURN'] = df.apply(calculate_expected_annual_return, axis=1)
        
        # Sonuçları göster
        print("\n=== BEKLENEN YILLIK GETİRİ SONUÇLARI ===")
        print("Hisse     | SMA63   | Last Price | Time to Div | Div Amount | Expected Return")
        print("----------|---------|------------|-------------|------------|-----------------")
        
        # NaN olmayan sonuçları filtrele ve sırala
        valid_results = df[df['EXPECTED_ANNUAL_RETURN'].notna()].copy()
        valid_results = valid_results.sort_values('EXPECTED_ANNUAL_RETURN', ascending=False)
        
        for _, row in valid_results.iterrows():
            ticker = row['PREF IBKR']
            sma63 = row['SMA63']
            last_price = row['Last Price']
            time_to_div = row['TIME TO DIV']
            div_amount = row['DIV AMOUNT']
            exp_return = row['EXPECTED_ANNUAL_RETURN']
            
            print(f"{ticker:<10}| {sma63:>7.2f} | {last_price:>10.2f} | {time_to_div:>11.0f} | {div_amount:>10.2f} | {exp_return:>13.2f}%")
        
        # İstatistikler
        print(f"\n=== İSTATİSTİKLER ===")
        print(f"Toplam hisse sayısı: {len(df)}")
        print(f"Hesaplanabilen hisse sayısı: {len(valid_results)}")
        print(f"Hesaplanamayan hisse sayısı: {len(df) - len(valid_results)}")
        
        if len(valid_results) > 0:
            print(f"\nOrtalama beklenen getiri: {valid_results['EXPECTED_ANNUAL_RETURN'].mean():.2f}%")
            print(f"En yüksek beklenen getiri: {valid_results['EXPECTED_ANNUAL_RETURN'].max():.2f}%")
            print(f"En düşük beklenen getiri: {valid_results['EXPECTED_ANNUAL_RETURN'].min():.2f}%")
            print(f"Medyan beklenen getiri: {valid_results['EXPECTED_ANNUAL_RETURN'].median():.2f}%")
        
        # Top 10 en yüksek beklenen getiri
        print(f"\n=== TOP 10 EN YÜKSEK BEKLENEN GETİRİ ===")
        top_10 = valid_results.head(10)[['PREF IBKR', 'EXPECTED_ANNUAL_RETURN', 'SMA63', 'Last Price', 'TIME TO DIV', 'DIV AMOUNT']]
        print(top_10.round(2).to_string(index=False))
        
        # Bottom 10 en düşük beklenen getiri
        print(f"\n=== BOTTOM 10 EN DÜŞÜK BEKLENEN GETİRİ ===")
        bottom_10 = valid_results.tail(10)[['PREF IBKR', 'EXPECTED_ANNUAL_RETURN', 'SMA63', 'Last Price', 'TIME TO DIV', 'DIV AMOUNT']]
        print(bottom_10.round(2).to_string(index=False))
        
        # Hesaplanamayan hisseleri listele
        invalid_results = df[df['EXPECTED_ANNUAL_RETURN'].isna()]
        if len(invalid_results) > 0:
            print(f"\n=== HESAPLANAMAYAN HİSSELER ===")
            print("Hisse     | SMA63   | Last Price | Time to Div | Div Amount | Sorun")
            print("----------|---------|------------|-------------|------------|-------")
            
            for _, row in invalid_results.iterrows():
                ticker = row['PREF IBKR']
                sma63 = row['SMA63']
                last_price = row['Last Price']
                time_to_div = row['TIME TO DIV']
                div_amount = row['DIV AMOUNT']
                
                # Sorun tespiti
                if pd.isna(sma63):
                    problem = "SMA63 eksik"
                elif pd.isna(last_price):
                    problem = "Last Price eksik"
                elif pd.isna(time_to_div):
                    problem = "TIME TO DIV eksik"
                elif pd.isna(div_amount):
                    problem = "DIV AMOUNT eksik"
                elif last_price == 0:
                    problem = "Last Price sıfır"
                elif time_to_div == 0:
                    problem = "TIME TO DIV sıfır"
                else:
                    problem = "Bilinmeyen"
                
                print(f"{ticker:<10}| {sma63:>7.2f} | {last_price:>10.2f} | {time_to_div:>11.0f} | {div_amount:>10.2f} | {problem}")
        
        # Sonuçları CSV'ye kaydet
        output_filename = 'expected_returns_results.csv'
        df.to_csv(output_filename, index=False, encoding='utf-8-sig')
        print(f"\nSonuçlar '{output_filename}' dosyasına kaydedildi.")
        
    except Exception as e:
        print(f"Genel hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main() 