# Phase 11: Persistent Dual Connection Architecture

## Overview

The Quant Engine now maintains **persistent connections** to **ALL trading accounts simultaneously**:
- **IBKR_PED** (Interactive Brokers PED account)
- **IBKR_GUN** (Interactive Brokers GUN account)
- **HAMMER_PRO** (Hammer Pro trading platform)

All connections are established **once on startup** and remain active throughout the application lifecycle. Account mode switching **ONLY changes which account's data is used** - it does NOT disconnect/reconnect anything.

## Key Principles

### 1. Persistent Connections
- All 3 accounts connect on application startup
- Connections remain active until application shutdown
- No disconnections occur during mode switching

### 2. Mode-Based Data Routing
- Active account mode determines which data source is used
- Mode is stored in Redis: `psfalgo:trading:account_mode`
- Switching modes is instant (no connection overhead)

### 3. Market Data Source
- Market data (bid/ask/last) **ALWAYS** comes from HAMMER PRO
- This is unchanged from previous architecture
- IBKR is ONLY used for positions/orders/account data

### 4. Redis Key Separation
- Each account has its own Redis keys:
  - `psfalgo:positions:IBKR_PED`
  - `psfalgo:positions:IBKR_GUN`
  - `psfalgo:positions:HAMPRO`
- Same pattern for orders, fills, etc.

## Architecture Components

### DualConnectionManager (`dual_connection_manager.py`)
**Purpose**: Manages persistent connections to all accounts

**Responsibilities**:
- Initialize IBKR_PED connection on startup
- Initialize IBKR_GUN connection on startup
- Initialize HAMMER_PRO connection on startup
- Track connection status for each account
- Provide unified interface for connection status queries

**Does NOT**:
- Switch active account mode (handled by AccountModeManager)
- Route data requests (handled by PositionSnapshotAPI)
- Execute orders (handled by ExecutionRouter)

### AccountModeManager (`account_mode.py`)
**Purpose**: Manages active account mode selection

**Changes in Phase 11**:
- `set_mode()` now ONLY updates Redis flags
- NO connection/disconnection logic
- Assumes all accounts are already connected

**Workflow**:
1. User clicks account button (IBKR_PED/IBKR_GUN/HAMPRO)
2. `set_mode()` updates Redis:
   - `psfalgo:trading:account_mode` → new mode
   - `psfalgo:recovery:account_open` → new mode
   - `psfalgo:ibkr:active_account` → new mode (or None for HAMPRO)
3. Position snapshot is refreshed for new account
4. Done - instant switch!

### IBKRConnector (`ibkr_connector.py`)
**Purpose**: Manages IBKR Gateway connections

**Changes in Phase 11**:
- Removed `disconnect_other_ibkr_account()` call
- Both IBKR_PED and IBKR_GUN can be connected simultaneously
- Each uses unique client ID (PED=21, GUN=19)
- Both use same port (4001 or auto-detect)

## Startup Sequence

```python
# 1. Initialize Dual Connection Manager
initialize_dual_connection_manager()

# 2. Connect ALL accounts in parallel
dual_conn_mgr = get_dual_connection_manager()
connection_results = await dual_conn_mgr.connect_all()

# 3. Set default active account (HAMMER_PRO)
set_active_ibkr_account(None)
redis.set("psfalgo:trading:account_mode", "HAMPRO")

# 4. All accounts remain connected
# User can switch between them instantly via UI
```

## Account Mode Switching

### User Action
User clicks account button in UI (e.g., "IBKR PED")

### Backend Flow
```python
# 1. API receives request
POST /api/psfalgo/account/mode?mode=IBKR_PED

# 2. AccountModeManager updates Redis (NO connections changed)
await account_mode_manager.set_mode("IBKR_PED")

# 3. Redis flags updated
psfalgo:trading:account_mode = "IBKR_PED"
psfalgo:ibkr:active_account = "IBKR_PED"

# 4. Position snapshot refreshed
snapshots = await pos_api.get_position_snapshot(account_id="IBKR_PED")

# 5. Done - instant switch!
```

### What Happens to Other Connections?
**NOTHING!** All connections remain active:
- IBKR_PED: ✅ Connected
- IBKR_GUN: ✅ Connected
- HAMMER_PRO: ✅ Connected

Only the **active account flag** changes.

## Data Routing

### Positions
```python
# PositionSnapshotAPI checks active account
active_account = get_active_ibkr_account()  # From Redis

if active_account == "IBKR_PED":
    positions = await ibkr_ped_connector.get_positions()
elif active_account == "IBKR_GUN":
    positions = await ibkr_gun_connector.get_positions()
else:  # HAMPRO
    positions = hammer_positions_service.get_positions()
```

