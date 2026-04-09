"""
IBKR Connection Test with Debug Logging and timeout=0
"""
import sys
import asyncio
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('ib_insync').setLevel(logging.DEBUG)

def main():
    print("=" * 60)
    print("IBKR Connection Test (DEBUG MODE)")
    print("=" * 60)
    
    # Windows fix
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Create event loop FIRST
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Now import ib_insync AFTER loop is set
    from ib_insync import IB
    import ib_insync
    print(f"ib_insync version: {ib_insync.__version__}")
    
    ib = IB()
    
    # Try with timeout=0 (infinite) or very long timeout
    ports = [4001]
    host = '127.0.0.1'
    
    for port in ports:
        try:
            print(f"\nTrying {host}:{port} with timeout=0 (infinite)...")
            ib.connect(host, port, clientId=996, timeout=0)
            
            if ib.isConnected():
                print(f"✅ SUCCESS! Connected to {host}:{port}")
                accounts = ib.managedAccounts()
                print(f"   Accounts: {accounts}")
                ib.disconnect()
                return
                
        except Exception as e:
            print(f"❌ Failed {host}:{port}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            try:
                ib.disconnect()
            except:
                pass
    
    print("\n❌ Connection failed")

if __name__ == "__main__":
    main()
