"""app/backtest/data_reader.py

Historical data reader - supports CSV and Parquet formats.
Reads tick or candle data for backtesting.
"""

import pandas as pd
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
from datetime import datetime

from app.core.logger import logger


class DataReader:
    """
    Reads historical market data from files.
    
    Supports:
    - CSV format
    - Parquet format
    - Tick data
    - Candle/OHLCV data
    """
    
    def __init__(self, data_dir: str = "data/historical"):
        """
        Initialize data reader.
        
        Args:
            data_dir: Directory containing historical data files
        """
        self.data_dir = Path(data_dir)
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(f"Data directory created: {self.data_dir}")
    
    def read_csv(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Read CSV file for symbol.
        
        Expected CSV format:
        - Tick data: timestamp, symbol, last, bid, ask, volume
        - Candle data: timestamp, symbol, open, high, low, close, volume
        
        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD) or None
            end_date: End date (YYYY-MM-DD) or None
            
        Returns:
            DataFrame with historical data
        """
        csv_path = self.data_dir / f"{symbol}.csv"
        
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        try:
            df = pd.read_csv(csv_path)
            
            # Convert timestamp to datetime if needed
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            elif 'ts' in df.columns:
                df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            
            # Filter by date range
            if start_date or end_date:
                date_col = 'timestamp' if 'timestamp' in df.columns else 'ts'
                if start_date:
                    df = df[df[date_col] >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df[date_col] <= pd.to_datetime(end_date)]
            
            # Sort by timestamp
            date_col = 'timestamp' if 'timestamp' in df.columns else 'ts'
            df = df.sort_values(date_col)
            
            logger.info(f"Loaded {len(df)} rows from {csv_path}")
            return df
        
        except Exception as e:
            logger.error(f"Error reading CSV {csv_path}: {e}")
            raise
    
    def read_parquet(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Read Parquet file for symbol.
        
        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD) or None
            end_date: End date (YYYY-MM-DD) or None
            
        Returns:
            DataFrame with historical data
        """
        parquet_path = self.data_dir / f"{symbol}.parquet"
        
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {parquet_path}")
        
        try:
            df = pd.read_parquet(parquet_path)
            
            # Convert timestamp if needed
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            elif 'ts' in df.columns:
                df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            
            # Filter by date range
            if start_date or end_date:
                date_col = 'timestamp' if 'timestamp' in df.columns else 'ts'
                if start_date:
                    df = df[df[date_col] >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[date_col] <= pd.to_datetime(end_date)
            
            # Sort by timestamp
            date_col = 'timestamp' if 'timestamp' in df.columns else 'ts'
            df = df.sort_values(date_col)
            
            logger.info(f"Loaded {len(df)} rows from {parquet_path}")
            return df
        
        except Exception as e:
            logger.error(f"Error reading Parquet {parquet_path}: {e}")
            raise
    
    def read_data(
        self,
        symbol: str,
        format: str = "auto",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Read data file (auto-detect format).
        
        Args:
            symbol: Stock symbol
            format: "csv", "parquet", or "auto"
            start_date: Start date (YYYY-MM-DD) or None
            end_date: End date (YYYY-MM-DD) or None
            
        Returns:
            DataFrame with historical data
        """
        if format == "auto":
            # Try Parquet first, then CSV
            parquet_path = self.data_dir / f"{symbol}.parquet"
            csv_path = self.data_dir / f"{symbol}.csv"
            
            if parquet_path.exists():
                return self.read_parquet(symbol, start_date, end_date)
            elif csv_path.exists():
                return self.read_csv(symbol, start_date, end_date)
            else:
                raise FileNotFoundError(f"No data file found for {symbol}")
        elif format == "csv":
            return self.read_csv(symbol, start_date, end_date)
        elif format == "parquet":
            return self.read_parquet(symbol, start_date, end_date)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def convert_to_ticks(self, df: pd.DataFrame) -> Iterator[Dict[str, Any]]:
        """
        Convert DataFrame to tick format iterator.
        
        Args:
            df: DataFrame with market data
            
        Yields:
            Tick dicts in format: {symbol, last, bid, ask, volume, ts}
        """
        for _, row in df.iterrows():
            # Determine timestamp
            if 'timestamp' in row:
                ts = int(pd.Timestamp(row['timestamp']).timestamp() * 1000)
            elif 'ts' in row:
                ts = int(row['ts'])
            else:
                continue
            
            # Determine symbol
            symbol = row.get('symbol', 'UNKNOWN')
            
            # Tick format
            if 'last' in row:
                # Already in tick format
                tick = {
                    'symbol': symbol,
                    'last': str(row['last']),
                    'bid': str(row.get('bid', row['last'])),
                    'ask': str(row.get('ask', row['last'])),
                    'volume': int(row.get('volume', 0)),
                    'ts': ts
                }
            elif 'close' in row:
                # Candle format - use close as last
                tick = {
                    'symbol': symbol,
                    'last': str(row['close']),
                    'bid': str(row.get('close', row['close']) - 0.01),
                    'ask': str(row.get('close', row['close']) + 0.01),
                    'volume': int(row.get('volume', 0)),
                    'ts': ts
                }
            else:
                continue
            
            yield tick
    
    def convert_to_candles(self, df: pd.DataFrame) -> Iterator[Dict[str, Any]]:
        """
        Convert DataFrame to candle format iterator.
        
        Args:
            df: DataFrame with market data
            
        Yields:
            Candle dicts in format: {symbol, timestamp, open, high, low, close, volume}
        """
        for _, row in df.iterrows():
            # Determine timestamp
            if 'timestamp' in row:
                timestamp = pd.Timestamp(row['timestamp']).timestamp()
            elif 'ts' in row:
                timestamp = pd.Timestamp(row['ts'], unit='ms').timestamp()
            else:
                continue
            
            # Determine symbol
            symbol = row.get('symbol', 'UNKNOWN')
            
            # Candle format
            if 'open' in row and 'high' in row and 'low' in row and 'close' in row:
                candle = {
                    'symbol': symbol,
                    'timestamp': timestamp,
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row.get('volume', 0))
                }
            else:
                # Convert from tick format
                price = float(row.get('last', row.get('close', 0)))
                candle = {
                    'symbol': symbol,
                    'timestamp': timestamp,
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': float(row.get('volume', 0))
                }
            
            yield candle