### Orders
```python
# ExecutionRouter checks active account
active_account = redis.get("psfalgo:trading:account_mode")

if active_account == "IBKR_PED":
    result = await ibkr_ped_connector.place_order(...)
elif active_account == "IBKR_GUN":
    result = await ibkr_gun_connector.place_order(...)
else:  # HAMPRO
    result = await hammer_execution_service.place_order(...)
```

### Market Data
```python
# ALWAYS from HAMMER PRO (unchanged)
bid, ask, last = hammer_feed.get_l1_data(symbol)
```

## Redis Key Structure

### Account-Specific Keys
Each account has its own namespace:

```
psfalgo:positions:IBKR_PED     → IBKR PED positions
psfalgo:positions:IBKR_GUN     → IBKR GUN positions
psfalgo:positions:HAMPRO       → HAMMER PRO positions

psfalgo:open_orders:IBKR_PED   → IBKR PED open orders
psfalgo:open_orders:IBKR_GUN   → IBKR GUN open orders
psfalgo:open_orders:HAMPRO     → HAMMER PRO open orders

psfalgo:fills:IBKR_PED         → IBKR PED fills
psfalgo:fills:IBKR_GUN         → IBKR GUN fills
psfalgo:fills:HAMPRO           → HAMMER PRO fills
```

### Global Keys
These keys track the active account:

```
psfalgo:trading:account_mode   → Current active mode (IBKR_PED/IBKR_GUN/HAMPRO)
psfalgo:ibkr:active_account    → Active IBKR account (IBKR_PED/IBKR_GUN or None)
psfalgo:recovery:account_open  → Account for recovery/REV orders
```

## Connection Status API

### Check All Connections
```bash
GET /api/psfalgo/account/ibkr/status
```

**Response**:
```json
{
  "success": true,
  "active_account": "IBKR_PED",
  "IBKR_PED": {
    "connected": true,
    "status": "connected",
    "error": null
  },
  "IBKR_GUN": {
    "connected": true,
    "status": "connected",
    "error": null
  },
  "HAMMER_PRO": {
    "connected": true,
    "status": "connected",
    "error": null
  }
}
```

## Benefits

### 1. Instant Mode Switching
- No connection overhead
- No waiting for authentication
- Immediate data availability

### 2. Reliability
- Connections maintained continuously
- No reconnection failures during mode switch
- Better connection stability

### 3. Flexibility
- Can monitor all accounts simultaneously
- Easy to add multi-account features later
- Simplified architecture (no complex disconnect logic)

### 4. Performance
- Parallel connection initialization on startup
- No serial connect/disconnect cycles
- Faster overall system response

## Migration from Phase 10

### What Changed
1. **Removed**: `disconnect_other_ibkr_account()` logic
2. **Added**: `DualConnectionManager` for unified connection management
3. **Modified**: `AccountModeManager.set_mode()` - now only updates Redis
4. **Modified**: Startup sequence - connects all accounts in parallel

### What Stayed the Same
1. Market data still comes from HAMMER PRO
2. Position/order APIs unchanged
3. Redis key structure (just clarified account-specific keys)
4. UI account selection buttons

### Backward Compatibility
- All existing APIs work unchanged
- Redis keys maintain same structure
- No breaking changes to frontend

## Troubleshooting

### Connection Issues on Startup
If a connection fails on startup, the system will continue with available connections:

```
[STARTUP] Connection Results:
  IBKR_PED: ✅ 
  IBKR_GUN: ❌ Connection refused
  HAMMER_PRO: ✅ 
```

User can still switch to IBKR_PED or HAMMER_PRO. IBKR_GUN will show as unavailable.

### Checking Connection Status
```python
from app.psfalgo.dual_connection_manager import get_dual_connection_manager

dual_conn_mgr = get_dual_connection_manager()
status = dual_conn_mgr.get_status()

print(f"IBKR_PED: {status['ibkr_ped']['connected']}")
print(f"IBKR_GUN: {status['ibkr_gun']['connected']}")
print(f"HAMMER_PRO: {status['hammer_pro']['connected']}")
```

### Reconnecting Failed Account
If a connection fails, it will NOT auto-reconnect. Restart the application to retry all connections.

## Future Enhancements

### Possible Additions
1. **Auto-reconnect**: Detect disconnections and auto-reconnect
2. **Health monitoring**: Periodic connection health checks
3. **Multi-account trading**: Execute orders across multiple accounts simultaneously
4. **Connection pooling**: Reuse connections more efficiently

### Not Planned
- Manual connect/disconnect buttons (connections are persistent)
- Per-account market data sources (always HAMMER PRO)
- Account-specific trading engines (engines are account-agnostic)

## Summary

Phase 11 introduces **persistent dual connections** to all trading accounts:
- ✅ All accounts connect on startup
- ✅ Connections remain active throughout application lifecycle
- ✅ Mode switching is instant (only Redis flags change)
- ✅ No disconnections during mode switch
- ✅ Simplified architecture with better reliability

This provides a more robust and performant foundation for multi-account trading operations.
