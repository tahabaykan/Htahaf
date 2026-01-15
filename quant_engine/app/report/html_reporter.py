"""app/report/html_reporter.py

HTML report generator for backtests and optimization results.
Generates professional HTML dashboards with charts and tables.
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, Any, Optional
from datetime import datetime
from jinja2 import Template

from app.core.logger import logger


class HTMLReportGenerator:
    """
    HTML report generator for backtest results.
    
    Generates:
    - HTML dashboard with charts and tables
    - PNG charts (equity curve, drawdown, etc.)
    - CSV/JSON data files
    """
    
    def __init__(self, output_dir: str = "reports"):
        """
        Initialize HTML report generator.
        
        Args:
            output_dir: Base output directory
        """
        self.output_dir = output_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_dir = f"{output_dir}/{self.timestamp}"
        
        # Set style
        sns.set_style("whitegrid")
        plt.style.use('seaborn-v0_8-darkgrid')
    
    def generate(
        self,
        backtest_result: Dict[str, Any],
        strategy_name: str = "Strategy",
        symbols: Optional[list] = None
    ):
        """
        Generate complete HTML report.
        
        Args:
            backtest_result: Backtest results dictionary
            strategy_name: Strategy name
            symbols: List of symbols tested
        """
        logger.info(f"Generating HTML report in {self.report_dir}")
        
        os.makedirs(self.report_dir, exist_ok=True)
        
        # Load data
        equity_curve = backtest_result.get('equity_curve', [])
        trades = backtest_result.get('trades', [])
        metrics = backtest_result.get('metrics', {})
        
        # Generate charts
        self._generate_equity_curve(equity_curve)
        self._generate_drawdown_chart(equity_curve)
        self._generate_monthly_returns(equity_curve)
        self._generate_trade_distribution(trades)
        
        # Save data files
        self._save_trade_list(trades)
        self._save_summary(metrics, strategy_name, symbols)
        
        # Generate HTML
        self._generate_html(backtest_result, strategy_name, symbols)
        
        logger.info(f"HTML report generated: {self.report_dir}/report.html")
    
    def _generate_equity_curve(self, equity_curve: list):
        """Generate equity curve chart"""
        if not equity_curve:
            return
        
        df = pd.DataFrame(equity_curve)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')
        df = df.sort_values('timestamp')
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(df['timestamp'], df['equity'], linewidth=2, color='#2E86AB')
        ax.fill_between(df['timestamp'], df['equity'], alpha=0.3, color='#2E86AB')
        ax.set_title('Equity Curve', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Equity ($)', fontsize=12)
        ax.grid(True, alpha=0.3)
        
        # Format y-axis as currency
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        plt.tight_layout()
        plt.savefig(f"{self.report_dir}/equity_curve.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    def _generate_drawdown_chart(self, equity_curve: list):
        """Generate drawdown chart"""
        if not equity_curve:
            return
        
        df = pd.DataFrame(equity_curve)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')
        df = df.sort_values('timestamp')
        
        # Calculate drawdown
        df['rolling_max'] = df['equity'].expanding().max()
        df['drawdown'] = (df['equity'] - df['rolling_max']) / df['rolling_max']
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.fill_between(df['timestamp'], df['drawdown'], 0, alpha=0.5, color='#E63946')
        ax.plot(df['timestamp'], df['drawdown'], linewidth=1, color='#E63946')
        ax.set_title('Drawdown Chart', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Drawdown (%)', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x*100:.1f}%'))
        
        plt.tight_layout()
        plt.savefig(f"{self.report_dir}/drawdown.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    def _generate_monthly_returns(self, equity_curve: list):
        """Generate monthly returns heatmap"""
        if not equity_curve:
            return
        
        df = pd.DataFrame(equity_curve)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')
        df = df.sort_values('timestamp')
        df.set_index('timestamp', inplace=True)
        
        # Calculate monthly returns
        monthly = df['equity'].resample('M').last().pct_change().dropna()
        
        # Create year-month matrix
        monthly_df = monthly.to_frame('return')
        monthly_df['year'] = monthly_df.index.year
        monthly_df['month'] = monthly_df.index.month
        
        pivot = monthly_df.pivot(index='year', columns='month', values='return')
        
        fig, ax = plt.subplots(figsize=(14, 8))
        sns.heatmap(
            pivot * 100,
            annot=True,
            fmt='.1f',
            cmap='RdYlGn',
            center=0,
            cbar_kws={'label': 'Return (%)'},
            ax=ax
        )
        ax.set_title('Monthly Returns Heatmap (%)', fontsize=16, fontweight='bold')
        ax.set_xlabel('Month', fontsize=12)
        ax.set_ylabel('Year', fontsize=12)
        
        plt.tight_layout()
        plt.savefig(f"{self.report_dir}/monthly_returns.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    def _generate_trade_distribution(self, trades: list):
        """Generate trade P&L distribution chart"""
        if not trades:
            return
        
        df = pd.DataFrame(trades)
        if 'pnl' not in df.columns:
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # P&L distribution
        ax1.hist(df['pnl'], bins=50, color='#06A77D', alpha=0.7, edgecolor='black')
        ax1.axvline(0, color='red', linestyle='--', linewidth=2)
        ax1.set_title('Trade P&L Distribution', fontsize=14, fontweight='bold')
        ax1.set_xlabel('P&L ($)', fontsize=12)
        ax1.set_ylabel('Frequency', fontsize=12)
        ax1.grid(True, alpha=0.3)
        
        # Holding time distribution
        if 'duration_s' in df.columns:
            df['duration_hours'] = df['duration_s'] / 3600
            ax2.hist(df['duration_hours'], bins=50, color='#F77F00', alpha=0.7, edgecolor='black')
            ax2.set_title('Holding Time Distribution', fontsize=14, fontweight='bold')
            ax2.set_xlabel('Holding Time (hours)', fontsize=12)
            ax2.set_ylabel('Frequency', fontsize=12)
            ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f"{self.report_dir}/trade_distribution.png", dpi=150, bbox_inches='tight')
        plt.close()
    
    def _save_trade_list(self, trades: list):
        """Save trade list to CSV"""
        if not trades:
            return
        
        df = pd.DataFrame(trades)
        df.to_csv(f"{self.report_dir}/trade_list.csv", index=False)
    
    def _save_summary(
        self,
        metrics: Dict[str, Any],
        strategy_name: str,
        symbols: Optional[list]
    ):
        """Save summary to JSON"""
        summary = {
            'strategy': strategy_name,
            'symbols': symbols or [],
            'timestamp': self.timestamp,
            'metrics': metrics
        }
        
        with open(f"{self.report_dir}/summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
    
    def _generate_html(
        self,
        backtest_result: Dict[str, Any],
        strategy_name: str,
        symbols: Optional[list]
    ):
        """Generate HTML report"""
        metrics = backtest_result.get('metrics', {})
        equity_metrics = metrics.get('equity_metrics', {})
        trade_metrics = metrics.get('trade_metrics', {})
        
        # Prepare data for template
        context = {
            'strategy_name': strategy_name,
            'symbols': symbols or [],
            'timestamp': self.timestamp,
            'report_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'equity_metrics': equity_metrics,
            'trade_metrics': trade_metrics,
            'charts': {
                'equity_curve': 'equity_curve.png',
                'drawdown': 'drawdown.png',
                'monthly_returns': 'monthly_returns.png',
                'trade_distribution': 'trade_distribution.png'
            }
        }
        
        # Load template
        template_str = self._get_html_template()
        template = Template(template_str)
        
        # Render HTML
        html = template.render(**context)
        
        # Save HTML
        with open(f"{self.report_dir}/report.html", 'w', encoding='utf-8') as f:
            f.write(html)
    
    def _get_html_template(self) -> str:
        """Get HTML template"""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report - {{ strategy_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f8f9fa;
            padding: 20px;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }
        .metric-label {
            color: #6c757d;
            font-size: 0.9em;
            text-transform: uppercase;
        }
        .chart-container {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .chart-container img {
            width: 100%;
            height: auto;
            border-radius: 5px;
        }
        table {
            width: 100%;
        }
        .positive {
            color: #28a745;
        }
        .negative {
            color: #dc3545;
        }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="header">
            <h1>{{ strategy_name }} - Backtest Report</h1>
            <p class="mb-0">Symbols: {{ symbols|join(', ') if symbols else 'N/A' }}</p>
            <p class="mb-0">Generated: {{ report_date }}</p>
        </div>

        <!-- Performance Metrics -->
        <div class="row">
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-label">Total P&L</div>
                    <div class="metric-value {{ 'positive' if trade_metrics.total_pnl > 0 else 'negative' }}">
                        ${{ "{:,.2f}".format(trade_metrics.total_pnl) }}
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-label">Sharpe Ratio</div>
                    <div class="metric-value">{{ "{:.2f}".format(equity_metrics.sharpe) }}</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-label">Max Drawdown</div>
                    <div class="metric-value negative">{{ "{:.2f}%".format(equity_metrics.max_drawdown * 100) }}</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value">{{ "{:.1f}%".format(trade_metrics.win_rate * 100) }}</div>
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div class="row">
            <div class="col-md-6">
                <div class="chart-container">
                    <h3>Equity Curve</h3>
                    <img src="{{ charts.equity_curve }}" alt="Equity Curve">
                </div>
            </div>
            <div class="col-md-6">
                <div class="chart-container">
                    <h3>Drawdown Chart</h3>
                    <img src="{{ charts.drawdown }}" alt="Drawdown Chart">
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-6">
                <div class="chart-container">
                    <h3>Monthly Returns Heatmap</h3>
                    <img src="{{ charts.monthly_returns }}" alt="Monthly Returns">
                </div>
            </div>
            <div class="col-md-6">
                <div class="chart-container">
                    <h3>Trade Distribution</h3>
                    <img src="{{ charts.trade_distribution }}" alt="Trade Distribution">
                </div>
            </div>
        </div>

        <!-- Detailed Metrics -->
        <div class="row">
            <div class="col-md-6">
                <div class="metric-card">
                    <h4>Equity Metrics</h4>
                    <table class="table">
                        <tr>
                            <td>CAGR</td>
                            <td>{{ "{:.2f}%".format(equity_metrics.CAGR * 100) }}</td>
                        </tr>
                        <tr>
                            <td>Volatility</td>
                            <td>{{ "{:.2f}%".format(equity_metrics.volatility * 100) }}</td>
                        </tr>
                        <tr>
                            <td>Sharpe Ratio</td>
                            <td>{{ "{:.2f}".format(equity_metrics.sharpe) }}</td>
                        </tr>
                        <tr>
                            <td>Sortino Ratio</td>
                            <td>{{ "{:.2f}".format(equity_metrics.sortino) }}</td>
                        </tr>
                        <tr>
                            <td>Max Drawdown</td>
                            <td class="negative">{{ "{:.2f}%".format(equity_metrics.max_drawdown * 100) }}</td>
                        </tr>
                    </table>
                </div>
            </div>
            <div class="col-md-6">
                <div class="metric-card">
                    <h4>Trade Metrics</h4>
                    <table class="table">
                        <tr>
                            <td>Total Trades</td>
                            <td>{{ trade_metrics.num_trades }}</td>
                        </tr>
                        <tr>
                            <td>Win Rate</td>
                            <td>{{ "{:.1f}%".format(trade_metrics.win_rate * 100) }}</td>
                        </tr>
                        <tr>
                            <td>Avg Win</td>
                            <td class="positive">${{ "{:,.2f}".format(trade_metrics.avg_win) }}</td>
                        </tr>
                        <tr>
                            <td>Avg Loss</td>
                            <td class="negative">${{ "{:,.2f}".format(trade_metrics.avg_loss) }}</td>
                        </tr>
                        <tr>
                            <td>Profit Factor</td>
                            <td>{{ "{:.2f}".format(trade_metrics.profit_factor) }}</td>
                        </tr>
                        <tr>
                            <td>Total P&L</td>
                            <td class="{{ 'positive' if trade_metrics.total_pnl > 0 else 'negative' }}">
                                ${{ "{:,.2f}".format(trade_metrics.total_pnl) }}
                            </td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""








