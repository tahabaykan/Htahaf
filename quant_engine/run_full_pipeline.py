"""Full pipeline: all stocks, save results to file."""
import sys, time
sys.path.insert(0, '.')
from app.agent.exdiv_pipeline import (
    run_detection, run_patterns, export_results, print_top_results
)

t0 = time.time()

# Adım 1: Tüm hisselerde ex-div tarih tespiti
print("ADIM 1: Ex-div tarih tespiti...")
detections = run_detection(verbose=True)

# Adım 2: Pattern hesaplama
print("\nADIM 2: Pattern hesaplama...")
all_data = run_patterns(detections, verbose=True)

# Adım 3: Export
print("\nADIM 3: Export...")
sdf = export_results(all_data)

# TOP 25 Sharpe
print_top_results(all_data, top_n=25)

elapsed = time.time() - t0
print(f"\nToplam süre: {elapsed:.1f}s")

# Detaylı sonuçları dosyaya kaydet
with open('full_pipeline_results.txt', 'w') as f:
    f.write("EX-DIV PIPELINE v5 - FULL RESULTS\n")
    f.write(f"Total: {len(all_data)} stocks analyzed\n")
    f.write(f"Time: {elapsed:.1f}s\n\n")
    
    # Sort by best sharpe
    ranked = []
    for tk, d in all_data.items():
        strats = d['patterns'].get('strategies', [])
        best = max(strats, key=lambda s: s.get('sharpe', 0), default=None)
        if best:
            ranked.append((tk, d, best))
    ranked.sort(key=lambda x: x[2]['sharpe'], reverse=True)
    
    f.write(f"{'Rank':>4s} {'Ticker':14s} {'Strategy':16s} {'Entry':>6s} {'Exit':>5s} "
            f"{'Ret%':>6s} {'Win%':>5s} {'Sharpe':>7s} {'pVal':>6s} {'n':>3s} "
            f"{'ExDivQ':>6s} {'Yield':>5s}\n")
    f.write("-" * 95 + "\n")
    
    for i, (tk, d, best) in enumerate(ranked):
        det = d['detection']
        pi = d['price_info']
        sig = '***' if best['pval'] < 0.05 else '**' if best['pval'] < 0.10 else ''
        f.write(f"{i+1:>4d} {tk:14s} {best['name']:16s} "
                f"d{best['entry_day']:+3d}  d{best['exit_day']:+3d} "
                f"{best['avg_ret']:>+5.2f}% {best['win_rate']:>4.0%} "
                f"{best['sharpe']:>+6.2f} {best['pval']:>5.3f} {best['n_trades']:>3d} "
                f"{det['quality']:>6s} {pi['yield_pct']:>4.1f}% {sig}\n")

print("Done -> full_pipeline_results.txt")
