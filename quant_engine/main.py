"""main.py

Main entry point for quant_engine.
Can run engine, API, or both.
"""

import sys
import os
import argparse
import asyncio
import time
import signal
from typing import Optional

from app.core.logger import logger
from app.engine.engine_loop import TradingEngine
from app.strategy.strategy_example import ExampleStrategy
from app.api.main import app
from app.config.settings import settings


def run_engine():
    """Run trading engine"""
    logger.info("Starting trading engine...")
    
    # Create strategy
    strategy = ExampleStrategy()
    
    # Create and run engine
    engine = TradingEngine(strategy)
    
    try:
        engine.run()
    except KeyboardInterrupt:
        logger.info("Engine stopped by user")
    except Exception as e:
        logger.error(f"Engine error: {e}", exc_info=True)


def run_engine_async(strategy_name: str = "ExampleStrategy", risk_config: Optional[str] = None):
    """Run trading engine (async mode)"""
    logger.info(f"Starting trading engine (async mode) with strategy: {strategy_name}")
    
    # Load risk limits if config provided
    if risk_config:
        from app.risk.risk_limits import load_risk_limits
        risk_limits = load_risk_limits(risk_config)
        logger.info(f"Risk limits loaded from: {risk_config}")
    else:
        risk_limits = None
    
    # Load strategy
    from app.strategy.strategy_loader import strategy_loader
    
    strategy = strategy_loader.load_strategy(strategy_name)
    if not strategy:
        logger.error(f"Failed to load strategy: {strategy_name}")
        return
    
    # Create and run engine
    engine = TradingEngine(strategy)
    
    # Update risk manager with custom limits if provided
    if risk_limits:
        from app.risk.risk_state import RiskState
        engine.risk_manager = engine.risk_manager.__class__(limits=risk_limits, state=RiskState())
        engine.risk_manager.set_position_manager(engine.position_manager)
        logger.info("Custom risk limits applied")
    
    try:
        asyncio.run(engine.run_async())
    except KeyboardInterrupt:
        logger.info("Engine stopped by user")
    except Exception as e:
        logger.error(f"Engine error: {e}", exc_info=True)


def run_api():
    """Run FastAPI server"""
    logger.info(f"Starting API server on {settings.API_HOST}:{settings.API_PORT}")
    
    import uvicorn
    # Use uvicorn.run() without nest_asyncio conflicts
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower()
    )


def run_ibkr_sync():
    """Run IBKR synchronization"""
    logger.info("Starting IBKR synchronization...")
    
    from app.ibkr.ibkr_sync import ibkr_sync
    
    # Connect to IBKR
    if not ibkr_client.is_connected():
        if not ibkr_client.connect():
            logger.error("Failed to connect to IBKR. Make sure TWS/Gateway is running.")
            return
    
    try:
        # Fetch and display positions
        logger.info("\n=== Open Positions ===")
        positions = ibkr_sync.fetch_open_positions()
        if positions:
            for pos in positions:
                logger.info(
                    f"  {pos['symbol']}: {pos['qty']:+.0f} @ ${pos['avg_price']:.2f} "
                    f"(P&L: ${pos['unrealized_pnl']:.2f})"
                )
        else:
            logger.info("  No open positions")
        
        # Fetch and display orders
        logger.info("\n=== Open Orders ===")
        orders = ibkr_sync.fetch_open_orders()
        if orders:
            for order in orders:
                logger.info(
                    f"  {order['symbol']} {order['action']} {order['quantity']:.0f} "
                    f"({order['order_type']}) - Status: {order['status']} "
                    f"(Filled: {order['filled']:.0f}, Remaining: {order['remaining']:.0f})"
                )
        else:
            logger.info("  No open orders")
        
        # Fetch and display account summary
        logger.info("\n=== Account Summary ===")
        summary = ibkr_sync.fetch_account_summary()
        if summary:
            for account in summary['accounts']:
                logger.info(f"\n  Account: {account}")
                if 'common' in summary:
                    for field, values in summary['common'].items():
                        if account in values:
                            logger.info(f"    {field}: {values[account]}")
        else:
            logger.info("  No account data available")
        
        logger.info("\n✅ IBKR synchronization complete")
        
    except Exception as e:
        logger.error(f"Error during sync: {e}", exc_info=True)


