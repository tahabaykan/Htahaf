import pandas as pd
import numpy as np
import os
import glob
import math

def get_file_specific_rules(file_name):
    """
    Her dosya için özel kuralları döndürür
    """
    rules = {
        'ssfinekheldsolidbig.csv': {
            'long_percent': 15, 'long_multiplier': 1.7,  # Aynı kaldı
            'short_percent': 10, 'short_multiplier': 0.35,  # Güncellendi: 10→10, 0.5→0.35
            'max_short': 2
        },
        'ssfinekheldbesmaturlu.csv': {
            'long_percent': 10, 'long_multiplier': 1.8,  # Güncellendi: 10→10, 1.6→1.8
            'short_percent': 5, 'short_multiplier': 0.25,  # Aynı kaldı
            'max_short': 2
        },
        'ssfinekheldtitrekhc.csv': {
            'long_percent': 15, 'long_multiplier': 1.7,  # Güncellendi: 20→15, 1.6→1.7
            'short_percent': 10, 'short_multiplier': 0.3,  # Aynı kaldı
            'max_short': 2
        },
        'ssfinekheldkuponlukreorta.csv': {
            'long_percent': 10, 'long_multiplier': 1.8,  # Aynı kaldı
            'short_percent': 15, 'short_multiplier': 0.4,  # Güncellendi: 20→15, 0.5→0.4
            'max_short': 3
        },
        'ssfinekheldflr.csv': {
            'long_percent': 20, 'long_multiplier': 1.7,  # Aynı kaldı
            'short_percent': 10, 'short_multiplier': 0.35,  # Güncellendi: 15→10, 0.5→0.35
            'max_short': 2
        },
        'ssfinekheldkuponlukreciliz.csv': {
            'long_percent': 10, 'long_multiplier': 1.8,  # Aynı kaldı
            'short_percent': 15, 'short_multiplier': 0.4,  # Güncellendi: 20→15, 0.5→0.4
            'max_short': 3
        },
        'ssfinekheldcommonsuz.csv': {
            'long_percent': 10, 'long_multiplier': 1.8,  # Güncellendi: 10→10, 1.6→1.8
            'short_percent': 15, 'short_multiplier': 0.4,  # Güncellendi: 25→15, 0.5→0.4
            'max_short': 3
        },
        'ssfineknotbesmaturlu.csv': {
            'long_percent': 10, 'long_multiplier': 1.8,  # Güncellendi: 10→10, 1.6→1.8
            'short_percent': 5, 'short_multiplier': 0.25,  # Güncellendi: 10→5, 0.3→0.25
            'max_short': 2
        },
        'ssfinekrumoreddanger.csv': {
            'long_percent': 5, 'long_multiplier': 1.8,  # Güncellendi: 5→5, 1.75→1.8
            'short_percent': 5, 'short_multiplier': 0.25,  # Güncellendi: 10→5, 0.3→0.25
            'max_short': 2
        },
        'ssfinekheldgarabetaltiyedi.csv': {
            'long_percent': 20, 'long_multiplier': 1.8,  # Aynı kaldı
            'short_percent': 10, 'short_multiplier': 0.35,  # Güncellendi: 15→10, 0.5→0.35
            'max_short': 3
        },
        'ssfinekheldnff.csv': {
            'long_percent': 20, 'long_multiplier': 1.7,  # Aynı kaldı
            'short_percent': 10, 'short_multiplier': 0.3,  # Güncellendi: 15→10, 0.35→0.3
            'max_short': 2
        },
        'ssfinekheldotelremorta.csv': {
            'long_percent': 10, 'long_multiplier': 1.8,  # Aynı kaldı
            'short_percent': 10, 'short_multiplier': 0.3,  # Güncellendi: 15→10, 0.4→0.3
            'max_short': 3
        },
        'ssfineksalakilliquid.csv': {
            'long_percent': 10, 'long_multiplier': 1.8,  # Aynı kaldı
            'short_percent': 10, 'short_multiplier': 0.35,  # Güncellendi: 15→10, 0.4→0.35
            'max_short': 2
        },
        'ssfinekheldff.csv': {
            'long_percent': 25, 'long_multiplier': 1.6,  # Aynı kaldı
            'short_percent': 10, 'short_multiplier': 0.35,  # Güncellendi: 15→10, 0.4→0.35
            'max_short': 2
        },
        'ssfinekhighmatur.csv': {
            'long_percent': 20, 'long_multiplier': 1.7,  # Güncellendi: 25→20, 1.5→1.7
            'short_percent': 5, 'short_multiplier': 0.2,  # Aynı kaldı
            'max_short': 2
        },
        'ssfineknotcefilliquid.csv': {
            'long_percent': 10, 'long_multiplier': 1.8,  # Güncellendi: 10→10, 1.7→1.8
            'short_percent': 5, 'short_multiplier': 0.25,  # Aynı kaldı
            'max_short': 2
        },
        'ssfinekhelddeznff.csv': {
            'long_percent': 20, 'long_multiplier': 1.7,  # Aynı kaldı
            'short_percent': 15, 'short_multiplier': 0.4,  # Güncellendi: 20→15, 0.6→0.4
            'max_short': 2
        },
        'ssfinekheldkuponlu.csv': {
            'long_percent': 35, 'long_multiplier': 1.3,  # Aynı kaldı
            'short_percent': 35, 'short_multiplier': 0.75,  # Aynı kaldı
            'max_short': 999  # Sınırsız - Aynı kaldı
        }
    }
    
    # Dosya adını al (path olmadan)
    file_basename = os.path.basename(file_name)
    
    # Eğer özel kural varsa onu döndür, yoksa varsayılan kuralı döndür
    if file_basename in rules:
        return rules[file_basename]
    else:
        # Varsayılan kural
        return {
            'long_percent': 25, 'long_multiplier': 1.5,  # 35→25, 1.35→1.5
            'short_percent': 25, 'short_multiplier': 0.7,
            'max_short': 3
        }

