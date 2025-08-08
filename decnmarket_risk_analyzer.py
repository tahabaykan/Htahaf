import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from ib_insync import IB, Stock, util
from simulation_helper import get_simulation_filename, is_simulation_mode

# Risk analizi için kullanılacak ETF'ler ve endeksler
RISK_INDICATORS = {
    "RISK_ON": ["SPY", "IWM", "HYG", "KRE"],  # Risk iştahının arttığı durumlarda yükselen
    "RISK_OFF": ["TLT", "VXX"]                # Güvenli liman arandığında yükselen
}

# --- SMA hesaplama fonksiyonu ---
def calculate_sma(df, window):
    return df['close'].rolling(window=window).mean()

def calculate_sma_diffs(df):
    sma20 = calculate_sma(df, 20)
    sma100 = calculate_sma(df, 100)
    sma200 = calculate_sma(df, 200)
    last_close = df['close'].iloc[-1]
    diff20 = (last_close - sma20.iloc[-1]) / sma20.iloc[-1] * 100 if not np.isnan(sma20.iloc[-1]) else np.nan
    diff100 = (last_close - sma100.iloc[-1]) / sma100.iloc[-1] * 100 if not np.isnan(sma100.iloc[-1]) else np.nan
    diff200 = (last_close - sma200.iloc[-1]) / sma200.iloc[-1] * 100 if not np.isnan(sma200.iloc[-1]) else np.nan
    return diff20, diff100, diff200

def connect_to_ibkr():
    """IBKR'ye bağlanır"""
    print("IBKR bağlantısı kuruluyor...")
    ib = IB()
    # TWS ve Gateway portlarını dene, öncelik TWS'de olsun
    ports = [7496, 4001]  # TWS ve Gateway portları
    connected = False
    for port in ports:
        try:
            service_name = "TWS" if port == 7496 else "Gateway"
            print(f"{service_name} ({port}) bağlantı deneniyor...")
            ib.connect('127.0.0.1', port, clientId=2, readonly=True, timeout=20)
            connected = True
            print(f"{service_name} ({port}) ile bağlantı başarılı!")
            break
        except Exception as e:
            print(f"{service_name} ({port}) bağlantı hatası: {e}")
    if not connected:
        print("IBKR bağlantısı kurulamadı! TWS veya Gateway çalışıyor mu?")
        return None
    return ib

def get_historical_data(ib, symbols, duration="15 D", bar_size="1 day"):
    """
    Sembollerin geçmiş fiyat verilerini alır
    duration: "2 D", "5 D", "15 D" etc.
    bar_size: "1 day", "1 hour", etc.
    """
    all_data = {}
    for symbol in symbols:
        try:
            print(f"{symbol} için veri çekiliyor...")
            contract = Stock(symbol, 'SMART', 'USD')
            # Kontratı doğrula
            qualified_contracts = ib.qualifyContracts(contract)
            if not qualified_contracts:
                print(f"WARNING {symbol} için kontrat bulunamadı, atlanıyor")
                continue
            contract = qualified_contracts[0]
            # Tarihsel veriyi çek
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=True
            )
            # DataFrame'e dönüştür
            df = util.df(bars)
            if len(df) > 0:
                all_data[symbol] = df
                print(f"OK {symbol}: {len(df)} gün veri alındı")
            else:
                print(f"WARNING {symbol} için veri alınamadı")
            # API hız limiti aşılmasın diye kısa bekleme
            ib.sleep(1)
        except Exception as e:
            print(f"ERROR {symbol} veri çekme hatası: {e}")
    return all_data

