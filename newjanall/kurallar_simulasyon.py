"""
PSFAlgo 5 Günlük Trading Simülasyonu - GERÇEK VERİLERLE
========================================================
Güncel befibped.csv portföyü ile 5 gün boyunca ADDNEWPOS ve KARBOTU/REDUCEMORE 
kurallarının nasıl çalışacağını gösteren detaylı simülasyon.

Gerçek veriler:
- befibped.csv → Mevcut pozisyonlar (BefDay Qty)
- final_fb_sfs_tumcsv_long_stocks.csv → AVG_ADV, Final_FB_skor, Final_SFS_skor
"""

import pandas as pd
import random
import os
from datetime import datetime, timedelta

# ==================== KURAL TANIMLARI ====================

RULE_MIN_LOT = 400
RULE_AVG_ADV_DIVISOR = 10

# ADDNEWPOS Kuralları
ADDNEWPOS_RULES = {
    1: (0.50, 5.0),
    3: (0.40, 4.0),
    5: (0.30, 3.0),
    7: (0.20, 2.0),
    10: (0.10, 1.5),
    100: (0.05, 1.0)
}

# REDUCE Kuralları
REDUCE_RULES = {
    3: (None, None),
    5: (0.75, 0.75),
    7: (0.60, 0.60),
    10: (0.50, 0.50),
    100: (0.40, 0.40)
}

# ==================== YARDIMCI FONKSİYONLAR ====================

def round_lot(lot, is_reduce=False, remaining_position=0):
    if lot <= 0:
        return 0
    rounded = round(lot / 100) * 100
    if rounded < 200:
        rounded = 200
    if is_reduce and remaining_position > 0:
        if remaining_position - rounded < 200 and remaining_position - rounded > 0:
            rounded = remaining_position
    return int(rounded)


def get_portfolio_ratio(befday_qty, portfolio_size):
    if portfolio_size <= 0:
        return 0
    return (abs(befday_qty) / portfolio_size) * 100


def get_addnewpos_limit(maxalw, befday_qty, portfolio_size):
    ratio = get_portfolio_ratio(befday_qty, portfolio_size)
    thresholds = sorted(ADDNEWPOS_RULES.keys())
    selected_threshold = thresholds[-1]
    for threshold in thresholds:
        if ratio < threshold:
            selected_threshold = threshold
            break
    maxalw_mult, port_pct = ADDNEWPOS_RULES.get(selected_threshold, (0.5, 5.0))
    limit1 = maxalw * maxalw_mult
    if limit1 < RULE_MIN_LOT:
        limit1 = RULE_MIN_LOT
    limit2 = portfolio_size * (port_pct / 100)
    final_limit = min(limit1, limit2)
    return round_lot(final_limit), maxalw_mult, port_pct, ratio, selected_threshold


def get_reduce_limit(maxalw, befday_qty, portfolio_size):
    abs_befday = abs(befday_qty)
    if abs_befday < RULE_MIN_LOT:
        return abs_befday, None, None, get_portfolio_ratio(befday_qty, portfolio_size), True, "Tamamı satılabilir", 0
    
    ratio = get_portfolio_ratio(befday_qty, portfolio_size)
    thresholds = sorted(REDUCE_RULES.keys())
    selected_threshold = thresholds[-1]
    for threshold in thresholds:
        if ratio < threshold:
            selected_threshold = threshold
            break
    
    maxalw_mult, befday_mult = REDUCE_RULES.get(selected_threshold, (0.5, 0.5))
    
    if maxalw_mult is None and befday_mult is None:
        return abs_befday, None, None, ratio, True, "Sınırsız (<%3)", selected_threshold
    
    limit1 = maxalw * maxalw_mult if maxalw_mult else float('inf')
    if limit1 < RULE_MIN_LOT and limit1 != float('inf'):
        limit1 = RULE_MIN_LOT
    limit2 = abs_befday * befday_mult if befday_mult else float('inf')
    final_limit = min(limit1, limit2)
    if final_limit == float('inf'):
        final_limit = abs_befday
    return round_lot(final_limit, True, abs_befday), maxalw_mult, befday_mult, ratio, False, "", selected_threshold


