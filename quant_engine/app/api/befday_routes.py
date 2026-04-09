"""
BEFDAY API Routes

Endpoints for automatic daily position snapshot capture.
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, date
from typing import Optional, Dict, Any
import os
import json

from app.core.logger import logger

router = APIRouter(prefix="/api/befday", tags=["BEFDAY"])


@router.post("/refresh-redis")
async def refresh_befday_redis(account_id: str = Query(..., description="IBKR_PED, IBKR_GUN, or HAMPRO")):
    """
    Invalidate BEFDAY Redis cache for the account so the next load uses CSV (with correct short = negative).
    Call this after fixing befibped.csv so the UI and other consumers get updated BEFDAY from CSV.
    """
    try:
        from app.core.redis_client import get_redis_client
        redis = get_redis_client()
        if not redis:
            raise HTTPException(status_code=503, detail="Redis not available")
        key = f"psfalgo:befday:positions:{account_id}"
        redis.delete(key)
        logger.info(f"[BEFDAY] Redis key deleted: {key}. Next load will use CSV and repopulate.")
        return {"success": True, "message": f"BEFDAY Redis cleared for {account_id}. Reload positions to refresh from CSV."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BEFDAY] refresh-redis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Track which accounts have been captured today
_daily_captures: Dict[str, str] = {}  # {account: date_str}

# Output directory for befday files
BEFDAY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "befday")


def get_today_str() -> str:
    """Get today's date as YYYYMMDD string"""
    return datetime.now().strftime("%Y%m%d")


