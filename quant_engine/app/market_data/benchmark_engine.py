"""
Benchmark Engine
Calculates benchmark change from ETF data using two-tier grouping system.

TWO-TIER GROUPING SYSTEM:
1) PRIMARY GROUP = FILE_GROUP (determines main benchmark regime)
2) SECONDARY GROUP = CGRUP (ONLY for heldkuponlu, determines coupon-band-specific benchmark)

For heldkuponlu: benchmark = f(CGRUP) → different ETF formulas per coupon band
For other groups: benchmark = f(primary_group) → group-specific benchmark
"""

from typing import Dict, Any, Optional
import yaml
from pathlib import Path
from app.core.logger import logger
from app.market_data.grouping import resolve_primary_group, resolve_secondary_group

# Global singleton instance
_benchmark_engine_instance: Optional['BenchmarkEngine'] = None


def get_benchmark_engine(config_path: Optional[str] = None) -> 'BenchmarkEngine':
    """
    Get or create singleton BenchmarkEngine instance.
    Config is loaded ONLY ONCE at first initialization.
    
    Args:
        config_path: Optional config path (only used on first initialization)
        
    Returns:
        Singleton BenchmarkEngine instance
    """
    global _benchmark_engine_instance
    if _benchmark_engine_instance is None:
        _benchmark_engine_instance = BenchmarkEngine(config_path=config_path)
    return _benchmark_engine_instance