# ==================== VERİ YÜKLEME ====================

def load_real_data():
    """Gerçek verileri yükle"""
    
    # befibped.csv yükle
    befibped_path = "befibped.csv"
    if not os.path.exists(befibped_path):
        print(f"❌ {befibped_path} bulunamadı!")
        return None, None
    
    befibped_df = pd.read_csv(befibped_path)
    print(f"✅ befibped.csv yüklendi: {len(befibped_df)} satır")
    
    # final_fb_sfs_tumcsv_long_stocks.csv yükle (AVG_ADV ve skorlar için)
    tumcsv_path = "final_fb_sfs_tumcsv_long_stocks.csv"
    tumcsv_df = None
    if os.path.exists(tumcsv_path):
        tumcsv_df = pd.read_csv(tumcsv_path)
        print(f"✅ {tumcsv_path} yüklendi: {len(tumcsv_df)} satır")
    else:
        print(f"⚠️ {tumcsv_path} bulunamadı, varsayılan AVG_ADV kullanılacak")
    
    return befibped_df, tumcsv_df


def create_portfolio_from_real_data():
    """Gerçek verilerden portföy oluştur"""
    
    befibped_df, tumcsv_df = load_real_data()
    
    if befibped_df is None:
        print("❌ Veri yüklenemedi, örnek veri kullanılıyor...")
        return create_sample_portfolio()
    
    stocks = []
    
    # AVG_ADV lookup tablosu oluştur
    avg_adv_lookup = {}
    fbtot_lookup = {}
    sfstot_lookup = {}
    
    if tumcsv_df is not None:
        for _, row in tumcsv_df.iterrows():
            symbol = str(row.get('PREF IBKR', '')).strip()
            if symbol:
                try:
                    avg_adv = float(row.get('AVG_ADV', 0))
                    avg_adv_lookup[symbol] = avg_adv
                except:
                    pass
                try:
                    fbtot = float(row.get('Final_FB_skor', 0))
                    if fbtot > 0:
                        fbtot_lookup[symbol] = fbtot / 1000  # Normalize et (örn: 1200 → 1.2)
                except:
                    pass
                try:
                    sfstot = float(row.get('Final_SFS_skor', 0))
                    if sfstot > 0:
                        sfstot_lookup[symbol] = sfstot / 1000
                except:
                    pass
    
    # befibped'den pozisyonları al
    for _, row in befibped_df.iterrows():
        symbol = str(row.get('Symbol', '')).strip()
        qty = float(row.get('Quantity', 0))
        
        if not symbol or qty == 0:
            continue
        
        # Symbol'ü IBKR formatına çevir (örn: "USB PRH" → "USB PRH")
        # Bazı semboller farklı formatta olabilir, eşleştirmeye çalış
        lookup_symbol = symbol
        if " PR" not in symbol and len(symbol) <= 5:
            # Belki kısa format (örn: "MBINM" gibi)
            lookup_symbol = symbol
        
        # AVG_ADV bul (bulunamazsa varsayılan kullan)
        avg_adv = avg_adv_lookup.get(lookup_symbol, 30000)  # Varsayılan 30000
        
        # FBtot ve SFStot bul (bulunamazsa rastgele)
        fbtot = fbtot_lookup.get(lookup_symbol, random.uniform(0.8, 1.6))
        sfstot = sfstot_lookup.get(lookup_symbol, random.uniform(0.8, 1.6))
        
        stocks.append({
            'symbol': symbol,
            'befday_qty': qty,
            'current_qty': qty,
            'avg_adv': avg_adv,
            'maxalw': avg_adv / RULE_AVG_ADV_DIVISOR,
            'fbtot': fbtot,
            'sfstot': sfstot,
            'daily_change': 0,
            'trades': [],
            'original_qty': qty
        })
    
    print(f"\n📊 {len(stocks)} aktif pozisyon yüklendi")
    return stocks


