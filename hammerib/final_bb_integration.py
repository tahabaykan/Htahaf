import pandas as pd
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from hammer_pro_client import HammerProClient

class FinalBBScoreCalculator:
    """
    FINAL BB Score Calculator integrated with Hammer Pro
    Migrates existing scoring algorithm to Hammer platform
    """
    
    def __init__(self, hammer_client: HammerProClient):
        self.hammer = hammer_client
        self.logger = logging.getLogger(__name__)
        
        # CSV data sources
        self.ssfi_data = None
        self.benchmark_data = {}
        
        # Score thresholds
        self.score_thresholds = {
            'high_score': 100,  # High FINAL BB score threshold
            'low_score': -50,   # Low FINAL BB score threshold
            'watchlist_size': 50  # Maximum symbols in watchlist
        }
        
    def load_ssfi_data(self, csv_path: str):
        """Load SSFI data from CSV file"""
        try:
            self.ssfi_data = pd.read_csv(csv_path)
            self.logger.info(f"Loaded SSFI data from {csv_path}")
        except Exception as e:
            self.logger.error(f"Failed to load SSFI data: {e}")
            
    def calculate_final_bb_score(self, row: pd.Series, market_data: Dict) -> float:
        """
        Calculate FINAL BB score using existing algorithm
        Based on the formula: FINAL_THG - 400 * bid_buy_ucuzluk
        """
        try:
            # Get FINAL_THG from CSV data
            final_thg = row.get('FINAL_THG', 0)
            
            # Get market data for calculations
            bid = market_data.get('bid', 0)
            ask = market_data.get('ask', 0)
            last = market_data.get('last', 0)
            prev_close = market_data.get('prevClose', 0)
            
            # Calculate benchmark (simplified - you can enhance this)
            benchmark = self.calculate_benchmark(row.get('benchmark_type', 'T'))
            
            # Calculate bid_buy_ucuzluk
            pf_bid_buy = bid + 0.01 if bid else 0
            pf_bid_buy_chg = pf_bid_buy - prev_close if prev_close else 0
            bid_buy_ucuzluk = pf_bid_buy_chg - benchmark
            
            # Calculate FINAL BB score
            final_bb_score = float(final_thg) - 400 * float(bid_buy_ucuzluk)
            
            return final_bb_score
            
        except Exception as e:
            self.logger.error(f"Error calculating FINAL BB score: {e}")
            return 0
            
    def calculate_benchmark(self, benchmark_type: str = 'T') -> float:
        """Calculate benchmark value based on type"""
        # This is a simplified benchmark calculation
        # You can enhance this based on your existing benchmark logic
        if benchmark_type == 'T':
            return 0.5  # Example benchmark value
        elif benchmark_type == 'C':
            return 0.3
        else:
            return 0.0
            
    async def calculate_all_scores(self, symbols: List[str]) -> List[Tuple[str, float]]:
        """Calculate FINAL BB scores for all symbols"""
        if self.ssfi_data is None:
            self.logger.error("SSFI data not loaded")
            return []
            
        scores = []
        
        for symbol in symbols:
            # Get symbol data from CSV
            symbol_data = self.ssfi_data[self.ssfi_data['PREF IBKR'] == symbol]
            if symbol_data.empty:
                continue
                
            row = symbol_data.iloc[0]
            
            # Get market data from Hammer
            market_data = await self.hammer.get_symbol_snapshot(symbol)
            
            # Calculate FINAL BB score
            score = self.calculate_final_bb_score(row, market_data)
            scores.append((symbol, score))
            
        return scores
        
    async def create_final_bb_watchlist(self, watchlist_name: str = "FINAL_BB_Watchlist"):
        """Create watchlist based on FINAL BB scores"""
        if self.ssfi_data is None:
            self.logger.error("SSFI data not loaded")
            return
            
        # Get all symbols from SSFI data
        symbols = self.ssfi_data['PREF IBKR'].dropna().unique().tolist()
        
        # Calculate scores for all symbols
        scores = await self.calculate_all_scores(symbols)
        
        # Sort by score (highest first)
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Select top symbols for watchlist
        top_symbols = [symbol for symbol, score in scores[:self.score_thresholds['watchlist_size']]]
        
        # Create watchlist in Hammer Pro
        result = await self.hammer.create_watchlist(watchlist_name, top_symbols)
        self.logger.info(f"Created FINAL BB watchlist: {result}")
        
        return top_symbols, scores[:self.score_thresholds['watchlist_size']]
        
    async def update_final_bb_watchlist(self, port_id: str):
        """Update existing FINAL BB watchlist with new scores"""
        if self.ssfi_data is None:
            self.logger.error("SSFI data not loaded")
            return
            
        # Get all symbols from SSFI data
        symbols = self.ssfi_data['PREF IBKR'].dropna().unique().tolist()
        
        # Calculate scores for all symbols
        scores = await self.calculate_all_scores(symbols)
        
        # Sort by score (highest first)
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Select top symbols for watchlist
        top_symbols = [symbol for symbol, score in scores[:self.score_thresholds['watchlist_size']]]
        
        # Update watchlist in Hammer Pro
        await self.hammer.update_watchlist(port_id, top_symbols)
        self.logger.info(f"Updated FINAL BB watchlist with {len(top_symbols)} symbols")
        
        return top_symbols, scores[:self.score_thresholds['watchlist_size']]
        
    async def create_score_based_watchlists(self):
        """Create multiple watchlists based on different score criteria"""
        if self.ssfi_data is None:
            self.logger.error("SSFI data not loaded")
            return
            
        # Get all symbols from SSFI data
        symbols = self.ssfi_data['PREF IBKR'].dropna().unique().tolist()
        
        # Calculate scores for all symbols
        scores = await self.calculate_all_scores(symbols)
        
        # Create different watchlists based on score ranges
        high_score_symbols = [symbol for symbol, score in scores if score >= self.score_thresholds['high_score']]
        low_score_symbols = [symbol for symbol, score in scores if score <= self.score_thresholds['low_score']]
        mid_score_symbols = [symbol for symbol, score in scores 
                           if self.score_thresholds['low_score'] < score < self.score_thresholds['high_score']]
        
        # Create watchlists
        watchlists = {
            'FINAL_BB_High_Scores': high_score_symbols,
            'FINAL_BB_Low_Scores': low_score_symbols,
            'FINAL_BB_Mid_Scores': mid_score_symbols[:20]  # Limit mid scores
        }
        
        for name, symbols in watchlists.items():
            if symbols:
                await self.hammer.create_watchlist(name, symbols)
                self.logger.info(f"Created {name} with {len(symbols)} symbols")
                
        return watchlists
        
    def get_score_analysis(self, scores: List[Tuple[str, float]]) -> Dict:
        """Analyze FINAL BB scores and provide statistics"""
        if not scores:
            return {}
            
        score_values = [score for _, score in scores]
        
        analysis = {
            'total_symbols': len(scores),
            'average_score': sum(score_values) / len(score_values),
            'highest_score': max(score_values),
            'lowest_score': min(score_values),
            'high_score_count': len([s for s in score_values if s >= self.score_thresholds['high_score']]),
            'low_score_count': len([s for s in score_values if s <= self.score_thresholds['low_score']]),
            'top_10_symbols': [symbol for symbol, score in sorted(scores, key=lambda x: x[1], reverse=True)[:10]]
        }
        
        return analysis

