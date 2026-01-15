"""
FastAPI Main Application
=======================

Main FastAPI app with all routers and middleware configured.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import json

from app.core.logger import logger
from app.config.settings import settings

# Import all routers
try:
    from app.api.market_data_routes import router as market_data_router
except ImportError as e:
    logger.warning(f"Could not import market_data_router: {e}")
    market_data_router = None

try:
    from app.api.websocket_routes import router as websocket_router
except ImportError as e:
    logger.warning(f"Could not import websocket_router: {e}")
    websocket_router = None

try:
    from app.api.data_fabric_routes import router as data_fabric_router
except ImportError as e:
    logger.warning(f"Could not import data_fabric_router: {e}")
    data_fabric_router = None

try:
    from app.api.trading_routes import router as trading_router
except ImportError as e:
    logger.warning(f"Could not import trading_router: {e}")
    trading_router = None

try:
    from app.api.intent_routes import router as intent_router
except ImportError as e:
    logger.warning(f"Could not import intent_router: {e}")
    intent_router = None

try:
    from app.api.psfalgo_routes import router as psfalgo_router
except ImportError as e:
    logger.warning(f"Could not import psfalgo_router: {e}")
    psfalgo_router = None

try:
    from app.api.jfin_routes import router as jfin_router
except ImportError as e:
    logger.warning(f"Could not import jfin_router: {e}")
    jfin_router = None

try:
    from app.port_adjuster.port_adjuster_routes import router as port_adjuster_router
except ImportError as e:
    logger.warning(f"Could not import port_adjuster_router: {e}")
    port_adjuster_router = None

try:
    from app.api.log_routes import router as log_router
except ImportError as e:
    logger.warning(f"Could not import log_router: {e}")
    log_router = None

try:
    from app.api.ticker_alert_routes import router as ticker_alert_router
except ImportError as e:
    logger.warning(f"Could not import ticker_alert_router: {e}")
    ticker_alert_router = None

try:
    from app.api.scanner_filter_routes import router as scanner_filter_router
except ImportError as e:
    logger.warning(f"Could not import scanner_filter_router: {e}")
    scanner_filter_router = None

try:
    from app.api.deeper_analysis_routes import router as deeper_analysis_router
except ImportError as e:
    logger.warning(f"Could not import deeper_analysis_router: {e}")
    deeper_analysis_router = None

try:
    from app.api.decision_helper_routes import router as decision_helper_router
except ImportError as e:
    logger.warning(f"Could not import decision_helper_router: {e}")
    decision_helper_router = None

try:
    from app.api.decision_helper_v2_routes import router as decision_helper_v2_router
except ImportError as e:
    logger.warning(f"Could not import decision_helper_v2_router: {e}")
    from app.api.decision_helper_v2_routes import router as decision_helper_v2_router
except ImportError as e:
    logger.warning(f"Could not import decision_helper_v2_router: {e}")
    decision_helper_v2_router = None

try:
    from app.api.genobs_routes import router as genobs_router
except ImportError as e:
    logger.warning(f"Could not import genobs_router: {e}")
    genobs_router = None

try:
    from app.api.truth_ticks_routes import router as truth_ticks_router
except Exception as e:
    logger.warning(f"Could not import truth_ticks_router: {e}")
    truth_ticks_router = None

try:
    from app.api.aura_mm_routes import router as aura_mm_router
except Exception as e:
    logger.warning(f"Could not import aura_mm_router: {e}")
    aura_mm_router = None

try:
    from app.api.qebench_routes import router as qebench_router
except Exception as e:
    logger.warning(f"Could not import qebench_router: {e}")
    qebench_router = None


try:
    from app.api.static_files import router as static_files_router
except ImportError as e:
    logger.warning(f"Could not import static_files_router: {e}")
    static_files_router = None

try:
    from app.api.security_routes import router as security_router
except ImportError as e:
    logger.warning(f"Could not import security_router: {e}")
    security_router = None

try:
    from app.api.sidehit_press_routes import router as sidehit_press_router
except Exception as e:
    logger.warning(f"Could not import sidehit_press_router: {e}")
    sidehit_press_router = None

try:
    from app.api.greatest_mm_routes import router as greatest_mm_router
except Exception as e:
    logger.warning(f"Could not import greatest_mm_router: {e}")
    greatest_mm_router = None

try:
    from app.api.befday_routes import router as befday_router
except Exception as e:
    logger.warning(f"Could not import befday_router: {e}")
    befday_router = None

try:
    from app.api.intracon_routes import router as intracon_router
except Exception as e:
    logger.warning(f"Could not import intracon_router: {e}")
    intracon_router = None

try:
    from app.api.gem_routes import router as gem_routes_router
except Exception as e:
    logger.warning(f"Could not import gem_routes_router: {e}")
    gem_routes_router = None

try:
    from app.api.benchmark_routes import router as benchmark_routes_router
except Exception as e:
    logger.warning(f"Could not import benchmark_routes_router: {e}")
    benchmark_routes_router = None

try:
    from app.api.system_routes import router as system_router
except Exception as e:
    logger.warning(f"Could not import system_router: {e}")
    system_router = None

try:
    from app.api.janall_routes import router as janall_router
except Exception as e:
    with open("import_error.log", "w") as f:
        f.write(f"Janall Import Error: {e}")
    logger.warning(f"Could not import janall_router: {e}")
    janall_router = None

# Create FastAPI app
app = FastAPI(
    title="Quant Engine API",
    description="Trading engine backend API",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers (only if imported successfully)
if market_data_router:
    app.include_router(market_data_router)
if websocket_router:
    app.include_router(websocket_router)
if data_fabric_router:
    app.include_router(data_fabric_router)
if trading_router:
    app.include_router(trading_router)
if intent_router:
    app.include_router(intent_router)
if psfalgo_router:
    app.include_router(psfalgo_router)
if jfin_router:
    app.include_router(jfin_router)
if port_adjuster_router:
    app.include_router(port_adjuster_router)
if log_router:
    app.include_router(log_router)
if ticker_alert_router:
    app.include_router(ticker_alert_router)
if scanner_filter_router:
    app.include_router(scanner_filter_router)
if deeper_analysis_router:
    app.include_router(deeper_analysis_router)
if decision_helper_router:
    app.include_router(decision_helper_router)
if decision_helper_v2_router:
    app.include_router(decision_helper_v2_router)
if genobs_router:
    app.include_router(genobs_router)
if truth_ticks_router:
    app.include_router(truth_ticks_router)
if aura_mm_router:
    app.include_router(aura_mm_router)
if sidehit_press_router:
    app.include_router(sidehit_press_router)
if greatest_mm_router:
    app.include_router(greatest_mm_router)
if security_router:
    app.include_router(security_router)
if befday_router:
    app.include_router(befday_router)
if intracon_router:
    app.include_router(intracon_router)
if gem_routes_router:
    app.include_router(gem_routes_router)
if benchmark_routes_router:
    app.include_router(benchmark_routes_router)
if janall_router:
    app.include_router(janall_router)
if qebench_router:
    app.include_router(qebench_router)
if system_router:
    app.include_router(system_router)
# IMPORTANT: static_files_router must be LAST because it has catch-all route
if static_files_router:
    app.include_router(static_files_router)



@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Quant Engine API",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "quant-engine-api"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    # Show detail only if log level is DEBUG
    show_detail = settings.LOG_LEVEL.upper() == "DEBUG"
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if show_detail else "An error occurred"
        }
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("🚀 Quant Engine API starting up...")
    logger.info(f"   Host: {settings.API_HOST}")
    logger.info(f"   Port: {settings.API_PORT}")
    logger.info(f"   Log Level: {settings.LOG_LEVEL}")
    
    # =========================================================================
    # PHASE 1: Initialize SecurityContext Architecture (FIRST!)
    # These are the foundation - other services depend on them
    # =========================================================================
    try:
        from app.core.symbol_resolver import initialize_symbol_resolver, get_symbol_resolver
        from app.core.security_registry import initialize_security_registry, get_security_registry
        from app.core.benchmark_store import initialize_benchmark_store, get_benchmark_store
        
        # 1. Initialize SymbolResolver
        initialize_symbol_resolver()
        resolver = get_symbol_resolver()
        
        # 2. Initialize SecurityRegistry
        initialize_security_registry()
        registry = get_security_registry()
        
        # 3. Initialize BenchmarkStore
        initialize_benchmark_store()
        benchmark_store = get_benchmark_store()
        
        logger.info("✅ SecurityContext Architecture initialized (Resolver + Registry + BenchmarkStore)")
        
        # NOTE: Symbol registration moved to AFTER initialize_market_data_services()
        # This ensures static_store is loaded before we register symbols
        
        # 5. Load ETF prev_closes from janeketfs.csv
        try:
            from pathlib import Path
            import pandas as pd
            
            etf_csv_paths = [
                # PRIORITY: Local
                Path(os.getcwd()) / 'janall' / 'janeketfs.csv',
                Path(os.getcwd()) / 'janeketfs.csv',
                
                # Fallbacks
                Path(r"C:\StockTracker\janall") / 'janeketfs.csv',
                Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall") / 'janeketfs.csv',
            ]
            
            for etf_path in etf_csv_paths:
                if etf_path.exists():
                    etf_df = pd.read_csv(etf_path)
                    for _, row in etf_df.iterrows():
                        symbol = str(row.get('symbol', row.get('Symbol', ''))).strip()
                        prev_close = row.get('prev_close', row.get('PrevClose', None))
                        if symbol and prev_close:
                            benchmark_store.set_prev_close(symbol, float(prev_close))
                    logger.info(f"✅ Loaded ETF prev_closes from {etf_path.name}")
                    break
        except Exception as e:
            logger.warning(f"⚠️ Could not load ETF prev_closes: {e}")
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize SecurityContext Architecture: {e}", exc_info=True)
    
    # =========================================================================
    # PHASE 2: Initialize Hammer Connection
    # =========================================================================
    
    # Initialize Hammer feed (for live market data)
    try:
        from app.live.hammer_client import HammerClient
        from app.live.hammer_feed import HammerFeed
        from app.api.market_data_routes import set_hammer_feed
        
        # Check if Hammer password is configured
        if settings.HAMMER_PASSWORD:
            logger.info("🔌 Connecting to Hammer Pro for live market data...")
            
            hammer_client = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD,
                account_key=settings.HAMMER_ACCOUNT_KEY
            )
            
            # Connect in background (non-blocking)
            def connect_hammer():
                try:
                    if hammer_client.connect():
                        # Wait for authentication
                        import time
                        auth_timeout = 10
                        auth_start = time.time()
                        while not hammer_client.authenticated and (time.time() - auth_start) < auth_timeout:
                            time.sleep(0.1)
                        
                        if hammer_client.authenticated:
                            hammer_feed = HammerFeed(hammer_client)
                            set_hammer_feed(hammer_feed)
                            logger.info("✅ Hammer feed initialized and connected")
                            
                            # Initialize Hammer Execution Services (Positions/Orders)
                            from app.api.trading_routes import set_hammer_services
                            set_hammer_services(hammer_client, settings.HAMMER_ACCOUNT_KEY)
                            
                            # Initialize Hammer Execution Service (Order Placement)
                            from app.trading.hammer_execution_service import set_hammer_execution_service
                            set_hammer_execution_service(hammer_client, settings.HAMMER_ACCOUNT_KEY)
                            
                            logger.info("✅ Hammer execution services initialized")

                            # --- BEFDAY TRACKING FOR HAMPRO (User Request) ---
                            try:
                                import asyncio
                                from app.psfalgo.befday_tracker import get_befday_tracker, initialize_befday_tracker
                                from app.api.trading_routes import get_hammer_positions_service
                                
                                # Run in separate safe block to not crash connection
                                def run_befday_check():
                                    try:
                                        tracker = get_befday_tracker()
                                        if not tracker:
                                            tracker = initialize_befday_tracker()
                                        
                                        should_track, reason = tracker.should_track('hampro')
                                        if should_track:
                                            logger.info(f"[BEFDAY] Need snapshot for HAMPRO ({reason})...")
                                            pos_service = get_hammer_positions_service()
                                            if pos_service:
                                                # Hammer positions are sync usually
                                                positions = pos_service.get_positions(force_refresh=True)
                                                if positions:
                                                    # Run async tracker in new event loop for this thread
                                                    asyncio.run(tracker.track_positions(positions, 'hampro', 'HAMPRO'))
                                                    logger.info("[BEFDAY] ✅ HAMPRO Snapshot created (befham.csv)")
                                                else:
                                                    logger.warning("[BEFDAY] No HAMPRO positions found. Snapshot skipped.")
                                    except Exception as be:
                                        logger.error(f"[BEFDAY] HAMPRO Auto-track error: {be}")

                                run_befday_check()

                            except Exception as e:
                                logger.error(f"[BEFDAY] Error initiating HAMPRO check: {e}")

                        else:
                            logger.warning("⚠️ Hammer client connected but authentication timeout")
                    else:
                        logger.warning("⚠️ Failed to connect to Hammer Pro - live market data will not be available")
                except Exception as e:
                    logger.warning(f"⚠️ Error connecting to Hammer Pro: {e}")
            
            # Start connection in background thread
            import threading
            hammer_thread = threading.Thread(target=connect_hammer, daemon=True)
            hammer_thread.start()
        else:
            logger.warning("⚠️ HAMMER_PASSWORD not configured - live market data will not be available")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize Hammer feed: {e}")
    
    # Initialize AccountModeManager (must be before market data services)
    try:
        from app.psfalgo.account_mode import initialize_account_mode_manager
        initialize_account_mode_manager(initial_mode="HAMMER_PRO")
        logger.info("✅ AccountModeManager initialized")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize AccountModeManager: {e}")

    # Initialize Hammer Services (Empty) & PositionSnapshotAPI
    # This ensures RunallEngine can access position services even before Hammer connects
    try:
        from app.api.trading_routes import set_hammer_services, get_hammer_positions_service
        from app.psfalgo.position_snapshot_api import initialize_position_snapshot_api
        from app.market_data.static_data_store import get_static_store
        from app.api.market_data_routes import market_data_cache
        
        # 1. Pre-initialize services (so they exist for referencing)
        set_hammer_services() 
        hammer_positions_service = get_hammer_positions_service()
        
        # 2. Initialize PositionSnapshotAPI
        static_store = get_static_store()
        initialize_position_snapshot_api(
            position_manager=hammer_positions_service,
            static_store=static_store,
            market_data_cache=market_data_cache
        )
        logger.info("✅ PositionSnapshotAPI initialized (with HammerPositionsService)")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize PositionSnapshotAPI: {e}")

    # Initialize market data services (loads CSV, initializes engines)
    try:
        from app.api.market_data_routes import initialize_market_data_services
        initialize_market_data_services()
        logger.info("✅ Market data services initialized")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize market data services: {e}")

    # =========================================================================
    # PHASE 2.5: Register Symbols AFTER Static Data is Loaded
    # This must happen after initialize_market_data_services() which loads CSV
    # =========================================================================
    try:
        from app.core.symbol_resolver import get_symbol_resolver
        from app.core.security_registry import get_security_registry
        from app.market_data.static_data_store import get_static_store
        
        resolver = get_symbol_resolver()
        registry = get_security_registry()
        static_store = get_static_store()
        
        if resolver and registry and static_store and static_store.loaded:
            registered_count = 0
            for pref_ibkr, static_data in static_store.data.items():
                # Normalize symbol
                pref_ibkr = pref_ibkr.strip()
                
                # Register the symbol in resolver
                resolver.register_pref(pref_ibkr)
                
                # Create SecurityContext and populate static data
                ctx = registry.get_or_create(pref_ibkr)
                if ctx:
                    ctx.update_static(
                        final_thg=static_data.get('FINAL_THG'),
                        short_final=static_data.get('SHORT_FINAL'),
                        avg_adv=static_data.get('AVG_ADV'),
                        group=static_data.get('GROUP'),
                        cmon=static_data.get('CMON'),
                        cgrup=static_data.get('CGRUP'),
                        maxalw=static_data.get('MAXALW', 2000),
                        prev_close=static_data.get('prev_close'),
                        sma63_chg=static_data.get('SMA63 chg'),
                        sma246_chg=static_data.get('SMA246 chg')
                    )
                    registered_count += 1
            
            logger.info(f"✅ Registered {registered_count} symbols in SecurityRegistry from static data")
        else:
            logger.warning("⚠️ Could not register symbols - resolver, registry, or static_store not available")
    except Exception as e:
        logger.error(f"❌ Failed to register symbols: {e}", exc_info=True)

    # Initialize MetricsSnapshotAPI & ExposureCalculator (Critical for Decision Engines)
    # MUST BE AFTER Market Data Services (dependencies) but BEFORE RunallEngine
    try:
        from app.psfalgo.metrics_snapshot_api import initialize_metrics_snapshot_api
        from app.psfalgo.exposure_calculator import initialize_exposure_calculator
        # from app.psfalgo.grpan_engine import get_grpan_engine # REMOVED: File missing
        from app.market_data.rwvap_engine import get_rwvap_engine
        from app.market_data.pricing_overlay_engine import get_pricing_overlay_engine
        from app.market_data.janall_metrics_engine import get_janall_metrics_engine
        from app.market_data.static_data_store import get_static_store
        from app.api.market_data_routes import market_data_cache
        
        # Initialize ExposureCalculator
        initialize_exposure_calculator()
        logger.info("✅ ExposureCalculator initialized")
        
        # Initialize MetricsSnapshotAPI (aggregates everything)
        initialize_metrics_snapshot_api(
            market_data_cache=market_data_cache,
            static_store=get_static_store(),

            rwvap_engine=get_rwvap_engine(),
            pricing_overlay_engine=get_pricing_overlay_engine(),
            janall_metrics_engine=get_janall_metrics_engine()
        )
        logger.info("✅ MetricsSnapshotAPI initialized")
        
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize Metrics/Exposure APIs: {e}")

    # Initialize Runall Engine & State API (Core Logic)
    try:
        from app.psfalgo.runall_engine import get_runall_engine, initialize_runall_engine
        from app.psfalgo.runall_state_api import initialize_runall_state_api
        from app.psfalgo.proposal_engine import initialize_proposal_engine
        from app.psfalgo.proposal_store import initialize_proposal_store
        
        # Initialize Proposal Engine & Store (MUST BE BEFORE Runall Engine)
        initialize_proposal_engine()
        initialize_proposal_store()
        logger.info("✅ Proposal Engine & Store initialized")
        
        # Initialize Engine
        initialize_runall_engine()
        runall_engine = get_runall_engine()
        
        # Initialize State API
        initialize_runall_state_api(runall_engine)
        logger.info("✅ Runall Engine & State API initialized")

        # Auto-start Runall Engine
        if runall_engine:
            logger.info("Auto-starting Runall Engine...")
            await runall_engine.start()

    except Exception as e:
        logger.warning(f"⚠️ Could not initialize Runall Engine: {e}")
    
    # Start Redis pub/sub listener for ticker alerts
    try:
        from app.api.websocket_routes import connection_manager
        asyncio.create_task(start_ticker_alert_listener(connection_manager))
        logger.info("✅ Ticker alert Redis listener started")
    except Exception as e:
        logger.warning(f"⚠️ Could not start ticker alert listener: {e}")
    
    # Start automatic deeper analysis job scheduler (15 minutes)
    try:
        asyncio.create_task(start_auto_deeper_analysis_scheduler())
        logger.info("✅ Auto deeper analysis scheduler started (15 min interval)")
    except Exception as e:
        logger.warning(f"⚠️ Could not start auto deeper analysis scheduler: {e}")


async def start_auto_deeper_analysis_scheduler():
    """Start automatic deeper analysis job scheduler (15 minutes interval)"""
    import uuid
    import json
    
    # Wait 1 minute before first job (let system stabilize)
    await asyncio.sleep(60)
    
    while True:
        try:
            from app.core.redis_client import get_redis_client
            from app.api.deeper_analysis_routes import JOB_QUEUE_KEY, JOB_STATUS_PREFIX
            
            redis_client = get_redis_client()
            if not redis_client:
                logger.warning("⚠️ Redis not available, skipping auto deeper analysis job")
                await asyncio.sleep(900)  # Wait 15 minutes before retry
                continue
            
            redis = redis_client.sync
            if not redis:
                logger.warning("⚠️ Redis sync client not available")
                await asyncio.sleep(900)
                continue
            
            # Generate job ID
            job_id = str(uuid.uuid4())
            
            # Create job payload
            job_data = {
                "job_id": job_id,
                "status": "queued",
                "created_at": str(uuid.uuid1().time),
                "symbols": None  # None = all symbols
            }
            
            # Add to Redis queue
            redis.lpush(JOB_QUEUE_KEY, json.dumps(job_data))
            
            # Set initial status
            redis.setex(
                f"{JOB_STATUS_PREFIX}{job_id}",
                3600,  # 1 hour TTL
                json.dumps({"status": "queued", "message": "Auto-scheduled job queued"})
            )
            
            logger.info(f"📊 Auto deeper analysis job queued: {job_id} (15 min scheduler)")
            
        except Exception as e:
            logger.error(f"❌ Error in auto deeper analysis scheduler: {e}", exc_info=True)
        
        # Wait 15 minutes (900 seconds) before next job
        await asyncio.sleep(900)


async def start_ticker_alert_listener(connection_manager):
    """Start Redis pub/sub listener for ticker alerts"""
    try:
        from app.core.redis_client import get_redis_client
        
        redis_client = get_redis_client()
        if not redis_client:
            logger.warning("⚠️ Redis client not available, ticker alerts will not be forwarded")
            return
        
        # Get async client
        async_redis = await redis_client.async_client()
        pubsub = async_redis.pubsub()
        await pubsub.subscribe("ticker_alerts:events")
        
        logger.info("✅ Subscribed to ticker_alerts:events channel")
        
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get('type') == 'message':
                    alert_data = json.loads(message['data'])
                    await connection_manager.broadcast_ticker_alert(alert_data)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing ticker alert: {e}", exc_info=True)
                await asyncio.sleep(1)
                
    except ImportError:
        logger.warning("⚠️ redis.asyncio not available, ticker alerts will not be forwarded")
    except Exception as e:
        logger.error(f"Error starting ticker alert listener: {e}", exc_info=True)


    # Initialize Janall Order Mechanisms (Bulk Logic + Native IBKR)
    try:
        from app.api.janall_routes import router as janall_router, set_janall_dependencies
        from app.algo.janall_bulk_manager import JanallBulkOrderManager
        from app.ibkr.ib_native_connector import IBNativeConnector
        from app.live.hammer_feed import get_hammer_feed  # Reuse existing feed for market data
        
        # 1. Initialize Native Client (STRICT LEGACY MODE)
        # User Rule: Always use Port 4001 (Real Gateway), even for PED account.
        # User Rule: "ASLA PAPER PORTU KULLANMIYORUM"
        # Match Legacy Janall Client ID (1)
        
        target_port = settings.IBKR_PORT # Default 4001
        logger.info(f"🔌 Initializing IBKR Native Connector on STRICT PORT {target_port} (Client ID: 1)...")
        
        native_client = IBNativeConnector(host=settings.IBKR_HOST, port=target_port, client_id=1)
        
        try:
            if native_client.connect_client():
                logger.info(f"✅ IB Native Connected on Port {target_port}")
            else:
                logger.warning(f"⚠️ IB Native Connection Failed on Port {target_port}")
        except Exception as e:
            logger.warning(f"⚠️ IB Native Connection Error: {e}")
        
        # 2. Market Data Adapter (Reuse Hammer Feed if available)
        class HammerFeedAdapter:
            def __init__(self):
                pass
            def get_market_data(self, ticker):
                # Fetch fresh data from backend cache
                try:
                    from app.api.market_data_routes import market_data_cache
                    from app.live.symbol_mapper import SymbolMapper
                    
                    # 1. Try direct lookup (e.g. CIM PRB)
                    data = market_data_cache.get(ticker)
                    
                    # 2. Try Display mapping (e.g. CIM-B -> CIM PRB)
                    if not data:
                        disp = SymbolMapper.to_display_symbol(ticker)
                        data = market_data_cache.get(disp)
                    
                    # 3. Try Hammer mapping (e.g. CIM PRB -> CIM-B) - rare but possible
                    if not data:
                        ham = SymbolMapper.to_hammer_symbol(ticker)
                        data = market_data_cache.get(ham) 
                        
                    if data:
                        return {
                            'bid': float(data.get('bid') or 0.0),
                            'ask': float(data.get('ask') or 0.0),
                            'last': float(data.get('last') or 0.0)
                        }
                except Exception:
                    pass
                return {'bid':0.0, 'ask':0.0, 'last':0.0}

        md_adapter = HammerFeedAdapter() # Use real adapter in production
        
        # 3. Initialize Manager
        janall_manager = JanallBulkOrderManager(native_client, md_adapter)
        
        # 4. Set Dependencies
        set_janall_dependencies(janall_manager, native_client)
        
        logger.info("✅ Janall Order Mechanisms initialized")
        
    except Exception as e:
        logger.error(f"❌ Critical Error initializing Janall Mechanisms: {e}", exc_info=True)
        # Fallback: Initialize with Dummy/None to allow API to start
        try:
             from app.api.janall_routes import set_janall_dependencies
             set_janall_dependencies(None, None)
        except: pass

    # Shutdown event
    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown"""
        logger.info("🛑 Quant Engine API shutting down...")
        if 'native_client' in locals() and native_client:
            try:
                native_client.disconnect()
                logger.info("IBKR Native disconnected")
            except: pass
