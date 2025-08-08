import pandas as pd
from collections import defaultdict
import json

def load_and_group_stocks():
    """nalltogether.csv ve nnotheldpff.csv dosyalarını yükle ve common stock'lara göre grupla"""
    
    alltogether_df = pd.DataFrame()
    notheldpff_df = pd.DataFrame()
    
    # nalltogether.csv dosyasını yükle
    try:
        alltogether_df = pd.read_csv('nalltogether.csv')
        print(f"nalltogether.csv yüklendi: {len(alltogether_df)} satır")
    except FileNotFoundError:
        print("nalltogether.csv dosyası bulunamadı!")
    
    # nnotheldpff.csv dosyasını yükle
    try:
        notheldpff_df = pd.read_csv('nnotheldpff.csv')
        print(f"nnotheldpff.csv yüklendi: {len(notheldpff_df)} satır")
    except FileNotFoundError:
        print("nnotheldpff.csv dosyası bulunamadı!")
    
    # Her iki dosyayı birleştir
    combined_df = pd.concat([alltogether_df, notheldpff_df], ignore_index=True)
    print(f"Birleştirilmiş toplam veri: {len(combined_df)} satır")
    
    # CMON kolonuna göre grupla
    groups = defaultdict(list)
    
    for idx, row in combined_df.iterrows():
        cmon = row.get('CMON', '')
        if pd.isna(cmon) or cmon == '' or cmon == '-':
            cmon = 'UNKNOWN'
        
        # Her hisse için bilgileri sakla
        stock_info = {
            'PREF IBKR': row.get('PREF IBKR', ''),
            'CMON': cmon,
            'DIV AMOUNT': row.get('DIV AMOUNT', ''),
            'COUPON': row.get('COUPON', ''),
            'EX-DIV DATE': row.get('EX-DIV DATE', ''),
            'CALL DATE': row.get('CALL DATE', ''),
            'MATUR DATE': row.get('MATUR DATE', ''),
            'CRDT_SCORE': row.get('CRDT_SCORE', ''),
            'BOND_': row.get('BOND_', ''),
            'Aug2022_Price': row.get('Aug2022_Price', ''),
            'Oct19_Price': row.get('Oct19_Price', ''),
            'CGRUP': row.get('CGRUP', ''),
            'Source': 'nalltogether.csv' if idx < len(alltogether_df) else 'nnotheldpff.csv'
        }
        
        groups[cmon].append(stock_info)
    
    return groups, combined_df

def analyze_groups(groups):
    """Grupları analiz et ve istatistikleri göster"""
    
    print("\n" + "="*80)
    print("COMMON STOCK GRUPLARI ANALİZİ")
    print("="*80)
    
    # Grup istatistikleri
    group_stats = []
    
    for cmon, stocks in groups.items():
        if cmon == 'UNKNOWN':
            continue
            
        group_info = {
            'CMON': cmon,
            'Total_Stocks': len(stocks),
            'Stocks': stocks,
            'Avg_Div_Amount': 0,
            'Avg_Coupon': 0,
            'Callable_Count': 0,
            'Mature_Count': 0
        }
        
        # Ortalama hesaplamaları
        div_amounts = []
        coupons = []
        
        for stock in stocks:
            # DIV AMOUNT hesapla
            div_amount = stock.get('DIV AMOUNT', '')
            if div_amount and div_amount != '':
                try:
                    div_amounts.append(float(div_amount))
                except:
                    pass
            
            # COUPON hesapla
            coupon = stock.get('COUPON', '')
            if coupon and coupon != '':
                try:
                    # % işaretini kaldır
                    coupon = str(coupon).replace('%', '')
                    coupons.append(float(coupon))
                except:
                    pass
            
            # Callable/Mature kontrolü
            if stock.get('CALL DATE', '') and stock.get('CALL DATE', '') != '':
                group_info['Callable_Count'] += 1
            
            if stock.get('MATUR DATE', '') and stock.get('MATUR DATE', '') != '':
                group_info['Mature_Count'] += 1
        
        if div_amounts:
            group_info['Avg_Div_Amount'] = sum(div_amounts) / len(div_amounts)
        
        if coupons:
            group_info['Avg_Coupon'] = sum(coupons) / len(coupons)
        
        group_stats.append(group_info)
    
    # Hisselerin sayısına göre sırala (büyükten küçüğe)
    group_stats.sort(key=lambda x: x['Total_Stocks'], reverse=True)
    
    # Sonuçları göster
    print(f"\nToplam {len(group_stats)} farklı common stock grubu bulundu:")
    print("-" * 80)
    print(f"{'CMON':<10} {'Hisse Sayısı':<12} {'Ort. Div':<10} {'Ort. Coupon':<12} {'Callable':<8} {'Mature':<8}")
    print("-" * 80)
    
    for group in group_stats:
        print(f"{group['CMON']:<10} {group['Total_Stocks']:<12} "
              f"{group['Avg_Div_Amount']:<10.2f} {group['Avg_Coupon']:<12.2f}% "
              f"{group['Callable_Count']:<8} {group['Mature_Count']:<8}")
    
    return group_stats

