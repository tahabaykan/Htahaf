"""
XNL Engine API Routes

Endpoints for:
- Start/Stop XNL Engine
- Get XNL Engine state
- Cancel orders by filter (incr/decr/sells/buys/lt/mm/tum) + rev_excluded
- ADDNEWPOS settings (get/update)
"""

from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel
from typing import Optional, Dict, Any
from pathlib import Path
from loguru import logger

router = APIRouter(prefix="/api/xnl", tags=["XNL Engine"])


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class XNLStateResponse(BaseModel):
    """XNL Engine state response"""
    state: str
    started_at: Optional[str]
    stopped_at: Optional[str]
    total_orders_sent: int
    total_orders_cancelled: int
    total_front_cycles: int
    total_refresh_cycles: int
    last_error: Optional[str]
    cycle_states: Dict[str, Any]


class XNLActionResponse(BaseModel):
    """Generic action response"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class CancelResponse(BaseModel):
    """Cancel orders response"""
    success: bool
    cancelled: int
    failed: int
    message: str


class AddnewposSettingsRequest(BaseModel):
    """ADDNEWPOS settings update request"""
    account_id: Optional[str] = None  # HAMPRO, IBKR_PED, IBKR_GUN - if None, uses current context
    enabled: Optional[bool] = None
    mode: Optional[str] = None  # both, addlong_only, addshort_only
    long_ratio: Optional[float] = None
    short_ratio: Optional[float] = None
    gort_min: Optional[float] = None
    gort_max: Optional[float] = None
    fbtot_threshold: Optional[float] = None
    fbtot_direction: Optional[str] = None
    sma63chg_threshold: Optional[float] = None
    sma63chg_direction: Optional[str] = None
    active_tab: Optional[str] = None
    jfin_pct: Optional[int] = None
    # Per-Tab Settings (V2)
    tab_bb: Optional[dict] = None
    tab_fb: Optional[dict] = None
    tab_sas: Optional[dict] = None
    tab_sfs: Optional[dict] = None


class MMSettingsRequest(BaseModel):
    """MM settings update request"""
    enabled: Optional[bool] = None
    est_cur_ratio: Optional[float] = None
    min_stock_count: Optional[int] = None
    max_stock_count: Optional[int] = None
    lot_per_stock: Optional[int] = None
    lot_mode: Optional[str] = None  # 'fixed' or 'adv_adjust'


class HeavyModeRequest(BaseModel):
    """HEAVY mode settings update request"""
    heavy_long_dec: Optional[bool] = None
    heavy_short_dec: Optional[bool] = None
    # Configurable HEAVY parameters (persisted to Redis)
    heavy_lot_pct: Optional[int] = None           # 1-100, default 30
    heavy_long_threshold: Optional[float] = None  # min pahalilik, default 0.02
    heavy_short_threshold: Optional[float] = None # max ucuzluk, default -0.02


# ═══════════════════════════════════════════════════════════════════════════════
# HEAVY MODE SETTINGS ENDPOINTS (ACCOUNT-AWARE)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/heavy-settings")
async def get_heavy_settings(account_id: Optional[str] = None):
    """
    Get HEAVY mode settings for all accounts or specific account.
    
    Account-specific: Each account (HAMPRO, IBKR_PED, IBKR_MAIN) has separate HEAVY settings.
    """
    try:
        from app.xnl.heavy_settings_store import get_heavy_settings_store
        
        store = get_heavy_settings_store()
        
        if account_id:
            # Get settings for specific account
            settings = store.get_settings_dict(account_id)
            return {
                "success": True,
                "account_id": account_id,
                "settings": settings
            }
        else:
            # Get settings for all accounts
            all_settings = store.get_all_accounts_settings()
            return {
                "success": True,
                "all_accounts": all_settings
            }
        
    except Exception as e:
        logger.error(f"[XNL_API] Get HEAVY settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heavy-settings/{account_id}")
async def update_heavy_settings(account_id: str, request: HeavyModeRequest):
    """
    Update HEAVY mode settings for a specific account.
    
    Settings are persisted to Redis under key: psfalgo:heavy_settings:{account_id}
    """
    try:
        from app.xnl.heavy_settings_store import get_heavy_settings_store
        
        store = get_heavy_settings_store()
        
        updates = {}
        if request.heavy_long_dec is not None:
            updates['heavy_long_dec'] = request.heavy_long_dec
        if request.heavy_short_dec is not None:
            updates['heavy_short_dec'] = request.heavy_short_dec
        if request.heavy_lot_pct is not None:
            updates['heavy_lot_pct'] = max(1, min(100, int(request.heavy_lot_pct)))
        if request.heavy_long_threshold is not None:
            updates['heavy_long_threshold'] = float(request.heavy_long_threshold)
        if request.heavy_short_threshold is not None:
            updates['heavy_short_threshold'] = float(request.heavy_short_threshold)
        
        if updates:
            settings = store.update_settings(account_id, updates)
            logger.info(f"[XNL_API] Updated HEAVY settings for {account_id}: {updates}")
        else:
            settings = store.get_settings(account_id)
        
        return {
            "success": True,
            "account_id": account_id,
            "settings": store.get_settings_dict(account_id),
            "updated": updates
        }
        
    except Exception as e:
        logger.error(f"[XNL_API] Update HEAVY settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heavy-settings/{account_id}/reset")
async def reset_heavy_settings(account_id: str):
    """Reset HEAVY mode settings for a specific account to defaults."""
    try:
        from app.xnl.heavy_settings_store import get_heavy_settings_store, HeavyModeSettings
        from dataclasses import asdict
        
        store = get_heavy_settings_store()
        defaults = asdict(HeavyModeSettings())
        store.update_settings(account_id, defaults)
        
        return {
            "success": True,
            "account_id": account_id,
            "settings": store.get_settings_dict(account_id),
            "message": f"HEAVY settings for {account_id} reset to defaults"
        }
    except Exception as e:
        logger.error(f"[XNL_API] Reset HEAVY settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoint for backward compatibility (uses current trading context)
@router.get("/controls")
async def get_runtime_controls():
    """Get current runtime controls including HEAVY mode flags (for current account)"""
    try:
        from app.xnl.heavy_settings_store import get_heavy_settings_store
        from app.trading.trading_account_context import get_trading_context
        
        ctx = get_trading_context()
        account_id = ctx.trading_mode.value
        
        store = get_heavy_settings_store()
        settings = store.get_settings_dict(account_id)
        
        return {
            "success": True,
            "account_id": account_id,
            "controls": settings  # Same structure as before for backward compat
        }
        
    except Exception as e:
        logger.error(f"[XNL_API] Get controls error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/controls")
async def update_runtime_controls(request: HeavyModeRequest):
    """Update runtime controls (HEAVY mode flags and parameters) for current account"""
    try:
        from app.xnl.heavy_settings_store import get_heavy_settings_store
        from app.trading.trading_account_context import get_trading_context
        
        ctx = get_trading_context()
        account_id = ctx.trading_mode.value
        
        store = get_heavy_settings_store()
        
        updates = {}
        if request.heavy_long_dec is not None:
            updates['heavy_long_dec'] = request.heavy_long_dec
        if request.heavy_short_dec is not None:
            updates['heavy_short_dec'] = request.heavy_short_dec
        if request.heavy_lot_pct is not None:
            updates['heavy_lot_pct'] = max(1, min(100, int(request.heavy_lot_pct)))
        if request.heavy_long_threshold is not None:
            updates['heavy_long_threshold'] = float(request.heavy_long_threshold)
        if request.heavy_short_threshold is not None:
            updates['heavy_short_threshold'] = float(request.heavy_short_threshold)
        
        if updates:
            store.update_settings(account_id, updates)
            logger.info(f"[XNL_API] Updated controls for {account_id}: {updates}")
        
        return {
            "success": True,
            "account_id": account_id,
            "controls": store.get_settings_dict(account_id),
            "updated": updates
        }
        
    except Exception as e:
        logger.error(f"[XNL_API] Update controls error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# XNL ENGINE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/state", response_model=XNLStateResponse)
async def get_xnl_state():
    """Get current XNL Engine state"""
    try:
        from app.xnl.xnl_engine import get_xnl_engine
        
        engine = get_xnl_engine()
        state = engine.get_state()
        
        return XNLStateResponse(**state)
        
    except Exception as e:
        logger.error(f"[XNL_API] Get state error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start", response_model=XNLActionResponse)
async def start_xnl_engine():
    """Start XNL Engine"""
    try:
        from app.xnl.xnl_engine import get_xnl_engine
        
        engine = get_xnl_engine()
        success = await engine.start()
        
        if success:
            return XNLActionResponse(
                success=True,
                message="XNL Engine started successfully",
                data=engine.get_state()
            )
        else:
            return XNLActionResponse(
                success=False,
                message="XNL Engine already running or failed to start",
                data=engine.get_state()
            )
        
    except Exception as e:
        logger.error(f"[XNL_API] Start error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop", response_model=XNLActionResponse)
async def stop_xnl_engine():
    """Stop XNL Engine"""
    try:
        from app.xnl.xnl_engine import get_xnl_engine
        
        engine = get_xnl_engine()
        success = await engine.stop()
        
        if success:
            return XNLActionResponse(
                success=True,
                message="XNL Engine stopped successfully",
                data=engine.get_state()
            )
        else:
            return XNLActionResponse(
                success=False,
                message="XNL Engine already stopped",
                data=engine.get_state()
            )
        
    except Exception as e:
        logger.error(f"[XNL_API] Stop error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# DUAL PROCESS (alternate XNL between two accounts; longest front cycle = 3.5 min)
# ═══════════════════════════════════════════════════════════════════════════════

class DualProcessStartRequest(BaseModel):
    """Start Dual Process: cycle XNL between two accounts."""
    account_a: str  # e.g. IBKR_PED
    account_b: str  # e.g. HAMPRO


@router.post("/dual-process/start", response_model=XNLActionResponse)
async def start_dual_process(request: DualProcessStartRequest):
    """
    Start Dual Process: alternate XNL between account_a and account_b.
    For each account: Cancel All → Start XNL → Wait longest front cycle (3.5 min) → Stop XNL (orders left as-is).
    """
    try:
        from app.xnl.dual_process_runner import get_dual_process_runner
        
        runner = get_dual_process_runner()
        success, err = await runner.start(request.account_a, request.account_b)
        if success:
            return XNLActionResponse(
                success=True,
                message="Dual Process started",
                data=runner.get_state()
            )
        return XNLActionResponse(
            success=False,
            message=err or "Failed to start Dual Process",
            data=runner.get_state()
        )
    except Exception as e:
        logger.error(f"[XNL_API] Dual Process start error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dual-process/stop", response_model=XNLActionResponse)
async def stop_dual_process():
    """Stop Dual Process; current account step will finish then loop exits."""
    try:
        from app.xnl.dual_process_runner import get_dual_process_runner
        
        runner = get_dual_process_runner()
        await runner.stop()
        return XNLActionResponse(
            success=True,
            message="Dual Process stop requested",
            data=runner.get_state()
        )
    except Exception as e:
        logger.error(f"[XNL_API] Dual Process stop error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dual-process/state")
async def get_dual_process_state():
    """Get Dual Process state (running/stopped, account_a, account_b, current_account, loop_count)."""
    try:
        from app.xnl.dual_process_runner import get_dual_process_runner
        
        runner = get_dual_process_runner()
        return runner.get_state()
    except Exception as e:
        logger.error(f"[XNL_API] Dual Process state error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# CANCEL ENDPOINT (filter + rev_excluded)
# ═══════════════════════════════════════════════════════════════════════════════

class CancelFilterRequest(BaseModel):
    """Cancel by filter request"""
    filter: str  # incr, decr, sells, buys, lt, mm, tum
    rev_excluded: bool = False  # when True, exclude REV-tagged orders from cancellation


@router.post("/cancel/filter", response_model=CancelResponse)
async def cancel_by_filter(request: CancelFilterRequest):
    """Cancel orders by filter (incr, decr, sells, buys, lt, mm, tum). rev_excluded=True excludes REV-tagged orders."""
    try:
        from app.xnl.xnl_engine import get_xnl_engine
        from app.trading.trading_account_context import get_trading_context
        
        ctx = get_trading_context()
        account_id = ctx.trading_mode.value
        filter_type = (request.filter or '').strip().lower()
        if filter_type not in ('incr', 'decr', 'sells', 'buys', 'lt', 'mm', 'tum'):
            raise HTTPException(status_code=400, detail=f"Invalid filter: {request.filter}. Use incr, decr, sells, buys, lt, mm, tum")
        
        engine = get_xnl_engine()
        result = await engine.cancel_by_filter(account_id, filter_type, request.rev_excluded)
        
        return CancelResponse(
            success=result['cancelled'] > 0 or result['failed'] == 0,
            cancelled=result['cancelled'],
            failed=result['failed'],
            message=f"Cancelled {result['cancelled']} orders, {result['failed']} failed"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XNL_API] Cancel filter error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# MINMAX AREA (per-symbol today's min/max qty bounds)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/minmax-area", response_model=XNLActionResponse)
async def compute_and_save_minmax_area(account_id: Optional[str] = None):
    """
    Compute MinMax Area for all PREF symbols: todays_max_qty, todays_min_qty
    per symbol (MAXALW, portfolio %, BEFDAY limits). Writes minmaxarea_<account>.csv.
    
    Query params:
        account_id: Optional - HAMPRO, IBKR_PED, IBKR_GUN. If not provided, uses current context.
    """
    try:
        from app.trading.trading_account_context import get_trading_context
        from app.psfalgo.minmax_area_service import get_minmax_area_service
        from app.psfalgo.position_snapshot_api import PositionSnapshotAPI

        if account_id:
            acc = account_id.strip().upper()
            if acc == "HAMMER_PRO":
                acc = "HAMPRO"
        else:
            ctx = get_trading_context()
            acc = ctx.trading_mode.value

        pos_api = PositionSnapshotAPI()
        snapshots = await pos_api.get_position_snapshot(acc)
        pos_map: Dict[str, float] = {}
        befday_map: Dict[str, float] = {}
        for s in snapshots or []:
            sym = getattr(s, "symbol", None) or (s.get("symbol") if isinstance(s, dict) else None)
            if not sym:
                continue
            qty = getattr(s, "qty", None) or (s.get("qty", s.get("quantity", 0)) if isinstance(s, dict) else 0)
            bef = getattr(s, "befday_qty", None) or (s.get("befday_qty", 0) if isinstance(s, dict) else 0)
            pos_map[sym] = float(qty or 0)
            befday_map[sym] = float(bef or 0)

        svc = get_minmax_area_service()
        count = svc.save_to_csv(
            acc,
            positions_override=pos_map if pos_map else None,
            befday_override=befday_map if befday_map else None,
        )

        return XNLActionResponse(
            success=True,
            message=f"MinMax Area computed: {count} symbols for {acc}",
            data={"row_count": count, "account_id": acc},
        )
    except Exception as e:
        logger.error(f"[XNL_API] MinMax Area error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/minmax-area/all", response_model=XNLActionResponse)
async def compute_minmax_area_all_accounts():
    """
    Compute MinMax Area for ALL configured accounts (HAMPRO + IBKR_PED).
    Useful for dual process — ensures both accounts have fresh MinMax rules.
    """
    try:
        from app.psfalgo.minmax_area_service import get_minmax_area_service
        from app.psfalgo.position_snapshot_api import PositionSnapshotAPI

        accounts = ["HAMPRO", "IBKR_PED"]
        results = {}
        total = 0

        for acc in accounts:
            try:
                pos_api = PositionSnapshotAPI()
                snapshots = await pos_api.get_position_snapshot(acc)
                pos_map: Dict[str, float] = {}
                befday_map: Dict[str, float] = {}
                for s in snapshots or []:
                    sym = getattr(s, "symbol", None) or (s.get("symbol") if isinstance(s, dict) else None)
                    if not sym:
                        continue
                    qty = getattr(s, "qty", None) or (s.get("qty", s.get("quantity", 0)) if isinstance(s, dict) else 0)
                    bef = getattr(s, "befday_qty", None) or (s.get("befday_qty", 0) if isinstance(s, dict) else 0)
                    pos_map[sym] = float(qty or 0)
                    befday_map[sym] = float(bef or 0)

                svc = get_minmax_area_service()
                count = svc.save_to_csv(
                    acc,
                    positions_override=pos_map if pos_map else None,
                    befday_override=befday_map if befday_map else None,
                )
                results[acc] = count
                total += count
                logger.info(f"[XNL_API] MinMax computed for {acc}: {count} symbols")
            except Exception as acc_err:
                results[acc] = f"ERROR: {acc_err}"
                logger.error(f"[XNL_API] MinMax for {acc} failed: {acc_err}")

        return XNLActionResponse(
            success=True,
            message=f"MinMax Area computed for {len(accounts)} accounts: {total} total symbols",
            data={"accounts": results, "total_symbols": total},
        )
    except Exception as e:
        logger.error(f"[XNL_API] MinMax Area all error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/minmax-area")
async def get_minmax_area_preview(account_id: Optional[str] = None):
    """Return current minmax area cache (or load from CSV) for UI preview.
    
    Query params:
        account_id: Optional - HAMPRO, IBKR_PED. If not provided, uses current context.
    """
    try:
        from app.trading.trading_account_context import get_trading_context
        from app.psfalgo.minmax_area_service import get_minmax_area_service

        if account_id:
            acc = account_id.strip().upper()
            if acc == "HAMMER_PRO":
                acc = "HAMPRO"
        else:
            ctx = get_trading_context()
            acc = ctx.trading_mode.value

        svc = get_minmax_area_service()
        rows = svc.get_all_rows(acc)
        if not rows:
            rows = svc.load_from_csv(account_id=acc)
        out = [
            {
                "symbol": r.symbol,
                "current_qty": r.current_qty,
                "befday_qty": r.befday_qty,
                "todays_max_qty": r.todays_max_qty,
                "todays_min_qty": r.todays_min_qty,
            }
            for r in (rows or {}).values()
        ]
        return {"success": True, "account_id": acc, "rows": out}
    except Exception as e:
        logger.error(f"[XNL_API] MinMax Area preview error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# ADDNEWPOS SETTINGS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/addnewpos/settings")
async def get_addnewpos_settings(account_id: Optional[str] = None):
    """Get ADDNEWPOS settings for specified or current account.
    
    Query params:
        account_id: Optional - HAMPRO, IBKR_PED, IBKR_GUN
                    If not provided, uses current trading context.
    """
    try:
        from app.xnl.addnewpos_settings_v2 import get_addnewpos_settings_store
        from app.trading.trading_account_context import get_trading_context
        
        if account_id:
            acc = account_id.upper()
            # Map HAMMER_PRO to HAMPRO for compatibility
            if acc == "HAMMER_PRO":
                acc = "HAMPRO"
        else:
            ctx = get_trading_context()
            acc = ctx.trading_mode.value  # HAMPRO, IBKR_PED, IBKR_GUN
        
        store = get_addnewpos_settings_store()
        settings = store.get_settings(acc)
        
        return {
            "success": True,
            "account_id": acc,
            "settings": settings
        }
        
    except Exception as e:
        logger.error(f"[XNL_API] Get ADDNEWPOS settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/addnewpos/settings")
async def update_addnewpos_settings(request: AddnewposSettingsRequest):
    """Update ADDNEWPOS settings for specified or current account.
    
    Body args:
        account_id: Optional - HAMPRO, IBKR_PED, IBKR_GUN
                    If not provided, uses current trading context.
    """
    try:
        from app.xnl.addnewpos_settings_v2 import get_addnewpos_settings_store
        from app.trading.trading_account_context import get_trading_context
        
        # Use account_id from request if provided, else from context
        if request.account_id:
            acc = request.account_id.upper()
            if acc == "HAMMER_PRO":
                acc = "HAMPRO"
        else:
            ctx = get_trading_context()
            acc = ctx.trading_mode.value  # HAMPRO, IBKR_PED, IBKR_GUN
        
        store = get_addnewpos_settings_store()
        
        # Build updates dict (only non-None values, exclude account_id itself)
        updates = {k: v for k, v in request.dict().items() if v is not None and k != 'account_id'}
        
        if updates:
            success = store.update_settings(acc, updates)
        else:
            success = True  # No updates to apply
        
        return {
            "success": success,
            "message": f"Settings updated for {acc}" if success else "Failed to update settings",
            "account_id": acc,
            "settings": store.get_settings(acc)
        }
        
    except Exception as e:
        logger.error(f"[XNL_API] Update ADDNEWPOS settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/addnewpos/settings/reset")
async def reset_addnewpos_settings(account_id: Optional[str] = None):
    """Reset ADDNEWPOS settings to defaults for specified or current account."""
    try:
        from app.xnl.addnewpos_settings_v2 import (
            get_addnewpos_settings_store,
            AddnewposSettings,
            tab_settings_to_dict,
        )
        from app.trading.trading_account_context import get_trading_context
        from dataclasses import fields as dc_fields

        if account_id:
            acc = account_id.upper()
            if acc == "HAMMER_PRO":
                acc = "HAMPRO"
        else:
            ctx = get_trading_context()
            acc = ctx.trading_mode.value

        store = get_addnewpos_settings_store()
        
        # Create default settings
        defaults = AddnewposSettings()
        updates = {
            "enabled": defaults.enabled,
            "mode": defaults.mode,
            "long_ratio": defaults.long_ratio,
            "short_ratio": defaults.short_ratio,
            "active_tab": defaults.active_tab,
            "tab_bb": tab_settings_to_dict(defaults.tab_bb),
            "tab_fb": tab_settings_to_dict(defaults.tab_fb),
            "tab_sas": tab_settings_to_dict(defaults.tab_sas),
            "tab_sfs": tab_settings_to_dict(defaults.tab_sfs),
        }
        
        store.update_settings(acc, updates)
        logger.info(f"[XNL_API] ADDNEWPOS settings reset to defaults for {acc}")

        return {
            "success": True,
            "account_id": acc,
            "settings": store.get_settings(acc),
            "message": f"ADDNEWPOS settings for {acc} reset to defaults"
        }
    except Exception as e:
        logger.error(f"[XNL_API] Reset ADDNEWPOS settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class AddnewposSaveCsvRequest(BaseModel):
    """Request body for save to CSV (user-provided filename)"""
    filename: str  # e.g. "my_addnewpos" -> saved as my_addnewpos.csv


@router.post("/addnewpos/settings/save-csv")
async def addnewpos_save_csv(request: AddnewposSaveCsvRequest):
    """Save current ADDNEWPOS settings to a named CSV and set as last-used."""
    try:
        from app.xnl.addnewpos_settings import get_addnewpos_settings_store, _config_dir
        name = (request.filename or "addnewpos").strip().replace("..", "").replace("/", "").replace("\\", "")
        if not name:
            raise HTTPException(status_code=400, detail="filename required")
        if not name.endswith(".csv"):
            name = name + ".csv"
        csv_dir = _config_dir() / "addnewpos_csvs"
        csv_dir.mkdir(parents=True, exist_ok=True)
        path = str(csv_dir / name)
        store = get_addnewpos_settings_store()
        if not store.save_to_csv(path):
            raise HTTPException(status_code=500, detail="Failed to save CSV")
        return {"success": True, "path": path, "filename": name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XNL_API] ADDNEWPOS save-csv error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/addnewpos/settings/load-csv")
async def addnewpos_load_csv(upload_file: Optional[UploadFile] = File(None)):
    """Load ADDNEWPOS settings from uploaded CSV; sets as last-used."""
    try:
        from app.xnl.addnewpos_settings import get_addnewpos_settings_store
        import tempfile
        if not upload_file or not upload_file.filename:
            raise HTTPException(status_code=400, detail="CSV file required")
        safe_name = Path(upload_file.filename).name
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(await upload_file.read())
            tmp_path = tmp.name
        try:
            store = get_addnewpos_settings_store()
            ok = store.load_from_csv(tmp_path)
            if not ok:
                raise HTTPException(status_code=400, detail="Failed to load CSV")
            return {"success": True, "settings": store.get_settings(), "filename": safe_name}
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XNL_API] ADDNEWPOS load-csv error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addnewpos/settings/last-csv")
async def addnewpos_last_csv():
    """Return last-used CSV path; used on startup to show/load default."""
    try:
        from app.xnl.addnewpos_settings import get_last_addnewpos_csv_path_resolved
        path = get_last_addnewpos_csv_path_resolved()
        if not path:
            return {"success": True, "path": None, "filename": None}
        return {"success": True, "path": path, "filename": Path(path).name}
    except Exception as e:
        logger.error(f"[XNL_API] ADDNEWPOS last-csv error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/addnewpos/settings/load-last-csv")
async def addnewpos_load_last_csv():
    """Load ADDNEWPOS settings from last-used CSV (server-side path)."""
    try:
        from app.xnl.addnewpos_settings import get_addnewpos_settings_store, get_last_addnewpos_csv_path_resolved
        path = get_last_addnewpos_csv_path_resolved()
        if not path:
            raise HTTPException(status_code=404, detail="No last CSV or file missing")
        store = get_addnewpos_settings_store()
        if not store.load_from_csv(path):
            raise HTTPException(status_code=500, detail="Failed to load from last CSV")
        return {"success": True, "settings": store.get_settings(), "filename": Path(path).name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[XNL_API] ADDNEWPOS load-last-csv error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# MM SETTINGS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/mm/settings")
async def get_mm_settings():
    """Get MM settings"""
    try:
        from app.xnl.mm_settings import get_mm_settings_store
        
        store = get_mm_settings_store()
        settings = store.get_settings()
        
        return {
            "success": True,
            "settings": settings
        }
        
    except Exception as e:
        logger.error(f"[XNL_API] Get MM settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mm/settings")
async def update_mm_settings(request: MMSettingsRequest):
    """Update MM settings"""
    try:
        from app.xnl.mm_settings import get_mm_settings_store
        
        store = get_mm_settings_store()
        
        # Build updates dict (only non-None values)
        updates = {k: v for k, v in request.dict().items() if v is not None}
        
        if updates:
            success = store.update_settings(updates)
        else:
            success = True  # No updates to apply
        
        return {
            "success": success,
            "message": "MM settings updated" if success else "Failed to update MM settings",
            "settings": store.get_settings()
        }
        
    except Exception as e:
        logger.error(f"[XNL_API] Update MM settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mm/settings/reset")
async def reset_mm_settings():
    """Reset MM settings to defaults (lot_mode=fixed, lot_per_stock=200, etc.)."""
    try:
        from app.xnl.mm_settings import get_mm_settings_store, MMSettings
        from dataclasses import asdict
        
        store = get_mm_settings_store()
        defaults = asdict(MMSettings())
        store.update_settings(defaults)
        
        return {
            "success": True,
            "settings": store.get_settings(),
            "message": "MM settings reset to defaults"
        }
    except Exception as e:
        logger.error(f"[XNL_API] Reset MM settings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# FREE EXPOSURE STATUS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/free-exposure")
async def get_free_exposure_status():
    """Get free exposure status for current account (or all accounts).
    
    Returns free current/potential exposure %, tier label, blocked state.
    Used by UI to show free capacity alongside existing exposure data.
    """
    try:
        from app.psfalgo.free_exposure_engine import get_free_exposure_engine
        from app.trading.trading_account_context import get_trading_context
        
        engine = get_free_exposure_engine()
        
        ctx = get_trading_context()
        account_id = ctx.trading_mode.value
        
        # Calculate fresh free exposure
        snapshot = await engine.calculate_free_exposure(account_id)
        
        return {
            "success": True,
            "account_id": account_id,
            "free_exposure": snapshot
        }
        
    except Exception as e:
        logger.error(f"[XNL_API] Free exposure error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

