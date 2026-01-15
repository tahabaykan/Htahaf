"""app/backtest/backtest_engine.py

Core backtest engine - main backtest loop.
Replays historical data and processes through strategy.
"""

import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.core.logger import logger
from app.strategy.strategy_base import StrategyBase
from app.strategy.candle_manager import CandleManager
from app.engine.position_manager import PositionManager
from app.risk.risk_manager import RiskManager
from app.risk.risk_limits import RiskLimits
from app.risk.risk_state import RiskState
from app.backtest.data_reader import DataReader
from app.backtest.replay_engine import ReplayEngine, ReplayMode, ReplaySpeed
from app.backtest.execution_simulator import ExecutionSimulator as LegacyExecutionSimulator
from app.backtest.backtest_report import BacktestReport
from app.portfolio.portfolio_manager import PortfolioManager
from app.portfolio.portfolio_risk import PortfolioRiskManager
from app.execution.execution_simulator import ExecutionSimulator, FillReport
from app.execution.commission import CommissionModel, CommissionType
from app.execution.liquidity import LiquidityModel, LiquidityModelType


class BacktestEngine:
    """
    Core backtest engine.
    
    Replays historical data and processes through strategy,
    similar to live TradingEngine but with historical data.
    """
    
    def __init__(
        self,
        strategy: StrategyBase,
        initial_capital: float = 100000.0,
        data_dir: str = "data/historical",
        replay_mode: ReplayMode = ReplayMode.TICK,
        replay_speed: ReplaySpeed = ReplaySpeed.INSTANT,
        slippage: float = 0.01,
        commission_per_share: float = 0.005,
        commission_min: float = 1.0
    ):
        """
        Initialize backtest engine.
        
        Args:
            strategy: Strategy instance to test
            initial_capital: Starting capital
            data_dir: Directory containing historical data
            replay_mode: TICK or CANDLE replay mode
            replay_speed: Replay speed (INSTANT, REALTIME, etc.)
        """
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.data_reader = DataReader(data_dir)
        self.replay_engine = ReplayEngine(mode=replay_mode, speed=replay_speed)
        
        # Portfolio management
        self.portfolio_manager = PortfolioManager(initial_capital=initial_capital)
        self.portfolio_risk_manager = PortfolioRiskManager()
        
        # Components (same as live engine) - kept for per-symbol position tracking
        self.position_manager = PositionManager()  # Legacy, will use portfolio_manager
        self.candle_managers: Dict[str, CandleManager] = {}  # Per-symbol candle managers
        
        # Risk manager with relaxed limits for backtesting
        risk_limits = RiskLimits(
            max_position_per_symbol=100000.0,
            max_daily_loss=100000.0,
            max_trades_per_minute=10000
        )
        risk_state = RiskState()
        risk_state.starting_equity = initial_capital
        risk_state.current_equity = initial_capital
        self.risk_manager = RiskManager(limits=risk_limits, state=risk_state)
        self.risk_manager.set_position_manager(self.position_manager)
        
        # Execution simulator (new realistic model)
        commission_model = CommissionModel.ibkr_stock()
        if commission_per_share > 0:
            commission_model = CommissionModel(
                commission_type=CommissionType.PERCENTAGE,
                percentage=commission_per_share / 100.0,  # Convert to fraction
                min_commission=commission_min
            )
        
        liquidity_model = LiquidityModel(
            model_type=LiquidityModelType.HYBRID,
            volume_fraction=0.1,  # Can fill 10% of volume
            impact_coefficient=0.1
        )
        
        self.execution_simulator = ExecutionSimulator(
            commission_model=commission_model,
            liquidity_model=liquidity_model,
            volatility_adjustment=True
        )
        
        # Initialize strategy (will be updated per-symbol in multi-asset mode)
        # For now, use a default candle manager
        default_candle_manager = CandleManager(interval_seconds=60)
        self.strategy.initialize(
            candle_manager=default_candle_manager,
            position_manager=self.position_manager,
            risk_manager=self.risk_manager
        )
        
        # Reporting
        self.report = BacktestReport()
        
        # Statistics
        self.tick_count = 0
        self.signal_count = 0
        self.order_count = 0
        self.execution_count = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
        # Track trades for metrics
        self.open_trades: Dict[str, Dict[str, Any]] = {}  # symbol -> trade info
    
    def run(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        data_format: str = "auto"
    ):
        """
        Run backtest for symbols (single or multiple).
        
        Args:
            symbols: List of stock symbols to backtest (or single symbol as string)
            start_date: Start date (YYYY-MM-DD) or None
            end_date: End date (YYYY-MM-DD) or None
            data_format: "csv", "parquet", or "auto"
        """
        # Handle single symbol (backward compatibility)
        if isinstance(symbols, str):
            symbols = [symbols]
        
        logger.info(f"🚀 Starting backtest for symbols: {', '.join(symbols)}")
        logger.info(f"  Date range: {start_date or 'start'} to {end_date or 'end'}")
        logger.info(f"  Initial capital: ${self.initial_capital:,.2f}")
        logger.info(f"  Replay mode: {self.replay_engine.mode.value}")
        logger.info(f"  Replay speed: {self.replay_engine.speed.value}")
        
        self.start_time = time.time()
        
        try:
            # Load historical data for all symbols
            symbol_data = {}
            symbol_ticks = {}
            
            for symbol in symbols:
                df = self.data_reader.read_data(symbol, data_format, start_date, end_date)
                
                if len(df) == 0:
                    logger.warning(f"No data found for {symbol}, skipping")
                    continue
                
                logger.info(f"Loaded {len(df):,} rows for {symbol}")
                symbol_data[symbol] = df
                
                # Convert to ticks
                if self.replay_engine.mode == ReplayMode.TICK:
                    ticks = self.data_reader.convert_to_ticks(df)
                    symbol_ticks[symbol] = ticks  # List of ticks
                else:
                    # Convert candles to ticks
                    candles = self.data_reader.convert_to_candles(df)
                    ticks = []
                    for candle in candles:
                        tick = {
                            'symbol': candle['symbol'],
                            'last': str(candle['close']),
                            'bid': str(candle['close'] - 0.01),
                            'ask': str(candle['close'] + 0.01),
                            'volume': int(candle['volume']),
                            'ts': int(candle['timestamp'] * 1000)
                        }
                        ticks.append(tick)
                    symbol_ticks[symbol] = ticks  # List of ticks
            
            if not symbol_ticks:
                logger.error("No data loaded for any symbol")
                return
            
            # Replay multi-symbol
            if len(symbols) == 1:
                # Single symbol - use simple replay
                symbol = symbols[0]
                ticks = symbol_ticks[symbol]
                self.replay_engine.replay_ticks(iter(ticks), lambda tick: self._on_tick_multi(symbol, tick))
            else:
                # Multi-symbol - use merged replay
                self.replay_engine.replay_multi_symbol_ticks(symbol_ticks, self._on_tick_multi)
        
        except Exception as e:
            logger.error(f"Error in backtest: {e}", exc_info=True)
        finally:
            self.end_time = time.time()
            
            # Save all reports
            output_dir = f"backtest_results/{self.strategy.name}_{int(time.time())}"
            self.report.save_all(output_dir)
            
            # Print summary
            self._print_summary(output_dir)
            
            # Return results for HTML report
            return self._get_backtest_result()
    
    def _get_backtest_result(self) -> Dict[str, Any]:
        """Get backtest result dictionary for HTML report"""
        import pandas as pd
        
        equity_df = pd.DataFrame(self.report.equity_curve) if self.report.equity_curve else pd.DataFrame()
        metrics = self.report.compute_metrics(equity_df) if len(equity_df) > 0 else {}
        trade_stats = self.report.compute_trade_metrics()
        
        # Convert trades to list of dicts
        trades = [t.__dict__ for t in self.report.trades]
        
        return {
            'equity_curve': self.report.equity_curve,
            'trades': trades,
            'metrics': {
                'equity_metrics': metrics,
                'trade_metrics': trade_stats
            },
            'symbols': list(self.candle_managers.keys()) if hasattr(self, 'candle_managers') else []
        }
    
    def _on_tick_multi(self, symbol: str, tick: Dict[str, Any]):
        """Process tick for specific symbol (multi-asset mode)"""
        try:
            self.tick_count += 1
            tick_ts = float(tick.get('ts', tick.get('timestamp', time.time() * 1000))) / 1000.0
            
            # Ensure tick has symbol
            tick['symbol'] = symbol
            
            # Get or create candle manager for symbol
            if symbol not in self.candle_managers:
                self.candle_managers[symbol] = CandleManager(interval_seconds=60)
            
            candle_mgr = self.candle_managers[symbol]
            
            # Update market price in portfolio
            price = float(tick.get('last', 0))
            if price > 0:
                self.portfolio_manager.update_market_price(symbol, price)
            
            # Update liquidity model with volume
            volume = float(tick.get('volume', 0))
            if volume > 0:
                self.execution_simulator.liquidity_model.update_volume(symbol, volume)
            
            # First, try to fill pending limit orders
            limit_fills = self.execution_simulator.process_tick(tick)
            executions = []
            
            # Convert FillReport to execution message format
            for fill in limit_fills:
                exec_msg = {
                    'symbol': symbol,
                    'side': 'BUY' if fill.filled_qty > 0 else 'SELL',
                    'fill_qty': fill.filled_qty,
                    'fill_price': fill.avg_fill_price,
                    'commission': fill.commission,
                    'slippage': fill.slippage,
                    'effective_price': fill.effective_price,
                    'liquidity_constrained': fill.liquidity_constrained,
                    'timestamp': fill.timestamp
                }
                executions.append(exec_msg)
            for exec_msg in executions:
                self.execution_count += 1
                
                symbol = exec_msg['symbol']
                side = exec_msg['side']
                qty = float(exec_msg['fill_qty'])
                price = float(exec_msg['fill_price'])
                
                # Get position before execution
                position_before = self.portfolio_manager.get_position(symbol)
                qty_before = position_before.get('qty', 0) if position_before else 0
                
                # Update portfolio manager
                commission = exec_msg.get('commission', 0)
                self.portfolio_manager.update_on_order_fill(symbol, side, qty, price, commission)
                
                # Update risk manager
                self.risk_manager.update_after_execution(symbol, side, qty, price)
                
                # Get position after execution
                position_after = self.portfolio_manager.get_position(symbol)
                qty_after = position_after.get('qty', 0) if position_after else 0
                
                # Track trades (entry/exit)
                if qty_before == 0 and qty_after != 0:
                    # Entry
                    self.open_trades[symbol] = {
                        'entry_time': tick_ts,
                        'entry_price': exec_msg.get('effective_price', price),
                        'entry_price_base': price,
                        'entry_qty': abs(qty_after),
                        'side': side,
                        'slippage': exec_msg.get('slippage', 0.0),
                        'commission': commission
                    }
                elif qty_before != 0 and qty_after == 0:
                    # Exit - close trade
                    if symbol in self.open_trades:
                        trade = self.open_trades[symbol]
                        pnl = (price - trade['entry_price']) * trade['entry_qty']
                        if trade['side'] == 'SELL':
                            pnl = -pnl
                        
                        duration_s = tick_ts - trade['entry_time']
                        
                        # Add to report
                        self.report.add_trade(
                            symbol=symbol,
                            side=trade['side'],
                            qty=trade['entry_qty'],
                            entry_price=trade['entry_price'],
                            exit_price=price,
                            pnl=pnl,
                            entry_time=trade['entry_time'],
                            exit_time=tick_ts,
                            duration_s=duration_s
                        )
                        del self.open_trades[symbol]
            
            # Calculate current portfolio equity
            current_equity = self.portfolio_manager.get_total_equity()
            
            # Add equity point
            self.report.add_equity_point(tick_ts, current_equity)
            
            # Update strategy's candle manager and position manager for this symbol
            if hasattr(self.strategy, 'candle_manager'):
                self.strategy.candle_manager = candle_mgr
            if hasattr(self.strategy, 'position_manager'):
                # Strategy should access portfolio manager's position manager for this symbol
                self.strategy.position_manager = self.portfolio_manager.get_position_manager(symbol)
            
            # Process through strategy (same as live engine)
            signal = self.strategy.on_tick(tick)
            
            if signal:
                self.signal_count += 1
                
                signal_symbol = signal.get('symbol', symbol)
                signal_qty = float(signal.get('quantity', signal.get('qty', 0)))
                signal_price = float(signal.get('price', price))
                
                # Portfolio risk check
                allowed, reason = self.portfolio_risk_manager.can_open_position(
                    signal_symbol,
                    signal_qty,
                    signal_price,
                    self.portfolio_manager
                )
                
                if not allowed:
                    logger.warning(f"Order rejected by portfolio risk: {reason}")
                    return
                
                # Convert signal to order format
                order = {
                    'symbol': signal_symbol,
                    'side': signal['signal'],  # BUY or SELL
                    'qty': signal_qty,
                    'limit_price': signal.get('limit_price')
                }
                
                # Submit order to execution simulator
                order_id = self.execution_simulator.process_new_order(order)
                self.order_count += 1
                
                logger.debug(f"Order submitted: {order} (ID: {order_id})")
        
        except Exception as e:
            logger.error(f"Error processing tick: {e}", exc_info=True)
    
    def _on_tick(self, tick: Dict[str, Any]):
        """Process tick (single symbol mode - backward compatibility)"""
        symbol = tick.get('symbol', 'UNKNOWN')
        self._on_tick_multi(symbol, tick)
    
    def _on_candle(self, candle: Dict[str, Any]):
        """Process candle (called by replay engine)"""
        try:
            symbol = candle.get('symbol', 'UNKNOWN')
            # Convert candle to tick format for strategy
            tick = {
                'symbol': symbol,
                'last': str(candle['close']),
                'bid': str(candle['close'] - 0.01),
                'ask': str(candle['close'] + 0.01),
                'volume': int(candle['volume']),
                'ts': int(candle['timestamp'] * 1000)
            }
            
            self._on_tick_multi(symbol, tick)
        
        except Exception as e:
            logger.error(f"Error processing candle: {e}", exc_info=True)
    
    def _print_summary(self, output_dir: str):
        """Print backtest summary"""
        elapsed = self.end_time - self.start_time if self.start_time and self.end_time else 0
        
        # Load equity curve for metrics
        import pandas as pd
        equity_df = pd.DataFrame(self.report.equity_curve)
        
        if len(equity_df) > 0:
            metrics = self.report.compute_metrics(equity_df)
            trade_stats = self.report.compute_trade_metrics()
            
            print("\n" + "="*60)
            print("BACKTEST SUMMARY")
            print("="*60)
            print(f"Initial capital:     ${self.initial_capital:,.2f}")
            if len(equity_df) > 0:
                final_equity = equity_df['equity'].iloc[-1]
                print(f"Final equity:         ${final_equity:,.2f}")
                print(f"Total return:          {((final_equity - self.initial_capital) / self.initial_capital * 100):.2f}%")
            
            print(f"\nTotal trades:          {trade_stats.get('num_trades', 0)}")
            print(f"Win rate:              {trade_stats.get('win_rate', 0) * 100:.2f}%")
            print(f"Profit factor:         {trade_stats.get('profit_factor', 0):.2f}")
            print(f"Sharpe ratio:          {metrics.get('sharpe', 0):.2f}")
            print(f"Sortino ratio:         {metrics.get('sortino', 0):.2f}")
            print(f"Max drawdown:          {metrics.get('max_drawdown', 0) * 100:.2f}%")
            print(f"CAGR:                  {metrics.get('CAGR', 0) * 100:.2f}%")
        
        print(f"\nTicks processed:      {self.tick_count:,}")
        print(f"Signals generated:    {self.signal_count:,}")
        print(f"Orders placed:        {self.order_count:,}")
        print(f"Executions:           {self.execution_count:,}")
        print(f"Backtest duration:    {elapsed:.2f}s")
        
        # Pending orders
        pending = self.execution_simulator.get_pending_orders()
        if pending:
            print(f"Pending orders:        {len(pending)}")
        print("="*60)
        print(f"\nReports saved to: {output_dir}")
    
    def get_results(self) -> Dict[str, Any]:
        """Get backtest results"""
        import pandas as pd
        
        equity_df = pd.DataFrame(self.report.equity_curve) if self.report.equity_curve else pd.DataFrame()
        metrics = self.report.compute_metrics(equity_df) if len(equity_df) > 0 else {}
        trade_stats = self.report.compute_trade_metrics()
        positions = self.position_manager.get_all_positions()
        
        return {
            **metrics,
            **trade_stats,
            'tick_count': self.tick_count,
            'signal_count': self.signal_count,
            'order_count': self.order_count,
            'execution_count': self.execution_count,
            'duration_seconds': self.end_time - self.start_time if self.start_time and self.end_time else 0,
            'positions': positions,
            'pending_orders': len(self.execution_simulator.get_pending_orders())
        }

