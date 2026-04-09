import json

data = json.load(open(r"C:\StockTracker\quant_engine\tt_training_result.json", encoding="utf-8"))
gemini = data.get("gemini_interpretation", "")
if gemini:
    with open(r"C:\StockTracker\quant_engine\gemini_report.txt", "w", encoding="utf-8") as f:
        f.write(gemini)
    print(f"Report saved: {len(gemini)} chars")
else:
    print("No gemini report")
