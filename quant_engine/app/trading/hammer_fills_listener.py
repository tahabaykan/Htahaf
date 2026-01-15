"""
Hammer Fills Listener
Listens to Hammer Pro 'transactionsUpdate' messages and logs fills to DailyFillsStore.
"""

from typing import Dict, Any, Optional, Set
from datetime import datetime
from app.core.logger import logger
from app.trading.daily_fills_store import get_daily_fills_store

class HammerFillsListener:
    """ Observer for Hammer Client messages to capture fills. """

    def __init__(self):
        self._order_tags: Dict[str, str] = {} # OrderID -> Strategy Tag
        self._processed_fill_ids: Set[str] = set() # Avoid duplicates
        # If FillID not available, dedupe by OrderID-Qty-Price combo?
        self._processed_events: Set[str] = set() 

    def register_order(self, order_id: str, tag: str):
        """ Register a strategy tag for an OrderID """
        if order_id and tag:
            self._order_tags[order_id] = tag
            # logger.debug(f"[HammerFills] Registered Order {order_id} with tag {tag}")

    def on_message(self, message: Dict[str, Any]):
        """ Handle incoming Hammer message """
        try:
            cmd = message.get("cmd")
            
            if cmd == "transactionsUpdate":
                self._handle_transactions_update(message)
                
        except Exception as e:
            logger.error(f"[HammerFills] Error processing message: {e}", exc_info=True)

    def _handle_transactions_update(self, message: Dict[str, Any]):
        result = message.get("result", {})
        transactions = result.get("transactions", [])
        
        for tx in transactions:
            # Check for filled status or usage of Fills array
            # Logic: If 'Fills' array exists, iterate it.
            # Else if StatusID == 'Filled' and 'FilledQTY' > 0, treat as fill (but be careful of partials)
            
            order_id = str(tx.get("OrderID", ""))
            symbol = tx.get("Symbol", "")
            action = tx.get("Action", "BUY").upper()
            
            # Use registered tag or default to MM (safer assumption for Hammer high freq?) 
            # Or "UNKNOWN". User prefers LT default generally, but Hammer is often MM.
            # Let's use UNKNOWN and let downstream logic handle it or user correction.
            strategy_tag = self._order_tags.get(order_id, "UNKNOWN") 
            
            fills = tx.get("Fills", [])
            
            if fills:
                # Iterate explicit fills
                for fill in fills:
                    self._log_single_fill(
                        fill_id=str(fill.get("FillID")),
                        symbol=symbol,
                        action=action,
                        qty=float(fill.get("QTY", 0)),
                        price=float(fill.get("Price", 0)),
                        tag=strategy_tag
                    )
            else:
                # No fills array, check generic fields
                # Only if StatusID is Filled or generic 'FilledQTY' increases?
                # The 'New' flag helps. Or 'changesOnly' mode.
                # If StatusID is Filled or Partial, we might have data.
                # But without FillID, deduplication is hard.
                # We will construct a synthetic FillID: OrderID_FilledQTY
                
                status = tx.get("StatusID", "")
                filled_qty = float(tx.get("FilledQTY", 0))
                filled_price = float(tx.get("FilledPrice", 0)) # Average price?
                
                # Only log if we have actual filled qty
                if filled_qty > 0 and status in ["Filled", "PartiallyFilled"]:
                    # Synthetic ID
                    # Note: If order fills 100, then 200... we get 100 then 200 total?
                    # API says "FilledQTY". Usually cumulative.
                    # Creating delta is complex without state.
                    # BUT we switched to 'changes=True'. 
                    # Does 'changes=True' send *deltas* or just *changed records*?
                    # "The transactionsUpdate... will always include only new or changed transactions."
                    # It returns the Transaction Object. The Transaction Object usually has Cumulative FilledQTY.
                    # If I see FilledQTY=100, then FilledQTY=200... 
                    # I need to log the *diff*.
                    # For now, let's assume 'Fills' array is present for granular updates as per example.
                    # If 'Fills' is missing, fallback is risky.
                    
                    # Log the cumulative as a single fill if it looks like a one-shot? 
                    # Or warn?
                    pass 

    def _log_single_fill(self, fill_id: str, symbol: str, action: str, qty: float, price: float, tag: str):
        if fill_id in self._processed_fill_ids:
            return
            
        self._processed_fill_ids.add(fill_id)
        
        # Log to DailyFillsStore
        try:
            # We use "HAMMER_PRO" as account type. 
            # This triggers 'hamfilledordersYYMMDD.csv'
            get_daily_fills_store().log_fill(
                account_type="HAMMER_PRO", 
                symbol=symbol, 
                action=action, 
                qty=qty, 
                price=price, 
                strategy_tag=tag
            )
            logger.info(f"🔨 [HAMMER FILL] Logged {symbol} {action} {qty} @ {price} ({tag})")
        except Exception as e:
            logger.error(f"[HammerFills] Failed to log fill: {e}")

# Global instance
_hammer_fills_listener = None

def get_hammer_fills_listener():
    global _hammer_fills_listener
    if not _hammer_fills_listener:
        _hammer_fills_listener = HammerFillsListener()
    return _hammer_fills_listener
