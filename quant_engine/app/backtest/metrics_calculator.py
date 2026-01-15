"""app/backtest/metrics_calculator.py

Metrics calculator for backtest results.
Calculates performance metrics, drawdown, Sharpe, Sortino, etc.
"""

import math
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from app.core.logger import logger


class MetricsCalculator:
    """
    Calculate backtest performance metrics.
    
    Metrics:
    - Total P&L
    - Max drawdown
    - Win rate
    - Profit factor
    - Sharpe ratio
    - Sortino ratio
    - Average trade length
    - Exposure time
    """
    
    def __init__(self, initial_capital: float = 100000.0):
        """
        Initialize metrics calculator.
        
        Args:
            initial_capital: Starting capital
        """
        self.initial_capital = initial_capital
        self.trades: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
    
    def add_trade(self, trade: Dict[str, Any]):
        """
        Add completed trade.
        
        Args:
            trade: Trade dict with keys: entry_time, exit_time, entry_price, exit_price,
                   qty, pnl, commission, symbol, side, entry_reason, exit_reason
        """
        self.trades.append(trade)
    
    def add_equity_point(self, timestamp: float, equity: float):
        """
        Add equity curve point.
        
        Args:
            timestamp: Timestamp
            equity: Equity value at this point
        """
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': equity
        })
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """Calculate all metrics"""
        if not self.trades:
            return self._empty_metrics()
        
        # Basic P&L metrics
        total_pnl = sum(t['pnl'] for t in self.trades)
        total_commission = sum(t.get('commission', 0) for t in self.trades)
        net_pnl = total_pnl - total_commission
        
        # Win/loss metrics
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] < 0]
        
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        total_trades = len(self.trades)
        
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = sum(t['pnl'] for t in winning_trades) / win_count if win_count > 0 else 0
        avg_loss = sum(t['pnl'] for t in losing_trades) / loss_count if loss_count > 0 else 0
        
        # Profit factor
        gross_profit = sum(t['pnl'] for t in winning_trades)
        gross_loss = abs(sum(t['pnl'] for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Trade length
        trade_lengths = [
            (t['exit_time'] - t['entry_time']) / 3600  # Convert to hours
            for t in self.trades
            if 'entry_time' in t and 'exit_time' in t
        ]
        avg_trade_length = sum(trade_lengths) / len(trade_lengths) if trade_lengths else 0
        
        # Returns and risk metrics
        returns = self._calculate_returns()
        sharpe = self._calculate_sharpe(returns)
        sortino = self._calculate_sortino(returns)
        
        # Drawdown
        max_drawdown, max_drawdown_pct = self._calculate_drawdown()
        
        # Exposure time
        exposure_time = self._calculate_exposure_time()
        
        return {
            'initial_capital': self.initial_capital,
            'final_equity': self.initial_capital + net_pnl,
            'total_pnl': total_pnl,
            'net_pnl': net_pnl,
            'total_commission': total_commission,
            'total_return_pct': (net_pnl / self.initial_capital * 100) if self.initial_capital > 0 else 0,
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate_pct': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'largest_win': max((t['pnl'] for t in winning_trades), default=0),
            'largest_loss': min((t['pnl'] for t in losing_trades), default=0),
            'profit_factor': profit_factor,
            'avg_trade_length_hours': avg_trade_length,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'exposure_time_pct': exposure_time
        }
    
    def _calculate_returns(self) -> List[float]:
        """Calculate periodic returns from equity curve"""
        if len(self.equity_curve) < 2:
            return []
        
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev_equity = self.equity_curve[i-1]['equity']
            curr_equity = self.equity_curve[i]['equity']
            if prev_equity > 0:
                ret = (curr_equity - prev_equity) / prev_equity
                returns.append(ret)
        
        return returns
    
    def _calculate_sharpe(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio"""
        if not returns:
            return 0.0
        
        excess_returns = [r - risk_free_rate for r in returns]
        avg_return = sum(excess_returns) / len(excess_returns)
        std_dev = math.sqrt(sum((r - avg_return) ** 2 for r in excess_returns) / len(excess_returns))
        
        if std_dev == 0:
            return 0.0
        
        # Annualize (assuming daily returns)
        sharpe = (avg_return / std_dev) * math.sqrt(252)
        return sharpe
    
    def _calculate_sortino(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sortino ratio (downside deviation only)"""
        if not returns:
            return 0.0
        
        excess_returns = [r - risk_free_rate for r in returns]
        avg_return = sum(excess_returns) / len(excess_returns)
        
        # Downside deviation (only negative returns)
        downside_returns = [r for r in excess_returns if r < 0]
        if not downside_returns:
            return float('inf') if avg_return > 0 else 0.0
        
        downside_std = math.sqrt(sum(r ** 2 for r in downside_returns) / len(downside_returns))
        
        if downside_std == 0:
            return 0.0
        
        # Annualize
        sortino = (avg_return / downside_std) * math.sqrt(252)
        return sortino
    
    def _calculate_drawdown(self) -> tuple:
        """Calculate maximum drawdown"""
        if not self.equity_curve:
            return 0.0, 0.0
        
        equity_values = [p['equity'] for p in self.equity_curve]
        peak = equity_values[0]
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        
        for equity in equity_values:
            if equity > peak:
                peak = equity
            
            drawdown = peak - equity
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0
            
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct
        
        return max_drawdown, max_drawdown_pct
    
    def _calculate_exposure_time(self) -> float:
        """Calculate percentage of time in market"""
        if not self.trades:
            return 0.0
        
        # Calculate total time in positions
        total_time = 0.0
        for trade in self.trades:
            if 'entry_time' in trade and 'exit_time' in trade:
                total_time += (trade['exit_time'] - trade['entry_time'])
        
        # Calculate total backtest time
        if self.equity_curve:
            total_backtest_time = self.equity_curve[-1]['timestamp'] - self.equity_curve[0]['timestamp']
            if total_backtest_time > 0:
                return (total_time / total_backtest_time * 100)
        
        return 0.0
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics dict"""
        return {
            'initial_capital': self.initial_capital,
            'final_equity': self.initial_capital,
            'total_pnl': 0.0,
            'net_pnl': 0.0,
            'total_commission': 0.0,
            'total_return_pct': 0.0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate_pct': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'profit_factor': 0.0,
            'avg_trade_length_hours': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'max_drawdown': 0.0,
            'max_drawdown_pct': 0.0,
            'exposure_time_pct': 0.0
        }








