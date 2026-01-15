"""app/backtest/report_generator.py

Report generator for backtest results.
Generates CSV files and summary reports.
"""

import csv
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.core.logger import logger
from app.backtest.metrics_calculator import MetricsCalculator


class ReportGenerator:
    """
    Generate backtest reports.
    
    Outputs:
    - trade_log.csv
    - position_log.csv
    - equity_curve.csv
    - metrics.json
    - summary.txt
    """
    
    def __init__(self, output_dir: str = "backtest_results"):
        """
        Initialize report generator.
        
        Args:
            output_dir: Directory to save reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.trades: List[Dict[str, Any]] = []
        self.positions: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
    
    def add_trade(self, trade: Dict[str, Any]):
        """Add trade to log"""
        self.trades.append(trade)
    
    def add_position(self, position: Dict[str, Any]):
        """Add position snapshot to log"""
        self.positions.append(position)
    
    def add_equity_point(self, timestamp: float, equity: float):
        """Add equity curve point"""
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': equity
        })
    
    def generate_all(self, metrics: Dict[str, Any], strategy_name: str = "Unknown"):
        """
        Generate all reports.
        
        Args:
            metrics: Metrics dict from MetricsCalculator
            strategy_name: Strategy name
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"{strategy_name}_{timestamp}"
        
        # Generate CSV files
        self.generate_trade_log(f"{prefix}_trade_log.csv")
        self.generate_position_log(f"{prefix}_position_log.csv")
        self.generate_equity_curve(f"{prefix}_equity_curve.csv")
        
        # Generate JSON metrics
        self.generate_metrics_json(metrics, f"{prefix}_metrics.json")
        
        # Generate summary
        self.generate_summary(metrics, strategy_name, f"{prefix}_summary.txt")
        
        logger.info(f"Reports generated in: {self.output_dir}")
    
    def generate_trade_log(self, filename: str):
        """Generate trade log CSV"""
        filepath = self.output_dir / filename
        
        if not self.trades:
            logger.warning("No trades to log")
            return
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'entry_time', 'exit_time', 'symbol', 'side', 'entry_price',
                'exit_price', 'qty', 'pnl', 'commission', 'net_pnl',
                'entry_reason', 'exit_reason', 'holding_duration_hours'
            ])
            writer.writeheader()
            
            for trade in self.trades:
                row = {
                    'entry_time': trade.get('entry_time', ''),
                    'exit_time': trade.get('exit_time', ''),
                    'symbol': trade.get('symbol', ''),
                    'side': trade.get('side', ''),
                    'entry_price': trade.get('entry_price', 0),
                    'exit_price': trade.get('exit_price', 0),
                    'qty': trade.get('qty', 0),
                    'pnl': trade.get('pnl', 0),
                    'commission': trade.get('commission', 0),
                    'net_pnl': trade.get('pnl', 0) - trade.get('commission', 0),
                    'entry_reason': trade.get('entry_reason', ''),
                    'exit_reason': trade.get('exit_reason', ''),
                    'holding_duration_hours': trade.get('holding_duration_hours', 0)
                }
                writer.writerow(row)
        
        logger.info(f"Trade log saved: {filepath}")
    
    def generate_position_log(self, filename: str):
        """Generate position log CSV"""
        filepath = self.output_dir / filename
        
        if not self.positions:
            logger.warning("No positions to log")
            return
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'symbol', 'qty', 'avg_price', 'market_price',
                'unrealized_pnl', 'realized_pnl', 'total_pnl'
            ])
            writer.writeheader()
            
            for pos in self.positions:
                writer.writerow(pos)
        
        logger.info(f"Position log saved: {filepath}")
    
    def generate_equity_curve(self, filename: str):
        """Generate equity curve CSV"""
        filepath = self.output_dir / filename
        
        if not self.equity_curve:
            logger.warning("No equity curve data")
            return
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['timestamp', 'equity', 'return_pct', 'drawdown_pct'])
            writer.writeheader()
            
            peak = self.equity_curve[0]['equity']
            initial = self.equity_curve[0]['equity']
            
            for point in self.equity_curve:
                equity = point['equity']
                if equity > peak:
                    peak = equity
                
                return_pct = ((equity - initial) / initial * 100) if initial > 0 else 0
                drawdown_pct = ((peak - equity) / peak * 100) if peak > 0 else 0
                
                writer.writerow({
                    'timestamp': point['timestamp'],
                    'equity': equity,
                    'return_pct': return_pct,
                    'drawdown_pct': drawdown_pct
                })
        
        logger.info(f"Equity curve saved: {filepath}")
    
    def generate_metrics_json(self, metrics: Dict[str, Any], filename: str):
        """Generate metrics JSON"""
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        logger.info(f"Metrics JSON saved: {filepath}")
    
    def generate_summary(self, metrics: Dict[str, Any], strategy_name: str, filename: str):
        """Generate text summary"""
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            f.write("="*60 + "\n")
            f.write(f"BACKTEST SUMMARY - {strategy_name}\n")
            f.write("="*60 + "\n\n")
            
            f.write("PERFORMANCE METRICS\n")
            f.write("-"*60 + "\n")
            f.write(f"Initial Capital:      ${metrics['initial_capital']:,.2f}\n")
            f.write(f"Final Equity:          ${metrics['final_equity']:,.2f}\n")
            f.write(f"Total Return:          {metrics['total_return_pct']:.2f}%\n")
            f.write(f"Total P&L:             ${metrics['net_pnl']:,.2f}\n")
            f.write(f"Total Commission:      ${metrics['total_commission']:,.2f}\n\n")
            
            f.write("TRADE STATISTICS\n")
            f.write("-"*60 + "\n")
            f.write(f"Total Trades:          {metrics['total_trades']}\n")
            f.write(f"Winning Trades:        {metrics['winning_trades']}\n")
            f.write(f"Losing Trades:         {metrics['losing_trades']}\n")
            f.write(f"Win Rate:              {metrics['win_rate_pct']:.2f}%\n")
            f.write(f"Average Win:           ${metrics['avg_win']:,.2f}\n")
            f.write(f"Average Loss:          ${metrics['avg_loss']:,.2f}\n")
            f.write(f"Largest Win:           ${metrics['largest_win']:,.2f}\n")
            f.write(f"Largest Loss:          ${metrics['largest_loss']:,.2f}\n")
            f.write(f"Profit Factor:         {metrics['profit_factor']:.2f}\n")
            f.write(f"Avg Trade Length:      {metrics['avg_trade_length_hours']:.2f} hours\n\n")
            
            f.write("RISK METRICS\n")
            f.write("-"*60 + "\n")
            f.write(f"Max Drawdown:          ${metrics['max_drawdown']:,.2f}\n")
            f.write(f"Max Drawdown %:        {metrics['max_drawdown_pct']:.2f}%\n")
            f.write(f"Sharpe Ratio:          {metrics['sharpe_ratio']:.2f}\n")
            f.write(f"Sortino Ratio:         {metrics['sortino_ratio']:.2f}\n")
            f.write(f"Exposure Time:         {metrics['exposure_time_pct']:.2f}%\n")
            f.write("="*60 + "\n")
        
        logger.info(f"Summary saved: {filepath}")








