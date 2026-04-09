"""
Zero-Snap Validator

KURAL: DECREASE tag'li emirlerde potential_qty -400 ile +400 arasında kalacaksa,
pozisyon TAMAMEN kapatılmalı (0'a getirilmeli). İncik cincik 50 lot, -50 lot 
gibi küçük pozisyonlar kalmamalı.

Örnek:
- Current: +250 LONG
- Proposed: -200 SELL → Potential: +50 (incik cincik!)
- Adjusted: -250 SELL → Potential: 0 ✅

- Current: +1000 LONG
- Proposed: -200 SELL → Potential: +800 (büyük, sorun yok)
- Adjusted: -200 SELL (aynen gider) ✅
"""

from typing import Tuple
from app.core.logger import logger


def apply_zero_snap_rule(
    symbol: str,
    current_qty: float,
    proposed_qty: float,  # BUY için pozitif, SELL için negatif
    order_tag: str,
    is_decrease: bool = True
) -> Tuple[float, float]:
    """
    0-SNAP Rule: DECREASE emirlerinde potential_qty küçük kalacaksa 0'a ayarla.
    
    Args:
        symbol: Sembol adı (log için)
        current_qty: Mevcut pozisyon (+250 LONG, -220 SHORT, +1000 LONG)
        proposed_qty: Önerilen değişim (+300 BUY, -300 SELL, -200 SELL)
        order_tag: Intent category (LT_TRIM, KARBOTU, vb.)
        is_decrease: Bu DECREASE tag'li bir emir mi?
        
    Returns:
        (adjusted_qty, potential_qty)
        
    Examples:
        >>> # İncik cincik kalan (0'a getir!)
        >>> apply_zero_snap_rule("BK PRK", 250, -200, "LT_TRIM", True)
        (-250.0, 0.0)  # SELL 250 (tam kapatma)
        
        >>> # Büyük pozisyon (sorun yok)
        >>> apply_zero_snap_rule("BK PRK", 1000, -200, "LT_TRIM", True)
        (-200.0, 800.0)  # SELL 200 (aynen gider)
        
        >>> # Ters geçme (0'a getir!)
        >>> apply_zero_snap_rule("REGCO", -220, 300, "KARBOTU", True)
        (220.0, 0.0)  # BUY 220 (tam kapatma)
    """
    # INCREASE emirlerinde snap YOK
    if not is_decrease:
        potential_qty = current_qty + proposed_qty
        return proposed_qty, potential_qty
    
    # Potential qty hesapla
    potential_qty = current_qty + proposed_qty
    
    # KURAL: Potential_qty küçük kalacaksa (-400 < x < 400) → 0'a getir
    # UYARI: 0 zaten sorun yok (tam kapatma başarılı)
    in_tiny_range = -400 < potential_qty < 400 and potential_qty != 0
    
    if in_tiny_range:
        # İNCİK CİNCİK POZISYON KALACAK!
        # Direkt 0'a getir
        adjusted_qty = -current_qty
        potential_qty = 0
        
        logger.info(
            f"[ZERO_SNAP] ✂️ {symbol}: "
            f"current={current_qty:+.0f}, "
            f"proposed={proposed_qty:+.0f}, "
            f"would_leave={current_qty + proposed_qty:+.0f} → "
            f"SNAPPED to {adjusted_qty:+.0f} (potential=0)"
        )
        
        return adjusted_qty, potential_qty
    
    # Snap gerekmiyorsa orijinal değerleri dön
    return proposed_qty, potential_qty


def is_decrease_order(intent_category: str) -> bool:
    """
    Check if this is a DECREASE order.
    
    DECREASE tags: LT_TRIM, KARBOTU, REDUCEMORE, any tag with DEC/DECREASE/REDUCE
    INCREASE tags: ADDNEWPOS, MM, any tag with INC/INCREASE/ADD
    """
    if not intent_category:
        return False
    
    category_upper = intent_category.upper()
    
    # Açık DECREASE belirteçleri (DEC catches both DEC and DECREASE)
    decrease_keywords = ['DEC', 'REDUCE', 'LT_TRIM', 'KARBOTU', 'REDUCEMORE', 'TRIM']
    
    return any(keyword in category_upper for keyword in decrease_keywords)
