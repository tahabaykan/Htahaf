"""
Redis Key Constants — Single Source of Truth
=============================================

All Redis keys used across quant_engine are documented here.
Each constant includes:
    - Key pattern (with any dynamic segments)
    - Data format (JSON / plain string / hash)
    - Writers (which modules SET this key)
    - Readers (which modules GET this key)

MIGRATION: Existing code still uses raw string literals.
New code should import from this module. Old code should be migrated
gradually to use these constants.

Usage:
    from app.core.redis_keys import RedisKeys
    redis_sync.get(RedisKeys.XNL_RUNNING)
"""


class RedisKeys:
    """
    Central registry of all Redis key names used across the system.

    Naming Convention:
        psfalgo:{domain}:{sub_key}
    """

    # =========================================================================
    # XNL ENGINE STATE
    # =========================================================================

    # Whether XNL Engine is currently running ("1" or "0", plain string)
    # Writers: xnl_engine.start(), xnl_engine.stop(), dual_process_runner._publish_state_to_redis()
    # Readers: revnbookcheck._is_xnl_running()
    XNL_RUNNING = "psfalgo:xnl:running"

    # Which account XNL Engine is currently running for (plain string: "HAMPRO" / "IBKR_PED" / "IBKR_GUN")
    # Writers: xnl_engine.start(), xnl_engine.stop(), dual_process_runner._publish_state_to_redis()
    # Readers: revnbookcheck._xnl_running_account()
    XNL_RUNNING_ACCOUNT = "psfalgo:xnl:running_account"

    # =========================================================================
    # DUAL PROCESS STATE
    # =========================================================================

    # Full Dual Process state (JSON: {state, accounts, current_account, loop_count, started_at})
    # Writers: dual_process_runner._publish_state_to_redis()
    # Readers: revnbookcheck._is_dual_process_running(), revnbookcheck._get_active_account_from_redis()
    # TTL: 3600 seconds
    DUAL_PROCESS_STATE = "psfalgo:dual_process:state"

    # =========================================================================
    # ACTIVE ACCOUNT IDENTIFICATION
    # These 4 keys all answer "which account is active?" but in different formats.
    # Priority order for reading (RevnBookCheck):
    #   1. RECOVERY_ACCOUNT_OPEN (most reliable — set by Connect API)
    #   2. XNL_RUNNING_ACCOUNT (set by XNL Engine when running)
    #   3. ACCOUNT_MODE (fallback — JSON format)
    # =========================================================================

    # Account opened via Connect API or recovery (plain string: "HAMPRO" / "IBKR_PED" / "IBKR_GUN")
    # Writers: dual_process_runner, account_mode, main.py startup, psfalgo_routes
    # Readers: revnbookcheck, rev_recovery_service, main.py periodic_refresh
    RECOVERY_ACCOUNT_OPEN = "psfalgo:recovery:account_open"

    # General account mode (JSON: {"mode": "HAMMER_PRO" / "IBKR_GUN" / "IBKR_PED"})
    # Writers: dual_process_runner, account_mode, main.py startup
    # Readers: revnbookcheck (priority 3), main.py periodic_refresh
    ACCOUNT_MODE = "psfalgo:account_mode"

    # Trading context account mode (plain string: "HAMPRO" / "IBKR_PED" / "IBKR_GUN")
    # Writers: dual_process_runner, main.py startup
    # Readers: TradingAccountContext
    TRADING_ACCOUNT_MODE = "psfalgo:trading:account_mode"

    # =========================================================================
    # POSITIONS & ORDERS
    # =========================================================================

    # Open orders for an account (JSON list)
    # Key pattern: psfalgo:open_orders:{account_id}
    # Writers: ibkr_connector.place_order(), position_redis_worker
    # Readers: revnbookcheck._get_open_orders(), frontlama_engine
    @staticmethod
    def open_orders(account_id: str) -> str:
        return f"psfalgo:open_orders:{account_id}"

    # Position snapshot for an account (JSON list)
    # Key pattern: psfalgo:positions:{account_id}
    # Writers: position_redis_worker, position_snapshot_api
    # Readers: revnbookcheck, dual_account_rev_service
    @staticmethod
    def positions(account_id: str) -> str:
        return f"psfalgo:positions:{account_id}"

    # BEFDAY positions for an account (JSON list)
    # Key pattern: psfalgo:befday:positions:{account_id}
    # Writers: befday_tracker.track_positions(), main.py startup
    # Readers: befday_data_service, revnbookcheck
    # TTL: 86400 seconds (1 day)
    @staticmethod
    def befday_positions(account_id: str) -> str:
        return f"psfalgo:befday:positions:{account_id}"

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    # L1 market data for a symbol (JSON: {bid, ask, spread, last})
    # Key pattern: market:l1:{symbol}
    # Writers: truth_ticks_worker L1 feed loop
    # Readers: revnbookcheck._get_l1_data(), data_fabric.get_live()
    @staticmethod
    def market_l1(symbol: str) -> str:
        return f"market:l1:{symbol}"

    # Live market data for a symbol (JSON: {bid, ask, last, volume, timestamp})
    # Key pattern: live:{symbol}
    # Writers: hammer_feed, truth_ticks_worker
    # Readers: data_fabric.get_live() (Redis fallback)
    @staticmethod
    def live(symbol: str) -> str:
        return f"live:{symbol}"

    # Market data snapshot for a symbol (JSON)
    # Key pattern: market_data:snapshot:{symbol}
    # Writers: position_redis_worker
    # Readers: data_fabric.get_live() (second fallback)
    @staticmethod
    def market_snapshot(symbol: str) -> str:
        return f"market_data:snapshot:{symbol}"

    # =========================================================================
    # FILL EVENTS (Redis Streams)
    # =========================================================================

    # Fill events stream for an account
    # Key pattern: psfalgo:fill_events:{account_id}
    # Writers: ibkr_connector._register_fill_recovery(), hammer_execution_service
    # Readers: revnbookcheck._subscribe_fill_events()
    @staticmethod
    def fill_events(account_id: str) -> str:
        return f"psfalgo:fill_events:{account_id}"

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    # Heavy mode settings per account (JSON)
    # Key pattern: psfalgo:heavy_settings:{account_id}
    # Writers: psfalgo_routes heavy-settings endpoint
    # Readers: karbotu_engine
    @staticmethod
    def heavy_settings(account_id: str) -> str:
        return f"psfalgo:heavy_settings:{account_id}"

    # AddNewPos settings per account (JSON)
    # Key pattern: psfalgo:addnewpos_settings:{account_id}
    # Writers: xnl_routes addnewpos settings endpoint
    # Readers: addnewpos_engine
    @staticmethod
    def addnewpos_settings(account_id: str) -> str:
        return f"psfalgo:addnewpos_settings:{account_id}"

    # =========================================================================
    # TRUTH TICKS
    # =========================================================================

    # Raw truth tick array (JSON list of {ts, price, size, exch})
    # Key pattern: tt:ticks:{symbol}
    # Writers: TruthTicksEngine.persist_to_redis()
    # Readers: MetricsCollector, Frontlama, XNL Engine, GemEngine (fallback)
    # TTL: 12 days (covers 2 weekends + buffer)
    # *** CANONICAL SOURCE — always available ***
    @staticmethod
    def tt_ticks(symbol: str) -> str:
        return f"tt:ticks:{symbol}"

    # Rich truth tick analysis data (JSON: {success, symbol, data: {path_dataset, volav_levels, temporal_analysis, ...}})
    # Key pattern: truth_ticks:inspect:{symbol}
    # Writers: TruthTicksWorker.process_job()
    # Readers: GemEngine._get_truth_price_raw(), GenObs, GreatestMM
    # TTL: 3600s (1 hour) — EXPIRES when worker not running
    @staticmethod
    def truth_ticks_inspect(symbol: str) -> str:
        return f"truth_ticks:inspect:{symbol}"

    # Latest truth tick snapshot (JSON: {price, ts, updated_at, size, venue, exch})
    # Key pattern: truthtick:latest:{symbol}
    # Writers: TruthTicksWorker.process_job()
    # Readers: (legacy) Frontlama, XNL Engine — now fallback only
    # TTL: 600s (10 min) — EXPIRES when worker not running
    @staticmethod
    def truthtick_latest(symbol: str) -> str:
        return f"truthtick:latest:{symbol}"

    # =========================================================================
    # EXPOSURE
    # =========================================================================

    # Exposure snapshot for an account (JSON: {pot_total, pot_max, ...})
    # Key pattern: psfalgo:exposure:{account_id}
    # Writers: XNL Engine (TODO: needs to be implemented)
    # Readers: Frontlama._get_current_exposure_pct(), MetricsCollector
    @staticmethod
    def exposure(account_id: str) -> str:
        return f"psfalgo:exposure:{account_id}"

    # =========================================================================
    # QAGENTT STATE
    # =========================================================================

    # QAGENTT agent state (JSON)
    # Key pattern: qagentt:state
    # Writers: LearningAgent
    # Readers: MetricsCollector, API
    QAGENTT_STATE = "qagentt:state"

