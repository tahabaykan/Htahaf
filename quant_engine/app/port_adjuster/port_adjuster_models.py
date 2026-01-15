"""
Port Adjuster Data Models

Data structures for portfolio exposure and group allocation.
"""

from typing import Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class GroupAllocation(BaseModel):
    """Group allocation (lot rights per group)"""
    group: str = Field(..., description="Group name (e.g., 'heldff', 'heldkuponlu')")
    weight_pct: float = Field(..., ge=0.0, le=100.0, description="Weight percentage (0-100)")
    max_lot: float = Field(..., ge=0.0, description="Maximum lot allocation for this group")
    max_value_usd: float = Field(..., ge=0.0, description="Maximum value in USD for this group")
    
    class Config:
        json_schema_extra = {
            "example": {
                "group": "heldff",
                "weight_pct": 35.0,
                "max_lot": 11900.0,
                "max_value_usd": 297500.0
            }
        }


class PortAdjusterConfig(BaseModel):
    """Port Adjuster configuration (user inputs)"""
    total_exposure_usd: float = Field(1000000.0, gt=0.0, description="Total exposure in USD")
    avg_pref_price: float = Field(25.0, gt=0.0, description="Average preferred stock price in USD")
    long_ratio_pct: float = Field(85.0, ge=0.0, le=100.0, description="Long ratio percentage (0-100)")
    short_ratio_pct: float = Field(15.0, ge=0.0, le=100.0, description="Short ratio percentage (0-100)")
    
    # Group weights (Long)
    long_groups: Dict[str, float] = Field(
        default_factory=lambda: {
            'heldcilizyeniyedi': 0.0,
            'heldcommonsuz': 0.0,
            'helddeznff': 10.0,
            'heldff': 35.0,
            'heldflr': 0.0,
            'heldgarabetaltiyedi': 0.0,
            'heldkuponlu': 15.0,
            'heldkuponlukreciliz': 0.0,
            'heldkuponlukreorta': 0.0,
            'heldnff': 5.0,
            'heldotelremorta': 3.0,
            'heldsolidbig': 5.0,
            'heldtitrekhc': 8.0,
            'highmatur': 15.0,
            'notbesmaturlu': 0.0,
            'notcefilliquid': 0.0,
            'nottitrekhc': 4.0,
            'rumoreddanger': 0.0,
            'salakilliquid': 0.0,
            'shitremhc': 0.0
        },
        description="Long group weights (percentage per group)"
    )
    
    # Group weights (Short)
    short_groups: Dict[str, float] = Field(
        default_factory=lambda: {
            'heldcilizyeniyedi': 0.0,
            'heldcommonsuz': 0.0,
            'helddeznff': 30.0,
            'heldff': 0.0,
            'heldflr': 0.0,
            'heldgarabetaltiyedi': 0.0,
            'heldkuponlu': 50.0,
            'heldkuponlukreciliz': 20.0,
            'heldkuponlukreorta': 0.0,
            'heldnff': 0.0,
            'heldotelremorta': 0.0,
            'heldsolidbig': 0.0,
            'heldtitrekhc': 0.0,
            'highmatur': 0.0,
            'notbesmaturlu': 0.0,
            'notcefilliquid': 0.0,
            'nottitrekhc': 0.0,
            'rumoreddanger': 0.0,
            'salakilliquid': 0.0,
            'shitremhc': 0.0
        },
        description="Short group weights (percentage per group)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_exposure_usd": 1000000.0,
                "avg_pref_price": 25.0,
                "long_ratio_pct": 85.0,
                "short_ratio_pct": 15.0,
                "long_groups": {
                    "heldff": 35.0,
                    "heldkuponlu": 15.0,
                    "highmatur": 15.0
                },
                "short_groups": {
                    "heldkuponlu": 50.0,
                    "helddeznff": 30.0
                }
            }
        }


class PortAdjusterSnapshot(BaseModel):
    """Port Adjuster snapshot (calculated outputs)"""
    timestamp: datetime = Field(default_factory=datetime.now, description="Snapshot timestamp")
    last_saved_at: Optional[datetime] = Field(None, description="When config was last persisted")
    config_source: Optional[str] = Field(None, description="Source of loaded config (csv/json/default/preset)")
    
    # Core calculations
    total_lot: float = Field(..., ge=0.0, description="Total lot (total_exposure_usd / avg_pref_price)")
    long_lot: float = Field(..., ge=0.0, description="Long lot (total_lot * long_ratio_pct / 100)")
    short_lot: float = Field(..., ge=0.0, description="Short lot (total_lot * short_ratio_pct / 100)")
    
    # Group allocations
    long_allocations: Dict[str, GroupAllocation] = Field(
        default_factory=dict,
        description="Long group allocations"
    )
    short_allocations: Dict[str, GroupAllocation] = Field(
        default_factory=dict,
        description="Short group allocations"
    )
    
    # Config reference (for traceability)
    config: PortAdjusterConfig = Field(..., description="Configuration used for this snapshot")
    
    # Validation flags
    long_total_pct: float = Field(..., description="Sum of long group percentages")
    short_total_pct: float = Field(..., description="Sum of short group percentages")
    is_valid: bool = Field(..., description="True if allocations are valid (sums ~100%)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2024-01-15T10:30:00",
                "total_lot": 40000.0,
                "long_lot": 34000.0,
                "short_lot": 6000.0,
                "last_saved_at": "2024-01-15T10:29:00",
                "config_source": "csv:exposureadjuster.csv",
                "long_allocations": {
                    "heldff": {
                        "group": "heldff",
                        "weight_pct": 35.0,
                        "max_lot": 11900.0,
                        "max_value_usd": 297500.0
                    }
                },
                "short_allocations": {
                    "heldkuponlu": {
                        "group": "heldkuponlu",
                        "weight_pct": 50.0,
                        "max_lot": 3000.0,
                        "max_value_usd": 75000.0
                    }
                },
                "long_total_pct": 100.0,
                "short_total_pct": 100.0,
                "is_valid": True
            }
        }

