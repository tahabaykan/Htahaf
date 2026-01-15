"""
QeBench Calculator Module

Core calculations for weighted averages and outperform metrics.
"""
from typing import Dict


def calculate_weighted_average(
    old_qty: int,
    old_avg: float,
    new_qty: int,
    new_price: float
) -> tuple[int, float]:
    """
    Calculate weighted average after adding to position.
    
    Returns:
        (total_qty, new_weighted_avg)
    """
    if old_qty == 0:
        return new_qty, new_price
    
    total_qty = old_qty + new_qty
    new_avg = (old_qty * old_avg + new_qty * new_price) / total_qty
    
    return total_qty, new_avg


def calculate_outperform(
    current_price: float,
    avg_cost: float,
    bench_now: float,
    bench_at_fill: float
) -> float:
    """
    Calculate outperformance vs benchmark.
    
    Formula:
        Outperform = (Current - AvgCost) - (BenchNow - BenchFill)
    
    Returns:
        Outperform change in cents
    """
    position_pnl = current_price - avg_cost
    bench_pnl = bench_now - bench_at_fill
    outperform = position_pnl - bench_pnl
    
    return outperform


def calculate_reset_bench_fill(
    current_price: float,
    avg_cost: float,
    bench_now: float
) -> float:
    """
    Calculate bench@fill value that makes outperform = 0.
    
    Used for "Reset All" functionality.
    
    Formula:
        Outperform = 0
        → (Current - AvgCost) - (BenchNow - X) = 0
        → X = BenchNow - (Current - AvgCost)
    
    Returns:
        New bench@fill value
    """
    bench_at_fill = bench_now - (current_price - avg_cost)
    return bench_at_fill


def merge_position_with_fill(
    existing_position: Dict,
    fill_qty: int,
    fill_price: float,
    bench_price_at_fill: float
) -> Dict:
    """
    Merge existing position with new fill (weighted average).
    
    Args:
        existing_position: {qty, avg_cost, bench_fill}
        fill_qty: New fill quantity
        fill_price: Fill price
        bench_price_at_fill: Benchmark price when filled
    
    Returns:
        Updated position dict with new weighted averages
    """
    old_qty = existing_position.get('total_qty', 0)
    old_avg_cost = existing_position.get('weighted_avg_cost', 0.0)
    old_bench_fill = existing_position.get('weighted_bench_fill', 0.0)
    
    # Calculate new weighted averages
    new_qty, new_avg_cost = calculate_weighted_average(
        old_qty, old_avg_cost, fill_qty, fill_price
    )
    
    _, new_bench_fill = calculate_weighted_average(
        old_qty, old_bench_fill, fill_qty, bench_price_at_fill
    )
    
    return {
        'total_qty': new_qty,
        'weighted_avg_cost': new_avg_cost,
        'weighted_bench_fill': new_bench_fill
    }
