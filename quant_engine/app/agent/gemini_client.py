"""
Gemini Flash Client — Zero-dependency REST API wrapper.

Uses Python stdlib (urllib) so no extra packages needed.
Async support via asyncio.run_in_executor.
"""

import json
import asyncio
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.logger import logger


GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)


class GeminiFlashClient:
    """
    Minimal Gemini 2.0 Flash client using REST API.
    
    Free tier limits (Google AI Studio):
    - 15 RPM (requests per minute)
    - 1,500 RPD (requests per day)  
    - 1,000,000 TPM (tokens per minute)
    
    Our usage: ~39 requests/day = 2.6% of limit.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._call_count = 0
        self._last_call_time: Optional[datetime] = None
        self._daily_calls = 0
        self._daily_reset_date: Optional[str] = None

    def _sync_call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1500,
    ) -> str:
        """
        Synchronous Gemini API call using stdlib urllib.
        
        Returns:
            Generated text response
        """
        url = f"{GEMINI_API_URL}?key={self.api_key}"

        # Build request payload
        contents = [{"parts": [{"text": prompt}]}]
        
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        
        # Add system instruction if provided
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        data = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            # Extract text from response
            candidates = result.get("candidates", [])
            if not candidates:
                logger.warning("[GEMINI] No candidates in response")
                return ""

            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)

            # Update stats
            self._call_count += 1
            self._last_call_time = datetime.now()
            today = datetime.now().strftime("%Y-%m-%d")
            if self._daily_reset_date != today:
                self._daily_calls = 0
                self._daily_reset_date = today
            self._daily_calls += 1

            # Log token usage if available
            usage = result.get("usageMetadata", {})
            prompt_tokens = usage.get("promptTokenCount", 0)
            output_tokens = usage.get("candidatesTokenCount", 0)
            logger.info(
                f"[GEMINI] Call #{self._daily_calls} today | "
                f"Tokens: {prompt_tokens} in / {output_tokens} out"
            )

            return text

        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error(f"[GEMINI] HTTP {e.code}: {body[:2000]}")
            return f"[GEMINI ERROR] HTTP {e.code}"
        except URLError as e:
            logger.error(f"[GEMINI] URL Error: {e.reason}")
            return f"[GEMINI ERROR] Connection failed"
        except Exception as e:
            logger.error(f"[GEMINI] Unexpected error: {e}")
            return f"[GEMINI ERROR] {e}"

    async def analyze(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1500,
    ) -> str:
        """
        Async Gemini API call (runs sync call in executor to avoid blocking).
        
        Args:
            prompt: Analysis prompt with metrics data
            system_prompt: System instruction for the model
            temperature: 0.0-1.0, lower = more deterministic
            max_tokens: Maximum output tokens
            
        Returns:
            Generated analysis text
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._sync_call(prompt, system_prompt, temperature, max_tokens),
        )

    @property
    def stats(self) -> Dict[str, Any]:
        """Get client usage stats."""
        return {
            "total_calls": self._call_count,
            "daily_calls": self._daily_calls,
            "daily_limit": 1500,
            "daily_usage_pct": round(self._daily_calls / 1500 * 100, 2),
            "last_call": self._last_call_time.isoformat() if self._last_call_time else None,
        }
