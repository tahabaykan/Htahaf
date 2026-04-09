"""Send existing analysis to Gemini with optimized prompt."""
import os, sys, json, asyncio
sys.path.insert(0, r"C:\StockTracker\quant_engine")

with open(r"C:\StockTracker\quant_engine\.env", "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

async def main():
    api_key = os.getenv("GEMINI_API_KEY", "")
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")

    # Load saved analysis
    data = json.load(open(r"C:\StockTracker\quant_engine\tt_training_result.json", encoding="utf-8"))
    raw = data["raw_analysis"]
    print(f"Symbols: {raw['total_symbols_analyzed']}, Groups: {raw['total_groups']}")

    # Build optimized prompt
    from app.agent.truth_tick_analyzer import build_analysis_prompt
    prompt = build_analysis_prompt(raw)
    print(f"Prompt: {len(prompt)} chars (~{len(prompt)//4} tokens)")

    # Save prompt for inspection
    with open(r"C:\StockTracker\quant_engine\gemini_prompt.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    # Send to Gemini
    print("Sending to Gemini 2.0 Flash...")
    from app.agent.gemini_client import GeminiFlashClient

    client = GeminiFlashClient(api_key)

    system_prompt = (
        "Sen QAGENTT — Preferred Stock Trading Learning Agent. "
        "Truth tick verilerini kullanarak mean reversion ve market making stratejileri gelistir. "
        "Sadece TRUTH TICK verileri gercek — diger tum printler gurultu. "
        "Volume hesaplamalari sadece truth tick size toplamindan. "
        "AVG_ADV ise janalldata.csv deki normal deger. "
        "Her zaman JSON formatinda cevap ver."
    )

    response = await client.analyze(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.35,
        max_tokens=8192,
    )

    print(f"Response: {len(response)} chars")

    # Save
    with open(r"C:\StockTracker\quant_engine\gemini_report.txt", "w", encoding="utf-8") as f:
        f.write(response)

    data["gemini_interpretation"] = response
    data["prompt_length"] = len(prompt)
    with open(r"C:\StockTracker\quant_engine\tt_training_result.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    print("Saved to gemini_report.txt")
    print(f"\n{'='*80}")
    print(response[:5000])

asyncio.run(main())
