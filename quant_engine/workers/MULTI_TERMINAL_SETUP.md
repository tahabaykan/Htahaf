# Multi-Terminal Setup Guide

## Overview

This guide explains how to run multiple terminals/processes for the Quant Engine application, enabling parallel processing and data flow between different components.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TERMINAL 1                                │
│              Main FastAPI Application                        │
│  - API Server (Port 8000)                                    │
│  - WebSocket Server                                          │
│  - Order Management                                          │
│  - Market Data Feed                                          │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ HTTP/WebSocket
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                    TERMINAL 2                                 │
│           Deeper Analysis Worker #1                          │
│  - Processes GOD/ROD/GRPAN jobs                              │
│  - Reads from Redis queue                                    │
│  - Writes results to Redis                                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ Redis (Docker)
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                    TERMINAL 3 (Optional)                     │
│           Deeper Analysis Worker #2                          │
│  - Additional worker for load distribution                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ Redis (Docker)
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                    TERMINAL 4 (Optional)                     │
│              Custom Analysis Script                          │
│  - Reads results from Redis                                  │
│  - Performs custom analysis                                  │
│  - Can write back to Redis                                   │
└─────────────────────────────────────────────────────────────┘
```

## Step-by-Step Setup

### Step 1: Start Redis (One-time)

Redis should auto-start with `baslat.py`, but verify:

```bash
docker ps | grep redis
```

If not running:
```bash
docker start redis-quant-engine
```

### Step 2: Terminal 1 - Main Application

**Open Terminal 1** and run:

```bash
cd quant_engine
python baslat.py
```

**What it does:**
- Starts FastAPI server on port 8000
- Handles all HTTP API requests
- Manages WebSocket connections
- Processes orders (non-blocking)
- Serves frontend

**Keep this terminal open** - this is your main application.

### Step 3: Terminal 2 - Deeper Analysis Worker

**Open Terminal 2** and run:

**Windows:**
```bash
cd quant_engine
set WORKER_NAME=worker1
workers\start_worker.bat
```

**Linux/Mac:**
```bash
cd quant_engine
export WORKER_NAME=worker1
./workers/start_worker.sh
```

**What it does:**
- Connects to Redis
- Polls for deeper analysis jobs
- Processes GOD/ROD/GRPAN computations
- Writes results back to Redis
- **Does NOT block Terminal 1**

### Step 4: Terminal 3 - Additional Worker (Optional)

For load distribution, you can run multiple workers:

**Open Terminal 3** and run:

**Windows:**
```bash
cd quant_engine
set WORKER_NAME=worker2
python workers\run_deeper_worker.py
```

**Linux/Mac:**
```bash
cd quant_engine
export WORKER_NAME=worker2
python workers/run_deeper_worker.py
```

### Step 5: Terminal 4 - Custom Script (Optional)

You can create custom scripts that read/write to Redis:

**Example: `custom_analysis.py`**
```python
import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Read a job result
job_id = "your-job-id"
result = r.get(f"deeper_analysis:result:{job_id}")
if result:
    data = json.loads(result)
    print(f"Processed {data['processed_count']} symbols")
    
    # Access analysis data
    for symbol, analysis in data['data'].items():
        print(f"{symbol}: GOD={analysis.get('god')}, ROD={analysis.get('rod')}")
```

## Data Flow Between Terminals

### Example: Frontend Requests Deeper Analysis

1. **Terminal 1 (FastAPI)** receives `POST /api/deeper-analysis/compute`
2. **Terminal 1** creates job and adds to Redis queue
3. **Terminal 1** returns immediately with `job_id` (non-blocking)
4. **Terminal 2 (Worker)** picks up job from Redis queue
5. **Terminal 2** processes job (computes GOD/ROD/GRPAN)
6. **Terminal 2** saves results to Redis
7. **Terminal 1** serves results when frontend polls for status

### Example: Custom Script Reads Results

1. **Terminal 4 (Custom Script)** reads from Redis:
   ```python
   result = r.get(f"deeper_analysis:result:{job_id}")
   ```
2. **Terminal 4** processes the data
3. **Terminal 4** can write back to Redis for other processes

## Verifying Setup

### Check All Processes

**Terminal 1 (FastAPI):**
- Should show: `INFO: Uvicorn running on http://0.0.0.0:8000`
- Should show: `🚀 Quant Engine API starting up...`