def calculate_price_changes(market_data):
    """
    Fiyat değişim yüzdelerini hesaplar
    2 günlük, 5 günlük ve 15 günlük değişimler
    """
    changes = {}
    periods = [2, 5, 15]  # 2, 5, 15 günlük değişimler
    for symbol, df in market_data.items():
        changes[symbol] = {}
        if len(df) < 2:
            print(f"WARNING {symbol} için yeterli veri yok, değişim hesaplanamadı")
            continue
        # Tersine çevir (en son tarih son sırada olsun)
        df = df.sort_index()
        for period in periods:
            # Eğer yeterli veri yoksa, mevcut maksimum veriyi kullan
            available_period = min(period, len(df)-1)
            if available_period < period:
                print(f"WARNING {symbol} için {period} günlük veri yerine {available_period} günlük veri kullanıldı")
            if available_period > 0:
                price_change = (df['close'].iloc[-1] / df['close'].iloc[-available_period-1] - 1) * 100
                changes[symbol][period] = price_change
    return changes

def analyze_market_conditions(price_changes, market_data=None):
    """
    Fiyat değişimlerine ve SMA momentumuna göre piyasa koşullarını analiz eder
    Risk-on ve Risk-off ağırlıklarını hesaplar
    """
    if not price_changes or len(price_changes) == 0:
        print("WARNING Piyasa analizi için veri yok!")
        return {
            'solidity_weight': 2.4, 
            'yield_weight': 12, 
            'adv_weight': 0.00025,
            'adj_risk_premium_weight': 1350,
            'solcall_score_weight': 4,
            'credit_score_norm_weight': 2
        }

    # --- SMA bazlı momentum analizi ---
    momentum_scores = []
    sma_table = []
    for symbol in ["SPY", "IWM", "KRE"]:
        if market_data and symbol in market_data:
            try:
                diff20, diff100, diff200 = calculate_sma_diffs(market_data[symbol])
                for d, label in zip([diff20, diff100, diff200], ["SMA20", "SMA100", "SMA200"]):
                    if not np.isnan(d):
                        momentum_scores.append(d)
                        sma_table.append((symbol, label, d))
            except Exception as e:
                print(f"SMA hesaplama hatası ({symbol}): {e}")
    market_momentum = np.mean(momentum_scores) if momentum_scores else 0
    market_momentum = max(min(market_momentum, 20), -20)

    period_weights = {2: 0.5, 5: 0.3, 15: 0.2}
    periods = list(period_weights.keys())
    risk_scores = {"RISK_ON": 0, "RISK_OFF": 0}
    valid_indicators = {"RISK_ON": [], "RISK_OFF": []}
    for risk_type, symbols in RISK_INDICATORS.items():
        for symbol in symbols:
            if symbol in price_changes:
                valid_indicators[risk_type].append(symbol)
                weighted_change = 0
                for period in periods:
                    if period in price_changes[symbol]:
                        weighted_change += price_changes[symbol][period] * period_weights[period]
                risk_scores[risk_type] += weighted_change
    for risk_type in risk_scores:
        if len(valid_indicators[risk_type]) > 0:
            risk_scores[risk_type] /= len(valid_indicators[risk_type])
    risk_balance = risk_scores["RISK_ON"] - risk_scores["RISK_OFF"]
    
    # Market momentum -20 ile +20 arası, bunu 0-1 arasına normalize et
    momentum_normalized = (market_momentum + 20) / 40  # 0-1 arası
    
    # Daha agresif ağırlık aralıkları
    # Yield weight: 6-55 (risk-on'da 55, risk-off'da 6)
    yield_weight = 6 + (55 - 6) * momentum_normalized
    # Solidity weight: 5-0.3 (risk-on'da 0.3, risk-off'da 5)
    solidity_weight = 5 - (5 - 0.3) * momentum_normalized
    base_adv = 0.00025
    # Adj Risk Premium Weight: 500-2500
    adj_risk_premium_weight = 500 + (2500 - 500) * momentum_normalized
    # SOLCALL Score Weight: 0.5-10
    solcall_score_weight = 0.5 + (10 - 0.5) * momentum_normalized
    # Credit Score Norm Weight: 4-0.2 (risk-on'da 0.2, risk-off'da 4)
    credit_score_norm_weight = 4 - (4 - 0.2) * momentum_normalized

    # Skala raporu
    if market_momentum >= 15:
        risk_state = '20/20: HÜCUM RALLİSİ'
    elif market_momentum >= 10:
        risk_state = '15/20: ÇOK GÜÇLÜ RİSK-ON'
    elif market_momentum >= 5:
        risk_state = '10/20: GÜÇLÜ RİSK-ON'
    elif market_momentum >= 2:
        risk_state = '7/20: RİSK-ON'
    elif market_momentum >= -2:
        risk_state = 'ORTA/NÖTR'
    elif market_momentum >= -5:
        risk_state = '-7/20: RİSK-OFF'
    elif market_momentum >= -10:
        risk_state = '-10/20: GÜÇLÜ RİSK-OFF'
    elif market_momentum >= -15:
        risk_state = '-15/20: ÇOK GÜÇLÜ RİSK-OFF'
    else:
        risk_state = '-20/20: MARKET CRASH'

    print(f"\n[SMA MOMENTUM] Market momentum skoru: {market_momentum:.2f}  [-20 (crash) ... 0 (nötr) ... +20 (ralli)]")
    print("SMA fark tablosu:")
    for symbol, label, d in sma_table:
        print(f"  {symbol} {label}: {d:.2f}%")
    print(f"Risk durumu: {risk_state}")
    print(f"Solidity ağırlık: {solidity_weight:.2f}, Yield ağırlık: {yield_weight:.2f}, ADV ağırlık: {base_adv:.8f}")
    print(f"Adj Risk Premium ağırlık: {adj_risk_premium_weight:.0f}, SOLCALL Score ağırlık: {solcall_score_weight:.2f}, Credit Score Norm ağırlık: {credit_score_norm_weight:.2f}")
    
    return {
        'solidity_weight': round(solidity_weight, 2),
        'yield_weight': round(yield_weight, 2),
        'adv_weight': round(base_adv, 8),
        'adj_risk_premium_weight': round(adj_risk_premium_weight, 0),
        'solcall_score_weight': round(solcall_score_weight, 2),
        'credit_score_norm_weight': round(credit_score_norm_weight, 2),
        'risk_balance': round(risk_balance, 2),
        'risk_on_score': round(risk_scores["RISK_ON"], 2),
        'risk_off_score': round(risk_scores["RISK_OFF"], 2),
        'market_momentum': round(market_momentum, 2)
    }

