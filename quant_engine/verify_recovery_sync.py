
import asyncio
from app.terminals.revnbookcheck import RevnBookCheckTerminal
from app.psfalgo.account_mode import AccountMode
from app.core.logger import logger

async def verify_recovery_sync():
    print("Verifying RevRecoveryService Sync...")
    
    # 0. Initialize PositionSnapshotAPI (Normally done by main app)
    from app.psfalgo.position_snapshot_api import initialize_position_snapshot_api
    initialize_position_snapshot_api()
    
    # 1. Instantiate Terminal
    terminal = RevnBookCheckTerminal()
    
    # 2. Set account mode (e.g. IBKR_PED)
    terminal.account_mode = "IBKR_PED"
    print(f"Testing with account mode: {terminal.account_mode}")
    
    # 3. Trigger connection initialization
    print("Initializing connections...")
    await terminal._ensure_connections()
    
    # 4. Try fetching positions via the recovery service's logic
    from app.psfalgo.position_snapshot_api import get_position_snapshot_api
    pos_api = get_position_snapshot_api()
    
    if not pos_api:
        print("✗ PositionSnapshotAPI not initialized")
        return
        
    print("Fetching position snapshots...")
    snapshots = await pos_api.get_position_snapshot(account_id=terminal.account_mode)
    
    print(f"Found {len(snapshots)} snapshots.")
    for snap in snapshots[:5]: # Show first 5
        print(f"Symbol: {snap.symbol}, Qty: {snap.qty}, Befday: {snap.befday_qty}, Potential: {snap.potential_qty}")
    
    if len(snapshots) > 0:
        print("\n✓ SUCCESS: Position snapshots fetched successfully.")
    else:
        print("\n⚠ WARNING: 0 positions fetched. This may be expected if the account is empty, but verify IBKR Gateway is running.")

if __name__ == "__main__":
    asyncio.run(verify_recovery_sync())
