"""
Exposure Calculator - Production-Grade

Calculates ExposureSnapshot from position snapshots.
Used by RUNALL to determine exposure mode (OFANSIF/DEFANSIF).
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from app.core.logger import logger
from app.psfalgo.decision_models import ExposureSnapshot, PositionSnapshot

# ═══ Cancel Grace Period (Fix 2) ═══
# After a global cancel, IBKR/Hammer takes time to confirm cancels.
# During this period, open orders from broker are stale (about to be cancelled)
# and should NOT be included in potential exposure calculation.
import time as _time
_last_global_cancel_ts: float = 0.0
_CANCEL_GRACE_PERIOD_SEC: float = 15.0  # Ignore pending orders for 15s after cancel

def notify_global_cancel_issued():
    """Called after reqGlobalCancel or batch cancel. Starts grace period."""
    global _last_global_cancel_ts
    _last_global_cancel_ts = _time.time()
    logger.info(f"[EXPOSURE] Cancel grace period started ({_CANCEL_GRACE_PERIOD_SEC}s)")

def _is_cancel_grace_period_active() -> bool:
    """Check if we're within the cancel grace period."""
    if _last_global_cancel_ts == 0:
        return False
    elapsed = _time.time() - _last_global_cancel_ts
    return elapsed < _CANCEL_GRACE_PERIOD_SEC


