"""
BEFDAY Data Service - Single Source of Truth

Tüm kanallar (positions sekmesi, RevnBookCheck, vb.) bu servis üzerinden 
BEFDAY verisine erişir. Günde 1 kez CSV'den yüklenir, Redis'e yazılır.

3 hesap için ayrı BEFDAY dosyaları:
- HAMPRO: befham.csv
- IBKR_GUN: befibgun.csv  
- IBKR_PED: befibped.csv

Kullanım:
    from app.psfalgo.befday_data_service import get_befday_data_service
    
    service = get_befday_data_service()
    befday_map = service.get_befday(account_id="IBKR_PED")
"""

import os
import json
import pandas as pd
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from app.core.logger import logger


@dataclass
class BefDayEntry:
    """Single BEFDAY entry"""
    symbol: str
    quantity: float
    strategy: str = "LT"  # LT or MM
    origin: str = "OV"    # OV (overnight) always for befday
    side: str = ""        # Long or Short
    avg_cost: float = 0.0
    full_taxonomy: str = ""


class BefDayDataService:
    """
    BEFDAY Data Service - Merkezi BEFDAY veri yönetimi.
    
    Günde 1 kez CSV'den yükler, gün boyunca Redis'ten okur.
    Tüm kanallar bu servisi kullanır.
    """
    
    # Hesap -> CSV dosya eşlemesi
    ACCOUNT_CSV_MAP = {
        "HAMPRO": "befham.csv",
        "HAMMER_PRO": "befham.csv",
        "IBKR_GUN": "befibgun.csv",
        "IBKR_PED": "befibped.csv",
    }
    
    # Redis key prefix
    REDIS_KEY_PREFIX = "psfalgo:befday:data"
    REDIS_TTL = 86400  # 24 saat (günlük veri)
    
    def __init__(self):
        self._root_dir = self._find_root_dir()
        self._cache: Dict[str, Dict[str, BefDayEntry]] = {}
        self._cache_date: Dict[str, date] = {}
        self._redis = None
        self._init_redis()
        logger.info(f"[BefDayDataService] Initialized. Root: {self._root_dir}")
    
    def _find_root_dir(self) -> Path:
        """Find project root (C:\\StockTracker)"""
        # app/psfalgo/befday_data_service.py -> psfalgo -> app -> quant_engine -> StockTracker
        current = Path(__file__).resolve()
        root = current.parent.parent.parent.parent
        if (root / "befibped.csv").exists() or (root / "befham.csv").exists():
            return root
        # Fallback
        return Path("C:/StockTracker")
    
    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            from app.core.redis_client import get_redis_client
            self._redis = get_redis_client()
        except Exception as e:
            logger.warning(f"[BefDayDataService] Redis init failed: {e}")
            self._redis = None
    
    def _normalize_account(self, account_id: str) -> str:
        """Normalize account ID"""
        if not account_id:
            return "HAMPRO"
        acc = str(account_id).strip().upper()
        if acc == "HAMMER_PRO":
            return "HAMPRO"
        return acc
    
    def _get_csv_path(self, account_id: str) -> Path:
        """Get CSV file path for account"""
        acc = self._normalize_account(account_id)
        filename = self.ACCOUNT_CSV_MAP.get(acc, "befday.csv")
        return self._root_dir / filename
    
    def _is_csv_today(self, csv_path: Path) -> bool:
        """Check if CSV was modified today"""
        if not csv_path.exists():
            return False
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(csv_path))
            return mtime.date() == date.today()
        except Exception:
            return False
    
    def _get_redis_key(self, account_id: str) -> str:
        """Get Redis key for account"""
        acc = self._normalize_account(account_id)
        return f"{self.REDIS_KEY_PREFIX}:{acc}:{date.today().isoformat()}"
    
    def _load_from_redis(self, account_id: str) -> Optional[Dict[str, BefDayEntry]]:
        """Load BEFDAY from Redis"""
        if not self._redis:
            return None
        try:
            key = self._get_redis_key(account_id)
            # Use sync.get for consistency
            redis_sync = getattr(self._redis, 'sync', self._redis)
            data = redis_sync.get(key)
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                entries_list = json.loads(raw)
                result = {}
                for item in entries_list:
                    sym = str(item.get('symbol', '')).strip()
                    if sym:
                        result[sym] = BefDayEntry(
                            symbol=sym,
                            quantity=float(item.get('quantity', 0)),
                            strategy=item.get('strategy', 'LT'),
                            origin=item.get('origin', 'OV'),
                            side=item.get('side', ''),
                            avg_cost=float(item.get('avg_cost', 0) or 0),
                            full_taxonomy=item.get('full_taxonomy', '')
                        )
                logger.info(f"[BefDayDataService] Loaded {len(result)} entries from Redis for {account_id}")
                return result
        except Exception as e:
            logger.debug(f"[BefDayDataService] Redis load failed: {e}")
        return None
    
    def _save_to_redis(self, account_id: str, entries: Dict[str, BefDayEntry]):
        """Save BEFDAY to Redis — ONLY if key does NOT already exist"""
        if not self._redis or not entries:
            return
        try:
            key = self._get_redis_key(account_id)
            redis_sync = getattr(self._redis, 'sync', self._redis)
            # GUARD: Never overwrite existing BEFDAY data
            existing = redis_sync.get(key)
            if existing:
                logger.debug(f"[BefDayDataService] Redis key {key} already exists — NOT overwriting")
                return
            entries_list = [
                {
                    'symbol': e.symbol,
                    'quantity': e.quantity,
                    'strategy': e.strategy,
                    'origin': e.origin,
                    'side': e.side,
                    'avg_cost': e.avg_cost,
                    'full_taxonomy': e.full_taxonomy,
                }
                for e in entries.values()
            ]
            redis_sync.set(key, json.dumps(entries_list), ex=self.REDIS_TTL)
            logger.info(f"[BefDayDataService] ✅ Saved {len(entries_list)} entries to Redis for {account_id} (first write)")
        except Exception as e:
            logger.warning(f"[BefDayDataService] Redis save failed: {e}")
    
    def _load_from_csv(self, account_id: str) -> Dict[str, BefDayEntry]:
        """Load BEFDAY from CSV file"""
        result = {}
        csv_path = self._get_csv_path(account_id)
        
        if not csv_path.exists():
            logger.warning(f"[BefDayDataService] CSV not found: {csv_path}")
            return {}
        
        try:
            df = pd.read_csv(csv_path)
            
            # Detect CSV format (new vs old)
            has_new_format = 'Strategy' in df.columns and 'Full_Taxonomy' in df.columns
            
            for _, row in df.iterrows():
                try:
                    # Symbol
                    sym = str(row.get('Symbol', row.get('symbol', ''))).strip()
                    if not sym:
                        continue
                    
                    # Quantity - must handle signed values correctly
                    qty = float(row.get('Quantity', row.get('quantity', 0)))
                    
                    # Side detection: short must be negative
                    side = str(row.get('Side', row.get('side', ''))).strip()
                    pos_type = str(row.get('Position_Type', row.get('position_type', ''))).strip().upper()
                    
                    # Enforce: short = negative quantity
                    if qty > 0 and (side.lower() == 'short' or pos_type == 'SHORT'):
                        qty = -qty
                    
                    # Determine side from quantity if not set
                    if not side:
                        side = "Long" if qty >= 0 else "Short"
                    
                    # Strategy and taxonomy
                    if has_new_format:
                        strategy = str(row.get('Strategy', 'LT')).strip() or 'LT'
                        full_tax = str(row.get('Full_Taxonomy', '')).strip()
                    else:
                        strategy = 'LT'
                        full_tax = f"LT OV {side}"
                    
                    # Avg cost
                    avg_cost = 0.0
                    if 'Avg_Cost' in df.columns:
                        try:
                            avg_cost = float(row.get('Avg_Cost', 0) or 0)
                        except:
                            pass
                    elif 'AveragePrice' in df.columns:
                        try:
                            avg_cost = float(row.get('AveragePrice', 0) or 0)
                        except:
                            pass
                    
                    result[sym] = BefDayEntry(
                        symbol=sym,
                        quantity=qty,
                        strategy=strategy,
                        origin="OV",
                        side=side,
                        avg_cost=avg_cost,
                        full_taxonomy=full_tax
                    )
                except Exception as row_err:
                    logger.debug(f"[BefDayDataService] Row parse error: {row_err}")
                    continue
            
            logger.info(f"[BefDayDataService] Loaded {len(result)} entries from CSV: {csv_path.name}")
            return result
            
        except Exception as e:
            logger.error(f"[BefDayDataService] CSV load failed: {e}")
            return {}
    
    def get_befday(self, account_id: str, force_refresh: bool = False) -> Dict[str, float]:
        """
        Get BEFDAY quantities for account.
        
        Returns:
            Dict[symbol, quantity] - quantity is signed (negative for short)
        """
        acc = self._normalize_account(account_id)
        today = date.today()
        
        # Check in-memory cache first
        if not force_refresh and acc in self._cache:
            if self._cache_date.get(acc) == today:
                entries = self._cache[acc]
                return {sym: e.quantity for sym, e in entries.items()}
        
        # Try Redis
        entries = self._load_from_redis(acc)
        
        # If Redis empty or stale, load from CSV
        if not entries:
            csv_path = self._get_csv_path(acc)
            if csv_path.exists():
                entries = self._load_from_csv(acc)
                if entries:
                    # Save to Redis for other processes
                    self._save_to_redis(acc, entries)
        
        # Update cache
        if entries:
            self._cache[acc] = entries
            self._cache_date[acc] = today
            return {sym: e.quantity for sym, e in entries.items()}
        
        return {}
    
    def get_befday_entries(self, account_id: str) -> Dict[str, BefDayEntry]:
        """Get full BEFDAY entries (with strategy, side, avg_cost)"""
        acc = self._normalize_account(account_id)
        
        # Ensure loaded
        _ = self.get_befday(acc)
        
        return self._cache.get(acc, {})
    
    def get_befday_for_symbol(self, account_id: str, symbol: str) -> Optional[float]:
        """Get BEFDAY quantity for a specific symbol"""
        befday = self.get_befday(account_id)
        return befday.get(symbol)
    
    def is_csv_current(self, account_id: str) -> bool:
        """Check if CSV for account is from today"""
        csv_path = self._get_csv_path(account_id)
        return self._is_csv_today(csv_path)
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status for all accounts"""
        status = {}
        for acc in ["HAMPRO", "IBKR_GUN", "IBKR_PED"]:
            csv_path = self._get_csv_path(acc)
            status[acc] = {
                "csv_exists": csv_path.exists(),
                "csv_path": str(csv_path),
                "csv_current": self._is_csv_today(csv_path),
                "cached": acc in self._cache,
                "cache_count": len(self._cache.get(acc, {})),
            }
            if csv_path.exists():
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(csv_path))
                    status[acc]["csv_modified"] = mtime.isoformat()
                except:
                    pass
        return status


# ============================================================================
# Singleton
# ============================================================================

_service_instance: Optional[BefDayDataService] = None


def get_befday_data_service() -> BefDayDataService:
    """Get or create BefDayDataService singleton"""
    global _service_instance
    if _service_instance is None:
        _service_instance = BefDayDataService()
    return _service_instance


def reset_befday_data_service():
    """Reset singleton (for testing)"""
    global _service_instance
    _service_instance = None