def generate_market_report(price_changes, market_weights):
    """Piyasa koşulları hakkında detaylı rapor üretir"""
    periods = [2, 5, 15]
    print("\n=== PAZAR KOŞULLARI RAPORU ===")
    
    # price_changes None ise sadece ağırlıkları göster
    if price_changes is None:
        print("Piyasa verisi yok, sadece ağırlıklar gösteriliyor...")
        print(f"\nKullanılacak Ağırlıklar:")
        print(f"Solidity Ağırlık: {market_weights['solidity_weight']:.2f} (Aralık: 0.8-4.0)")
        print(f"Yield Ağırlık: {market_weights['yield_weight']:.2f} (Aralık: 8-40)")
        print(f"ADV Ağırlık: {market_weights['adv_weight']:.8f} (Sabit: 0.00025000)")
        print(f"Adj Risk Premium Ağırlık: {market_weights['adj_risk_premium_weight']:.0f} (Aralık: 750-2050)")
        print(f"SOLCALL Score Ağırlık: {market_weights['solcall_score_weight']:.2f} (Aralık: 1-7)")
        print(f"Credit Score Norm Ağırlık: {market_weights['credit_score_norm_weight']:.2f} (Aralık: 0.5-3.5)")
        print(f"\nSolidity Değişim: %{((market_weights['solidity_weight']/2.4 - 1) * 100):.1f}")
        print(f"Yield Değişim: %{((market_weights['yield_weight']/24 - 1) * 100):.1f}")
        print(f"Adj Risk Premium Değişim: %{((market_weights['adj_risk_premium_weight']/1350 - 1) * 100):.1f}")
        print(f"SOLCALL Score Değişim: %{((market_weights['solcall_score_weight']/4 - 1) * 100):.1f}")
        print(f"Credit Score Norm Değişim: %{((market_weights['credit_score_norm_weight']/2 - 1) * 100):.1f}")
        return
        
    # Değişimleri göster
    print("\nFiyat Değişimleri (%):")
    print(f"{'Sembol':<8}", end="")
    for period in periods:
        print(f"{period:>5} gün", end="  ")
    print("")
    # Tüm sembolleri toplu göster
    all_symbols = set()
    for symbols in RISK_INDICATORS.values():
        all_symbols.update(symbols)
    all_symbols = sorted(all_symbols)
    for symbol in all_symbols:
        if symbol in price_changes:
            print(f"{symbol:<8}", end="")
            for period in periods:
                if period in price_changes[symbol]:
                    print(f"{price_changes[symbol][period]:>7.2f}", end="  ")
                else:
                    print(f"{'N/A':>7}", end="  ")
            print("")
    # Risk durumunu göster
    print("\nRisk Durumu:")
    print(f"Risk-On Skoru: {market_weights['risk_on_score']:.2f}")
    print(f"Risk-Off Skoru: {market_weights['risk_off_score']:.2f}")
    print(f"Risk Dengesi: {market_weights['risk_balance']:.2f}")
    # Stratejiyi açıkla
    if market_weights['risk_balance'] > 3:
        risk_state = "RISK_ON GÜÇLÜ RİSK-ON (Yüksek risk iştahı)"
        strategy = "Getiri (CUR_YIELD) ve işlem hacmi (ADV) odaklı hisselere ağırlık ver"
    elif market_weights['risk_balance'] > 0:
        risk_state = "🔼 HAFİF RİSK-ON (Risk iştahı var)"
        strategy = "Getiri ve işlem hacmi biraz daha önemli, dengeli gitmeye çalış"
    elif market_weights['risk_balance'] > -3:
        risk_state = "🔽 HAFİF RİSK-OFF (Risk iştahı düşük)"
        strategy = "Sağlamlık (SOLIDITY) biraz daha önemli, kaliteli hisseler seç"
    else:
        risk_state = "📉 GÜÇLÜ RİSK-OFF (Güvenli limanlara kaçış)"
        strategy = "Sağlamlık odaklı hisselere ağırlık ver, işlem hacmini göz ardı et"
    print(f"\nPazar Durumu: {risk_state}")
    print(f"Strateji: {strategy}")
    print(f"\nKullanılacak Ağırlıklar:")
    print(f"Solidity Ağırlık: {market_weights['solidity_weight']:.2f} (Aralık: 0.8-4.0)")
    print(f"Yield Ağırlık: {market_weights['yield_weight']:.2f} (Aralık: 8-40)")
    print(f"ADV Ağırlık: {market_weights['adv_weight']:.8f} (Sabit: 0.00025000)")
    # Kullanılacak değişim oranlarını göster
    print(f"\nSolidity Değişim: %{((market_weights['solidity_weight']/2.4 - 1) * 100):.1f}")
    print(f"Yield Değişim: %{((market_weights['yield_weight']/24 - 1) * 100):.1f}")

