import asyncio
from app.psfalgo.ibkr_connector import get_ibkr_connector
from app.core.logger import logger

async def test_reconnect():
    # Use PED for testing if safer
    connector = get_ibkr_connector("IBKR_PED")
    
    print("Test 1: First connection (should use random ID)")
    # Note: We don't actually need to connect to a real TWS to verify the logic, 
    # but we can try if it's running.
    # We just want to see the LOGS showing the ID selection.
    
    # We'll mock the connectAsync to avoid needing a real TWS
    from unittest.mock import AsyncMock, MagicMock
    connector._ensure_ib_insync = lambda: True
    import app.psfalgo.ibkr_connector as ib_mod
    ib_mod.IB = MagicMock
    ib_mod.IB.return_value.connectAsync = AsyncMock()
    
    res = await connector.connect(port=4001)
    print(f"Result: {res}")
    
    print("\nTest 2: Second connection (should use ANOTHER random ID)")
    res2 = await connector.connect(port=4001)
    print(f"Result: {res2}")

if __name__ == "__main__":
    asyncio.run(test_reconnect())
