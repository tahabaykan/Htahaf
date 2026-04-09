"""
Minimal IBKR connection test - timeout=0 (infinite wait)
"""
import asyncio
import sys

# Windows fix
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Create loop BEFORE importing ib_insync
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from ib_insync import IB

print("Connecting to IBKR Gateway (timeout=0 means infinite wait)...")
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=999, timeout=0)
print("CONNECTED:", ib.client.serverVersion())
ib.disconnect()
print("DISCONNECTED OK")