def save_detailed_groups(group_stats):
    """Detaylı grup bilgilerini dosyaya kaydet"""
    
    # JSON formatında kaydet
    with open('common_stock_groups.json', 'w', encoding='utf-8') as f:
        json.dump(group_stats, f, indent=2, ensure_ascii=False)
    
    # CSV formatında da kaydet
    csv_data = []
    for group in group_stats:
        for stock in group['Stocks']:
            csv_data.append({
                'CMON': group['CMON'],
                'Total_Stocks_In_Group': group['Total_Stocks'],
                'PREF IBKR': stock['PREF IBKR'],
                'DIV AMOUNT': stock['DIV AMOUNT'],
                'COUPON': stock['COUPON'],
                'EX-DIV DATE': stock['EX-DIV DATE'],
                'CALL DATE': stock['CALL DATE'],
                'MATUR DATE': stock['MATUR DATE'],
                'CRDT_SCORE': stock['CRDT_SCORE'],
                'BOND_': stock['BOND_'],
                'Aug2022_Price': stock['Aug2022_Price'],
                'Oct19_Price': stock['Oct19_Price'],
                'CGRUP': stock['CGRUP'],
                'Source': stock['Source']
            })
    
    df = pd.DataFrame(csv_data)
    df.to_csv('common_stock_groups.csv', index=False, encoding='utf-8-sig')
    
    print(f"\n✓ Detaylı grup bilgileri kaydedildi:")
    print(f"  - common_stock_groups.json")
    print(f"  - common_stock_groups.csv")

def show_top_groups(group_stats, top_n=10):
    """En büyük grupları detaylı göster"""
    
    print(f"\n" + "="*80)
    print(f"EN BÜYÜK {top_n} COMMON STOCK GRUBU")
    print("="*80)
    
    for i, group in enumerate(group_stats[:top_n]):
        print(f"\n{i+1}. {group['CMON']} - {group['Total_Stocks']} hisse")
        print("-" * 50)
        
        # Hisseleri listele
        for j, stock in enumerate(group['Stocks'], 1):
            print(f"  {j:2d}. {stock['PREF IBKR']:<15} "
                  f"Div: {stock['DIV AMOUNT']:<8} "
                  f"Coupon: {stock['COUPON']:<8} "
                  f"Source: {stock['Source']}")
        
        # Grup özeti
        print(f"  Ortalama Div: {group['Avg_Div_Amount']:.2f}")
        print(f"  Ortalama Coupon: {group['Avg_Coupon']:.2f}%")
        print(f"  Callable: {group['Callable_Count']}, Mature: {group['Mature_Count']}")

def main():
    """Ana fonksiyon"""
    
    print("Common Stock Gruplandırma Analizi Başlıyor...")
    print("="*80)
    
    # Verileri yükle ve grupla
    groups, combined_df = load_and_group_stocks()
    
    # Grupları analiz et
    group_stats = analyze_groups(groups)
    
    # Detaylı sonuçları kaydet
    save_detailed_groups(group_stats)
    
    # En büyük grupları göster
    show_top_groups(group_stats, top_n=15)
    
    # Özet istatistikler
    print(f"\n" + "="*80)
    print("ÖZET İSTATİSTİKLER")
    print("="*80)
    
    total_stocks = sum(group['Total_Stocks'] for group in group_stats)
    total_groups = len(group_stats)
    
    print(f"Toplam hisse sayısı: {total_stocks}")
    print(f"Toplam common stock grubu: {total_groups}")
    print(f"Ortalama grup büyüklüğü: {total_stocks/total_groups:.1f} hisse/grup")
    
    # En büyük 5 grup
    top_5_total = sum(group['Total_Stocks'] for group in group_stats[:5])
    print(f"En büyük 5 gruptaki toplam hisse: {top_5_total} ({top_5_total/total_stocks*100:.1f}%)")
    
    print(f"\n✓ Analiz tamamlandı! Sonuçlar dosyalara kaydedildi.")

if __name__ == "__main__":
    main() 