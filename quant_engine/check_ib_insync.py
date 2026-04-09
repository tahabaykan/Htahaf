#!/usr/bin/env python3
"""Backend'in kullandığı Python'da ib_insync import kontrolü. quant_engine klasöründen: python check_ib_insync.py"""
import sys
print("Python:", sys.executable)
print("Version:", sys.version)
print()
try:
    from ib_insync import IB, Contract
    print("ib_insync import: OK")
except Exception as e:
    print("ib_insync import HATA:", type(e).__name__, str(e))
