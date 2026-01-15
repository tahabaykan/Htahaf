"""
Intent Risk Checks
Risk and guardrail checks for intent creation.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from app.core.logger import logger
from app.psfalgo.intent_models import Intent, RiskCheckResult, IntentStatus, IntentAction
from app.psfalgo.intent_store import get_intent_store


def extract_company_symbol(ticker: str) -> str:
    """
    Extract company symbol from ticker.
    Example: 'INN PRE' -> 'INN', 'PEB PRF' -> 'PEB', 'JAGX' -> 'JAGX'
    """
    if not ticker:
        return ""
    
    if ' ' in ticker:
        return ticker.split(' ')[0]
    
    return ticker


def check_maxalw_company_limit(
    symbol: str,
    action: IntentAction,
    candidate_list: List[str]
) -> RiskCheckResult:
    """
    Check MAXALW (company-based order limit).
    
    Formula: min(3, max(1, round(total_stocks_for_company / 3)))
    
    Args:
        symbol: Symbol to check
        action: Intent action
        candidate_list: List of candidate symbols in current cycle
        
    Returns:
        RiskCheckResult
    """
    try:
        company = extract_company_symbol(symbol)
        
        # Count how many stocks from same company in candidate list
        company_stocks_count = sum(
            1 for candidate in candidate_list
            if extract_company_symbol(candidate) == company
        )
        
        if company_stocks_count == 0:
            return RiskCheckResult(
                passed=True,
                reason="Company not in candidate list",
                details={'company': company, 'stocks_count': 0}
            )
        
        # Calculate max orders for this company
        calculated_max = round(company_stocks_count / 3)
        final_max = max(1, min(3, calculated_max))
        
        # Check if we already have pending/approved intents for this company
        intent_store = get_intent_store()
        company_intents = [
            intent for intent in intent_store.get_intents(status=IntentStatus.PENDING, limit=1000)
            if extract_company_symbol(intent.symbol) == company
        ]
        company_intents.extend([
            intent for intent in intent_store.get_intents(status=IntentStatus.APPROVED, limit=1000)
            if extract_company_symbol(intent.symbol) == company
        ])
        
        active_company_intents = len(company_intents)
        
        if active_company_intents >= final_max:
            return RiskCheckResult(
                passed=False,
                reason=f"Company limit exceeded: {active_company_intents}/{final_max} active intents for {company}",
                details={
                    'company': company,
                    'stocks_count': company_stocks_count,
                    'max_allowed': final_max,
                    'active_intents': active_company_intents
                }
            )
        
        return RiskCheckResult(
            passed=True,
            reason=f"Company limit OK: {active_company_intents}/{final_max} for {company}",
            details={
                'company': company,
                'stocks_count': company_stocks_count,
                'max_allowed': final_max,
                'active_intents': active_company_intents
            }
        )
        
    except Exception as e:
        logger.error(f"[RISK_CHECK] Error in MAXALW check: {e}", exc_info=True)
        return RiskCheckResult(
            passed=True,  # Fail open (allow if check fails)
            reason=f"MAXALW check error: {e}",
            details={'error': str(e)}
        )


def check_daily_lot_limit(
    symbol: str,
    action: IntentAction,
    qty: int,
    daily_limits: Dict[str, Dict[str, int]]  # {symbol: {'BUY': total, 'SELL': total, 'date': date}}
) -> RiskCheckResult:
    """
    Check daily lot limit (±600 per symbol).
    
    Args:
        symbol: Symbol to check
        action: Intent action
        qty: Quantity (lots)
        daily_limits: Daily order totals tracking
        
    Returns:
        RiskCheckResult
    """
    try:
        today = datetime.now().date()
        
        # Get current daily totals for this symbol
        symbol_limits = daily_limits.get(symbol, {})
        symbol_date = symbol_limits.get('date')
        
        # Reset if different day
        if symbol_date != today:
            symbol_limits = {'BUY': 0, 'SELL': 0, 'date': today}
            daily_limits[symbol] = symbol_limits
        
        # Determine side
        side = 'BUY' if action in [IntentAction.BUY, IntentAction.BUY_TO_COVER] else 'SELL'
        
        current_total = symbol_limits.get(side, 0)
        new_total = current_total + qty
        
        # Check limit (±600)
        if abs(new_total) > 600:
            return RiskCheckResult(
                passed=False,
                reason=f"Daily lot limit exceeded: {new_total} > 600 for {symbol} ({side})",
                details={
                    'symbol': symbol,
                    'side': side,
                    'current_total': current_total,
                    'new_total': new_total,
                    'limit': 600
                }
            )
        
        return RiskCheckResult(
            passed=True,
            reason=f"Daily lot limit OK: {new_total}/600 for {symbol} ({side})",
            details={
                'symbol': symbol,
                'side': side,
                'current_total': current_total,
                'new_total': new_total,
                'limit': 600
            }
        )
        
    except Exception as e:
        logger.error(f"[RISK_CHECK] Error in daily lot limit check: {e}", exc_info=True)
        return RiskCheckResult(
            passed=True,  # Fail open
            reason=f"Daily lot limit check error: {e}",
            details={'error': str(e)}
        )


def check_exposure_limit(
    symbol: str,
    action: IntentAction,
    qty: int,
    price: float,
    current_exposure: Optional[Dict[str, Any]]
) -> RiskCheckResult:
    """
    Check exposure limit.
    
    Args:
        symbol: Symbol to check
        action: Intent action
        qty: Quantity
        price: Price
        current_exposure: Current exposure snapshot
        
    Returns:
        RiskCheckResult
    """
    try:
        if not current_exposure:
            return RiskCheckResult(
                passed=True,
                reason="Exposure data not available",
                details={}
            )
        
        pot_total = current_exposure.get('pot_total', 0)
        pot_max = current_exposure.get('pot_max', 0)
        
        # Calculate new exposure
        new_exposure = qty * price
        if action in [IntentAction.BUY, IntentAction.BUY_TO_COVER]:
            new_pot_total = pot_total + new_exposure
        else:
            new_pot_total = pot_total - new_exposure
        
        if new_pot_total > pot_max:
            return RiskCheckResult(
                passed=False,
                reason=f"Exposure limit exceeded: {new_pot_total:,.0f} > {pot_max:,.0f}",
                details={
                    'current_exposure': pot_total,
                    'new_exposure': new_pot_total,
                    'max_exposure': pot_max,
                    'symbol': symbol
                }
            )
        
        return RiskCheckResult(
            passed=True,
            reason=f"Exposure limit OK: {new_pot_total:,.0f}/{pot_max:,.0f}",
            details={
                'current_exposure': pot_total,
                'new_exposure': new_pot_total,
                'max_exposure': pot_max,
                'symbol': symbol
            }
        )
        
    except Exception as e:
        logger.error(f"[RISK_CHECK] Error in exposure limit check: {e}", exc_info=True)
        return RiskCheckResult(
            passed=True,  # Fail open
            reason=f"Exposure limit check error: {e}",
            details={'error': str(e)}
        )


def check_duplicate_intent(
    symbol: str,
    action: IntentAction,
    ttl_seconds: int = 90
) -> RiskCheckResult:
    """
    Check for duplicate intent.
    
    Duplicate if:
    - Same symbol
    - Same action
    - Status is PENDING or APPROVED
    - Within TTL window (90 seconds)
    
    Args:
        symbol: Symbol to check
        action: Intent action
        ttl_seconds: TTL window in seconds
        
    Returns:
        RiskCheckResult
    """
    try:
        intent_store = get_intent_store()
        
        # Get recent intents for this symbol
        cutoff_time = datetime.now() - timedelta(seconds=ttl_seconds)
        
        pending_intents = intent_store.get_intents(status=IntentStatus.PENDING, symbol=symbol, limit=1000)
        approved_intents = intent_store.get_intents(status=IntentStatus.APPROVED, symbol=symbol, limit=1000)
        
        # Check for duplicates within TTL window
        for intent in pending_intents + approved_intents:
            if intent.symbol == symbol and intent.action == action:
                # Check if within TTL window
                if intent.timestamp >= cutoff_time:
                    return RiskCheckResult(
                        passed=False,
                        reason=f"Duplicate intent found: {intent.id} (created {intent.timestamp})",
                        details={
                            'duplicate_intent_id': intent.id,
                            'duplicate_timestamp': intent.timestamp.isoformat(),
                            'ttl_seconds': ttl_seconds
                        }
                    )
        
        return RiskCheckResult(
            passed=True,
            reason="No duplicate intent found",
            details={'ttl_seconds': ttl_seconds}
        )
        
    except Exception as e:
        logger.error(f"[RISK_CHECK] Error in duplicate check: {e}", exc_info=True)
        return RiskCheckResult(
            passed=True,  # Fail open
            reason=f"Duplicate check error: {e}",
            details={'error': str(e)}
        )


def run_all_risk_checks(
    intent: Intent,
    candidate_list: Optional[List[str]] = None,
    daily_limits: Optional[Dict[str, Dict[str, int]]] = None,
    current_exposure: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = 90
) -> List[RiskCheckResult]:
    """
    Run all risk checks for an intent.
    
    Args:
        intent: Intent to check
        candidate_list: List of candidate symbols (for MAXALW)
        daily_limits: Daily lot limits tracking
        current_exposure: Current exposure snapshot
        ttl_seconds: TTL for duplicate check
        
    Returns:
        List of RiskCheckResult
    """
    risk_checks = []
    
    # 1. MAXALW (company limit)
    if candidate_list:
        maxalw_result = check_maxalw_company_limit(
            intent.symbol,
            intent.action,
            candidate_list
        )
        risk_checks.append(maxalw_result)
    
    # 2. Daily lot limit
    if daily_limits is not None:
        daily_limit_result = check_daily_lot_limit(
            intent.symbol,
            intent.action,
            intent.qty,
            daily_limits
        )
        risk_checks.append(daily_limit_result)
    
    # 3. Exposure limit
    if current_exposure:
        exposure_result = check_exposure_limit(
            intent.symbol,
            intent.action,
            intent.qty,
            intent.price or 0.0,
            current_exposure
        )
        risk_checks.append(exposure_result)
    
    # 4. Duplicate intent check
    duplicate_result = check_duplicate_intent(
        intent.symbol,
        intent.action,
        ttl_seconds
    )
    risk_checks.append(duplicate_result)
    
    return risk_checks





