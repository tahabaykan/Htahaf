"""
Market Context Worker (Redis-based)

This worker is responsible for:
1.  Fetching 5-minute snapshot data for 450+ stocks (Bid, Ask, Last, Volume).
2.  Logging this data to Redis (`market_context:{symbol}:5m`).
3.  Performing Gap Analysis (marking "Incomplete" if data is missing).
4.  Calculates and stores "DOS Group" indexes for fallback logic.

Usage:
    python -m workers.market_context_worker
"""

import sys
import os
import time
import json
import asyncio
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Add parent dir to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.config.settings import settings
from app.market_data.janall_metrics_engine import initialize_janall_metrics_engine, get_janall_metrics_engine
from app.market_data.static_data_store import initialize_static_store, get_static_store
from app.analysis.ofi_engine import get_ofi_engine

# CSV File Mapping (Read-Only)
# Maps Group Names to File Names (based on gorter.py logic)
GROUP_FILE_MAP = {
    'heldff': 'janek_ssfinekheldff.csv',
    'helddeznff': 'janek_ssfinekhelddeznff.csv', 
    'heldkuponlu': 'janek_ssfinekheldkuponlu.csv',
    'heldnff': 'janek_ssfinekheldnff.csv',
    'heldflr': 'janek_ssfinekheldflr.csv',
    'heldgarabetaltiyedi': 'janek_ssfinekheldgarabetaltiyedi.csv',
    'heldkuponlukreciliz': 'janek_ssfinekheldkuponlukreciliz.csv',
    'heldkuponlukreorta': 'janek_ssfinekheldkuponlukreorta.csv',
    'heldotelremorta': 'janek_ssfinekheldotelremorta.csv',
    'heldsolidbig': 'janek_ssfinekheldsolidbig.csv',
    'heldtitrekhc': 'janek_ssfinekheldtitrekhc.csv',
    'highmatur': 'janek_ssfinekhighmatur.csv',
    'notcefilliquid': 'janek_ssfineknotcefilliquid.csv',
    'notbesmaturlu': 'janek_ssfineknotbesmaturlu.csv',
    'nottitrekhc': 'janek_ssfineknottitrekhc.csv',
    'salakilliquid': 'janek_ssfineksalakilliquid.csv',
    'shitremhc': 'janek_ssfinekshitremhc.csv'
}

# Resolve root directory (c:\StockTracker) where CSV files are located
# __file__ = .../quant_engine/workers/market_context_worker.py
# parent = workers, parent.parent = quant_engine, parent.parent.parent = StockTracker
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

JANALL_PATH = ROOT_DIR / 'janalldata.csv'
SSFINEK_DIR = ROOT_DIR