**Terminal 2 (Worker):**
- Should show: `✅ Worker worker1 connected to Redis`
- Should show: `🚀 Worker worker1 started`

**Redis:**
```bash
docker exec -it redis-quant-engine redis-cli PING
# Should return: PONG
```

### Test Job Submission

1. Open frontend: `http://localhost:3000`
2. Navigate to "Deeper Analysis" page
3. Click "Refresh" or enable deeper analysis
4. Check Terminal 2 - should show job processing

## Benefits of Multi-Terminal Architecture

### ✅ Non-Blocking Operations
- Main application (Terminal 1) never blocks
- Orders can be placed while analysis runs
- WebSocket stays responsive

### ✅ Scalability
- Add more workers (Terminal 3, 4, etc.) as needed
- Workers share the same queue
- Automatic load distribution

### ✅ Flexibility
- Custom scripts can read/write to Redis
- Different processes can work with same data
- Easy to add new analysis types

### ✅ Fault Tolerance
- If one worker crashes, others continue
- Jobs are persisted in Redis
- No data loss

## Common Scenarios

### Scenario 1: Heavy Analysis During Trading Hours

**Setup:**
- Terminal 1: FastAPI (orders, market data)
- Terminal 2: Worker (deeper analysis)
- Terminal 3: Worker (backup/load distribution)

**Result:** Orders are never blocked, analysis runs in background.

### Scenario 2: Custom Analysis Pipeline

**Setup:**
- Terminal 1: FastAPI
- Terminal 2: Worker (GOD/ROD/GRPAN)
- Terminal 4: Custom script (reads results, performs additional analysis)

**Result:** Custom analysis can use worker results without blocking main app.

### Scenario 3: Multiple Analysis Types

**Setup:**
- Terminal 1: FastAPI
- Terminal 2: Worker (deeper analysis)
- Terminal 3: Custom worker (different analysis type)
- Terminal 4: Monitoring script

**Result:** Different analysis types run in parallel, all share Redis.

## Troubleshooting

### Worker Not Connecting to Redis

1. Check Redis is running:
   ```bash
   docker ps | grep redis
   ```

2. Check Redis connection in worker logs:
   - Should show: `✅ Worker connected to Redis`
   - If error: Check `REDIS_HOST` and `REDIS_PORT` in settings

### Jobs Not Processing

1. Check worker is running (Terminal 2)
2. Check Redis queue:
   ```bash
   docker exec -it redis-quant-engine redis-cli LLEN deeper_analysis:jobs
   ```
3. Check worker logs for errors

### Multiple Workers Not Sharing Load

- Ensure each worker has unique `WORKER_NAME`
- Workers automatically share the same queue
- Jobs are distributed by Redis (FIFO)

## Next Steps

1. ✅ Start Terminal 1 (FastAPI)
2. ✅ Start Terminal 2 (Worker)
3. ✅ Test job submission from frontend
4. ✅ Monitor logs in both terminals
5. ✅ Add Terminal 3 (optional, for load distribution)
6. ✅ Create custom scripts (optional, for custom analysis)

## Summary

- **Terminal 1**: Main application (FastAPI) - handles orders, API, WebSocket
- **Terminal 2+**: Worker processes - handle heavy computations
- **Redis**: Message broker and data store - connects all processes
- **Custom Scripts**: Can read/write to Redis - flexible integration

This architecture ensures your trading application stays responsive while performing heavy analysis in the background.