def limit_by_company(stocks_df, direction='LONG', original_df=None):
    """
    Aynı şirketten (CMON) gelen hisseleri sınırlar
    """
    if len(stocks_df) == 0:
        return stocks_df
    
    # Orijinal dosyadaki tüm hisseleri kullan
    if original_df is not None:
        full_df = original_df
    else:
        full_df = stocks_df
    
    # CMON'a göre grupla (filtrelenmiş hisseler)
    company_groups = stocks_df.groupby('CMON')
    limited_stocks = []
    
    for company, group in company_groups:
        # Orijinal dosyadaki bu şirketin toplam hisse sayısını bul
        company_total_count = len(full_df[full_df['CMON'] == company])
        # 1.6'ya böl ve normal yuvarla (0.5+ yukarı, 0.4- aşağı)
        # Minimum 1 hisse seçilebilir
        max_allowed = max(1, round(company_total_count / 1.6))
        
        print(f"      📊 {company}: {company_total_count} hisse → maksimum {max_allowed} seçilebilir")
        
        if direction == 'LONG':
            # En yüksek Final FB skoruna sahip olanları seç
            selected = group.nlargest(max_allowed, 'Final FB')
        else:  # SHORT
            # En düşük Final SFS skoruna sahip olanları seç
            selected = group.nsmallest(max_allowed, 'Final SFS')
        
        limited_stocks.append(selected)
    
    if limited_stocks:
        return pd.concat(limited_stocks, ignore_index=True)
    else:
        return pd.DataFrame()

def limit_by_cgroup(stocks_df, direction='LONG', max_per_group=3):
    """
    Aynı CGRUP'tan gelen hisseleri sınırlar (maksimum 3 hisse)
    """
    if len(stocks_df) == 0:
        return stocks_df
    
    # CGRUP'a göre grupla
    cgroup_groups = stocks_df.groupby('CGRUP')
    limited_stocks = []
    
    for cgroup, group in cgroup_groups:
        print(f"      📊 CGRUP {cgroup}: {len(group)} hisse → maksimum {max_per_group} seçilebilir")
        
        if direction == 'LONG':
            # En yüksek Final FB skoruna sahip olanları seç
            selected = group.nlargest(max_per_group, 'Final FB')
        else:  # SHORT
            # En düşük Final SFS skoruna sahip olanları seç
            selected = group.nsmallest(max_per_group, 'Final SFS')
        
        limited_stocks.append(selected)
    
    if limited_stocks:
        return pd.concat(limited_stocks, ignore_index=True)
    else:
        return pd.DataFrame()

