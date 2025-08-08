import pandas as pd
import numpy as np

def check_credit_scores():
    """Tüm hisselerin credit score'larını kontrol et"""
    
    # Sonuç dosyasını oku
    try:
        df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
        print(f"Dosya okundu: {len(df)} satır")
    except FileNotFoundError:
        print("allcomek_sld.csv dosyası bulunamadı!")
        return
    
    # Credit score'a göre sırala
    credit_sorted = df.sort_values('CRDT_SCORE', ascending=False)
    
    print("\n" + "="*80)
    print("EN YÜKSEK CREDIT SCORE'LAR")
    print("="*80)
    
    print(f"{'CMON':<8} | {'PREF IBKR':<12} | {'Market Cap(B$)':<15} | {'CRDT_SCORE':<12} | {'CRDT_NORM':<10} | {'SOLIDITY_NORM':<12}")
    print("-"*80)
    
    # Top 20 credit score'u göster
    for idx, row in credit_sorted.head(20).iterrows():
        print(f"{row['CMON']:<8} | {row['PREF IBKR']:<12} | {row['COM_MKTCAP']:<15.2f} | {row['CRDT_SCORE']:<12.2f} | {row['CRDT_NORM']:<10.2f} | {row['SOLIDITY_SCORE_NORM']:<12.2f}")
    
    # EAI, ELC, EMP'yi özel olarak ara
    print("\n" + "="*80)
    print("EAI, ELC, EMP HİSSELERİ")
    print("="*80)
    
    eai_elc_emp = df[df['CMON'].isin(['EAI', 'ELC', 'EMP'])]
    
    if not eai_elc_emp.empty:
        print(f"{'CMON':<8} | {'PREF IBKR':<12} | {'Market Cap(B$)':<15} | {'CRDT_SCORE':<12} | {'CRDT_NORM':<10} | {'SOLIDITY_NORM':<12}")
        print("-"*80)
        
        for idx, row in eai_elc_emp.iterrows():
            print(f"{row['CMON']:<8} | {row['PREF IBKR']:<12} | {row['COM_MKTCAP']:<15.2f} | {row['CRDT_SCORE']:<12.2f} | {row['CRDT_NORM']:<10.2f} | {row['SOLIDITY_SCORE_NORM']:<12.2f}")
    else:
        print("EAI, ELC, EMP hisseleri bulunamadı!")
    
    # APO'yu da göster
    print("\n" + "="*80)
    print("APO HİSSESİ")
    print("="*80)
    
    apo = df[df['CMON'] == 'APO']
    
    if not apo.empty:
        print(f"{'CMON':<8} | {'PREF IBKR':<12} | {'Market Cap(B$)':<15} | {'CRDT_SCORE':<12} | {'CRDT_NORM':<10} | {'SOLIDITY_NORM':<12}")
        print("-"*80)
        
        for idx, row in apo.iterrows():
            print(f"{row['CMON']:<8} | {row['PREF IBKR']:<12} | {row['COM_MKTCAP']:<15.2f} | {row['CRDT_SCORE']:<12.2f} | {row['CRDT_NORM']:<10.2f} | {row['SOLIDITY_SCORE_NORM']:<12.2f}")
    
    # İstatistikler
    print("\n" + "="*80)
    print("CREDIT SCORE İSTATİSTİKLERİ")
    print("="*80)
    
    print(f"En yüksek Credit Score: {df['CRDT_SCORE'].max():.2f}")
    print(f"En düşük Credit Score: {df['CRDT_SCORE'].min():.2f}")
    print(f"Ortalama Credit Score: {df['CRDT_SCORE'].mean():.2f}")
    print(f"APO Credit Score: {apo['CRDT_SCORE'].iloc[0] if not apo.empty else 'N/A'}")
    
    # Credit score 13.00 ve üzeri olan hisseler
    high_credit = df[df['CRDT_SCORE'] >= 13.00]
    print(f"\nCredit Score 13.00 ve üzeri hisse sayısı: {len(high_credit)}")
    
    if not high_credit.empty:
        print("\nCredit Score 13.00+ Hisseler:")
        for idx, row in high_credit.iterrows():
            print(f"  {row['CMON']} ({row['PREF IBKR']}): {row['CRDT_SCORE']:.2f}")

if __name__ == "__main__":
    check_credit_scores() 