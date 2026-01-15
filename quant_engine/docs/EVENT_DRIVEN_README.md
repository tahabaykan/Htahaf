# Event-Driven Trading System - Sprint 1

## Overview

Production-grade, event-driven algorithmic trading system with latency tolerance of ~2-15 seconds. This is the Sprint 1 skeleton implementation focusing on robust contracts, clean separation of responsibilities, idempotency, and an event-driven state machine.

## Architecture

See [EVENT_DRIVEN_ARCHITECTURE.md](./EVENT_DRIVEN_ARCHITECTURE.md) for detailed architecture documentation.

### Key Components

1. **Workers (Terminals)**: Produce events
   - Exposure Worker: Publishes exposure snapshots every 15s
   - Session Worker: Publishes session clock every 1s
   - Market Data Worker: (Sprint 2) Hammer/IBKR feed adapter
   - Alerts Worker: (Sprint 2) Alerts producer
   - Prints Worker: (Sprint 2) GRPAN/dominant price

2. **Decision Engine (Brain)**: Consumes all events, maintains state, produces Intents
   - Consumes: ev.exposure, ev.session
   - Produces: ev.intents
   - Applies risk rules from `risk_rules.yaml`

3. **Execution Service**: The ONLY component that talks to broker (IBKR)
   - Consumes: ev.intents
   - Produces: ev.orders
   - Owns order lifecycle: place, cancel, replace, track fills

### Communication

- **Redis Streams** (NOT PubSub) for durability and replayability
- **Consumer Groups** for reliable processing
- **Redis Hashes** for latest state
- **Event Contracts** with JSON schemas and idempotency keys

## Quick Start

### Prerequisites

- Python 3.8+
- Redis (via Docker)
- Dependencies installed: `pip install -r requirements.txt`

### 1. Start Redis

```bash
# Using docker-compose
cd quant_engine
docker-compose up -d redis

# Or manually
docker run -d -p 6379:6379 --name redis-quant-engine redis:latest
```

### 2. Run Workers

Open separate terminals for each component:

**Terminal 1: Exposure Worker**
```bash
cd quant_engine
python workers/run_exposure_worker.py
```

**Terminal 2: Session Worker**
```bash
cd quant_engine
python workers/run_session_worker.py
```

**Terminal 3: Decision Engine**
```bash
cd quant_engine
python workers/run_decision_engine.py
```

**Terminal 4: Execution Service**
```bash
cd quant_engine
python workers/run_execution_service.py
```

### 3. Monitor Events

You can monitor Redis streams using `redis-cli`:

```bash
# Monitor exposure events
redis-cli XREAD COUNT 10 STREAMS ev.exposure 0

# Monitor session events
redis-cli XREAD COUNT 10 STREAMS ev.session 0

# Monitor intents
redis-cli XREAD COUNT 10 STREAMS ev.intents 0

# Monitor orders
redis-cli XREAD COUNT 10 STREAMS ev.orders 0
```

## Event Streams

All events are published to Redis Streams with the naming convention `ev.{stream_name}`:

- `ev.exposure` - Exposure snapshots (15s cadence)
- `ev.session` - Session clock (1s cadence)
- `ev.intents` - Trading intents from Decision Engine
- `ev.orders` - Order updates from Execution Service

### Event Structure

All events follow this structure:

```json
{
  "event_id": "uuid",
  "event_type": "exposure|session|intent|order",
  "timestamp": 1234567890000000000,
  "idempotency_key": "uuid",
  "data": {
    // Event-specific payload
  }
}
```

## Risk Rules

Risk rules are configured in `app/config/risk_rules.yaml`:

- **Gross Exposure**: HARD CAP 130%, soft limit 120%
- **Buckets**: LT (target 80%, max 90%), MM_PURE (target 20%, max 30%)
- **Time Regimes**: OPEN, EARLY, MID, LATE, CLOSE
- **De-risk Playbook**:
  - After 16:15 US: SOFT_DERISK (truth tick proximity)
  - At 16:28 US: HARD_DERISK (aggressive reduction to <= 100%)

## State Management

### Latest State (Redis Hashes)

- `state:exposure` - Latest exposure snapshot
- `state:session` - Latest session state
- `state:orders` - Latest order state (Sprint 2)

### Event Log (Redis Streams)

All events are logged to streams for replayability and audit.

## Adding a New Worker

1. Create worker class in `app/event_driven/workers/`:

```python
from app.event_driven.state.event_log import EventLog
from app.event_driven.contracts.events import YourEvent

class YourWorker:
    def __init__(self):
        self.event_log = EventLog()
    
    def publish_event(self):
        event = YourEvent.create(...)
        self.event_log.publish("your_stream", event)
```

2. Create entry point in `workers/run_your_worker.py`:

```python
from app.event_driven.workers.your_worker import main
if __name__ == "__main__":
    main()
```

3. Add event contract in `app/event_driven/contracts/events.py`

## Testing Event Flows

### Test Exposure → Decision Engine → Execution Service

1. Start all components
2. Exposure Worker publishes exposure events every 15s
3. Decision Engine consumes exposure events
4. If exposure exceeds limits, Decision Engine generates intents
5. Execution Service consumes intents and logs actions

### Test Session → Decision Engine

1. Start Session Worker and Decision Engine
2. Session Worker publishes session events every 1s
3. Decision Engine consumes session events
4. At 16:15, if exposure > soft limit, Decision Engine generates SOFT_DERISK intent
5. At 16:28, if exposure > 100%, Decision Engine generates HARD_DERISK intent

### Monitor with Redis CLI

