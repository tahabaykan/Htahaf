import pandas as pd
import glob

def check_us15y_usage():
    """
    US15Y kullanımını kontrol eder
    """
    print("=== US15Y Kullanım Kontrolü ===")
    
    yek_files = glob.glob('yek*.csv')
    total_us15y = 0
    
    for file in yek_files:
        try:
            df = pd.read_csv(file)
            us15y_count = len(df[df['Normal Treasury Bench'] == 'US15Y'])
            
            if us15y_count > 0:
                print(f"{file}: {us15y_count} US15Y")
                total_us15y += us15y_count
                
                # İlk birkaç örneği göster
                examples = df[df['Normal Treasury Bench'] == 'US15Y'][['COUPON', 'Normal Treasury Bench']].head(3)
                print("  Örnekler:")
                for _, row in examples.iterrows():
                    print(f"    {row['COUPON']} -> {row['Normal Treasury Bench']}")
                print()
                
        except Exception as e:
            print(f"{file}: Hata - {e}")
    
    print(f"Toplam US15Y kullanımı: {total_us15y}")
    
    if total_us15y == 0:
        print("\nUS15Y hiç kullanılmamış. 5.16% - 5.80% aralığında kupon yok.")

if __name__ == "__main__":
    check_us15y_usage() 