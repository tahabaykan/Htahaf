"""tests/unit/test_risk_limits_parsing.py

Test risk limits parsing from YAML, JSON, environment variables.
"""

import pytest
import os
import json
import tempfile
from pathlib import Path

from app.risk.risk_limits import RiskLimits, load_risk_limits


class TestRiskLimitsParsing:
    """Test risk limits parsing"""
    
    def test_default_values(self):
        """Test default values"""
        limits = RiskLimits()
        
        assert limits.max_position_per_symbol == 10000.0
        assert limits.max_daily_loss == 5000.0
        assert limits.max_trades_per_minute == 10
        print("✓ Default values correct")
    
    def test_yaml_parsing(self):
        """Test YAML config parsing"""
        yaml_content = """
max_position_per_symbol: 5000.0
max_daily_loss: 2000.0
max_trades_per_minute: 5
"""
        # Create temp YAML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            limits = load_risk_limits(temp_path)
            
            assert limits.max_position_per_symbol == 5000.0
            assert limits.max_daily_loss == 2000.0
            assert limits.max_trades_per_minute == 5
            print("✓ YAML parsing works")
        finally:
            os.unlink(temp_path)
    
    def test_json_parsing(self):
        """Test JSON config parsing"""
        json_content = {
            "max_position_per_symbol": 3000.0,
            "max_daily_loss": 1500.0,
            "max_trades_per_minute": 3
        }
        
        # Create temp JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(json_content, f)
            temp_path = f.name
        
        try:
            limits = load_risk_limits(temp_path)
            
            assert limits.max_position_per_symbol == 3000.0
            assert limits.max_daily_loss == 1500.0
            assert limits.max_trades_per_minute == 3
            print("✓ JSON parsing works")
        finally:
            os.unlink(temp_path)
    
    def test_environment_variables(self):
        """Test environment variable parsing"""
        # Set environment variables
        os.environ['RISK_MAX_POSITION_PER_SYMBOL'] = '2500.0'
        os.environ['RISK_MAX_DAILY_LOSS'] = '1000.0'
        os.environ['RISK_MAX_TRADES_PER_MINUTE'] = '2'
        
        try:
            limits = load_risk_limits()  # No config file, use env vars
            
            assert limits.max_position_per_symbol == 2500.0
            assert limits.max_daily_loss == 1000.0
            assert limits.max_trades_per_minute == 2
            print("✓ Environment variable parsing works")
        finally:
            # Cleanup
            os.environ.pop('RISK_MAX_POSITION_PER_SYMBOL', None)
            os.environ.pop('RISK_MAX_DAILY_LOSS', None)
            os.environ.pop('RISK_MAX_TRADES_PER_MINUTE', None)
    
    def test_type_validation(self):
        """Test type validation"""
        # Should raise validation error for invalid types
        with pytest.raises(Exception):  # Pydantic validation error
            RiskLimits(max_position_per_symbol="invalid")
        
        print("✓ Type validation works")
    
    def test_required_fields(self):
        """Test required fields have defaults"""
        # All fields should have defaults, so empty constructor should work
        limits = RiskLimits()
        
        assert limits.max_position_per_symbol is not None
        assert limits.max_daily_loss is not None
        assert limits.max_trades_per_minute is not None
        
        print("✓ Required fields have defaults")






