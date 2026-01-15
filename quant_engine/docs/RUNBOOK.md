# Quant Engine - Runbook

Operational guide for starting, stopping, and troubleshooting the Quant Engine system.

## Quick Start

### Windows (Single Command)

```powershell
.\run.ps1
```

This will:
- Start backend in a new terminal window
- Start frontend in a new terminal window
- Print all URLs and endpoints

### Manual Start

**Backend:**
```powershell
cd quant_engine
python main.py api
```

**Frontend:**
```powershell
cd quant_engine\frontend
npm run dev
```

## Ports

- **Backend API**: `http://localhost:8000`
- **Frontend UI**: `http://localhost:3000`
- **WebSocket**: `ws://localhost:8000/ws`
- **Redis** (optional): `localhost:6379`

## Verification

### 1. Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "time": "2024-01-01T12:00:00",
  "version": "0.1.0",
  "service": "quant_engine"
}
```

### 2. Status Check

```bash
curl http://localhost:8000/api/status
```

Expected response:
```json
{
  "backend": "ok",
  "websocket_clients": 0,
  "symbols_loaded": 0,
  "last_update_ts": null,
  "hammer_connected": false,
  "redis_connected": false,
  "csv_loaded": false,
  "csv_row_count": 0,
  "timestamp": "2024-01-01T12:00:00"
}
```

### 3. UI Verification

1. Open browser: `http://localhost:3000`
2. Click "Load CSV" button
3. Verify table shows data
4. Check WebSocket connection indicator (should show "Connected")

## Configuration

### Auto-Load CSV on Startup

Set in `.env` file or environment variable:

```bash
AUTO_LOAD_CSV=true
```

If enabled, `janalldata.csv` will be loaded automatically when backend starts.

### Redis (Optional)

Redis is **optional**. If Redis is not running:
- Backend will use in-memory cache
- Warning will be logged (not an error)
- System will continue to work normally

To use Redis:
1. Start Redis server
2. Backend will automatically connect
3. Status endpoint will show `redis_connected: true`

## Troubleshooting

### Port Already in Use

**Error:** `Address already in use` or `Port 8000 is in use`

**Solution:**
1. Find process using the port:
   ```powershell
   netstat -ano | findstr :8000
   ```
2. Kill the process:
   ```powershell
   taskkill /PID <process_id> /F
   ```
3. Or change port in `.env`:
   ```
   API_PORT=8001
   ```

### npm / node not found

**Error:** `'npm' is not recognized` or `'node' is not recognized`

**Solution:**
1. Install Node.js from https://nodejs.org/
2. Add to PATH:
   - Open System Properties → Environment Variables
   - Add `C:\Program Files\nodejs\` to PATH
3. Restart terminal/PowerShell

### Python not found

**Error:** `'python' is not recognized`

**Solution:**
1. Install Python from https://www.python.org/
2. During installation, check "Add Python to PATH"
3. Or manually add Python to PATH
4. Restart terminal/PowerShell

### Redis Connection Failed

**Error:** `Redis connection failed` (warning, not error)

**Solution:**
- This is **normal** if Redis is not running
- Backend will use in-memory cache
- To use Redis:
  1. Install Redis: https://redis.io/download
  2. Start Redis server
  3. Backend will auto-connect

### CSV Not Loading

**Error:** CSV file not found or empty

**Solution:**
1. Verify `janalldata.csv` exists in `quant_engine/` directory
2. Check file permissions
3. Use manual load endpoint:
   ```bash
   curl -X POST http://localhost:8000/api/market-data/load-csv
   ```
4. Check status endpoint for `csv_loaded` and `csv_row_count`

### Frontend Not Connecting to Backend

**Error:** WebSocket disconnected or API calls failing

**Solution:**
1. Verify backend is running: `http://localhost:8000/health`
2. Check CORS settings (should allow all origins in dev)
3. Verify WebSocket endpoint: `ws://localhost:8000/ws`
4. Check browser console for errors

### Python Virtual Environment

**Recommended:** Use virtual environment

```powershell
# Create venv
python -m venv venv

# Activate (Windows)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Missing Python Packages

**Error:** `ModuleNotFoundError: No module named 'X'`

**Solution:**
```powershell
cd quant_engine
pip install -r requirements.txt
```

## Stopping Services

1. **Backend**: Press `Ctrl+C` in backend terminal window
2. **Frontend**: Press `Ctrl+C` in frontend terminal window
3. **Or**: Close the terminal windows

## Logs

Backend logs are printed to console. For production, configure logging in `app/core/logger.py`.

## Environment Variables

Create `.env` file in `quant_engine/` directory:

```env
# API
API_HOST=0.0.0.0
API_PORT=8000

# Redis (optional)
REDIS_HOST=localhost
REDIS_PORT=6379

# Auto-load CSV
AUTO_LOAD_CSV=false

# Hammer Pro
HAMMER_HOST=127.0.0.1
HAMMER_PORT=16400
```

## Next Steps

After system is running:
1. Load CSV data (if not auto-loaded)
2. Connect Hammer Pro for live market data
3. Monitor status endpoint for system health
4. Use UI to inspect symbol states and reasons