def save_market_weights(market_weights):
    """Piyasa ağırlıklarını dosyaya kaydeder"""
    try:
        # Mevcut tarihi ekle
        market_weights['date'] = datetime.now().strftime('%Y-%m-%d')
        # Pandas DataFrame'e dönüştür ve kaydet
        df = pd.DataFrame([market_weights])
        df.to_csv(get_simulation_filename('market_weights.csv'), index=False)
        print("\nPiyasa ağırlıkları 'market_weights.csv' dosyasına kaydedildi.")
        return True
    except Exception as e:
        print(f"Piyasa ağırlıkları kaydedilirken hata: {e}")
        return False

def get_saved_market_weights():
    """Kaydedilmiş piyasa ağırlıklarını yükler"""
    try:
        df = pd.read_csv(get_simulation_filename('market_weights.csv'))
        if len(df) > 0:
            weights = {
                'solidity_weight': df['solidity_weight'].iloc[0],
                'yield_weight': df['yield_weight'].iloc[0],
                'adv_weight': df['adv_weight'].iloc[0],
                'adj_risk_premium_weight': df.get('adj_risk_premium_weight', 1350).iloc[0],
                'solcall_score_weight': df.get('solcall_score_weight', 4).iloc[0],
                'credit_score_norm_weight': df.get('credit_score_norm_weight', 2).iloc[0],
                'risk_balance': df['risk_balance'].iloc[0],
                'risk_on_score': df['risk_on_score'].iloc[0],
                'risk_off_score': df['risk_off_score'].iloc[0],
                'market_momentum': df['market_momentum'].iloc[0]
            }
            print(f"OK Kaydedilmiş ağırlıklar yüklendi:")
            print(f"Solidity: {weights['solidity_weight']:.2f}, Yield: {weights['yield_weight']:.2f}, ADV: {weights['adv_weight']:.8f}")
            print(f"Adj Risk Premium: {weights['adj_risk_premium_weight']:.0f}, SOLCALL: {weights['solcall_score_weight']:.2f}, Credit Score: {weights['credit_score_norm_weight']:.2f}")
            return weights
    except Exception as e:
        print(f"WARNING Kaydedilmiş ağırlıklar yüklenemedi: {e}")
    
    # Varsayılan değerler
    return {
        'solidity_weight': 2.4, 
        'yield_weight': 24, 
        'adv_weight': 0.00025,
        'adj_risk_premium_weight': 1350,
        'solcall_score_weight': 4,
        'credit_score_norm_weight': 2
    }

