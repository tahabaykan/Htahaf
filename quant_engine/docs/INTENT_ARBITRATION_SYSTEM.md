# Intent Arbitration System

## Overview

The Intent Arbitration layer resolves conflicts between multiple intents produced by the Decision Engine. It ensures deterministic, priority-based selection of which intents are allowed, merged, suppressed, or delayed before execution.

## Architecture

```
Decision Engine
    ↓ (generates multiple intents)
IntentArbiter
    ↓ (filters, merges, resolves conflicts)
Execution Service
```

## Priority Order (Highest to Lowest)

1. **CAP_RECOVERY** (Priority: 100)
   - Triggered when gross exposure ≥ 130%
   - Suppresses ALL risk-increasing intents (*_INCREASE)
   - Allows only risk-reducing intents
   - Target: reduce to ~123% (configurable)

2. **HARD_DERISK** (Priority: 80)
   - Aggressive risk reduction
   - Suppresses MM churn and LT drift corrective
   - Allows only derisk-related intents

3. **SOFT_DERISK** (Priority: 60)
   - Gentle risk reduction
   - May coexist with LT drift corrective if no conflict
   - Suppresses MM churn if exposure > soft threshold

4. **Risk-Reducing** (Priority: 40)
   - Any intent with effect=DECREASE
   - Includes derisk intents and corrective actions

5. **LT Band Drift Corrective** (Priority: 20)
   - Gentle corrective intents for LT band violations
   - Suppressed during HARD_DERISK

6. **MM Churn** (Priority: 10)
   - Opportunistic market-making intents
   - Lowest priority
   - Suppressed during:
     - CAP_RECOVERY
     - HARD_DERISK
     - When gross exposure > soft threshold

## Core Rules

### 1. CAP_RECOVERY Behavior

**Trigger**: `current_gross_exposure_pct >= 130%`

**Actions**:
- Immediately suppress ALL risk-increasing intents (*_INCREASE)
- Allow only:
  - Risk-reducing intents (*_DECREASE)
  - Quick profit-take opportunities
- Target: reduce to `cap_recovery_target_gross` (default: 123%)
- Not strict 120% - reduce along cheapest path

### 2. SOFT / HARD Derisk Interaction

- **HARD_DERISK** overrides SOFT_DERISK
- **SOFT_DERISK** may coexist with LT drift corrective ONLY if no conflict
- During **HARD_DERISK**:
  - Suppress all MM churn intents
  - Suppress LT drift corrective intents
  - Allow only derisk-related intents

### 3. Symbol-Level Conflict Resolution

For intents on the same symbol:

- **Same direction & effect**: Merge quantities (subject to LiquidityGuard)
- **Conflicting** (e.g., LONG_INCREASE vs LONG_DECREASE):
  - Higher priority intent wins
- **Both risk-reducing**: Choose one with lower expected cost (PnL-aware if available)

### 4. Cross-Symbol Behavior

- CAP_RECOVERY / HARD_DERISK can select multiple symbols
- LT Band Drift intents must never block higher-priority risk actions
- MM churn intents are dropped if they interfere with risk reduction

### 5. MM Churn Rules

- No explicit churn target
- MM churn intents are opportunistic and always lowest priority
- Suppressed during:
  - CAP_RECOVERY
  - HARD_DERISK
  - When `current_gross_exposure_pct > soft_suppress_threshold` (default: 120%)

### 6. Overnight MM Leftover Rule

- MM bucket leftover up to 15% gross is allowed overnight
- If MM leftover > 15%:
  - Next day OPEN/EARLY, generate prioritized MM_DECREASE intents
  - These are still lower priority than CAP_RECOVERY or HARD_DERISK

## Configuration

**File**: `app/config/risk_rules.yaml`

```yaml
intent_arbitration:
  # CAP_RECOVERY target (reduce to this level, not strict 120%)
  cap_recovery_target_gross: 123.0
  
  # MM overnight leftover threshold
  mm_overnight_max_pct: 15.0
  
  # Soft suppress threshold (suppress MM churn above this)
  soft_suppress_threshold: 120.0
```

## Conflict Resolution Table

| Scenario | Intent 1 | Intent 2 | Result |
|----------|----------|----------|--------|
| Same symbol, same direction | LONG_INCREASE (100) | LONG_INCREASE (50) | Merged: 150 |
| Same symbol, conflict | LONG_INCREASE (MM_CHURN) | LONG_DECREASE (SOFT_DERISK) | SOFT_DERISK wins |
| CAP_RECOVERY active | MM_LONG_INCREASE | LT_LONG_DECREASE | MM suppressed, LT passes |
| HARD_DERISK active | MM_CHURN | LT_BAND_CORRECTIVE | Both suppressed |
| SOFT_DERISK + LT drift | SOFT_DERISK (AAPL) | LT_BAND_CORRECTIVE (MSFT) | Both pass (no conflict) |

