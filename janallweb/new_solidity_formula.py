import pandas as pd
import numpy as np

def analyze_current_scores():
    """Mevcut solidity skorlarını analiz et"""
    try:
        df = pd.read_csv('sldekheldkuponlu.csv', encoding='utf-8-sig')
        
        # Şirket bazında grupla
        company_scores = df.groupby('CMON').agg({
            'SOLIDITY_SCORE': 'mean',
            'COM_MKTCAP': 'mean',
            'CRDT_SCORE': 'mean',
            'COM_LAST_PRICE': 'mean',
            'COM_52W_HIGH': 'mean',
            'COM_5Y_HIGH': 'mean'
        }).round(2)
        
        print("=== MEVCUT SOLIDITY SKORLARI ===")
        print(company_scores.sort_values('SOLIDITY_SCORE', ascending=False))
        
        return company_scores
        
    except Exception as e:
        print(f"Analiz hatası: {e}")
        return None

def calculate_market_cap_weight(market_cap_billions):
    """
    Market cap'e göre ağırlık hesapla - Daha detaylı aralıklar
    Küçük şirketlerde performans daha önemli
    """
    if market_cap_billions < 1:
        return 0.8  # Performans çok önemli (80%)
    elif market_cap_billions < 3:
        return 0.75  # Performans çok önemli (75%)
    elif market_cap_billions < 6:
        return 0.7   # Performans önemli (70%)
    elif market_cap_billions < 10:
        return 0.65  # Performans önemli (65%)
    elif market_cap_billions < 15:
        return 0.6   # Performans orta önemli (60%)
    elif market_cap_billions < 25:
        return 0.55  # Performans orta önemli (55%)
    elif market_cap_billions < 40:
        return 0.5   # Performans orta (50%)
    elif market_cap_billions < 70:
        return 0.45  # Performans az önemli (45%)
    elif market_cap_billions < 130:
        return 0.4   # Performans az önemli (40%)
    elif market_cap_billions < 200:
        return 0.35  # Performans çok az önemli (35%)
    elif market_cap_billions < 400:
        return 0.3   # Performans çok az önemli (30%)
    else:  # 400B+
        return 0.25  # Performans minimal önemli (25%)

def calculate_performance_score(row):
    """
    Performans skoru hesapla - COVID low'larına yakınlık da dahil
    """
    try:
        # High skorları
        high_52w = (row['COM_LAST_PRICE'] / row['COM_52W_HIGH']) if row['COM_52W_HIGH'] > 0 else 0.5
        high_5y = (row['COM_LAST_PRICE'] / row['COM_5Y_HIGH']) if row['COM_5Y_HIGH'] > 0 else 0.5
        
        # High skorlarını 10-90 aralığına normalize et
        high_52w_norm = max(10, min(90, 90 * high_52w))
        high_5y_norm = max(10, min(90, 90 * high_5y))
        
        # Ortalama high skoru
        avg_high_score = (high_52w_norm + high_5y_norm) / 2
        
        # Son dönem performansı (3M ve 6M)
        perf_3m = (row['COM_LAST_PRICE'] / row['COM_3M_PRICE'] - 1) if row['COM_3M_PRICE'] > 0 else 0
        perf_6m = (row['COM_LAST_PRICE'] / row['COM_6M_PRICE'] - 1) if row['COM_6M_PRICE'] > 0 else 0
        
        # Performans skoru (0-100 aralığında)
        recent_perf = (perf_3m + perf_6m) * 100
        recent_perf_norm = max(10, min(90, 50 + recent_perf))
        
        # COVID low'larına yakınlık kontrolü (FEB2020 ve MAR2020)
        covid_penalty = 0
        if pd.notna(row['COM_FEB2020_PRICE']) and row['COM_FEB2020_PRICE'] > 0:
            covid_ratio = row['COM_LAST_PRICE'] / row['COM_FEB2020_PRICE']
            if covid_ratio < 1.2:  # COVID low'larına çok yakın
                covid_penalty = -15
            elif covid_ratio < 1.5:  # COVID low'larına yakın
                covid_penalty = -10
            elif covid_ratio < 2.0:  # COVID low'larına orta yakın
                covid_penalty = -5
        
        if pd.notna(row['COM_MAR2020_PRICE']) and row['COM_MAR2020_PRICE'] > 0:
            covid_ratio_mar = row['COM_LAST_PRICE'] / row['COM_MAR2020_PRICE']
            if covid_ratio_mar < 1.2:  # COVID low'larına çok yakın
                covid_penalty = min(covid_penalty, -15)
            elif covid_ratio_mar < 1.5:  # COVID low'larına yakın
                covid_penalty = min(covid_penalty, -10)
            elif covid_ratio_mar < 2.0:  # COVID low'larına orta yakın
                covid_penalty = min(covid_penalty, -5)
        
        # Toplam performans skoru
        performance_score = (avg_high_score * 0.6 + recent_perf_norm * 0.4) + covid_penalty
        
        return max(10, min(90, performance_score))
        
    except Exception as e:
        print(f"Performans skoru hesaplama hatası: {e}")
        return 50