def create_sample_portfolio():
    """Örnek portföy oluştur (veri bulunamazsa)"""
    return [
        {'symbol': 'GS PRA', 'befday_qty': 2725, 'current_qty': 2725, 'avg_adv': 50000, 'maxalw': 5000, 'fbtot': 1.25, 'sfstot': 0.85, 'daily_change': 0, 'trades': [], 'original_qty': 2725},
        {'symbol': 'FITBO', 'befday_qty': 1791, 'current_qty': 1791, 'avg_adv': 40000, 'maxalw': 4000, 'fbtot': 1.15, 'sfstot': 0.92, 'daily_change': 0, 'trades': [], 'original_qty': 1791},
        {'symbol': 'ACGLO', 'befday_qty': 1700, 'current_qty': 1700, 'avg_adv': 35000, 'maxalw': 3500, 'fbtot': 1.35, 'sfstot': 0.78, 'daily_change': 0, 'trades': [], 'original_qty': 1700},
    ]


# ==================== TRADİNG SİMÜLASYONU ====================

def calculate_portfolio_size(stocks):
    """Portföy büyüklüğünü hesapla"""
    return sum(abs(s['current_qty']) for s in stocks)


def simulate_addnewpos(stocks, day, log, portfolio_size):
    """ADDNEWPOS: Yeni pozisyon ekleme simülasyonu"""
    log.append(f"\n  🟢 ADDNEWPOS Çalışıyor... (Portföy: {portfolio_size:,} lot)")
    
    # FBtot < 1.0 olan (ucuz) hisselere alım yap (long pozisyonlar veya 0 pozisyon)
    candidates = [s for s in stocks if s['fbtot'] < 1.0 and s['current_qty'] >= 0]
    
    if not candidates:
        log.append(f"     → FBtot < 1.0 olan uygun hisse bulunamadı")
        return
    
    # En ucuz 3 hisseyi seç
    candidates_sorted = sorted(candidates, key=lambda x: x['fbtot'])[:3]
    
    for stock in candidates_sorted:
        limit, mult, port_pct, ratio, threshold = get_addnewpos_limit(stock['maxalw'], stock['befday_qty'], portfolio_size)
        
        # Kalan günlük hak
        remaining = limit - abs(stock['daily_change'])
        
        if remaining < RULE_MIN_LOT:
            log.append(f"     ⚠️ {stock['symbol']}: Günlük limit doldu")
            log.append(f"        Değişim: {abs(stock['daily_change']):,} / Limit: {limit:,}")
            continue
        
        # Rastgele alım miktarı
        buy_amount = round_lot(min(remaining, random.randint(200, 500)))
        
        if buy_amount > 0:
            old_qty = stock['current_qty']
            stock['current_qty'] += buy_amount
            stock['daily_change'] += buy_amount
            stock['trades'].append({'day': day, 'type': 'BUY', 'qty': buy_amount, 'reason': 'ADDNEWPOS', 'fbtot': stock['fbtot']})
            
            log.append(f"     ✅ {stock['symbol']}: BUY +{buy_amount:,} lot (FBtot={stock['fbtot']:.2f})")
            log.append(f"        {old_qty:,} → {stock['current_qty']:,} lot")
            log.append(f"        Eşik: <{threshold}% (Port%={ratio:.2f}%) → Limit={limit:,} (MAXALW×{mult})")
            log.append(f"        Günlük: {abs(stock['daily_change']):,}/{limit:,}")


