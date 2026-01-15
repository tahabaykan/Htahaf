"""app/optimization/advanced_optimizer.py

Advanced hyperparameter optimization using Optuna (Bayesian TPE).
Supports parallel execution and pruning.
"""

import os
import json
import pandas as pd
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner
import matplotlib.pyplot as plt
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

try:
    from optuna.visualization import (
        plot_param_importances,
        plot_parallel_coordinate,
        plot_slice
    )
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from app.core.logger import logger
from app.strategy.strategy_base import StrategyBase
from app.backtest.backtest_engine import BacktestEngine
from app.backtest.replay_engine import ReplayMode, ReplaySpeed


@dataclass
class OptimizationResult:
    """Result of advanced optimization"""
    best_params: Dict[str, Any]
    best_value: float
    n_trials: int
    study: optuna.Study
    history: pd.DataFrame


class AdvancedOptimizer:
    """
    Advanced hyperparameter optimizer using Optuna.
    
    Features:
    - Bayesian TPE optimization
    - Parallel execution
    - Early stopping (pruning)
    - Multiple scoring metrics
    - Visualization
    """
    
    def __init__(
        self,
        strategy_cls: type,
        param_space: Dict[str, List[Any]],
        symbols: List[str],
        start_date: str,
        end_date: str,
        scoring: str = "sharpe",
        initial_capital: float = 100000.0,
        data_dir: str = "data/historical",
        custom_scorer: Optional[Callable] = None
    ):
        """
        Initialize advanced optimizer.
        
        Args:
            strategy_cls: Strategy class to optimize
            param_space: Parameter space {param_name: [values]}
            symbols: List of symbols
            start_date: Start date
            end_date: End date
            scoring: Scoring metric ("sharpe", "sortino", "pnl", etc.)
            initial_capital: Initial capital
            data_dir: Data directory
            custom_scorer: Custom scoring function
        """
        self.strategy_cls = strategy_cls
        self.param_space = param_space
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.scoring = scoring
        self.initial_capital = initial_capital
        self.data_dir = data_dir
        self.custom_scorer = custom_scorer
        
        # Convert param space to Optuna format
        self.optuna_space = self._convert_param_space(param_space)
    
    def _convert_param_space(self, param_space: Dict[str, List[Any]]) -> Dict[str, Any]:
        """Convert parameter space to Optuna suggest format"""
        optuna_space = {}
        
        for param_name, values in param_space.items():
            if len(values) == 0:
                continue
            
            # Determine type
            first_val = values[0]
            
            if isinstance(first_val, int):
                # Integer range
                optuna_space[param_name] = {
                    'type': 'int',
                    'low': min(values),
                    'high': max(values)
                }
            elif isinstance(first_val, float):
                # Float range
                optuna_space[param_name] = {
                    'type': 'float',
                    'low': min(values),
                    'high': max(values)
                }
            else:
                # Categorical
                optuna_space[param_name] = {
                    'type': 'categorical',
                    'choices': values
                }
        
        return optuna_space
    
    def _suggest_param(self, trial: optuna.Trial, param_name: str, param_def: Dict[str, Any]):
        """Suggest parameter value for trial"""
        if param_def['type'] == 'int':
            return trial.suggest_int(param_name, param_def['low'], param_def['high'])
        elif param_def['type'] == 'float':
            return trial.suggest_float(param_name, param_def['low'], param_def['high'])
        else:
            return trial.suggest_categorical(param_name, param_def['choices'])
    
    def optimize(
        self,
        num_trials: int = 100,
        n_jobs: int = 4,
        timeout: Optional[float] = None,
        output_dir: str = "optimization_results"
    ) -> OptimizationResult:
        """
        Run optimization.
        
        Args:
            num_trials: Number of trials
            n_jobs: Number of parallel jobs
            timeout: Timeout in seconds
            output_dir: Output directory
            
        Returns:
            OptimizationResult
        """
        logger.info("="*60)
        logger.info("ADVANCED HYPERPARAMETER OPTIMIZATION")
        logger.info("="*60)
        logger.info(f"Strategy: {self.strategy_cls.__name__}")
        logger.info(f"Symbols: {', '.join(self.symbols)}")
        logger.info(f"Date range: {self.start_date} to {self.end_date}")
        logger.info(f"Scoring metric: {self.scoring}")
        logger.info(f"Trials: {num_trials}, Parallel jobs: {n_jobs}")
        
        os.makedirs(output_dir, exist_ok=True)
        study_db = f"{output_dir}/study.db"
        
        # Create study
        study = optuna.create_study(
            direction='maximize',
            sampler=TPESampler(seed=42),
            pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=10),
            study_name=f"{self.strategy_cls.__name__}_optimization",
            storage=f"sqlite:///{study_db}",
            load_if_exists=True
        )
        
        # Objective function
        def objective(trial: optuna.Trial) -> float:
            # Suggest parameters
            params = {}
            for param_name, param_def in self.optuna_space.items():
                params[param_name] = self._suggest_param(trial, param_name, param_def)
            
            try:
                # Run backtest
                metrics = self._evaluate_params(params)
                
                # Calculate score
                if self.custom_scorer:
                    score = self.custom_scorer(metrics)
                else:
                    score = self._calculate_score(metrics)
                
                return score
            
            except Exception as e:
                logger.warning(f"Trial failed: {e}")
                return float('-inf')
        
        # Run optimization
        logger.info("Starting optimization...")
        study.optimize(
            objective,
            n_trials=num_trials,
            n_jobs=n_jobs,
            timeout=timeout,
            show_progress_bar=True
        )
        
        # Get results
        best_params = study.best_params
        best_value = study.best_value
        
        logger.info(f"\nOptimization complete!")
        logger.info(f"Best score: {best_value:.4f}")
        logger.info(f"Best parameters: {best_params}")
        
        # Generate history DataFrame
        history = self._get_history(study)
        
        # Generate visualizations
        self._generate_plots(study, output_dir)
        
        # Save results
        self._save_results(study, best_params, best_value, history, output_dir)
        
        return OptimizationResult(
            best_params=best_params,
            best_value=best_value,
            n_trials=len(study.trials),
            study=study,
            history=history
        )
    
    def _evaluate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate parameter set"""
        # Create strategy with parameters
        strategy = self.strategy_cls(**params)
        
        # Create backtest engine
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=self.initial_capital,
            data_dir=self.data_dir,
            replay_mode=ReplayMode.TICK,
            replay_speed=ReplaySpeed.INSTANT
        )
        
        # Run backtest
        engine.run(
            symbols=self.symbols,
            start_date=self.start_date,
            end_date=self.end_date
        )
        
        # Get results
        results = engine.get_results()
        
        return results
    
    def _calculate_score(self, metrics: Dict[str, Any]) -> float:
        """Calculate score based on selected metric"""
        if self.scoring == "sharpe":
            return metrics.get('sharpe', 0.0)
        elif self.scoring == "sortino":
            return metrics.get('sortino', 0.0)
        elif self.scoring == "pnl":
            return metrics.get('total_pnl', 0.0)
        elif self.scoring == "winrate":
            return metrics.get('win_rate', 0.0)
        elif self.scoring == "profit_factor":
            return metrics.get('profit_factor', 0.0)
        elif self.scoring == "drawdown_adjusted_return":
            pnl = metrics.get('total_pnl', 0.0)
            drawdown = abs(metrics.get('max_drawdown', 0.01))
            if drawdown > 0:
                return pnl / drawdown
            return 0.0
        else:
            logger.warning(f"Unknown scoring metric: {self.scoring}, using sharpe")
            return metrics.get('sharpe', 0.0)
    
    def _get_history(self, study: optuna.Study) -> pd.DataFrame:
        """Get optimization history as DataFrame"""
        trials = study.trials
        
        data = []
        for trial in trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                row = {
                    'trial': trial.number,
                    'value': trial.value,
                    'state': trial.state.name
                }
                row.update(trial.params)
                data.append(row)
        
        return pd.DataFrame(data)
    
    def _generate_plots(self, study: optuna.Study, output_dir: str):
        """Generate optimization visualization plots"""
        logger.info("Generating optimization plots...")
        
        if not HAS_PLOTLY:
            logger.warning("Plotly not available, skipping visualization plots")
            return
        
        try:
            # Parameter importance
            fig = plot_param_importances(study)
            if hasattr(fig, 'write_image'):
                fig.write_image(f"{output_dir}/optimization_plot_param_importance.png")
            else:
                fig.write_html(f"{output_dir}/optimization_plot_param_importance.html")
            
            # Parallel coordinate
            if len(study.trials) > 0:
                fig = plot_parallel_coordinate(study)
                if hasattr(fig, 'write_image'):
                    fig.write_image(f"{output_dir}/optimization_plot_parallel_coords.png")
                else:
                    fig.write_html(f"{output_dir}/optimization_plot_parallel_coords.html")
                
                # Slice plot
                fig = plot_slice(study)
                if hasattr(fig, 'write_image'):
                    fig.write_image(f"{output_dir}/optimization_plot_slice.png")
                else:
                    fig.write_html(f"{output_dir}/optimization_plot_slice.html")
        
        except Exception as e:
            logger.warning(f"Error generating plots: {e}")
    
    def _save_results(
        self,
        study: optuna.Study,
        best_params: Dict[str, Any],
        best_value: float,
        history: pd.DataFrame,
        output_dir: str
    ):
        """Save optimization results"""
        # Best parameters
        with open(f"{output_dir}/best_params.json", 'w') as f:
            json.dump(best_params, f, indent=2)
        
        # Summary
        summary = {
            'best_params': best_params,
            'best_value': best_value,
            'n_trials': len(study.trials),
            'scoring_metric': self.scoring,
            'strategy': self.strategy_cls.__name__,
            'symbols': self.symbols,
            'date_range': {
                'start': self.start_date,
                'end': self.end_date
            }
        }
        
        with open(f"{output_dir}/optimization_summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
        # History CSV
        history.to_csv(f"{output_dir}/optimization_history.csv", index=False)
        
        logger.info(f"Results saved to: {output_dir}")

