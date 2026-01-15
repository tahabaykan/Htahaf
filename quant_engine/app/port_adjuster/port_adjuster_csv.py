"""
Port Adjuster CSV Import/Export

Compatible with Janall's exposureadjuster.csv format.
"""

import csv
from pathlib import Path
from typing import Dict, Optional
from app.core.logger import logger
from app.port_adjuster.port_adjuster_models import PortAdjusterConfig


def load_config_from_csv(csv_path: str) -> Optional[PortAdjusterConfig]:
    """
    Load Port Adjuster configuration from CSV file.
    
    CSV format (exposureadjuster.csv compatible):
    - First row: Headers
    - Second row: Values
    - Columns: total_exposure, avg_pref_price, long_ratio, short_ratio, 
               long_groups (as columns), short_groups (as columns)
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        PortAdjusterConfig, or None if error
    """
    try:
        csv_file = Path(csv_path)
        if not csv_file.exists():
            logger.warning(f"[PORT_ADJUSTER_CSV] CSV file not found: {csv_path}")
            return None
        
        # Read CSV
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if not rows:
                logger.warning(f"[PORT_ADJUSTER_CSV] CSV file is empty: {csv_path}")
                return None
            
            # First row contains the values
            row = rows[0]
            
            # Extract core values
            total_exposure = float(row.get('total_exposure', '1000000').replace(',', ''))
            avg_pref_price = float(row.get('avg_pref_price', '25.0'))
            long_ratio = float(row.get('long_ratio', '85.0'))
            short_ratio = float(row.get('short_ratio', '15.0'))
            
            # Extract long groups (columns starting with 'long_')
            long_groups: Dict[str, float] = {}
            short_groups: Dict[str, float] = {}
            
            # Default group lists (from Janall)
            default_long_groups = [
                'heldcilizyeniyedi', 'heldcommonsuz', 'helddeznff', 'heldff',
                'heldflr', 'heldgarabetaltiyedi', 'heldkuponlu', 'heldkuponlukreciliz',
                'heldkuponlukreorta', 'heldnff', 'heldotelremorta', 'heldsolidbig',
                'heldtitrekhc', 'highmatur', 'notbesmaturlu', 'notcefilliquid',
                'nottitrekhc', 'rumoreddanger', 'salakilliquid', 'shitremhc'
            ]
            
            default_short_groups = default_long_groups.copy()
            
            # Try to read group weights from CSV
            for group in default_long_groups:
                long_key = f'long_{group}'
                short_key = f'short_{group}'
                
                if long_key in row:
                    try:
                        long_groups[group] = float(row[long_key])
                    except (ValueError, TypeError):
                        long_groups[group] = 0.0
                else:
                    long_groups[group] = 0.0
                
                if short_key in row:
                    try:
                        short_groups[group] = float(row[short_key])
                    except (ValueError, TypeError):
                        short_groups[group] = 0.0
                else:
                    short_groups[group] = 0.0
            
            # Create config
            config = PortAdjusterConfig(
                total_exposure_usd=total_exposure,
                avg_pref_price=avg_pref_price,
                long_ratio_pct=long_ratio,
                short_ratio_pct=short_ratio,
                long_groups=long_groups,
                short_groups=short_groups
            )
            
            logger.info(
                f"[PORT_ADJUSTER_CSV] Config loaded from CSV: "
                f"exposure=${total_exposure:,.0f}, long={long_ratio}%, short={short_ratio}%"
            )
            
            return config
            
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_CSV] Error loading CSV: {e}", exc_info=True)
        return None


def save_config_to_csv(config: PortAdjusterConfig, csv_path: str) -> bool:
    """
    Save Port Adjuster configuration to CSV file.
    
    Args:
        config: PortAdjusterConfig to save
        csv_path: Path to CSV file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        csv_file = Path(csv_path)
        
        # Prepare row data
        row_data = {
            'total_exposure': f"{config.total_exposure_usd:,.0f}",
            'avg_pref_price': f"{config.avg_pref_price:.2f}",
            'long_ratio': f"{config.long_ratio_pct:.1f}",
            'short_ratio': f"{config.short_ratio_pct:.1f}"
        }
        
        # Add group columns
        all_groups = sorted(set(list(config.long_groups.keys()) + list(config.short_groups.keys())))
        
        for group in all_groups:
            row_data[f'long_{group}'] = f"{config.long_groups.get(group, 0.0):.1f}"
            row_data[f'short_{group}'] = f"{config.short_groups.get(group, 0.0):.1f}"
        
        # Write CSV
        with open(csv_file, 'w', encoding='utf-8', newline='') as f:
            fieldnames = ['total_exposure', 'avg_pref_price', 'long_ratio', 'short_ratio']
            fieldnames.extend([f'long_{g}' for g in all_groups])
            fieldnames.extend([f'short_{g}' for g in all_groups])
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(row_data)
        
        logger.info(f"[PORT_ADJUSTER_CSV] Config saved to CSV: {csv_path}")
        return True
        
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_CSV] Error saving CSV: {e}", exc_info=True)
        return False





