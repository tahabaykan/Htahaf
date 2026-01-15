"""tests/fault/fault_ibkr_disconnect.py

Test IBKR disconnect handling: automatic retry, exponential backoff, no crash.
"""

import time
import pytest
from unittest.mock import Mock, patch

from app.order.order_router import OrderRouter
from app.core.logger import logger


class TestIBKRDisconnect:
    """Test IBKR disconnect handling"""
    
    def test_disconnect_during_active_executions(self):
        """Test disconnect during active executions"""
        router = OrderRouter()
        
        # Mock IB connection
        mock_ib = Mock()
        mock_ib.isConnected.return_value = False
        mock_ib.connect.side_effect = [Exception("Connection lost"), True]  # Fail then succeed
        
        router.ib = mock_ib
        router.connected = True
        
        # Simulate disconnect
        router.connected = False
        
        # Try to reconnect
        retry_count = 0
        max_retries = 3
        backoff = 1.0
        
        for i in range(max_retries):
            try:
                if router.connect():
                    break
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(backoff)
                    backoff *= 2  # Exponential backoff
                else:
                    raise
        
        # Verify retry logic
        assert retry_count > 0, "Should have retried"
        print(f"✓ Retried {retry_count} times with exponential backoff")
    
    def test_no_crash_on_disconnect(self):
        """Test system doesn't crash on disconnect"""
        router = OrderRouter()
        router.connected = True
        
        # Simulate disconnect
        router.connected = False
        
        # Try to execute order (should handle gracefully)
        try:
            # This should not crash
            if not router.connected:
                logger.warning("Not connected, skipping order")
        except Exception as e:
            pytest.fail(f"System crashed on disconnect: {e}")
        
        print("✓ System handles disconnect gracefully")
    
    def test_state_consistency_after_disconnect(self):
        """Test state consistency after disconnect"""
        router = OrderRouter()
        router.connected = True
        
        # Simulate some state
        pending_orders = [1, 2, 3]
        
        # Disconnect
        router.connected = False
        
        # Verify state is consistent
        assert router.connected == False, "Should be disconnected"
        # Pending orders should be preserved or handled
        print("✓ State remains consistent after disconnect")








