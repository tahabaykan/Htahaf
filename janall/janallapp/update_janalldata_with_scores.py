"""
janalldata.csv dosyasını skor kolonları ile güncelle
"""

import pandas as pd
import numpy as np

def calculate_scores(row, bid, ask, last_price, prev_close, benchmark_chg=0):
    """Ntahaf formüllerine göre skorları hesapla"""
    try:
        # Spread hesapla
        spread = float(ask) - float(bid) if ask != 'N/A' and bid != 'N/A' else 0
        
        # Passive fiyatlar hesapla
        pf_bid_buy = float(bid) + (spread * 0.15) if bid != 'N/A' else 0
        pf_front_buy = float(last_price) + 0.01 if last_price != 'N/A' else 0
        pf_ask_buy = float(ask) + 0.01 if ask != 'N/A' else 0
        pf_ask_sell = float(ask) - (spread * 0.15) if ask != 'N/A' else 0
        pf_front_sell = float(last_price) - 0.01 if last_price != 'N/A' else 0
        pf_bid_sell = float(bid) - 0.01 if bid != 'N/A' else 0
        
        # Değişimler hesapla (dolar bazında)
        pf_bid_buy_chg = pf_bid_buy - float(prev_close) if prev_close != 'N/A' else 0
        pf_front_buy_chg = pf_front_buy - float(prev_close) if prev_close != 'N/A' else 0
        pf_ask_buy_chg = pf_ask_buy - float(prev_close) if prev_close != 'N/A' else 0
        pf_ask_sell_chg = pf_ask_sell - float(prev_close) if prev_close != 'N/A' else 0
        pf_front_sell_chg = pf_front_sell - float(prev_close) if prev_close != 'N/A' else 0
        pf_bid_sell_chg = pf_bid_sell - float(prev_close) if prev_close != 'N/A' else 0
        
        # CENT'E ÇEVİRME KALDIRILDI - DOLAR BAZINDA KALSIN!
        # Ucuzluk/Pahalilik skorları (DOLAR bazında - puan olarak)
        bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
        front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
        ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
        ask_sell_pahali = pf_ask_sell_chg - benchmark_chg
        front_sell_pahali = pf_front_sell_chg - benchmark_chg
        bid_sell_pahali = pf_bid_sell_chg - benchmark_chg
        
        # Final skorlar (FINAL_THG ve SHORT_FINAL varsa kullan, yoksa 0)
        final_thg = float(row.get('FINAL_THG', 0)) if row.get('FINAL_THG') != 'N/A' else 0
        short_final = float(row.get('SHORT_FINAL', 0)) if row.get('SHORT_FINAL') != 'N/A' else 0
        
        def final_skor(final_value, skor):
            return final_value - 1000 * skor
        
        final_bb = final_skor(final_thg, bid_buy_ucuzluk)
        final_fb = final_skor(final_thg, front_buy_ucuzluk)
        final_ab = final_skor(final_thg, ask_buy_ucuzluk)
        final_as = final_skor(final_thg, ask_sell_pahali)
        final_fs = final_skor(final_thg, front_sell_pahali)
        final_bs = final_skor(final_thg, bid_sell_pahali)
        # SHORT_FINAL tabanlı ek skorlar
        final_sas = final_skor(short_final, ask_sell_pahali)
        final_sfs = final_skor(short_final, front_sell_pahali)
        final_sbs = final_skor(short_final, bid_sell_pahali)
        
        return {
            'Bid_buy_ucuzluk_skoru': round(bid_buy_ucuzluk, 2),
            'Front_buy_ucuzluk_skoru': round(front_buy_ucuzluk, 2),
            'Ask_buy_ucuzluk_skoru': round(ask_buy_ucuzluk, 2),
            'Ask_sell_pahalilik_skoru': round(ask_sell_pahali, 2),
            'Front_sell_pahalilik_skoru': round(front_sell_pahali, 2),
            'Bid_sell_pahalilik_skoru': round(bid_sell_pahali, 2),
            'Final_BB_skor': round(final_bb, 2),
            'Final_FB_skor': round(final_fb, 2),
            'Final_AB_skor': round(final_ab, 2),
            'Final_AS_skor': round(final_as, 2),
            'Final_FS_skor': round(final_fs, 2),
            'Final_BS_skor': round(final_bs, 2),
            'Final_SAS_skor': round(final_sas, 2),
            'Final_SFS_skor': round(final_sfs, 2),
            'Final_SBS_skor': round(final_sbs, 2),
            'Spread': round(spread, 4)
        }
    except Exception as e:
        print(f"Skor hesaplama hatası: {e}")
        return {
            'Bid_buy_ucuzluk_skoru': 0,
            'Front_buy_ucuzluk_skoru': 0,
            'Ask_buy_ucuzluk_skoru': 0,
            'Ask_sell_pahalilik_skoru': 0,
            'Front_sell_pahalilik_skoru': 0,
            'Bid_sell_pahalilik_skoru': 0,
            'Final_BB_skor': 0,
            'Final_FB_skor': 0,
            'Final_AB_skor': 0,
            'Final_AS_skor': 0,
            'Final_FS_skor': 0,
            'Final_BS_skor': 0,
            'Final_SAS_skor': 0,
            'Final_SFS_skor': 0,
            'Final_SBS_skor': 0,
            'Spread': 0
        }

def update_janalldata_with_scores():
    """janalldata.csv dosyasını skor kolonları ile güncelle"""
    try:
        # CSV'yi oku
        df = pd.read_csv('janalldata.csv')
        
        # Skor kolonlarını ekle
        score_columns = [
            'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
            'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
            'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor',
            'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor',
            'Spread'
        ]
        
        # Benchmark kolonlarını ekle
        benchmark_columns = ['Benchmark_Type', 'Benchmark_Chg']
        
        # Tüm yeni kolonları ekle
        for col in score_columns + benchmark_columns:
            if col not in df.columns:
                df[col] = 0.0
        
        # CSV'yi kaydet
        df.to_csv('janalldata.csv', index=False)
        print("✅ janalldata.csv güncellendi!")
        print(f"📊 Toplam {len(df)} satır")
        print(f"📋 Eklenen kolonlar: {score_columns + benchmark_columns}")
        
    except Exception as e:
        print(f"❌ Hata: {e}")

if __name__ == "__main__":
    update_janalldata_with_scores() 