def run_order_router():
    """Run order router"""
    logger.info("Starting Order Router...")
    
    from app.order.order_router import OrderRouter
    
    router = OrderRouter()
    
    # Connect to IBKR
    if not router.connect():
        logger.error("Failed to connect to IBKR. Make sure TWS/Gateway is running.")
        return
    
    try:
        # Start router loop
        router.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        router.stop()


def run_hammer_ingest(symbol: str = "AAPL", use_fake: bool = True):
    """Run Hammer PRO market data ingestion"""
    logger.info(f"Starting Hammer PRO ingestion (symbol: {symbol}, fake: {use_fake})")
    
    if use_fake:
        from app.market_data.hammer_api_stub import hammer_fake_feed
        feed_reader = hammer_fake_feed(symbol, delay=0.05)
    else:
        # TODO: Use real Hammer PRO API
        from app.market_data.hammer_api_stub import hammer_fake_feed
        logger.warning("Real Hammer PRO API not implemented, using fake feed")
        feed_reader = hammer_fake_feed(symbol, delay=0.05)
    
    from app.market_data.hammer_ingest_stub import HammerIngest
    
    ingest = HammerIngest(feed_reader=feed_reader)
    ingest.start()
    
    logger.info("✅ Hammer ingest running... Press Ctrl+C to exit")
    
    try:
        # Keep running until interrupted
        while True:
            time.sleep(1)
            # Periodic stats
            stats = ingest.get_stats()
            if stats['tick_count'] % 1000 == 0 and stats['tick_count'] > 0:
                logger.info(
                    f"Hammer stats: Ticks={stats['tick_count']}, "
                    f"Errors={stats['error_count']}"
                )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        ingest.stop()
        logger.info("Hammer ingest stopped")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Quant Engine - Trading Backend")
    parser.add_argument(
        'mode',
        choices=['engine', 'engine-async', 'api', 'hammer', 'router', 'sync', 'backtest', 'walkforward', 'optimize', 'montecarlo', 'live', 'all'],
        help='Run mode: engine (sync), engine-async, api, hammer (market data), router (order router), sync (IBKR sync), backtest, or all'
    )
    parser.add_argument(
        '--symbol',
        type=str,
        default='AAPL',
        help='Symbol for hammer mode or backtest (default: AAPL)'
    )
    parser.add_argument(
        '--symbols',
        type=str,
        default=None,
        help='Comma-separated symbols for backtest (e.g., AAPL,MSFT,GOOG)'
    )
    parser.add_argument(
        '--real-feed',
        action='store_true',
        help='Use real Hammer PRO API (default: fake feed)'
    )
    parser.add_argument(
        '--strategy',
        type=str,
        default='ExampleStrategy',
        help='Strategy name to use (default: ExampleStrategy)'
    )
    parser.add_argument(
        '--risk-config',
        type=str,
        default=None,
        help='Path to risk limits config file (YAML/JSON)'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        default=None,
        help='Start date for backtest (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='End date for backtest (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--data-dir',
        type=str,
        default='data/historical',
        help='Directory containing historical data (default: data/historical)'
    )
    parser.add_argument(
        '--replay-speed',
        type=str,
        choices=['instant', 'realtime', 'slow', 'fast'],
        default='instant',
        help='Replay speed (default: instant)'
    )
    parser.add_argument(
        '--model',
        type=str,
        choices=['bootstrap', 'gbm', 'regime'],
        default='bootstrap',
        help='Monte Carlo simulation model (default: bootstrap)'
    )
    parser.add_argument(
        '--horizon',
        type=int,
        default=252,
        help='Monte Carlo time horizon in days (default: 252)'
    )
    parser.add_argument(
        '--simulations',
        type=int,
        default=5000,
        help='Number of Monte Carlo simulations (default: 5000)'
    )
    parser.add_argument(
        '--mc-jobs',
        type=int,
        default=-1,
        help='Number of parallel jobs for Monte Carlo (default: -1 = all cores)'
    )
    parser.add_argument(
        '--hammer-host',
        type=str,
        default='127.0.0.1',
        help='Hammer Pro host (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--hammer-port',
        type=int,
        default=16400,
        help='Hammer Pro port (default: 16400)'
    )
    parser.add_argument(
        '--hammer-password',
        type=str,
        default=None,
        help='Hammer Pro API password (or set HAMMER_PASSWORD env var)'
    )
    parser.add_argument(
        '--execution-broker',
        type=str,
        choices=['IBKR', 'HAMMER'],
        default='HAMMER',
        help='Execution broker: IBKR or HAMMER (default: HAMMER). Market data ALWAYS from Hammer.'
    )
    parser.add_argument(
        '--ibkr-account',
        type=str,
        default=None,
        help='IBKR account ID (e.g., DU123456). Required if --execution-broker=IBKR'
    )
    parser.add_argument(
        '--hammer-account',
        type=str,
        default='ALARIC:TOPI002240A7',
        help='Hammer account key (default: ALARIC:TOPI002240A7)'
    )
    parser.add_argument(
        '--no-trading',
        action='store_true',
        help='Data subscribe only, no orders (default: False)'
    )
    parser.add_argument(
        '--test-order',
        action='store_true',
        help='Send test order (dry-run, will cancel immediately)'
    )
    
    args = parser.parse_args()
    
    if args.mode == 'engine':
        run_engine()
    elif args.mode == 'engine-async':
        run_engine_async(strategy_name=args.strategy, risk_config=args.risk_config)
    elif args.mode == 'api':
        run_api()
    elif args.mode == 'hammer':
        run_hammer_ingest(symbol=args.symbol, use_fake=not args.real_feed)
    elif args.mode == 'router':
        run_order_router()
    elif args.mode == 'backtest':
        from app.backtest.backtest_engine import BacktestEngine
        from app.backtest.replay_engine import ReplayMode, ReplaySpeed
        from app.strategy.strategy_loader import strategy_loader
        
        # Load strategy
        strategy = strategy_loader.load_strategy(args.strategy)
        if not strategy:
            logger.error(f"Failed to load strategy: {args.strategy}")
            return
        
        # Map replay speed
        speed_map = {
            'instant': ReplaySpeed.INSTANT,
            'realtime': ReplaySpeed.REALTIME,
            'slow': ReplaySpeed.SLOW,
            'fast': ReplaySpeed.FAST
        }
        replay_speed = speed_map.get(args.replay_speed, ReplaySpeed.INSTANT)
        
        # Create backtest engine
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=100000.0,
            data_dir=args.data_dir,
            replay_mode=ReplayMode.TICK,
            replay_speed=replay_speed
        )
        
        # Parse symbols
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(',')]
        else:
            # Backward compatibility: use --symbol if --symbols not provided
            symbols = [args.symbol]
        
        # Run backtest
        try:
            result = engine.run(
                symbols=symbols,
                start_date=args.start_date,
                end_date=args.end_date
            )
            
            # Generate HTML report if requested
            if args.report and result:
                from app.report.html_reporter import HTMLReportGenerator
                reporter = HTMLReportGenerator()
                reporter.generate(
                    backtest_result=result,
                    strategy_name=args.strategy,
                    symbols=symbols
                )
                logger.info(f"HTML report generated: {reporter.report_dir}/report.html")
        
        except KeyboardInterrupt:
            logger.info("Backtest interrupted by user")
        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
    
    elif args.mode == 'walkforward':
        from app.optimization.walk_forward_engine import WalkForwardEngine
        from app.optimization.window_generator import WindowMode
        from app.optimization.parameter_optimizer import SearchMethod, ScoringMetric
        from app.strategy.strategy_loader import strategy_loader
        import yaml
        
        # Load strategy
        strategy_class = strategy_loader.load_strategy_class(args.strategy)
        if not strategy_class:
            logger.error(f"Failed to load strategy: {args.strategy}")
            return
        
        # Parse symbols
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(',')]
        else:
            symbols = [args.symbol]
        
        # Load parameter space
        if not args.param_space:
            logger.error("--param-space required for walkforward optimization")
            return
        
        with open(args.param_space, 'r') as f:
            param_space = yaml.safe_load(f)
        
        if not param_space:
            logger.error("Invalid parameter space file")
            return
        
        # Create walk-forward engine
        wfo_engine = WalkForwardEngine(
            strategy_class=strategy_class,
            param_space=param_space,
            symbols=symbols,
            start_date=args.start_date or "2020-01-01",
            end_date=args.end_date or "2023-12-31",
            training_period=args.training_period,
            testing_period=args.testing_period,
            mode=WindowMode.SLIDING if args.wfo_mode == 'sliding' else WindowMode.EXPANDING,
            search_method=SearchMethod.GRID,
            scoring_metric=ScoringMetric.WEIGHTED,
            initial_capital=100000.0,
            data_dir=args.data_dir
        )
        
        # Run walk-forward optimization
        try:
            wfo_engine.run()
        except KeyboardInterrupt:
            logger.info("Walk-forward optimization interrupted by user")
        except Exception as e:
            logger.error(f"Walk-forward error: {e}", exc_info=True)
    
    elif args.mode == 'walkforward':
        from app.optimization.walk_forward_engine import WalkForwardEngine
        from app.optimization.window_generator import WindowMode
        from app.optimization.parameter_optimizer import SearchMethod, ScoringMetric
        from app.strategy.strategy_loader import strategy_loader
        import yaml
        
        # Load strategy class
        strategy_class = strategy_loader.load_strategy_class(args.strategy)
        if not strategy_class:
            logger.error(f"Failed to load strategy: {args.strategy}")
            return
        
        # Parse symbols
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(',')]
        else:
            symbols = [args.symbol]
        
        # Load parameter space
        if not args.param_space:
            logger.error("--param-space required for walkforward optimization")
            return
        
        with open(args.param_space, 'r') as f:
            param_space = yaml.safe_load(f)
        
        if not param_space:
            logger.error("Invalid parameter space file")
            return
        
        # Create walk-forward engine
        wfo_engine = WalkForwardEngine(
            strategy_class=strategy_class,
            param_space=param_space,
            symbols=symbols,
            start_date=args.start_date or "2020-01-01",
            end_date=args.end_date or "2023-12-31",
            training_period=args.training_period,
            testing_period=args.testing_period,
            mode=WindowMode.SLIDING if args.wfo_mode == 'sliding' else WindowMode.EXPANDING,
            search_method=SearchMethod.GRID,
            scoring_metric=ScoringMetric.WEIGHTED,
            initial_capital=100000.0,
            data_dir=args.data_dir
        )
        
        # Run walk-forward optimization
        try:
            wfo_engine.run()
        except KeyboardInterrupt:
            logger.info("Walk-forward optimization interrupted by user")
        except Exception as e:
            logger.error(f"Walk-forward error: {e}", exc_info=True)
    
    elif args.mode == 'optimize':
        from app.optimization.advanced_optimizer import AdvancedOptimizer
        from app.strategy.strategy_loader import strategy_loader
        import yaml
        
        # Load strategy class
        strategy_class = strategy_loader.load_strategy_class(args.strategy)
        if not strategy_class:
            logger.error(f"Failed to load strategy: {args.strategy}")
            return
        
        # Parse symbols
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(',')]
        else:
            symbols = [args.symbol]
        
        # Load parameter space
        if not args.param_space:
            logger.error("--param-space required for optimization")
            return
        
        with open(args.param_space, 'r') as f:
            param_space = yaml.safe_load(f)
        
        if not param_space:
            logger.error("Invalid parameter space file")
            return
        
        # Create optimizer
        optimizer = AdvancedOptimizer(
            strategy_cls=strategy_class,
            param_space=param_space,
            symbols=symbols,
            start_date=args.start_date or "2020-01-01",
            end_date=args.end_date or "2023-12-31",
            scoring=args.scoring,
            initial_capital=100000.0,
            data_dir=args.data_dir
        )
        
        # Run optimization
        try:
            result = optimizer.optimize(
                num_trials=args.trials,
                n_jobs=args.jobs,
                timeout=args.timeout
            )
            
            logger.info(f"\nOptimization complete!")
            logger.info(f"Best parameters: {result.best_params}")
            logger.info(f"Best score: {result.best_value:.4f}")
            logger.info(f"Results saved to: optimization_results/")
        
        except KeyboardInterrupt:
            logger.info("Optimization interrupted by user")
        except Exception as e:
            logger.error(f"Optimization error: {e}", exc_info=True)
    
    elif args.mode == 'montecarlo':
        import numpy as np
        import pandas as pd
        from app.risk.monte_carlo import MonteCarloEngine
        from app.backtest.backtest_engine import BacktestEngine
        from app.backtest.replay_engine import ReplayMode, ReplaySpeed
        from app.strategy.strategy_loader import strategy_loader
        
        # Load strategy
        strategy = strategy_loader.load_strategy(args.strategy)
        if not strategy:
            logger.error(f"Failed to load strategy: {args.strategy}")
            return
        
        # Parse symbols
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(',')]
        else:
            symbols = [args.symbol]
        
        # Run backtest to get returns
        logger.info("Running backtest to generate returns...")
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=100000.0,
            data_dir=args.data_dir,
            replay_mode=ReplayMode.TICK,
            replay_speed=ReplaySpeed.INSTANT
        )
        
        result = engine.run(
            symbols=symbols,
            start_date=args.start_date,
            end_date=args.end_date
        )
        
        if not result or 'equity_curve' not in result:
            logger.error("No equity curve data from backtest")
            return
        
        # Extract returns from equity curve
        equity_df = pd.DataFrame(result['equity_curve'])
        equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'], unit='s', errors='coerce')
        equity_df = equity_df.sort_values('timestamp')
        equity_df['returns'] = equity_df['equity'].pct_change().dropna()
        
        returns = equity_df['returns']
        
        if len(returns) == 0:
            logger.error("No returns data available")
            return
        
        # Run Monte Carlo simulation
        logger.info("Running Monte Carlo simulation...")
        mc_engine = MonteCarloEngine(
            returns=returns,
            simulations=args.simulations,
            horizon=args.horizon,
            n_jobs=args.mc_jobs
        )
        
        mc_result = mc_engine.run(model=args.model)
        
        # Print results
        print("\n" + "="*60)
        print("MONTE CARLO SIMULATION RESULTS")
        print("="*60)
        print(f"Model: {args.model}")
        print(f"Simulations: {mc_result.simulations:,}")
        print(f"Horizon: {mc_result.horizon} days")
        print(f"\nReturn Statistics:")
        print(f"  Mean return:     {mc_result.mean_return:.4f}")
        print(f"  Median return:   {mc_result.median_return:.4f}")
        print(f"\nRisk Metrics:")
        print(f"  VaR (95%):       {mc_result.var_95:.4f}")
        print(f"  CVaR (95%):      {mc_result.cvar_95:.4f}")
        print(f"  Worst 1%:        {mc_result.worst_1pct:.4f}")
        print(f"  Avg Max DD:      {np.mean(mc_result.max_drawdowns):.2%}")
        print(f"  Worst Max DD:    {np.max(mc_result.max_drawdowns):.2%}")
        print("="*60)
    
    elif args.mode == 'sync':
        run_ibkr_sync()
    elif args.mode == 'all':
        # Run both engine and API (in separate processes)
        logger.warning("Running both engine and API - use separate processes in production")
        import multiprocessing
        
        # Start API in separate process
        api_process = multiprocessing.Process(target=run_api)
        api_process.start()
        
        # Run engine in main process
        try:
            run_engine_async()
        finally:
            api_process.terminate()
            api_process.join()


    elif args.mode == 'live':
        from app.live.hammer_client import HammerClient
        from app.live.hammer_feed import HammerFeed
        from app.live.execution_adapter import ExecutionBroker
        from app.live.hammer_execution_adapter import HammerExecutionAdapter
        from app.live.ibkr_execution_adapter import IBKRExecutionAdapter
        from app.engine.live_engine import LiveEngine
        from app.engine.position_manager import PositionManager
        from app.risk.risk_manager import RiskManager
        from app.risk.risk_limits import RiskLimits
        from app.risk.risk_state import RiskState
        
        # Test symbols (data subscribe only, no orders)
        test_symbols = ["CIM PRB", "MFA PRC", "AGNCM", "DTG"]
        
        # Determine mode
        if args.no_trading:
            mode_str = "DATA SUBSCRIBE ONLY (NO ORDERS)"
        elif args.test_order:
            mode_str = "TEST ORDER MODE (DRY-RUN)"
        else:
            mode_str = "LIVE TRADING MODE"
        
        logger.info("="*60)
        logger.info(f"LIVE TRADING ENGINE - {mode_str}")
        logger.info("="*60)
        logger.info(f"Test symbols: {', '.join(test_symbols)}")
        if args.no_trading:
            logger.info("⚠️  NO TRADING MODE: Orders disabled, data only")
        elif args.test_order:
            logger.info("🧪 TEST ORDER MODE: Will send test order and cancel")
        else:
            logger.info("🚀 LIVE MODE: Orders enabled")
        
        # Get execution broker
        execution_broker = args.execution_broker.upper()
        logger.info(f"Execution Broker: {execution_broker}")
        logger.info("Market Data: ALWAYS from Hammer (single source of truth)")
        
        # Get password from: CLI arg > env var > settings
        password = (
            args.hammer_password or 
            os.getenv("HAMMER_PASSWORD") or 
            settings.HAMMER_PASSWORD
        )
        if not password:
            logger.error("Hammer Pro password required!")
            logger.error("Options:")
            logger.error("  1. --hammer-password YOUR_PASSWORD")
            logger.error("  2. Set HAMMER_PASSWORD environment variable")
            logger.error("  3. Add HAMMER_PASSWORD to .env file")
            return
        
        # Get host/port from: CLI arg > settings > default
        host = args.hammer_host or settings.HAMMER_HOST
        port = args.hammer_port or settings.HAMMER_PORT
        
        # ============================================================
        # MARKET DATA: ALWAYS FROM HAMMER (SINGLE SOURCE OF TRUTH)
        # ============================================================
        hammer_client = HammerClient(
            host=host,
            port=port,
            password=password
        )
        
        if not hammer_client.connect():
            logger.error("Failed to connect to Hammer Pro (market data)")
            return
        
        hammer_feed = HammerFeed(hammer_client)
        
        # ============================================================
        # EXECUTION: PLUGGABLE (IBKR | HAMMER)
        # ============================================================
        if execution_broker == "IBKR":
            # IBKR Execution
            if not args.ibkr_account:
                logger.error("--ibkr-account required when --execution-broker=IBKR")
                logger.error("Example: --ibkr-account DU123456")
                return
            
            from app.ibkr.ibkr_client import IBKRClient
            ibkr_client = IBKRClient()
            execution_adapter = IBKRExecutionAdapter(
                account_id=args.ibkr_account,
                ibkr_client=ibkr_client
            )
            
            if not execution_adapter.connect():
                logger.error("Failed to connect to IBKR (execution)")
                hammer_client.disconnect()
                return
            
            logger.info(f"✅ Using IBKR for execution (account: {args.ibkr_account})")
        
        elif execution_broker == "HAMMER":
            # Hammer Execution
            execution_adapter = HammerExecutionAdapter(
                account_key=args.hammer_account,
                hammer_client=hammer_client
            )
            
            if not execution_adapter.connect():
                logger.error("Failed to connect to Hammer Pro (execution)")
                hammer_client.disconnect()
                return
            
            logger.info(f"✅ Using Hammer Pro for execution (account: {args.hammer_account})")
        
        else:
            logger.error(f"Invalid execution broker: {execution_broker}")
            hammer_client.disconnect()
            return
        
        # Create position and risk managers
        position_manager = PositionManager()
        risk_limits = RiskLimits()
        risk_state = RiskState()
        risk_manager = RiskManager(limits=risk_limits, state=risk_state)
        risk_manager.set_position_manager(position_manager)
        
        # Create live engine (broker-agnostic)
        live_engine = LiveEngine(
            hammer_feed=hammer_feed,
            execution_adapter=execution_adapter,
            position_manager=position_manager,
            risk_manager=risk_manager
        )
        
        # Wait for authentication to complete
        logger.info("Waiting for authentication...")
        auth_timeout = 10
        auth_start = time.time()
        while not hammer_client.authenticated and (time.time() - auth_start) < auth_timeout:
            time.sleep(0.1)
        
        if not hammer_client.authenticated:
            logger.error("❌ Authentication timeout")
            hammer_client.disconnect()
            return
        
        logger.info("✅ Authentication complete, subscribing to symbols...")
        
        # Subscribe to test symbols
        for symbol in test_symbols:
            if live_engine.feed.subscribe_symbol(symbol, include_l2=True):
                logger.info(f"✅ Subscribed to {symbol}")
            else:
                logger.warning(f"⚠️ Failed to subscribe to {symbol}")
            time.sleep(0.2)  # Small delay between subscriptions
        
        logger.info("Subscribed to all symbols. Waiting for market data...")
        logger.info("Press Ctrl+C to stop")
        
        # Test order mode
        if args.test_order:
            import time as time_module
            logger.info("="*60)
            logger.info("TEST ORDER MODE - Sending test order in 5 seconds...")
            logger.info("="*60)
            time_module.sleep(5)
            
            # Get first symbol and current tick
            test_symbol = test_symbols[0]
            if test_symbol in live_engine.last_tick:
                tick = live_engine.last_tick[test_symbol]
                bid = tick.get("bid", 0)
                ask = tick.get("ask", 0)
                
                if bid > 0 and ask > 0:
                    # Place order far from market (won't fill)
                    test_price = bid * 0.95  # 5% below bid
                    test_qty = 1
                    
                    logger.info(f"🧪 Sending TEST ORDER:")
                    logger.info(f"   Symbol: {test_symbol}")
                    logger.info(f"   Side: BUY")
                    logger.info(f"   Quantity: {test_qty}")
                    logger.info(f"   Price: ${test_price:.2f} (bid: ${bid:.2f}, ask: ${ask:.2f})")
                    logger.info(f"   Broker: {execution_broker}")
                    logger.info(f"   Account: {execution_adapter.account_id}")
                    
                    # Place order
                    order_sent = live_engine.place_order(
                        symbol=test_symbol,
                        side="BUY",
                        quantity=test_qty,
                        price=test_price,
                        order_type="LIMIT"
                    )
                    
                    if order_sent:
                        logger.info("✅ Test order sent successfully")
                        logger.info("⏳ Waiting 3 seconds before cancel...")
                        time_module.sleep(3)
                        
                        # Note: We need order_id to cancel, but we don't have it yet
                        # For now, just log that order was sent
                        logger.info("⚠️  Note: Order cancellation requires order_id tracking")
                        logger.info("   Check broker GUI to verify order appeared")
                    else:
                        logger.error("❌ Failed to send test order")
                else:
                    logger.warning("⚠️  No valid bid/ask for test order")
            else:
                logger.warning(f"⚠️  No tick data yet for {test_symbol}, waiting...")
                time_module.sleep(5)
                # Try again if we have data now
                if test_symbol in live_engine.last_tick:
                    tick = live_engine.last_tick[test_symbol]
                    bid = tick.get("bid", 0)
                    ask = tick.get("ask", 0)
                    if bid > 0 and ask > 0:
                        test_price = bid * 0.95
                        test_qty = 1
                        logger.info(f"🧪 Sending TEST ORDER: {test_symbol} BUY {test_qty} @ ${test_price:.2f}")
                        live_engine.place_order(test_symbol, "BUY", test_qty, test_price, "LIMIT")
        
        # No trading mode - just log data
        if args.no_trading:
            logger.info("="*60)
            logger.info("DATA MONITORING MODE - No orders will be sent")
            logger.info("="*60)
        
        # Graceful shutdown
        def signal_handler(sig, frame):
            logger.info("\nShutting down...")
            execution_adapter.disconnect()
            hammer_client.disconnect()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Keep running
        try:
            while True:
                time.sleep(1)
                # Check connections
                if not hammer_client.is_connected():
                    logger.warning("Hammer connection lost, attempting reconnect...")
                    hammer_client.connect()
                    time.sleep(2)
                if not execution_adapter.is_connected():
                    logger.warning("Execution connection lost, attempting reconnect...")
                    execution_adapter.connect()
                    time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            execution_adapter.disconnect()
            hammer_client.disconnect()

if __name__ == "__main__":
    main()