```bash
# Watch exposure stream
redis-cli --raw XREAD COUNT 1 BLOCK 1000 STREAMS ev.exposure $

# Watch intents stream
redis-cli --raw XREAD COUNT 1 BLOCK 1000 STREAMS ev.intents $

# Check latest state
redis-cli HGETALL state:exposure
redis-cli HGETALL state:session
```

## Risk & Order Lifecycle Test Rig (Upgraded)

The system has been upgraded to a realistic "Risk & Order Lifecycle Test Rig". See [RISK_ORDER_LIFECYCLE_UPGRADE.md](./RISK_ORDER_LIFECYCLE_UPGRADE.md) for details.

### Key Upgrades

1. **Full Exposure Breakdown**: Gross exposure, long/short percentages, bucket exposure (current/potential), per-group exposure
2. **Policy Decision Table**: Deterministic decision logic (NORMAL, THROTTLE, SOFT_DERISK, HARD_DERISK)
3. **Deterministic Order Lifecycle**: Order registry, idempotency, fill simulation
4. **Scenario Runner**: Testing harness with 5 test scenarios
5. **8-Way Order Classification**: Strict classification system (MM/LT × LONG/SHORT × INCREASE/DECREASE)
6. **LT Band Drift Controller**: Gentle corrective intents for LT band violations
7. **Daily Ledger/Reporting**: Aggregates fills by classification, generates EOD reports (JSON/CSV)
8. **BefDay Snapshot & Dual-Ledger**: Separates overnight baseline from intraday trading, accurate intraday P&L calculation
9. **Intraday PnL Tracking**: Realized PnL calculated only from closing intraday-opened positions (not baseline)
10. **LiquidityGuard**: Pre-trade sizing constraints to prevent order spam and respect market liquidity

### Running Scenario Runner

```bash
# Terminal 1: Start Decision Engine
python workers/run_decision_engine.py

# Terminal 2: Run scenarios
python workers/run_scenario_runner.py
```

### Running Ledger Consumer

```bash
# Terminal 1: Start Execution Service (generates fills)
python workers/run_execution_service.py

# Terminal 2: Start Ledger Consumer (records fills)
python workers/run_ledger_consumer.py

# Terminal 3: Generate report
python workers/run_report_generator.py

# Generate dual-ledger report (Baseline + Intraday)
python workers/run_report_generator.py --dual HAMMER
```

### Running BefDay Snapshot

```bash
# Create daily baseline snapshot for HAMMER account
python workers/run_befday_snapshot.py HAMMER

# Create snapshot for IBKR_GUN account
python workers/run_befday_snapshot.py IBKR_GUN

# Create snapshot for IBKR_PED account
python workers/run_befday_snapshot.py IBKR_PED
```

**See also:** 
- [BefDay & Dual-Ledger System](BEFDAY_DUAL_LEDGER_SYSTEM.md)
- [PnL Calculation Fix & LiquidityGuard](PNL_LIQUIDITYGUARD_FIXES.md)

## Sprint 1 Limitations (Still Apply)

- **Mock Data**: Exposure Worker uses mock position data
- **Stub Execution**: Execution Service simulates fills but doesn't execute real orders
- **Simple Derisk**: Basic strategy (reduce largest position)
- **No Real Broker**: IBKR integration stubbed
- **No GRPAN**: Prints/features computation stubbed

## Next Steps (Sprint 2)

1. **Real Broker Execution**
   - Implement IBKR adapter in Execution Service
   - Real order placement, cancellation, replacement
   - Fill callbacks → ev.orders events

2. **Open Orders Tracking**
   - Track open orders in Redis
   - Handle order lifecycle: pending → filled/cancelled
   - Potential exposure calculation (worst-case if all orders fill)

3. **Market Data Ingestion**
   - Hammer/IBKR feed adapter
   - L1 market data → ev.l1
   - Trade prints → ev.prints

4. **GRPAN Math**
   - Implement GRPAN/dominant price computation
   - Features → ev.features
   - Truth tick proximity for derisk

5. **Alerts System**
   - Alerts worker
   - ev.alerts stream

6. **Enhanced Derisk**
   - Truth tick proximity for SOFT_DERISK
   - Dominant print zones for reduction
   - Chunked reduction (10% per step)

## Troubleshooting

### Redis Connection Failed

- Check Redis is running: `docker ps | grep redis`
- Check Redis port: `redis-cli ping`
- Verify `REDIS_HOST` and `REDIS_PORT` in settings

### Events Not Flowing

- Check consumer groups: `redis-cli XINFO GROUPS ev.exposure`
- Check stream length: `redis-cli XLEN ev.exposure`
- Check worker logs for errors

### Decision Engine Not Generating Intents

- Check exposure state: `redis-cli HGETALL state:exposure`
- Check session state: `redis-cli HGETALL state:session`
- Verify risk rules loaded (check logs)
- Check if exposure exceeds limits

## Development

### Code Structure

```
app/event_driven/
├── contracts/          # Event schemas
├── workers/            # Event producers
├── decision_engine/   # Decision Engine (Brain)
├── execution/         # Execution Service
└── state/             # State store abstraction
```

### Logging

All components use structured logging via `app.core.logger`. Logs include:
- Component name
- Event IDs
- State changes
- Errors with stack traces

### Idempotency

All events include `idempotency_key` for deduplication. Processing the same event twice produces the same result.

## Support

For questions or issues, refer to:
- [EVENT_DRIVEN_ARCHITECTURE.md](./EVENT_DRIVEN_ARCHITECTURE.md) - Architecture details
- [risk_rules.yaml](../app/config/risk_rules.yaml) - Risk configuration
- Component logs - Detailed runtime information