class ExposureCalculator:
    """
    Exposure Calculator - calculates exposure from position snapshots.
    
    Responsibilities:
    - Calculate pot_total (total exposure)
    - Calculate long_lots / short_lots
    - Calculate net_exposure
    - Determine exposure_mode (OFANSIF/DEFANSIF)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Exposure Calculator.
        
        Args:
            config: Configuration dict with:
                - pot_max_lot: Maximum exposure limit (default: 63636)
                - avg_price: Average price for lot calculation (default: 100)
        """
        self.config = config or {}
        self.pot_max_lot = self.config.get('pot_max_lot', 63636)
        self.avg_price = self.config.get('avg_price', 100.0)  # Default $100 for lot calculation
    
    def calculate_exposure(
        self,
        positions: List[PositionSnapshot],
        pot_max: Optional[float] = None,
        avg_price: Optional[float] = None
    ) -> ExposureSnapshot:
        """
        Calculate exposure snapshot from position snapshots.
        
        Args:
            positions: List of PositionSnapshot objects
            pot_max: Override pot_max from config (optional)
            avg_price: Account-specific avg_price for lot conversion (optional).
                       Stored in snapshot to prevent singleton mutation.
            
        Returns:
            ExposureSnapshot object
        """
        if pot_max is None:
            pot_max = self.pot_max_lot
        
        # Use provided avg_price or fall back to instance default
        effective_avg_price = avg_price if (avg_price and avg_price > 0) else self.avg_price
        
        pot_total = 0.0
        long_lots = 0.0
        short_lots = 0.0
        # NEW: Track dollar values
        long_value = 0.0
        short_value = 0.0
        
        for pos in positions:
            # Safety check: Ensure pos is PositionSnapshot object, not string
            if not isinstance(pos, PositionSnapshot):
                logger.warning(f"[EXPOSURE] Skipping invalid position type: {type(pos)}")
                continue
                
            # Use current price if available, fallback to avg_price (Janall/Positions Screen Logic)
            price_to_use = pos.current_price if (pos.current_price and pos.current_price > 0) else pos.avg_price
            
            # DEBUG LOG (was INFO; downgraded to reduce log volume and I/O - 100+ symbols per request)
            accepted_flag = "OK"
            if not price_to_use or price_to_use <= 0:
                accepted_flag = "REJECTED_NO_PRICE"
            elif pos.qty == 0:
                accepted_flag = "REJECTED_ZERO_QTY"
            logger.debug(
                f"[EXPOSURE_DEBUG] sym={pos.symbol} qty={pos.qty} price={pos.current_price} "
                f"fallback_price={pos.avg_price} value={abs(pos.qty) * (price_to_use or 0)} accepted={accepted_flag}"
            )

            # Calculate position value (absolute) using best available price
            position_value = abs(pos.qty) * (price_to_use or 0.0)
            pot_total += position_value
            
            # Accumulate lots AND dollar values
            if pos.qty > 0:
                long_lots += pos.qty
                long_value += position_value  # LONG dollar value
            elif pos.qty < 0:
                short_lots += abs(pos.qty)
                short_value += position_value  # SHORT dollar value
        
        # Calculate net exposure (in shares/lots)
        net_exposure = long_lots - short_lots
        
        # Determine mode using Janall logic (lot-based thresholds)
        # Will be recalculated properly in determine_exposure_mode()
        # For now, use simple fallback
        mode = 'OFANSIF' if pot_total < pot_max else 'DEFANSIF'
        
        exposure = ExposureSnapshot(
            pot_total=pot_total,
            pot_max=pot_max,
            long_lots=long_lots,
            short_lots=short_lots,
            net_exposure=net_exposure,
            long_value=long_value,  # NEW
            short_value=short_value,  # NEW
            avg_price=effective_avg_price,  # Per-account, prevents singleton leak
            mode=mode,  # Will be recalculated by determine_exposure_mode()
            timestamp=datetime.now()
        )
        
        # Recalculate mode using proper Janall logic
        exposure.mode = self.determine_exposure_mode(exposure)
        
        logger.debug(
            f"Exposure calculated: "
            f"Pot Total={pot_total:,.0f}, "
            f"Pot Max={pot_max:,.0f}, "
            f"Long={long_lots:,.0f}, "
            f"Short={short_lots:,.0f}, "
            f"Net={net_exposure:,.0f}, "
            f"Mode={exposure.mode}"
        )
        
        return exposure
    
    def determine_exposure_mode(self, exposure: ExposureSnapshot, config: Optional[Dict[str, Any]] = None) -> str:
        """
        Determine exposure mode from exposure snapshot (Janall-compatible).
        
        Janall Logic:
        - defensive_threshold = max_lot * 0.955 (%95.5)
        - offensive_threshold = max_lot * 0.927 (%92.7)
        - total_lots > defensive_threshold → DEFANSIF (only REDUCEMORE)
        - total_lots < offensive_threshold → OFANSIF (KARBOTU + ADDNEWPOS)
        - between → GECIS (REDUCEMORE)
        
        Args:
            exposure: ExposureSnapshot object
            config: Optional config with thresholds (defaults from rules)
            
        Returns:
            'OFANSIF', 'DEFANSIF', or 'GECIS'
        """
        if config is None:
            # Load defaults from rules
            from app.psfalgo.rules_store import get_rules_store
            rules_store = get_rules_store()
            if rules_store:
                exposure_rules = rules_store.get_rules().get('exposure', {})
                defensive_threshold_percent = exposure_rules.get('defensive_threshold_percent', 95.5)
                offensive_threshold_percent = exposure_rules.get('offensive_threshold_percent', 92.7)
            else:
                defensive_threshold_percent = 95.5
                offensive_threshold_percent = 92.7
        else:
            defensive_threshold_percent = config.get('defensive_threshold_percent', 95.5)
            offensive_threshold_percent = config.get('offensive_threshold_percent', 92.7)
        
        # Calculate max_lot from pot_max
        # Janall uses lot-based thresholds, not dollar-based
        # We'll use total_lots (long_lots + short_lots) as total_lots
        total_lots = exposure.long_lots + exposure.short_lots
        
        # Calculate thresholds (as percentages of pot_max in lots)
        # pot_max is in dollars, convert to lots using avg_price
        # CRITICAL: Use snapshot's avg_price (per-account) instead of self.avg_price
        # to prevent cross-account contamination through singleton mutation
        avg_price = getattr(exposure, 'avg_price', None) or self.avg_price
        max_lot = exposure.pot_max / avg_price if avg_price > 0 else 63636
        
        defensive_threshold = max_lot * (defensive_threshold_percent / 100.0)
        offensive_threshold = max_lot * (offensive_threshold_percent / 100.0)
        
        # Janall logic
        if total_lots > defensive_threshold:
            return 'DEFANSIF'  # Only REDUCEMORE
        elif total_lots < offensive_threshold:
            return 'OFANSIF'  # KARBOTU + ADDNEWPOS
        else:
            return 'GECIS'  # Transition mode - REDUCEMORE


# Global instance
_exposure_calculator: Optional[ExposureCalculator] = None


def get_exposure_calculator() -> Optional[ExposureCalculator]:
    """Get global ExposureCalculator instance"""
    return _exposure_calculator


def initialize_exposure_calculator(config: Optional[Dict[str, Any]] = None):
    """Initialize global ExposureCalculator instance"""
    global _exposure_calculator
    _exposure_calculator = ExposureCalculator(config=config)
    logger.info("ExposureCalculator initialized")


