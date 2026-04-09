"""
Enhanced Tag Generator

Generates detailed tags for all engines that include stage/step/variant information.

UNIFIED TAG FORMAT:
    [FR_][REV_]{SOURCE}_{DIRECTION}_{ACTION}[_DETAIL]

Examples:
    - LT_LONG_DEC_STAGE_1_AGGRESSIVE
    - LT_LONG_DEC_STAGE_2_SMALL
    - KARBOTU_LONG_DEC_STEP_2
    - KARBOTU_SHORT_DEC_STEP_9
    - ADDNEWPOS_LONG_INC_JFIN_LT
    - MM_LONG_INC_SMALL
    - REV_MM_LONG_DEC (take profit after MM buy)
    - FR_REV_MM_LONG_DEC (fronted REV)
"""
from enum import Enum
from typing import Optional


class Side(Enum):
    """Position side"""
    LONG = "LONG"
    SHORT = "SHORT"


class Direction(Enum):
    """Order direction"""
    INCREASE = "INC"
    DECREASE = "DEC"


class LTStage(Enum):
    """LT_TRIM stages"""
    STAGE_1 = "STAGE_1"
    STAGE_2 = "STAGE_2"


class LTVariant(Enum):
    """LT_TRIM variants"""
    AGGRESSIVE = "AGGRESSIVE"
    LADDER = "LADDER"
    SMALL = "SMALL"


def generate_lt_trim_tag(
    side: Side,
    direction: Direction,
    stage: LTStage,
    variant: Optional[LTVariant] = None
) -> str:
    """
    Generate LT_TRIM tag with stage and variant information.
    
    Examples:
        LT_LONG_DEC_STAGE_1
        LT_LONG_DEC_STAGE_1_AGGRESSIVE
        LT_SHORT_INC_STAGE_2_LADDER
    """
    tag = f"LT_{side.value}_{direction.value}_{stage.value}"
    
    if variant:
        tag += f"_{variant.value}"
    
    return tag


def generate_karbotu_tag(
    side: Side,
    step: int
) -> str:
    """
    Generate KARBOTU tag with step information.
    
    Examples:
        KARBOTU_LONG_DEC_STEP_2
        KARBOTU_SHORT_DEC_STEP_9
    """
    # KARBOTU always decreases positions
    return f"KARBOTU_{side.value}_DEC_STEP_{step}"


def generate_addnewpos_tag(
    side: Side,
    source: str = "JFIN_LT"
) -> str:
    """
    Generate ADDNEWPOS tag.
    
    Examples:
        ADDNEWPOS_LONG_INC_JFIN_LT
        ADDNEWPOS_SHORT_INC_JFIN_LT
    """
    # ADDNEWPOS always increases positions
    return f"ADDNEWPOS_{side.value}_INC_{source}"


def generate_mm_tag(
    side: Side,
    direction: Direction,
    variant: Optional[str] = None
) -> str:
    """
    Generate MM (Market Making) tag.
    
    Examples:
        MM_LONG_INC
        MM_LONG_INC_SMALL
        MM_SHORT_DEC_AGGRESSIVE
    """
    tag = f"MM_{side.value}_{direction.value}"
    
    if variant:
        tag += f"_{variant}"
    
    return tag


def generate_reducemore_tag(
    side: Side,
    emergency: bool = False
) -> str:
    """
    Generate REDUCEMORE tag.
    
    Examples:
        REDUCEMORE_LONG_DEC
        REDUCEMORE_LONG_DEC_EMERGENCY
    """
    tag = f"REDUCEMORE_{side.value}_DEC"
    
    if emergency:
        tag += "_EMERGENCY"
    
    return tag


# Convenience functions for common cases
def lt_long_decrease_stage1(aggressive: bool = False) -> str:
    """LT LONG DECREASE Stage 1"""
    variant = LTVariant.AGGRESSIVE if aggressive else None
    return generate_lt_trim_tag(Side.LONG, Direction.DECREASE, LTStage.STAGE_1, variant)


def lt_long_decrease_stage2(variant: Optional[LTVariant] = None) -> str:
    """LT LONG DECREASE Stage 2"""
    return generate_lt_trim_tag(Side.LONG, Direction.DECREASE, LTStage.STAGE_2, variant)


def karbotu_long_step(step: int) -> str:
    """KARBOTU LONG Step N"""
    return generate_karbotu_tag(Side.LONG, step)


def karbotu_short_step(step: int) -> str:
    """KARBOTU SHORT Step N"""
    return generate_karbotu_tag(Side.SHORT, step)


def addnewpos_long() -> str:
    """ADDNEWPOS LONG INCREASE"""
    return generate_addnewpos_tag(Side.LONG)


def addnewpos_short() -> str:
    """ADDNEWPOS SHORT INCREASE"""
    return generate_addnewpos_tag(Side.SHORT)
