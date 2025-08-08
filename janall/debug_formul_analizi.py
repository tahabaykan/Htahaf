#!/usr/bin/env python3
"""
Formül analizi - büyük sayıların nereden geldiğini bulalım
"""

def analyze_formula():
    print("🔍 FORMÜL ANALİZİ - BÜYÜK SAYILAR PROBLEMI")
    print("=" * 60)
    
    # Gerçek veriler (tablodaki gibi)
    bid = 15.58        # Bid price
    ask = 15.62        # Ask price
    last = 15.62       # Last price
    prev_close = 14.65 # Previous close (burası kritik!)
    final_thg = 1405.95 # FINAL_THG değeri
    
    print(f"📊 GİRİŞ VERİLERİ:")
    print(f"   Bid: ${bid:.2f}")
    print(f"   Ask: ${ask:.2f}")
    print(f"   Last: ${last:.2f}")
    print(f"   Previous Close: ${prev_close:.2f}")
    print(f"   FINAL_THG: {final_thg}")
    print()
    
    # 1. Spread hesaplama
    spread = ask - bid
    print(f"1️⃣ SPREAD:")
    print(f"   Spread = Ask - Bid = {ask} - {bid} = {spread:.4f}")
    print()
    
    # 2. Passive fiyatlar
    pf_bid_buy = bid + (spread * 0.15)
    pf_front_buy = last + 0.01
    pf_ask_buy = ask + 0.01
    pf_ask_sell = ask - (spread * 0.15)
    pf_front_sell = last - 0.01
    pf_bid_sell = bid - 0.01
    
    print(f"2️⃣ PASSIVE FİYATLAR:")
    print(f"   pf_bid_buy   = {bid} + ({spread} × 0.15) = {pf_bid_buy:.4f}")
    print(f"   pf_front_buy = {last} + 0.01 = {pf_front_buy:.4f}")
    print(f"   pf_ask_buy   = {ask} + 0.01 = {pf_ask_buy:.4f}")
    print(f"   pf_ask_sell  = {ask} - ({spread} × 0.15) = {pf_ask_sell:.4f}")
    print(f"   pf_front_sell= {last} - 0.01 = {pf_front_sell:.4f}")
    print(f"   pf_bid_sell  = {bid} - 0.01 = {pf_bid_sell:.4f}")
    print()
    
    # 3. Previous close'dan farklar (BURASI ÖNEMLİ!)
    pf_bid_buy_chg = pf_bid_buy - prev_close
    pf_front_buy_chg = pf_front_buy - prev_close
    pf_ask_buy_chg = pf_ask_buy - prev_close
    pf_ask_sell_chg = pf_ask_sell - prev_close
    pf_front_sell_chg = pf_front_sell - prev_close
    pf_bid_sell_chg = pf_bid_sell - prev_close
    
    print(f"3️⃣ PREV CLOSE'DAN FARKLAR (DOLAR):")
    print(f"   ⚠️  Previous Close: ${prev_close:.2f} (ÇOK DÜŞÜK!)")
    print(f"   pf_bid_buy_chg   = {pf_bid_buy:.4f} - {prev_close} = {pf_bid_buy_chg:.4f}")
    print(f"   pf_front_buy_chg = {pf_front_buy:.4f} - {prev_close} = {pf_front_buy_chg:.4f}")
    print(f"   pf_ask_buy_chg   = {pf_ask_buy:.4f} - {prev_close} = {pf_ask_buy_chg:.4f}")
    print(f"   pf_ask_sell_chg  = {pf_ask_sell:.4f} - {prev_close} = {pf_ask_sell_chg:.4f}")
    print(f"   pf_front_sell_chg= {pf_front_sell:.4f} - {prev_close} = {pf_front_sell_chg:.4f}")
    print(f"   pf_bid_sell_chg  = {pf_bid_sell:.4f} - {prev_close} = {pf_bid_sell_chg:.4f}")
    print()
    
    # 4. Cent'e çevirme (BÜYÜK SAYILARIN KAYNAĞI!)
    pf_bid_buy_chg_cents = pf_bid_buy_chg * 100
    pf_front_buy_chg_cents = pf_front_buy_chg * 100
    pf_ask_buy_chg_cents = pf_ask_buy_chg * 100
    
    print(f"4️⃣ CENT'E ÇEVİRME (BÜYÜK SAYILARIN KAYNAĞI!):")
    print(f"   💥 pf_bid_buy_chg_cents   = {pf_bid_buy_chg:.4f} × 100 = {pf_bid_buy_chg_cents:.2f}")
    print(f"   💥 pf_front_buy_chg_cents = {pf_front_buy_chg:.4f} × 100 = {pf_front_buy_chg_cents:.2f}")
    print(f"   💥 pf_ask_buy_chg_cents   = {pf_ask_buy_chg:.4f} × 100 = {pf_ask_buy_chg_cents:.2f}")
    print()
    
    # 5. Benchmark (varsayalım -17 cent)
    benchmark_chg_dollars = -0.17
    benchmark_chg_cents = benchmark_chg_dollars * 100
    
    print(f"5️⃣ BENCHMARK:")
    print(f"   benchmark_chg = {benchmark_chg_dollars:.4f} dolar = {benchmark_chg_cents:.2f} cent")
    print()
    
    # 6. Ucuzluk skorları
    bid_buy_ucuzluk = pf_bid_buy_chg_cents - benchmark_chg_cents
    front_buy_ucuzluk = pf_front_buy_chg_cents - benchmark_chg_cents
    ask_buy_ucuzluk = pf_ask_buy_chg_cents - benchmark_chg_cents
    
    print(f"6️⃣ UCUZLUK SKORLARI:")
    print(f"   bid_buy_ucuzluk   = {pf_bid_buy_chg_cents:.2f} - ({benchmark_chg_cents:.2f}) = {bid_buy_ucuzluk:.2f}")
    print(f"   front_buy_ucuzluk = {pf_front_buy_chg_cents:.2f} - ({benchmark_chg_cents:.2f}) = {front_buy_ucuzluk:.2f}")
    print(f"   ask_buy_ucuzluk   = {pf_ask_buy_chg_cents:.2f} - ({benchmark_chg_cents:.2f}) = {ask_buy_ucuzluk:.2f}")
    print()
    
    # 7. Final skorlar
    final_bb = final_thg - 400 * bid_buy_ucuzluk
    final_fb = final_thg - 400 * front_buy_ucuzluk
    final_ab = final_thg - 400 * ask_buy_ucuzluk
    
    print(f"7️⃣ FINAL SKORLAR:")
    print(f"   💥 Final_BB = {final_thg} - 400 × {bid_buy_ucuzluk:.2f} = {final_bb:.2f}")
    print(f"   💥 Final_FB = {final_thg} - 400 × {front_buy_ucuzluk:.2f} = {final_fb:.2f}")
    print(f"   💥 Final_AB = {final_thg} - 400 × {ask_buy_ucuzluk:.2f} = {final_ab:.2f}")
    print()
    
    print("🔍 PROBLEM TESPİTİ:")
    print("=" * 40)
    print(f"❌ Previous Close ({prev_close}) çok düşük!")
    print(f"❌ Current price ({last}) ile prev_close ({prev_close}) arasında {last - prev_close:.2f} dolar fark!")
    print(f"❌ Bu fark cent'e çevrilince {(last - prev_close) * 100:.0f} cent oluyor!")
    print(f"❌ 400 ile çarpılınca final skorlarda {400 * (last - prev_close) * 100:.0f} puanlık değişim!")
    print()
    print("💡 ÇÖZÜM:")
    print("   - Previous close doğru mu kontrol et")
    print("   - Formülde cent çevirme katsayısını düşür")
    print("   - Ya da final skorda 400 çarpanını düşür")

if __name__ == "__main__":
    analyze_formula()