# Async wrapper for account_id-based exposure calculation
async def calculate_exposure_for_account(account_id: str) -> Optional[ExposureSnapshot]:
    """
    Async wrapper to calculate exposure for an account.
    Fetches positions and calculates exposure.
    
    Uses Port Adjuster V2 for account-specific total_exposure_usd (pot_max).
    
    IMPORTANT: Publishes result to Redis psfalgo:exposure:{account_id}
    so ALL consumers (Frontlama, MetricsCollector, Agent, GreatestMM) 
    can read the latest exposure snapshot.
    
    Args:
        account_id: Account ID (HAMPRO, IBKR_PED, etc.)
        
    Returns:
        ExposureSnapshot or None if error
    """
    try:
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        
        calculator = get_exposure_calculator()
        if not calculator:
            logger.error("[EXPOSURE] ExposureCalculator not initialized")
            return None
        
        pos_api = get_position_snapshot_api()
        if not pos_api:
            logger.error("[EXPOSURE] PositionSnapshotAPI not available")
            return None
        
        # Get account-specific pot_max from Port Adjuster V2
        pot_max = None
        try:
            from app.port_adjuster.port_adjuster_store_v2 import get_port_adjuster_store_v2
            pa_store = get_port_adjuster_store_v2()
            pa_config = pa_store.get_config(account_id)
            if pa_config and pa_config.total_exposure_usd > 0:
                pot_max = pa_config.total_exposure_usd
                logger.debug(f"[EXPOSURE] Using Port Adjuster V2 pot_max for {account_id}: ${pot_max:,.0f}")
        except Exception as e:
            logger.debug(f"[EXPOSURE] Could not get Port Adjuster V2 config: {e}")
            # Fallback to V1
            try:
                from app.port_adjuster.port_adjuster_store import get_port_adjuster_store
                pa_store = get_port_adjuster_store()
                pa_config = pa_store.get_config()
                if pa_config and pa_config.total_exposure_usd > 0:
                    pot_max = pa_config.total_exposure_usd
            except Exception:
                pass
        
        # Get positions for account
        positions = await pos_api.get_position_snapshot(account_id=account_id)
        
        # Filter out any non-PositionSnapshot objects
        from app.psfalgo.decision_models import PositionSnapshot
        valid_positions = [
            pos for pos in positions 
            if isinstance(pos, PositionSnapshot)
        ]
        
        if not valid_positions:
            logger.warning(f"[EXPOSURE] No valid positions for {account_id}")
            return None
        
        # Calculate exposure with account-specific pot_max AND avg_price
        # CRITICAL FIX: Pass avg_price as parameter instead of mutating singleton
        # This prevents cross-account contamination when multiple accounts are processed
        account_avg_price = None
        if pa_config and pa_config.avg_pref_price > 0:
            account_avg_price = pa_config.avg_pref_price
            logger.debug(f"[EXPOSURE] Using avg_price=${pa_config.avg_pref_price:.0f} from Port Adjuster V2 for {account_id}")
        
        exposure = calculator.calculate_exposure(valid_positions, pot_max=pot_max, avg_price=account_avg_price)
        
        # ═══════════════════════════════════════════════════════════════
        # PUBLISH TO REDIS — so all consumers can read from one place
        # Key: psfalgo:exposure:{account_id}
        # TTL: 300s (5 min) — refreshed every XNL cycle (~60s)
        # ═══════════════════════════════════════════════════════════════
        if exposure:
            try:
                import json
                import time
                from app.core.redis_client import get_redis_client
                
                redis_client = get_redis_client()
                if redis_client:
                    redis_sync = getattr(redis_client, 'sync', redis_client)
                    exposure_payload = {
                        "pot_total": round(exposure.pot_total, 2),
                        "pot_max": round(exposure.pot_max, 2),
                        "exposure_pct": round(exposure.pot_total / exposure.pot_max * 100, 2) if exposure.pot_max > 0 else 0,
                        "long_lots": round(exposure.long_lots, 0),
                        "short_lots": round(exposure.short_lots, 0),
                        "net_exposure": round(exposure.net_exposure, 0),
                        "long_value": round(getattr(exposure, 'long_value', 0), 2),
                        "short_value": round(getattr(exposure, 'short_value', 0), 2),
                        "mode": exposure.mode,
                        "account_id": account_id,
                        "updated_at": time.time(),
                        "position_count": len(valid_positions),
                    }
                    key = f"psfalgo:exposure:{account_id}"
                    redis_sync.setex(key, 300, json.dumps(exposure_payload))
                    logger.debug(
                        f"[EXPOSURE] Published to Redis: {key} → "
                        f"${exposure.pot_total:,.0f}/${exposure.pot_max:,.0f} "
                        f"({exposure_payload['exposure_pct']:.1f}%) mode={exposure.mode}"
                    )
            except Exception as e:
                logger.debug(f"[EXPOSURE] Redis publish failed (non-critical): {e}")
        
        return exposure
        
    except Exception as e:
        logger.error(f"[EXPOSURE] Error calculating exposure for {account_id}: {e}", exc_info=True)
        return None


