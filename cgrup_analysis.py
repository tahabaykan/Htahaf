import pandas as pd
import numpy as np

def analyze_cgrup():
    """mastermind_histport.csv dosyasındaki CGRUP'ları analiz et"""
    
    print("CGRUP analizi başlatılıyor...")
    
    try:
        # mastermind_histport.csv dosyasını oku
        df = pd.read_csv('mastermind_histport.csv')
        print(f'Dosya başarıyla okundu: {len(df)} satır')
        print(f'Kolonlar: {list(df.columns)}')
        
        # CGRUP kolonunu kontrol et
        if 'CGRUP' not in df.columns:
            print('HATA: CGRUP kolonu bulunamadı!')
            return
            
        # FINAL_THG kolonunu kontrol et  
        if 'FINAL_THG' not in df.columns:
            print('HATA: FINAL_THG kolonu bulunamadı!')
            return
        
        # CGRUP değerlerini göster
        unique_cgrups = sorted(df['CGRUP'].unique())
        print(f'\nCGRUP değerleri: {unique_cgrups}')
        print(f'CGRUP sayısı: {len(unique_cgrups)}')
        print(f'FINAL_THG değerleri mevcut: {df["FINAL_THG"].count()} / {len(df)}')
        
        # Her CGRUP için analiz
        print(f'\n=== CGRUP ANALİZİ ===')
        
        results = []
        
        for cgrup in unique_cgrups:
            group_df = df[df['CGRUP'] == cgrup].copy()
            
            # FINAL_THG'ye göre sırala
            group_df = group_df.sort_values('FINAL_THG', ascending=False)
            
            print(f'\n--- {cgrup} Grubu ({len(group_df)} hisse) ---')
            
            # En yüksek 3
            top_3 = group_df.head(3)
            print(f'En yüksek FINAL_THG (Top 3):')
            for idx, (_, row) in enumerate(top_3.iterrows(), 1):
                print(f'  {idx}. {row["PREF IBKR"]}: {row["FINAL_THG"]:.4f}')
                results.append({
                    'CGRUP': cgrup,
                    'Type': 'TOP',
                    'Rank': idx,
                    'PREF IBKR': row['PREF IBKR'],
                    'FINAL_THG': row['FINAL_THG'],
                    'AVGADV': row.get('AVGADV', row.get('AVG_ADV', 'N/A')),
                    'CMON': row.get('CMON', 'N/A')
                })
            
            # En düşük 3
            bottom_3 = group_df.tail(3).iloc[::-1]  # Ters çevir ki en düşük önce gelsin
            print(f'En düşük FINAL_THG (Bottom 3):')
            for idx, (_, row) in enumerate(bottom_3.iterrows(), 1):
                print(f'  {idx}. {row["PREF IBKR"]}: {row["FINAL_THG"]:.4f}')
                results.append({
                    'CGRUP': cgrup,
                    'Type': 'BOTTOM',
                    'Rank': idx,
                    'PREF IBKR': row['PREF IBKR'],
                    'FINAL_THG': row['FINAL_THG'],
                    'AVGADV': row.get('AVGADV', row.get('AVG_ADV', 'N/A')),
                    'CMON': row.get('CMON', 'N/A')
                })
        
        # Sonuçları DataFrame'e çevir
        results_df = pd.DataFrame(results)
        
        # Sıralama: CGRUP, Type, Rank
        results_df = results_df.sort_values(['CGRUP', 'Type', 'Rank'])
        
        # mastercgrup.csv dosyasına kaydet
        results_df.to_csv('mastercgrup.csv', index=False)
        print(f'\n✅ mastercgrup.csv dosyası oluşturuldu: {len(results_df)} satır')
        
        # Özet istatistikler
        print(f'\n=== ÖZET ===')
        print(f'Toplam CGRUP sayısı: {len(unique_cgrups)}')
        print(f'Her grup için 6 hisse (3 top + 3 bottom)')
        print(f'Toplam seçilen hisse: {len(results_df)}')
        
        # Grup başına dağılım
        print(f'\n=== GRUP BAŞINA DAĞILIM ===')
        for cgrup in unique_cgrups:
            group_count = len(results_df[results_df['CGRUP'] == cgrup])
            top_count = len(results_df[(results_df['CGRUP'] == cgrup) & (results_df['Type'] == 'TOP')])
            bottom_count = len(results_df[(results_df['CGRUP'] == cgrup) & (results_df['Type'] == 'BOTTOM')])
            print(f'{cgrup}: {group_count} hisse ({top_count} top + {bottom_count} bottom)')
        
        # Dosya içeriğini göster
        print(f'\n=== MASTERCGRUP.CSV İÇERİĞİ (İLK 10 SATIR) ===')
        print(results_df.head(10).to_string(index=False))
        
        return results_df
        
    except Exception as e:
        print(f'HATA: {e}')
        return None

if __name__ == "__main__":
    analyze_cgrup() 