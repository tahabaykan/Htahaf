"""app/risk/monte_carlo.py

Monte Carlo Simulation for risk analysis.
Simulates portfolio returns under different scenarios.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional
from app.core.logger import logger

try:
    from joblib import Parallel, delayed
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False
    logger.warning("joblib not available, Monte Carlo will run sequentially")


@dataclass
class MonteCarloResult:
    """Result of Monte Carlo simulation"""
    simulations: int
    horizon: int
    max_drawdowns: List[float]
    ending_values: List[float]
    var_95: float
    cvar_95: float
    worst_1pct: float
    median_return: float
    mean_return: float


class MonteCarloEngine:
    """
    Monte Carlo simulation engine for risk analysis.
    
    Simulates portfolio returns under different scenarios:
    - Bootstrap: Resample from historical returns
    - GBM: Geometric Brownian Motion
    - Regime: Volatility regime switching
    """
    
    def __init__(
        self,
        returns: pd.Series,
        simulations: int = 10000,
        horizon: int = 252,
        n_jobs: int = -1,
    ):
        """
        Initialize Monte Carlo engine.
        
        Args:
            returns: Historical returns series
            simulations: Number of simulations to run
            horizon: Time horizon (days)
            n_jobs: Number of parallel jobs (-1 = all cores)
        """
        self.returns = returns.dropna().values
        self.simulations = simulations
        self.horizon = horizon
        self.n_jobs = n_jobs if HAS_JOBLIB else 1
        
        if len(self.returns) == 0:
            raise ValueError("No valid returns provided")
    
    # -------------------------------
    # BOOTSTRAP MODEL
    # -------------------------------
    def _simulate_bootstrap(self):
        """Bootstrap simulation: resample from historical returns"""
        sampled = np.random.choice(self.returns, size=self.horizon, replace=True)
        equity = np.cumprod(1 + sampled)
        max_dd = self._max_drawdown(equity)
        return equity[-1], max_dd
    
    # -------------------------------
    # GEOMETRIC BROWNIAN MOTION
    # -------------------------------
    def _simulate_gbm(self):
        """Geometric Brownian Motion simulation"""
        mu = np.mean(self.returns)
        sigma = np.std(self.returns)
        shocks = np.random.normal(mu, sigma, self.horizon)
        equity = np.cumprod(1 + shocks)
        max_dd = self._max_drawdown(equity)
        return equity[-1], max_dd
    
    # -------------------------------
    # VOLATILITY REGIME SWITCHING
    # -------------------------------
    def _simulate_regime(self):
        """Volatility regime switching simulation"""
        mu = np.mean(self.returns)
        sigma_normal = np.std(self.returns)
        sigma_stress = sigma_normal * 2.5  # high vol regime
        
        equity = [1.0]
        for _ in range(self.horizon):
            # 15% chance of high volatility regime
            if np.random.rand() < 0.15:
                shock = np.random.normal(mu, sigma_stress)
            else:
                shock = np.random.normal(mu, sigma_normal)
            equity.append(equity[-1] * (1 + shock))
        
        equity = np.array(equity)
        max_dd = self._max_drawdown(equity)
        return equity[-1], max_dd
    
    # -------------------------------
    # MAX DRAWDOWN HELPER
    # -------------------------------
    @staticmethod
    def _max_drawdown(series):
        """Calculate maximum drawdown"""
        peak = -np.inf
        max_dd = 0
        for x in series:
            peak = max(peak, x)
            dd = (x - peak) / peak
            max_dd = min(max_dd, dd)
        return abs(max_dd)
    
    # -------------------------------
    # MAIN EXECUTION
    # -------------------------------
    def run(self, model: str = "bootstrap") -> MonteCarloResult:
        """
        Run Monte Carlo simulation.
        
        Args:
            model: Simulation model ("bootstrap", "gbm", "regime")
            
        Returns:
            MonteCarloResult
        """
        logger.info(f"Running Monte Carlo simulation: {model}")
        logger.info(f"  Simulations: {self.simulations:,}")
        logger.info(f"  Horizon: {self.horizon} days")
        logger.info(f"  Parallel jobs: {self.n_jobs}")
        
        if model == "bootstrap":
            sim_func = self._simulate_bootstrap
        elif model == "gbm":
            sim_func = self._simulate_gbm
        elif model == "regime":
            sim_func = self._simulate_regime
        else:
            raise ValueError(f"Unknown model: {model}. Use 'bootstrap', 'gbm', or 'regime'")
        
        # Run simulations
        if HAS_JOBLIB and self.n_jobs != 1:
            logger.info("Running parallel simulations...")
            results = Parallel(n_jobs=self.n_jobs)(
                delayed(sim_func)() for _ in range(self.simulations)
            )
        else:
            logger.info("Running sequential simulations...")
            results = [sim_func() for _ in range(self.simulations)]
        
        end_vals, drawdowns = zip(*results)
        
        # Calculate statistics
        end_vals = np.array(end_vals)
        drawdowns = np.array(drawdowns)
        
        var_95 = np.percentile(end_vals, 5)
        cvar_95 = np.mean([x for x in end_vals if x <= var_95])
        worst_1pct = np.percentile(end_vals, 1)
        
        result = MonteCarloResult(
            simulations=self.simulations,
            horizon=self.horizon,
            max_drawdowns=drawdowns.tolist(),
            ending_values=end_vals.tolist(),
            var_95=float(var_95),
            cvar_95=float(cvar_95),
            worst_1pct=float(worst_1pct),
            median_return=float(np.median(end_vals)),
            mean_return=float(np.mean(end_vals))
        )
        
        logger.info(f"Simulation complete!")
        logger.info(f"  Mean return: {result.mean_return:.4f}")
        logger.info(f"  Median return: {result.median_return:.4f}")
        logger.info(f"  VaR (95%): {result.var_95:.4f}")
        logger.info(f"  CVaR (95%): {result.cvar_95:.4f}")
        logger.info(f"  Worst 1%: {result.worst_1pct:.4f}")
        
        return result








