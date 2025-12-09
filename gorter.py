"""
GORT Analiz Scripti
janalldata.csv dosyasındaki hisseleri CGRUP'a göre gruplayıp,
her grup için en yüksek ve en düşük 3 GORT değerine sahip hisseleri bulur.

GORT değeri runtime'da hesaplanır:
GORT = (SMA63 chg - group_avg_sma63) + (SMA246 chg - group_avg_sma246)

Kuponlu hisseler: CGRUP'a göre gruplanır (c425, c450, c475 vs)
Diğer hisseler: Kendi grupları içinde bakılır (helddeznff, heldff vs)
"""

import pandas as pd
import os

def get_group_from_symbol(symbol, group_file_map):
    """Symbol'ün hangi gruba ait olduğunu bul"""
    for group, file_name in group_file_map.items():
        if os.path.exists(file_name):
            try:
                df = pd.read_csv(file_name)
                if symbol in df['PREF IBKR'].tolist():
                    return group
            except Exception:
                continue
    return None

def calculate_gort_for_symbol(symbol, group, cgrup, group_file_map, janalldata_df):
    """Bir hisse için GORT değerini hesapla"""
    try:
        # Grup dosyasını bul
        file_name = group_file_map.get(group.lower())
        if not file_name or not os.path.exists(file_name):
            return None
        
        # Grup dosyasını oku
        group_df = pd.read_csv(file_name)
        
        # Symbol'ü bul
        symbol_row = group_df[group_df['PREF IBKR'] == symbol]
        if symbol_row.empty:
            return None
        
        # SMA 63 CHG ve SMA 246 CHG değerlerini al
        sma63chg = None
        sma246chg = None
        
        # SMA 63 CHG için farklı isimleri dene
        sma63_col_names = ['SMA63 chg', 'SMA63CHG', 'SMA63_chg', 'SMA 63 CHG']
        for col_name in sma63_col_names:
            if col_name in group_df.columns:
                sma63chg_val = symbol_row[col_name].iloc[0]
                if pd.notna(sma63chg_val):
                    sma63chg = pd.to_numeric(sma63chg_val, errors='coerce')
                    if not pd.isna(sma63chg):
                        break
        
        # SMA 246 CHG için farklı isimleri dene
        sma246_col_names = ['SMA246 chg', 'SMA 246 CHG', 'SMA246CHG', 'SMA246_CHG', 'SMA 246 chg']
        for col_name in sma246_col_names:
            if col_name in group_df.columns:
                sma246chg_val = symbol_row[col_name].iloc[0]
                if pd.notna(sma246chg_val):
                    sma246chg = pd.to_numeric(sma246chg_val, errors='coerce')
                    if not pd.isna(sma246chg):
                        break
        
        if sma63chg is None or sma246chg is None:
            return None
        
        # CGRUP bilgisini al (kuponlu gruplar için)
        if 'CGRUP' in group_df.columns:
            cgrup_val = symbol_row['CGRUP'].iloc[0]
            if pd.notna(cgrup_val) and cgrup_val != '' and cgrup_val != 'N/A':
                cgrup = str(cgrup_val).strip()
        
        # Grup ortalamalarını hesapla
        kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
        
        # SMA 63 CHG ortalama
        if group.lower() in kuponlu_groups and cgrup:
            # CGRUP'a göre gruplama
            cgrup_rows = group_df[(group_df['CGRUP'] == cgrup) & (group_df['PREF IBKR'] != symbol)]
            for col_name in sma63_col_names:
                if col_name in group_df.columns:
                    sma63_values = cgrup_rows[col_name].dropna()
                    sma63_values = pd.to_numeric(sma63_values, errors='coerce').dropna()
                    if not sma63_values.empty:
                        group_avg_sma63 = sma63_values.mean()
                        if group_avg_sma63 == 0:
                            group_avg_sma63 = 0.01
                        break
            else:
                group_avg_sma63 = 0.01
        else:
            # Normal gruplar için - Grup dosyasındaki tüm hisselerin ortalaması
            for col_name in sma63_col_names:
                if col_name in group_df.columns:
                    sma63_values = group_df[col_name].dropna()
                    sma63_values = pd.to_numeric(sma63_values, errors='coerce').dropna()
                    if not sma63_values.empty:
                        group_avg_sma63 = sma63_values.mean()
                        if group_avg_sma63 == 0:
                            group_avg_sma63 = 0.01
                        break
            else:
                group_avg_sma63 = 0.01
        
        # SMA 246 CHG ortalama
        if group.lower() in kuponlu_groups and cgrup:
            # CGRUP'a göre gruplama
            cgrup_rows = group_df[(group_df['CGRUP'] == cgrup) & (group_df['PREF IBKR'] != symbol)]
            for col_name in sma246_col_names:
                if col_name in group_df.columns:
                    sma246_values = cgrup_rows[col_name].dropna()
                    sma246_values = pd.to_numeric(sma246_values, errors='coerce').dropna()
                    if not sma246_values.empty:
                        group_avg_sma246 = sma246_values.mean()
                        if group_avg_sma246 == 0:
                            group_avg_sma246 = 0.01
                        break
            else:
                group_avg_sma246 = 0.01
        else:
            # Normal gruplar için - Grup dosyasındaki tüm hisselerin ortalaması
            for col_name in sma246_col_names:
                if col_name in group_df.columns:
                    sma246_values = group_df[col_name].dropna()
                    sma246_values = pd.to_numeric(sma246_values, errors='coerce').dropna()
                    if not sma246_values.empty:
                        group_avg_sma246 = sma246_values.mean()
                        if group_avg_sma246 == 0:
                            group_avg_sma246 = 0.01
                        break
            else:
                group_avg_sma246 = 0.01
        
        # GORT hesapla (SMA63: %25, SMA246: %75 ağırlık)
        gort = (0.25 * (sma63chg - group_avg_sma63)) + (0.75 * (sma246chg - group_avg_sma246))
        
        return gort
        
    except Exception as e:
        return None

