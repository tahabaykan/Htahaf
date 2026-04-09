"""
Minimal Claude API Client — No Dependencies
=============================================
Uses Python's built-in urllib (no pip install needed).
Supports Claude Haiku 4.5 (cheapest) and Sonnet 4.6 (deep reasoning).

Tool calling: Sonnet DEEP mode can use tools to actively query
Redis/DataFabric for specific data it's curious about.
Max 5 tool iterations per call to control costs (~$0.10-0.15/day extra).

Pricing (per 1M tokens):
  Haiku 4.5:   $0.80 input / $4.00 output  → ~$0.25/day for monitoring
  Sonnet 4.6:  $3.00 input / $15.00 output  → ~$0.40/day for deep analysis
"""
import json
import logging
import asyncio
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Model options — updated Feb 2026
MODEL_HAIKU = "claude-haiku-4-5-20251001"      # Fast, cheap — scan mode
MODEL_SONNET = "claude-sonnet-4-6"             # Deep reasoning — learning mode

MAX_TOOL_ITERATIONS = 5  # Max tool call rounds per deep session


class ClaudeClient:
    """
    Minimal Claude API client using urllib.
    No external dependencies required.
    
    Two call modes:
    - analyze(): Simple prompt → text response (for Haiku SCAN)
    - analyze_with_tools(): Prompt + tools → iterative tool-use (for Sonnet DEEP)
    """

    def __init__(self, api_key: str, model: str = MODEL_HAIKU):
        self.api_key = api_key
        self.model = model
        self._daily_calls = 0
        self._daily_input_tokens = 0
        self._daily_output_tokens = 0
        self._daily_tool_calls = 0
        self._last_reset = datetime.now().date()

    def _reset_daily_if_needed(self):
        today = datetime.now().date()
        if today != self._last_reset:
            self._daily_calls = 0
            self._daily_input_tokens = 0
            self._daily_output_tokens = 0
            self._daily_tool_calls = 0
            self._last_reset = today

    def _api_call(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Low-level Claude API call. Returns full response dict.
        """
        self._reset_daily_if_needed()

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system_prompt:
            body["system"] = system_prompt
        
        if tools:
            body["tools"] = tools

        payload = json.dumps(body).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }

        req = Request(
            ANTHROPIC_API_URL,
            data=payload,
            headers=headers,
            method="POST",
        )

        with urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        # Track usage
        usage = result.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        self._daily_calls += 1
        self._daily_input_tokens += input_tokens
        self._daily_output_tokens += output_tokens

        # Cost calculation (Haiku 4.5 / Sonnet 4.6 pricing)
        if "haiku" in self.model:
            cost = (input_tokens * 0.80 + output_tokens * 4.00) / 1_000_000
        else:
            cost = (input_tokens * 3.00 + output_tokens * 15.00) / 1_000_000

        logger.info(
            f"[CLAUDE] Call #{self._daily_calls} | "
            f"{input_tokens} in / {output_tokens} out | "
            f"${cost:.4f} | model={self.model}"
        )

        return result

    def _sync_call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        Simple synchronous Claude API call (no tools).
        Returns the text response or an error string.
        Used by Haiku SCAN mode.
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            result = self._api_call(messages, system_prompt, temperature, max_tokens)

            # Extract text from response
            content = result.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")
            return text

        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error(f"[CLAUDE] HTTP {e.code}: {body[:1000]}")
            return f"[CLAUDE ERROR] HTTP {e.code}"
        except URLError as e:
            logger.error(f"[CLAUDE] URL Error: {e.reason}")
            return f"[CLAUDE ERROR] Connection failed"
        except Exception as e:
            logger.error(f"[CLAUDE] Unexpected error: {e}")
            return f"[CLAUDE ERROR] {e}"

    def _sync_call_with_tools(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
    ) -> str:
        """
        Synchronous Claude API call WITH tool support.
        Handles the tool_use → execute → tool_result loop.
        Max MAX_TOOL_ITERATIONS rounds to control costs.
        
        Used by Sonnet DEEP mode.
        """
        try:
            from app.agent.qagentt_tools import execute_tool
        except ImportError:
            logger.warning("[CLAUDE] qagentt_tools not available, falling back to simple call")
            return self._sync_call(prompt, system_prompt, temperature, max_tokens)

        try:
            messages = [{"role": "user", "content": prompt}]
            
            for iteration in range(MAX_TOOL_ITERATIONS):
                result = self._api_call(
                    messages, system_prompt, temperature, max_tokens, tools
                )
                
                stop_reason = result.get("stop_reason", "end_turn")
                content = result.get("content", [])
                
                if stop_reason != "tool_use":
                    # No more tool calls — extract final text
                    text = ""
                    for block in content:
                        if block.get("type") == "text":
                            text += block.get("text", "")
                    return text
                
                # Claude wants to use tools — process tool_use blocks
                # Add assistant's response (with tool_use blocks) to messages
                messages.append({"role": "assistant", "content": content})
                
                # Execute each tool and build tool_result blocks
                tool_results = []
                for block in content:
                    if block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})
                        tool_id = block.get("id", "")
                        
                        self._daily_tool_calls += 1
                        
                        logger.info(
                            f"[CLAUDE-TOOLS] 🔧 Iteration {iteration+1} | "
                            f"Tool: {tool_name} | Input: {json.dumps(tool_input, ensure_ascii=False)[:200]}"
                        )
                        
                        # Execute tool locally (Redis/DataFabric query — free!)
                        tool_result = execute_tool(tool_name, tool_input)
                        
                        # JSON-aware truncation to save tokens
                        if len(tool_result) > 4000:
                            try:
                                import json as _json
                                data = _json.loads(tool_result)
                                if isinstance(data, list) and len(data) > 10:
                                    data = data[:10]
                                    tool_result = _json.dumps(
                                        {"items": data, "_truncated": True, "_total": len(data)},
                                        ensure_ascii=False
                                    )
                                elif isinstance(data, dict):
                                    for k in list(data.keys()):
                                        if isinstance(data[k], str) and len(data[k]) > 500:
                                            data[k] = data[k][:500] + "..."
                                        elif isinstance(data[k], list) and len(data[k]) > 10:
                                            data[k] = data[k][:10]
                                    tool_result = _json.dumps(data, ensure_ascii=False)
                                if len(tool_result) > 4000:
                                    tool_result = tool_result[:3900] + "...(truncated)"
                            except Exception:
                                tool_result = tool_result[:3900] + "...(truncated)"
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": tool_result,
                        })
                
                # Send tool results back to Claude
                messages.append({"role": "user", "content": tool_results})
                
                logger.info(
                    f"[CLAUDE-TOOLS] Iteration {iteration+1}/{MAX_TOOL_ITERATIONS} | "
                    f"Executed {len(tool_results)} tools | "
                    f"Total tool calls today: {self._daily_tool_calls}"
                )
            
            # Max iterations reached — extract whatever text we have
            logger.warning(
                f"[CLAUDE-TOOLS] Max iterations ({MAX_TOOL_ITERATIONS}) reached"
            )
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")
            return text or "[CLAUDE] Max tool iterations reached"

        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error(f"[CLAUDE] HTTP {e.code}: {body[:1000]}")
            return f"[CLAUDE ERROR] HTTP {e.code}"
        except URLError as e:
            logger.error(f"[CLAUDE] URL Error: {e.reason}")
            return f"[CLAUDE ERROR] Connection failed"
        except Exception as e:
            logger.error(f"[CLAUDE] Unexpected error: {e}")
            return f"[CLAUDE ERROR] {e}"

    async def analyze(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Async wrapper around simple call (no tools). Used by Haiku SCAN."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._sync_call(prompt, system_prompt, temperature, max_tokens),
        )

    async def analyze_with_tools(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
    ) -> str:
        """
        Async wrapper around tool-calling call. Used by Sonnet DEEP.
        Claude can call tools to query Redis/DataFabric for specific data.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._sync_call_with_tools(
                prompt, system_prompt, temperature, max_tokens, tools
            ),
        )

    @property
    def stats(self) -> dict:
        self._reset_daily_if_needed()
        if "haiku" in self.model:
            cost = (self._daily_input_tokens * 0.80 + self._daily_output_tokens * 4.00) / 1_000_000
        else:
            cost = (self._daily_input_tokens * 3.00 + self._daily_output_tokens * 15.00) / 1_000_000
        return {
            "model": self.model,
            "daily_calls": self._daily_calls,
            "daily_tool_calls": self._daily_tool_calls,
            "daily_input_tokens": self._daily_input_tokens,
            "daily_output_tokens": self._daily_output_tokens,
            "daily_cost_usd": round(cost, 4),
        }

