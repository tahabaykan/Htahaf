import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from .hammer_pro_client import HammerProClient

class MarketDataManager:
    """
    Market data manager for Hammer Pro integration
    Handles CSV data loading and Hammer Pro market data
    """
    
    def __init__(self, connect_on_init=False):
        self.hammer_pro = None
        self.connected = False
        self.logger = logging.getLogger(__name__)
        
        # CSV data
        self.historical_data = None
        self.extended_data = None
        self.mastermind_data = None
        self.befday_data = None
        
        # Market data cache
        self.market_data = {}
        self.active_subscriptions = set()
        
        # Load CSV files
        self._load_csv_data()
        
        if connect_on_init:
            self.connect()
    
    def _load_csv_data(self):
        """Load CSV data files"""
        try:
            # Load historical data
            self.historical_data = pd.read_csv('historical_data.csv')
            self.logger.info("Loaded historical_data.csv")
        except FileNotFoundError:
            self.logger.warning("historical_data.csv not found")
            self.historical_data = pd.DataFrame()
        
        try:
            # Load extended data
            self.extended_data = pd.read_csv('extlthistorical.csv')
            self.logger.info("Loaded extlthistorical.csv")
        except FileNotFoundError:
            self.logger.warning("extlthistorical.csv not found")
            self.extended_data = pd.DataFrame()
        
        try:
            # Load mastermind data
            self.mastermind_data = pd.read_csv('mastermind_extltport.csv')
            self.logger.info("Loaded mastermind_extltport.csv")
        except FileNotFoundError:
            self.logger.warning("mastermind_extltport.csv not found")
            self.mastermind_data = pd.DataFrame()
        
        try:
            # Load befday data
            self.befday_data = pd.read_csv('befday.csv')
            self.logger.info("Loaded befday.csv")
        except FileNotFoundError:
            self.logger.warning("befday.csv not found")
            self.befday_data = pd.DataFrame()
    
    def connect(self, host='127.0.0.1', port=8080, password=''):
        """Connect to Hammer Pro"""
        try:
            # Disconnect if already connected
            if self.hammer_pro:
                self.disconnect()
            
            self.hammer_pro = HammerProClient(host, port, password)
            
            # Set up event handlers
            self.hammer_pro.on_connect = self._on_hammer_pro_connect
            self.hammer_pro.on_disconnect = self._on_hammer_pro_disconnect
            self.hammer_pro.on_market_data = self._on_market_data_update
            
            # Connect
            self.hammer_pro.connect()
            self.connected = True
            self.logger.info(f"Connected to Hammer Pro at {host}:{port}")
            
            # Start data streamer automatically
            self._start_data_streamer()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Hammer Pro: {e}")
            self.connected = False
            return False
    
    def _start_data_streamer(self, streamer_id='AMTD'):
        """Start data streamer for live market data"""
        if not self.connected or not self.hammer_pro:
            self.logger.warning("Cannot start data streamer - not connected")
            return False
        
        try:
            self.logger.info(f"Starting data streamer: {streamer_id}")
            self.hammer_pro.start_data_streamer(streamer_id)
            
            # Wait a bit for streamer to start
            time.sleep(1)
            
            # Subscribe to some common symbols for testing
            test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY', 'QQQ']
            self.logger.info(f"Subscribing to test symbols: {test_symbols}")
            
            for symbol in test_symbols:
                try:
                    self.hammer_pro.subscribe_l1(streamer_id, [symbol])
                    self.logger.info(f"Subscribed to {symbol}")
                except Exception as e:
                    self.logger.error(f"Failed to subscribe to {symbol}: {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start data streamer: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Hammer Pro"""
        if self.hammer_pro:
            self.hammer_pro.disconnect()
        self.connected = False
        self.logger.info("Disconnected from Hammer Pro")
    
    def _on_hammer_pro_connect(self):
        """Handle Hammer Pro connection"""
        self.logger.info("Hammer Pro connected")
        self.connected = True
    
    def _on_hammer_pro_disconnect(self):
        """Handle Hammer Pro disconnection"""
        self.logger.info("Hammer Pro disconnected")
        self.connected = False
    
    def _on_market_data_update(self, symbol, data):
        """Handle market data updates"""
        self.market_data[symbol] = data
        self.logger.debug(f"Market data update for {symbol}: {data}")
    
    def get_historical_tickers(self, start_idx, end_idx):
        """Get tickers from historical data for the given page range"""
        if self.historical_data.empty:
            return []
        
        if 'PREF IBKR' in self.historical_data.columns:
            return self.historical_data['PREF IBKR'].dropna().iloc[start_idx:end_idx].tolist()
        return []
    
    def get_extended_tickers(self, start_idx, end_idx):
        """Get tickers from extended data for the given page range"""
        if self.extended_data.empty:
            return []
        
        if 'PREF IBKR' in self.extended_data.columns:
            return self.extended_data['PREF IBKR'].dropna().iloc[start_idx:end_idx].tolist()
        return []
    
    def get_mastermind_tickers(self, start_idx, end_idx):
        """Get tickers from mastermind data for the given page range"""
        if self.mastermind_data.empty:
            return []
        
        if 'PREF IBKR' in self.mastermind_data.columns:
            return self.mastermind_data['PREF IBKR'].dropna().iloc[start_idx:end_idx].tolist()
        return []
    
    def get_befday_tickers(self, start_idx, end_idx):
        """Get tickers from befday data for the given page range"""
        if self.befday_data.empty:
            return []
        
        if 'Symbol' in self.befday_data.columns:
            return self.befday_data['Symbol'].dropna().iloc[start_idx:end_idx].tolist()
        return []
    
    def get_max_pages(self, data_type, items_per_page):
        """Calculate maximum number of pages based on data size"""
        if data_type == 'historical':
            return len(self.historical_data) // items_per_page if not self.historical_data.empty else 0
        elif data_type == 'extended':
            return len(self.extended_data) // items_per_page if not self.extended_data.empty else 0
        elif data_type == 'mastermind':
            return len(self.mastermind_data) // items_per_page if not self.mastermind_data.empty else 0
        elif data_type == 'befday':
            return len(self.befday_data) // items_per_page if not self.befday_data.empty else 0
        return 0
    
    def subscribe_page_tickers(self, tickers, streamer_id='AMTD'):
        """Subscribe to market data for tickers on current page"""
        if not self.connected or not self.hammer_pro:
            return
        
        # Unsubscribe from previous tickers
        self.unsubscribe_previous_tickers(tickers)
        
        # Subscribe to new tickers
        for ticker in tickers:
            if ticker and ticker not in self.active_subscriptions:
                try:
                    self.hammer_pro.subscribe_l1(streamer_id, [ticker])
                    self.active_subscriptions.add(ticker)
                    self.logger.debug(f"Subscribed to {ticker}")
                except Exception as e:
                    self.logger.error(f"Failed to subscribe to {ticker}: {e}")
    
    def unsubscribe_previous_tickers(self, current_tickers):
        """Unsubscribe from tickers not in current page"""
        if not self.connected or not self.hammer_pro:
            return
        
        for ticker in list(self.active_subscriptions):
            if ticker not in current_tickers:
                try:
                    self.hammer_pro.unsubscribe('AMTD', 'L1', [ticker])
                    self.active_subscriptions.remove(ticker)
                    self.logger.debug(f"Unsubscribed from {ticker}")
                except Exception as e:
                    self.logger.error(f"Failed to unsubscribe from {ticker}: {e}")
    
    def get_market_data(self, symbol):
        """Get market data for a symbol"""
        return self.market_data.get(symbol, {})
    
    def get_all_market_data(self):
        """Get all current market data"""
        return self.market_data.copy()
    
    def get_market_data_snapshot(self):
        """Get snapshot of all market data"""
        return self.market_data.copy()
    
    def start_data_streamer(self, streamer_id='AMTD'):
        """Start a data streamer"""
        if not self.connected or not self.hammer_pro:
            return False
        
        try:
            self.hammer_pro.start_data_streamer(streamer_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to start data streamer {streamer_id}: {e}")
            return False
    
    def enum_data_streamers(self):
        """Get available data streamers"""
        if not self.connected or not self.hammer_pro:
            return []
        
        streamers = []
        
        def on_streamers_response(data):
            nonlocal streamers
            if data.get('success') == 'OK':
                result = data.get('result', [])
                streamers = result
        
        self.hammer_pro.enum_data_streamers(on_streamers_response)
        
        # Wait for response
        timeout = 5
        start_time = time.time()
        while not streamers and time.time() - start_time < timeout:
            time.sleep(0.1)
        
        return streamers
    
    def get_positions(self):
        """Get account positions"""
        if not self.connected or not self.hammer_pro:
            return []
        
        positions = []
        
        def on_positions_response(data):
            nonlocal positions
            if data.get('success') == 'OK':
                result = data.get('result', {})
                positions = result.get('positions', [])
        
        # Get positions from first available account
        accounts = self.get_trading_accounts()
        if accounts:
            account_key = accounts[0]['accountKey']
            self.hammer_pro.get_positions(account_key, on_positions_response)
            
            # Wait for response
            timeout = 5
            start_time = time.time()
            while not positions and time.time() - start_time < timeout:
                time.sleep(0.1)
        
        return positions
    
    def get_trading_accounts(self):
        """Get available trading accounts"""
        if not self.connected or not self.hammer_pro:
            return []
        
        accounts = []
        
        def on_accounts_response(data):
            nonlocal accounts
            if data.get('success') == 'OK':
                result = data.get('result', {})
                accounts = result.get('accounts', [])
        
        self.hammer_pro.enum_trading_accounts(on_accounts_response)
        
        # Wait for response
        timeout = 5
        start_time = time.time()
        while not accounts and time.time() - start_time < timeout:
            time.sleep(0.1)
        
        return accounts
    
    def get_etf_data(self):
        """Get ETF market data"""
        etf_symbols = ['TLT', 'TMF', 'TQQQ', 'SQQQ', 'SPY', 'QQQ', 'IWM', 'UVXY', 'VXX']
        etf_data = {}
        
        for symbol in etf_symbols:
            data = self.get_market_data(symbol)
            if data:
                etf_data[symbol] = data
        
        return etf_data
    
    def is_connected(self):
        """Check if connected to Hammer Pro"""
        return self.connected and self.hammer_pro and self.hammer_pro.is_connected()
    
    def connect_ibkr(self):
        """Wrapper for connect method (for compatibility)"""
        return self.connect()
    
    def disconnect_ibkr(self):
        """Wrapper for disconnect method (for compatibility)"""
        self.disconnect()
    
    def update_data_once(self):
        """Update data once (for compatibility)"""
        # This method is called periodically to refresh data
        pass
    
    def subscribe_visible(self):
        """Subscribe to visible tickers (for compatibility)"""
        # This method is called when visible tickers change
        pass 