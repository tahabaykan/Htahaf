# Deeper Analysis Worker

## Overview

The Deeper Analysis Worker processes CPU/IO-heavy computations (GOD, ROD, GRPAN) in a **separate process** to avoid blocking the main FastAPI application. This allows you to:

- ✅ Place orders while deeper analysis runs
- ✅ Keep the main application responsive
- ✅ Run multiple workers for load distribution
- ✅ Scale horizontally as needed

## Architecture

```
┌─────────────────┐
│   Frontend      │
│   (React)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   FastAPI       │  ← Main Application (Terminal 1)
│   (Port 8000)   │     - Handles orders
└────────┬────────┘     - Market data
         │              - WebSocket
         │ POST /api/deeper-analysis/compute
         ▼
┌─────────────────┐
│     Redis       │  ← Message Broker (Docker)
│   (Port 6379)   │     - Job Queue
└────────┬────────┘     - Results Cache
         │
         │ BRPOP (blocking pop)
         ▼
┌─────────────────┐
│  Worker Process │  ← Separate Terminal (Terminal 2+)
│  (Background)   │     - Processes jobs
└─────────────────┘     - Computes GOD/ROD/GRPAN
```

## Quick Start

### 1. Start Redis (if not running)

Redis should auto-start with `baslat.py`, but if needed:

```bash
docker start redis-quant-engine
```

### 2. Start Main Application (Terminal 1)

```bash
cd quant_engine
python baslat.py
# Or: python main.py api
```

### 3. Start Worker (Terminal 2)

**Windows:**
```bash
cd quant_engine
workers\start_worker.bat
```

**Linux/Mac:**
```bash
cd quant_engine
chmod +x workers/start_worker.sh
./workers/start_worker.sh
```

**Or directly:**
```bash
python workers/run_deeper_worker.py
```

## Multi-Terminal Setup

### Recommended Setup (3-4 Terminals)

#### Terminal 1: Main FastAPI Application
```bash
cd quant_engine
python baslat.py
```
**Purpose:** Handles all API requests, WebSocket, order placement

#### Terminal 2: Deeper Analysis Worker #1
```bash
cd quant_engine
set WORKER_NAME=worker1
workers\start_worker.bat
```
**Purpose:** Processes deeper analysis jobs

#### Terminal 3: Deeper Analysis Worker #2 (Optional)
```bash
cd quant_engine
set WORKER_NAME=worker2
workers\start_worker.bat
```
**Purpose:** Additional worker for load distribution

#### Terminal 4: Redis Monitor (Optional)
```bash
docker exec -it redis-quant-engine redis-cli
# Then: MONITOR
```
**Purpose:** Monitor Redis activity

### Environment Variables

You can customize worker behavior:

```bash
# Windows
set WORKER_NAME=worker1
set POLL_TIMEOUT=5
set MAX_JOB_TIME=300
python workers\run_deeper_worker.py

# Linux/Mac
export WORKER_NAME=worker1
export POLL_TIMEOUT=5
export MAX_JOB_TIME=300
python workers/run_deeper_worker.py
```

**Variables:**
- `WORKER_NAME`: Unique identifier for this worker (default: `worker_{pid}`)
- `POLL_TIMEOUT`: Seconds to wait for jobs (default: 5)
- `MAX_JOB_TIME`: Maximum seconds per job (default: 300)

## How It Works

### 1. Job Submission
- Frontend calls `POST /api/deeper-analysis/compute`
- FastAPI creates a job and adds it to Redis queue
- Returns immediately with `job_id`

### 2. Job Processing
- Worker polls Redis queue (blocking pop)
- Picks up job when available
- Computes GOD, ROD, GRPAN for all symbols
- Saves results to Redis

### 3. Status Polling
- Frontend polls `GET /api/deeper-analysis/status/{job_id}`
- Gets status: `queued` → `processing` → `completed` or `failed`

### 4. Result Retrieval
- When status is `completed`, frontend calls `GET /api/deeper-analysis/result/{job_id}`
- Gets computed results from Redis

## Data Flow

```
Frontend → FastAPI → Redis Queue
                          ↓
                    Worker Process
                          ↓
                    Redis Results
                          ↓
                    FastAPI → Frontend
```

## Monitoring

### Check Worker Status

Worker logs show:
- ✅ Job processing start/completion
- ❌ Errors
- 📊 Statistics (processed/failed counts)

### Check Redis Queue

```bash
docker exec -it redis-quant-engine redis-cli
> LLEN deeper_analysis:jobs
> KEYS deeper_analysis:*
```

### Check Job Status (via API)

```bash
curl http://localhost:8000/api/deeper-analysis/status/{job_id}
```

## Troubleshooting

### Worker Not Processing Jobs

1. **Check Redis connection:**
   ```bash
   docker ps | grep redis
   ```

2. **Check worker logs:**
   - Look for "✅ Worker connected to Redis"
   - Check for connection errors

3. **Verify queue:**
   ```bash
   docker exec -it redis-quant-engine redis-cli LLEN deeper_analysis:jobs
   ```

### Jobs Stuck in Queue

- Check if workers are running
- Check worker logs for errors
- Restart workers if needed

### Redis Connection Failed

- Ensure Redis Docker container is running:
  ```bash
  docker start redis-quant-engine
  ```
- Check Redis host/port in `settings.py`

## Scaling

### Run Multiple Workers

You can run multiple workers simultaneously for load distribution:

```bash
# Terminal 2
set WORKER_NAME=worker1
python workers\run_deeper_worker.py

# Terminal 3
set WORKER_NAME=worker2
python workers\run_deeper_worker.py

# Terminal 4
set WORKER_NAME=worker3
python workers\run_deeper_worker.py
```

Each worker will:
- Process jobs independently
- Share the same Redis queue
- Distribute load automatically

## Integration with Other Processes

The worker architecture allows other processes to:

1. **Submit jobs** via FastAPI or directly to Redis
2. **Read results** from Redis (any process with Redis access)
3. **Monitor status** via FastAPI endpoints

Example: Another Python script can read results:

```python
import redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
result = r.get('deeper_analysis:result:{job_id}')
```

## Notes

- ⚠️ **Worker must have access to DataFabric**: Ensure tick-by-tick data is enabled
- ⚠️ **Results expire**: Results stored for 2 hours, status for 1 hour
- ⚠️ **Graceful shutdown**: Workers handle SIGINT/SIGTERM for clean shutdown
