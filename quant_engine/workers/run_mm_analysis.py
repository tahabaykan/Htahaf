"""
Run MM Analysis Worker
======================

Executes the Market Making Analysis Engine strategy.
Produces 'MM_Strategy_Summary.csv'.

Usage:
    python workers/run_mm_analysis.py
"""

import sys
import os
import pandas as pd
from datetime import datetime

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force load .env from quant_engine root
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

from app.core.logger import logger
from app.mm.mm_analysis_engine import MMAnalysisEngine
from app.config.settings import settings

def main():
    logger.info("🚀 Starting MM Strategic Analysis...")
    logger.info(f"Configuration: Hammer Host={settings.HAMMER_HOST}, Pwd_Set={'Yes' if settings.HAMMER_PASSWORD else 'No'}")
    
    # Initialize Engine (will use settings automatically)
    engine = MMAnalysisEngine()
    
    # Run analysis
    logger.info("Starting MM Analysis Engine (EXECUTION STRATEGIST MODE)...")
    # Run for diverse groups to get a good sample
    target_groups = ["heldsolidbig", "notcefilliquid", "heldkuponlu:c500", "heldnff"]
    
    logger.info(f"Target Groups: {target_groups}")
    
    combined_results = []
    
    for grp in target_groups:
        results = engine.analyze_all_groups(group_filter=grp, lookback=3000)
        if results:
            combined_results.extend(results)
            
    # Save combined output
    if combined_results:
        # Generate generic filename
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_filename = f"MM_Strategy_Summary_{ts}.csv"
        
        # Helper method in engine usually saves internal list, but we have a combined list now.
        # We need to manually save using the engine's helper or pandas.
        # engine.save_reports() saves engine.results. 
        # Let's override engine.results
        engine.results = combined_results
        df = engine.save_reports()
        
        logger.info("Summary Preview:")
        print(df[['Symbol', 'Group', 'Optimal_Spread', 'Execution_Mode', 'Initial_Action', 'Profit_Target', 'Max_Size', 'Tactical_Override', 'PM_Transition_Plan']].head(15))
    else:
        logger.warning("No results generated.")
    
    if not results:
        logger.warning("No results generated. Check connection or data availability.")
        return
        
    # Convert to DataFrame
    df = pd.DataFrame(results)
    
    # Sort by Group then Score (High to Low - Best Value first)
    if 'Final_BB_Score' in df.columns:
        df = df.sort_values(by=['Group', 'Final_BB_Score'], ascending=[True, False])
    
    # Output file
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"MM_Strategy_Summary_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    output_path = os.path.join(output_dir, filename)
    
    df.to_csv(output_path, index=False)
    
    logger.info(f"✅ Analysis Complete. Generated report: {output_path}")
    logger.info("Summary Preview:")
    print(df[['Symbol', 'Group', 'Optimal_Spread', 'Execution_Mode', 'Profit_Target', 'PM_Transition_Plan']].head(10))

if __name__ == "__main__":
    main()
