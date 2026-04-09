import json

with open(r'c:\StockTracker\quant_engine\befday\befibped_20260218.json', 'r') as f:
    data = json.load(f)

print(f"Capture date: {data.get('capture_date')}")
print(f"Capture time: {data.get('capture_time')}")
print(f"Position count: {data.get('position_count')}")

syms = ['VNO PRO','ACGLO','VNO PRL','GS PRA','MS PRP','FHN PRE','JAGX']
for p in data['positions']:
    if p.get('Symbol') in syms:
        print(f"  {p['Symbol']:14s}  qty={p['Quantity']}")

# Check for VNO PRO specifically
found_vno = [p for p in data['positions'] if 'VNO' in p.get('Symbol', '')]
print("\nAll VNO entries:")
for p in found_vno:
    print(f"  {p['Symbol']:14s}  qty={p['Quantity']}")