async def get_current_and_potential_exposure_pct(account_id: str) -> tuple:
    """
    For an account: (current_exposure_snapshot, current_pct, potential_pct).
    Potential = if all open orders fill, exposure %. Used for hard risk (max pot exp).
    """
    from types import SimpleNamespace

    exposure = await calculate_exposure_for_account(account_id)
    if not exposure or exposure.pot_max <= 0:
        return (exposure, 0.0, 0.0)

    current_pct = (exposure.pot_total / exposure.pot_max * 100.0)

    try:
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2
        from app.psfalgo.decision_models import PositionSnapshot
        from app.core.data_fabric import get_data_fabric
        import asyncio

        pos_api = get_position_snapshot_api()
        if not pos_api:
            return (exposure, current_pct, current_pct)

        positions = await pos_api.get_position_snapshot(account_id=account_id)
        valid_positions = [p for p in positions if isinstance(p, PositionSnapshot)]
        if not valid_positions:
            return (exposure, current_pct, current_pct)
        
        # ═══ FIX 4: Deduplicate positions by symbol ═══
        # IBKR API sometimes returns duplicate position snapshots,
        # causing cur to spike to impossible values (e.g., $2.9M when max is $1.4M).
        seen_symbols = {}
        deduped_positions = []
        for p in valid_positions:
            if p.symbol not in seen_symbols:
                seen_symbols[p.symbol] = p
                deduped_positions.append(p)
            else:
                logger.warning(f"[EXPOSURE] Duplicate position for {p.symbol} dropped (qty={p.qty})")
        valid_positions = deduped_positions

        # Open orders for account (broker) - run in executor to avoid deadlock
        def _fetch_open_orders():
            try:
                from app.psfalgo.ibkr_connector import get_open_orders_isolated_sync
                if "HAMPRO" in (account_id or "").upper():
                    from app.trading.hammer_orders_service import get_hammer_orders_service
                    svc = get_hammer_orders_service()
                    if svc:
                        raw = svc.get_open_orders()
                        return [{"symbol": o.get("symbol"), "action": o.get("side") or o.get("action"), "quantity": o.get("qty") or o.get("quantity"), "tag": o.get("tag")} for o in (raw or [])] if raw else []
                return get_open_orders_isolated_sync(account_id)
            except Exception:
                return []

        loop = asyncio.get_running_loop()
        raw_orders = await loop.run_in_executor(None, _fetch_open_orders)

        pending = []
        symbols = set()
        for o in raw_orders or []:
            sym = (o.get("symbol") or "").strip()
            if not sym:
                continue
            symbols.add(sym)
            side = (o.get("action") or o.get("side") or "").upper()
            if side in ("SELL", "SHORT"):
                side = "SELL"
            elif side in ("BUY", "COVER"):
                side = "BUY"
            qty = int(o.get("quantity") or o.get("qty") or 0)
            tag = (o.get("tag") or o.get("strategy_tag") or "")
            pending.append(SimpleNamespace(symbol=sym, side=side, qty=qty, strategy_tag=tag))

        # ═══ FIX 2: Cancel Grace Period ═══
        # If a global cancel was just issued, pending orders are stale
        # (broker is processing cancels). Treat potential = current.
        if _is_cancel_grace_period_active():
            logger.info(f"[EXPOSURE] Cancel grace period active — skipping {len(pending)} stale pending orders")
            pending = []

        l1_data = {}
        fabric = get_data_fabric()
        if fabric:
            for sym in symbols:
                snap = fabric.get_fast_snapshot(sym)
                if snap:
                    l1_data[sym] = {"last": snap.get("last") or 0, "bid": snap.get("bid") or 0, "ask": snap.get("ask") or 0}

        # V2: Account-aware threshold service
        thresh_svc = get_exposure_threshold_service_v2()
        potential_pct, _ = thresh_svc.calculate_potential_exposure(
            exposure, valid_positions, pending, l1_data
        )
        return (exposure, current_pct, potential_pct)
    except Exception as e:
        logger.debug(f"[EXPOSURE] Potential exposure calc: {e}")
        return (exposure, current_pct, current_pct)

