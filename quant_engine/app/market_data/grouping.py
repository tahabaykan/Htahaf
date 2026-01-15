"""
Grouping Module
Resolves group keys for symbols based on CSV static data.

TWO-TIER GROUPING SYSTEM:

1) PRIMARY GROUP = FILE_GROUP (Primary Strategy Regime)
   - Determines main behavior characteristics:
     * Maturity structure (fixed maturity vs perpetual)
     * Coupon type (fixed vs floating)
     * Issuer quality
     * Sector risk
     * Liquidity profile
   - Examples (from Janall): heldkuponlu, heldff, helddeznff, heldnff, heldflr, heldgarabetaltiyedi,
     heldkuponlukreciliz, heldkuponlukreorta, heldotelremorta, heldsolidbig, heldtitrekhc,
     heldbesmaturlu, heldcilizyeniyedi, heldcommonsuz, highmatur, notcefilliquid, notbesmaturlu,
     nottitrekhc, salakilliquid, shitremhc, rumoreddanger
   - Total: ~22 primary groups

2) SECONDARY GROUP = CGRUP (ONLY for kuponlu groups)
   - Represents coupon band (C400, C425, C450, C475, C500, C525, C550, C575, C600)
   - ONLY used for kuponlu groups: heldkuponlu, heldkuponlukreciliz, heldkuponlukreorta
   - Other groups IGNORE CGRUP completely
   - Why? Kuponlu groups have:
     * Fixed coupon
     * No maturity
     * Duration and rate sensitivity entirely coupon-driven
     * C400 ≠ C550 (different benchmarks, different behavior)
   - Janall logic: kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']

Group Key Rules:
- If primary_group in kuponlu_groups and CGRUP exists: group_key = f"{primary_group}:{CGRUP}"
- Else: group_key = primary_group (CGRUP is ignored)

This structure ensures:
- Each primary group maintains its natural mean-reversion and sensitivity regime
- Kuponlu groups get proper coupon-band-based sub-grouping
- CGRUP is never mistakenly used as a global group
- Matches Janall's GORT calculation logic exactly
"""

from typing import Dict, Any, Optional
import pandas as pd
import os
from pathlib import Path
from app.core.logger import logger


# Group file mapping (Janall mantığı - her grubun ayrı CSV dosyası var)
GROUP_FILE_MAP = {
    'heldff': 'ssfinekheldff.csv',
    'helddeznff': 'ssfinekhelddeznff.csv', 
    'heldkuponlu': 'ssfinekheldkuponlu.csv',
    'heldnff': 'ssfinekheldnff.csv',
    'heldflr': 'ssfinekheldflr.csv',
    'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
    'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
    'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
    'heldotelremorta': 'ssfinekheldotelremorta.csv',
    'heldsolidbig': 'ssfinekheldsolidbig.csv',
    'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
    'highmatur': 'ssfinekhighmatur.csv',
    'notcefilliquid': 'ssfineknotcefilliquid.csv',
    'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
    'nottitrekhc': 'ssfineknottitrekhc.csv',
    'salakilliquid': 'ssfineksalakilliquid.csv',
    'shitremhc': 'ssfinekshitremhc.csv',
    'heldcilizyeniyedi': 'ssfinekheldcilizyeniyedi.csv',
    'heldcommonsuz': 'ssfinekheldcommonsuz.csv',
    'notheldtitrekhc': 'ssfineknotheldtitrekhc.csv',
    'rumoreddanger': 'ssfinekrumoreddanger.csv'
}

# Cache for group file lookups (symbol -> group mapping)
_group_cache: Dict[str, Optional[str]] = {}
_group_symbols_cache: Dict[str, set] = {}
_group_files_loaded = False


def _load_group_files(base_path: Optional[Path] = None) -> Dict[str, set]:
    """
    Load all group CSV files and create symbol -> group mapping.
    Janall mantığı: Her grubun ayrı CSV dosyası var, PREF IBKR kolonunda symbol'ler var.
    
    Returns:
        Dict mapping group_name -> set of symbols (PREF_IBKR values)
    """
    global _group_files_loaded, _group_symbols_cache
    
    if _group_files_loaded and _group_symbols_cache:
        return _group_symbols_cache
    
    group_symbols: Dict[str, set] = {}
    
    # Find base path (quant_engine root or current directory)
    if base_path is None:
        # Try to find quant_engine directory
        current = Path(__file__).parent.parent.parent
        if current.name == 'quant_engine':
            base_path = current.parent
        else:
            base_path = Path.cwd()
    
    for group, file_name in GROUP_FILE_MAP.items():
        # Try multiple possible locations
        possible_paths = [
            base_path / file_name,
            base_path / 'janall' / file_name,
            Path(file_name),  # Current directory
            Path('janall') / file_name
        ]
        
        for file_path in possible_paths:
            if file_path.exists():
                try:
                    df = pd.read_csv(file_path)
                    if 'PREF IBKR' in df.columns:
                        symbols = set(df['PREF IBKR'].astype(str).str.strip().tolist())
                        group_symbols[group] = symbols
                        logger.debug(f"Loaded {len(symbols)} symbols for group {group} from {file_path}")
                        break
                except Exception as e:
                    logger.warning(f"Error reading group file {file_path}: {e}")
                    continue
    
    _group_files_loaded = True
    _group_symbols_cache = group_symbols
    logger.info(f"Loaded {len(group_symbols)} group files with {sum(len(syms) for syms in group_symbols.values())} total symbols")
    return group_symbols


