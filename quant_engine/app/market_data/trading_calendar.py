"""app/market_data/trading_calendar.py

NYSE Trading Calendar and Trading Clock.
Handles market hours, holidays, and trading-time aware calculations.
"""

from datetime import datetime, time, timedelta
from typing import Optional, List, Tuple
import pytz

from app.core.logger import logger


class TradingCalendar:
    """
    NYSE Trading Calendar.
    
    Handles:
    - Market open/close times
    - Trading days vs calendar days
    - Holidays
    - Trading-time aware calculations
    """
    
    # NYSE regular trading hours (ET)
    MARKET_OPEN = time(9, 30)  # 9:30 AM ET
    MARKET_CLOSE = time(16, 0)  # 4:00 PM ET
    
    # NYSE timezone
    NYSE_TZ = pytz.timezone('America/New_York')
    
    # Major NYSE holidays (simplified - can be extended)
    # Format: (month, day) - these are approximate, real holidays vary by year
    MAJOR_HOLIDAYS = [
        (1, 1),   # New Year's Day
        (7, 4),   # Independence Day
        (12, 25), # Christmas
        (12, 31), # New Year's Eve (sometimes)
    ]
    
    def __init__(self):
        """Initialize trading calendar."""
        pass
    
    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if market is open at given time.
        
        Args:
            dt: Datetime to check (default: now in NYSE timezone)
            
        Returns:
            True if market is open, False otherwise
        """
        if dt is None:
            dt = datetime.now(self.NYSE_TZ)
        else:
            # Convert to NYSE timezone if needed
            if dt.tzinfo is None:
                dt = self.NYSE_TZ.localize(dt)
            else:
                dt = dt.astimezone(self.NYSE_TZ)
        
        # Check if weekend
        if dt.weekday() >= 5:  # Saturday (5) or Sunday (6)
            return False
        
        # Check if holiday (simplified check)
        if (dt.month, dt.day) in self.MAJOR_HOLIDAYS:
            return False
        
        # Check if within trading hours
        dt_time = dt.time()
        return self.MARKET_OPEN <= dt_time <= self.MARKET_CLOSE
    
    def get_last_trading_day(self, dt: Optional[datetime] = None) -> datetime:
        """
        Get the last trading day (market open day).
        
        Args:
            dt: Reference datetime (default: now in NYSE timezone)
            
        Returns:
            Last trading day datetime (at market close time)
        """
        if dt is None:
            dt = datetime.now(self.NYSE_TZ)
        else:
            if dt.tzinfo is None:
                dt = self.NYSE_TZ.localize(dt)
            else:
                dt = dt.astimezone(self.NYSE_TZ)
        
        # Go back until we find a trading day
        current = dt
        max_iterations = 10  # Safety limit
        
        while max_iterations > 0:
            # Check if current day is a trading day
            if current.weekday() < 5 and (current.month, current.day) not in self.MAJOR_HOLIDAYS:
                # This is a trading day - return market close time
                market_close = datetime.combine(current.date(), self.MARKET_CLOSE)
                return self.NYSE_TZ.localize(market_close)
            
            # Go back one day
            current = current - timedelta(days=1)
            max_iterations -= 1
        
        # Fallback: return 5 days ago (shouldn't happen)
        logger.warning(f"Could not find last trading day, using fallback")
        fallback = dt - timedelta(days=5)
        market_close = datetime.combine(fallback.date(), self.MARKET_CLOSE)
        return self.NYSE_TZ.localize(market_close)
    
    def get_trading_time_now(self, last_trade_timestamp: Optional[float] = None) -> float:
        """
        Get current trading time (unix timestamp).
        
        If market is open: returns current time
        If market is closed: returns last trade timestamp (or last trading day close)
        
        Args:
            last_trade_timestamp: Last trade timestamp (unix timestamp)
            
        Returns:
            Trading time as unix timestamp
        """
        now_nyse = datetime.now(self.NYSE_TZ)
        
        if self.is_market_open(now_nyse):
            # Market is open - use real time
            return now_nyse.timestamp()
        else:
            # Market is closed - use last trade timestamp or last trading day close
            if last_trade_timestamp:
                return last_trade_timestamp
            else:
                # No last trade - use last trading day close
                last_trading_day = self.get_last_trading_day(now_nyse)
                return last_trading_day.timestamp()
    
    def get_trading_day_start(self, dt: Optional[datetime] = None) -> datetime:
        """
        Get trading day start (market open) for given date.
        
        Args:
            dt: Reference datetime (default: now)
            
        Returns:
            Trading day start (market open time)
        """
        if dt is None:
            dt = datetime.now(self.NYSE_TZ)
        else:
            if dt.tzinfo is None:
                dt = self.NYSE_TZ.localize(dt)
            else:
                dt = dt.astimezone(self.NYSE_TZ)
        
        # If market is closed, get last trading day
        if not self.is_market_open(dt):
            dt = self.get_last_trading_day(dt)
        
        # Return market open time for this day
        market_open = datetime.combine(dt.date(), self.MARKET_OPEN)
        return self.NYSE_TZ.localize(market_open)
    
    def get_trading_day_end(self, dt: Optional[datetime] = None) -> datetime:
        """
        Get trading day end (market close) for given date.
        
        Args:
            dt: Reference datetime (default: now)
            
        Returns:
            Trading day end (market close time)
        """
        if dt is None:
            dt = datetime.now(self.NYSE_TZ)
        else:
            if dt.tzinfo is None:
                dt = self.NYSE_TZ.localize(dt)
            else:
                dt = dt.astimezone(self.NYSE_TZ)
        
        # If market is closed, get last trading day
        if not self.is_market_open(dt):
            dt = self.get_last_trading_day(dt)
        
        # Return market close time for this day
        market_close = datetime.combine(dt.date(), self.MARKET_CLOSE)
        return self.NYSE_TZ.localize(market_close)
    
    def get_trading_days_back(self, n_days: int, dt: Optional[datetime] = None) -> List[datetime]:
        """
        Get last N trading days.
        
        Args:
            n_days: Number of trading days to go back
            dt: Reference datetime (default: now)
            
        Returns:
            List of trading day datetimes (at market close)
        """
        if dt is None:
            dt = datetime.now(self.NYSE_TZ)
        else:
            if dt.tzinfo is None:
                dt = self.NYSE_TZ.localize(dt)
            else:
                dt = dt.astimezone(self.NYSE_TZ)
        
        trading_days = []
        current = dt
        max_iterations = n_days * 3  # Safety limit
        
        while len(trading_days) < n_days and max_iterations > 0:
            # Check if current day is a trading day
            if current.weekday() < 5 and (current.month, current.day) not in self.MAJOR_HOLIDAYS:
                market_close = datetime.combine(current.date(), self.MARKET_CLOSE)
                trading_days.append(self.NYSE_TZ.localize(market_close))
            
            # Go back one day
            current = current - timedelta(days=1)
            max_iterations -= 1
        
        return trading_days


# Global instance
_trading_calendar: Optional[TradingCalendar] = None


def get_trading_calendar() -> TradingCalendar:
    """Get global TradingCalendar instance."""
    global _trading_calendar
    if _trading_calendar is None:
        _trading_calendar = TradingCalendar()
    return _trading_calendar






