# Windows AsyncIO Shutdown Error Fix

## Problem Summary

When shutting down the FastAPI/Uvicorn application on Windows, the following error chain occurred:

```
OSError: [WinError 995] Bir iş parçacığı çıkışı veya bir uygulama isteği nedeniyle G/Ç işlemi iptal edildi
↓
ConnectionResetError: [WinError 995] ...
↓
asyncio.exceptions.InvalidStateError: invalid state
↓
AttributeError: 'NoneType' object has no attribute 'send'
```

## Root Cause

This is a **known Windows-specific issue** with Python's `ProactorEventLoop`:

1. **WinError 995**: I/O operation aborted due to thread/application exit
2. **InvalidStateError**: Event loop futures entered invalid state during cleanup
3. **NoneType.send**: The event loop's proactor was set to `None` during shutdown before all connections were cleaned up

This occurs because:
- Windows uses `ProactorEventLoop` (different from Unix's `SelectorEventLoop`)
- During shutdown, pending I/O operations are cancelled
- The cancellation triggers `ConnectionResetError` which propagates to the event loop
- The event loop tries to handle the error but its internal state is already being torn down

## Solution Implemented

### 1. Windows-Specific Error Suppression (`main.py`)

Added monkey-patching to suppress WinError 995 during shutdown:

```python
if platform.system() == "Windows":
    import asyncio.windows_events
    original_poll = asyncio.windows_events.IocpProactor._poll
    
    def patched_poll(self, timeout=None):
        try:
            return original_poll(self, timeout)
        except (ConnectionResetError, OSError) as e:
            if e.winerror == 995:
                return []  # Suppress during shutdown
            raise
    
    asyncio.windows_events.IocpProactor._poll = patched_poll
```

### 2. Graceful Exception Handling

Wrapped `uvicorn.run()` with try-except to catch and suppress `InvalidStateError`:

```python
try:
    uvicorn.run(app, ...)
except KeyboardInterrupt:
    logger.info("API server stopped by user")
except Exception as e:
    if "invalid state" not in str(e).lower():
        logger.error(f"API server error: {e}", exc_info=True)
    else:
        logger.info("API server shutdown complete")
```

### 3. Proper Shutdown Handler (`app/api/main.py`)

**Fixed**: Moved shutdown event handler from inside `startup_event()` to module level:

```python
# BEFORE (WRONG): Nested inside startup_event
@app.on_event("startup")
async def startup_event():
    ...
    @app.on_event("shutdown")  # ❌ This never gets registered!
    async def shutdown_event():
        ...

# AFTER (CORRECT): Module level
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    # Disconnect Hammer
    # Disconnect IBKR
    # Stop workers
    ...
```

**Enhanced cleanup**:
- Disconnect Hammer client
- Disconnect all IBKR connections (via `DualConnectionManager`)
- Disconnect native IBKR client
- Stop background workers (Position Redis Worker, Order Queue Worker)

## Testing

To verify the fix:

1. **Start the backend**:
   ```bash
   cd C:\StockTracker\quant_engine
   python baslat.py
   ```

2. **Stop with Ctrl+C**:
   - Should see clean shutdown logs
   - No `InvalidStateError` or `WinError 995` errors
   - All connections properly closed

## Expected Shutdown Output

```
🛑 Quant Engine API shutting down...
✅ Hammer client disconnected
✅ IBKR connections disconnected
✅ IBKR Native disconnected
✅ Background workers stopped
🛑 Shutdown complete
API server shutdown complete
```

## References

- **Python Issue**: https://bugs.python.org/issue39010
- **Uvicorn Issue**: https://github.com/encode/uvicorn/issues/1579
- **ProactorEventLoop Docs**: https://docs.python.org/3/library/asyncio-platforms.html#windows

## Related Knowledge Items

- **IBKR Integration Master Guide**: Contains event loop troubleshooting patterns
- **Conversation 6f1e0e4c**: Port conflict resolution (related to connection cleanup)
