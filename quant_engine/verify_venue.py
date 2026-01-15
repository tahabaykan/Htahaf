
from app.market_data.hammer_ingest_stub import HammerIngest
import logging

# Configure dummy logger
logging.basicConfig(level=logging.ERROR)

def dummy_feed():
    yield {} # Dummy to satisfy iterator type

def test_normalization():
    ingest = HammerIngest(dummy_feed())
    
    # Test case 1: 'e' field (from getTicks)
    tick1 = {
        "symbol": "HBANL",
        "last": 25.3947,
        "ts": "2025-10-23T17:55:55.094",
        "e": "FNRA"
    }
    norm1 = ingest._normalize_tick(tick1)
    print(f"Test 1 (e='FNRA'): {norm1}")
    assert norm1.get('exch') == 'FNRA', f"Failed to extract 'e' field. Got: {norm1}"

    # Test case 2: 'MMID' field (from L2)
    tick2 = {
        "symbol": "NFLX",
        "last": 100.0, 
        "MMID": "NYSE"
    }
    norm2 = ingest._normalize_tick(tick2)
    print(f"Test 2 (MMID='NYSE'): {norm2}")
    assert norm2.get('exch') == 'NYSE', f"Failed to extract 'MMID' field. Got: {norm2}"
    
    # Test case 3: 'venue' field (generic)
    tick3 = {
        "symbol": "AAPL",
        "last": 150.0,
        "venue": "ARCA"
    }
    norm3 = ingest._normalize_tick(tick3)
    print(f"Test 3 (venue='ARCA'): {norm3}")
    assert norm3.get('exch') == 'ARCA', f"Failed to extract 'venue' field. Got: {norm3}"

    print("\n✅ Verification SUCCESS: All venue fields extracted correctly.")

if __name__ == "__main__":
    test_normalization()