def simulate_karbotu(stocks, day, log, portfolio_size):
    """KARBOTU: Kar al simülasyonu (Long pozisyonlar)"""
    log.append(f"\n  🔴 KARBOTU Çalışıyor... (Long pozisyonlar)")
    
    # FBtot > 1.3 olan (pahalı) long hisseleri sat
    candidates = [s for s in stocks if s['fbtot'] > 1.3 and s['current_qty'] > 0]
    
    if not candidates:
        log.append(f"     → FBtot > 1.3 olan uygun long pozisyon bulunamadı")
        return
    
    # En pahalı hisseleri seç
    candidates_sorted = sorted(candidates, key=lambda x: x['fbtot'], reverse=True)[:4]
    
    for stock in candidates_sorted:
        limit, maxalw_mult, befday_mult, ratio, is_unlimited, note, threshold = get_reduce_limit(stock['maxalw'], stock['befday_qty'], portfolio_size)
        
        # Kalan günlük hak
        remaining = limit - abs(stock['daily_change'])
        
        if remaining < RULE_MIN_LOT and not is_unlimited:
            log.append(f"     ⚠️ {stock['symbol']}: Günlük limit doldu")
            continue
        
        # Satış miktarı (FBtot'a göre)
        if stock['fbtot'] > 1.6:
            sell_pct = 50
        elif stock['fbtot'] > 1.4:
            sell_pct = 35
        else:
            sell_pct = 25
            
        sell_amount = round_lot(stock['current_qty'] * sell_pct / 100, True, stock['current_qty'])
        
        # Limite göre ayarla
        if not is_unlimited and sell_amount > remaining:
            sell_amount = round_lot(remaining, True, stock['current_qty'])
        
        # Ters pozisyona geçiş kontrolü
        if stock['current_qty'] - sell_amount < 0:
            sell_amount = stock['current_qty']
        
        if sell_amount > 0:
            old_qty = stock['current_qty']
            stock['current_qty'] -= sell_amount
            stock['daily_change'] -= sell_amount
            stock['trades'].append({'day': day, 'type': 'SELL', 'qty': sell_amount, 'reason': 'KARBOTU', 'fbtot': stock['fbtot']})
            
            log.append(f"     ✅ {stock['symbol']}: SELL -{sell_amount:,} lot (FBtot={stock['fbtot']:.2f})")
            log.append(f"        {old_qty:,} → {stock['current_qty']:,} lot")
            if is_unlimited:
                log.append(f"        Eşik: <{threshold}% (Port%={ratio:.2f}%) → {note}")
            else:
                log.append(f"        Eşik: <{threshold}% (Port%={ratio:.2f}%) → Limit={limit:,}")
                log.append(f"        Kural: MAXALW×{maxalw_mult}, BefQty×{befday_mult}")


def simulate_karbotu_shorts(stocks, day, log, portfolio_size):
    """KARBOTU Shorts: Short pozisyonları kapatma"""
    log.append(f"\n  🟡 KARBOTU SHORTS Çalışıyor... (Short pozisyonlar)")
    
    # SFStot > 1.3 olan short pozisyonları kapat (qty < 0)
    candidates = [s for s in stocks if s['sfstot'] > 1.3 and s['current_qty'] < 0]
    
    if not candidates:
        log.append(f"     → SFStot > 1.3 olan uygun short pozisyon bulunamadı")
        return
    
    candidates_sorted = sorted(candidates, key=lambda x: x['sfstot'], reverse=True)[:3]
    
    for stock in candidates_sorted:
        limit, maxalw_mult, befday_mult, ratio, is_unlimited, note, threshold = get_reduce_limit(stock['maxalw'], stock['befday_qty'], portfolio_size)
        
        remaining = limit - abs(stock['daily_change'])
        
        if remaining < RULE_MIN_LOT and not is_unlimited:
            log.append(f"     ⚠️ {stock['symbol']}: Günlük limit doldu")
            continue
        
        # Kapatma miktarı
        if stock['sfstot'] > 1.6:
            buy_pct = 50
        elif stock['sfstot'] > 1.4:
            buy_pct = 35
        else:
            buy_pct = 25
            
        buy_amount = round_lot(abs(stock['current_qty']) * buy_pct / 100, True, abs(stock['current_qty']))
        
        if not is_unlimited and buy_amount > remaining:
            buy_amount = round_lot(remaining, True, abs(stock['current_qty']))
        
        # Ters pozisyona geçiş kontrolü
        if stock['current_qty'] + buy_amount > 0:
            buy_amount = abs(stock['current_qty'])
        
        if buy_amount > 0:
            old_qty = stock['current_qty']
            stock['current_qty'] += buy_amount
            stock['daily_change'] += buy_amount
            stock['trades'].append({'day': day, 'type': 'BUY', 'qty': buy_amount, 'reason': 'KARBOTU SHORT', 'sfstot': stock['sfstot']})
            
            log.append(f"     ✅ {stock['symbol']}: BUY +{buy_amount:,} lot (SFStot={stock['sfstot']:.2f})")
            log.append(f"        {old_qty:,} → {stock['current_qty']:,} lot")
            if is_unlimited:
                log.append(f"        Eşik: <{threshold}% → {note}")
            else:
                log.append(f"        Eşik: <{threshold}% → Limit={limit:,}")