def get_default_market_weights():
    """Varsayılan piyasa ağırlıklarını döndürür"""
    return {
        'solidity_weight': 2.4, 
        'yield_weight': 24, 
        'adv_weight': 0.00025,
        'adj_risk_premium_weight': 1350,
        'solcall_score_weight': 4,
        'credit_score_norm_weight': 2
    }

def main():
    """Ana program"""
    print("Piyasa Risk Analizi Başlatılıyor...")
    saved_weights = get_saved_market_weights()
    if saved_weights:
        user_input = input("Bugün için piyasa analizi zaten yapılmış. Yeniden analiz yapmak ister misiniz? (e/h): ")
        if user_input.lower() not in ['e', 'evet', 'y', 'yes']:
            print("Mevcut piyasa ağırlıkları kullanılacak.")
            generate_market_report(None, saved_weights)
            return saved_weights
    ib = connect_to_ibkr()
    if ib is None:
        print("IBKR bağlantısı kurulamadı!")
        return {'solidity_weight': 2.4, 'yield_weight': 12, 'adv_weight': 0.00025}
    try:
        all_symbols = []
        for symbols in RISK_INDICATORS.values():
            all_symbols.extend(symbols)
        market_data = get_historical_data(ib, all_symbols, duration="220 D", bar_size="1 day")
        price_changes = calculate_price_changes(market_data)
        market_weights = analyze_market_conditions(price_changes, market_data)
        generate_market_report(price_changes, market_weights)
        save_market_weights(market_weights)
        return market_weights
    except Exception as e:
        print(f"Piyasa analizi sırasında hata: {e}")
        import traceback
        traceback.print_exc()
        return {'solidity_weight': 2.4, 'yield_weight': 12, 'adv_weight': 0.00025}
    finally:
        if ib and ib.isConnected():
            ib.disconnect()
            print("\nIBKR bağlantısı kapatıldı")

if __name__ == "__main__":
    main()