def analyze_gort_by_group():
    """janalldata.csv'yi okuyup grup bazında GORT analizi yapar"""
    try:
        csv_file = "janalldata.csv"
        
        if not os.path.exists(csv_file):
            print(f"❌ {csv_file} dosyası bulunamadı!")
            return
        
        print(f"📊 {csv_file} dosyası okunuyor...")
        df = pd.read_csv(csv_file)
        
        # Gerekli kolonları kontrol et
        required_columns = ['PREF IBKR', 'CGRUP']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"❌ Eksik kolonlar: {', '.join(missing_columns)}")
            print(f"📋 Mevcut kolonlar: {', '.join(df.columns[:10])}...")
            return
        
        print(f"✅ {len(df)} hisse bulundu")
        
        # Grup dosya eşleşmesi
        group_file_map = {
            'heldff': 'ssfinekheldff.csv',
            'helddeznff': 'ssfinekhelddeznff.csv', 
            'heldkuponlu': 'ssfinekheldkuponlu.csv',
            'heldnff': 'ssfinekheldnff.csv',
            'heldflr': 'ssfinekheldflr.csv',
            'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
            'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
            'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
            'heldotelremorta': 'ssfinekheldotelremorta.csv',
            'heldsolidbig': 'ssfinekheldsolidbig.csv',
            'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
            'highmatur': 'ssfinekhighmatur.csv',
            'notcefilliquid': 'ssfineknotcefilliquid.csv',
            'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
            'nottitrekhc': 'ssfineknottitrekhc.csv',
            'salakilliquid': 'ssfineksalakilliquid.csv',
            'shitremhc': 'ssfinekshitremhc.csv'
        }
        
        # Her hisse için GORT hesapla
        print("🔄 GORT değerleri hesaplanıyor...")
        gort_values = {}
        
        for idx, row in df.iterrows():
            symbol = row['PREF IBKR']
            cgrup = row.get('CGRUP', '')
            
            # Grup bilgisini bul
            group = get_group_from_symbol(symbol, group_file_map)
            if not group:
                continue
            
            # GORT hesapla
            gort = calculate_gort_for_symbol(symbol, group, cgrup, group_file_map, df)
            if gort is not None:
                gort_values[symbol] = gort
        
        print(f"✅ {len(gort_values)} hisse için GORT hesaplandı")
        
        # GORT değerlerini DataFrame'e ekle
        df['GORT'] = df['PREF IBKR'].map(gort_values)
        df['GORT'] = pd.to_numeric(df['GORT'], errors='coerce')
        
        # Her hisse için grup bilgisini ekle
        symbol_to_group = {}
        for group, file_name in group_file_map.items():
            if os.path.exists(file_name):
                try:
                    group_df = pd.read_csv(file_name)
                    for symbol in group_df['PREF IBKR'].tolist():
                        symbol_to_group[symbol] = group
                except Exception:
                    pass
        
        df['GROUP'] = df['PREF IBKR'].map(symbol_to_group)
        df_clean = df.dropna(subset=['GORT', 'GROUP'])
        
        print(f"✅ {len(df_clean)} hisse geçerli GORT ve GROUP değerine sahip")
        
        results = []
        
        # 1. HELDKUPONLU grubu: CGRUP'a göre grupla
        heldkuponlu_symbols = set()
        heldkuponlu_file = group_file_map.get('heldkuponlu')
        if heldkuponlu_file and os.path.exists(heldkuponlu_file):
            try:
                heldkuponlu_df = pd.read_csv(heldkuponlu_file)
                heldkuponlu_symbols.update(heldkuponlu_df['PREF IBKR'].tolist())
            except Exception:
                pass
        
        heldkuponlu_data = df_clean[df_clean['PREF IBKR'].isin(heldkuponlu_symbols)].copy()
        
        if len(heldkuponlu_data) > 0:
            # CGRUP değerlerini temizle
            heldkuponlu_data['CGRUP'] = heldkuponlu_data['CGRUP'].astype(str).str.strip()
            heldkuponlu_data = heldkuponlu_data[heldkuponlu_data['CGRUP'] != '']
            heldkuponlu_data = heldkuponlu_data[heldkuponlu_data['CGRUP'] != 'nan']
            
            # CGRUP'a göre grupla
            for cgrup, group_df in heldkuponlu_data.groupby('CGRUP'):
                if len(group_df) < 3:
                    continue
                
                cgrup_str = str(cgrup).strip()
                group_sorted = group_df.sort_values('GORT', ascending=False)
                
                top_3 = group_sorted.head(3)
                bottom_3 = group_sorted.tail(3).sort_values('GORT', ascending=True)
                
                for pos, (idx, row) in enumerate(top_3.iterrows(), 1):
                    results.append({
                        'GROUP': 'heldkuponlu',
                        'CGRUP': cgrup_str,
                        'Symbol': row['PREF IBKR'],
                        'GORT': round(row['GORT'], 2),
                        'Rank': 'TOP',
                        'Position': pos
                    })
                
                for pos, (idx, row) in enumerate(bottom_3.iterrows(), 1):
                    results.append({
                        'GROUP': 'heldkuponlu',
                        'CGRUP': cgrup_str,
                        'Symbol': row['PREF IBKR'],
                        'GORT': round(row['GORT'], 2),
                        'Rank': 'BOTTOM',
                        'Position': pos
                    })
        
        # 2. Diğer tüm gruplar: CGRUP'u görmezden gel, grup adına göre grupla
        other_groups_data = df_clean[~df_clean['PREF IBKR'].isin(heldkuponlu_symbols)].copy()
        
        for group_name, group_df in other_groups_data.groupby('GROUP'):
            if len(group_df) < 3:
                continue
            
            group_sorted = group_df.sort_values('GORT', ascending=False)
            
            top_3 = group_sorted.head(3)
            bottom_3 = group_sorted.tail(3).sort_values('GORT', ascending=True)
            
            for pos, (idx, row) in enumerate(top_3.iterrows(), 1):
                results.append({
                    'GROUP': group_name,
                    'CGRUP': 'N/A',  # CGRUP görmezden gelindi
                    'Symbol': row['PREF IBKR'],
                    'GORT': round(row['GORT'], 2),
                    'Rank': 'TOP',
                    'Position': pos
                })
            
            for pos, (idx, row) in enumerate(bottom_3.iterrows(), 1):
                results.append({
                    'GROUP': group_name,
                    'CGRUP': 'N/A',  # CGRUP görmezden gelindi
                    'Symbol': row['PREF IBKR'],
                    'GORT': round(row['GORT'], 2),
                    'Rank': 'BOTTOM',
                    'Position': pos
                })
        
        if not results:
            print("❌ Hiç sonuç bulunamadı!")
            return
        
        # Sonuçları DataFrame'e çevir
        results_df = pd.DataFrame(results)
        
        # CSV olarak kaydet
        output_file = "gort_analysis.csv"
        results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"✅ Sonuçlar {output_file} dosyasına kaydedildi")
        
        # Özet rapor yazdır
        print("\n" + "=" * 80)
        print("📊 GORT ANALİZ RAPORU")
        print("=" * 80)
        
        # HELDKUPONLU grubu: CGRUP'a göre göster
        heldkuponlu_results = results_df[results_df['GROUP'] == 'heldkuponlu']
        if len(heldkuponlu_results) > 0:
            print("\n📁 HELDKUPONLU GRUBU (CGRUP'a göre):")
            for cgrup in sorted(heldkuponlu_results['CGRUP'].unique()):
                cgrup_df = heldkuponlu_results[heldkuponlu_results['CGRUP'] == cgrup]
                top_df = cgrup_df[cgrup_df['Rank'] == 'TOP'].sort_values('GORT', ascending=False)
                bottom_df = cgrup_df[cgrup_df['Rank'] == 'BOTTOM'].sort_values('GORT', ascending=True)
                
                print(f"\n   CGRUP: {cgrup} ({len(cgrup_df)} kayıt)")
                print(f"   🔝 TOP 3 (En Yüksek GORT):")
                for idx, row in top_df.iterrows():
                    print(f"      {row['Position']}. {row['Symbol']}: {row['GORT']:.2f}")
                
                print(f"   🔻 BOTTOM 3 (En Düşük GORT):")
                for idx, row in bottom_df.iterrows():
                    print(f"      {row['Position']}. {row['Symbol']}: {row['GORT']:.2f}")
        
        # Diğer gruplar: Grup adına göre göster
        other_results = results_df[results_df['GROUP'] != 'heldkuponlu']
        if len(other_results) > 0:
            print("\n📁 DİĞER GRUPLAR (CGRUP görmezden gelindi):")
            for group_name in sorted(other_results['GROUP'].unique()):
                group_df = other_results[other_results['GROUP'] == group_name]
                top_df = group_df[group_df['Rank'] == 'TOP'].sort_values('GORT', ascending=False)
                bottom_df = group_df[group_df['Rank'] == 'BOTTOM'].sort_values('GORT', ascending=True)
                
                print(f"\n   GROUP: {group_name} ({len(group_df)} kayıt)")
                print(f"   🔝 TOP 3 (En Yüksek GORT):")
                for idx, row in top_df.iterrows():
                    print(f"      {row['Position']}. {row['Symbol']}: {row['GORT']:.2f}")
                
                print(f"   🔻 BOTTOM 3 (En Düşük GORT):")
                for idx, row in bottom_df.iterrows():
                    print(f"      {row['Position']}. {row['Symbol']}: {row['GORT']:.2f}")
        
        print("\n" + "=" * 80)
        print(f"✅ Toplam {len(results_df['GROUP'].unique())} grup analiz edildi")
        print(f"✅ {len(results_df)} kayıt {output_file} dosyasına kaydedildi")
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 GORT Analiz Scripti Başlatılıyor...")
    print("=" * 60)
    analyze_gort_by_group()
    print("\n✅ GORT analizi tamamlandı!")