class HammerWatchlistManager:
    """
    Advanced watchlist management for Hammer Pro
    """
    
    def __init__(self, hammer_client: HammerProClient):
        self.hammer = hammer_client
        self.logger = logging.getLogger(__name__)
        self.active_watchlists = {}
        
    async def setup_auto_watchlists(self):
        """Setup automatic watchlist management"""
        # Get existing portfolios
        portfolios = await self.hammer.get_portfolios()
        
        # Create default watchlists if they don't exist
        default_watchlists = [
            "FINAL_BB_Top_Picks",
            "FINAL_BB_High_Scorers", 
            "FINAL_BB_Low_Scorers",
            "FINAL_BB_Momentum"
        ]
        
        for watchlist_name in default_watchlists:
            if not any(p['name'] == watchlist_name for p in portfolios):
                await self.hammer.create_watchlist(watchlist_name, [])
                self.logger.info(f"Created default watchlist: {watchlist_name}")
                
    async def subscribe_to_watchlist_symbols(self, watchlist_name: str):
        """Subscribe to real-time data for all symbols in a watchlist"""
        # Get watchlist symbols
        portfolios = await self.hammer.get_portfolios()
        watchlist = next((p for p in portfolios if p['name'] == watchlist_name), None)
        
        if watchlist:
            symbols = await self.hammer.get_portfolio_symbols(watchlist['portID'])
            if symbols:
                await self.hammer.subscribe_market_data(symbols)
                self.logger.info(f"Subscribed to {len(symbols)} symbols in {watchlist_name}")
                
    async def monitor_watchlist_performance(self, watchlist_name: str):
        """Monitor performance of symbols in a watchlist"""
        portfolios = await self.hammer.get_portfolios()
        watchlist = next((p for p in portfolios if p['name'] == watchlist_name), None)
        
        if watchlist:
            symbols = await self.hammer.get_portfolio_symbols(watchlist['portID'])
            performance_data = []
            
            for symbol in symbols:
                snapshot = await self.hammer.get_symbol_snapshot(symbol)
                if snapshot:
                    performance_data.append({
                        'symbol': symbol,
                        'last': snapshot.get('last', 0),
                        'change': snapshot.get('change', 0),
                        'volume': snapshot.get('volume', 0)
                    })
                    
            return performance_data 