def process_ssfinekheldkuponlu_special(df, rules):
    """
    ssfinekheldkuponlu.csv için özel işleme:
    - C575, C600, C625 hariç her CGRUP'tan en iyi LONG ve en kötü SHORT zorunlu seçilir
    - CMON sınırlaması: Her şirketin toplam hisse sayısı / 1.6 (normal yuvarlama)
    - LONG ve SHORT ayrı ayrı değerlendirilir
    - Ek olarak kurallara uyan hisseler de seçilir
    """
    print(f"   🎯 Özel işleme: ssfinekheldkuponlu.csv")
    
    # Ortalama değerleri hesapla
    avg_final_fb = df['Final FB'].mean()
    avg_final_sfs = df['Final SFS'].mean()
    
    print(f"   📈 Ortalama Final FB: {avg_final_fb:.4f}")
    print(f"   📉 Ortalama Final SFS: {avg_final_sfs:.4f}")
    
    # CMON sınırlarını hesapla
    cmon_counts = df['CMON'].value_counts()
    cmon_limits_long = {}
    cmon_limits_short = {}
    
    print(f"   📊 CMON sınırları hesaplanıyor:")
    for cmon, count in cmon_counts.items():
        limit = max(1, round(count / 1.6))  # Minimum 1, normal yuvarlama
        cmon_limits_long[cmon] = limit
        cmon_limits_short[cmon] = limit
        print(f"      {cmon}: {count} hisse → maksimum {limit} LONG + {limit} SHORT")
    
    # CGRUP'a göre grupla
    cgroup_groups = df.groupby('CGRUP')
    
    all_long_stocks = []
    all_short_stocks = []
    used_cmons_long = {}  # CMON -> seçilen hisse sayısı
    used_cmons_short = {}  # CMON -> seçilen hisse sayısı
    
    # Önce zorunlu seçimleri yap (C600, C625 hariç)
    for cgroup, group in cgroup_groups:
        if cgroup.upper() in ['C600', 'C625']:
            print(f"   📊 CGRUP {cgroup}: Zorunlu seçim yok, sadece kurallara uyan hisseler seçilecek")
            continue
            
        print(f"   📊 CGRUP {cgroup}: Zorunlu seçim yapılıyor")
        
        # En iyi LONG'u bul (CMON sınırına uygun)
        best_long_candidates = group.nlargest(len(group), 'Final FB')
        best_long = None
        
        for _, candidate in best_long_candidates.iterrows():
            cmon = candidate['CMON']
            current_count = used_cmons_long.get(cmon, 0)
            max_allowed = cmon_limits_long.get(cmon, 1)
            if current_count < max_allowed:
                best_long = candidate
                used_cmons_long[cmon] = current_count + 1
                break
        
        # En kötü SHORT'u bul (CMON sınırına uygun)
        worst_short_candidates = group.nsmallest(len(group), 'Final SFS')
        worst_short = None
        
        for _, candidate in worst_short_candidates.iterrows():
            cmon = candidate['CMON']
            current_count = used_cmons_short.get(cmon, 0)
            max_allowed = cmon_limits_short.get(cmon, 1)
            if current_count < max_allowed:
                worst_short = candidate
                used_cmons_short[cmon] = current_count + 1
                break
        
        if best_long is not None:
            cmon = best_long['CMON']
            max_allowed = cmon_limits_long.get(cmon, 1)
            
            # LONG hisse için KUME_ORT ve KUME_PREM hesapla
            cmon_final_fbs = df[df['CMON'] == cmon]['Final FB']
            cmon_avg_final_fb = cmon_final_fbs.mean()
            
            # AVG_ADV ve RECSIZE hesapla
            avg_adv = best_long.get('AVG_ADV', 0)
            kume_prem = best_long['Final FB'] - cmon_avg_final_fb
            recsize = round((kume_prem * 8 + avg_adv / 25) / 4 / 100) * 100
            # AVG_ADV/6 sınırlaması
            max_recsize = round(avg_adv / 6 / 100) * 100
            recsize = min(recsize, max_recsize)
            
            # KUME_ORT ve KUME_PREM değerlerini row'a ekle
            best_long_dict = best_long.to_dict()
            best_long_dict['KUME_ORT'] = cmon_avg_final_fb
            best_long_dict['KUME_PREM'] = kume_prem
            best_long_dict['AVG_ADV'] = avg_adv
            best_long_dict['RECSIZE'] = recsize
            
            print(f"      🟢 Zorunlu LONG: {best_long['PREF IBKR']} ({cmon}) (Final FB={best_long['Final FB']:.4f}) [CMON kullanımı: {used_cmons_long[cmon]}/{max_allowed}]")
            all_long_stocks.append(best_long_dict)
        else:
            print(f"      ⚠️ CGRUP {cgroup}: Uygun LONG bulunamadı (CMON sınırı)")
        
        if worst_short is not None:
            cmon = worst_short['CMON']
            max_allowed = cmon_limits_short.get(cmon, 1)
            
            # SHORT hisse için KUME_ORT ve KUME_PREM hesapla
            cmon_final_sfs = df[df['CMON'] == cmon]['Final SFS']
            cmon_avg_final_sfs = cmon_final_sfs.mean()
            
            # AVG_ADV ve RECSIZE hesapla
            avg_adv = worst_short.get('AVG_ADV', 0)
            kume_prem = cmon_avg_final_sfs - worst_short['Final SFS']
            recsize = round((kume_prem * 8 + avg_adv / 25) / 4 / 100) * 100
            # AVG_ADV/6 sınırlaması
            max_recsize = round(avg_adv / 6 / 100) * 100
            recsize = min(recsize, max_recsize)
            
            # KUME_ORT ve KUME_PREM değerlerini row'a ekle
            worst_short_dict = worst_short.to_dict()
            worst_short_dict['KUME_ORT'] = cmon_avg_final_sfs
            worst_short_dict['KUME_PREM'] = kume_prem
            worst_short_dict['AVG_ADV'] = avg_adv
            worst_short_dict['RECSIZE'] = recsize
            
            print(f"      🔴 Zorunlu SHORT: {worst_short['PREF IBKR']} ({cmon}) (Final SFS={worst_short['Final SFS']:.4f}) [CMON kullanımı: {used_cmons_short[cmon]}/{max_allowed}]")
            all_short_stocks.append(worst_short_dict)
        else:
            print(f"      ⚠️ CGRUP {cgroup}: Uygun SHORT bulunamadı (CMON sınırı)")
    
    # Şimdi tüm CGRUP'lar için kurallara uyan hisseleri seç
    for cgroup, group in cgroup_groups:
        if cgroup.upper() in ['C600', 'C625']:
            print(f"   📊 CGRUP {cgroup}: Sadece kurallara uyan hisseler aranıyor (zorunlu seçim yok)")
        else:
            print(f"   📊 CGRUP {cgroup}: Kurallara uyan ek hisseler aranıyor")
        
        # Kurallara uyan hisseleri bul
        # LONG kriterleri: Top %30 + 1.35x ortalama
        top_count = math.ceil(len(group) * rules['long_percent'] / 100)
        top_stocks = group.nlargest(top_count, 'Final FB')
        long_candidates = group[group['Final FB'] >= (avg_final_fb * rules['long_multiplier'])]
        
        # Kesişim
        long_intersection = set(top_stocks['PREF IBKR']).intersection(set(long_candidates['PREF IBKR']))
        long_rule_stocks = group[group['PREF IBKR'].isin(long_intersection)]
        
        # SHORT kriterleri: Bottom %40 + 0.80x ortalama
        bottom_count = math.ceil(len(group) * rules['short_percent'] / 100)
        bottom_stocks = group.nsmallest(bottom_count, 'Final SFS')
        short_candidates = group[group['Final SFS'] <= (avg_final_sfs * rules['short_multiplier'])]
        
        # Kesişim
        short_intersection = set(bottom_stocks['PREF IBKR']).intersection(set(short_candidates['PREF IBKR']))
        short_rule_stocks = group[group['PREF IBKR'].isin(short_intersection)]
        
        # CMON sınırlaması uygula
        long_available = []
        for _, row in long_rule_stocks.iterrows():
            cmon = row['CMON']
            current_count = used_cmons_long.get(cmon, 0)
            max_allowed = cmon_limits_long.get(cmon, 1)
            if current_count < max_allowed:
                long_available.append(row)
        
        short_available = []
        for _, row in short_rule_stocks.iterrows():
            cmon = row['CMON']
            current_count = used_cmons_short.get(cmon, 0)
            max_allowed = cmon_limits_short.get(cmon, 1)
            if current_count < max_allowed:
                short_available.append(row)
        
        # Maksimum hisse sınırı
        if cgroup.upper() in ['C600', 'C625']:
            # Bu CGRUP'lar için zorunlu seçim yok, tüm 3 slot kullanılabilir
            max_extra_long = 3
            max_extra_short = 3
            selected_long_in_group = []
            selected_short_in_group = []
        else:
            # Diğer CGRUP'lar için zorunlu seçimler çıkarılır
            max_extra_long = 3  # Toplam 3 hisse per CGRUP
            max_extra_short = 3  # Toplam 3 hisse per CGRUP
            selected_long_in_group = [stock for stock in all_long_stocks if stock.get('CGRUP') == cgroup]
            selected_short_in_group = [stock for stock in all_short_stocks if stock.get('CGRUP') == cgroup]
        
        remaining_long_slots = max_extra_long - len(selected_long_in_group)
        remaining_short_slots = max_extra_short - len(selected_short_in_group)
        
        # En iyi hisseleri seç
        long_available.sort(key=lambda x: x['Final FB'], reverse=True)
        short_available.sort(key=lambda x: x['Final SFS'])
        
        for i, row in enumerate(long_available[:remaining_long_slots]):
            # LONG hisse için KUME_ORT ve KUME_PREM hesapla
            cmon = row['CMON']
            # Aynı CMON'daki tüm hisselerin Final FB ortalamasını hesapla
            cmon_final_fbs = df[df['CMON'] == cmon]['Final FB']
            cmon_avg_final_fb = cmon_final_fbs.mean()
            
            # AVG_ADV ve RECSIZE hesapla
            avg_adv = row.get('AVG_ADV', 0)
            kume_prem = row['Final FB'] - cmon_avg_final_fb
            recsize = round((kume_prem * 8 + avg_adv / 25) / 4 / 100) * 100
            # AVG_ADV/6 sınırlaması
            max_recsize = round(avg_adv / 6 / 100) * 100
            recsize = min(recsize, max_recsize)
            
            # KUME_ORT ve KUME_PREM değerlerini row'a ekle
            row_dict = row.to_dict()
            row_dict['KUME_ORT'] = cmon_avg_final_fb
            row_dict['KUME_PREM'] = kume_prem
            row_dict['AVG_ADV'] = avg_adv
            row_dict['RECSIZE'] = recsize
            
            all_long_stocks.append(row_dict)
            used_cmons_long[cmon] = used_cmons_long.get(cmon, 0) + 1
            max_allowed = cmon_limits_long.get(cmon, 1)
            print(f"      🟢 Ek LONG: {row['PREF IBKR']} ({cmon}) (Final FB={row['Final FB']:.4f}) [CMON kullanımı: {used_cmons_long[cmon]}/{max_allowed}]")
        
        for i, row in enumerate(short_available[:remaining_short_slots]):
            # SHORT hisse için KUME_ORT ve KUME_PREM hesapla
            cmon = row['CMON']
            # Aynı CMON'daki tüm hisselerin Final SFS ortalamasını hesapla
            cmon_final_sfs = df[df['CMON'] == cmon]['Final SFS']
            cmon_avg_final_sfs = cmon_final_sfs.mean()
            
            # AVG_ADV ve RECSIZE hesapla
            avg_adv = row.get('AVG_ADV', 0)
            kume_prem = cmon_avg_final_sfs - row['Final SFS']
            recsize = round((kume_prem * 8 + avg_adv / 25) / 4 / 100) * 100
            # AVG_ADV/6 sınırlaması
            max_recsize = round(avg_adv / 6 / 100) * 100
            recsize = min(recsize, max_recsize)
            
            # KUME_ORT ve KUME_PREM değerlerini row'a ekle
            row_dict = row.to_dict()
            row_dict['KUME_ORT'] = cmon_avg_final_sfs
            row_dict['KUME_PREM'] = kume_prem
            row_dict['AVG_ADV'] = avg_adv
            row_dict['RECSIZE'] = recsize
            
            all_short_stocks.append(row_dict)
            used_cmons_short[cmon] = used_cmons_short.get(cmon, 0) + 1
            max_allowed = cmon_limits_short.get(cmon, 1)
            print(f"      🔴 Ek SHORT: {row['PREF IBKR']} ({cmon}) (Final SFS={row['Final SFS']:.4f}) [CMON kullanımı: {used_cmons_short[cmon]}/{max_allowed}]")
    
    # DataFrame'e çevir ve unique satırları koru
    long_df = pd.DataFrame(all_long_stocks) if all_long_stocks else pd.DataFrame()
    short_df = pd.DataFrame(all_short_stocks) if all_short_stocks else pd.DataFrame()
    
    # Unique satırları koru (PREF IBKR'e göre)
    if not long_df.empty:
        long_df = long_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
    if not short_df.empty:
        short_df = short_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
    
    print(f"   📊 Toplam LONG: {len(long_df)} hisse")
    print(f"   📊 Toplam SHORT: {len(short_df)} hisse")
    print(f"   📊 Kullanılan CMON'lar (LONG): {len(used_cmons_long)}")
    print(f"   📊 Kullanılan CMON'lar (SHORT): {len(used_cmons_short)}")
    
    return long_df, short_df

