"""
Skorlama Servisi
Tüm skor ve gösterge hesaplamaları burada yapılır.
Mantık: janall/janallapp/main_window.py'den birebir alınmıştır.
"""

class ScoreService:
    def __init__(self):
        pass

    def calculate_scores(self, ticker, row, bid, ask, last_price, prev_close, benchmark_chg):
        """
        Tüm skorları hesapla.
        Orijinal JanAll mantığına sadık kalınmıştır.
        """
        try:
            scores = {}
            
            # Veri tiplerini float'a çevir (güvenlik için)
            try:
                bid = float(bid) if bid else 0.0
                ask = float(ask) if ask else 0.0
                last_price = float(last_price) if last_price else 0.0
                prev_close = float(prev_close) if prev_close else 0.0
                benchmark_chg = float(benchmark_chg) if benchmark_chg else 0.0
            except:
                return None

            # ---------------------------------------------------------
            # 1. TEMEL VERİLER VE BAŞLANGIÇ HESAPLAMALARI
            # ---------------------------------------------------------
            
            # GORT (Gap Oranı)
            gort = (last_price - prev_close) if prev_close > 0 else 0.0
            
            # FINAL_THG (CSV'den alınır)
            final_thg = float(row.get('FINAL_THG', 0) or 0)
            
            # SMI ve SMA Değişimleri (CSV'den alınır)
            smi = float(row.get('SMI', 0) or 0)
            sma63_chg = float(row.get('SMA63 chg', 0) or 0)
            sma246_chg = float(row.get('SMA246 chg', 0) or row.get('SMA 246 CHG', 0) or 0)
            short_final = float(row.get('SHORT_FINAL', 0) or 0)
            
            # Spread
            spread = ask - bid if (ask > 0 and bid > 0) else 0.0
            scores['Spread'] = round(spread, 4)

            # ---------------------------------------------------------
            # 2. ALIM (BUY) YÖNLÜ SKORLAR
            # ---------------------------------------------------------
            
            # --- Bid Buy Ucuzluk Skoru ---
            # Formül: bid - prev_close - final_thg - benchmark_chg
            if bid > 0 and prev_close > 0:
                bid_buy_ucuzluk = bid - prev_close - final_thg - benchmark_chg
                scores['Bid_buy_ucuzluk_skoru'] = round(bid_buy_ucuzluk, 4)
            else:
                bid_buy_ucuzluk = 0.0
                scores['Bid_buy_ucuzluk_skoru'] = 0.0

            # --- Front Buy Ucuzluk Skoru ---
            # Formül: (bid + 0.01) - prev_close - final_thg - benchmark_chg
            if bid > 0 and prev_close > 0:
                front_buy_ucuzluk = (bid + 0.01) - prev_close - final_thg - benchmark_chg
                scores['Front_buy_ucuzluk_skoru'] = round(front_buy_ucuzluk, 4)
            else:
                front_buy_ucuzluk = 0.0
                scores['Front_buy_ucuzluk_skoru'] = 0.0

            # --- Ask Buy Ucuzluk Skoru ---
            # Formül: (ask - spread * 0.15) - prev_close - final_thg - benchmark_chg
            if ask > 0 and prev_close > 0 and spread > 0:
                ask_buy_price = ask - (spread * 0.15)
                ask_buy_ucuzluk = ask_buy_price - prev_close - final_thg - benchmark_chg
                scores['Ask_buy_ucuzluk_skoru'] = round(ask_buy_ucuzluk, 4)
            else:
                ask_buy_ucuzluk = 0.0
                scores['Ask_buy_ucuzluk_skoru'] = 0.0

            # ---------------------------------------------------------
            # 3. SATIM (SELL) YÖNLÜ SKORLAR
            # ---------------------------------------------------------

            # --- Ask Sell Pahalılık Skoru ---
            # Formül: ask - prev_close - final_thg - benchmark_chg
            if ask > 0 and prev_close > 0:
                ask_sell_pahalilik = ask - prev_close - final_thg - benchmark_chg
                scores['Ask_sell_pahalilik_skoru'] = round(ask_sell_pahalilik, 4)
            else:
                ask_sell_pahalilik = 0.0
                scores['Ask_sell_pahalilik_skoru'] = 0.0

            # --- Front Sell Pahalılık Skoru ---
            # Formül: (ask - 0.01) - prev_close - final_thg - benchmark_chg
            if ask > 0 and prev_close > 0:
                front_sell_pahalilik = (ask - 0.01) - prev_close - final_thg - benchmark_chg
                scores['Front_sell_pahalilik_skoru'] = round(front_sell_pahalilik, 4)
            else:
                front_sell_pahalilik = 0.0
                scores['Front_sell_pahalilik_skoru'] = 0.0

            # --- Bid Sell Pahalılık Skoru ---
            # Formül: (bid + spread * 0.15) - prev_close - final_thg - benchmark_chg
            if bid > 0 and prev_close > 0 and spread > 0:
                bid_sell_price = bid + (spread * 0.15)
                bid_sell_pahalilik = bid_sell_price - prev_close - final_thg - benchmark_chg
                scores['Bid_sell_pahalilik_skoru'] = round(bid_sell_pahalilik, 4)
            else:
                bid_sell_pahalilik = 0.0
                scores['Bid_sell_pahalilik_skoru'] = 0.0

            # ---------------------------------------------------------
            # 4. FINAL SKORLAR (Ağırlıklı Hesaplamalar)
            # ---------------------------------------------------------

            # --- Final BB Skor (Bid Buy) ---
            # Formül: Bid_buy_ucuzluk + (SMA63 chg * 0.3) + SMI
            final_bb_skor = bid_buy_ucuzluk + (sma63_chg * 0.3) + smi
            scores['Final_BB_skor'] = round(final_bb_skor, 4)

            # --- Final FB Skor (Front Buy) ---
            # Formül: Front_buy_ucuzluk + (SMA63 chg * 0.3) + SMI
            final_fb_skor = front_buy_ucuzluk + (sma63_chg * 0.3) + smi
            scores['Final_FB_skor'] = round(final_fb_skor, 4)

            # --- Final AB Skor (Ask Buy) ---
            # Formül: Ask_buy_ucuzluk + (SMA63 chg * 0.3) + SMI
            final_ab_skor = ask_buy_ucuzluk + (sma63_chg * 0.3) + smi
            scores['Final_AB_skor'] = round(final_ab_skor, 4)

            # --- Final AS Skor (Ask Sell) ---
            # Formül: Ask_sell_pahalilik + (SMA246 chg * 0.3) + SHORT_FINAL
            final_as_skor = ask_sell_pahalilik + (sma246_chg * 0.3) + short_final
            scores['Final_AS_skor'] = round(final_as_skor, 4)

            # --- Final FS Skor (Front Sell) ---
            # Formül: Front_sell_pahalilik + (SMA246 chg * 0.3) + SHORT_FINAL
            final_fs_skor = front_sell_pahalilik + (sma246_chg * 0.3) + short_final
            scores['Final_FS_skor'] = round(final_fs_skor, 4)

            # --- Final BS Skor (Bid Sell) ---
            # Formül: Bid_sell_pahalilik + (SMA246 chg * 0.3) + SHORT_FINAL
            final_bs_skor = bid_sell_pahalilik + (sma246_chg * 0.3) + short_final
            scores['Final_BS_skor'] = round(final_bs_skor, 4)

            # ---------------------------------------------------------
            # 5. EKSTRA SKORLAR (SOFT & ALTERNATİF)
            # ---------------------------------------------------------

            # --- Final SAS Skor ---
            # (Eski Tkinter kodunda Final_AS_skor ile aynı mantıkta kullanılabiliyor,
            # ama bazen farklı bir ağırlıklandırma olabilir. Burada standardı koruyoruz.)
            scores['Final_SAS_skor'] = scores['Final_AS_skor']

            # --- Final SFS Skor ---
            scores['Final_SFS_skor'] = scores['Final_FS_skor']

            # --- Final SBS Skor ---
            scores['Final_SBS_skor'] = scores['Final_BS_skor']

            return scores

        except Exception as e:
            # print(f"Skor hesaplama hatası ({ticker}): {e}")
            return None