def calculate_market_cap_score(market_cap_billions):
    """
    Market cap skoru hesapla - Daha detaylı aralıklar
    """
    try:
        if market_cap_billions <= 0:
            return 35
        
        # Puanlama aralıkları - Daha detaylı
        if market_cap_billions >= 400:     # 400B+
            return 95
        elif market_cap_billions >= 200:   # 200-400B
            return 90 + ((market_cap_billions - 200) / 200) * 5
        elif market_cap_billions >= 130:   # 130-200B
            return 85 + ((market_cap_billions - 130) / 70) * 5
        elif market_cap_billions >= 70:    # 70-130B
            return 80 + ((market_cap_billions - 70) / 60) * 5
        elif market_cap_billions >= 40:    # 40-70B
            return 75 + ((market_cap_billions - 40) / 30) * 5
        elif market_cap_billions >= 25:    # 25-40B
            return 70 + ((market_cap_billions - 25) / 15) * 5
        elif market_cap_billions >= 15:    # 15-25B
            return 65 + ((market_cap_billions - 15) / 10) * 5
        elif market_cap_billions >= 10:    # 10-15B
            return 60 + ((market_cap_billions - 10) / 5) * 5
        elif market_cap_billions >= 6:     # 6-10B
            return 55 + ((market_cap_billions - 6) / 4) * 5
        elif market_cap_billions >= 3:     # 3-6B
            return 50 + ((market_cap_billions - 3) / 3) * 5
        elif market_cap_billions >= 1:     # 1-3B
            return 45 + ((market_cap_billions - 1) / 2) * 5
        else:                              # <1B
            return max(35, 35 + (market_cap_billions * 10))
            
    except Exception as e:
        print(f"Market cap skoru hesaplama hatası: {e}")
        return 35

def calculate_credit_score(credit_rating):
    """
    Credit rating skoru hesapla
    """
    try:
        if pd.isna(credit_rating):
            return 50
        
        credit_rating = float(credit_rating)
        
        # Credit rating skorlama
        if credit_rating >= 15:     # Çok yüksek
            return 95
        elif credit_rating >= 12:   # Yüksek
            return 85
        elif credit_rating >= 10:   # Orta-yüksek
            return 75
        elif credit_rating >= 8:    # Orta
            return 65
        elif credit_rating >= 6:    # Orta-düşük
            return 55
        else:                       # Düşük
            return 45
            
    except Exception as e:
        print(f"Credit skoru hesaplama hatası: {e}")
        return 50

def calculate_new_solidity_score(row):
    """
    Yeni solidity skoru hesapla - Market cap'e göre dinamik ağırlıklandırma
    """
    try:
        # Market cap'i milyar dolar cinsinden al
        market_cap_billions = row['COM_MKTCAP'] if pd.notna(row['COM_MKTCAP']) else 1
        
        # Market cap ağırlığını hesapla
        performance_weight = calculate_market_cap_weight(market_cap_billions)
        market_cap_weight = 1 - performance_weight
        
        # Skorları hesapla
        performance_score = calculate_performance_score(row)
        market_cap_score = calculate_market_cap_score(market_cap_billions)
        credit_score = calculate_credit_score(row['CRDT_SCORE'])
        
        # Yeni solidity skoru - Dinamik ağırlıklandırma
        new_solidity = (
            performance_score * performance_weight +
            market_cap_score * 0.4 +
            credit_score * 0.2
        )
        
        # BB bonusu
        if str(row['Type']).strip() == 'BB':
            new_solidity *= 1.02
        
        return round(new_solidity, 2)
        
    except Exception as e:
        print(f"Yeni solidity hesaplama hatası ({row['PREF IBKR']}): {e}")
        return 50

