"""Test Claude API key and list available models."""
import os, sys, json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, r"C:\StockTracker\quant_engine")
with open(r"C:\StockTracker\quant_engine\.env", "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

api_key = os.getenv("ANTHROPIC_API_KEY", "")
out = open(r"C:\StockTracker\quant_engine\claude_test.txt", "w", encoding="utf-8")

# Try different model names
models_to_try = [
    "claude-3-5-haiku-20241022",
    "claude-3-haiku-20240307",
    "claude-3-5-sonnet-20241022",
    "claude-sonnet-4-20250514",
    "claude-3-5-haiku-latest",
    "claude-3-haiku-latest",
]

for model in models_to_try:
    body = {
        "model": model,
        "max_tokens": 50,
        "messages": [{"role": "user", "content": "Say hello"}],
    }
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    req = Request("https://api.anthropic.com/v1/messages", data=payload, headers=headers, method="POST")
    
    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = result.get("content", [{}])[0].get("text", "")
            usage = result.get("usage", {})
            out.write(f"✅ {model}: {text[:50]} (in={usage.get('input_tokens')}, out={usage.get('output_tokens')})\n")
            break  # First success is enough
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        out.write(f"❌ {model}: HTTP {e.code} — {body_text[:200]}\n")
    except Exception as e:
        out.write(f"❌ {model}: {e}\n")

out.close()
print("Done — see claude_test.txt")
