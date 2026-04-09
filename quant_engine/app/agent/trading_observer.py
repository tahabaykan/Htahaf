"""
Trading Observer Agent — AI-powered trading system monitor.

Dual-provider: Gemini 2.0 Flash (primary, free) → Claude Haiku 3.5 (fallback, ~$1/month).
When Gemini quota runs out, auto-switches to Claude Haiku seamlessly.

Runs as a background asyncio task, collecting metrics every N minutes
and sending them to the active AI provider for analysis. Stores insights
in Redis for UI consumption and logs results.

Usage:
    from app.agent import start_trading_observer, stop_trading_observer
    
    # Start (usually called from startup or API)
    await start_trading_observer(api_key="AIza...")
    
    # Stop
    await stop_trading_observer()
    
    # Get latest insight
    from app.agent.trading_observer import get_trading_observer
    observer = get_trading_observer()
    latest = observer.latest_insight
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import deque

from app.core.logger import logger
from app.agent.gemini_client import GeminiFlashClient
from app.agent.metrics_collector import MetricsCollector
from app.agent.observer_prompts import SYSTEM_PROMPT, build_analysis_prompt


# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

DEFAULT_INTERVAL_SECONDS = 600    # 10 minutes
MAX_INSIGHT_HISTORY = 50          # Keep last 50 insights in memory
REDIS_INSIGHT_KEY = "psfalgo:agent:latest_insight"
REDIS_INSIGHTS_LIST_KEY = "psfalgo:agent:insights_history"
REDIS_ALERT_KEY = "psfalgo:agent:active_alert"
REDIS_API_KEY_KEY = "psfalgo:agent:gemini_api_key"
REDIS_CLAUDE_API_KEY_KEY = "psfalgo:agent:claude_api_key"
REDIS_INSIGHT_TTL = 86400         # 24 hours


class TradingObserverAgent:
    """
    AI-powered Trading Observer Agent with dual-provider fallback.
    
    Provider chain:
    1. Gemini 2.0 Flash (free tier — 1500 RPD)
    2. Claude Haiku 3.5 (fallback — ~$0.05/day)
    
    Runs as an independent background task:
    1. Collects metrics from Redis + in-memory services
    2. Sends structured metrics to active AI provider
    3. Parses response (JSON expected)
    4. Stores insights in Redis for UI
    5. Detects critical alerts
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        claude_api_key: Optional[str] = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ):
        # Primary: Gemini Flash
        self.gemini: Optional[GeminiFlashClient] = None
        if gemini_api_key:
            self.gemini = GeminiFlashClient(gemini_api_key)
        
        # Fallback: Claude Haiku
        self.claude = None
        if claude_api_key:
            try:
                from app.agent.claude_client import ClaudeClient, MODEL_HAIKU
                self.claude = ClaudeClient(api_key=claude_api_key, model=MODEL_HAIKU)
                logger.info("[OBSERVER] Claude Haiku fallback initialized")
            except Exception as e:
                logger.warning(f"[OBSERVER] Claude client import failed: {e}")
        
        self.collector = MetricsCollector()
        self.interval = interval_seconds
        
        # Active provider tracking
        self._active_provider = "gemini" if self.gemini else ("claude" if self.claude else "none")
        self._gemini_quota_exhausted = False
        self._gemini_quota_retry_at: Optional[datetime] = None

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._cycle_count = 0
        self._started_at: Optional[datetime] = None

        # History
        self._insights: deque = deque(maxlen=MAX_INSIGHT_HISTORY)
        self._previous_snapshot: Optional[Dict[str, Any]] = None
        self._latest_insight: Optional[Dict[str, Any]] = None
        self._active_alert: Optional[str] = None

        providers = []
        if self.gemini:
            providers.append("Gemini Flash")
        if self.claude:
            providers.append("Claude Haiku (fallback)")
        logger.info(f"[OBSERVER] TradingObserverAgent initialized — providers: {', '.join(providers) or 'NONE'}")

    # ═══════════════════════════════════════════════════════════════
    # Dual-Provider AI Call
    # ═══════════════════════════════════════════════════════════════

    async def _call_ai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1500,
    ) -> tuple[str, str]:
        """
        Call AI with automatic failover.
        
        Returns:
            (response_text, provider_name)
        """
        # Try Gemini first (if available and not quota-exhausted)
        if self.gemini and not self._gemini_quota_exhausted:
            try:
                result = await self.gemini.analyze(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                # Check for quota error in response
                if result and "[GEMINI ERROR]" in result:
                    if "429" in result or "503" in result or "RESOURCE_EXHAUSTED" in result:
                        logger.warning("[OBSERVER] 🔄 Gemini quota exhausted — switching to Claude Haiku")
                        self._gemini_quota_exhausted = True
                        self._gemini_quota_retry_at = datetime.now()
                        # Fall through to Claude
                    else:
                        # Other Gemini error, still try Claude
                        logger.warning(f"[OBSERVER] Gemini error: {result[:200]}")
                        # Fall through to Claude
                else:
                    self._active_provider = "gemini"
                    return result, "gemini"
            except Exception as e:
                logger.warning(f"[OBSERVER] Gemini call failed: {e}")
                # Fall through to Claude
        elif self._gemini_quota_exhausted:
            # Retry Gemini every 30 minutes to check if quota is refreshed
            if self._gemini_quota_retry_at:
                elapsed = (datetime.now() - self._gemini_quota_retry_at).total_seconds()
                if elapsed > 1800:  # 30 minutes
                    logger.info("[OBSERVER] 🔄 Retrying Gemini (30 min since quota exhaust)")
                    self._gemini_quota_exhausted = False
                    return await self._call_ai(prompt, system_prompt, temperature, max_tokens)
        
        # Fallback: Claude Haiku
        if self.claude:
            try:
                result = await self.claude.analyze(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if result and "[CLAUDE ERROR]" not in result:
                    self._active_provider = "claude"
                    return result, "claude"
                else:
                    logger.error(f"[OBSERVER] Claude also failed: {result[:200]}")
                    return result or "", "claude_error"
            except Exception as e:
                logger.error(f"[OBSERVER] Claude call failed: {e}")
                return f"[ERROR] Both providers failed: {e}", "error"
        
        return "[ERROR] No AI provider available", "none"

    # ═══════════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════════

    async def start(self) -> bool:
        """Start the observation loop as a background task."""
        if self._running:
            logger.warning("[OBSERVER] Already running")
            return False

        if not self.gemini and not self.claude:
            logger.error("[OBSERVER] No AI provider available — cannot start")
            return False

        self._running = True
        self._started_at = datetime.now()
        self._cycle_count = 0

        self._task = asyncio.create_task(
            self._observation_loop(),
            name="trading_observer_loop",
        )

        # Store API keys in Redis for persistence
        self._save_api_keys_to_redis()

        logger.info(
            f"[OBSERVER] 🚀 Started! Analyzing every {self.interval}s "
            f"({self.interval // 60} min) — active provider: {self._active_provider}"
        )
        return True

    async def stop(self) -> bool:
        """Stop the observation loop."""
        if not self._running:
            return False

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        logger.info(
            f"[OBSERVER] 🛑 Stopped after {self._cycle_count} cycles"
        )
        return True

    # ═══════════════════════════════════════════════════════════════
    # Main Loop
    # ═══════════════════════════════════════════════════════════════

    async def _observation_loop(self):
        """Main observation loop — runs until stopped."""
        logger.info("[OBSERVER] Observation loop started")

        # Run first analysis immediately
        await self._observe_and_analyze()

        while self._running:
            try:
                # Sleep for interval
                await asyncio.sleep(self.interval)

                if not self._running:
                    break

                # Run analysis
                await self._observe_and_analyze()

            except asyncio.CancelledError:
                logger.info("[OBSERVER] Loop cancelled")
                break
            except Exception as e:
                logger.error(f"[OBSERVER] Loop error: {e}", exc_info=True)
                await asyncio.sleep(30)  # Brief pause on error

    async def _observe_and_analyze(self):
        """
        Single observation cycle:
        1. Collect metrics → 2. Build prompt → 3. Call AI → 4. Store result
        """
        self._cycle_count += 1
        cycle_start = datetime.now()
        logger.info(f"[OBSERVER] ═══ Analysis #{self._cycle_count} starting ═══")

        try:
            # 1. Collect metrics
            snapshot = self.collector.collect_snapshot()
            logger.info(
                f"[OBSERVER] Metrics collected: "
                f"{len(snapshot.get('accounts', {}))} accounts, "
                f"{len(snapshot.get('anomalies_detected', []))} anomalies pre-detected"
            )

            # 2. Build analysis prompt
            prompt = build_analysis_prompt(
                current_snapshot=snapshot,
                previous_snapshot=self._previous_snapshot,
                cycle_number=self._cycle_count,
            )

            # 3. Call AI (Gemini → Claude fallback)
            raw_response, provider = await self._call_ai(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=1500,
            )

            # 4. Parse response
            insight = self._parse_insight(raw_response)
            insight["cycle"] = self._cycle_count
            insight["timestamp"] = cycle_start.isoformat()
            insight["analysis_duration_ms"] = int(
                (datetime.now() - cycle_start).total_seconds() * 1000
            )
            insight["provider"] = provider
            
            # Add provider-specific stats
            if provider == "gemini" and self.gemini:
                insight["ai_stats"] = self.gemini.stats
            elif provider == "claude" and self.claude:
                insight["ai_stats"] = self.claude.stats

            # 5. Store
            self._latest_insight = insight
            self._insights.append(insight)
            self._previous_snapshot = snapshot
            self._store_insight_to_redis(insight)

            # 6. Check for critical alerts
            self._handle_alert(insight)

            # 7. Log summary
            status = insight.get("durum", "UNKNOWN")
            score = insight.get("skor", "?")
            summary = insight.get("ozet", "")
            anomaly_count = len(insight.get("anomaliler", []))
            
            provider_tag = f"🤖 {provider.upper()}"
            logger.info(
                f"[OBSERVER] ═══ Analysis #{self._cycle_count} complete ═══\n"
                f"  Provider: {provider_tag}\n"
                f"  Durum: {status} | Skor: {score}/100\n"
                f"  Özet: {summary}\n"
                f"  Anomaliler: {anomaly_count} | "
                f"Süre: {insight['analysis_duration_ms']}ms"
            )

        except Exception as e:
            logger.error(
                f"[OBSERVER] Analysis #{self._cycle_count} failed: {e}",
                exc_info=True,
            )

    # ═══════════════════════════════════════════════════════════════
    # Response Parsing
    # ═══════════════════════════════════════════════════════════════

    def _parse_insight(self, raw_response: str) -> Dict[str, Any]:
        """
        Parse AI response into structured insight dict.
        
        Expects JSON wrapped in ```json``` code block.
        Falls back to raw text if parsing fails.
        """
        if not raw_response:
            return {"durum": "HATA", "skor": 0, "ozet": "AI yanıt vermedi", "raw": ""}

        # Try to extract JSON from code block
        text = raw_response.strip()
        
        # Remove ```json ... ``` wrapper
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        try:
            parsed = json.loads(text)
            # Validate expected fields
            return {
                "durum": parsed.get("durum", "UNKNOWN"),
                "skor": parsed.get("skor", 50),
                "ozet": parsed.get("ozet", ""),
                "gozlemler": parsed.get("gozlemler", []),
                "anomaliler": parsed.get("anomaliler", []),
                "oneriler": parsed.get("oneriler", []),
                "kritik_uyari": parsed.get("kritik_uyari"),
            }
        except (json.JSONDecodeError, ValueError):
            logger.warning("[OBSERVER] Failed to parse JSON response, using raw text")
            return {
                "durum": "UNKNOWN",
                "skor": 50,
                "ozet": text[:200],
                "gozlemler": [],
                "anomaliler": [],
                "oneriler": [],
                "kritik_uyari": None,
                "raw_text": text,
            }

    # ═══════════════════════════════════════════════════════════════
    # Alert Handling
    # ═══════════════════════════════════════════════════════════════

    def _handle_alert(self, insight: Dict[str, Any]):
        """Check for critical alerts and handle them."""
        critical = insight.get("kritik_uyari")
        durum = insight.get("durum", "").upper()

        if critical:
            self._active_alert = critical
            logger.warning(f"[OBSERVER] 🚨 KRİTİK UYARI: {critical}")
            self._store_alert_to_redis(critical)
        elif durum == "KRİTİK":
            self._active_alert = insight.get("ozet", "Kritik durum tespit edildi")
            logger.warning(f"[OBSERVER] 🚨 KRİTİK DURUM: {self._active_alert}")
            self._store_alert_to_redis(self._active_alert)
        else:
            if self._active_alert:
                logger.info("[OBSERVER] ✅ Önceki alert kaldırıldı — durum normale döndü")
            self._active_alert = None
            self._clear_alert_from_redis()

    # ═══════════════════════════════════════════════════════════════
    # Redis Storage
    # ═══════════════════════════════════════════════════════════════

    def _get_redis_sync(self):
        """Get Redis sync client."""
        try:
            from app.core.redis_client import get_redis_client
            client = get_redis_client()
            return getattr(client, "sync", client)
        except Exception:
            return None

    def _store_insight_to_redis(self, insight: Dict[str, Any]):
        """Store insight in Redis for UI consumption."""
        redis = self._get_redis_sync()
        if not redis:
            return

        try:
            data = json.dumps(insight, default=str, ensure_ascii=False)
            
            # Latest insight
            redis.set(REDIS_INSIGHT_KEY, data, ex=REDIS_INSIGHT_TTL)
            
            # History list (prepend, keep last 50)
            redis.lpush(REDIS_INSIGHTS_LIST_KEY, data)
            redis.ltrim(REDIS_INSIGHTS_LIST_KEY, 0, MAX_INSIGHT_HISTORY - 1)
            redis.expire(REDIS_INSIGHTS_LIST_KEY, REDIS_INSIGHT_TTL)

        except Exception as e:
            logger.warning(f"[OBSERVER] Redis store error: {e}")

    def _store_alert_to_redis(self, alert_text: str):
        """Store active alert in Redis."""
        redis = self._get_redis_sync()
        if not redis:
            return
        try:
            redis.set(REDIS_ALERT_KEY, alert_text, ex=3600)
        except Exception:
            pass

    def _clear_alert_from_redis(self):
        """Clear active alert from Redis."""
        redis = self._get_redis_sync()
        if not redis:
            return
        try:
            redis.delete(REDIS_ALERT_KEY)
        except Exception:
            pass

    def _save_api_keys_to_redis(self):
        """Save API keys to Redis for persistence across restarts."""
        redis = self._get_redis_sync()
        if not redis:
            return
        try:
            if self.gemini:
                redis.set(REDIS_API_KEY_KEY, self.gemini.api_key, ex=86400 * 30)
            if self.claude:
                redis.set(REDIS_CLAUDE_API_KEY_KEY, self.claude.api_key, ex=86400 * 30)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════
    # Public Properties
    # ═══════════════════════════════════════════════════════════════

    @property
    def latest_insight(self) -> Optional[Dict[str, Any]]:
        """Get the latest analysis insight."""
        return self._latest_insight

    @property
    def insights_history(self) -> List[Dict[str, Any]]:
        """Get insight history (most recent first)."""
        return list(self._insights)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> Dict[str, Any]:
        """Get current observer status."""
        ai_stats = {}
        if self._active_provider == "gemini" and self.gemini:
            ai_stats = self.gemini.stats
        elif self._active_provider == "claude" and self.claude:
            ai_stats = self.claude.stats
            
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "interval_seconds": self.interval,
            "active_alert": self._active_alert,
            "active_provider": self._active_provider,
            "gemini_quota_exhausted": self._gemini_quota_exhausted,
            "has_gemini": self.gemini is not None,
            "has_claude": self.claude is not None,
            "latest_durum": self._latest_insight.get("durum") if self._latest_insight else None,
            "latest_skor": self._latest_insight.get("skor") if self._latest_insight else None,
            "ai_stats": ai_stats,
        }


# ═══════════════════════════════════════════════════════════════
# Global Instance Management
# ═══════════════════════════════════════════════════════════════

_observer: Optional[TradingObserverAgent] = None


def get_trading_observer() -> Optional[TradingObserverAgent]:
    """Get the global trading observer instance."""
    return _observer


async def start_trading_observer(
    api_key: Optional[str] = None,
    claude_api_key: Optional[str] = None,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> TradingObserverAgent:
    """
    Start the global trading observer with dual-provider support.
    
    Args:
        api_key: Gemini API key. If None, tries Redis then env var.
        claude_api_key: Claude API key. If None, tries Redis then env var.
        interval_seconds: Analysis interval (default 600 = 10 min)
    
    Returns:
        TradingObserverAgent instance
    """
    global _observer

    # Stop existing observer if running
    if _observer and _observer.is_running:
        await _observer.stop()

    # Resolve Gemini API key
    if not api_key:
        api_key = _resolve_gemini_api_key()

    # Resolve Claude API key
    if not claude_api_key:
        claude_api_key = _resolve_claude_api_key()

    if not api_key and not claude_api_key:
        raise ValueError(
            "No AI provider API key found. Provide at least one of:\n"
            "  - Gemini: api_key param, GEMINI_API_KEY env var, or Redis psfalgo:agent:gemini_api_key\n"
            "  - Claude: claude_api_key param, ANTHROPIC_API_KEY env var, or Redis psfalgo:agent:claude_api_key"
        )

    _observer = TradingObserverAgent(
        gemini_api_key=api_key,
        claude_api_key=claude_api_key,
        interval_seconds=interval_seconds,
    )
    await _observer.start()
    return _observer


async def stop_trading_observer() -> bool:
    """Stop the global trading observer."""
    global _observer
    if _observer:
        return await _observer.stop()
    return False


def _resolve_gemini_api_key() -> Optional[str]:
    """Try to find Gemini API key from Redis, then env var."""
    # 1. Try Redis
    try:
        from app.core.redis_client import get_redis_client
        client = get_redis_client()
        redis_sync = getattr(client, "sync", client)
        key = redis_sync.get(REDIS_API_KEY_KEY)
        if key:
            logger.info("[OBSERVER] Gemini API key found in Redis")
            return key
    except Exception:
        pass

    # 2. Try env var
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        logger.info("[OBSERVER] Gemini API key found in GEMINI_API_KEY env var")
        return env_key

    return None


def _resolve_claude_api_key() -> Optional[str]:
    """Try to find Claude API key from Redis, then env var."""
    # 1. Try Redis
    try:
        from app.core.redis_client import get_redis_client
        client = get_redis_client()
        redis_sync = getattr(client, "sync", client)
        key = redis_sync.get(REDIS_CLAUDE_API_KEY_KEY)
        if key:
            logger.info("[OBSERVER] Claude API key found in Redis")
            return key
    except Exception:
        pass

    # 2. Try env var (standard Anthropic env var)
    env_key = os.getenv("ANTHROPIC_API_KEY")
    if env_key:
        logger.info("[OBSERVER] Claude API key found in ANTHROPIC_API_KEY env var")
        return env_key

    return None
