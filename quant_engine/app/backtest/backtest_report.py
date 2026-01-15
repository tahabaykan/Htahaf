"""app/backtest/backtest_report.py

Backtest reporting module - generates trade logs, equity curves, and metrics.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json
import os


@dataclass
class Trade:
    """Completed trade"""
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    entry_time: float
    exit_time: float
    duration_s: float
    entry_slippage: float = 0.0
    exit_slippage: float = 0.0
    entry_commission: float = 0.0
    exit_commission: float = 0.0
    effective_entry_price: float = 0.0
    effective_exit_price: float = 0.0


@dataclass
class BacktestReport:
    """Backtest report generator"""
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Dict] = field(default_factory=list)
    
    # ------------------------------------------------------------
    # ADD TRADE
    # ------------------------------------------------------------
    def add_trade(self, **kwargs):
        """Add completed trade"""
        self.trades.append(Trade(**kwargs))
    
    # ------------------------------------------------------------
    # ADD EQUITY POINT
    # ------------------------------------------------------------
    def add_equity_point(self, timestamp: float, equity: float):
        """Add equity curve point"""
        self.equity_curve.append({"timestamp": timestamp, "equity": equity})
    
    # ------------------------------------------------------------
    # EXPORT TRADE LOG
    # ------------------------------------------------------------
    def save_trade_log(self, path: str):
        """Save trade log to CSV"""
        if not self.trades:
            return None
        
        df = pd.DataFrame([t.__dict__ for t in self.trades])
        df.to_csv(path, index=False)
        return df
    
    # ------------------------------------------------------------
    # EXPORT EQUITY CURVE
    # ------------------------------------------------------------
    def save_equity_curve(self, path: str):
        """Save equity curve to CSV"""
        if not self.equity_curve:
            return None
        
        df = pd.DataFrame(self.equity_curve)
        df.to_csv(path, index=False)
        return df
    
    # ------------------------------------------------------------
    # PERFORMANCE METRICS
    # ------------------------------------------------------------
    def compute_metrics(self, equity_df: pd.DataFrame):
        """Compute performance metrics from equity curve"""
        metrics = {}
        
        # Returns
        equity_df["returns"] = equity_df["equity"].pct_change().fillna(0)
        
        # CAGR
        start_val = equity_df["equity"].iloc[0]
        end_val = equity_df["equity"].iloc[-1]
        duration_days = (equity_df["timestamp"].iloc[-1] - equity_df["timestamp"].iloc[0]) / (60 * 60 * 24)
        years = max(duration_days / 365, 1e-9)
        metrics["CAGR"] = (end_val / start_val) ** (1 / years) - 1
        
        # Volatility
        metrics["volatility"] = np.std(equity_df["returns"]) * np.sqrt(252)
        
        # Sharpe
        if metrics["volatility"] > 0:
            metrics["sharpe"] = metrics["CAGR"] / metrics["volatility"]
        else:
            metrics["sharpe"] = 0
        
        # Sortino
        downside = equity_df.loc[equity_df["returns"] < 0, "returns"]
        if len(downside) > 0:
            downside_std = np.std(downside) * np.sqrt(252)
            metrics["sortino"] = metrics["CAGR"] / downside_std
        else:
            metrics["sortino"] = 0
        
        # Max drawdown
        curve = equity_df["equity"].values
        rolling_max = np.maximum.accumulate(curve)
        drawdowns = (curve - rolling_max) / rolling_max
        metrics["max_drawdown"] = drawdowns.min()
        
        return metrics
    
    # ------------------------------------------------------------
    # COMPUTE TRADE METRICS
    # ------------------------------------------------------------
    def compute_trade_metrics(self):
        """Compute trade statistics"""
        if not self.trades:
            return {}
        
        df = pd.DataFrame([t.__dict__ for t in self.trades])
        
        wins = df[df["pnl"] > 0]
        losses = df[df["pnl"] < 0]
        
        stats = {
            "num_trades": len(df),
            "win_rate": len(wins) / len(df) if len(df) > 0 else 0,
            "avg_win": wins["pnl"].mean() if len(wins) > 0 else 0,
            "avg_loss": losses["pnl"].mean() if len(losses) > 0 else 0,
            "profit_factor": wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) > 0 else float("inf"),
            "max_win": df["pnl"].max(),
            "max_loss": df["pnl"].min(),
            "gross_profit": df[df["pnl"] > 0]["pnl"].sum(),
            "gross_loss": df[df["pnl"] < 0]["pnl"].sum(),
            "total_pnl": df["pnl"].sum(),
            "avg_duration_s": df["duration_s"].mean(),
        }
        
        return stats
    
    # ------------------------------------------------------------
    # EXPORT ALL METRICS
    # ------------------------------------------------------------
    def save_metrics(self, path: str, equity_df: pd.DataFrame):
        """Save all metrics to JSON"""
        metrics = self.compute_metrics(equity_df)
        trade_stats = self.compute_trade_metrics()
        
        full = {
            "equity_metrics": metrics,
            "trade_metrics": trade_stats,
        }
        
        with open(path, "w") as f:
            json.dump(full, f, indent=4)
        
        return full
    
    # ------------------------------------------------------------
    # FULL SAVE PROCESS
    # ------------------------------------------------------------
    def save_all(self, output_dir: str):
        """Save all reports to directory"""
        os.makedirs(output_dir, exist_ok=True)
        
        trade_df = self.save_trade_log(f"{output_dir}/trade_log.csv")
        equity_df = self.save_equity_curve(f"{output_dir}/equity_curve.csv")
        
        if equity_df is not None:
            self.save_metrics(f"{output_dir}/metrics.json", equity_df)
        
        return {
            "trade_log": trade_df,
            "equity_curve": equity_df,
        }