## Examples

### Example 1: CAP_RECOVERY Suppresses Risk-Increasing

**Input**:
- MM_LONG_INCREASE (AAPL, 100 shares)
- LT_BAND_CORRECTIVE (MSFT, 50 shares, DECREASE)
- CAP_RECOVERY (GOOGL, 200 shares, DECREASE)
- Gross exposure: 131%

**Output**:
- MM_LONG_INCREASE: **Suppressed** (risk-increasing)
- LT_BAND_CORRECTIVE: **Pass** (risk-reducing)
- CAP_RECOVERY: **Pass** (highest priority)

### Example 2: Symbol Conflict Resolution

**Input** (same symbol AAPL):
- MM_LONG_INCREASE (100 shares, priority: 10)
- SOFT_DERISK LONG_DECREASE (50 shares, priority: 60)

**Output**:
- SOFT_DERISK wins (higher priority)
- MM_LONG_INCREASE suppressed

### Example 3: Merge Same Direction

**Input** (same symbol AAPL, both LONG_DECREASE):
- SOFT_DERISK (100 shares)
- HARD_DERISK (50 shares)

**Output**:
- Merged: 150 shares (HARD_DERISK priority, combined quantity)

## Integration

### Decision Engine Flow

1. Decision Engine generates multiple intents:
   - Derisk intents (HARD_DERISK, SOFT_DERISK)
   - LT band drift corrective
   - MM churn (if enabled)
   - CAP_RECOVERY (if gross ≥ 130%)

2. Intents collected in `pending_intents` list

3. `_arbitrate_and_publish_intents()` called:
   - Passes intents to `IntentArbiter.arbitrate()`
   - Receives filtered/merged list
   - Publishes approved intents to `ev.intents` stream

### Execution Service

Execution Service consumes arbitrated intents from `ev.intents` stream. All intents have already been:
- Filtered (suppressed intents removed)
- Merged (same direction/effect combined)
- Resolved (conflicts resolved, higher priority wins)

## Testing

### Run Tests

```bash
python workers/run_intent_arbitration_tests.py
```

### Test Scenarios

1. **CAP_RECOVERY Suppresses All**: MM churn + LT drift + CAP_RECOVERY → only CAP_RECOVERY passes
2. **SOFT_DERISK + LT Drift**: Both allowed if no conflict
3. **HARD_DERISK Suppresses MM**: MM churn suppressed during HARD_DERISK
4. **Symbol Conflict**: Higher priority wins
5. **Merge Same Direction**: Quantities merged
6. **MM Overnight Leftover**: MM_DECREASE generated if >15%

## Determinism

The IntentArbiter is **deterministic**: same input → same output.

- Priority calculation is deterministic
- Conflict resolution is deterministic (higher priority always wins)
- Merging is deterministic (sum quantities, use highest priority metadata)

## Logging

IntentArbiter logs:
- `🚨 [IntentArbiter] CAP_RECOVERY active`: CAP_RECOVERY mode activated
- `🚫 [IntentArbiter] Suppressed MM churn intents`: MM churn suppressed
- `🚫 [IntentArbiter] Suppressed LT drift intents`: LT drift suppressed
- `🔀 [IntentArbiter] Suppressed conflicting intent`: Lower priority intent suppressed
- `💰 [IntentArbiter] Chose cheaper derisk`: Selected lower-cost option
- `✅ [IntentArbiter] Arbitrated N → M intents`: Summary of arbitration

## Files

- `app/event_driven/decision_engine/intent_arbiter.py`: Core arbitration logic
- `app/event_driven/decision_engine/engine.py`: Integration with Decision Engine
- `app/config/risk_rules.yaml`: Configuration
- `app/event_driven/testing/intent_arbitration_tests.py`: Test scenarios

## Next Steps

1. **MM Overnight Leftover Detection**: Add logic to Decision Engine to detect MM leftover >15% at market open
2. **PnL-Aware Selection**: Enhance conflict resolution to use estimated PnL/slippage costs
3. **Delayed Intents**: Support for delaying low-priority intents instead of suppressing
4. **Historical Analysis**: Track arbitration decisions over time



