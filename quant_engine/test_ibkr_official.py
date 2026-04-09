"""
IBKR Connection Test using OFFICIAL ibapi (not ib_insync)
"""
import sys
import time
import threading

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

class TestApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.connected = False
        self.accounts = []
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        print(f"Error: reqId={reqId}, code={errorCode}, msg={errorString}")
        
    def connectAck(self):
        print("✅ connectAck received!")
        self.connected = True
        
    def nextValidId(self, orderId):
        print(f"✅ nextValidId: {orderId}")
        self.connected = True
        
    def managedAccounts(self, accountsList):
        print(f"✅ Accounts: {accountsList}")
        self.accounts = accountsList.split(",")
        
    def connectionClosed(self):
        print("❌ Connection closed")
        self.connected = False

def main():
    print("=" * 60)
    print("IBKR Connection Test (Official ibapi)")
    print("=" * 60)
    
    app = TestApp()
    
    host = "127.0.0.1"
    port = 4001
    client_id = 995
    
    print(f"\nConnecting to {host}:{port} with clientId={client_id}...")
    
    try:
        app.connect(host, port, client_id)
        
        # Start message processing in background
        api_thread = threading.Thread(target=app.run, daemon=True)
        api_thread.start()
        
        # Wait for connection
        timeout = 15
        start = time.time()
        while not app.connected and time.time() - start < timeout:
            print(f"  Waiting... ({int(time.time() - start)}s)")
            time.sleep(1)
        
        if app.connected:
            print(f"\n✅ SUCCESS! Connected to IBKR Gateway")
            print(f"   Accounts: {app.accounts}")
            time.sleep(2)  # Let more messages come in
            app.disconnect()
            print("\n✅ IBKR API CONNECTION WORKS!")
        else:
            print(f"\n❌ Connection timeout after {timeout}s")
            print("   Socket connected but no handshake response from Gateway")
            
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