def resolve_primary_group(static_row: Dict[str, Any], symbol: Optional[str] = None) -> Optional[str]:
    """
    Resolve PRIMARY GROUP (file_group) for a symbol using Janall mantığı.
    
    Janall'da her grubun ayrı CSV dosyası var (ssfinekheldff.csv, etc.).
    Symbol'ü tüm grup CSV dosyalarında PREF IBKR kolonunda arar.
    
    Args:
        static_row: Static data row from CSV (must include PREF_IBKR or 'PREF IBKR')
        symbol: Optional symbol string (PREF_IBKR). If not provided, extracted from static_row.
        
    Returns:
        Primary group string (e.g., "heldff", "heldkuponlu", "heldsolidbig")
        Returns None if symbol not found in any group file
    """
    global _group_cache
    
    try:
        # Extract symbol from static_row if not provided
        if symbol is None:
            for col_name in ['PREF_IBKR', 'PREF IBKR']:
                if col_name in static_row:
                    symbol = str(static_row[col_name]).strip()
                    break
        
        if not symbol:
            logger.warning(f"No symbol found in static_row: {list(static_row.keys())}")
            return None
        
        # Check cache first
        if symbol in _group_cache:
            return _group_cache[symbol]
        
        # Try GROUP column first (if exists in CSV)
        for col_name in ['GROUP', 'file_group', 'group']:
            if col_name in static_row:
                value = static_row[col_name]
                if value is not None and str(value).strip() and str(value).strip().lower() != 'nan':
                    file_group = str(value).strip().lower()
                    _group_cache[symbol] = file_group
                    return file_group
        
        # Load group files and search for symbol
        group_symbols = _load_group_files()
        
        # Search for symbol in all groups
        for group, symbols in group_symbols.items():
            if symbol in symbols:
                _group_cache[symbol] = group
                logger.debug(f"Symbol {symbol} found in group {group}")
                return group
        
        # Not found in any group file
        logger.warning(f"Symbol {symbol} not found in any group CSV file")
        _group_cache[symbol] = None
        return None
        
    except Exception as e:
        logger.error(f"Error resolving primary group for {symbol}: {e}", exc_info=True)
        return None


def resolve_secondary_group(static_row: Dict[str, Any], primary_group: str) -> Optional[str]:
    """
    Resolve SECONDARY GROUP (CGRUP) for a symbol.
    ONLY used for kuponlu groups: heldkuponlu, heldkuponlukreciliz, heldkuponlukreorta
    
    Args:
        static_row: Static data row from CSV
        primary_group: Primary group string (from resolve_primary_group)
        
    Returns:
        Secondary group string (e.g., "c400", "c425") or None
        Returns None if primary_group is not a kuponlu group or CGRUP is missing
    """
    # Secondary group (CGRUP) is ONLY used for kuponlu groups
    # Janall'da 3 kuponlu grup var: heldkuponlu, heldkuponlukreciliz, heldkuponlukreorta
    kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
    
    if primary_group not in kuponlu_groups:
        return None
    
    try:
        cgrup = static_row.get('CGRUP')
        if cgrup:
            cgrup_str = str(cgrup).strip()
            if cgrup_str and cgrup_str.upper() != 'N/A':
                return cgrup_str.lower()
        return None
    except Exception as e:
        logger.debug(f"Error resolving secondary group: {e}")
        return None


def resolve_group_key(static_row: Dict[str, Any]) -> Optional[str]:
    """
    Resolve full group key for a symbol (PRIMARY:SECONDARY format).
    
    This is the main entry point for grouping logic.
    
    Args:
        static_row: Static data row from CSV (must include file_group and optionally CGRUP)
        
    Returns:
        Group key string:
        - For heldkuponlu: "heldkuponlu:c400" (if CGRUP exists)
        - For other groups: "heldff", "heldsolidbig", etc. (CGRUP ignored)
        Returns None if file_group is missing
    """
    try:
        # Step 1: Resolve PRIMARY GROUP
        # Extract symbol for lookup
        symbol = None
        for col_name in ['PREF_IBKR', 'PREF IBKR']:
            if col_name in static_row:
                symbol = str(static_row[col_name]).strip()
                break
        
        primary_group = resolve_primary_group(static_row, symbol)
        if not primary_group:
            return None
        
        # Step 2: Resolve SECONDARY GROUP (only for heldkuponlu)
        secondary_group = resolve_secondary_group(static_row, primary_group)
        
        # Step 3: Build group key
        # Kuponlu groups: heldkuponlu, heldkuponlukreciliz, heldkuponlukreorta
        kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
        
        if primary_group in kuponlu_groups and secondary_group:
            # Kuponlu group with CGRUP: "heldkuponlu:c400", "heldkuponlukreciliz:c425", etc.
            return f"{primary_group}:{secondary_group}"
        elif primary_group in kuponlu_groups and not secondary_group:
            # Kuponlu group without CGRUP: fallback to just primary group
            logger.debug(f"{primary_group} symbol but no CGRUP found, using primary group only")
            return primary_group
        else:
            # All other groups: use primary group as-is (CGRUP is ignored)
            return primary_group
        
    except Exception as e:
        logger.error(f"Error resolving group key: {e}", exc_info=True)
        return None


def get_all_group_keys(static_store) -> Dict[str, list]:
    """
    Get all group keys and their symbols from static store.
    
    Args:
        static_store: StaticDataStore instance
        
    Returns:
        Dict mapping group_key -> list of symbols
    """
    groups: Dict[str, list] = {}
    
    try:
        symbols = static_store.get_all_symbols()
        for symbol in symbols:
            static_data = static_store.get_static_data(symbol)
            if not static_data:
                continue
            
            group_key = resolve_group_key(static_data)
            if group_key:
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(symbol)
        
        logger.info(f"Found {len(groups)} groups with {sum(len(syms) for syms in groups.values())} total symbols")
        return groups
        
    except Exception as e:
        logger.error(f"Error getting all group keys: {e}", exc_info=True)
        return {}



