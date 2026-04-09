"""
MM COMPREHENSIVE TRAINING — Real mechanics, group correlation, range trading.
ALL stocks scored for MM suitability. 10x lots. Multiple strategies.
"""
import os, sys, json, math
sys.path.insert(0, r"C:\StockTracker\quant_engine")

with open(r"C:\StockTracker\quant_engine\.env", "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')

# Load analysis
data = json.load(open(r"C:\StockTracker\quant_engine\tt_training_result.json", encoding="utf-8"))
raw = data["raw_analysis"]
groups = raw.get("groups", {})

# Load static data
from app.market_data.static_data_store import initialize_static_store
store = initialize_static_store()
store.load_csv()

# ═══════════════════════════════════════════════════════════════
# Build comprehensive stock data with ALL relevant metrics
# ═══════════════════════════════════════════════════════════════
all_stocks = []
group_stats = {}  # for correlation benchmarking

for g_name, g_data in sorted(groups.items()):
    g_ticks = g_data.get("total_ticks_group", 0)
    g_dir = g_data.get("group_direction", "balanced")
    g_active = g_data.get("active_count", 0)
    g_busiest = g_data.get("group_busiest_window", "")
    g_buyer_seller = g_data.get("buyer_vs_seller", {})
    
    group_stats[g_name] = {
        "ticks": g_ticks,
        "direction": g_dir,
        "active": g_active,
        "busiest": g_busiest,
        "buyer_pct": g_buyer_seller.get("buyer_pct", 50) if isinstance(g_buyer_seller, dict) else 50,
    }
    
    for stock in g_data.get("top_stocks", []):
        sym = stock.get("symbol", "")
        static = store.get_static_data(sym) or {}
        
        avg_adv = float(static.get("AVG_ADV", 0) or 0)
        price = float(static.get("prev_close", 0) or 0)
        fbtot = float(static.get("FINAL_THG", 0) or 0)
        sfstot = float(static.get("SHORT_FINAL", 0) or 0)
        sma246_chg = float(static.get("SMA246 chg", 0) or 0)
        sma63_chg = float(static.get("SMA63 chg", 0) or 0)
        if not price: price = 25.0
        
        days = max(stock.get("days_covered", 1), 1)
        daily_ticks = stock.get("total_ticks", 0) / days
        vol_adv_pct = stock.get("vol_adv_total_pct", 0)
        spread_bps = stock.get("overall_spread_bps", 0)
        
        # Window analysis
        windows = stock.get("window_summary", {})
        busiest = stock.get("busiest_window", "")
        
        # Calculate MM composite score (0-100)
        # Factor 1: Volume/frequency (truth ticks per day) — weight 25%
        vol_score = min(daily_ticks / 50 * 100, 100)  # 50+ ticks/day = 100%
        
        # Factor 2: ADV liquidity — weight 20%
        adv_score = min(avg_adv / 20000 * 100, 100)  # 20K+ ADV = 100%
        
        # Factor 3: Spread opportunity (wider = more profit per RT) — weight 20%
        spread_score = min(spread_bps / 10 * 100, 100)  # 10+ bps = 100%
        
        # Factor 4: Two-way flow (balanced buyer/seller = better MM) — weight 15%
        # If direction is balanced, score high
        dir_map = {"balanced": 100, "buyer_dominant": 60, "seller_dominant": 60}
        direction = stock.get("direction", "balanced")
        if isinstance(direction, dict):
            direction = "balanced"
        flow_score = dir_map.get(str(direction), 50)
        
        # Factor 5: Price range potential (higher spread_bps = range trading) — weight 10%
        range_score = min(spread_bps / 5 * 100, 100)
        
        # Factor 6: Group size/activity (bigger group = better correlation) — weight 10%
        grp_score = min(g_ticks / 2000 * 100, 100)
        
        mm_composite = (
            vol_score * 0.25 +
            adv_score * 0.20 +
            spread_score * 0.20 +
            flow_score * 0.15 +
            range_score * 0.10 +
            grp_score * 0.10
        )
        
        # Suggested lot = ADV * 10-15% (realistic for preferred stocks)
        lot_pct = 0.10  # 10% of ADV
        if avg_adv > 30000:
            lot_pct = 0.08  # slightly less for high ADV
        elif avg_adv < 5000:
            lot_pct = 0.15  # more aggressive for low ADV
        
        suggested_lot = max(100, int(avg_adv * lot_pct / 100) * 100)  # round to 100s
        # Cap at $25K per stock
        max_lot_by_dollar = int(25000 / price / 100) * 100 if price > 0 else 1000
        suggested_lot = min(suggested_lot, max_lot_by_dollar)
        suggested_lot = max(suggested_lot, 100)
        
        dollar_exposure = suggested_lot * price
        
        all_stocks.append({
            "sym": sym,
            "grp": g_name,
            "price": round(price, 2),
            "adv": int(avg_adv),
            "tt_day": round(daily_ticks, 0),
            "va_pct": round(vol_adv_pct, 1),
            "sp_bps": round(spread_bps, 1),
            "mm_pct": round(mm_composite, 0),
            "lot": suggested_lot,
            "lot_usd": round(dollar_exposure, 0),
            "fbtot": round(fbtot, 0),
            "sfstot": round(sfstot, 0),
            "sma63": round(sma63_chg, 2),
            "peak": busiest,
            "g_dir": g_dir[:10],
        })

# Sort by composite MM score
all_stocks.sort(key=lambda x: x["mm_pct"], reverse=True)

# Tier classification
tier_a = [s for s in all_stocks if s["mm_pct"] >= 70]
tier_b = [s for s in all_stocks if 50 <= s["mm_pct"] < 70]
tier_c = [s for s in all_stocks if 30 <= s["mm_pct"] < 50]

print(f"Total: {len(all_stocks)} stocks scored")
print(f"Tier A (70-100%): {len(tier_a)}")
print(f"Tier B (50-69%): {len(tier_b)}")
print(f"Tier C (30-49%): {len(tier_c)}")

# ═══════════════════════════════════════════════════════════════
# Build mega-prompt
# ═══════════════════════════════════════════════════════════════
lines = []
lines.append("## PREFERRED STOCK MM EGITIM — KAPSAMLI ANALIZ\n")
lines.append("5 is gunu truth tick verisiyle 95 hisseye yuzdesel MM skorlamasi yapildi.")
lines.append("Asagidaki veriler GERCEK — truth tick bazli.\n")

lines.append("### MM STRATEJILERI (hepsi kullanilabilir):")
lines.append("**S1. Spread Capture**: Bid+0.01 hidden buy, Ask-0.01 hidden sell. Min $0.05/share.")
lines.append("**S2. Truth Tick Frontlama**: Son print $25.58 ise, buy $25.51 sell $25.57.")
lines.append("**S3. Range Trading**: Hisse $25.40-25.70 arasinda oynuyorsa, alt range'de al ust range'de sat.")
lines.append("**S4. Arka Kademe**: Ilk kademeye degil, 2.-3. kademeye hidden yaz. Fill gelince oteki taraftan cikis bekle.")
lines.append("**S5. Grup Korelasyonu**: DOS grubundaki diger hisseler yukari giderken bu hisse geri kaldiysa = al sinyali.")
lines.append("**S6. Mean Reversion**: GORT dusukse al, yuksekse sat. FBtot/SFStot'a gore yon.\n")

lines.append("### SKORLAMA (0-100, agirlikli):")
lines.append("25% Volume/Frequency + 20% ADV Likidite + 20% Spread + 15% Iki-Yonlu Akis + 10% Range + 10% Grup\n")

lines.append("### EXPOSURE: $500K toplam. Lot = ADV'nin %10-15'i (yuvarlanmis).\n")

lines.append(f"### TIER A — EN IYI MM ADAYLARI ({len(tier_a)} hisse, skor 70-100%):\n")
hdr = f"{'Sym':<13s} {'Grp':<18s} {'Pr$':>6s} {'ADV':>7s} {'TT/d':>4s} {'V/A%':>5s} {'Sp':>4s} {'MM%':>3s} {'Lot':>5s} {'$Exp':>6s} {'FBt':>5s} {'SFt':>5s} {'63d':>5s} {'GDir':>10s} {'Peak':>11s}"
lines.append(hdr)
lines.append("-" * len(hdr))
for s in tier_a:
    lines.append(f"{s['sym']:<13s} {s['grp']:<18s} ${s['price']:>4.0f} {s['adv']:>7,d} {s['tt_day']:>4.0f} {s['va_pct']:>4.0f}% {s['sp_bps']:>4.0f} {s['mm_pct']:>3.0f} {s['lot']:>5d} ${s['lot_usd']:>5.0f} {s['fbtot']:>5.0f} {s['sfstot']:>5.0f} {s['sma63']:>+5.1f} {s['g_dir']:>10s} {s['peak']:>11s}")

lines.append(f"\n### TIER B — IYI MM ADAYLARI ({len(tier_b)} hisse, skor 50-69%):\n")
lines.append(hdr)
lines.append("-" * len(hdr))
for s in tier_b:
    lines.append(f"{s['sym']:<13s} {s['grp']:<18s} ${s['price']:>4.0f} {s['adv']:>7,d} {s['tt_day']:>4.0f} {s['va_pct']:>4.0f}% {s['sp_bps']:>4.0f} {s['mm_pct']:>3.0f} {s['lot']:>5d} ${s['lot_usd']:>5.0f} {s['fbtot']:>5.0f} {s['sfstot']:>5.0f} {s['sma63']:>+5.1f} {s['g_dir']:>10s} {s['peak']:>11s}")

lines.append(f"\n### GRUP BENCHMARK:\n")
for g_name, g in sorted(group_stats.items()):
    lines.append(f"  {g_name:<24s} ticks={g['ticks']:>5d} dir={g['direction']:<18s} buyer%={g['buyer_pct']:>3.0f}% peak={g['busiest']}")

lines.append(f"\n### ANALIZ GOREVI:\n")
lines.append("Butun Tier A ve Tier B hisseler icin MM stratejisi belirle:\n")
lines.append("**A. STRATEJI SECIMI**: Her hisse icin hangi strateji (S1-S6) en uygun? Neden?")
lines.append("Her hisse icin satir: Symbol | Strateji | Neden | BUY mekanigi | SELL mekanigi | Lot | $/roundtrip | RT/gun | Tahmini gun/$\n")
lines.append("**B. SENARYO **: En iyi 5 hisse icin adim adim:")
lines.append("- Truth tick / bid-ask durumunu gor")
lines.append("- Hidden emir yerlesimi (kac lot, nereye, hangi kademe)")
lines.append("- Fill gelince ne yapilir")
lines.append("- Fiyat aleyhine giderse ne yapilir")
lines.append("- Grup benchmark'i nasil kullanilir\n")
lines.append("**C. $500K DAGITIM VE RETURN**:")
lines.append("- Kac hisse secilir? Her birine kac $ exposure?")
lines.append("- Gunluk toplam gelir tahmini (GERCEKCI, fill rate %25-35)")
lines.append("- Aylik ve yillik")
lines.append("- % return ($500K uzerinden)\n")
lines.append("**D. ILK 20 HiSSE DETAY TABLOSU**:")
lines.append("Symbol | Strateji | Lot | $/RT | FillRate% | RT/gun | Gross$/gun | Net$/gun | Aylik$ | Yillik$\n")
lines.append("Gercekci ol. Preferred stock'lar $18-28 arasi, $0.01 tick, dusuk volatilite.")
lines.append("Ama BIRSURU hissede MM yapilabilir — sadece spread capture degil, range/korelasyon da var.")
lines.append("LOTLAR BUYUK OLMALI — ADV'nin %10-15'i. Turkce yaz.")

prompt = "\n".join(lines)

with open(r"C:\StockTracker\quant_engine\tt_learning\gemini_reports\2026-02-16_mm_train_prompt.txt", "w", encoding="utf-8") as f:
    f.write(prompt)

print(f"\nPrompt: {len(prompt)} chars (~{len(prompt)//4} tokens)")

# Send to Claude
from app.agent.claude_client import ClaudeClient
api_key = os.getenv("ANTHROPIC_API_KEY", "")
client = ClaudeClient(api_key)

print("Sending to Claude Haiku 3 (big prompt)...")
response = client._sync_call(
    prompt=prompt,
    system_prompt=(
        "Sen deneyimli preferred stock market maker'sin. Birden fazla MM stratejisi kullaniyorsun: "
        "spread capture, truth tick frontlama, range trading, arka kademe hidden emirler, "
        "grup korelasyon trading, mean reversion. "
        "BIRSURU hissede MM yapilabilir. Sadece spread'e bakma — range, korelasyon, akis da onemli. "
        "LOTLAR BUYUK: ADV'nin %10-15'i. 100 lot minimum. "
        "Fill rate %25-35 arasi. Gercekci ama kapsamli ol. "
        "Her hisse icin ayri strateji ve rakam ver. Turkce yaz."
    ),
    temperature=0.25,
    max_tokens=4096,
)

print(f"\nResponse: {len(response)} chars")
print(f"Cost: {client.stats}")

report_path = r"C:\StockTracker\quant_engine\tt_learning\gemini_reports\2026-02-16_mm_train.txt"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(response)

print(f"Report: {report_path}")
