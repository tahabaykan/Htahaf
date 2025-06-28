import pandas as pd
import numpy as np
import math

def create_short_candidate_file(input_file, smi_file, output_file):
    """
    Girdi dosyasından (mastermind_histport.csv veya mastermind_extltport.csv) ve SMI dosyasından (Smiall.csv)
    PREF IBKR üzerinden merge ederek, SMI ve SHORT_FINAL kolonlarını ekler ve tüm orijinal kolonları koruyarak kaydeder.
    """
    print(f"\n{'-'*50}")
    print(f"SHORT ADAY DOSYASI OLUŞTURULUYOR: {input_file} + {smi_file} -> {output_file}")
    print(f"{'-'*50}")
    try:
        df = pd.read_csv(input_file)
        smi_df = pd.read_csv(smi_file)
        df = df.merge(smi_df[['PREF IBKR', 'SMI']], on='PREF IBKR', how='left')
        missing_smi = df['SMI'].isna().sum()
        if missing_smi > 0:
            print(f"⚠️ {missing_smi} hisse için SMI değeri bulunamadı! Ortalama ile doldurulacak.")
            mean_smi = df['SMI'].mean()
            df['SMI'].fillna(mean_smi, inplace=True)
        df['SHORT_FINAL'] = df['FINAL_THG'] + (df['SMI'] * 500)
        df.to_csv(output_file, index=False)
        print(f"{output_file} dosyası kaydedildi. Toplam {len(df)} satır.")
        return df
    except Exception as e:
        print(f"HATA: Short aday dosyası oluşturulurken bir sorun oluştu: {e}")
        return None

def create_short_portfolio_by_cgrup(long_file, short_file, output_file, num_stocks):
    """
    CGRUP bazlı short portföy oluşturur:
    - Her CGRUP için long portföydeki hisse sayısının ve lot sayısının en az yarısı kadar short seçer
    - Seçim yaparken o CGRUP'taki en düşük SHORT_FINAL skoruna sahip hisseleri alır
    - Toplam num_stocks kadar hisse seçilir
    """
    print(f"\n{'-'*50}")
    print(f"CGRUP BAZLI SHORT PORTFÖY OLUŞTURULUYOR: {long_file} + {short_file} -> {output_file}")
    print(f"{'-'*50}")
    
    try:
        # 1. Long portföyü yükle
        long_df = pd.read_csv(long_file)
        print(f"Long portföy yüklendi: {len(long_df)} hisse")
        
        # 2. Short adaylarını yükle
        short_df = pd.read_csv(short_file)
        print(f"Short adayları yüklendi: {len(short_df)} hisse")
        
        # 3. Long portföyde CGRUP bazında istatistikler
        cgrup_stats = long_df.groupby('CGRUP').agg(
            long_count=('PREF IBKR', 'count'),
            long_lots=('Final_Shares', 'sum')
        ).reset_index()
        
        print("\nLong portföyde CGRUP bazında dağılım:")
        print(cgrup_stats.to_string(index=False))
        
        # 4. Her CGRUP için minimum short gereksinimleri
        cgrup_stats['min_short_count'] = cgrup_stats['long_count'].apply(lambda x: math.ceil(x/2))
        cgrup_stats['min_short_lots'] = cgrup_stats['long_lots'].apply(lambda x: math.ceil(x/2))
        
        # 5. Short portföyü oluştur
        selected_shorts = []
        remaining_slots = num_stocks
        
        # Önce her CGRUP için minimum gereksinimleri karşıla
        for _, row in cgrup_stats.iterrows():
            cgrup = row['CGRUP']
            min_count = row['min_short_count']
            min_lots = row['min_short_lots']
            
            # O CGRUP'taki short adaylarını bul
            cgrup_shorts = short_df[short_df['CGRUP'] == cgrup].copy()
            if len(cgrup_shorts) == 0:
                print(f"UYARI: {cgrup} için short aday bulunamadı!")
                continue
            
            # SHORT_FINAL'a göre sırala
            cgrup_shorts = cgrup_shorts.sort_values('SHORT_FINAL')
            
            # En az min_count kadar hisse seç
            selected = cgrup_shorts.head(min_count)
            selected_shorts.append(selected)
            remaining_slots -= len(selected)
            
            # Dinamik kolon gösterimi
            cols_to_show = ['PREF IBKR', 'SHORT_FINAL']
            if 'CGRUP' in selected.columns:
                cols_to_show.append('CGRUP')
            print(f"\n{cgrup} için seçilen short pozisyonlar:")
            print(f"Minimum gereksinim: {min_count} hisse, {min_lots} lot")
            print(f"Seçilen: {len(selected)} hisse")
            print(selected[cols_to_show].to_string(index=False))
        
        # 6. Kalan slotları en düşük SHORT_FINAL'lı hisselerle doldur
        if remaining_slots > 0:
            # Seçilmemiş hisseleri bul
            selected_symbols = pd.concat(selected_shorts)['PREF IBKR'].tolist() if selected_shorts else []
            remaining_shorts = short_df[~short_df['PREF IBKR'].isin(selected_symbols)]
            
            if len(remaining_shorts) > 0:
                # SHORT_FINAL'a göre sırala
                remaining_shorts = remaining_shorts.sort_values('SHORT_FINAL')
                # Kalan slotları doldur
                additional_shorts = remaining_shorts.head(remaining_slots)
                selected_shorts.append(additional_shorts)
                
                cols_to_show = ['PREF IBKR', 'SHORT_FINAL']
                if 'CGRUP' in additional_shorts.columns:
                    cols_to_show.append('CGRUP')
                print(f"\nKalan {remaining_slots} slot için eklenen short pozisyonlar:")
                print(additional_shorts[cols_to_show].to_string(index=False))
        
        # 7. Sonuçları birleştir
        if len(selected_shorts) == 0:
            print("Hiç short pozisyon seçilemedi!")
            return None
        
        final_df = pd.concat(selected_shorts, ignore_index=True)
        
        # 8. Sonuçları göster
        print("\nFINAL SHORT PORTFÖY:")
        print(f"Toplam {len(final_df)} hisse seçildi")
        print("\nCGRUP bazında dağılım:")
        print(final_df.groupby('CGRUP').agg(
            short_count=('PREF IBKR', 'count')
        ).to_string())
        
        # 9. Dosyayı kaydet
        final_df.to_csv(output_file, index=False)
        print(f"\nShort portföy '{output_file}' dosyasına kaydedildi.")
        
        return final_df
        
    except Exception as e:
        print(f"HATA: Short portföy oluşturulurken bir sorun oluştu: {e}")
        return None

