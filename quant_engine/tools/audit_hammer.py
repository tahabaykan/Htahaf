"""
Hammer Streamer Auditor
=======================

Audits all available streamers and their status.
"""
import sys
import os
import json
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.live.hammer_client import HammerClient
from app.config.settings import settings

def main():
    client = HammerClient(
        host=settings.HAMMER_HOST,
        port=settings.HAMMER_PORT,
        password=settings.HAMMER_PASSWORD,
        account_key=settings.HAMMER_ACCOUNT_KEY
    )
    
    if not client.connect():
        print("❌ Failed to connect")
        return

    print("✅ Authenticated")
    
    print("\n📋 Enumerating Data Streamers...")
    resp = client.send_command_and_wait({"cmd": "enumDataStreamers"}, timeout=5.0)
    if resp and resp.get('success') == 'OK':
        streamers = resp.get('result', [])
        for s in streamers:
            print(f"  - ID: {s.get('streamerID')}, Name: {s.get('name')}, isSet: {s.get('isSet')}")
    else:
        print(f"❌ Failed to enum streamers: {resp}")

    print("\n📋 Enumerating Trading Accounts...")
    resp = client.send_command_and_wait({"cmd": "enumTradingAccounts"}, timeout=5.0)
    if resp and resp.get('success') == 'OK':
        accounts = resp.get('result', {}).get('accounts', [])
        for a in accounts:
            print(f"  - Key: {a.get('accountKey')}, ID: {a.get('accountID')}, Nick: {a.get('accountNick')}")
    else:
        print(f"❌ Failed to enum accounts: {resp}")

    client.disconnect()
    print("\n👋 Done")

if __name__ == "__main__":
    main()