def process_ssfinek_files():
    """
    SSFINEK dosyalarını işler ve Long/Short hisseleri seçer
    """
    print("🚀 SSFINEK DOSYALARINDAN LONG/SHORT HİSSELERİ SEÇİLİYOR...")
    print("=" * 80)
    
    # SSFINEK dosyalarını bul
    ssfinek_files = glob.glob('ssfinek*.csv')
    print(f"📁 Bulunan SSFINEK dosyaları: {len(ssfinek_files)} adet")
    
    all_long_stocks = []
    all_short_stocks = []
    
    for file_name in ssfinek_files:
        print(f"\n📊 İşleniyor: {file_name}")
        
        try:
            # Dosyayı oku
            df = pd.read_csv(file_name)
            print(f"   ✅ Dosya okundu: {len(df)} satır")
            
            if len(df) == 0:
                print(f"   ⚠️ Dosya boş, atlanıyor")
                continue
            
            # Gerekli kolonları kontrol et
            required_columns = ['PREF IBKR', 'Final FB', 'Final SFS', 'CMON']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                print(f"   ❌ Eksik kolonlar: {missing_columns}")
                continue
            
            # Dosya için özel kuralları al
            rules = get_file_specific_rules(file_name)
            
            # ssfinekheldkuponlu.csv için özel işleme
            if file_name == 'ssfinekheldkuponlu.csv':
                long_stocks_limited, short_stocks_limited = process_ssfinekheldkuponlu_special(df, rules)
            else:
                # Ortalama değerleri hesapla
                avg_final_fb = df['Final FB'].mean()
                avg_final_sfs = df['Final SFS'].mean()
                
                print(f"   📈 Ortalama Final FB: {avg_final_fb:.4f}")
                print(f"   📉 Ortalama Final SFS: {avg_final_sfs:.4f}")
                print(f"   📋 Kurallar: LONG {rules['long_percent']}% + {rules['long_multiplier']}x, SHORT {rules['short_percent']}% + {rules['short_multiplier']}x (Max: {rules['max_short']})")
                
                # LONG hisseleri seç
                long_candidates = df[df['Final FB'] >= (avg_final_fb * rules['long_multiplier'])].copy()
                long_candidates = long_candidates.sort_values('Final FB', ascending=False)
                
                # Top %X'i hesapla (yukarı yuvarlama)
                top_count = math.ceil(len(df) * rules['long_percent'] / 100)
                top_stocks = df.nlargest(top_count, 'Final FB')
                
                # İki kriterin kesişimini al
                long_candidates_set = set(long_candidates['PREF IBKR'])
                top_set = set(top_stocks['PREF IBKR'])
                long_intersection = long_candidates_set.intersection(top_set)
                
                # Kesişimdeki hisseleri al
                long_stocks = df[df['PREF IBKR'].isin(long_intersection)].copy()
                
                # Şirket sınırını uygula
                long_stocks_limited = limit_by_company(long_stocks, 'LONG', df) # original_df'i gönder
                
                print(f"   🟢 LONG kriterleri:")
                print(f"      - {rules['long_multiplier']}x ortalama kriteri: {len(long_candidates)} hisse")
                print(f"      - Top {rules['long_percent']}% kriteri: {len(top_stocks)} hisse")
                print(f"      - Kesişim: {len(long_stocks)} hisse")
                print(f"      - Şirket sınırı uygulandıktan sonra: {len(long_stocks_limited)} hisse")
                
                # SHORT hisseleri seç
                short_candidates = df[df['Final SFS'] <= (avg_final_sfs * rules['short_multiplier'])].copy()
                short_candidates = short_candidates.sort_values('Final SFS', ascending=True)
                
                # Bottom %X'i hesapla (yukarı yuvarlama)
                bottom_count = math.ceil(len(df) * rules['short_percent'] / 100)
                bottom_stocks = df.nsmallest(bottom_count, 'Final SFS')
                
                # İki kriterin kesişimini al
                short_candidates_set = set(short_candidates['PREF IBKR'])
                bottom_set = set(bottom_stocks['PREF IBKR'])
                short_intersection = short_candidates_set.intersection(bottom_set)
                
                # Kesişimdeki hisseleri al
                short_stocks = df[df['PREF IBKR'].isin(short_intersection)].copy()
                
                # SHORT sınırını uygula
                if len(short_stocks) > rules['max_short']:
                    print(f"   ⚠️ SHORT sınırı uygulanıyor: {len(short_stocks)} → {rules['max_short']}")
                    short_stocks = short_stocks.nsmallest(rules['max_short'], 'Final SFS')
                
                # Şirket sınırını uygula
                short_stocks_limited = limit_by_company(short_stocks, 'SHORT', df) # original_df'i gönder
                
                print(f"   🔴 SHORT kriterleri:")
                print(f"      - {rules['short_multiplier']}x ortalama kriteri: {len(short_candidates)} hisse")
                print(f"      - Bottom {rules['short_percent']}% kriteri: {len(bottom_stocks)} hisse")
                print(f"      - Kesişim: {len(short_intersection)} hisse")
                print(f"      - SHORT sınırı uygulandıktan sonra: {len(short_stocks)} hisse")
                print(f"      - Şirket sınırı uygulandıktan sonra: {len(short_stocks_limited)} hisse")
            
            # LONG hisseleri listeye ekle
            for _, row in long_stocks_limited.iterrows():
                # AVG_ADV ve RECSIZE hesapla
                avg_adv = row.get('AVG_ADV', 0)
                kume_prem = row['Final FB'] - avg_final_fb
                
                # HELDFF için özel RECSIZE kuralları
                if file_name == 'ssfinekheldff.csv':
                    recsize = round((kume_prem * 12 + avg_adv / 25) / 4 / 100) * 100
                    # AVG_ADV/4 sınırlaması (HELDFF için özel)
                    max_recsize = round(avg_adv / 4 / 100) * 100
                else:
                    recsize = round((kume_prem * 8 + avg_adv / 25) / 4 / 100) * 100
                    # AVG_ADV/6 sınırlaması (diğer gruplar için)
                    max_recsize = round(avg_adv / 6 / 100) * 100
                
                recsize = min(recsize, max_recsize)
                
                stock_info = {
                    'DOSYA': file_name,
                    'PREF_IBKR': row['PREF IBKR'],
                    'Final FB': row['Final FB'],
                    'Final SFS': row['Final SFS'],
                    'SMI': row.get('SMI', 'N/A'),
                    'CGRUP': row.get('CGRUP', 'N/A'),
                    'CMON': row.get('CMON', 'N/A'),
                    'TİP': 'LONG',
                    'ORTALAMA_FINAL_FB': avg_final_fb,
                    'ORTALAMA_FINAL_SFS': avg_final_sfs,
                    'LONG_KURAL': f"Top {rules['long_percent']}% + {rules['long_multiplier']}x",
                    'SHORT_KURAL': f"Bottom {rules['short_percent']}% + {rules['short_multiplier']}x",
                    'KUME_ORT': avg_final_fb,
                    'KUME_PREM': kume_prem,
                    'AVG_ADV': avg_adv,
                    'RECSIZE': recsize
                }
                all_long_stocks.append(stock_info)
            
            # SHORT hisseleri listeye ekle
            for _, row in short_stocks_limited.iterrows():
                # AVG_ADV ve RECSIZE hesapla
                avg_adv = row.get('AVG_ADV', 0)
                kume_prem = avg_final_sfs - row['Final SFS']
                
                # HELDFF için özel RECSIZE kuralları
                if file_name == 'ssfinekheldff.csv':
                    recsize = round((kume_prem * 12 + avg_adv / 25) / 4 / 100) * 100
                    # AVG_ADV/4 sınırlaması (HELDFF için özel)
                    max_recsize = round(avg_adv / 4 / 100) * 100
                else:
                    recsize = round((kume_prem * 8 + avg_adv / 25) / 4 / 100) * 100
                    # AVG_ADV/6 sınırlaması (diğer gruplar için)
                    max_recsize = round(avg_adv / 6 / 100) * 100
                
                recsize = min(recsize, max_recsize)
                
                stock_info = {
                    'DOSYA': file_name,
                    'PREF_IBKR': row['PREF IBKR'],
                    'Final FB': row['Final FB'],
                    'Final SFS': row['Final SFS'],
                    'SMI': row.get('SMI', 'N/A'),
                    'CGRUP': row.get('CGRUP', 'N/A'),
                    'CMON': row.get('CMON', 'N/A'),
                    'TİP': 'SHORT',
                    'ORTALAMA_FINAL_FB': avg_final_fb,
                    'ORTALAMA_FINAL_SFS': avg_final_sfs,
                    'LONG_KURAL': f"Top {rules['long_percent']}% + {rules['long_multiplier']}x",
                    'SHORT_KURAL': f"Bottom {rules['short_percent']}% + {rules['short_multiplier']}x",
                    'KUME_ORT': avg_final_sfs,
                    'KUME_PREM': kume_prem,
                    'AVG_ADV': avg_adv,
                    'RECSIZE': recsize
                }
                all_short_stocks.append(stock_info)
            
            # Seçilen hisseleri göster
            if len(long_stocks_limited) > 0:
                print(f"   🟢 LONG seçilen hisseler:")
                for _, row in long_stocks_limited.iterrows():
                    print(f"      - {row['PREF IBKR']} ({row['CMON']}): Final FB={row['Final FB']:.4f}")
            
            if len(short_stocks_limited) > 0:
                print(f"   🔴 SHORT seçilen hisseler:")
                for _, row in short_stocks_limited.iterrows():
                    print(f"      - {row['PREF IBKR']} ({row['CMON']}): Final SFS={row['Final SFS']:.4f}")
            
        except Exception as e:
            print(f"   ❌ Hata oluştu: {e}")
            continue
    
    # Tüm sonuçları birleştir
    all_stocks = all_long_stocks + all_short_stocks
    
    if all_stocks:
        # DataFrame'e çevir
        result_df = pd.DataFrame(all_stocks)
        
        # LONG ve SHORT hisseleri ayır
        long_df = result_df[result_df['TİP'] == 'LONG'].copy()
        short_df = result_df[result_df['TİP'] == 'SHORT'].copy()
        
        # LONG hisseleri kaydet
        if not long_df.empty:
            long_output_file = 'tumcsvlong.csv'
            print(f"\n💾 LONG hisseler kaydediliyor: {long_output_file}")
            long_df.to_csv(long_output_file, index=False)
            print(f"✅ Başarıyla kaydedildi: {long_output_file}")
            print(f"📊 Toplam {len(long_df)} LONG hisse seçildi")
        else:
            print(f"\n⚠️ LONG hisse seçilemedi!")
        
        # SHORT hisseleri kaydet
        if not short_df.empty:
            short_output_file = 'tumcsvshort.csv'
            print(f"\n💾 SHORT hisseler kaydediliyor: {short_output_file}")
            short_df.to_csv(short_output_file, index=False)
            print(f"✅ Başarıyla kaydedildi: {short_output_file}")
            print(f"📊 Toplam {len(short_df)} SHORT hisse seçildi")
        else:
            print(f"\n⚠️ SHORT hisse seçilemedi!")
        
        print(f"\n📊 Özet:")
        print(f"   🟢 LONG: {len(long_df)} hisse")
        print(f"   🔴 SHORT: {len(short_df)} hisse")
        print(f"   📋 Toplam: {len(result_df)} hisse")
        
        return result_df
    else:
        print("❌ Hiç hisse seçilemedi!")
        return None

def main():
    print("🎯 SSFINEK DOSYALARINDAN LONG/SHORT HİSSELERİ SEÇİLİYOR...")
    print("=" * 80)
    
    # Ana işlemi yap
    result = process_ssfinek_files()
    
    if result is not None:
        print(f"\n✅ Tüm işlemler tamamlandı!")
        print(f"📁 Sonuç dosyaları:")
        print(f"   🟢 LONG: tumcsvlong.csv")
        print(f"   🔴 SHORT: tumcsvshort.csv")
    else:
        print(f"\n❌ İşlem başarısız!")

if __name__ == "__main__":
    main() 