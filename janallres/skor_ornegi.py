#!/usr/bin/env python3
"""
Skor hesaplama örneği
Gerçek market veriler ile skorların nasıl hesaplandığını gösterir
"""

def ornek_skor_hesaplama():
    print("🧮 SKOR HESAPLAMA ÖRNEĞİ")
    print("=" * 50)
    
    # Örnek market verileri
    ticker = "AHL PRE"
    bid = 20.25
    ask = 20.55
    last_price = 20.47
    prev_close = 20.30
    benchmark_chg = 0.05  # Benchmark %0.05 yükselmiş
    final_thg = 1223.15  # CSV'den gelen değer
    
    print(f"📊 Ticker: {ticker}")
    print(f"💰 Bid: ${bid}")
    print(f"💰 Ask: ${ask}")
    print(f"💰 Last: ${last_price}")
    print(f"💰 Prev Close: ${prev_close}")
    print(f"📈 Benchmark Change: {benchmark_chg} cent")
    print(f"🎯 FINAL_THG: {final_thg}")
    print()
    
    # 1. Spread hesapla
    spread = ask - bid
    print(f"📏 Spread = {ask} - {bid} = {spread:.4f}")
    print()
    
    # 2. Passive fiyatlar
    print("🎯 PASSIVE FİYATLAR:")
    pf_bid_buy = bid + (spread * 0.15)
    pf_front_buy = last_price + 0.01
    pf_ask_buy = ask + 0.01
    pf_ask_sell = ask - (spread * 0.15)
    pf_front_sell = last_price - 0.01
    pf_bid_sell = bid - 0.01
    
    print(f"  PF_Bid_Buy = {bid} + ({spread} × 0.15) = {pf_bid_buy:.4f}")
    print(f"  PF_Front_Buy = {last_price} + 0.01 = {pf_front_buy:.4f}")
    print(f"  PF_Ask_Buy = {ask} + 0.01 = {pf_ask_buy:.4f}")
    print(f"  PF_Ask_Sell = {ask} - ({spread} × 0.15) = {pf_ask_sell:.4f}")
    print(f"  PF_Front_Sell = {last_price} - 0.01 = {pf_front_sell:.4f}")
    print(f"  PF_Bid_Sell = {bid} - 0.01 = {pf_bid_sell:.4f}")
    print()
    
    # 3. Fiyat değişimleri
    print("📊 FİYAT DEĞİŞİMLERİ:")
    pf_bid_buy_chg = pf_bid_buy - prev_close
    pf_front_buy_chg = pf_front_buy - prev_close
    pf_ask_buy_chg = pf_ask_buy - prev_close
    pf_ask_sell_chg = pf_ask_sell - prev_close
    pf_front_sell_chg = pf_front_sell - prev_close
    pf_bid_sell_chg = pf_bid_sell - prev_close
    
    print(f"  PF_Bid_Buy_Chg = {pf_bid_buy:.4f} - {prev_close} = {pf_bid_buy_chg:.4f}")
    print(f"  PF_Front_Buy_Chg = {pf_front_buy:.4f} - {prev_close} = {pf_front_buy_chg:.4f}")
    print(f"  PF_Ask_Buy_Chg = {pf_ask_buy:.4f} - {prev_close} = {pf_ask_buy_chg:.4f}")
    print(f"  PF_Ask_Sell_Chg = {pf_ask_sell:.4f} - {prev_close} = {pf_ask_sell_chg:.4f}")
    print(f"  PF_Front_Sell_Chg = {pf_front_sell:.4f} - {prev_close} = {pf_front_sell_chg:.4f}")
    print(f"  PF_Bid_Sell_Chg = {pf_bid_sell:.4f} - {prev_close} = {pf_bid_sell_chg:.4f}")
    print()
    
    # 4. Ucuzluk/Pahalılık skorları
    print("🎯 UCUZLUK/PAHALILIK SKORLARI:")
    bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
    front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
    ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
    ask_sell_pahali = pf_ask_sell_chg - benchmark_chg
    front_sell_pahali = pf_front_sell_chg - benchmark_chg
    bid_sell_pahali = pf_bid_sell_chg - benchmark_chg
    
    print(f"  Bid_Buy_Ucuzluk = {pf_bid_buy_chg:.4f} - {benchmark_chg} = {bid_buy_ucuzluk:.4f}")
    print(f"  Front_Buy_Ucuzluk = {pf_front_buy_chg:.4f} - {benchmark_chg} = {front_buy_ucuzluk:.4f}")
    print(f"  Ask_Buy_Ucuzluk = {pf_ask_buy_chg:.4f} - {benchmark_chg} = {ask_buy_ucuzluk:.4f}")
    print(f"  Ask_Sell_Pahali = {pf_ask_sell_chg:.4f} - {benchmark_chg} = {ask_sell_pahali:.4f}")
    print(f"  Front_Sell_Pahali = {pf_front_sell_chg:.4f} - {benchmark_chg} = {front_sell_pahali:.4f}")
    print(f"  Bid_Sell_Pahali = {pf_bid_sell_chg:.4f} - {benchmark_chg} = {bid_sell_pahali:.4f}")
    print()
    
    # 5. Final skorlar
    print("🏆 FINAL SKORLAR:")
    def final_skor(final_thg, skor):
        return final_thg - 1000 * skor
    
    final_bb = final_skor(final_thg, bid_buy_ucuzluk)
    final_fb = final_skor(final_thg, front_buy_ucuzluk)
    final_ab = final_skor(final_thg, ask_buy_ucuzluk)
    final_as = final_skor(final_thg, ask_sell_pahali)
    final_fs = final_skor(final_thg, front_sell_pahali)
    final_bs = final_skor(final_thg, bid_sell_pahali)
    
    print(f"  Final_BB = {final_thg} - (400 × {bid_buy_ucuzluk:.4f}) = {final_bb:.2f}")
    print(f"  Final_FB = {final_thg} - (400 × {front_buy_ucuzluk:.4f}) = {final_fb:.2f}")
    print(f"  Final_AB = {final_thg} - (400 × {ask_buy_ucuzluk:.4f}) = {final_ab:.2f}")
    print(f"  Final_AS = {final_thg} - (400 × {ask_sell_pahali:.4f}) = {final_as:.2f}")
    print(f"  Final_FS = {final_thg} - (400 × {front_sell_pahali:.4f}) = {final_fs:.2f}")
    print(f"  Final_BS = {final_thg} - (400 × {bid_sell_pahali:.4f}) = {final_bs:.2f}")
    print()
    
    # 6. Yorum
    print("💡 YORUM:")
    print(f"  📏 Spread: {spread:.4f} ({'Dar' if spread < 0.10 else 'Geniş'} spread)")
    
    # En iyi buy stratejisi
    buy_scores = [
        ("Bid Buy", final_bb),
        ("Front Buy", final_fb),
        ("Ask Buy", final_ab)
    ]
    best_buy = max(buy_scores, key=lambda x: x[1])
    print(f"  📈 En iyi buy stratejisi: {best_buy[0]} ({best_buy[1]:.2f})")
    
    # En iyi sell stratejisi
    sell_scores = [
        ("Ask Sell", final_as),
        ("Front Sell", final_fs),
        ("Bid Sell", final_bs)
    ]
    best_sell = max(sell_scores, key=lambda x: x[1])
    print(f"  📉 En iyi sell stratejisi: {best_sell[0]} ({best_sell[1]:.2f})")
    
    # Ucuzluk analizi
    if bid_buy_ucuzluk < -0.05:
        print(f"  💰 Bid Buy çok ucuz! ({bid_buy_ucuzluk:.4f})")
    elif bid_buy_ucuzluk > 0.05:
        print(f"  💸 Bid Buy pahalı! ({bid_buy_ucuzluk:.4f})")
    else:
        print(f"  ⚖️ Bid Buy makul fiyatlı ({bid_buy_ucuzluk:.4f})")

if __name__ == "__main__":
    ornek_skor_hesaplama()