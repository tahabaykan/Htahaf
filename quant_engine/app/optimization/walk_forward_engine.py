"""app/optimization/walk_forward_engine.py

Walk-forward optimization engine.
Manages the complete WFO process.
"""

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.logger import logger
from app.optimization.window_generator import WindowGenerator, WindowMode
from app.optimization.parameter_optimizer import ParameterOptimizer, SearchMethod, ScoringMetric
from app.backtest.backtest_engine import BacktestEngine
from app.backtest.replay_engine import ReplayMode, ReplaySpeed
from app.strategy.strategy_base import StrategyBase


class WalkForwardEngine:
    """
    Walk-forward optimization engine.
    
    Process:
    1. Generate training/testing windows
    2. For each window:
       a. Optimize parameters on training data
       b. Test best parameters on testing data
       c. Store results
    3. Generate reports
    """
    
    def __init__(
        self,
        strategy_class: type,
        param_space: Dict[str, List[Any]],
        symbols: List[str],
        start_date: str,
        end_date: str,
        training_period: str = "12M",
        testing_period: str = "3M",
        mode: WindowMode = WindowMode.SLIDING,
        search_method: SearchMethod = SearchMethod.GRID,
        scoring_metric: ScoringMetric = ScoringMetric.WEIGHTED,
        initial_capital: float = 100000.0,
        data_dir: str = "data/historical",
        output_dir: str = "walkforward_results"
    ):
        """
        Initialize walk-forward engine.
        
        Args:
            strategy_class: Strategy class to optimize
            param_space: Parameter space for optimization
            symbols: List of symbols
            start_date: Overall start date
            end_date: Overall end date
            training_period: Training window size
            testing_period: Testing window size
            mode: SLIDING or EXPANDING
            search_method: GRID or RANDOM
            scoring_metric: Metric to optimize
            initial_capital: Initial capital
            data_dir: Data directory
            output_dir: Output directory
        """
        self.strategy_class = strategy_class
        self.param_space = param_space
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.data_dir = data_dir
        self.output_dir = output_dir
        
        # Window generator
        self.window_generator = WindowGenerator(
            training_period=training_period,
            testing_period=testing_period,
            mode=mode
        )
        
        # Parameter optimizer
        self.optimizer = ParameterOptimizer(
            search_method=search_method,
            scoring_metric=scoring_metric
        )
        
        # Results storage
        self.window_results: List[Dict[str, Any]] = []
        self.chosen_parameters: List[Dict[str, Any]] = []
        self.oos_results: List[Dict[str, Any]] = []  # Out-of-sample results
    
    def run(self):
        """Run walk-forward optimization"""
        logger.info("="*60)
        logger.info("WALK-FORWARD OPTIMIZATION")
        logger.info("="*60)
        logger.info(f"Strategy: {self.strategy_class.__name__}")
        logger.info(f"Symbols: {', '.join(self.symbols)}")
        logger.info(f"Date range: {self.start_date} to {self.end_date}")
        logger.info(f"Mode: {self.window_generator.mode.value}")
        
        # Generate windows
        windows = self.window_generator.generate_windows(
            self.start_date,
            self.end_date
        )
        
        if not windows:
            logger.error("No windows generated. Check date range and periods.")
            return
        
        logger.info(f"Generated {len(windows)} windows")
        
        # Process each window
        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            logger.info(f"\n{'='*60}")
            logger.info(f"Window {i+1}/{len(windows)}")
            logger.info(f"Training: {train_start.strftime('%Y-%m-%d')} to {train_end.strftime('%Y-%m-%d')}")
            logger.info(f"Testing:  {test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')}")
            logger.info(f"{'='*60}")
            
            # Step 1: Optimize on training data
            logger.info("Step 1: Optimizing parameters on training data...")
            opt_result = self.optimizer.optimize(
                strategy_class=self.strategy_class,
                param_space=self.param_space,
                symbols=self.symbols,
                start_date=train_start.strftime("%Y-%m-%d"),
                end_date=train_end.strftime("%Y-%m-%d"),
                initial_capital=self.initial_capital,
                data_dir=self.data_dir
            )
            
            best_params = opt_result.best_params
            logger.info(f"Best parameters: {best_params}")
            logger.info(f"Best training score: {opt_result.best_score:.4f}")
            
            # Step 2: Test on out-of-sample data
            logger.info("Step 2: Testing best parameters on out-of-sample data...")
            oos_result = self._test_parameters(
                best_params,
                test_start.strftime("%Y-%m-%d"),
                test_end.strftime("%Y-%m-%d")
            )
            
            # Store results
            window_result = {
                'window': i + 1,
                'train_start': train_start.strftime("%Y-%m-%d"),
                'train_end': train_end.strftime("%Y-%m-%d"),
                'test_start': test_start.strftime("%Y-%m-%d"),
                'test_end': test_end.strftime("%Y-%m-%d"),
                'chosen_params': best_params,
                'training_score': opt_result.best_score,
                'training_metrics': opt_result.all_results[0]['metrics'] if opt_result.all_results else {},
                'oos_metrics': oos_result
            }
            
            self.window_results.append(window_result)
            self.chosen_parameters.append({
                'window': i + 1,
                'params': best_params,
                'test_period': f"{test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')}"
            })
            self.oos_results.append(oos_result)
        
        # Generate reports
        logger.info("\n" + "="*60)
        logger.info("Generating reports...")
        self._generate_reports()
        
        logger.info(f"\nWalk-forward optimization complete!")
        logger.info(f"Results saved to: {self.output_dir}")
    
    def _test_parameters(
        self,
        params: Dict[str, Any],
        test_start: str,
        test_end: str
    ) -> Dict[str, Any]:
        """Test parameters on out-of-sample data"""
        # Create strategy with best parameters
        strategy = self.strategy_class(**params)
        
        # Create backtest engine
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=self.initial_capital,
            data_dir=self.data_dir,
            replay_mode=ReplayMode.TICK,
            replay_speed=ReplaySpeed.INSTANT
        )
        
        # Run backtest on test period
        engine.run(
            symbols=self.symbols,
            start_date=test_start,
            end_date=test_end
        )
        
        # Get results
        results = engine.get_results()
        
        return {
            'total_pnl': results.get('total_pnl', 0),
            'sharpe': results.get('sharpe', 0),
            'sortino': results.get('sortino', 0),
            'max_drawdown': results.get('max_drawdown', 0),
            'win_rate': results.get('win_rate', 0),
            'profit_factor': results.get('profit_factor', 0),
            'num_trades': results.get('num_trades', 0)
        }
    
    def _generate_reports(self):
        """Generate all output reports"""
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 1. Chosen parameters
        with open(f"{self.output_dir}/chosen_parameters.json", "w") as f:
            json.dump(self.chosen_parameters, f, indent=2)
        
        # 2. Window results
        with open(f"{self.output_dir}/window_results.json", "w") as f:
            json.dump(self.window_results, f, indent=2)
        
        # 3. Out-of-sample equity curve
        import pandas as pd
        equity_data = []
        cumulative_pnl = 0
        
        for i, result in enumerate(self.oos_results):
            cumulative_pnl += result.get('total_pnl', 0)
            equity_data.append({
                'window': i + 1,
                'pnl': result.get('total_pnl', 0),
                'cumulative_pnl': cumulative_pnl,
                'sharpe': result.get('sharpe', 0),
                'max_drawdown': result.get('max_drawdown', 0)
            })
        
        equity_df = pd.DataFrame(equity_data)
        equity_df.to_csv(f"{self.output_dir}/oos_equity_curve.csv", index=False)
        
        # 4. Summary
        summary = self._calculate_summary()
        
        with open(f"{self.output_dir}/walkforward_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        # 5. Markdown summary
        self._generate_markdown_summary(summary)
    
    def _calculate_summary(self) -> Dict[str, Any]:
        """Calculate walk-forward summary statistics"""
        if not self.oos_results:
            return {}
        
        total_pnl = sum(r.get('total_pnl', 0) for r in self.oos_results)
        avg_sharpe = sum(r.get('sharpe', 0) for r in self.oos_results) / len(self.oos_results)
        avg_sortino = sum(r.get('sortino', 0) for r in self.oos_results) / len(self.oos_results)
        avg_drawdown = sum(abs(r.get('max_drawdown', 0)) for r in self.oos_results) / len(self.oos_results)
        avg_win_rate = sum(r.get('win_rate', 0) for r in self.oos_results) / len(self.oos_results)
        total_trades = sum(r.get('num_trades', 0) for r in self.oos_results)
        
        # Calculate consistency (how often OOS was profitable)
        profitable_windows = sum(1 for r in self.oos_results if r.get('total_pnl', 0) > 0)
        consistency = profitable_windows / len(self.oos_results) if self.oos_results else 0
        
        return {
            'num_windows': len(self.window_results),
            'total_pnl': total_pnl,
            'avg_pnl_per_window': total_pnl / len(self.oos_results) if self.oos_results else 0,
            'avg_sharpe': avg_sharpe,
            'avg_sortino': avg_sortino,
            'avg_max_drawdown': avg_drawdown,
            'avg_win_rate': avg_win_rate,
            'total_trades': total_trades,
            'consistency': consistency,
            'profitable_windows': profitable_windows,
            'window_info': self.window_generator.get_window_info(
                self.window_generator.generate_windows(self.start_date, self.end_date)
            )
        }
    
    def _generate_markdown_summary(self, summary: Dict[str, Any]):
        """Generate markdown summary report"""
        md = f"""# Walk-Forward Optimization Summary

## Overview

- **Strategy**: {self.strategy_class.__name__}
- **Symbols**: {', '.join(self.symbols)}
- **Date Range**: {self.start_date} to {self.end_date}
- **Mode**: {self.window_generator.mode.value}
- **Number of Windows**: {summary.get('num_windows', 0)}

## Performance Metrics

- **Total P&L**: ${summary.get('total_pnl', 0):,.2f}
- **Average P&L per Window**: ${summary.get('avg_pnl_per_window', 0):,.2f}
- **Average Sharpe Ratio**: {summary.get('avg_sharpe', 0):.4f}
- **Average Sortino Ratio**: {summary.get('avg_sortino', 0):.4f}
- **Average Max Drawdown**: {summary.get('avg_max_drawdown', 0)*100:.2f}%
- **Average Win Rate**: {summary.get('avg_win_rate', 0)*100:.2f}%
- **Total Trades**: {summary.get('total_trades', 0)}

## Consistency

- **Profitable Windows**: {summary.get('profitable_windows', 0)} / {summary.get('num_windows', 0)}
- **Consistency Rate**: {summary.get('consistency', 0)*100:.2f}%

## Window Configuration

- **Training Period**: {self.window_generator.training_period}
- **Testing Period**: {self.window_generator.testing_period}
- **Mode**: {self.window_generator.mode.value}

## Files Generated

- `chosen_parameters.json` - Parameters chosen for each window
- `window_results.json` - Detailed results for each window
- `oos_equity_curve.csv` - Out-of-sample equity curve
- `walkforward_summary.json` - Summary statistics
"""
        
        with open(f"{self.output_dir}/walkforward_summary.md", "w") as f:
            f.write(md)








