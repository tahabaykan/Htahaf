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
    decision_helper_v2_router = None

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
    from app.api.static_files import router as static_files_router
except ImportError as e:
    logger.warning(f"Could not import static_files_router: {e}")
    static_files_router = None

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
if truth_ticks_router:
    app.include_router(truth_ticks_router)
if aura_mm_router:
    app.include_router(aura_mm_router)
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

    # Initialize MetricsSnapshotAPI & ExposureCalculator (Critical for Decision Engines)
    # MUST BE AFTER Market Data Services (dependencies) but BEFORE RunallEngine
    try:
        from app.psfalgo.metrics_snapshot_api import initialize_metrics_snapshot_api
        from app.psfalgo.exposure_calculator import initialize_exposure_calculator
        from app.psfalgo.grpan_engine import get_grpan_engine
        from app.psfalgo.rwvap_engine import get_rwvap_engine
        from app.psfalgo.pricing_overlay_engine import get_pricing_overlay_engine
        from app.psfalgo.janall_metrics_engine import get_janall_metrics_engine
        from app.market_data.static_data_store import get_static_store
        from app.api.market_data_routes import market_data_cache
        
        # Initialize ExposureCalculator
        initialize_exposure_calculator()
        logger.info("✅ ExposureCalculator initialized")
        
        # Initialize MetricsSnapshotAPI (aggregates everything)
        initialize_metrics_snapshot_api(
            market_data_cache=market_data_cache,
            static_store=get_static_store(),
            grpan_engine=get_grpan_engine(),
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
        
        # Initialize Engine
        initialize_runall_engine()
        runall_engine = get_runall_engine()
        
        # Initialize State API
        initialize_runall_state_api(runall_engine)
        logger.info("✅ Runall Engine & State API initialized")
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


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Quant Engine API shutting down...")