def end_of_day(stocks, day, log):
    """Gün sonu işlemleri"""
    log.append(f"\n  📊 Gün {day} Sonu Özeti:")
    
    total_long = sum(s['current_qty'] for s in stocks if s['current_qty'] > 0)
    total_short = sum(s['current_qty'] for s in stocks if s['current_qty'] < 0)
    
    day_trades = sum(len([t for t in s['trades'] if t['day'] == day]) for s in stocks)
    
    log.append(f"     📈 Toplam Long: {total_long:,} lot")
    log.append(f"     📉 Toplam Short: {abs(total_short):,} lot")
    log.append(f"     📝 Bugünkü İşlem: {day_trades} adet")
    
    # Gün sonu: befday_qty güncelle, daily_change sıfırla
    for stock in stocks:
        stock['befday_qty'] = stock['current_qty']
        stock['daily_change'] = 0
        
        # FBtot ve SFStot'u rastgele değiştir (piyasa hareketi)
        stock['fbtot'] += random.uniform(-0.12, 0.12)
        stock['fbtot'] = max(0.6, min(1.8, stock['fbtot']))
        stock['sfstot'] += random.uniform(-0.12, 0.12)
        stock['sfstot'] = max(0.6, min(1.8, stock['sfstot']))


def run_5_day_simulation():
    """5 günlük simülasyonu çalıştır"""
    
    print("=" * 120)
    print("🤖 PSFAlgo 5 GÜNLÜK TRADİNG SİMÜLASYONU - GERÇEK VERİLER")
    print("=" * 120)
    
    # Gerçek verileri yükle
    stocks = create_portfolio_from_real_data()
    
    if not stocks:
        print("❌ Portföy oluşturulamadı!")
        return
    
    portfolio_size = calculate_portfolio_size(stocks)
    
    print(f"\n📊 Toplam Portföy: {portfolio_size:,} lot")
    print(f"📊 Min Lot: {RULE_MIN_LOT}")
    print(f"📊 AVG_ADV Bölen: {RULE_AVG_ADV_DIVISOR}")
    
    # Başlangıç durumu
    print("\n" + "=" * 120)
    print("📋 BAŞLANGIÇ PORTFÖYÜ")
    print("=" * 120)
    
    # Pozisyonları büyüklüğe göre sırala
    sorted_stocks = sorted(stocks, key=lambda x: abs(x['befday_qty']), reverse=True)
    
    print(f"\n{'#':<3} {'Hisse':<12} {'Tip':<6} {'Qty':>10} {'MAXALW':>8} {'Port%':>7} {'FBtot':>7} {'SFStot':>7}")
    print("-" * 75)
    
    for i, stock in enumerate(sorted_stocks[:25], 1):  # İlk 25
        pos_type = 'LONG' if stock['befday_qty'] > 0 else 'SHORT'
        ratio = get_portfolio_ratio(stock['befday_qty'], portfolio_size)
        print(f"{i:<3} {stock['symbol']:<12} {pos_type:<6} {stock['befday_qty']:>10,.0f} {stock['maxalw']:>8,.0f} "
              f"{ratio:>6.2f}% {stock['fbtot']:>7.2f} {stock['sfstot']:>7.2f}")
    
    if len(sorted_stocks) > 25:
        print(f"... ve {len(sorted_stocks) - 25} hisse daha")
    
    # 5 gün simülasyonu
    start_date = datetime(2024, 12, 2)  # Pazartesi
    
    for day in range(1, 6):
        current_date = start_date + timedelta(days=day-1)
        day_name = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma'][day-1]
        
        log = []
        portfolio_size = calculate_portfolio_size(stocks)
        
        print("\n" + "=" * 120)
        print(f"📅 GÜN {day}: {current_date.strftime('%d/%m/%Y')} {day_name}")
        print("=" * 120)
        
        # Sabah: ADDNEWPOS
        simulate_addnewpos(stocks, day, log, portfolio_size)
        
        # Öğlen: KARBOTU Longs
        simulate_karbotu(stocks, day, log, portfolio_size)
        
        # Öğleden sonra: KARBOTU Shorts
        simulate_karbotu_shorts(stocks, day, log, portfolio_size)
        
        # Gün sonu
        end_of_day(stocks, day, log)
        
        # Logları yazdır
        for line in log:
            print(line)
    
    # Final özet
    print("\n" + "=" * 120)
    print("📋 5 GÜNLÜK SİMÜLASYON ÖZETİ")
    print("=" * 120)
    
    # Değişen pozisyonlar
    changed_stocks = [s for s in stocks if s['trades']]
    
    print(f"\n{'Hisse':<12} {'Başlangıç':>12} {'Final':>12} {'Değişim':>12} {'İşlem':>8}")
    print("-" * 60)
    
    total_buys = 0
    total_sells = 0
    
    for stock in sorted(changed_stocks, key=lambda x: abs(x['current_qty'] - x['original_qty']), reverse=True):
        change = stock['current_qty'] - stock['original_qty']
        trade_count = len(stock['trades'])
        
        buys = sum(t['qty'] for t in stock['trades'] if t['type'] == 'BUY')
        sells = sum(t['qty'] for t in stock['trades'] if t['type'] == 'SELL')
        total_buys += buys
        total_sells += sells
        
        print(f"{stock['symbol']:<12} {stock['original_qty']:>12,.0f} {stock['current_qty']:>12,.0f} {change:>+12,.0f} {trade_count:>8}")
    
    print("-" * 60)
    print(f"{'TOPLAM':>24} {'':<12} {'Alım':>12} {total_buys:>+12,}")
    print(f"{'':>24} {'':<12} {'Satım':>12} {total_sells:>+12,}")
    
    # Detaylı işlem geçmişi
    print("\n" + "=" * 120)
    print("📜 DETAYLI İŞLEM GEÇMİŞİ")
    print("=" * 120)
    
    for stock in changed_stocks:
        if stock['trades']:
            print(f"\n{stock['symbol']} ({stock['original_qty']:,.0f} → {stock['current_qty']:,.0f}):")
            for trade in stock['trades']:
                score_info = f"FBtot={trade.get('fbtot', 'N/A'):.2f}" if 'fbtot' in trade else f"SFStot={trade.get('sfstot', 'N/A'):.2f}"
                sign = '+' if trade['type'] == 'BUY' else '-'
                print(f"   Gün {trade['day']}: {trade['type']:>4} {sign}{trade['qty']:,} lot ({trade['reason']}, {score_info})")
    
    # Kural etkileri özeti
    print("\n" + "=" * 120)
    print("📊 KURAL ETKİ ANALİZİ")
    print("=" * 120)
    
    print("\n🔹 ADDNEWPOS Kuralları Uygulandı:")
    for threshold, (mult, pct) in ADDNEWPOS_RULES.items():
        print(f"   <%{threshold}: MAXALW×{mult}, Portföy×%{pct}")
    
    print("\n🔹 KARBOTU/REDUCEMORE Kuralları Uygulandı:")
    for threshold, (maxalw_mult, befday_mult) in REDUCE_RULES.items():
        if maxalw_mult is None:
            print(f"   <%{threshold}: Sınırsız (ters poz. yasak)")
        else:
            print(f"   <%{threshold}: MAXALW×{maxalw_mult}, BefQty×{befday_mult}")
    
    print("\n🔹 Özel Durumlar:")
    print(f"   - Minimum lot: {RULE_MIN_LOT}")
    print(f"   - {RULE_MIN_LOT} lot altı pozisyonlar: Tamamı tek seferde satılabilir")
    print(f"   - Ters pozisyona geçiş: Yasak")
    
    print("\n" + "=" * 120)
    print("✅ SİMÜLASYON TAMAMLANDI")
    print("=" * 120)


if __name__ == "__main__":
    run_5_day_simulation()
