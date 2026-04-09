"""
Simple IBKR Connection Test - SYNC version (no async)
"""
import sys
import time

# Windows fix
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from ib_insync import IB

def test_connection():
    ib = IB()
    
    ports = [4001, 7497, 7496, 4002]
    host = '127.0.0.1'
    
    for port in ports:
        try:
            print(f"Trying {host}:{port} (SYNC)...")
            ib.connect(host, port, clientId=998, timeout=10)
            
            if ib.isConnected():
                print(f"✅ SUCCESS! Connected to {host}:{port}")
                
                # Get some basic info
                accounts = ib.managedAccounts()
                print(f"   Accounts: {accounts}")
                
                positions = ib.positions()
                print(f"   Positions: {len(positions)}")
                
                ib.disconnect()
                return True
                
        except Exception as e:
            print(f"❌ Failed {host}:{port}: {e}")
            try:
                ib.disconnect()
            except:
                pass
    
    return False

def main():
    print("=" * 60)
    print("Simple IBKR Connection Test (SYNC)")
    print("=" * 60)
    
    result = test_connection()
    if result:
        print("\n✅ IBKR CONNECTION WORKS!")
    else:
        print("\n❌ All connection attempts failed")

if __name__ == "__main__":
    main()