class MarketContextWorker:
    def __init__(self):
        self.redis = get_redis_client().sync
        self.running = True
        self.universe: Dict[str, Dict] = {} # Symbol -> {Group, CGRUP, etc.}
        
        # Hammer/Feed Client (Placeholder/Mock for now, should integrate with real app.live)
        # In a real scenario, this might subscribe to the EventBus or connect to Hammer directly.
        # For this standalone worker, we assume we can fetch snapshots.
        self.feed_source = "HAMMER" 
        self.ofi_engine = get_ofi_engine() 
    
    def load_universe(self):
        """
        Reads ssfinek*.csv files to build the Universe map (Symbol -> Group).
        Strictly Read-Only.
        """
        logger.info("Loading Universe from CSV files (Read-Only)...")
        temp_universe = {}
        count = 0
        
        for group_name, filename in GROUP_FILE_MAP.items():
            filepath = os.path.join(SSFINEK_DIR, filename)
            if os.path.exists(filepath):
                try:
                    df = pd.read_csv(filepath)
                    if 'PREF IBKR' in df.columns:
                        for _, row in df.iterrows():
                            symbol = row['PREF IBKR']
                            cgrup = row.get('CGRUP', 'N/A')
                            # Extract additional columns for gem_engine analysis
                            # Subdivide heldkuponlu by CGRUP immediately
                            final_group = group_name
                            str_cgrup = str(cgrup).strip() if pd.notna(cgrup) else 'N/A'
                            
                            if group_name == 'heldkuponlu' and str_cgrup.upper() not in ['NONE', 'NAN', 'N/A', '']:
                                final_group = f"heldkuponlu:{str_cgrup}"

                            temp_universe[symbol] = {
                                'group': final_group,
                                'cgrup': str_cgrup,
                                # Add fields needed by gem_engine
                                'prev_close': float(row.get('prev_close', 0)) if pd.notna(row.get('prev_close')) else 0,
                                'MAXALW': float(row.get('MAXALW', 5000)) if pd.notna(row.get('MAXALW')) else 5000,
                                'ADV': float(row.get('ADV', 50000)) if pd.notna(row.get('ADV')) else 50000,
                            }
                            count += 1
                except Exception as e:
                    logger.error(f"Error reading {filename}: {e}")
            else:
                 logger.warning(f"File not found: {filename}")
        
        self.universe = temp_universe
        logger.info(f"Universe loaded: {len(self.universe)} symbols.")
        
        # Initialize Static Store with same CSV loop logic? No, just initialize it.
        # It loads janalldata.csv by default.
        initialize_static_store()
        initialize_janall_metrics_engine()
        
        # Also store universe in Redis for other components
        try:
             self.redis.set("market_context:universe", json.dumps(self.universe))
        except Exception as e:
             logger.error(f"Failed to save universe to Redis: {e}")

    def fetch_market_snapshots(self) -> Dict[str, Dict]:
        """
        Fetches current market data for all symbols in universe.
        In production, this calls Hammer Pro API.
        For now, we'll simulate or read from a shared source if available.
        """
        try:
            import requests
            response = requests.get("http://localhost:8000/api/market-data/snapshot", timeout=10)
            if response.status_code == 200:
                json_data = response.json()
                if json_data.get('success'):
                    real_data = json_data.get('data', {})
                    logger.info(f"Fetched {len(real_data)} real snapshots from API.")
                    return real_data
        except Exception as e:
             logger.warning(f"Failed to fetch snapshot from API: {e}. Using mock/empty data.")

        # Fallback / Placeholder if API fails (or startup)
        snapshots = {}
        timestamp = time.time()
        for symbol in self.universe:
            # Empty structure to avoid crashes (or keep previous values if persisted?)
            # Ideally we want REAL data. If API is down, maybe better to skip logging?
            # But let's return empty dict so we don't log garbage.
            pass
            
        return snapshots

    def log_context(self):
        """
        Main loop step: Fetch data, log to Redis, check gaps.
        """
        snapshots = self.fetch_market_snapshots()
        timestamp = time.time()
        
        pipeline = self.redis.pipeline()
        
        # 1. Store Snapshots & Update History
        for symbol, data in snapshots.items():
            key = f"market_context:{symbol}:5m"
            
            # Get prev_close from universe (loaded from CSV PRVDAY column)
            universe_info = self.universe.get(symbol, {})
            prev_close = universe_info.get('prev_close', 0)
            
            # Skip logging if critical data is missing (Wait for next L1 update)
            bid = data.get('bid')
            ask = data.get('ask')
            last = data.get('last')
            
            if bid is None or ask is None or last is None:
                 continue

            entry = {
                'ts': timestamp,
                'bid': bid,
                'ask': ask,
                'last': last,
                'vol': data.get('vol', data.get('volume', 0)),
                'prev_close': prev_close  # From CSV PRVDAY column
            }
            
            # --- OFI CALCULATION ---
            # Calculate OFI score (Order Flow Imbalance) and store in Redis
            # We assume 'bid_size' and 'ask_size' might be available in data or use 0
            # Ideally API should provide these.
            self.ofi_engine.process_tick(
                symbol=symbol,
                bid=data['bid'],
                bid_size=data.get('bid_size', 0),
                ask=data['ask'],
                ask_size=data.get('ask_size', 0),
                timestamp=timestamp
            )
            # -----------------------
            
            # Push to list (Left Push)
            pipeline.lpush(key, json.dumps(entry))
            # Trim to keep last ~2 days (2 days * 24h * 12 * 5min = 576 entries)
            pipeline.ltrim(key, 0, 600) 
            
            # Update gap status
            gap_key = f"market_context:{symbol}:gap_status"
            pipeline.set(gap_key, "OK", ex=600) # Expires if not updated
            
        pipeline.execute()
        
        # 2. Calculate Group Indexes (DOS Group Averages)
        self.calculate_group_indexes(snapshots)
        
        logger.info(f"Logged 5-min context for {len(snapshots)} symbols.")
        return snapshots

    def calculate_group_indexes(self, snapshots: Dict[str, Dict]):
        """
        Calculates average price/volume for each DOS Group.
        Used for Gap Analysis fallback.
        """
        group_aggregates = {}
        
        for symbol, data in snapshots.items():
            info = self.universe.get(symbol)
            if not info: continue
            
            group = info['group']
            
            # Calculate daily chg for this symbol
            last = data.get('last')
            if last is None: continue # Safety
            
            prev_close = data.get('prev_close', 0)
            daily_chg = 0.0
            daily_chg_pct = 0.0
            
            if prev_close and prev_close > 0:
                daily_chg = last - prev_close
                daily_chg_pct = (daily_chg / prev_close) * 100

            if group not in group_aggregates:
                group_aggregates[group] = {'sum_price': 0.0, 'sum_vol': 0, 'sum_chg': 0.0, 'count': 0}
            
            group_aggregates[group]['sum_price'] += last
            vol = data.get('vol') or data.get('volume') or 0
            group_aggregates[group]['sum_vol'] += vol
            # Use daily_chg NOT percentage for bench_chg (in cents) if we want absolute change overlay
            group_aggregates[group]['sum_chg'] += daily_chg
            group_aggregates[group]['count'] += 1
            
        # Compute averages and store
        pipeline = self.redis.pipeline()
        for group, agg in group_aggregates.items():
            if agg['count'] > 0:
                avg_price = agg['sum_price'] / agg['count']
                avg_vol = agg['sum_vol'] / agg['count']
                avg_chg = agg['sum_chg'] / agg['count']  # Average Daily Change in Cents
                
                index_key = f"group_index:{group}"
                pipeline.set(index_key, json.dumps({
                    'ts': time.time(),
                    'avg_price': avg_price,
                    'avg_vol': avg_vol,
                    'avg_chg': avg_chg, # This is the new BENCH_CHG for the group
                    'count': agg['count']
                }))
        pipeline.execute()

    def run(self):
        logger.info("Starting Market Context Worker...")
        
        # Initial Load
        self.load_universe()
        
        while self.running:
            try:
                start_time = time.time()
                
                # Check Redis Connection
                if not self.redis.ping():
                    logger.error("Redis connection lost!")
                    time.sleep(5)
                    continue
                
                # Logic
                snapshots = self.log_context()
                
                if not snapshots:
                    logger.warning("No data processed (Backend not ready?). Retrying in 10s...")
                    time.sleep(10)
                    continue

                # 1.5. Calculate Janall Metrics (Fbtot, Sfstot, etc.)
                try:
                    janall_engine = get_janall_metrics_engine()
                    static_store = get_static_store()
                    
                    if janall_engine and static_store:
                        # Ensure static data loaded
                        if not static_store.is_loaded():
                            static_store.load_csv()

                        # Compute batch metrics without ETF data store (will rely on group averages eventually)
                        janall_engine.compute_batch_metrics(
                            symbols=list(self.universe.keys()),
                            static_store=static_store,
                            market_data_cache=snapshots,
                            etf_data_store={}
                        )
                except Exception as e:
                    logger.error(f"Janall metrics calculation failed: {e}")

                # Trigger Gem Engine
                from app.analysis.gem_engine import gem_engine
                gem_engine.generate_proposals()
                
                # Wait for next cycle
                time.sleep(15)
                
            except KeyboardInterrupt:
                logger.info("Stopping worker...")
                self.running = False
            except Exception as e:
                logger.error(f"Worker iteration error: {e}", exc_info=True)
                time.sleep(60) # Wait before retry

if __name__ == "__main__":
    worker = MarketContextWorker()
    worker.run()
