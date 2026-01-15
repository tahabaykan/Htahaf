"""
Daily Fills Store
-----------------
Manages the recording and retrieval of daily filled orders.
This explicitly follows the user requirement to persist fills to:
`data/logs/orders/ib{account}filledorders{YYMMDD}.csv`

And allows querying these fills to reconstruct "Intraday Strategy Breakdown" (LT vs MM).
"""

import os
import csv
import threading
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from app.core.logger import logger

class DailyFillsStore:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DailyFillsStore, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.log_dir = r"data/logs/daily_fills"
        os.makedirs(self.log_dir, exist_ok=True)
        self.lock = threading.Lock()
        
    def _get_filename(self, account_type: str) -> str:
        """
        Generate filename: ib{account}filledorders{YYMMDD}.csv
        Example: ibibkr_gunfilledorders260114.csv (per user example format)
        User said: ibpedfilledorders140126.csv
        So format is: ib{ped/gun}filledorders{YYMMDD}.csv
        """
        # User defined format: 
        # - ibpedfilledordersYYMMDD.csv
        # - ibgunfilledordersYYMMDD.csv
        # - hamfilledordersYYMMDD.csv
        
        date_str = datetime.now().strftime("%y%m%d")
        acc_lower = account_type.lower()
        
        if "hammer" in acc_lower:
            return f"hamfilledorders{date_str}.csv"
        elif "ped" in acc_lower:
            return f"ibpedfilledorders{date_str}.csv"
        elif "gun" in acc_lower:
            return f"ibgunfilledorders{date_str}.csv"
        else:
             # Fallback
             return f"unknown_filledorders{date_str}.csv"
        
    def log_fill(self, 
                 account_type: str, 
                 symbol: str, 
                 action: str, 
                 qty: float, 
                 price: float, 
                 strategy_tag: str):
        """
        Append a fill to the daily CSV.
        Args:
            strategy_tag: The orderRef (e.g. "LT_TRIM", "MM_ENGINE", "JFIN")
        """
        filename = self._get_filename(account_type)
        filepath = os.path.join(self.log_dir, filename)
        
        row = {
            "Time": datetime.now().strftime("%H:%M:%S"),
            "Symbol": symbol,
            "Action": action,
            "Quantity": qty,
            "Price": price,
            "Strategy": strategy_tag,
            "Source": "AUTO"
        }
        
        fieldnames = ["Time", "Symbol", "Action", "Quantity", "Price", "Strategy", "Source"]
        
        with self.lock:
            file_exists = os.path.isfile(filepath)
            try:
                with open(filepath, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow(row)
                logger.info(f"[FILL_LOG] Logged fill to {filename}: {symbol} {action} {qty} ({strategy_tag})")
            except Exception as e:
                logger.error(f"[FILL_LOG] Failed to log fill: {e}")

    def get_intraday_breakdown(self, account_type: str, symbol: str) -> Dict[str, float]:
        """
        Read today's CSV and aggregate Net Quantity per Strategy Tag for a specific symbol.
        Returns:
            Dict: {'LT': 100.0, 'MM': 50.0} (Aggregated by inferred bucket)
        """
        filename = self._get_filename(account_type)
        filepath = os.path.join(self.log_dir, filename)
        
        breakdown = defaultdict(float)
        
        if not os.path.exists(filepath):
            return dict(breakdown)
            
        try:
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Symbol") == symbol:
                        qty = float(row.get("Quantity", 0))
                        action = row.get("Action", "").upper()
                        strategy = row.get("Strategy", "UNKNOWN").upper()
                        
                        # Sign correction (Sell is negative impact on holdings)
                        signed_qty = qty if action == "BUY" else -qty
                        
                        # Map specific strategies to buckets (LT/MM)
                        # "JFIN", "LT_TRIM", "REDUCEMORE" -> LT
                        # "GREATEST_MM", "SIDEHIT", "MM_ENGINE" -> MM
                        bucket = "LT" # Default fallback as per user request
                        
                        if any(x in strategy for x in ["MM", "SIDEHIT"]):
                            bucket = "MM"
                        elif any(x in strategy for x in ["LT", "JFIN", "REDUCEMORE", "KARBOTU"]):
                            bucket = "LT"
                        
                        breakdown[bucket] += signed_qty
                        
            return dict(breakdown)
            
        except Exception as e:
            logger.error(f"[FILL_LOG] Failed to read breakdown: {e}")
            return {}

_daily_fills_store = None
def get_daily_fills_store():
    global _daily_fills_store
    if _daily_fills_store is None:
        _daily_fills_store = DailyFillsStore()
    return _daily_fills_store
