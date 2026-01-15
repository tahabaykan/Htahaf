import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import from DEBUG module
from app.psfalgo.order_controller_debug import (
    initialize_order_controller, 
    get_order_controller, 
    TrackedOrder, 
    OrderStatus
)

async def test_scoped_cancel():
    print("--- Test Scoped Cancel (DEBUG MODULE) ---")
    
    # 1. Initialize Controller
    ctrl = initialize_order_controller()
    
    # 2. Setup Valid Context (Helper Mock)
    async def mock_cancel(order, account_id):
        print(f"  [MOCK] Cancelled {order.order_id} in {account_id}")
    
    ctrl.set_callbacks(cancel_order_func=mock_cancel)
    
    # 3. Create Orders
    # HAMPRO - LT (Should Cancel)
    o1 = TrackedOrder(
        order_id="ord_1", symbol="AAPL", action="SELL", order_type="LIMIT",
        lot_qty=100, price=150.0, provider="HAMPRO", book="LT"
    )
    ctrl.track_order(o1)
    
    # HAMPRO - MM (Should KEEP)
    o2 = TrackedOrder(
        order_id="ord_2", symbol="GOOGL", action="BUY", order_type="LIMIT",
        lot_qty=50, price=2000.0, provider="HAMPRO", book="MM"
    )
    ctrl.track_order(o2)
    
    # IBKR_PED - LT (Should KEEP - Different Account)
    o3 = TrackedOrder(
        order_id="ord_3", symbol="MSFT", action="SELL", order_type="LIMIT",
        lot_qty=100, price=300.0, provider="IBKR_PED", book="LT"
    )
    ctrl.track_order(o3)
    
    print(f"Initial Active Orders: {len(ctrl.get_active_orders())}")
    
    # 4. Execute Cancel All for HAMPRO / LT
    print("Executing cancel_open_orders(HAMPRO, book='LT')...")
    count = await ctrl.cancel_open_orders("HAMPRO", book="LT")
    
    print(f"Cancelled Count: {count}")
    
    # 5. Assertions
    o1_final = ctrl.get_order("HAMPRO", "ord_1")
    o2_final = ctrl.get_order("HAMPRO", "ord_2")
    o3_final = ctrl.get_order("IBKR_PED", "ord_3")
    
    print(f"Order 1 (HAMPRO/LT) Status: {o1_final.status.value}")
    print(f"Order 2 (HAMPRO/MM) Status: {o2_final.status.value}")
    print(f"Order 3 (IBKR/LT) Status: {o3_final.status.value}")
    
    assert o1_final.status == OrderStatus.CANCELLED, "HAMPRO/LT should be CANCELLED"
    assert o2_final.status == OrderStatus.PENDING, "HAMPRO/MM should be PENDING"
    assert o3_final.status == OrderStatus.PENDING, "IBKR/LT should be PENDING"
    assert count == 1, f"Expected 1 cancellation, got {count}"
    
    print("✅ TEST PASSED")

if __name__ == "__main__":
    asyncio.run(test_scoped_cancel())
