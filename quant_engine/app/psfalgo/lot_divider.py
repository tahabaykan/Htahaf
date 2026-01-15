"""
Lot Divider - Janall-Compatible

Splits large orders into smaller chunks to avoid market impact.

Janall Logic:
- If order size > max_lot_per_order (default 500), split into smaller orders
- Each split order is max_lot_per_order or less
- Delay between split orders (default 500ms)

Janall Lot Rounding:
- 0-100 → 100
- 101-200 → 200
- 201-300 → 300
- ... (round up to nearest 100)
- >1000 → (calculated + 99) // 100 * 100 (round up to 100)

Example:
- Order: 1500 lots
- max_lot_per_order: 500
- Result: 3 orders of 500 lots each
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.core.logger import logger


@dataclass
class SplitOrder:
    """A single split order"""
    symbol: str
    action: str                    # BUY, SELL, SHORT, COVER
    order_type: str               # BID_BUY, ASK_SELL
    lot_qty: int
    price_hint: Optional[float]
    parent_order_id: str          # Reference to original order
    split_index: int              # 0, 1, 2, ...
    total_splits: int
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class LotDividerConfig:
    """Lot Divider configuration"""
    enabled: bool = True
    max_lot_per_order: int = 500      # Maximum lot per single order
    split_threshold: int = 500         # Split if lot > this value
    split_delay_ms: int = 500          # Delay between split orders (ms)
    min_lot_size: int = 100            # Minimum lot size


class LotDivider:
    """
    Lot Divider - splits large orders into smaller chunks.
    
    Features:
    - Configurable max lot per order
    - Configurable delay between splits
    - Maintains order sequence
    - Tracks parent-child relationship
    - Janall-compatible lot rounding
    """
    
    def __init__(self, config: Optional[LotDividerConfig] = None):
        """
        Initialize Lot Divider.
        
        Args:
            config: LotDividerConfig object
        """
        self.config = config or LotDividerConfig()
        logger.info(
            f"LotDivider initialized: max_lot={self.config.max_lot_per_order}, "
            f"threshold={self.config.split_threshold}, delay={self.config.split_delay_ms}ms"
        )
    
    @staticmethod
    def round_lot_janall(lot_qty: int, min_lot: int = 100) -> int:
        """
        Round lot quantity using Janall's rounding logic.
        
        Janall Rounding Rules:
        - 0-100 → 100 (minimum lot)
        - 101-200 → 200
        - 201-300 → 300
        - ... (round UP to nearest 100)
        - Formula: ((lot + 99) // 100) * 100
        
        Args:
            lot_qty: Raw lot quantity
            min_lot: Minimum lot size (default 100)
            
        Returns:
            Rounded lot quantity
        """
        if lot_qty <= 0:
            return 0
        
        if lot_qty <= min_lot:
            return min_lot
        
        # Round UP to nearest 100
        # Formula: ((lot + 99) // 100) * 100
        rounded = ((lot_qty + 99) // 100) * 100
        
        return max(rounded, min_lot)
    
    def should_split(self, lot_qty: int) -> bool:
        """
        Check if order should be split.
        
        Args:
            lot_qty: Order lot quantity
            
        Returns:
            True if order should be split
        """
        if not self.config.enabled:
            return False
        
        return lot_qty > self.config.split_threshold
    
    def split_order(
        self,
        symbol: str,
        action: str,
        order_type: str,
        total_lot: int,
        price_hint: Optional[float] = None,
        order_id: Optional[str] = None,
        apply_rounding: bool = True
    ) -> List[SplitOrder]:
        """
        Split a large order into smaller orders.
        
        Args:
            symbol: Symbol string
            action: BUY, SELL, SHORT, COVER
            order_type: BID_BUY, ASK_SELL
            total_lot: Total lot quantity
            price_hint: Price hint (optional)
            order_id: Parent order ID (optional)
            apply_rounding: Whether to apply Janall lot rounding (default True)
            
        Returns:
            List of SplitOrder objects
        """
        # Apply Janall rounding to total lot first
        if apply_rounding:
            total_lot = self.round_lot_janall(total_lot, self.config.min_lot_size)
        
        if not self.config.enabled or total_lot <= self.config.split_threshold:
            # No split needed, return single order
            return [SplitOrder(
                symbol=symbol,
                action=action,
                order_type=order_type,
                lot_qty=total_lot,
                price_hint=price_hint,
                parent_order_id=order_id or f"{symbol}_{datetime.now().timestamp()}",
                split_index=0,
                total_splits=1
            )]
        
        # Calculate splits
        splits = []
        remaining = total_lot
        split_index = 0
        parent_id = order_id or f"{symbol}_{datetime.now().timestamp()}"
        
        while remaining > 0:
            # Calculate this split's lot
            split_lot = min(remaining, self.config.max_lot_per_order)
            
            # Apply Janall rounding to each split
            if apply_rounding:
                split_lot = self.round_lot_janall(split_lot, self.config.min_lot_size)
            
            # Ensure minimum lot size
            if split_lot < self.config.min_lot_size:
                if remaining >= self.config.min_lot_size:
                    split_lot = self.config.min_lot_size
                else:
                    # Remaining is less than minimum, skip
                    break
            
            splits.append(SplitOrder(
                symbol=symbol,
                action=action,
                order_type=order_type,
                lot_qty=split_lot,
                price_hint=price_hint,
                parent_order_id=parent_id,
                split_index=split_index,
                total_splits=0  # Will be updated after loop
            ))
            
            remaining -= split_lot
            split_index += 1
        
        # Update total_splits
        total_splits = len(splits)
        for split in splits:
            split.total_splits = total_splits
        
        logger.info(
            f"[LOT_DIVIDER] {symbol}: Split {total_lot} lots into {total_splits} orders "
            f"({self.config.max_lot_per_order} max each)"
        )
        
        return splits
    
    async def execute_splits_with_delay(
        self,
        splits: List[SplitOrder],
        execute_func
    ) -> List[Dict[str, Any]]:
        """
        Execute split orders with delay between each.
        
        Args:
            splits: List of SplitOrder objects
            execute_func: Async function to execute each order
                         Signature: execute_func(split: SplitOrder) -> Dict
            
        Returns:
            List of execution results
        """
        results = []
        
        for i, split in enumerate(splits):
            # Execute order
            try:
                result = await execute_func(split)
                results.append({
                    'split_index': split.split_index,
                    'symbol': split.symbol,
                    'lot_qty': split.lot_qty,
                    'success': True,
                    'result': result
                })
                
                logger.debug(
                    f"[LOT_DIVIDER] {split.symbol}: Split {i+1}/{len(splits)} executed "
                    f"({split.lot_qty} lots)"
                )
                
            except Exception as e:
                results.append({
                    'split_index': split.split_index,
                    'symbol': split.symbol,
                    'lot_qty': split.lot_qty,
                    'success': False,
                    'error': str(e)
                })
                
                logger.error(
                    f"[LOT_DIVIDER] {split.symbol}: Split {i+1}/{len(splits)} failed: {e}"
                )
            
            # Delay before next split (except for last one)
            if i < len(splits) - 1:
                await asyncio.sleep(self.config.split_delay_ms / 1000.0)
        
        return results


# ============================================================================
# Global Instance Management
# ============================================================================

_lot_divider: Optional[LotDivider] = None


def get_lot_divider() -> Optional[LotDivider]:
    """Get global LotDivider instance"""
    return _lot_divider


def initialize_lot_divider(config: Optional[Dict[str, Any]] = None) -> LotDivider:
    """Initialize global LotDivider instance"""
    global _lot_divider
    
    if config:
        lot_config = LotDividerConfig(
            enabled=config.get('enabled', True),
            max_lot_per_order=config.get('max_lot_per_order', 500),
            split_threshold=config.get('split_threshold', 500),
            split_delay_ms=config.get('split_delay_ms', 500),
            min_lot_size=config.get('min_lot_size', 100)
        )
    else:
        lot_config = LotDividerConfig()
    
    _lot_divider = LotDivider(config=lot_config)
    logger.info("LotDivider initialized (Janall-compatible)")
    return _lot_divider

