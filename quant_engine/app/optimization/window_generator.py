"""app/optimization/window_generator.py

Window generator for walk-forward optimization.
Generates training and testing windows.
"""

from enum import Enum
from typing import List, Tuple, Optional
from datetime import datetime, timedelta

from app.core.logger import logger


class WindowMode(Enum):
    """Window generation mode"""
    SLIDING = "sliding"  # Fixed-size windows that slide forward
    EXPANDING = "expanding"  # Training window expands, test window slides


class WindowGenerator:
    """
    Generates training and testing windows for walk-forward optimization.
    
    Supports:
    - Sliding windows (fixed training size)
    - Expanding windows (growing training size)
    """
    
    def __init__(
        self,
        training_period: str = "12M",
        testing_period: str = "3M",
        step: Optional[str] = None,
        mode: WindowMode = WindowMode.SLIDING
    ):
        """
        Initialize window generator.
        
        Args:
            training_period: Training period (e.g., "12M", "252D", "1Y")
            testing_period: Testing period (e.g., "3M", "63D")
            step: Step size between windows (defaults to testing_period)
            mode: SLIDING or EXPANDING
        """
        self.training_period = training_period
        self.testing_period = testing_period
        self.step = step or testing_period
        self.mode = mode
    
    def parse_period(self, period: str) -> timedelta:
        """
        Parse period string to timedelta.
        
        Formats:
        - "12M" → 12 months
        - "252D" → 252 days
        - "1Y" → 1 year
        - "6W" → 6 weeks
        
        Args:
            period: Period string
            
        Returns:
            timedelta object
        """
        period = period.upper().strip()
        
        if period.endswith('D'):
            days = int(period[:-1])
            return timedelta(days=days)
        elif period.endswith('W'):
            weeks = int(period[:-1])
            return timedelta(weeks=weeks)
        elif period.endswith('M'):
            months = int(period[:-1])
            # Approximate: 1 month ≈ 21 trading days
            return timedelta(days=months * 21)
        elif period.endswith('Y'):
            years = int(period[:-1])
            return timedelta(days=years * 252)  # Trading days
        else:
            raise ValueError(f"Invalid period format: {period}")
    
    def generate_windows(
        self,
        start_date: str,
        end_date: str
    ) -> List[Tuple[datetime, datetime, datetime, datetime]]:
        """
        Generate training and testing windows.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            List of (train_start, train_end, test_start, test_end) tuples
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        training_delta = self.parse_period(self.training_period)
        testing_delta = self.parse_period(self.testing_period)
        step_delta = self.parse_period(self.step)
        
        windows = []
        train_start = start
        
        if self.mode == WindowMode.SLIDING:
            # Sliding window: fixed training size
            while train_start + training_delta + testing_delta <= end:
                train_end = train_start + training_delta
                test_start = train_end
                test_end = test_start + testing_delta
                
                if test_end > end:
                    break
                
                windows.append((train_start, train_end, test_start, test_end))
                
                # Move forward by step
                train_start += step_delta
            
        elif self.mode == WindowMode.EXPANDING:
            # Expanding window: training grows, test slides
            train_end = train_start + training_delta
            
            while train_end + testing_delta <= end:
                test_start = train_end
                test_end = test_start + testing_delta
                
                if test_end > end:
                    break
                
                windows.append((train_start, train_end, test_start, test_end))
                
                # Training window expands, test window slides
                train_end += step_delta
        
        logger.info(f"Generated {len(windows)} windows ({self.mode.value} mode)")
        return windows
    
    def get_window_info(self, windows: List[Tuple]) -> dict:
        """Get summary information about windows"""
        if not windows:
            return {}
        
        return {
            'num_windows': len(windows),
            'mode': self.mode.value,
            'training_period': self.training_period,
            'testing_period': self.testing_period,
            'first_train_start': windows[0][0].strftime("%Y-%m-%d"),
            'last_train_end': windows[-1][1].strftime("%Y-%m-%d"),
            'first_test_start': windows[0][2].strftime("%Y-%m-%d"),
            'last_test_end': windows[-1][3].strftime("%Y-%m-%d")
        }

