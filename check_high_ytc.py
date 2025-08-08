import pandas as pd

def check_high_ytc():
    """YTC'si 20'nin üzerinde olan hisseleri bul"""
    try:
        # Dosyaları oku
        df1 = pd.read_csv('finekheldnff_ytc.csv', encoding='utf-8-sig')
        df2 = pd.read_csv('finekhelddeznff_ytc.csv', encoding='utf-8-sig')
        
        # Birleştir
        high_ytc = pd.concat([df1, df2])
        
        # YTC > 20 olanları filtrele
        high_ytc_filtered = high_ytc[high_ytc['YTC'] > 20]
        
        print('YTC > 20 olan hisseler:')
        print('PREF IBKR | YTC | EXP_RETURN | SOLIDITY | FINAL_THG')
        print('-' * 60)
        
        for _, row in high_ytc_filtered.iterrows():
            print(f"{row['PREF IBKR']:<10} | {row['YTC']:>5.2f} | {row['EXP_ANN_RETURN']:>10.2f} | {row['SOLIDITY_SCORE_NORM']:>8.2f} | {row['FINAL_THG_CALLABLE']:>9.2f}")
        
        print(f'\nToplam {len(high_ytc_filtered)} hisse YTC > 20')
        if len(high_ytc_filtered) > 0:
            print(f'YTC > 20 hisselerin ortalama YTC: {high_ytc_filtered["YTC"].mean():.2f}%')
            print(f'En yüksek YTC: {high_ytc_filtered["YTC"].max():.2f}%')
            print(f'En düşük YTC: {high_ytc_filtered["YTC"].min():.2f}%')
        
        # Bu hisseleri ayrı bir dosyaya kaydet
        if len(high_ytc_filtered) > 0:
            output_file = 'high_ytc_stocks.csv'
            high_ytc_filtered.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f'\nYüksek YTC hisseleri "{output_file}" dosyasına kaydedildi.')
        
        return high_ytc_filtered
        
    except Exception as e:
        print(f"Hata: {e}")
        return None

if __name__ == "__main__":
    check_high_ytc() 