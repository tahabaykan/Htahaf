"""
Mode Manager - Trading Mode Management

Manages transitions between HAMPRO MOD, IBKR GUN MOD, and IBKR PED MOD.

!!! IMPORTANT FILE PATH WARNING !!!
===================================
ALL CSV READING AND WRITING OPERATIONS MUST BE DONE TO StockTracker DIRECTORY!!
NOT TO StockTracker/janall/ DIRECTORY!!
TO PREVENT CONFUSION, THIS RULE MUST BE STRICTLY FOLLOWED!
===================================
"""

import logging
import time
from typing import Optional, Callable, Dict, List, Any


class ModeManager:
    """
    Manages transitions between HAMPRO MOD, IBKR GUN MOD, and IBKR PED MOD.
    
    This class handles mode switching, order placement routing, and position/order
    retrieval based on the current active mode.
    """
    
    HAMPRO_MODE = "HAMPRO"
    IBKR_GUN_MODE = "IBKR_GUN"
    IBKR_PED_MODE = "IBKR_PED"
    
    def __init__(
        self,
        hammer_client=None,
        ibkr_client=None,
        ibkr_native_client=None,
        main_window=None
    ):
        """
        Initialize ModeManager.
        
        Args:
            hammer_client: Hammer Pro client instance
            ibkr_client: IBKR client instance (ib_insync)
            ibkr_native_client: IBKR native client instance (TWS API)
            main_window: Main window reference (for controller checks)
        """
        self.current_mode = self.HAMPRO_MODE  # Default mode
        self.hammer_client = hammer_client
        self.ibkr_client = ibkr_client
        self.ibkr_native_client = ibkr_native_client
        self.main_window = main_window
        
        # IBKR global throttle system
        self.last_ibkr_order_time = 0.0
        self.min_ibkr_order_interval = 0.1  # Minimum 0.1 second interval
        
        # Callbacks
        self.on_mode_changed: Optional[Callable[[str], None]] = None
        self.on_positions_changed: Optional[Callable[[List], None]] = None
        self.on_orders_changed: Optional[Callable[[List], None]] = None
        
        # Logging
        self.logger = logging.getLogger('mode_manager')
        self.logger.setLevel(logging.INFO)
    
    def set_mode(self, mode: str) -> bool:
        """
        Change the current trading mode.
        
        Args:
            mode: Mode to switch to (HAMPRO_MODE, IBKR_GUN_MODE, IBKR_PED_MODE)
            
        Returns:
            bool: True if mode was changed successfully, False otherwise
        """
        valid_modes = [self.HAMPRO_MODE, self.IBKR_GUN_MODE, self.IBKR_PED_MODE]
        if mode not in valid_modes:
            print(f"[MODE] ❌ Invalid mode: {mode}")
            return False
        
        if mode == self.current_mode:
            print(f"[MODE] ⚠️ Mode already set to {mode}")
            return True
        
        old_mode = self.current_mode
        self.current_mode = mode
        
        print(f"[MODE] 🔄 Mode changed: {old_mode} -> {mode}")
        
        # Call callback if set
        if callable(self.on_mode_changed):
            self.on_mode_changed(mode)
        
        return True
    
    def get_current_mode(self) -> str:
        """Get the current trading mode."""
        return self.current_mode
    
    def get_active_account(self) -> str:
        """Get the active account name based on current mode."""
        if self.is_hampro_mode():
            return "HAMPRO"
        elif self.is_ibkr_gun_mode():
            return "IBKR_GUN"
        elif self.is_ibkr_ped_mode():
            return "IBKR_PED"
        else:
            return "UNKNOWN"
    
    def is_hampro_mode(self) -> bool:
        """Check if currently in HAMPRO mode."""
        return self.current_mode == self.HAMPRO_MODE
    
    def is_hammer_mode(self) -> bool:
        """Check if currently in Hammer Pro mode (same as is_hampro_mode)."""
        return self.current_mode == self.HAMPRO_MODE
    
    def is_ibkr_mode(self) -> bool:
        """Check if currently in IBKR mode (GUN or PED)."""
        return self.current_mode in [self.IBKR_GUN_MODE, self.IBKR_PED_MODE]
    
    def is_ibkr_gun_mode(self) -> bool:
        """Check if currently in IBKR GUN mode."""
        return self.current_mode == self.IBKR_GUN_MODE
    
    def is_ibkr_ped_mode(self) -> bool:
        """Check if currently in IBKR PED mode."""
        return self.current_mode == self.IBKR_PED_MODE
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get positions based on current mode.
        
        Returns:
            List of position dictionaries
        """
        try:
            if self.is_hampro_mode():
                if self.hammer_client and self.hammer_client.connected:
                    positions = self.hammer_client.get_positions_direct()
                    print(f"[MODE] 📊 Retrieved {len(positions)} positions from HAMPRO")
                    return positions
                else:
                    print("[MODE] ❌ HAMPRO client not connected")
                    return []
            
            elif self.is_ibkr_mode():
                if self.ibkr_client and self.ibkr_client.is_connected():
                    positions = self.ibkr_client.get_positions_direct()
                    print(f"[MODE] 📊 Retrieved {len(positions)} positions from IBKR")
                    return positions
                else:
                    print("[MODE] ❌ IBKR client not connected")
                    return []
            
            return []
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    def get_orders(self) -> List[Dict[str, Any]]:
        """
        Get orders based on current mode.
        
        Returns:
            List of order dictionaries
        """
        try:
            if self.is_hampro_mode():
                if self.hammer_client and self.hammer_client.connected:
                    orders = self.hammer_client.get_orders()
                    print(f"[MODE] 📋 Retrieved {len(orders)} orders from HAMPRO")
                    return orders
                else:
                    print("[MODE] ❌ HAMPRO client not connected")
                    return []
            
            elif self.is_ibkr_mode():
                # Prefer native IBKR client
                if self.ibkr_native_client and self.ibkr_native_client.is_connected():
                    orders = self.ibkr_native_client.get_open_orders()
                    print(f"[MODE] 📋 Retrieved {len(orders)} orders from IBKR Native")
                    return orders
                elif self.ibkr_client and self.ibkr_client.is_connected():
                    orders = self.ibkr_client.get_orders_direct()
                    print(f"[MODE] 📋 Retrieved {len(orders)} orders from IBKR Client")
                    return orders
                else:
                    print("[MODE] ❌ IBKR client not connected")
                    return []
            
            return []
        except Exception as e:
            self.logger.error(f"Error getting orders: {e}")
            return []
    
    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get market data (always from Hammer Pro).
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary containing market data
        """
        if self.hammer_client and self.hammer_client.connected:
            return self.hammer_client.get_market_data(symbol)
        return {}
    
    def get_l2_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get L2 data (always from Hammer Pro).
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary containing L2 data
        """
        if self.hammer_client and self.hammer_client.connected:
            return self.hammer_client.get_l2_data(symbol)
        return {}
    
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        order_type: str = "LIMIT",
        hidden: bool = True
    ) -> bool:
        """
        Place order based on current mode with IBKR throttle and controller checks.
        
        Args:
            symbol: Stock symbol
            side: Order side (BUY/SELL/LONG/SHORT)
            quantity: Order quantity
            price: Order price
            order_type: Order type (default: LIMIT)
            hidden: Whether order is hidden (default: True)
            
        Returns:
            bool: True if order was placed successfully, False otherwise
        """
        try:
            # Log active mode
            active_mode = self.get_current_mode()
            active_account = self.get_active_account()
            print(
                f"[MODE] 📤 Placing order: {symbol} {side} {quantity} lots "
                f"@ ${price:.2f} | Mode: {active_mode} ({active_account})"
            )
            
            # Controller check (if main_window exists and controller is active)
            if self.main_window and hasattr(self.main_window, 'controller_check_order'):
                allowed, adjusted_qty, reason = self.main_window.controller_check_order(
                    symbol, side, quantity
                )
                
                if not allowed:
                    print(
                        f"[CONTROLLER] ❌ Order blocked: {symbol} {side} {quantity} - {reason}"
                    )
                    return False
                
                if adjusted_qty != quantity:
                    print(
                        f"[CONTROLLER] ⚠️ Order adjusted: {symbol} {side} {quantity} → "
                        f"{adjusted_qty} - {reason}"
                    )
                    quantity = adjusted_qty
            
            if self.is_hampro_mode():
                if self.hammer_client and self.hammer_client.connected:
                    print(
                        f"[MODE] 🔨 Placing order in HAMPRO mode: {symbol} {side} {quantity} lots"
                    )
                    return self.hammer_client.place_order(
                        symbol, side, quantity, price, order_type, hidden
                    )
                else:
                    print("[MODE] ❌ HAMPRO client not connected, cannot place order")
                    return False
            
            elif self.is_ibkr_mode():
                # IBKR global throttle check
                current_time = time.time()
                time_since_last_order = current_time - self.last_ibkr_order_time
                
                if time_since_last_order < self.min_ibkr_order_interval:
                    wait_time = self.min_ibkr_order_interval - time_since_last_order
                    print(f"[MODE] ⏳ IBKR throttle: waiting {wait_time:.2f}s...")
                    time.sleep(wait_time)
                
                # Determine IBKR mode detail (GUN or PED)
                ibkr_mode_detail = (
                    "IBKR_GUN" if self.is_ibkr_gun_mode()
                    else "IBKR_PED" if self.is_ibkr_ped_mode()
                    else "IBKR"
                )
                print(
                    f"[MODE] 🔄 Placing order in {ibkr_mode_detail} mode: "
                    f"{symbol} {side} {quantity} lots"
                )
                
                # Prefer native IBKR client (for hidden orders with displayQuantity)
                if self.ibkr_native_client and self.ibkr_native_client.is_connected():
                    print(f"[MODE] 🔄 Sending order via {ibkr_mode_detail} Native client...")
                    result = self.ibkr_native_client.place_order(
                        symbol, side, quantity, price, order_type, hidden
                    )
                    self.last_ibkr_order_time = time.time()
                    return result
                elif self.ibkr_client and self.ibkr_client.is_connected():
                    print(f"[MODE] 🔄 Sending order via {ibkr_mode_detail} ib_async client...")
                    result = self.ibkr_client.place_order(
                        symbol, side, quantity, price, order_type, hidden
                    )
                    self.last_ibkr_order_time = time.time()
                    return result
                else:
                    print(
                        f"[MODE] ❌ {ibkr_mode_detail} client not connected, "
                        f"cannot place order"
                    )
                    return False
            
            return False
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get connection status for all clients.
        
        Returns:
            Dictionary with connection statuses and current mode
        """
        hampro_status = (
            self.hammer_client.connected if self.hammer_client else False
        )
        ibkr_status = (
            self.ibkr_client.is_connected() if self.ibkr_client else False
        )
        
        return {
            'hampro': hampro_status,
            'ibkr': ibkr_status,
            'current_mode': self.current_mode
        }



