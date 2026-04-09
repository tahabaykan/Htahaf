"""Clean analysis — redirect to file"""
import csv, os, sys
from collections import Counter, defaultdict

BASE = "data/logs/daily_fills"

# Redirect stdout to file to prevent garbling
with open("_fill_report.txt", "w") as out:
    def p(s=""):
        out.write(s + "\n")
    
    for date_suffix in ["260224", "260225"]:
        p(f"\n{'='*60}")
        p(f"DATE: {date_suffix}")
        p(f"{'='*60}")
        
        ham_file = os.path.join(BASE, f"hamfilledorders{date_suffix}.csv")
        ped_file = os.path.join(BASE, f"ibpedfilledorders{date_suffix}.csv")
        
        ham_syms = set()
        ped_syms = set()
        
        for label, fp, sym_set in [("HAMPRO", ham_file, ham_syms), ("IBKR_PED", ped_file, ped_syms)]:
            if not os.path.exists(fp):
                p(f"  {label}: FILE NOT FOUND ({fp})")
                continue
            
            rows = list(csv.DictReader(open(fp, 'r', encoding='utf-8', errors='replace')))
            size = os.path.getsize(fp)
            
            # Header check
            with open(fp, 'r') as f:
                header = f.readline().strip()
            
            strats = Counter()
            hours_dist = Counter()
            zero_time = 0
            
            for r in rows:
                sym_set.add(r.get("Symbol", ""))
                strats[r.get("Strategy", "?")] += 1
                t = r.get("Time", "")
                if t == "00:00:00":
                    zero_time += 1
                if t and ":" in t:
                    hours_dist[t.split(":")[0]] += 1
            
            p(f"\n  {label}:")
            p(f"    File: {fp} ({size} bytes)")
            p(f"    Header: {header[:100]}")
            p(f"    Total rows: {len(rows)}")
            p(f"    Unique symbols: {len(sym_set)}")
            p(f"    Fills with Time=00:00:00: {zero_time}")
            p(f"    Strategies: {strats.most_common(10)}")
            p(f"    Hour distribution: {dict(sorted(hours_dist.items()))}")
            
            # Show all fills if small count
            if len(rows) <= 5:
                p(f"    ALL FILLS:")
                for r in rows:
                    p(f"      {r}")
        
        # Cross-compare
        if ham_syms and ped_syms:
            both = ham_syms & ped_syms
            only_ham = sorted(ham_syms - ped_syms)
            only_ped = sorted(ped_syms - ham_syms)
            p(f"\n  COMPARISON:")
            p(f"    Symbols in BOTH accounts: {len(both)} -> {sorted(both)}")
            p(f"    ONLY in HAM ({len(only_ham)}): {only_ham[:20]}")
            p(f"    ONLY in PED ({len(only_ped)}): {only_ped[:20]}")

    # Check how daily_fills_store gets account type
    p(f"\n{'='*60}")
    p("HOW _get_filename WORKS")
    p(f"{'='*60}")
    
    # Read the function
    store_file = os.path.join("app", "trading", "daily_fills_store.py")
    if os.path.exists(store_file):
        with open(store_file, 'r') as f:
            content = f.read()
        # Find _get_filename function
        start = content.find("def _get_filename")
        if start >= 0:
            end = content.find("\n    def ", start + 10)
            if end < 0:
                end = start + 500
            p(content[start:end])

print("Report written to _fill_report.txt")
