"""
Simple IBKR Connection Test - Proper event loop setup
"""
import sys
import asyncio

def main():
    print("=" * 60)
    print("Simple IBKR Connection Test (Proper Setup)")
    print("=" * 60)
    
    # Windows fix - must be done BEFORE any asyncio operations
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Create event loop FIRST
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Now import ib_insync AFTER loop is set
    from ib_insync import IB
    
    ib = IB()
    
    ports = [4001, 7497, 7496, 4002]
    host = '127.0.0.1'
    
    for port in ports:
        try:
            print(f"Trying {host}:{port}...")
            ib.connect(host, port, clientId=997, timeout=10)
            
            if ib.isConnected():
                print(f"✅ SUCCESS! Connected to {host}:{port}")
                
                # Get some basic info
                accounts = ib.managedAccounts()
                print(f"   Accounts: {accounts}")
                
                positions = ib.positions()
                print(f"   Positions: {len(positions)}")
                
                ib.disconnect()
                print("\n✅ IBKR CONNECTION WORKS!")
                return
                
        except Exception as e:
            print(f"❌ Failed {host}:{port}: {type(e).__name__}: {e}")
            try:
                ib.disconnect()
            except:
                pass
    
    print("\n❌ All connection attempts failed")
    print("\nPlease check:")
    print("  1. IBKR Gateway API settings: Enable ActiveX and Socket Clients")
    print("  2. Socket port: Should be 4001 for Gateway")
    print("  3. Trusted IPs: Add 127.0.0.1")

if __name__ == "__main__":
    main()
