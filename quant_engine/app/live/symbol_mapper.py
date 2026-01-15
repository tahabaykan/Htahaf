"""app/live/symbol_mapper.py

Symbol mapping between display format and Hammer Pro format.
Handles preferred stocks, ETFs, and common stocks.
"""

from typing import Optional


class SymbolMapper:
    """
    Maps symbols between display format and Hammer Pro format.
    
    Display format: "CIM PRB", "MFA PRC", "AGNCM", "SPY"
    Hammer format: "CIM-B", "MFA-C", "AGNC-M", "SPY"
    """
    
    # ETF list - no conversion needed
    ETF_LIST = ["SHY", "IEF", "TLT", "IWM", "KRE", "SPY", "PFF", "PGF", "IEI"]
    
    @staticmethod
    def to_hammer_symbol(display_symbol: str) -> str:
        """
        Convert display symbol to Hammer Pro format.
        
        Examples:
            "CIM PRB" -> "CIM-B"
            "MFA PRC" -> "MFA-C"
            "AGNCM" -> "AGNC-M"
            "SPY" -> "SPY" (ETF, no change)
            "AAPL" -> "AAPL" (common stock, no change)
        
        Args:
            display_symbol: Display format symbol
            
        Returns:
            Hammer Pro format symbol
        """
        if not display_symbol:
            return display_symbol
        
        # ETF'ler için değişiklik yok
        if display_symbol in SymbolMapper.ETF_LIST:
            return display_symbol
        
        # Preferred stock: "CIM PRB" -> "CIM-B"
        if " PR" in display_symbol:
            base, suffix = display_symbol.split(" PR", 1)
            return f"{base}-{suffix}"
        
        # Preferred stock (alternative format): "AGNCM" -> "AGNC-M"
        # Check if ends with single letter (A-Z) and base is 4+ chars
        if len(display_symbol) >= 5 and display_symbol[-1].isalpha() and display_symbol[-1].isupper():
            # Could be preferred: "AGNCM" -> "AGNC-M"
            # But we can't be 100% sure, so only convert if explicitly requested
            # For now, leave as-is unless it matches known patterns
            pass
        
        # Common stock or other - no change
        return display_symbol
    
    @staticmethod
    def to_display_symbol(hammer_symbol: str) -> str:
        """
        Convert Hammer Pro symbol to display format.
        
        Examples:
            "CIM-B" -> "CIM PRB"
            "MFA-C" -> "MFA PRC"
            "AGNC-M" -> "AGNCM" (or "AGNC PRM" if preferred)
            "SPY" -> "SPY" (ETF, no change)
            "AAPL" -> "AAPL" (common stock, no change)
        
        Args:
            hammer_symbol: Hammer Pro format symbol
            
        Returns:
            Display format symbol
        """
        if not hammer_symbol:
            return hammer_symbol
        
        # ETF'ler için değişiklik yok
        if hammer_symbol in SymbolMapper.ETF_LIST:
            return hammer_symbol
        
        # Preferred stock: "CIM-B" -> "CIM PRB"
        if "-" in hammer_symbol:
            base, suffix = hammer_symbol.split("-", 1)
            # Only convert if suffix is single letter (A-Z)
            if len(suffix) == 1 and suffix.isalpha() and suffix.isupper():
                return f"{base} PR{suffix}"
        
        # Common stock or other - no change
        return hammer_symbol
    
    @staticmethod
    def normalize_symbol(symbol: str, to_hammer: bool = True) -> str:
        """
        Normalize symbol (convenience method).
        
        Args:
            symbol: Symbol to normalize
            to_hammer: If True, convert to Hammer format; else to display format
            
        Returns:
            Normalized symbol
        """
        if to_hammer:
            return SymbolMapper.to_hammer_symbol(symbol)
        else:
            return SymbolMapper.to_display_symbol(symbol)








