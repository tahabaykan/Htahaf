"""
Benchmark Data API Routes
Exposes QeBenchData logs (CSV) and real-time status to the Frontend.
"""
import os
import csv
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException

from app.core.logger import logger
from app.core.redis_client import redis_client
from app.core.redis_client import redis_client

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])

CSV_DIR = r"c:\StockTracker\quant_engine\reports"

@router.get("/fills")
async def get_benchmark_fills(date: Optional[str] = None):
    """
    Get list of fills with benchmark data from CSV.
    Default: Today's fills.
    
    Args:
        date: YYYYMMDD string (optional)
    """
    try:
        if not date:
            date = datetime.now().strftime("%Y%m%d")
            
        filename = f"qebenchdata_{date}.csv"
        filepath = os.path.join(CSV_DIR, filename)
        
        if not os.path.exists(filepath):
            return {
                "success": True,
                "date": date,
                "fills": [],
                "count": 0,
                "message": "No data found for this date"
            }
            
        fills = []
        try:
            with open(filepath, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Enrich or format if needed
                    # Calculate deviation %
                    try:
                        price = float(row.get('price', 0))
                        bench = float(row.get('bench_price', 0)) if row.get('bench_price') else 0
                        diff_pct = 0.0
                        if bench > 0:
                            diff_pct = ((price - bench) / bench) * 100
                        
                        row['diff_pct'] = round(diff_pct, 4)
                        fills.append(row)
                    except:
                        fills.append(row)
                        
        except Exception as e:
            logger.error(f"Error reading CSV {filepath}: {e}")
            return {"success": False, "error": str(e)}
            
        # Sort by timestamp desc (newest first)
        fills.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
        return {
            "success": True,
            "date": date,
            "fills": fills,
            "count": len(fills)
        }

    except Exception as e:
        logger.error(f"Error in get_benchmark_fills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
