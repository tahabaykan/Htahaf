"""Capture full Gemini 429 error body to file."""
import os, sys, json
sys.path.insert(0, r"C:\StockTracker\quant_engine")

with open(r"C:\StockTracker\quant_engine\.env", "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from urllib.request import Request, urlopen
from urllib.error import HTTPError

api_key = os.getenv("GEMINI_API_KEY", "")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

payload = json.dumps({
    "contents": [{"parts": [{"text": "Say hello"}]}],
    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 50},
}).encode("utf-8")

req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

out = open(r"C:\StockTracker\quant_engine\gemini_error.txt", "w", encoding="utf-8")
try:
    with urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        out.write(f"SUCCESS: {text}\n")
except HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    out.write(f"HTTP {e.code}\n")
    out.write(body)
except Exception as e:
    out.write(f"Error: {e}\n")
out.close()
print("Saved to gemini_error.txt")