def create_simple_short_portfolio(short_file, output_file, num_stocks):
    """
    Basit short portföy oluşturur:
    - Sadece en düşük SHORT_FINAL skoruna sahip num_stocks kadar hisse seçer
    """
    print(f"\n{'-'*50}")
    print(f"BASIT SHORT PORTFÖY OLUŞTURULUYOR: {short_file} -> {output_file}")
    print(f"{'-'*50}")
    
    try:
        # 1. Short adaylarını yükle
        df = pd.read_csv(short_file)
        print(f"Short adayları yüklendi: {len(df)} hisse")
        
        # 2. SHORT_FINAL'a göre sırala ve seç
        selected_df = df.nsmallest(num_stocks, 'SHORT_FINAL')
        
        cols_to_show = ['PREF IBKR', 'SHORT_FINAL']
        if 'CGRUP' in selected_df.columns:
            cols_to_show.append('CGRUP')
        print("\nSeçilen hisseler (SHORT_FINAL en düşük olanlar):")
        print(selected_df[cols_to_show].to_string(index=False))
        
        # 4. Dosyayı kaydet
        selected_df.to_csv(output_file, index=False)
        print(f"\nShort portföy '{output_file}' dosyasına kaydedildi.")
        
        return selected_df
        
    except Exception as e:
        print(f"HATA: Short portföy oluşturulurken bir sorun oluştu: {e}")
        return None

def main():
    print("Short portföy oluşturma işlemi başlatılıyor...")
    # 0. Short aday dosyalarını oluştur
    create_short_candidate_file(
        input_file="mastermind_histport.csv",
        smi_file="Smiall.csv",
        output_file="short_histport.csv"
    )
    create_short_candidate_file(
        input_file="mastermind_extltport.csv",
        smi_file="Smiall.csv",
        output_file="short_extlt.csv"
    )
    # 1. Historical portföy için CGRUP bazlı short portföy oluştur
    create_short_portfolio_by_cgrup(
        long_file="optimized_50_stocks_portfolio.csv",
        short_file="short_histport.csv",
        output_file="final_short_histport.csv",
        num_stocks=30
    )
    # 2. Extended LT portföy için basit short portföy oluştur
    create_simple_short_portfolio(
        short_file="short_extlt.csv",
        output_file="final_short_extlt.csv",
        num_stocks=10
    )
    print("\nTüm işlemler tamamlandı!")

if __name__ == "__main__":
    main() 