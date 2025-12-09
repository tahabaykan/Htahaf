import csv
import os

CONID_CSV_PATH = os.path.join(os.path.dirname(__file__), "conids.csv")

def load_conids():
    symbol_to_conid = {}
    if os.path.exists(CONID_CSV_PATH):
        with open(CONID_CSV_PATH, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                symbol = row['symbol'].strip()
                conid = int(row['conid'])
                symbol_to_conid[symbol] = conid
    return symbol_to_conid

def save_conids(symbol_to_conid):
    with open(CONID_CSV_PATH, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['symbol', 'conid'])
        writer.writeheader()
        for symbol, conid in symbol_to_conid.items():
            writer.writerow({'symbol': symbol, 'conid': conid}) 
