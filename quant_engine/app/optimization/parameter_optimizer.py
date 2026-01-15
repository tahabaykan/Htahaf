"""app/optimization/parameter_optimizer.py

Parameter optimizer for strategy parameter tuning.
Supports grid search and random search.
"""

import random
import itertools
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from app.core.logger import logger
from app.strategy.strategy_base import StrategyBase
from app.backtest.backtest_engine import BacktestEngine
from app.backtest.replay_engine import ReplayMode, ReplaySpeed


class SearchMethod(Enum):
    """Search method for parameter optimization"""
    GRID = "grid"
    RANDOM = "random"


class ScoringMetric(Enum):
    """Scoring metric for parameter evaluation"""
    PNL = "pnl"
    SHARPE = "sharpe"
    SORTINO = "sortino"
    DRAWDOWN = "drawdown"
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    WEIGHTED = "weighted"  # Weighted combination


@dataclass
class OptimizationResult:
    """Result of parameter optimization"""
    best_params: Dict[str, Any]
    best_score: float
    all_results: List[Dict[str, Any]]
    num_evaluations: int


class ParameterOptimizer:
    """
    Parameter optimizer for strategy tuning.
    
    Supports:
    - Grid search (exhaustive)
    - Random search (sampling)
    - Multiple scoring metrics
    """
    
    def __init__(
        self,
        search_method: SearchMethod = SearchMethod.GRID,
        scoring_metric: ScoringMetric = ScoringMetric.WEIGHTED,
        max_evaluations: Optional[int] = None,
        random_seed: Optional[int] = None
    ):
        """
        Initialize parameter optimizer.
        
        Args:
            search_method: GRID or RANDOM
            scoring_metric: Metric to optimize
            max_evaluations: Max evaluations for random search
            random_seed: Random seed for reproducibility
        """
        self.search_method = search_method
        self.scoring_metric = scoring_metric
        self.max_evaluations = max_evaluations
        self.random_seed = random_seed
        
        if random_seed:
            random.seed(random_seed)
    
    def optimize(
        self,
        strategy_class: type,
        param_space: Dict[str, List[Any]],
        symbols: List[str],
        start_date: str,
        end_date: str,
        initial_capital: float = 100000.0,
        data_dir: str = "data/historical"
    ) -> OptimizationResult:
        """
        Optimize strategy parameters.
        
        Args:
            strategy_class: Strategy class to optimize
            param_space: Parameter space {param_name: [values]}
            symbols: List of symbols to test
            start_date: Training start date
            end_date: Training end date
            initial_capital: Initial capital
            data_dir: Data directory
            
        Returns:
            OptimizationResult with best parameters
        """
        logger.info(f"Starting parameter optimization ({self.search_method.value})")
        logger.info(f"Parameter space: {list(param_space.keys())}")
        
        # Generate parameter combinations
        if self.search_method == SearchMethod.GRID:
            param_combinations = list(itertools.product(*param_space.values()))
        else:
            # Random search
            num_combinations = self._count_combinations(param_space)
            max_evals = self.max_evaluations or min(100, num_combinations)
            param_combinations = self._sample_random(param_space, max_evals)
        
        logger.info(f"Evaluating {len(param_combinations)} parameter combinations")
        
        results = []
        best_score = float('-inf')
        best_params = None
        
        for i, param_values in enumerate(param_combinations):
            params = dict(zip(param_space.keys(), param_values))
            
            try:
                score, metrics = self._evaluate_params(
                    strategy_class,
                    params,
                    symbols,
                    start_date,
                    end_date,
                    initial_capital,
                    data_dir
                )
                
                result = {
                    'params': params,
                    'score': score,
                    'metrics': metrics
                }
                results.append(result)
                
                if score > best_score:
                    best_score = score
                    best_params = params
                
                if (i + 1) % 10 == 0:
                    logger.info(f"Evaluated {i + 1}/{len(param_combinations)} combinations")
            
            except Exception as e:
                logger.warning(f"Error evaluating params {params}: {e}")
                continue
        
        logger.info(f"Optimization complete. Best score: {best_score:.4f}")
        logger.info(f"Best parameters: {best_params}")
        
        return OptimizationResult(
            best_params=best_params or {},
            best_score=best_score,
            all_results=results,
            num_evaluations=len(results)
        )
    
    def _evaluate_params(
        self,
        strategy_class: type,
        params: Dict[str, Any],
        symbols: List[str],
        start_date: str,
        end_date: str,
        initial_capital: float,
        data_dir: str
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate a parameter set.
        
        Returns:
            Tuple of (score, metrics_dict)
        """
        # Create strategy instance with parameters
        strategy = strategy_class(**params)
        
        # Create backtest engine
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=initial_capital,
            data_dir=data_dir,
            replay_mode=ReplayMode.TICK,
            replay_speed=ReplaySpeed.INSTANT
        )
        
        # Run backtest
        engine.run(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date
        )
        
        # Get results
        results = engine.get_results()
        
        # Calculate score based on metric
        score = self._calculate_score(results)
        
        # Extract metrics
        metrics = {
            'total_pnl': results.get('total_pnl', 0),
            'sharpe': results.get('sharpe', 0),
            'sortino': results.get('sortino', 0),
            'max_drawdown': results.get('max_drawdown', 0),
            'win_rate': results.get('win_rate', 0),
            'profit_factor': results.get('profit_factor', 0)
        }
        
        return score, metrics
    
    def _calculate_score(self, results: Dict[str, Any]) -> float:
        """Calculate score based on selected metric"""
        if self.scoring_metric == ScoringMetric.PNL:
            return results.get('total_pnl', 0)
        elif self.scoring_metric == ScoringMetric.SHARPE:
            return results.get('sharpe', 0)
        elif self.scoring_metric == ScoringMetric.SORTINO:
            return results.get('sortino', 0)
        elif self.scoring_metric == ScoringMetric.DRAWDOWN:
            # Negative drawdown (lower is better)
            return -abs(results.get('max_drawdown', 0))
        elif self.scoring_metric == ScoringMetric.WIN_RATE:
            return results.get('win_rate', 0)
        elif self.scoring_metric == ScoringMetric.PROFIT_FACTOR:
            return results.get('profit_factor', 0)
        elif self.scoring_metric == ScoringMetric.WEIGHTED:
            # Weighted combination
            sharpe = results.get('sharpe', 0)
            pnl = results.get('total_pnl', 0) / 1000.0  # Normalize
            drawdown = -abs(results.get('max_drawdown', 0))
            win_rate = results.get('win_rate', 0)
            
            # Weights: sharpe=0.4, pnl=0.3, drawdown=0.2, win_rate=0.1
            score = 0.4 * sharpe + 0.3 * pnl + 0.2 * drawdown + 0.1 * win_rate
            return score
        else:
            return 0.0
    
    def _count_combinations(self, param_space: Dict[str, List[Any]]) -> int:
        """Count total parameter combinations"""
        count = 1
        for values in param_space.values():
            count *= len(values)
        return count
    
    def _sample_random(self, param_space: Dict[str, List[Any]], n: int) -> List[tuple]:
        """Sample n random parameter combinations"""
        combinations = []
        seen = set()
        
        while len(combinations) < n:
            combo = tuple(random.choice(values) for values in param_space.values())
            if combo not in seen:
                combinations.append(combo)
                seen.add(combo)
        
        return combinations








