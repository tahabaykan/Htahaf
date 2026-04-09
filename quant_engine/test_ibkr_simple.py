"""
Simple IBKR Connection Test - No complexity, just raw ib_insync
"""
import asyncio
import sys

# Windows fix for SelectorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from ib_insync import IB

async def test_connection():
    ib = IB()
    
    ports = [4001, 7497, 7496, 4002]
    hosts = ['127.0.0.1', 'localhost']
    
    for port in ports:
        for host in hosts:
            try:
                print(f"Trying {host}:{port}...")
                await ib.connectAsync(host, port, clientId=999, timeout=5)
                
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
    print("Simple IBKR Connection Test")
    print("=" * 60)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(test_connection())
        if result:
            print("\n✅ IBKR CONNECTION WORKS!")
        else:
            print("\n❌ All connection attempts failed")
            print("\nCheck:")
            print("  1. Is IBKR Gateway/TWS running?")
            print("  2. Is API enabled in Gateway settings?")
            print("  3. Is the correct port configured (4001 for Gateway, 7497 for TWS)?")
    finally:
        loop.close()

if __name__ == "__main__":
    main()
