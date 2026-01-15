# Event-Driven Algorithmic Trading System Architecture

## Overview

Production-grade, event-driven algorithmic trading system with latency tolerance of ~2-15 seconds. Focus on correctness, responsiveness (no UI blocking), and robust order lifecycle management.

## Core Principles

1. **Event-Driven**: All communication via Redis Streams (NOT PubSub) for durability and replayability
2. **Separation of Concerns**: 
   - Workers produce events (market data, alerts, prints, exposure, session)
   - Decision Engine ("Brain") consumes all events, maintains state, produces Intents
   - Execution Service is the ONLY component that talks to broker (IBKR)
3. **Idempotency**: All events have idempotency keys; operations are idempotent
4. **State Management**: Latest state in Redis Hashes; event log in Redis Streams

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        WORKERS (Terminals)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Market Data  │  │   Alerts     │  │   Prints/    │          │
│  │   Worker     │  │   Worker     │  │  Features    │          │
│  │              │  │              │  │   Worker     │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            │                                     │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │  Exposure    │  │   Session    │                            │
│  │   Worker     │  │   Worker     │                            │
│  │  (15s cad.)  │  │  (1s cad.)   │                            │
│  └──────┬───────┘  └──────┬───────┘                            │
└─────────┼──────────────────┼─────────────────────────────────────┘
          │                  │
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    REDIS STREAMS                                 │
│  ev.l1 │ ev.prints │ ev.features │ ev.alerts │ ev.exposure │    │
│  ev.positions │ ev.session │ ev.orders │ ev.intents            │
└─────────────────────────────────────────────────────────────────┘
          │                  │
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                   DECISION ENGINE (Brain)                        │
│  - Consumes ALL events from streams                              │
│  - Maintains latest state (Redis Hashes)                        │
│  - Applies risk rules (risk_rules.yaml)                         │
│  - Produces Intents (ev.intents stream)                          │
│  - State machine: NORMAL → SOFT_DERISK → HARD_DERISK            │
└─────────────────────────────────────────────────────────────────┘
          │
          │ ev.intents
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   EXECUTION SERVICE                              │
│  - ONLY component that talks to IBKR                             │
│  - Consumes ev.intents                                           │
│  - Owns order lifecycle: place, cancel, replace                 │
│  - Tracks open orders, fills                                    │
│  - Publishes ev.orders (order updates, fills)                   │
└─────────────────────────────────────────────────────────────────┘
          │
          │ ev.orders
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    REDIS STREAMS                                 │
│  ev.orders → consumed by Decision Engine (feedback loop)        │
└─────────────────────────────────────────────────────────────────┘
```

## Project Layout

```
quant_engine/
├── app/
│   ├── event_driven/              # NEW: Event-driven system
│   │   ├── __init__.py
│   │   ├── contracts/             # Event schemas
│   │   │   ├── __init__.py
│   │   │   ├── events.py          # Event contract definitions
│   │   │   └── schemas.py         # JSON schemas/validators
│   │   ├── workers/               # Event producers
│   │   │   ├── __init__.py
│   │   │   ├── market_data_worker.py    # Hammer/IBKR feed adapter
│   │   │   ├── alerts_worker.py         # Alerts producer
│   │   │   ├── prints_worker.py         # GRPAN/dominant price
│   │   │   ├── exposure_worker.py      # Exposure snapshots (15s)
│   │   │   └── session_worker.py        # Session clock (1s)
│   │   ├── decision_engine/       # Decision Engine (Brain)
│   │   │   ├── __init__.py
│   │   │   ├── engine.py         # Main decision engine
│   │   │   ├── state_manager.py  # State management (Redis Hashes)
│   │   │   ├── risk_engine.py    # Risk rules engine
│   │   │   └── intent_generator.py # Intent generation
│   │   ├── execution/             # Execution Service
│   │   │   ├── __init__.py
│   │   │   ├── service.py         # Main execution service
│   │   │   ├── order_lifecycle.py # Order lifecycle management
│   │   │   ├── ibkr_adapter.py    # IBKR integration
│   │   │   └── idempotency.py     # Idempotency handling
│   │   └── state/                 # State store abstraction
│   │       ├── __init__.py
│   │       ├── store.py           # Redis Hash wrapper
│   │       └── event_log.py       # Redis Stream wrapper
│   ├── config/
│   │   └── risk_rules.yaml        # Risk rules configuration
│   └── ... (existing modules)
├── workers/                        # Worker entry points
│   ├── run_exposure_worker.py
│   ├── run_session_worker.py
│   ├── run_decision_engine.py
│   └── run_execution_service.py
├── docker-compose.yml
└── README.md
```

## Event Streams

All streams use Redis Streams with Consumer Groups for reliable processing.

### Stream Naming Convention

- `ev.l1` - Level 1 market data (bid/ask updates)
- `ev.prints` - Trade prints
- `ev.features` - GRPAN/dominant price features
- `ev.alerts` - Alerts/notifications
- `ev.positions` - Position updates
- `ev.exposure` - Exposure snapshots (gross exposure, buckets)
- `ev.session` - Session clock (regime, time-to-close)
- `ev.orders` - Order updates (placed, filled, cancelled, replaced)
- `ev.intents` - Trading intents from Decision Engine

### Consumer Groups

- `decision_engine` - Decision Engine consumer group
- `execution_service` - Execution Service consumer group
- `workers` - Worker consumer group (for monitoring/debugging)

## Risk Rules

See `app/config/risk_rules.yaml` for detailed configuration.

### Key Concepts

1. **Gross Exposure**: `(abs(long_notional) + abs(short_notional)) / equity * 100`
   - HARD CAP: Never exceed 130%
2. **Current vs Potential Exposure**:
   - Current: Actual positions
   - Potential: Worst-case if all open orders fill
3. **Buckets**:
   - LT (Long-term portfolio): target ~80%, max ~90%
   - MM_PURE (Market-making): target ~20%, max ~30%
   - Within LT: 10-20% may be "inventory rotation"
4. **Time Regimes** (US market time):
   - OPEN / EARLY / MID / LATE / CLOSE
   - Different tolerances per regime
5. **De-risk Playbook**:
   - After 16:15 US: SOFT_DERISK (truth tick proximity)
   - At 16:28 US: HARD_DERISK (aggressive reduction to <= 100%)

## State Management

### Redis Hashes (Latest State)

- `state:exposure` - Latest exposure snapshot
- `state:positions` - Latest positions
- `state:session` - Latest session state
- `state:orders` - Latest order state (open orders)
- `state:decision` - Decision Engine state

### Redis Streams (Event Log)

All events are logged to streams for replayability and audit.

## Idempotency

All events include:
- `event_id` - Unique event identifier
- `timestamp` - Event timestamp (Unix epoch, nanoseconds)
- `idempotency_key` - For deduplication

Operations are idempotent: processing the same event twice produces the same result.

## Next Steps (Sprint 2+)

1. Real broker execution (IBKR adapter)
2. Open orders tracking
3. Fill handling → ev.orders events
4. GRPAN math implementation
5. Market data ingestion (Hammer/IBKR feed)
6. Alerts system
7. Prints/features computation