def apply_new_formula():
    """Yeni formülü uygula"""
    try:
        # Veriyi oku
        df = pd.read_csv('sldekheldkuponlu.csv', encoding='utf-8-sig')
        
        print("Yeni solidity skorları hesaplanıyor...")
        
        # Yeni solidity skorunu hesapla
        df['NEW_SOLIDITY_SCORE'] = df.apply(calculate_new_solidity_score, axis=1)
        
        # Şirket bazında sonuçları göster
        company_results = df.groupby('CMON').agg({
            'NEW_SOLIDITY_SCORE': 'mean',
            'COM_MKTCAP': 'mean',
            'CRDT_SCORE': 'mean',
            'SOLIDITY_SCORE': 'mean'  # Eski skor
        }).round(2)
        
        print("\n=== YENİ SOLIDITY SKORLARI ===")
        print("CMON    | Yeni Skor | Eski Skor | Market Cap | Credit | Fark")
        print("--------|-----------|-----------|------------|--------|------")
        
        for company, row in company_results.iterrows():
            new_score = row['NEW_SOLIDITY_SCORE']
            old_score = row['SOLIDITY_SCORE']
            market_cap = row['COM_MKTCAP']
            credit = row['CRDT_SCORE']
            diff = new_score - old_score
            
            print(f"{company:<8}| {new_score:>9.2f} | {old_score:>9.2f} | {market_cap:>10.1f} | {credit:>6.1f} | {diff:>+5.2f}")
        
        # Hedef skorlarla karşılaştır
        target_scores = {
            'JPM': 85, 'BAC': 80, 'ETR': 80, 'WFC': 76, 'T': 73, 'ACGL': 63,
            'CMS': 65, 'COF': 68, 'DLR': 66, 'DTE': 68, 'EQH': 65, 'MET': 74,
            'ALL': 74, 'PSA': 74, 'SF': 63, 'F': 53, 'DUK': 78, 'CNO': 48,
            'AFG': 58, 'AGM': 45, 'FCNCA': 65, 'CFG': 62, 'FITB': 68
        }
        
        print("\n=== HEDEF SKORLARLA KARŞILAŞTIRMA ===")
        print("CMON    | Yeni Skor | Hedef Skor | Fark")
        print("--------|-----------|------------|------")
        
        for company, target in target_scores.items():
            if company in company_results.index:
                new_score = company_results.loc[company, 'NEW_SOLIDITY_SCORE']
                diff = new_score - target
                print(f"{company:<8}| {new_score:>9.2f} | {target:>10.0f} | {diff:>+5.2f}")
        
        # Market cap aralıklarını göster
        print("\n=== MARKET CAP ARALIKLARI VE AĞIRLIKLAR ===")
        ranges = [
            (0, 1, "0-1B", 0.8),
            (1, 3, "1-3B", 0.75),
            (3, 6, "3-6B", 0.7),
            (6, 10, "6-10B", 0.65),
            (10, 15, "10-15B", 0.6),
            (15, 25, "15-25B", 0.55),
            (25, 40, "25-40B", 0.5),
            (40, 70, "40-70B", 0.45),
            (70, 130, "70-130B", 0.4),
            (130, 200, "130-200B", 0.35),
            (200, 400, "200-400B", 0.3),
            (400, float('inf'), "400B+", 0.25)
        ]
        
        print("Aralık    | Performans Ağırlığı | Market Cap Ağırlığı")
        print("----------|-------------------|-------------------")
        for start, end, label, perf_weight in ranges:
            mcap_weight = 1 - perf_weight
            print(f"{label:<10}| {perf_weight*100:>17.0f}% | {mcap_weight*100:>17.0f}%")
        
        # Sonuçları CSV'ye kaydet
        output_filename = 'new_solidity_scores.csv'
        df.to_csv(output_filename, index=False, encoding='utf-8-sig')
        print(f"\nSonuçlar '{output_filename}' dosyasına kaydedildi.")
        
        return df
        
    except Exception as e:
        print(f"Formül uygulama hatası: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Ana fonksiyon"""
    print("=== YENİ SOLIDITY FORMÜLÜ ANALİZİ ===")
    
    # Mevcut skorları analiz et
    current_scores = analyze_current_scores()
    
    # Yeni formülü uygula
    new_results = apply_new_formula()
    
    if new_results is not None:
        print("\n=== FORMÜL ÖZETİ ===")
        print("1. Market Cap'e göre dinamik ağırlıklandırma")
        print("2. Performans skoru: High'lara yakınlık + son dönem performansı + COVID low'larına yakınlık")
        print("3. Market Cap skoru: Detaylı logaritmik normalizasyon")
        print("4. Credit skoru: Rating'e göre puanlama")
        print("5. BB bonusu: %2 artış")
        print("\nÖzellikler:")
        print("- Küçük şirketlerde performans daha önemli")
        print("- COVID low'larına yakınlık cezası")
        print("- Büyük şirketlerde performans etkisi azalır")

if __name__ == '__main__':
    main() 