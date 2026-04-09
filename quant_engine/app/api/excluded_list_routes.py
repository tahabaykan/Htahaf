from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pydantic import BaseModel
import os
import csv
from app.core.logger import logger

router = APIRouter(prefix="/api/excluded-list", tags=["excluded-list"])

EXCLUDED_FILE = "qe_excluded.csv"

# Request model
class SaveExcludedListRequest(BaseModel):
    symbols: List[str]

@router.get("")
async def get_excluded_list() -> Dict[str, Any]:
    """
    Get the list of excluded symbols from qe_excluded.csv.
    """
    try:
        # Check if file exists in root directory (c:\StockTracker)
        # We assume app runs from StockTracker root or we use absolute path logic
        root_dir = os.getcwd() 
        file_path = os.path.join(root_dir, EXCLUDED_FILE)
        
        excluded_list = []
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                try:
                    # Expecting single column or just list
                    for row in reader:
                        if row:
                            excluded_list.extend([s.strip().upper() for s in row if s.strip()])
                except Exception as e:
                    logger.error(f"Error reading excluded csv: {e}")
                    
        # Dedup just in case
        excluded_list = list(set(excluded_list))
        excluded_list.sort()
        
        return {
            "success": True,
            "list": excluded_list
        }
    except Exception as e:
        logger.error(f"Error getting excluded list: {e}", exc_info=True)
        return {"success": False, "message": str(e)}

@router.post("/save")
async def save_excluded_list(request: SaveExcludedListRequest) -> Dict[str, Any]:
    """
    Save the list of excluded symbols to qe_excluded.csv (Overwrite).
    """
    try:
        root_dir = os.getcwd()
        file_path = os.path.join(root_dir, EXCLUDED_FILE)
        
        symbols = sorted(list(set([s.strip().upper() for s in request.symbols if s.strip()])))
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write as a single column
            for sym in symbols:
                writer.writerow([sym])
                
        logger.info(f"Saved {len(symbols)} excluded symbols to {file_path}")
        
        return {
            "success": True,
            "list": symbols,
            "message": f"Saved {len(symbols)} symbols"
        }
    except Exception as e:
        logger.error(f"Error saving excluded list: {e}", exc_info=True)
        return {"success": False, "message": str(e)}
