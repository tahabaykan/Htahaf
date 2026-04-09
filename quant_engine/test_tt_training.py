"""
Truth Tick Training — Standalone Backtest with Gemini Analysis
Fetches historical ticks via Hammer API, analyzes 30-min windows,
and sends to Gemini for strategic interpretation.

Usage: python test_tt_training.py
"""
import sys
import os
import asyncio
import json
import time
import logging

sys.path.insert(0, r"C:\StockTracker\quant_engine")

# Load .env file
env_path = os.path.join(r"C:\StockTracker\quant_engine", ".env")
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip())

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            r"C:\StockTracker\quant_engine\tt_output.txt",
            mode='w', encoding='utf-8'
        ),
    ]
)
log = logging.getLogger("TT")


def setup_hammer():
    """Create a standalone Hammer connection."""
    from app.live.hammer_client import HammerClient, set_hammer_client

    password = os.getenv("HAMMER_PASSWORD", "")
    host = os.getenv("HAMMER_HOST", "127.0.0.1")
    port = int(os.getenv("HAMMER_PORT", "16400"))

    if not password:
        log.error("HAMMER_PASSWORD not set!")
        return None

    client = HammerClient(host=host, port=port, password=password)
    if client.connect():
        log.info(f"Hammer Pro connected ({host}:{port})")
        set_hammer_client(client)
        return client
    else:
        log.error("Hammer Pro connection failed")
        return None


async def run_training():
    """Run complete truth tick backtest training with Gemini analysis."""

    log.info("=" * 80)
    log.info("TRUTH TICK BACKTEST TRAINING — GEMINI ANALYSIS")
    log.info("=" * 80)

    # Check Gemini API key
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        log.info(f"Gemini API key: {gemini_key[:8]}...{gemini_key[-4:]}")
    else:
        log.warning("GEMINI_API_KEY not set — Gemini analysis will be skipped!")

    # Step 1: Load static data
    log.info("Loading static data...")
    from app.market_data.static_data_store import initialize_static_store
    store = initialize_static_store()
    if not store.load_csv():
        log.error("janalldata.csv load failed!")
        return
    log.info(f"{len(store.get_all_symbols())} symbols loaded")

    # Step 2: Connect to Hammer
    log.info("Connecting to Hammer Pro...")
    client = setup_hammer()
    if not client:
        log.error("Cannot proceed without Hammer connection.")
        return

    # Wait for auth completion
    time.sleep(2)

    # Step 3: Quick test
    from app.agent.truth_tick_analyzer import fetch_ticks_from_hammer
    test_sym = "NLY PRD"
    test_ticks = fetch_ticks_from_hammer(test_sym, last_few=100)
    log.info(f"Test: {test_sym} -> {len(test_ticks)} truth ticks")
    if test_ticks:
        from datetime import datetime
        oldest = datetime.fromtimestamp(min(t["ts"] for t in test_ticks))
        newest = datetime.fromtimestamp(max(t["ts"] for t in test_ticks))
        total_vol = sum(t["size"] for t in test_ticks)
        log.info(f"  Range: {oldest:%Y-%m-%d %H:%M} -> {newest:%Y-%m-%d %H:%M}")
        log.info(f"  Truth tick volume: {total_vol:,.0f} shares")
        log.info(f"  Venues: {set(t['exch'] for t in test_ticks)}")

    # Step 4: Run full analysis (this calls Gemini internally)
    log.info("")
    log.info("=" * 80)
    log.info("Running full analysis (5 trading days, 30-min windows)...")
    log.info("This will take ~5 minutes to fetch ticks for all 400+ symbols")
    log.info("=" * 80)

    start = time.time()

    from app.agent.truth_tick_analyzer import run_truth_tick_deep_analysis
    result = await run_truth_tick_deep_analysis(
        lookback_days=5,
        top_n=5,
        mode="backtest",
    )

    elapsed = time.time() - start

    if result.get("error"):
        log.error(f"Error: {result['error']}")
        return

    # Step 5: Show summary
    raw = result.get("raw_analysis", {})
    log.info("")
    log.info("=" * 80)
    log.info("SONUCLAR")
    log.info("=" * 80)
    log.info(f"  Symbols: {raw.get('total_symbols_analyzed', 0)}")
    log.info(f"  Groups: {raw.get('total_groups', 0)}")
    log.info(f"  Elapsed: {elapsed:.0f}s")

    groups = raw.get("groups", {})
    for g_name, g_data in sorted(groups.items()):
        top = g_data.get("top_stocks", [])
        if not top:
            continue
        log.info(f"")
        log.info(f"  [{g_name}] {g_data.get('group_direction','?')} | {g_data.get('buyer_vs_seller','')} | ticks={g_data.get('total_ticks_group',0)}")
        for s in top[:3]:
            log.info(
                f"    {s.get('symbol','?'):12s} "
                f"int={s.get('interest_score',0):.1f} "
                f"mm={s.get('mm_score',0):.1f} "
                f"ticks={s.get('total_ticks',0):4d} "
                f"vol/ADV={s.get('vol_adv_total_pct',0):5.0f}% "
                f"sprd={s.get('overall_spread_bps',0):5.1f}bps "
                f"FBtot={str(s.get('fbtot',''))[:7]:>7s} "
                f"SFStot={str(s.get('sfstot',''))[:7]:>7s} "
                f"GORT={str(s.get('gort',''))[:6]:>6s}"
            )

    # Step 6: Gemini output
    if result.get("gemini_interpretation"):
        report = result["gemini_interpretation"]
        log.info("")
        log.info("=" * 80)
        log.info("GEMINI RAPORU")
        log.info("=" * 80)
        for line in report.split("\n"):
            log.info(line)
    else:
        log.info("")
        log.info("Gemini raporu yok — API key kontrol et")

    # Step 7: Save
    output_path = r"C:\StockTracker\quant_engine\tt_training_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    log.info("")
    log.info(f"Result: {output_path}")
    log.info(f"Log: tt_output.txt")

    # Cleanup
    if client:
        client.disconnect()


if __name__ == "__main__":
    asyncio.run(run_training())