class BenchmarkEngine:
    """
    Calculates benchmark change from ETF market data.
    Uses two-tier grouping system for benchmark selection.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize BenchmarkEngine with config file.
        
        Args:
            config_path: Path to benchmark config file (default: benchmark_rules.yaml, fallback: group_benchmark.yaml)
        """
        if config_path is None:
            # Default path: app/config/benchmark_rules.yaml (preferred), fallback to group_benchmark.yaml
            base_dir = Path(__file__).parent.parent.parent
            benchmark_rules_path = base_dir / "app" / "config" / "benchmark_rules.yaml"
            group_benchmark_path = base_dir / "app" / "config" / "group_benchmark.yaml"
            
            # Prefer benchmark_rules.yaml, fallback to group_benchmark.yaml
            if benchmark_rules_path.exists():
                config_path = benchmark_rules_path
            elif group_benchmark_path.exists():
                config_path = group_benchmark_path
            else:
                config_path = benchmark_rules_path  # Use as default even if doesn't exist
        
        self.config_path = config_path
        self.config = self._load_config()
        self.default_benchmark = "PFF"
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load benchmark configuration from YAML file.
        ⚠️ CRITICAL: This is called ONLY ONCE during __init__.
        Config is cached in self.config and never reloaded.
        """
        try:
            # Convert to Path if it's a string
            config_path = Path(self.config_path) if isinstance(self.config_path, str) else self.config_path
            
            if config_path and config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    logger.info(f"Benchmark config loaded from {config_path} (ONCE at startup)")
                    return config or {}
            else:
                logger.warning(f"Benchmark config file not found: {config_path}, using defaults")
                return {}
        except Exception as e:
            logger.error(f"Error loading benchmark config: {e}", exc_info=True)
            return {}
    
    def get_benchmark_formula(
        self, 
        static_data: Optional[Dict[str, Any]] = None,
        primary_group: Optional[str] = None,
        secondary_group: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get benchmark formula (ETF weights) for a symbol.
        
        Uses two-tier grouping:
        - PRIMARY GROUP determines base benchmark regime
        - For heldkuponlu, SECONDARY GROUP (CGRUP) determines coupon-band-specific formula
        - For other groups, SECONDARY GROUP is ignored
        
        Args:
            static_data: Static data row (optional, used to resolve groups if not provided)
            primary_group: Primary group string (optional, will be resolved from static_data if not provided)
            secondary_group: Secondary group string (optional, will be resolved from static_data if not provided)
            
        Returns:
            Dict mapping ETF symbol to coefficient (e.g., {'PFF': 0.36, 'TLT': 0.36, 'IEF': 0.08})
        """
        try:
            # Resolve groups if not provided
            if static_data:
                if not primary_group:
                    primary_group = resolve_primary_group(static_data)
                if not secondary_group:
                    secondary_group = resolve_secondary_group(static_data, primary_group or "")
            
            if not primary_group:
                # Fallback to default
                default_formula = self.config.get('default', {}).get('formula', {'PFF': 1.0})
                logger.debug(f"No primary group, using default benchmark formula")
                return default_formula
            
            primary_group_lower = primary_group.lower()
            
            # Special case: Kuponlu groups use CGRUP-based formulas
            # Janall'da 3 kuponlu grup var: heldkuponlu, heldkuponlukreciliz, heldkuponlukreorta
            kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
            
            if primary_group_lower in kuponlu_groups:
                if secondary_group:
                    # Use CGRUP-specific formula (shared across all kuponlu groups)
                    cgrup_lower = secondary_group.lower()
                    heldkuponlu_config = self.config.get('heldkuponlu', {})
                    cgrup_config = heldkuponlu_config.get(cgrup_lower)
                    
                    if cgrup_config and 'formula' in cgrup_config:
                        formula = cgrup_config['formula']
                        logger.debug(f"Using {primary_group_lower}:{cgrup_lower} benchmark formula")
                        return formula
                    else:
                        # CGRUP not found, use heldkuponlu default
                        heldkuponlu_default = heldkuponlu_config.get('default', {}).get('formula', {'PFF': 1.0})
                        logger.debug(f"CGRUP {cgrup_lower} not found in config, using heldkuponlu default")
                        return heldkuponlu_default
                else:
                    # Kuponlu group without CGRUP, use default
                    heldkuponlu_config = self.config.get('heldkuponlu', {})
                    heldkuponlu_default = heldkuponlu_config.get('default', {}).get('formula', {'PFF': 1.0})
                    logger.debug(f"{primary_group_lower} without CGRUP, using heldkuponlu default")
                    return heldkuponlu_default
            
            # Other groups: use primary group formula (CGRUP is ignored)
            group_config = self.config.get(primary_group_lower)
            if group_config and 'formula' in group_config:
                formula = group_config['formula']
                logger.debug(f"Using {primary_group_lower} benchmark formula")
                return formula
            
            # Fallback to default
            default_formula = self.config.get('default', {}).get('formula', {'PFF': 1.0})
            logger.debug(f"No config for {primary_group_lower}, using default benchmark formula")
            return default_formula
            
        except Exception as e:
            logger.error(f"Error getting benchmark formula: {e}", exc_info=True)
            return {'PFF': 1.0}  # Safe fallback
    
    def get_benchmark_symbol(self, symbol: str, static_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Get primary benchmark symbol for a given symbol.
        For composite benchmarks, returns the primary ETF (highest weight).
        
        Args:
            symbol: Symbol to get benchmark for
            static_data: Static data row (optional, used to resolve groups)
            
        Returns:
            Primary benchmark symbol (default: PFF)
        """
        formula = self.get_benchmark_formula(static_data=static_data)
        if formula:
            # Return ETF with highest weight
            primary_etf = max(formula.items(), key=lambda x: x[1])[0]
            return primary_etf
        return self.default_benchmark
    
    def compute_composite_benchmark(
        self,
        etf_data_store: Dict[str, Dict[str, Any]],
        formula: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Compute composite benchmark value from ETF data using formula.
        
        Args:
            etf_data_store: Dict of ETF market data {symbol: data}
            formula: Benchmark formula {ETF: coefficient}
            
        Returns:
            Dict with:
                - benchmark_value: Composite benchmark value
                - benchmark_last: Last composite value
                - benchmark_prev_close: Previous close composite value
                - benchmark_formula: Formula used
        """
        benchmark_last = 0.0
        benchmark_prev_close = 0.0
        
        for etf_symbol, coefficient in formula.items():
            etf_data = etf_data_store.get(etf_symbol)
            if etf_data:
                last = etf_data.get('last') or etf_data.get('price')
                prev_close = etf_data.get('prev_close')
                
                if last is not None:
                    benchmark_last += last * coefficient
                if prev_close is not None:
                    benchmark_prev_close += prev_close * coefficient
        
        return {
            'benchmark_value': benchmark_last if benchmark_last > 0 else None,
            'benchmark_last': benchmark_last if benchmark_last > 0 else None,
            'benchmark_prev_close': benchmark_prev_close if benchmark_prev_close > 0 else None,
            'benchmark_formula': formula
        }
    
    def compute_benchmark_change(
        self, 
        etf_data_store: Dict[str, Dict[str, Any]],
        static_data: Optional[Dict[str, Any]] = None,
        primary_group: Optional[str] = None,
        secondary_group: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compute benchmark change from ETF market data using two-tier grouping.
        
        Args:
            etf_data_store: Dict of ETF market data {symbol: data}
            static_data: Static data row (optional, used to resolve groups)
            primary_group: Primary group string (optional)
            secondary_group: Secondary group string (optional)
            
        Returns:
            Dict with:
                - benchmark_chg: Change in cents (composite last - composite prev_close)
                - benchmark_chg_percent: Change in percentage
                - benchmark_symbol: Primary ETF symbol (highest weight)
                - benchmark_formula: Formula used {ETF: coefficient}
                - benchmark_last: Composite last value
                - benchmark_prev_close: Composite prev_close value
        """
        try:
            # Get benchmark formula based on two-tier grouping
            formula = self.get_benchmark_formula(
                static_data=static_data,
                primary_group=primary_group,
                secondary_group=secondary_group
            )
            
            # Compute composite benchmark
            composite = self.compute_composite_benchmark(etf_data_store, formula)
            
            benchmark_last = composite.get('benchmark_last')
            benchmark_prev_close = composite.get('benchmark_prev_close')
            
            if benchmark_last is None or benchmark_prev_close is None or benchmark_prev_close <= 0:
                return {
                    'benchmark_chg': None,
                    'benchmark_chg_percent': None,
                    'benchmark_symbol': self.get_benchmark_symbol("", static_data),
                    'benchmark_formula': formula,
                    'benchmark_last': benchmark_last,
                    'benchmark_prev_close': benchmark_prev_close
                }
            
            # Calculate change in cents
            benchmark_chg = benchmark_last - benchmark_prev_close
            
            # Calculate change in percentage
            benchmark_chg_percent = (benchmark_chg / benchmark_prev_close) * 100
            
            # Get primary ETF symbol
            primary_etf = max(formula.items(), key=lambda x: x[1])[0] if formula else self.default_benchmark
            
            return {
                'benchmark_chg': round(benchmark_chg, 4),
                'benchmark_chg_percent': round(benchmark_chg_percent, 4),
                'benchmark_symbol': primary_etf,
                'benchmark_formula': formula,
                'benchmark_last': round(benchmark_last, 4),
                'benchmark_prev_close': round(benchmark_prev_close, 4)
            }
            
        except Exception as e:
            logger.error(f"Error computing benchmark change: {e}", exc_info=True)
            return {
                'benchmark_chg': None,
                'benchmark_chg_percent': None,
                'benchmark_symbol': self.default_benchmark,
                'benchmark_formula': {'PFF': 1.0},
                'benchmark_last': None,
                'benchmark_prev_close': None
            }
    
    def get_benchmark_for_symbol(
        self, 
        symbol: str, 
        etf_data_store: Dict[str, Dict[str, Any]],
        static_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get benchmark data for a symbol using two-tier grouping.
        
        Args:
            symbol: Symbol to get benchmark for
            etf_data_store: Dict of ETF market data {symbol: data}
            static_data: Static data row (optional, used to resolve groups)
            
        Returns:
            Benchmark change dict with composite benchmark calculation
        """
        return self.compute_benchmark_change(
            etf_data_store=etf_data_store,
            static_data=static_data
        )



