
import requests
import json
import sys

try:
    response = requests.get('http://localhost:8000/api/psfalgo/proposals/latest?limit=1')
    data = response.json()
    
    if not data.get('success'):
        print(f"API Error: {data}")
        sys.exit(1)
        
    proposals = data.get('proposals', [])
    if not proposals:
        print("No proposals found.")
    else:
        p = proposals[0]
        print(f"Proposal ID: {p.get('id')}")
        print(f"Engine Key Exists: {'engine' in p}")
        print(f"Engine Value: '{p.get('engine')}'")
        print(f"Book: {p.get('book')}")
        print(f"All Keys: {list(p.keys())}")

except Exception as e:
    print(f"Script Error: {e}")
