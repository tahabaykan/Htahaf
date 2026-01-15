"""
BEFDAY API Routes

Endpoints for automatic daily position snapshot capture.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, date
from typing import Optional, Dict, Any
import os
import json

from app.core.logger import logger

router = APIRouter(prefix="/api/befday", tags=["BEFDAY"])

# Track which accounts have been captured today
_daily_captures: Dict[str, str] = {}  # {account: date_str}

# Output directory for befday files
BEFDAY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "befday")


def get_today_str() -> str:
    """Get today's date as YYYYMMDD string"""
    return datetime.now().strftime("%Y%m%d")


def has_captured_today(account: str) -> bool:
    """Check if account was already captured today"""
    today = get_today_str()
    
    # Check in-memory cache first
    if _daily_captures.get(account) == today:
        return True
    
    # Check if file exists
    json_path = os.path.join(BEFDAY_DIR, f"bef{account}_{today}.json")
    if os.path.exists(json_path):
        _daily_captures[account] = today
        return True
    
    return False


def save_befday_snapshot(account: str, positions: list) -> Dict[str, Any]:
    """
    Save positions to befday JSON and CSV files.
    
    Args:
        account: Account name (ham, ibped, ibgun)
        positions: List of position dicts
        
    Returns:
        Result dict with file paths
    """
    today = get_today_str()
    timestamp = datetime.now().isoformat()
    
    # Ensure directory exists
    os.makedirs(BEFDAY_DIR, exist_ok=True)
    
    # File paths
    json_path = os.path.join(BEFDAY_DIR, f"bef{account}_{today}.json")
    csv_path = os.path.join(BEFDAY_DIR, f"bef{account}_{today}.csv")
    
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
    
    # Save CSV
    if positions:
        import csv
        fieldnames = ['symbol', 'quantity', 'avg_cost', 'market_value', 'unrealized_pnl', 
                      'position_type', 'book', 'account']
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for pos in positions:
                writer.writerow(pos)
    
    # Update cache
    _daily_captures[account] = today
    
    logger.info(f"[BEFDAY] ✅ Captured {len(positions)} positions for {account} → {json_path}")
    
    return {
        "success": True,
        "account": account,
        "date": today,
        "position_count": len(positions),
        "json_path": json_path,
        "csv_path": csv_path
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
    
    # Check if already captured today
    if not force and has_captured_today(account):
        return {
            "success": True,
            "already_captured": True,
            "account": account,
            "date": get_today_str(),
            "message": f"{account} already captured today"
        }
    
    try:
        # Get positions based on account type
        positions = []
        
        if account == "ham":
            # Get HammerPro positions
            from app.live.hammer_feed import get_hammer_feed
            feed = get_hammer_feed()
            if feed and hasattr(feed, 'positions'):
                positions = [
                    {
                        "symbol": sym,
                        "quantity": pos.get('quantity', 0),
                        "avg_cost": pos.get('avg_cost', 0),
                        "market_value": pos.get('market_value', 0),
                        "unrealized_pnl": pos.get('unrealized_pnl', 0),
                        "position_type": "LONG" if pos.get('quantity', 0) > 0 else "SHORT" if pos.get('quantity', 0) < 0 else "FLAT",
                        "book": pos.get('book', 'LT'),
                        "account": "hampro"
                    }
                    for sym, pos in feed.positions.items()
                    if pos.get('quantity', 0) != 0
                ]
        
        elif account in ["ibped", "ibgun"]:
            # Get IBKR positions (placeholder - needs IBKR integration)
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            mode = "ibkr_ped" if account == "ibped" else "ibkr_gun"
            
            if fabric and hasattr(fabric, 'get_all_positions'):
                raw_positions = fabric.get_all_positions(mode=mode)
                if raw_positions:
                    positions = [
                        {
                            "symbol": sym,
                            "quantity": pos.get('quantity', 0),
                            "avg_cost": pos.get('avg_cost', 0),
                            "market_value": pos.get('market_value', 0),
                            "unrealized_pnl": pos.get('unrealized_pnl', 0),
                            "position_type": "LONG" if pos.get('quantity', 0) > 0 else "SHORT" if pos.get('quantity', 0) < 0 else "FLAT",
                            "book": pos.get('book', 'LT'),
                            "account": mode
                        }
                        for sym, pos in raw_positions.items()
                        if pos.get('quantity', 0) != 0
                    ]
        
        # Save snapshot
        result = save_befday_snapshot(account, positions)
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
