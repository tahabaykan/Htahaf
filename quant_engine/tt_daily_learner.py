"""
Truth Tick Daily Learning Agent
================================
Persistent daily analysis that accumulates knowledge over time.

Each run:
1. Fetches truth ticks from Hammer API
2. Analyzes 30-min windows (spread, volume, direction, MM suitability)
3. Saves daily snapshot to persistent storage (JSON per day)
4. Builds cumulative insights across all saved days
5. Sends to Gemini when available (retries on rate limit)

Storage: C:\StockTracker\quant_engine\tt_learning\
  - daily\YYYY-MM-DD.json     — raw daily analysis
  - cumulative_insights.json  — accumulated learning across all days
  - gemini_reports\YYYY-MM-DD.txt — Gemini interpretations

Run: python tt_daily_learner.py
"""
import sys
import os
import asyncio
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, r"C:\StockTracker\quant_engine")

# Load .env
env_path = os.path.join(r"C:\StockTracker\quant_engine", ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Storage paths
LEARNING_DIR = Path(r"C:\StockTracker\quant_engine\tt_learning")
DAILY_DIR = LEARNING_DIR / "daily"
GEMINI_DIR = LEARNING_DIR / "gemini_reports"
CUMULATIVE_FILE = LEARNING_DIR / "cumulative_insights.json"

for d in [LEARNING_DIR, DAILY_DIR, GEMINI_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Setup logging
log_file = LEARNING_DIR / "learner.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("TT_LEARNER")


def setup_hammer():
    """Create standalone Hammer connection."""
    from app.live.hammer_client import HammerClient, set_hammer_client

    password = os.getenv("HAMMER_PASSWORD", "")
    host = os.getenv("HAMMER_HOST", "127.0.0.1")
    port = int(os.getenv("HAMMER_PORT", "16400"))

    if not password:
        log.error("HAMMER_PASSWORD not set!")
        return None

    client = HammerClient(host=host, port=port, password=password)
    if client.connect():
        log.info(f"Hammer connected ({host}:{port})")
        set_hammer_client(client)
        return client
    return None


def load_cumulative() -> dict:
    """Load cumulative insights from disk."""
    if CUMULATIVE_FILE.exists():
        return json.loads(CUMULATIVE_FILE.read_text(encoding="utf-8"))
    return {
        "created": datetime.now().isoformat(),
        "days_analyzed": [],
        "symbol_history": {},  # {symbol: [{date, ticks, vol, spread, direction, ...}]}
        "group_trends": {},    # {group: [{date, direction, total_ticks, ...}]}
        "top_performers": [],  # Consistently high interest scores
        "learning_notes": [],  # Key findings across days
    }


def save_cumulative(data: dict):
    """Save cumulative insights to disk."""
    data["last_updated"] = datetime.now().isoformat()
    CUMULATIVE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def update_cumulative(cumulative: dict, today: str, analysis: dict) -> dict:
    """
    Merge today's analysis into cumulative insights.
    Tracks per-symbol and per-group trends over time.
    """
    if today in cumulative["days_analyzed"]:
        log.info(f"  Day {today} already in cumulative — updating")
    else:
        cumulative["days_analyzed"].append(today)

    groups = analysis.get("groups", {})

    for g_name, g_data in groups.items():
        # Group-level trend tracking
        if g_name not in cumulative["group_trends"]:
            cumulative["group_trends"][g_name] = []

        # Remove old entry for same day if exists
        cumulative["group_trends"][g_name] = [
            e for e in cumulative["group_trends"][g_name] if e.get("date") != today
        ]

        cumulative["group_trends"][g_name].append({
            "date": today,
            "direction": g_data.get("group_direction"),
            "total_ticks": g_data.get("total_ticks_group", 0),
            "active_count": g_data.get("active_count", 0),
            "busiest_window": g_data.get("group_busiest_window"),
            "buyer_vs_seller": g_data.get("buyer_vs_seller"),
        })

        # Keep last 30 days of group trends
        cumulative["group_trends"][g_name] = cumulative["group_trends"][g_name][-30:]

        # Per-stock tracking
        for stock in g_data.get("top_stocks", []):
            sym = stock.get("symbol", "")
            if not sym:
                continue

            if sym not in cumulative["symbol_history"]:
                cumulative["symbol_history"][sym] = []

            # Remove old entry for same day
            cumulative["symbol_history"][sym] = [
                e for e in cumulative["symbol_history"][sym] if e.get("date") != today
            ]

            cumulative["symbol_history"][sym].append({
                "date": today,
                "group": g_name,
                "interest_score": stock.get("interest_score", 0),
                "mm_score": stock.get("mm_score", 0),
                "total_ticks": stock.get("total_ticks", 0),
                "vol_adv_pct": stock.get("vol_adv_total_pct", 0),
                "spread_bps": stock.get("overall_spread_bps", 0),
                "fbtot": stock.get("fbtot"),
                "sfstot": stock.get("sfstot"),
                "gort": stock.get("gort"),
                "busiest_window": stock.get("busiest_window"),
            })

            # Keep last 30 days
            cumulative["symbol_history"][sym] = cumulative["symbol_history"][sym][-30:]

    # Identify consistent top performers (appear in top stocks 3+ times)
    freq = {}
    for sym, hist in cumulative["symbol_history"].items():
        if len(hist) >= 2:
            avg_int = sum(h["interest_score"] for h in hist) / len(hist)
            freq[sym] = {"appearances": len(hist), "avg_interest": round(avg_int, 2)}

    top = sorted(freq.items(), key=lambda x: x[1]["avg_interest"], reverse=True)[:20]
    cumulative["top_performers"] = [{"symbol": s, **d} for s, d in top]

    return cumulative


def try_llm_analysis(analysis: dict, today: str) -> str:
    """
    Send analysis to LLM for interpretation.
    Priority: Claude Haiku ($0.04/day) → Gemini Flash (free) → skip.
    Uses sync calls directly to avoid event loop conflicts.
    """
    from app.agent.truth_tick_analyzer import build_analysis_prompt
    prompt = build_analysis_prompt(analysis)
    log.info(f"  Prompt: {len(prompt)} chars (~{len(prompt)//4} tokens)")

    system_prompt = (
        "Sen QAGENTT — Preferred Stock Trading Learning Agent. "
        "Sadece TRUTH TICK verileri gercek — diger tum printler gurultu. "
        "Volume hesaplamalari sadece truth tick size toplamindan yapilir. "
        "AVG_ADV ise janalldata.csv deki normal deger. "
        "Analizi JSON formatinda ver. Turkce yaz."
    )

    # Try 1: Claude (preferred — reliable, cheap)
    claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    if claude_key:
        try:
            from app.agent.claude_client import ClaudeClient
            client = ClaudeClient(claude_key)  # Haiku 3.5 by default
            log.info(f"  Using Claude Haiku 3.5...")
            response = client._sync_call(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.35,
                max_tokens=4096,
            )
            if response and "ERROR" not in response:
                report_path = GEMINI_DIR / f"{today}.txt"
                report_path.write_text(response, encoding="utf-8")
                log.info(f"  Claude report saved: {report_path.name} ({len(response)} chars)")
                log.info(f"  Cost: {client.stats}")
                return response
            else:
                log.warning(f"  Claude failed: {response[:100]}")
        except Exception as e:
            log.error(f"  Claude error: {e}")

    # Try 2: Gemini Flash (free fallback)
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            from app.agent.gemini_client import GeminiFlashClient
            client = GeminiFlashClient(gemini_key)
            log.info(f"  Falling back to Gemini Flash...")
            response = client._sync_call(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.35,
                max_tokens=4096,
            )
            if response and "ERROR" not in response:
                report_path = GEMINI_DIR / f"{today}.txt"
                report_path.write_text(response, encoding="utf-8")
                log.info(f"  Gemini report saved: {report_path.name} ({len(response)} chars)")
                return response
            else:
                log.warning(f"  Gemini failed: {response[:100]}")
                return response
        except Exception as e:
            log.error(f"  Gemini error: {e}")

    return "[NO_KEY] Neither ANTHROPIC_API_KEY nor GEMINI_API_KEY set"


async def run_daily_learning():
    """Run daily truth tick analysis and persist results."""

    today = datetime.now().strftime("%Y-%m-%d")
    log.info("=" * 80)
    log.info(f"TRUTH TICK DAILY LEARNER — {today}")
    log.info("=" * 80)

    # Step 1: Load static data
    log.info("Step 1: Loading static data...")
    from app.market_data.static_data_store import initialize_static_store
    store = initialize_static_store()
    if not store.load_csv():
        log.error("  janalldata.csv load failed!")
        return
    log.info(f"  {len(store.get_all_symbols())} symbols loaded")

    # Step 2: Connect to Hammer
    log.info("Step 2: Connecting to Hammer...")
    client = setup_hammer()
    if not client:
        log.error("  Hammer connection failed")
        return

    time.sleep(2)

    # Step 3: Run analysis
    log.info("Step 3: Running 5-day truth tick analysis...")
    start = time.time()

    from app.agent.truth_tick_analyzer import analyze_dos_groups
    raw_analysis = analyze_dos_groups(
        lookback_days=5,
        top_n=5,
        use_in_memory=True,
        mode="backtest",
    )

    elapsed = time.time() - start
    log.info(f"  Analysis complete in {elapsed:.0f}s")
    log.info(f"  Symbols: {raw_analysis.get('total_symbols_analyzed', 0)}")
    log.info(f"  Groups: {raw_analysis.get('total_groups', 0)}")

    # Count total ticks
    total_ticks = sum(
        g.get("total_ticks_group", 0)
        for g in raw_analysis.get("groups", {}).values()
    )
    log.info(f"  Total truth ticks analyzed: {total_ticks:,}")

    # Step 4: Save daily snapshot
    log.info("Step 4: Saving daily snapshot...")
    daily_file = DAILY_DIR / f"{today}.json"
    daily_data = {
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "analysis": raw_analysis,
    }
    daily_file.write_text(
        json.dumps(daily_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info(f"  Saved: {daily_file} ({daily_file.stat().st_size/1024:.0f} KB)")

    # Step 5: Update cumulative insights
    log.info("Step 5: Updating cumulative insights...")
    cumulative = load_cumulative()
    cumulative = update_cumulative(cumulative, today, raw_analysis)
    save_cumulative(cumulative)
    log.info(f"  Days in cumulative: {len(cumulative['days_analyzed'])}")
    log.info(f"  Symbols tracked: {len(cumulative['symbol_history'])}")
    log.info(f"  Top performers: {len(cumulative['top_performers'])}")

    # Step 6: Print summary
    log.info("")
    log.info("DAILY SUMMARY:")
    groups = raw_analysis.get("groups", {})
    for g_name in sorted(groups.keys()):
        g = groups[g_name]
        top = g.get("top_stocks", [])
        if not top:
            continue
        leader = top[0]
        log.info(
            f"  {g_name:<24s} "
            f"{g.get('group_direction','?'):>15s} "
            f"ticks={g.get('total_ticks_group',0):>5d} "
            f"leader={leader.get('symbol','?')} (int={leader.get('interest_score',0):.1f})"
        )

    # Step 7: Try Gemini (non-blocking, okay if it fails)
    log.info("")
    log.info("Step 7: Sending to LLM for interpretation...")
    llm_result = try_llm_analysis(raw_analysis, today)
    if llm_result and "ERROR" not in llm_result and "NO_KEY" not in llm_result:
        log.info("  LLM interpretation received!")
        # Add to cumulative
        cumulative["learning_notes"].append({
            "date": today,
            "source": "claude",
            "note": llm_result[:500],  # First 500 chars as summary
        })
        # Keep last 30 notes
        cumulative["learning_notes"] = cumulative["learning_notes"][-30:]
        save_cumulative(cumulative)
    else:
        log.info(f"  LLM skipped: {llm_result[:80] if llm_result else 'no response'}")
        log.info("  Raw analysis is still saved — LLM can be retried later")

    # Step 8: Cross-day insights (if we have multiple days)
    if len(cumulative["days_analyzed"]) > 1:
        log.info("")
        log.info("CROSS-DAY INSIGHTS:")
        log.info(f"  Analyzed days: {', '.join(cumulative['days_analyzed'][-5:])}")

        if cumulative["top_performers"]:
            log.info(f"  Consistent top performers:")
            for p in cumulative["top_performers"][:10]:
                log.info(f"    {p['symbol']:12s} avg_int={p['avg_interest']:.1f} appearances={p['appearances']}")

    # Cleanup
    if client:
        client.disconnect()

    log.info("")
    log.info("=" * 80)
    log.info("DAILY LEARNING COMPLETE")
    log.info(f"  Storage: {LEARNING_DIR}")
    log.info(f"  Daily:   {daily_file.name}")
    log.info(f"  Cumulative: {CUMULATIVE_FILE.name}")
    log.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_daily_learning())