def has_captured_today(account: str) -> bool:
    """Check if account was already captured today WITH VALID POSITIONS.
    
    A capture with 0 positions is NOT a valid capture — it means
    the broker connection wasn't ready yet. We must allow re-capture.
    """
    today = get_today_str()
    
    # Check in-memory cache first
    if _daily_captures.get(account) == today:
        return True
    
    # Check if file exists AND has positions > 0
    json_path = os.path.join(BEFDAY_DIR, f"bef{account}_{today}.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            position_count = data.get('position_count', 0)
            if position_count > 0:
                _daily_captures[account] = today
                return True
            else:
                # File exists but 0 positions — NOT a valid capture
                logger.warning(f"[BEFDAY] Found {json_path} but position_count=0 — allowing re-capture")
                return False
        except Exception as e:
            logger.warning(f"[BEFDAY] Error reading {json_path}: {e}")
            return False
    
    return False


def save_befday_snapshot(account: str, positions: list) -> Dict[str, Any]:
    """
    Save positions to befday JSON and CSV files.
    
    CRITICAL GUARD: Refuses to save if positions list is empty.
    A 0-position capture would block all future captures for the day.
    
    Args:
        account: Account name (ham, ibped, ibgun)
        positions: List of position dicts
        
    Returns:
        Result dict with file paths
    """
    # ═══════════════════════════════════════════════════════════════════
    # CRITICAL: NEVER save 0-position snapshots!
    # A 0-position JSON file tricks has_captured_today() into returning 
    # True, which blocks all future capture attempts for the entire day.
    # ═══════════════════════════════════════════════════════════════════
    if not positions:
        logger.error(f"[BEFDAY] ❌ REFUSED to save 0-position snapshot for {account} — "
                     f"this would block all captures for the rest of the day!")
        return {
            "success": False,
            "account": account,
            "date": get_today_str(),
            "position_count": 0,
            "error": "Cannot save BEFDAY with 0 positions — broker data not ready"
        }
    
    today = get_today_str()
    timestamp = datetime.now().isoformat()
    
    # Ensure directory exists
    os.makedirs(BEFDAY_DIR, exist_ok=True)
    
    # File paths (dated files in quant_engine/befday/)
    json_path = os.path.join(BEFDAY_DIR, f"bef{account}_{today}.json")
    csv_path = os.path.join(BEFDAY_DIR, f"bef{account}_{today}.csv")
    
    # Canonical CSV path (what _load_befday_map reads from: C:\StockTracker\befham.csv etc)
    # FIXED: Previous code used os.path.dirname(BEFDAY_DIR) x3 which resolved to C:\ (WRONG!)
    # BEFDAY_DIR = C:\StockTracker\quant_engine\befday
    #   dirname x1 = C:\StockTracker\quant_engine
    #   dirname x2 = C:\StockTracker  ← CORRECT
    #   dirname x3 = C:\              ← BUG! CSV was written to C:\befibped.csv
    CANONICAL_MAP = {"ham": "befham.csv", "ibped": "befibped.csv", "ibgun": "befibgun.csv"}
    canonical_csv = os.path.join("C:\\StockTracker", CANONICAL_MAP.get(account, f"bef{account}.csv"))
    
    # Prepare snapshot data
    snapshot = {
        "account": account,
        "capture_date": today,
        "capture_time": timestamp,
        "position_count": len(positions),
        "positions": positions
    }
    
    # Save JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    
    # Save CSV (both dated and canonical)
    # CRITICAL: Column names MUST be capitalized to match _load_befday_map expectations
    # (Symbol, Quantity, Avg_Cost, etc.) — NOT lowercase!
    import csv
    fieldnames = ['Export_Time', 'Symbol', 'Book', 'Strategy', 'Origin', 'Side',
                  'Full_Taxonomy', 'Position_Type', 'Quantity', 'Avg_Cost',
                  'Market_Value', 'Unrealized_PnL', 'Account']
    
    for target_path in [csv_path, canonical_csv]:
        with open(target_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for pos in positions:
                writer.writerow(pos)
    
    logger.info(f"[BEFDAY] Also wrote canonical CSV: {canonical_csv}")
    
    # Update cache — ONLY after successful write with real positions
    _daily_captures[account] = today
    
    logger.info(f"[BEFDAY] ✅ Captured {len(positions)} positions for {account} → {json_path}")
    
    return {
        "success": True,
        "account": account,
        "date": today,
        "position_count": len(positions),
        "json_path": json_path,
        "csv_path": csv_path,
        "canonical_csv": canonical_csv
    }


@router.post("/capture/{account}")
async def capture_befday(account: str, force: bool = False):
    """
    Capture BEFDAY positions for an account.
    
    Args:
        account: Account name - "ham" (HammerPro), "ibped" (IBKR Ped), "ibgun" (IBKR Gun)
        force: If True, capture even if already captured today
        
    Returns:
        Capture result or skip message
    """
    valid_accounts = ["ham", "ibped", "ibgun"]
    if account not in valid_accounts:
        raise HTTPException(status_code=400, detail=f"Invalid account. Must be one of: {valid_accounts}")
    
    # Check if already captured today (skip if force=True for manual override)
    if not force and has_captured_today(account):
        return {
            "success": True,
            "already_captured": True,
            "account": account,
            "date": get_today_str(),
            "message": f"{account} already captured today — BEFDAY is sacred, 1 capture per day only"
        }
    
    # ADDITIONAL CHECK: Redis key exists AND belongs to TODAY?
    # ═══════════════════════════════════════════════════════════════════
    # CRITICAL FIX: Old code only checked if the key EXISTS.
    # But the key has a 24-hour TTL, so a key written at 20:18 yesterday
    # would still be alive at 09:00 today, blocking today's capture!
    # 
    # NEW LOGIC: Check the companion date key (psfalgo:befday:date:{account})
    # to verify the data actually belongs to today. If it's stale, delete it.
    # ═══════════════════════════════════════════════════════════════════
    if not force:
        try:
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if redis:
                account_map = {"ham": "HAMPRO", "ibped": "IBKR_PED", "ibgun": "IBKR_GUN"}
                redis_account = account_map.get(account, account)
                redis_key = f"psfalgo:befday:positions:{redis_account}"
                date_key = f"psfalgo:befday:date:{redis_account}"
                
                existing = redis.get(redis_key)
                if existing:
                    # Verify date matches TODAY
                    stored_date = redis.get(date_key)
                    stored_date_str = stored_date.decode() if isinstance(stored_date, bytes) else stored_date
                    today = get_today_str()
                    
                    if stored_date_str == today:
                        # Key is from today — skip capture
                        _daily_captures[account] = today
                        return {
                            "success": True,
                            "already_captured": True,
                            "account": account,
                            "date": today,
                            "message": f"{account} already captured today (Redis key exists with today's date) — BEFDAY is sacred"
                        }
                    else:
                        # Key is STALE (from yesterday or earlier) — delete and allow re-capture!
                        redis.delete(redis_key)
                        redis.delete(date_key)
                        logger.warning(
                            f"[BEFDAY] 🗑️ Deleted STALE Redis BEFDAY key for {redis_account}: "
                            f"stored date={stored_date_str}, today={today}"
                        )
        except Exception:
            pass
    
    try:
        # Get positions based on account type
        positions = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if account == "ham":
            # Get HAMPRO positions — same approach as /api/trading/positions endpoint
            try:
                from app.trading.hammer_positions_service import HammerPositionsService
                pos_service = HammerPositionsService()
                
                # Set hammer client from the live feed
                from app.live.hammer_feed import get_hammer_feed
                feed = get_hammer_feed()
                if feed and hasattr(feed, 'hammer_client'):
                    from app.config.settings import settings
                    pos_service.set_hammer_client(feed.hammer_client, settings.HAMMER_ACCOUNT_KEY)
                
                raw = pos_service.get_positions(force_refresh=True)
                if raw:
                    # ═══════════════════════════════════════════════════════════
                    # CRITICAL: Determine LT/MM book from Internal Ledger
                    # The raw position data has NO book field — if we default
                    # everything to 'LT', MM positions get misclassified and
                    # the entire tag chain breaks (fill inference, UI taxonomy).
                    # ═══════════════════════════════════════════════════════════
                    ledger = None
                    try:
                        from app.psfalgo.internal_ledger_store import get_internal_ledger_store, initialize_internal_ledger_store
                        ledger = get_internal_ledger_store()
                        if not ledger:
                            initialize_internal_ledger_store()
                            ledger = get_internal_ledger_store()
                    except Exception:
                        pass
                    
                    for p in raw:
                        qty_val = float(p.get('quantity', p.get('qty', 0)) or 0)
                        if qty_val == 0:
                            continue
                        side = "Long" if qty_val > 0 else "Short"
                        pos_type = "LONG" if qty_val > 0 else "SHORT"
                        sym = p.get('symbol', '')
                        
                        # Determine book from Internal Ledger
                        book = 'LT'  # default
                        if ledger and sym:
                            lt_qty = ledger.get_lt_quantity("HAMPRO", sym)
                            mm_qty = qty_val - lt_qty
                            # Dominant bucket by absolute size
                            if abs(mm_qty) > abs(lt_qty) and abs(mm_qty) > 0.01:
                                book = 'MM'
                            elif abs(lt_qty) > 0.01:
                                book = 'LT'
                        
                        positions.append({
                            "Export_Time": timestamp,
                            "Symbol": sym,
                            "Book": book,
                            "Strategy": book,
                            "Origin": "OV",
                            "Side": side,
                            "Full_Taxonomy": f"{book} OV {side}",
                            "Position_Type": pos_type,
                            "Quantity": qty_val,
                            "Avg_Cost": p.get('avg_cost', p.get('avg_price', p.get('AveragePrice', 0))),
                            "Market_Value": p.get('market_value', p.get('MarketValue', 0)),
                            "Unrealized_PnL": p.get('unrealized_pnl', p.get('UnrealizedPnL', 0)),
                            "Account": "HAMPRO"
                        })
                    logger.info(f"[BEFDAY] Got {len(positions)} HAMPRO positions via HammerPositionsService (with Ledger book resolution)")
                else:
                    logger.warning("[BEFDAY] HammerPositionsService returned no positions")
            except Exception as hps_err:
                logger.warning(f"[BEFDAY] HammerPositionsService failed: {hps_err}", exc_info=True)
            
            # ═══════════════════════════════════════════════════════════════════
            # FALLBACK 1: Redis cached positions (PositionRedisWorker writes these)
            # On startup, Hammer WS hasn't loaded positions yet (3s timeout fails),
            # but a previous session's positions are still in Redis. These are valid
            # for BEFDAY because overnight positions don't change.
            # ═══════════════════════════════════════════════════════════════════
            if not positions:
                try:
                    from app.core.redis_client import get_redis_client
                    import json as _json
                    redis = get_redis_client()
                    redis_key = "psfalgo:positions:HAMPRO"
                    raw_data = redis.get(redis_key) if redis else None
                    if raw_data:
                        raw_str = raw_data.decode() if isinstance(raw_data, bytes) else raw_data
                        redis_data = _json.loads(raw_str)
                        
                        # Handle both dict format {symbol: {qty, ...}} and list format
                        if isinstance(redis_data, dict):
                            items = [(k, v) for k, v in redis_data.items() if k != '_meta']
                        elif isinstance(redis_data, list):
                            items = [(p.get('symbol', ''), p) for p in redis_data]
                        else:
                            items = []
                        
                        if items:
                            # Ledger for book resolution
                            ledger_fb = None
                            try:
                                from app.psfalgo.internal_ledger_store import get_internal_ledger_store
                                ledger_fb = get_internal_ledger_store()
                            except Exception:
                                pass
                            
                            for sym, p in items:
                                if not sym or sym == '_meta':
                                    continue
                                if isinstance(p, dict):
                                    qty_val = float(p.get('qty', p.get('quantity', 0)) or 0)
                                else:
                                    continue
                                if qty_val == 0:
                                    continue
                                if not sym:
                                    sym = p.get('symbol', '')
                                side = "Long" if qty_val > 0 else "Short"
                                pos_type = "LONG" if qty_val > 0 else "SHORT"
                                avg_cost_val = float(p.get('avg_price', p.get('avg_cost', 0)) or 0)
                                market_val = avg_cost_val * abs(qty_val) if avg_cost_val > 0 else 0
                                # Book from ledger
                                book = 'LT'
                                if ledger_fb and sym:
                                    lt_q = ledger_fb.get_lt_quantity("HAMPRO", sym)
                                    mm_q = qty_val - lt_q
                                    if abs(mm_q) > abs(lt_q) and abs(mm_q) > 0.01:
                                        book = 'MM'
                                positions.append({
                                    "Export_Time": timestamp,
                                    "Symbol": sym,
                                    "Book": book,
                                    "Strategy": book,
                                    "Origin": "OV",
                                    "Side": side,
                                    "Full_Taxonomy": f"{book} OV {side}",
                                    "Position_Type": pos_type,
                                    "Quantity": qty_val,
                                    "Avg_Cost": avg_cost_val,
                                    "Market_Value": market_val,
                                    "Unrealized_PnL": 0,
                                    "Account": "HAMPRO"
                                })
                            if positions:
                                logger.info(f"[BEFDAY] Got {len(positions)} HAMPRO positions via Redis fallback (psfalgo:positions:HAMPRO)")
                except Exception as redis_fb_err:
                    logger.warning(f"[BEFDAY] HAMPRO Redis fallback failed: {redis_fb_err}")
            
            # ═══════════════════════════════════════════════════════════════════
            # FALLBACK 2: data_fabric (internal position store)
            # ═══════════════════════════════════════════════════════════════════
            if not positions:
                try:
                    from app.core.data_fabric import get_data_fabric
                    fabric = get_data_fabric()
                    if fabric and hasattr(fabric, 'get_all_positions'):
                        raw_positions = fabric.get_all_positions(mode="hampro")
                        if raw_positions:
                            ledger_df = None
                            try:
                                from app.psfalgo.internal_ledger_store import get_internal_ledger_store
                                ledger_df = get_internal_ledger_store()
                            except Exception:
                                pass
                            for sym, pos in raw_positions.items():
                                qty_val = float(pos.get('quantity', pos.get('qty', 0)) or 0)
                                if qty_val == 0:
                                    continue
                                side = "Long" if qty_val > 0 else "Short"
                                pos_type = "LONG" if qty_val > 0 else "SHORT"
                                book = 'LT'
                                if ledger_df and sym:
                                    lt_q = ledger_df.get_lt_quantity("HAMPRO", sym)
                                    mm_q = qty_val - lt_q
                                    if abs(mm_q) > abs(lt_q) and abs(mm_q) > 0.01:
                                        book = 'MM'
                                positions.append({
                                    "Export_Time": timestamp,
                                    "Symbol": sym,
                                    "Book": book,
                                    "Strategy": book,
                                    "Origin": "OV",
                                    "Side": side,
                                    "Full_Taxonomy": f"{book} OV {side}",
                                    "Position_Type": pos_type,
                                    "Quantity": qty_val,
                                    "Avg_Cost": pos.get('avg_cost', 0),
                                    "Market_Value": pos.get('market_value', 0),
                                    "Unrealized_PnL": pos.get('unrealized_pnl', 0),
                                    "Account": "HAMPRO"
                                })
                            if positions:
                                logger.info(f"[BEFDAY] Got {len(positions)} HAMPRO positions via data_fabric fallback")
                except Exception:
                    pass
        
        elif account in ["ibped", "ibgun"]:
            # Get IBKR positions via ibkr_connector
            try:
                from app.psfalgo.ibkr_connector import get_positions_isolated_sync
                account_type = "IBKR_PED" if account == "ibped" else "IBKR_GUN"
                raw = get_positions_isolated_sync(account_type)
                if raw:
                    positions = []
                    
                    # Ledger for LT/MM book resolution
                    ledger = None
                    try:
                        from app.psfalgo.internal_ledger_store import get_internal_ledger_store, initialize_internal_ledger_store
                        ledger = get_internal_ledger_store()
                        if not ledger:
                            initialize_internal_ledger_store()
                            ledger = get_internal_ledger_store()
                    except Exception:
                        pass
                    
                    for p in raw:
                        qty_val = float(p.get('qty', 0) or 0)
                        if qty_val == 0:
                            continue
                        side = "Long" if qty_val > 0 else "Short"
                        pos_type = "LONG" if qty_val > 0 else "SHORT"
                        avg_cost_val = float(p.get('avg_price', 0) or 0)
                        market_val = avg_cost_val * abs(qty_val) if avg_cost_val > 0 else 0
                        sym = p.get('symbol', '')
                        
                        # Determine book from Internal Ledger
                        book = 'LT'  # default
                        if ledger and sym:
                            lt_qty = ledger.get_lt_quantity(account_type, sym)
                            mm_qty = qty_val - lt_qty
                            if abs(mm_qty) > abs(lt_qty) and abs(mm_qty) > 0.01:
                                book = 'MM'
                        
                        positions.append({
                            "Export_Time": timestamp,
                            "Symbol": sym,
                            "Book": book,
                            "Strategy": book,
                            "Origin": "OV",
                            "Side": side,
                            "Full_Taxonomy": f"{book} OV {side}",
                            "Position_Type": pos_type,
                            "Quantity": qty_val,
                            "Avg_Cost": avg_cost_val,
                            "Market_Value": market_val,
                            "Unrealized_PnL": 0,
                            "Account": account_type
                        })
                    logger.info(f"[BEFDAY] Got {len(positions)} {account_type} positions via ibkr_connector (with Ledger book resolution)")
            except Exception as ibkr_err:
                logger.warning(f"[BEFDAY] ibkr_connector failed: {ibkr_err}")
            
            # Fallback: Redis cached positions (PositionRedisWorker writes these)
            if not positions:
                try:
                    from app.core.redis_client import get_redis_client
                    import json as _json
                    redis = get_redis_client()
                    account_type = "IBKR_PED" if account == "ibped" else "IBKR_GUN"
                    redis_key = f"psfalgo:positions:{account_type}"
                    raw_data = redis.get(redis_key) if redis else None
                    if raw_data:
                        raw_str = raw_data.decode() if isinstance(raw_data, bytes) else raw_data
                        redis_data = _json.loads(raw_str)
                        
                        # Handle both dict format {symbol: {qty, ...}} and list format [{symbol, qty, ...}]
                        if isinstance(redis_data, dict):
                            items = redis_data.items()
                        elif isinstance(redis_data, list):
                            items = [(p.get('symbol', ''), p) for p in redis_data]
                        else:
                            items = []
                        
                        if items:
                            positions = []
                            # Ledger for book resolution
                            ledger_fb = None
                            try:
                                from app.psfalgo.internal_ledger_store import get_internal_ledger_store
                                ledger_fb = get_internal_ledger_store()
                            except Exception:
                                pass
                            for sym, p in items:
                                if sym == '_meta':
                                    continue
                                if isinstance(p, dict):
                                    qty_val = float(p.get('qty', p.get('quantity', 0)) or 0)
                                else:
                                    continue
                                if qty_val == 0:
                                    continue
                                if not sym:
                                    sym = p.get('symbol', '')
                                side = "Long" if qty_val > 0 else "Short"
                                pos_type = "LONG" if qty_val > 0 else "SHORT"
                                avg_cost_val = float(p.get('avg_price', p.get('avg_cost', 0)) or 0)
                                market_val = avg_cost_val * abs(qty_val) if avg_cost_val > 0 else 0
                                # Determine book from Ledger
                                book = 'LT'
                                if ledger_fb and sym:
                                    lt_q = ledger_fb.get_lt_quantity(account_type, sym)
                                    mm_q = qty_val - lt_q
                                    if abs(mm_q) > abs(lt_q) and abs(mm_q) > 0.01:
                                        book = 'MM'
                                positions.append({
                                    "Export_Time": timestamp,
                                    "Symbol": sym,
                                    "Book": book,
                                    "Strategy": book,
                                    "Origin": "OV",
                                    "Side": side,
                                    "Full_Taxonomy": f"{book} OV {side}",
                                    "Position_Type": pos_type,
                                    "Quantity": qty_val,
                                    "Avg_Cost": avg_cost_val,
                                    "Market_Value": market_val,
                                    "Unrealized_PnL": 0,
                                    "Account": account_type
                                })
                            logger.info(f"[BEFDAY] Got {len(positions)} {account_type} positions via Redis cached positions fallback")
                except Exception as redis_fb_err:
                    logger.warning(f"[BEFDAY] Redis fallback also failed: {redis_fb_err}")
            
            # Fallback: data_fabric
            if not positions:
                try:
                    from app.core.data_fabric import get_data_fabric
                    fabric = get_data_fabric()
                    mode = "ibkr_ped" if account == "ibped" else "ibkr_gun"
                    if fabric and hasattr(fabric, 'get_all_positions'):
                        raw_positions = fabric.get_all_positions(mode=mode)
                        if raw_positions:
                            positions = []
                            # Ledger for book resolution
                            ledger_df = None
                            try:
                                from app.psfalgo.internal_ledger_store import get_internal_ledger_store
                                ledger_df = get_internal_ledger_store()
                            except Exception:
                                pass
                            for sym, pos in raw_positions.items():
                                qty_val = float(pos.get('quantity', 0) or 0)
                                if qty_val == 0:
                                    continue
                                side = "Long" if qty_val > 0 else "Short"
                                pos_type = "LONG" if qty_val > 0 else "SHORT"
                                book = 'LT'
                                if ledger_df and sym:
                                    lt_q = ledger_df.get_lt_quantity(account_type, sym)
                                    mm_q = qty_val - lt_q
                                    if abs(mm_q) > abs(lt_q) and abs(mm_q) > 0.01:
                                        book = 'MM'
                                positions.append({
                                    "Export_Time": timestamp,
                                    "Symbol": sym,
                                    "Book": book,
                                    "Strategy": book,
                                    "Origin": "OV",
                                    "Side": side,
                                    "Full_Taxonomy": f"{book} OV {side}",
                                    "Position_Type": pos_type,
                                    "Quantity": qty_val,
                                    "Avg_Cost": pos.get('avg_cost', 0),
                                    "Market_Value": pos.get('market_value', 0),
                                    "Unrealized_PnL": pos.get('unrealized_pnl', 0),
                                    "Account": mode
                                })
                except Exception:
                    pass
        
        # ═══════════════════════════════════════════════════════════════════
        # GUARD: Refuse to save if 0 positions were retrieved.
        # This prevents a poison-pill JSON that blocks all future captures.
        # ═══════════════════════════════════════════════════════════════════
        if not positions:
            logger.error(f"[BEFDAY] ❌ {account} returned 0 positions — NOT saving. "
                         f"Broker may not be ready. Re-try will happen on next click or reconnect.")
            return {
                "success": False,
                "account": account,
                "date": get_today_str(),
                "position_count": 0,
                "error": "No positions retrieved from broker — BEFDAY NOT captured"
            }
        
        # Save snapshot
        result = save_befday_snapshot(account, positions)
        
        # Also write to Redis for terminals
        if result.get("success") and positions:
            try:
                from app.core.redis_client import get_redis_client
                redis = get_redis_client()
                if redis:
                    account_map = {"ham": "HAMPRO", "ibped": "IBKR_PED", "ibgun": "IBKR_GUN"}
                    redis_key = f"psfalgo:befday:positions:{account_map.get(account, account)}"
                    
                    # Clear any stale Redis BEFDAY key first
                    redis.delete(redis_key)
                    
                    befday_list = [
                        {"symbol": p.get("Symbol", ""), "qty": float(p.get("Quantity", 0)),
                         "avg_cost": p.get("Avg_Cost", 0), "side": p.get("Side", ""),
                         "full_taxonomy": p.get("Full_Taxonomy", "")}
                        for p in positions if p.get("Symbol")
                    ]
                    redis.set(redis_key, json.dumps(befday_list), ex=86400)
                    
                    # Write companion date key so staleness check knows WHEN this was captured
                    redis_account = account_map.get(account, account)
                    date_key = f"psfalgo:befday:date:{redis_account}"
                    redis.set(date_key, get_today_str(), ex=86400)
                    
                    logger.info(f"[BEFDAY] ✅ Redis written: {len(befday_list)} entries for {account} + date key (sacred, first & only write)")
            except Exception as redis_err:
                logger.warning(f"[BEFDAY] Redis write failed: {redis_err}")
        
        return result
        
    except Exception as e:
        logger.error(f"[BEFDAY] Error capturing {account}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_befday_status():
    """
    Get today's BEFDAY capture status for all accounts.
    
    Returns:
        Status for each account (captured or not)
    """
    today = get_today_str()
    
    accounts = {
        "ham": {
            "name": "HammerPro",
            "captured": has_captured_today("ham"),
            "file": f"befham_{today}.json" if has_captured_today("ham") else None
        },
        "ibped": {
            "name": "IBKR Ped",
            "captured": has_captured_today("ibped"),
            "file": f"befibped_{today}.json" if has_captured_today("ibped") else None
        },
        "ibgun": {
            "name": "IBKR Gun",
            "captured": has_captured_today("ibgun"),
            "file": f"befibgun_{today}.json" if has_captured_today("ibgun") else None
        }
    }
    
    return {
        "success": True,
        "date": today,
        "befday_dir": BEFDAY_DIR,
        "accounts": accounts
    }


@router.get("/files")
async def list_befday_files():
    """
    List all BEFDAY files in the directory.
    """
    if not os.path.exists(BEFDAY_DIR):
        return {"success": True, "files": [], "directory": BEFDAY_DIR}
    
    files = []
    for f in os.listdir(BEFDAY_DIR):
        if f.endswith('.json') or f.endswith('.csv'):
            path = os.path.join(BEFDAY_DIR, f)
            files.append({
                "name": f,
                "size": os.path.getsize(path),
                "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
            })
    
    return {
        "success": True,
        "directory": BEFDAY_DIR,
        "file_count": len(files),
        "files": sorted(files, key=lambda x: x['name'], reverse=True)
    }
