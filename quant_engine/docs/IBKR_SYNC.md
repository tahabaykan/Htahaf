# IBKR Synchronization Documentation

## Overview

IBKRSync module handles synchronization of positions, orders, and account data from IBKR TWS/Gateway. It's used for system startup, position reconciliation, and manual synchronization.

## Architecture

```
┌─────────────┐
│   IBKR      │
│  TWS/Gateway│
└──────┬──────┘
       │
       │ API calls
       ▼
┌─────────────┐
│  IBKRSync   │
│             │
│ - fetch_open_positions() │
│ - fetch_open_orders()    │
│ - fetch_account_summary()│
└──────┬──────┘
       │
       │ sync_positions_to_manager()
       ▼
┌──────────────────┐
│ Position Manager │
│  Position State  │
└──────────────────┘
```

## Methods

### `fetch_open_positions()`

Fetches all open positions from IBKR.

**Returns:** List of position dicts

**Example:**
```python
from app.ibkr.ibkr_sync import ibkr_sync

positions = ibkr_sync.fetch_open_positions()
# Returns:
# [
#     {
#         'symbol': 'AAPL',
#         'qty': 10.0,
#         'avg_price': 150.25,
#         'account': 'DU123456',
#         'market_value': 1502.50,
#         'unrealized_pnl': 2.50,
#         'realized_pnl': 0.0
#     },
#     ...
# ]
```

### `fetch_open_orders()`

Fetches all open orders from IBKR.

**Returns:** List of order dicts

**Example:**
```python
orders = ibkr_sync.fetch_open_orders()
# Returns:
# [
#     {
#         'order_id': 12345,
#         'symbol': 'AAPL',
#         'action': 'BUY',
#         'quantity': 10.0,
#         'order_type': 'LMT',
#         'limit_price': 150.0,
#         'status': 'Submitted',
#         'filled': 0.0,
#         'remaining': 10.0,
#         'avg_fill_price': None
#     },
#     ...
# ]
```

### `fetch_account_summary(account=None)`

Fetches account summary from IBKR.

**Parameters:**
- `account`: Account ID (None = all accounts)

**Returns:** Account summary dict

**Example:**
```python
summary = ibkr_sync.fetch_account_summary()
# Returns:
# {
#     'accounts': ['DU123456'],
#     'values': {
#         'NetLiquidation': {'DU123456': '100000.00'},
#         'TotalCashValue': {'DU123456': '50000.00'},
#         ...
#     },
#     'common': {
#         'NetLiquidation': {'DU123456': '100000.00'},
#         'BuyingPower': {'DU123456': '200000.00'},
#         ...
#     }
# }
```

### `sync_positions_to_manager(position_manager)`

Syncs IBKR positions to position manager.

**Parameters:**
- `position_manager`: PositionManager instance

**Returns:** None

**Example:**
```python
from app.engine.position_manager import PositionManager
from app.ibkr.ibkr_sync import ibkr_sync

pm = PositionManager()
ibkr_sync.sync_positions_to_manager(pm)
```

## Startup Sync Sequence

### Automatic Sync

Engine automatically syncs positions on startup:

```python
# engine_loop.py
async def run_async(self):
    # Sync positions from IBKR
    if self.sync_on_start:
        await self._sync_positions_on_start()
    
    # Start engine...
```

### Sync Flow

```
1. Engine starts
   ↓
2. Connect to IBKR (if not connected)
   ↓
3. Fetch open positions
   ↓
4. Update position manager
   ↓
5. Log synced positions
   ↓
6. Start engine loop
```

### Example Output

```
Syncing positions from IBKR...
Synced position: AAPL = 10 @ 150.25
Synced position: MSFT = -5 @ 350.00
Synced 2 positions from IBKR
```

## Manual Sync

### CLI Command

```bash
python main.py sync
```

### Output

```
=== Open Positions ===
  AAPL: +10 @ $150.25 (P&L: $2.50)
  MSFT: -5 @ $350.00 (P&L: -$1.25)

=== Open Orders ===
  AAPL BUY 10 (LMT) - Status: Submitted (Filled: 0, Remaining: 10)

=== Account Summary ===
  Account: DU123456
    NetLiquidation: 100000.00
    TotalCashValue: 50000.00
    BuyingPower: 200000.00
```

### Programmatic Usage

```python
from app.ibkr.ibkr_sync import ibkr_sync
from app.ibkr.ibkr_client import ibkr_client

# Connect to IBKR
ibkr_client.connect()

# Fetch data
positions = ibkr_sync.fetch_open_positions()
orders = ibkr_sync.fetch_open_orders()
summary = ibkr_sync.fetch_account_summary()

# Sync to position manager
from app.engine.position_manager import PositionManager
pm = PositionManager()
ibkr_sync.sync_positions_to_manager(pm)
```

## Offline/Online Mode Behavior

### Online Mode (IBKR Connected)

- Fetches real-time data from IBKR
- Updates position manager
- Shows current account values

### Offline Mode (IBKR Not Connected)

- Logs warning
- Skips sync
- Engine continues with existing positions
- Manual sync command shows error

### Error Handling

```python
# If IBKR not connected
if not ibkr_client.is_connected():
    logger.warning("IBKR not connected, skipping position sync")
    return

# If fetch fails
try:
    positions = ibkr_sync.fetch_open_positions()
except Exception as e:
    logger.error(f"Error fetching positions: {e}")
    return []
```

## Account Summary Fields

### Common Fields

- `NetLiquidation`: Total account value
- `TotalCashValue`: Cash balance
- `BuyingPower`: Available buying power
- `GrossPositionValue`: Total position value
- `AvailableFunds`: Available funds
- `ExcessLiquidity`: Excess liquidity

### Usage

```python
summary = ibkr_sync.fetch_account_summary()
net_liq = summary['common']['NetLiquidation']['DU123456']
buying_power = summary['common']['BuyingPower']['DU123456']
```

## Best Practices

1. **Always sync on startup** - Ensures position accuracy
2. **Handle connection errors** - Don't fail if IBKR unavailable
3. **Log sync results** - For audit trail
4. **Validate position data** - Before updating manager
5. **Use manual sync for debugging** - `python main.py sync`

## Troubleshooting

### Problem: Sync fails on startup

**Symptoms:**
- Engine starts but positions not synced
- Warning in logs

**Solutions:**
1. Check IBKR connection: `ibkr_client.is_connected()`
2. Verify TWS/Gateway is running
3. Check API permissions
4. Try manual sync: `python main.py sync`

### Problem: Positions not matching IBKR

**Symptoms:**
- Position manager shows different positions than IBKR

**Solutions:**
1. Run manual sync: `python main.py sync`
2. Check for execution handler errors
3. Verify execution messages are processed
4. Reconcile manually if needed

### Problem: Account summary empty

**Symptoms:**
- Account summary returns empty dict

**Solutions:**
1. Check account ID is correct
2. Verify IBKR connection
3. Check API permissions for account data
4. Review IBKR logs

## Related Documentation

- [Execution Pipeline](./EXECUTION_PIPELINE.md) - Execution flow
- [Position Manager](./POSITION_MANAGER.md) - Position tracking








