import json, os

f = r"C:\StockTracker\quant_engine\tt_training_result.json"
if os.path.exists(f):
    data = json.load(open(f, encoding="utf-8"))
    raw = data.get("raw_analysis", {})
    print("Result file exists")
    print("Symbols:", raw.get("total_symbols_analyzed", 0))
    print("Groups:", raw.get("total_groups", 0))
    print("Has Gemini:", "yes" if data.get("gemini_interpretation") else "no")
    print("Prompt length:", data.get("prompt_length", 0))
else:
    print("No result file")
