"""
PreferredStockLearningAgent — Main Engine
==========================================

Gün boyu preferred stock piyasasını izleyen, öğrenen ve raporlayan agent.

SMART HYBRID v2:
  - Haiku SCAN (every 5min): Hızlı tarama, anomali tespiti
  - Sonnet DEEP (on anomaly): Derin analiz, strateji önerisi
  - ORTAK HAFIZA: Her iki model de aynı Redis memory'yi kullanır

Legacy (v1): Gemini Flash (free) → Claude Haiku fallback.

Kullanım:
    from app.agent.learning_agent import start_learning_agent, stop_learning_agent

    # Başlat (v2 Smart Hybrid)
    agent = await start_learning_agent(claude_api_key="sk-...", mode="v2", auto_start=True)

    # Direktif ver
    await agent.add_directive("Bugün NLY-PD'ye dikkat et, ex-div yaklaşıyor")

    # Son analizi oku
    insight = agent.latest_insight

    # Durdur
    await stop_learning_agent()
"""

import os
import json
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.core.logger import logger
from app.agent.gemini_client import GeminiFlashClient
from app.agent.metrics_collector import MetricsCollector
from app.agent.learning_agent_brain import (
    LEARNING_AGENT_SYSTEM_PROMPT,
    QUICK_CHECK_PROMPT,
    TREND_ANALYSIS_PROMPT,
    DEEP_ANALYSIS_PROMPT,
    DIRECTIVE_CONTEXT_PROMPT,
    REDIS_KEYS,
    REDIS_TTL,
    INTERVALS,
    TOKEN_LIMITS,
    # v2 Smart Hybrid
    SMART_HYBRID_CONFIG,
    SCAN_MODE_PROMPT,
    DEEP_MODE_PROMPT,
    EVOLUTION_PROMPT,
)



class PreferredStockLearningAgent:
    """
    Preferred Stock piyasasını gün boyu izleyip öğrenen AI agent.

    Üç frekansta analiz yapar:
    1. Quick Check (5 dk)   — anomali taraması
    2. Trend Analysis (30 dk) — grup trendleri
    3. Deep Analysis (2 saat) — derin strateji düşüncesi

    Kesinlikle işlem AÇMAZ. Sadece izler, öğrenir, raporlar.
    """

    def __init__(
        self,
        api_key: str,
        claude_api_key: Optional[str] = None,
        quick_interval: int = INTERVALS["quick_check"],
        trend_interval: int = INTERVALS["trend_analysis"],
        deep_interval: int = INTERVALS["deep_analysis"],
        mode: str = "v1",  # "v1" (legacy) or "v2" (smart hybrid)
    ):
        self.api_key = api_key
        self.gemini = GeminiFlashClient(api_key)
        self.collector = MetricsCollector()
        self._mode = mode

        # Claude clients
        self.claude = None           # Legacy v1 fallback (Haiku)
        self._claude_haiku = None    # v2 SCAN model
        self._claude_sonnet = None   # v2 DEEP model
        self._active_provider = "gemini"
        self._gemini_quota_exhausted = False
        self._gemini_quota_retry_at: Optional[datetime] = None

        # Resolve Claude key
        ck = claude_api_key or _resolve_claude_key()

        if ck:
            try:
                from app.agent.claude_client import ClaudeClient, MODEL_HAIKU, MODEL_SONNET
                self.claude = ClaudeClient(api_key=ck, model=MODEL_HAIKU)
                logger.info("[QAGENTT] 🤖 Claude Haiku fallback initialized")

                if mode == "v2":
                    self._claude_haiku = ClaudeClient(api_key=ck, model=MODEL_HAIKU)
                    self._claude_sonnet = ClaudeClient(api_key=ck, model=MODEL_SONNET)
                    logger.info("[QAGENTT] 🧠 Smart Hybrid v2: Haiku SCAN + Sonnet DEEP initialized")
            except Exception as e:
                logger.warning(f"[QAGENTT] Claude init failed: {e}")

        # Intervals
        self.quick_interval = quick_interval
        self.trend_interval = trend_interval
        self.deep_interval = deep_interval

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._cycle_count = 0
        self._quick_count = 0
        self._trend_count = 0
        self._deep_count = 0
        self._tt_analysis_count = 0
        self._start_time: Optional[datetime] = None

        # v2 Smart Hybrid state
        self._scan_count = 0
        self._deep_v2_count = 0
        self._last_scan_result: Optional[Dict[str, Any]] = None
        self._daily_deep_calls = 0
        self._last_deep_reset_date = datetime.now().date()

        # De-escalation state — prevents repeated identical deep analyses
        self._consecutive_zero_pattern_deeps = 0  # How many deeps in a row found 0 patterns
        self._last_escalation_reason_hash = ""     # Hash of last escalation reason
        self._deescalation_cooldown_until = 0.0    # time.time() when cooldown expires
        self._DEESCALATION_THRESHOLD = 3           # After N identical zero-pattern deeps, enter cooldown
        self._DEESCALATION_COOLDOWN_SECS = 3600    # 1 hour cooldown before allowing anomaly-escalated deeps again

        # In-memory buffers
        self._latest_insight: Optional[Dict[str, Any]] = None
        self._insights_history: List[Dict[str, Any]] = []
        self._snapshot_buffer: List[Dict[str, Any]] = []  # Son 72 snapshot
        self._learned_patterns: List[str] = []
        self._directives: List[str] = []

        # Timing
        self._last_quick_time = 0.0
        self._last_trend_time = 0.0
        self._last_deep_time = 0.0
        self._last_tt_analysis: Optional[Dict[str, Any]] = None

        provider_info = f"v2 Smart Hybrid (Haiku+Sonnet)" if mode == "v2" and self._claude_haiku else (
            f"gemini + claude" if self.claude else "gemini only"
        )
        logger.info(f"[QAGENTT] 🧠 Learning Agent initialized [{provider_info}] mode={mode}")

    # ═══════════════════════════════════════════════════════════
    # LIFECYCLE
    # ═══════════════════════════════════════════════════════════

    async def start(self):
        """Start the learning observation loop."""
        if self._running:
            logger.warning("[QAGENTT] Already running")
            return

        self._running = True
        self._start_time = datetime.now()

        # Load persisted state from Redis
        await self._load_state_from_redis()
        
        # Restore knowledge from disk if Redis was empty (restart protection)
        if self._mode == "v2":
            await self._restore_knowledge_from_disk()

        # Store API key in Redis for persistence
        await self._save_to_redis(REDIS_KEYS["status"], "running")

        if self._mode == "v2" and self._claude_haiku:
            self._task = asyncio.create_task(self._smart_hybrid_loop())
            logger.info("[QAGENTT] 🚀 Smart Hybrid v2 started — Haiku SCAN + Sonnet DEEP!")
        else:
            self._task = asyncio.create_task(self._observation_loop())
            logger.info("[QAGENTT] 🚀 Learning Agent v1 started — izle, öğren, raporla!")

    async def stop(self):
        """Stop the learning loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Persist state
        await self._save_daily_summary()
        await self._save_to_redis(REDIS_KEYS["status"], "stopped")
        
        # Backup knowledge to disk before shutdown
        if self._mode == "v2":
            await self._backup_knowledge_to_disk()

        if self._mode == "v2":
            haiku_stats = self._claude_haiku.stats if self._claude_haiku else {}
            sonnet_stats = self._claude_sonnet.stats if self._claude_sonnet else {}
            logger.info(
                f"[QAGENTT] 🛑 Smart Hybrid v2 stopped | "
                f"Scans: {self._scan_count} | Deeps: {self._deep_v2_count} | "
                f"Haiku: ${haiku_stats.get('daily_cost_usd', 0):.2f} | "
                f"Sonnet: ${sonnet_stats.get('daily_cost_usd', 0):.2f}"
            )
        else:
            logger.info(
                f"[QAGENTT] 🛑 Learning Agent v1 stopped | "
                f"Cycles: {self._cycle_count} | "
                f"Quick: {self._quick_count} | Trend: {self._trend_count} | "
                f"Deep: {self._deep_count}"
            )

    # ═══════════════════════════════════════════════════════════
    # v2 SMART HYBRID LOOP
    # ═══════════════════════════════════════════════════════════

    async def _smart_hybrid_loop(self):
        """
        Smart Hybrid v2 observation loop.
        
        Every 5 minutes:
        1. Collect full payload (150 tickers + ETF + positions + orders + fills)
        2. Run Haiku SCAN (quick anomaly detection)
        3. IF anomaly_score >= threshold OR Haiku says escalate → Run Sonnet DEEP
        4. Every 2 hours: Scheduled Sonnet DEEP (sürekli öğrenme, anomali olmasa bile)
        5. Store insights in shared memory (Redis)
        """
        scan_interval = SMART_HYBRID_CONFIG["scan_interval"]  # 300s = 5min
        deep_threshold = SMART_HYBRID_CONFIG["deep_threshold"]  # 3
        max_deep_per_day = SMART_HYBRID_CONFIG["max_deep_per_day"]  # 50
        scheduled_deep_interval = SMART_HYBRID_CONFIG.get("scheduled_deep_interval", 7200)  # 2h
        
        logger.info(
            f"[QAGENTT-v2] Smart Hybrid loop started | "
            f"Scan: {scan_interval}s | Deep threshold: {deep_threshold} | "
            f"Scheduled deep: every {scheduled_deep_interval}s | "
            f"Max deep/day: {max_deep_per_day}"
        )

        last_scheduled_deep = time.time()  # First scheduled deep after 2h

        while self._running:
            try:
                self._cycle_count += 1
                now = time.time()
                
                # Reset daily deep counter
                today = datetime.now().date()
                if today != self._last_deep_reset_date:
                    self._daily_deep_calls = 0
                    self._last_deep_reset_date = today
                
                # ── Step 1: Check market hours ──
                # US market: 9:30 AM - 4:00 PM ET
                # Off-hours: scan every 30min (not 5min), block Sonnet DEEP
                from datetime import timezone
                et_offset = timedelta(hours=-5)  # EST (simplified, no DST handling)
                now_utc = datetime.now(timezone.utc)
                now_et = now_utc + et_offset
                et_hour = now_et.hour
                is_market_hours = 8 <= et_hour < 17  # 8 AM - 5 PM ET
                is_weekday = now_et.weekday() < 5  # Mon-Fri
                off_hours = not (is_market_hours and is_weekday)
                
                # ── Step 2: Collect full payload ──
                payload = self.collector.collect_qagentt_payload()
                payload["cycle"] = self._cycle_count
                
                ticker_count = len(payload.get("tickers", []))
                anomaly_score = payload.get("anomaly_score", 0)
                
                logger.info(
                    f"[QAGENTT-v2] Cycle #{self._cycle_count} | "
                    f"Tickers: {ticker_count} | Anomaly: {anomaly_score}/10 | "
                    f"Deeps today: {self._daily_deep_calls}/{max_deep_per_day}"
                )
                
                # ── Step 2: Haiku SCAN ──
                scan_result = await self._run_scan_mode(payload)
                
                # ── Step 3: Check if Sonnet DEEP needed ──
                should_escalate = False
                escalation_reason = ""
                
                # 3a: Anomaly score check
                if anomaly_score >= deep_threshold:
                    should_escalate = True
                    escalation_reason = f"Anomaly score {anomaly_score} >= {deep_threshold}"
                
                # 3b: Haiku flagged escalation
                is_haiku_escalation = False
                if scan_result and isinstance(scan_result, dict):
                    if scan_result.get("escalate_to_deep", False):
                        should_escalate = True
                        is_haiku_escalation = True
                        escalation_reason = scan_result.get(
                            "escalation_reason", "Haiku flagged escalation"
                        )
                
                # 3c: Scheduled deep (every 2 hours — continuous learning)
                is_scheduled_deep = False
                time_since_last_scheduled = now - last_scheduled_deep
                if time_since_last_scheduled >= scheduled_deep_interval and not should_escalate:
                    should_escalate = True
                    is_scheduled_deep = True
                    escalation_reason = (
                        f"Scheduled — sürekli öğrenme ({int(time_since_last_scheduled/60)}dk'dır deep yok)"
                    )
                
                # ── DE-ESCALATION CHECK ──
                # If we've had N consecutive deep analyses with 0 new patterns
                # and the same reason keeps repeating, enter cooldown.
                # Scheduled deeps (every 2hr) are ALWAYS allowed — cooldown only blocks
                # anomaly-triggered escalations.
                in_cooldown = now < self._deescalation_cooldown_until
                if in_cooldown and is_haiku_escalation and not is_scheduled_deep:
                    remaining_min = int((self._deescalation_cooldown_until - now) / 60)
                    logger.info(
                        f"[QAGENTT-v2] 🧊 De-escalation cooldown active — "
                        f"skipping Haiku escalation ({remaining_min}dk kaldı) | "
                        f"Reason would be: {escalation_reason[:100]}"
                    )
                    should_escalate = False
                
                # ── Step 4: Sonnet DEEP (if needed & budget allows) ──
                # Off-hours: skip DEEP (save $0.37/call), only Haiku scans
                if off_hours and should_escalate:
                    logger.info(
                        f"[QAGENTT-v2] 🌙 Off-hours — DEEP skipped (ET: {now_et.strftime('%H:%M')}) | "
                        f"Reason would be: {escalation_reason}"
                    )
                elif should_escalate and self._daily_deep_calls < max_deep_per_day:
                    logger.info(
                        f"[QAGENTT-v2] 🟡 Escalating to Sonnet DEEP | "
                        f"Reason: {escalation_reason} | "
                        f"Deep calls today: {self._daily_deep_calls}/{max_deep_per_day}"
                    )
                    patterns_before = len(self._learned_patterns)
                    await self._run_deep_mode(payload, scan_result, escalation_reason)
                    patterns_after = len(self._learned_patterns)
                    last_scheduled_deep = now  # Reset scheduled timer after any deep
                    
                    # ── Update de-escalation state ──
                    new_patterns_found = patterns_after - patterns_before
                    reason_hash = escalation_reason[:50]  # Rough similarity check
                    
                    if new_patterns_found == 0 and not is_scheduled_deep:
                        # Check if same type of reason is repeating
                        if reason_hash == self._last_escalation_reason_hash:
                            self._consecutive_zero_pattern_deeps += 1
                        else:
                            self._consecutive_zero_pattern_deeps = 1
                        self._last_escalation_reason_hash = reason_hash
                        
                        if self._consecutive_zero_pattern_deeps >= self._DEESCALATION_THRESHOLD:
                            self._deescalation_cooldown_until = now + self._DEESCALATION_COOLDOWN_SECS
                            logger.warning(
                                f"[QAGENTT-v2] 🧊 DE-ESCALATION: {self._consecutive_zero_pattern_deeps} "
                                f"consecutive zero-pattern deeps with same reason. "
                                f"Cooldown for {self._DEESCALATION_COOLDOWN_SECS//60}min. "
                                f"Scheduled deeps still allowed."
                            )
                    else:
                        # Found new patterns — reset de-escalation
                        self._consecutive_zero_pattern_deeps = 0
                        self._last_escalation_reason_hash = ""
                        if in_cooldown:
                            self._deescalation_cooldown_until = 0.0
                            logger.info("[QAGENTT-v2] ✅ De-escalation cooldown cleared — new patterns found")
                elif should_escalate:
                    logger.warning(
                        f"[QAGENTT-v2] ⚠️ Would escalate but daily limit reached "
                        f"({self._daily_deep_calls}/{max_deep_per_day})"
                    )
                
                # ── Step 5: Save snapshot to history ──
                self._snapshot_buffer.append({
                    "ts": payload.get("ts"),
                    "cycle": self._cycle_count,
                    "anomaly_score": anomaly_score,
                    "ticker_count": ticker_count,
                    "scan_status": scan_result.get("status", "?") if isinstance(scan_result, dict) else "?",
                    "escalated": should_escalate,
                })
                if len(self._snapshot_buffer) > 72:
                    self._snapshot_buffer = self._snapshot_buffer[-72:]
                
                # Log cost summary every 12 cycles (1 hour)
                if self._cycle_count % 12 == 0:
                    await self._log_cost_summary()
                
                # Weekly evolution (öz-değerlendirme) every ~2016 cycles (≈1 week at 5min)
                if self._cycle_count > 0 and self._cycle_count % 2016 == 0:
                    try:
                        await self._run_weekly_evolution()
                    except Exception as e:
                        logger.error(f"[QAGENTT-v2] Weekly evolution error: {e}")
                
                # Sleep until next scan (30min off-hours, 5min market hours)
                sleep_time = 1800 if off_hours else scan_interval
                if off_hours and self._cycle_count % 6 == 1:
                    logger.info(
                        f"[QAGENTT-v2] 🌙 Off-hours mode (ET: {now_et.strftime('%H:%M')}) | "
                        f"Next scan in {sleep_time//60}min"
                    )
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[QAGENTT-v2] Loop error: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _run_scan_mode(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Run Haiku SCAN mode — quick anomaly detection every 5 minutes.
        Returns parsed scan result dict (or None on error).
        """
        self._scan_count += 1
        
        if not self._claude_haiku:
            logger.warning("[QAGENTT-v2] No Haiku client configured")
            return None
        
        # Build prompt
        previous_scan = json.dumps(
            self._last_scan_result, ensure_ascii=False, default=str
        ) if self._last_scan_result else "İlk scan — önceki bulgu yok."
        
        prompt = SCAN_MODE_PROMPT.format(
            payload=json.dumps(payload, ensure_ascii=False, default=str),
            previous_scan=previous_scan,
        )
        
        try:
            response = await self._claude_haiku.analyze(
                prompt=prompt,
                system_prompt=LEARNING_AGENT_SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=1500,
            )
            
            if response and "[CLAUDE ERROR]" not in response:
                parsed = self._try_parse_json(response)
                
                if isinstance(parsed, dict):
                    self._last_scan_result = parsed
                    
                    status = parsed.get("status", "?")
                    flags = parsed.get("anomaly_flags", [])
                    dikkat = parsed.get("dikkat_cekici", [])
                    
                    insight = {
                        "type": "scan_v2",
                        "cycle": self._cycle_count,
                        "scan_number": self._scan_count,
                        "timestamp": datetime.now().isoformat(),
                        "status": status,
                        "anomaly_flags": flags,
                        "dikkat_cekici": dikkat[:5],
                        "provider": "haiku",
                        "raw_response": response[:500],
                    }
                    self._store_insight(insight)
                    
                    # Save to Redis shared memory
                    await self._save_to_redis(
                        "qagentt:v2:last_scan",
                        json.dumps(parsed, ensure_ascii=False, default=str),
                        ttl=600,  # 10 min TTL
                    )
                    
                    logger.info(
                        f"[QAGENTT-v2] 🔵 Scan #{self._scan_count} → {status} | "
                        f"Flags: {flags} | "
                        f"Haiku: ${self._claude_haiku.stats.get('daily_cost_usd', 0):.3f}"
                    )
                    
                    return parsed
                else:
                    # Response wasn't valid JSON, store raw
                    self._last_scan_result = {"status": "RAW", "raw": response[:300]}
                    return self._last_scan_result
            else:
                logger.error(f"[QAGENTT-v2] Haiku scan error: {response[:200] if response else 'empty'}")
                return None
                
        except Exception as e:
            logger.error(f"[QAGENTT-v2] Scan error: {e}")
            return None

    async def _run_deep_mode(
        self,
        payload: Dict[str, Any],
        scan_result: Optional[Dict[str, Any]],
        escalation_reason: str,
    ):
        """
        Run Sonnet DEEP mode — strategic analysis with TOOL CALLING.
        
        Sonnet can now actively query Redis/DataFabric to investigate
        anything it's curious about:
        - Symbol details, truth tick history, group dynamics
        - Positions, orders, fills, exposure
        - ETF data, QeBench performance
        - Search by criteria (find cheap/expensive stocks)
        
        Tool calling is limited to MAX_TOOL_ITERATIONS (5) per session.
        Cost impact: ~$0.10-0.15/day extra.
        """
        self._deep_v2_count += 1
        self._daily_deep_calls += 1
        
        if not self._claude_sonnet:
            logger.warning("[QAGENTT-v2] No Sonnet client configured")
            return
        
        # Use the payload passed from the hybrid loop (already collected)
        # Only add cycle number
        payload["cycle"] = self._cycle_count
        
        # ── Compile evolving memory ──
        flat_patterns = "\n".join(self._learned_patterns[-30:]) if self._learned_patterns else "Henüz pattern yok."
        
        # Load evolving knowledge from Redis
        evolving_sections = []
        for key_name in ("symbol_knowledge", "metric_impacts", "etf_correlations",
                         "fill_quality", "recommendations", "weekly_evolution",
                         "system_health", "loss_analysis"):
            redis_key = REDIS_KEYS.get(key_name)
            if redis_key:
                stored = await self._load_from_redis(redis_key)
                if stored:
                    evolving_sections.append(f"[{key_name}]\n{stored[:2000]}")
        
        memory = flat_patterns
        if evolving_sections:
            memory += "\n\n═══ BİRİKMİŞ BİLGİ TABANI ═══\n" + "\n\n".join(evolving_sections)
        
        directives = "\n".join(self._directives) if self._directives else "Aktif direktif yok."
        
        scan_result_str = json.dumps(
            scan_result, ensure_ascii=False, default=str
        ) if scan_result else "Scan sonucu yok."
        
        # ── Build DEEP prompt with tool-calling instructions ──
        tool_instructions = """

═══ AKTİF ARAŞTIRMA YETENEĞİN ═══

Sen artık pasif bir gözlemci değilsin. Elinde araştırma araçları var.
Merak ettiğin herhangi bir veriyi sorgulayabilirsin:

ARAÇLARIN:
1. get_symbol_detail(symbol) → Tek hissenin TÜM metrikleri
2. get_truth_tick_history(symbol, last_n) → Truth tick geçmişi + volav analizi
3. get_group_analysis(group_name) → Grup üyeleri ve istatistikleri
4. get_positions(account_id) → Pozisyonlar
5. get_open_orders(account_id) → Açık emirler
6. get_fills_today(symbol, account_id) → Bugünkü fill'ler
7. get_exposure_status() → Exposure durumu
8. get_etf_data() → ETF fiyatları ve değişimleri
9. get_qebench_performance(account_id) → QeBench performansı
10. compare_symbols(symbols) → Sembolleri karşılaştır
11. search_by_criteria(group, gort_min/max, ...) → Kritere göre hisse ara

KURALLAR:
- Scan sonucunda dikkat çeken şeyleri DERINLEMESINE ARAŞTIR
- Her anomaliyi sorguyla — "Neden böyle?" diye araştır
- Grup arkadaşlarını karşılaştır — outlier bul
- Fill kalitesini kontrol et — motor iyi mi çalışıyor?
- Cevabını VERİYE DAYANDIRMALI olarak ver
- Max 3-5 araç çağrısı yap (maliyet kontrolü)
"""
        
        prompt = DEEP_MODE_PROMPT.format(
            payload=json.dumps(payload, ensure_ascii=False, default=str),
            scan_result=scan_result_str,
            memory=memory,
            directives=directives,
            escalation_reason=escalation_reason,
        ) + tool_instructions
        
        try:
            # Import tool schemas
            from app.agent.qagentt_tools import TOOL_SCHEMAS
            
            response = await self._claude_sonnet.analyze_with_tools(
                prompt=prompt,
                system_prompt=LEARNING_AGENT_SYSTEM_PROMPT,
                temperature=0.4,
                max_tokens=4000,
                tools=TOOL_SCHEMAS,
            )
            
            if response and "[CLAUDE ERROR]" not in response:
                parsed = self._try_parse_json(response)
                
                insight = {
                    "type": "deep_v2",
                    "cycle": self._cycle_count,
                    "deep_number": self._deep_v2_count,
                    "timestamp": datetime.now().isoformat(),
                    "escalation_reason": escalation_reason,
                    "parsed": parsed,
                    "raw_response": response[:1500],
                    "provider": "sonnet",
                    "tool_calls": self._claude_sonnet.stats.get("daily_tool_calls", 0),
                }
                
                # ── Extract & persist evolving knowledge ──
                if isinstance(parsed, dict):
                    await self._persist_evolving_knowledge(parsed)
                
                self._store_insight(insight)
                
                # Save deep result to Redis
                await self._save_to_redis(
                    "qagentt:v2:last_deep",
                    json.dumps({
                        "timestamp": datetime.now().isoformat(),
                        "escalation_reason": escalation_reason,
                        "result": parsed,
                    }, ensure_ascii=False, default=str),
                    ttl=7200,  # 2 hour TTL
                )
                
                logger.info(
                    f"[QAGENTT-v2] 🟡 Deep #{self._deep_v2_count} complete | "
                    f"Reason: {escalation_reason} | "
                    f"Patterns: {len(self._learned_patterns)} | "
                    f"Tools used: {self._claude_sonnet.stats.get('daily_tool_calls', 0)} | "
                    f"Sonnet: ${self._claude_sonnet.stats.get('daily_cost_usd', 0):.3f}"
                )
            else:
                logger.error(f"[QAGENTT-v2] Sonnet deep error: {response[:200] if response else 'empty'}")
                
        except Exception as e:
            logger.error(f"[QAGENTT-v2] Deep analysis error: {e}", exc_info=True)

    async def _persist_evolving_knowledge(self, parsed: Dict[str, Any]):
        """
        Persist structured knowledge from deep analysis to Redis.
        Model-agnostic: ANY model's output can be stored and read by ANY other model.
        Knowledge accumulates over days/weeks, building deep understanding.
        """
        ts = datetime.now().isoformat()
        
        # 1. LEARNINGS — structured (yeni/dogrulanan/duzeltme)
        ogrendiklerim = parsed.get("ogrendiklerim", {})
        new_pattern_count = 0
        
        if isinstance(ogrendiklerim, dict):
            # v2 structured format
            for learning in ogrendiklerim.get("yeni", []):
                if learning and learning not in self._learned_patterns:
                    self._learned_patterns.append(learning)
                    new_pattern_count += 1
                    logger.info(f"[QAGENTT-v2] 🎓 Yeni: {learning}")
            
            for confirmed in ogrendiklerim.get("dogrulanan", []):
                logger.info(f"[QAGENTT-v2] ✅ Doğrulandı: {confirmed}")
            
            for correction in ogrendiklerim.get("duzeltme", []):
                logger.info(f"[QAGENTT-v2] 🔄 Düzeltme: {correction}")
                
        elif isinstance(ogrendiklerim, list):
            # v1 flat format (backward compat)
            for learning in ogrendiklerim:
                if learning and learning not in self._learned_patterns:
                    self._learned_patterns.append(learning)
                    new_pattern_count += 1
                    logger.info(f"[QAGENTT-v2] 🎓 Yeni: {learning}")
        
        if new_pattern_count > 0:
            # Cap at 200 patterns (FIFO — oldest patterns dropped)
            if len(self._learned_patterns) > 200:
                dropped = len(self._learned_patterns) - 200
                self._learned_patterns = self._learned_patterns[-200:]
                logger.info(f"[QAGENTT-v2] 🗑️ Patterns capped: dropped {dropped} oldest")
            
            await self._save_to_redis(
                REDIS_KEYS["learned_patterns"],
                json.dumps(self._learned_patterns, ensure_ascii=False),
                ttl=REDIS_TTL["learned_patterns"],
            )
        
        # 2. SYMBOL KNOWLEDGE — per-symbol insights accumulate
        symbol_bilgi = parsed.get("symbol_bilgi", {})
        if symbol_bilgi and isinstance(symbol_bilgi, dict):
            existing = await self._load_json_from_redis(REDIS_KEYS["symbol_knowledge"]) or {}
            for symbol, info in symbol_bilgi.items():
                if symbol not in existing:
                    existing[symbol] = {"history": []}
                existing[symbol]["latest"] = info
                existing[symbol]["updated"] = ts
                # Keep last 10 insights per symbol
                history = existing[symbol].get("history", [])
                history.append({"ts": ts, **info})
                existing[symbol]["history"] = history[-10:]
            
            await self._save_to_redis(
                REDIS_KEYS["symbol_knowledge"],
                json.dumps(existing, ensure_ascii=False, default=str),
                ttl=REDIS_TTL["symbol_knowledge"],
            )
            logger.info(f"[QAGENTT-v2] 📚 Symbol bilgi güncellendi: {list(symbol_bilgi.keys())}")
        
        # 3. METRIC IMPACTS — accumulative learning about metrics
        metrik_etkileri = parsed.get("metrik_etkileri", {})
        if metrik_etkileri and isinstance(metrik_etkileri, dict):
            existing = await self._load_json_from_redis(REDIS_KEYS["metric_impacts"]) or {}
            for metric, impact in metrik_etkileri.items():
                if metric not in existing:
                    existing[metric] = {"observations": []}
                existing[metric]["latest"] = impact
                existing[metric]["updated"] = ts
                existing[metric]["observations"].append({"ts": ts, "v": impact})
                existing[metric]["observations"] = existing[metric]["observations"][-20:]
            
            await self._save_to_redis(
                REDIS_KEYS["metric_impacts"],
                json.dumps(existing, ensure_ascii=False, default=str),
                ttl=REDIS_TTL["metric_impacts"],  # 0 = SONSUZ
            )
        
        # 4. STRATEGY RECOMMENDATIONS — with confidence
        strat_recs = parsed.get("strateji_onerileri", [])
        if strat_recs and isinstance(strat_recs, list):
            existing = await self._load_json_from_redis(REDIS_KEYS["recommendations"]) or []
            for rec in strat_recs:
                if isinstance(rec, dict):
                    rec["ts"] = ts
                    existing.append(rec)
            existing = existing[-50:]  # Keep last 50 recommendations
            
            await self._save_to_redis(
                REDIS_KEYS["recommendations"],
                json.dumps(existing, ensure_ascii=False, default=str),
                ttl=REDIS_TTL["recommendations"],
            )
        
        # 5. FILL QUALITY — track fill analysis
        fill_analiz = parsed.get("fill_analiz", {})
        if fill_analiz and isinstance(fill_analiz, dict):
            existing = await self._load_json_from_redis(REDIS_KEYS["fill_quality"]) or {"history": []}
            existing["latest"] = fill_analiz
            existing["updated"] = ts
            existing["history"].append({"ts": ts, **fill_analiz})
            existing["history"] = existing["history"][-30:]
            
            await self._save_to_redis(
                REDIS_KEYS["fill_quality"],
                json.dumps(existing, ensure_ascii=False, default=str),
                ttl=REDIS_TTL["fill_quality"],
            )
        
        # 6. ETF CORRELATIONS
        etf_analiz = parsed.get("etf_analiz", {})
        if etf_analiz and isinstance(etf_analiz, dict):
            existing = await self._load_json_from_redis(REDIS_KEYS["etf_correlations"]) or {"history": []}
            existing["latest"] = etf_analiz
            existing["updated"] = ts
            existing["history"].append({"ts": ts, **etf_analiz})
            existing["history"] = existing["history"][-30:]
            
            await self._save_to_redis(
                REDIS_KEYS["etf_correlations"],
                json.dumps(existing, ensure_ascii=False, default=str),
                ttl=REDIS_TTL["etf_correlations"],
            )
        
        # 7. SYSTEM HEALTH — track system issues over time
        sistem_sagligi = parsed.get("sistem_sagligi", {})
        if sistem_sagligi and isinstance(sistem_sagligi, dict):
            existing = await self._load_json_from_redis("qagentt:v2:system_health") or {"history": []}
            existing["latest"] = sistem_sagligi
            existing["updated"] = ts
            existing["history"].append({"ts": ts, **sistem_sagligi})
            existing["history"] = existing["history"][-50:]  # Keep last 50
            
            await self._save_to_redis(
                "qagentt:v2:system_health",
                json.dumps(existing, ensure_ascii=False, default=str),
                ttl=604800,  # 7 days
            )
            
            # Log system issues prominently
            genel = sistem_sagligi.get("genel", "")
            sorunlar = sistem_sagligi.get("sorunlar", [])
            if genel in ("DİKKAT", "SORUNLU") or sorunlar:
                logger.warning(
                    f"[QAGENTT-v2] ⚠️ SİSTEM SAĞLIĞI: {genel} | "
                    f"Sorunlar: {sorunlar}"
                )
        
        # 8. LOSS ANALYSIS — track losses and weak points
        zarar_analizi = parsed.get("zarar_analizi", {})
        if zarar_analizi and isinstance(zarar_analizi, dict):
            existing = await self._load_json_from_redis("qagentt:v2:loss_analysis") or {"history": []}
            existing["latest"] = zarar_analizi
            existing["updated"] = ts
            existing["history"].append({"ts": ts, **zarar_analizi})
            existing["history"] = existing["history"][-30:]
            
            await self._save_to_redis(
                "qagentt:v2:loss_analysis",
                json.dumps(existing, ensure_ascii=False, default=str),
                ttl=604800,  # 7 days
            )

    async def _load_from_redis(self, key: str) -> Optional[str]:
        """Load a string value from Redis (async)."""
        try:
            from app.core.redis_client import redis_client
            r = await redis_client.async_client()
            if r:
                val = await r.get(key)
                if val:
                    return val if isinstance(val, str) else val.decode("utf-8")
        except Exception:
            pass
        return None

    async def _load_json_from_redis(self, key: str) -> Optional[Any]:
        """Load and parse JSON from Redis."""
        raw = await self._load_from_redis(key)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    async def _log_cost_summary(self):
        """Log hourly cost summary."""
        haiku_cost = self._claude_haiku.stats.get("daily_cost_usd", 0) if self._claude_haiku else 0
        sonnet_cost = self._claude_sonnet.stats.get("daily_cost_usd", 0) if self._claude_sonnet else 0
        total = haiku_cost + sonnet_cost
        
        logger.info(
            f"[QAGENTT-v2] 💰 Cost report | "
            f"Haiku: ${haiku_cost:.3f} ({self._scan_count} scans) | "
            f"Sonnet: ${sonnet_cost:.3f} ({self._deep_v2_count} deeps) | "
            f"Total: ${total:.3f}/day | "
            f"Patterns: {len(self._learned_patterns)}"
        )
        
        # Daily disk backup (every 12 hours = every 144 cycles)
        if self._cycle_count % 144 == 0:
            await self._backup_knowledge_to_disk()

    # ═══════════════════════════════════════════════════════════
    # WEEKLY EVOLUTION — Haftalık Öz-Değerlendirme
    # ═══════════════════════════════════════════════════════════

    async def _run_weekly_evolution(self):
        """
        Run weekly self-evaluation using Sonnet.
        Consolidates learnings, validates patterns, prunes wrong knowledge.
        Called every ~2016 cycles (≈1 week at 5min intervals).
        Cost: ~$0.50/call → ~$2/month.
        """
        logger.info("[QAGENTT-v2] 🏆 Starting weekly evolution...")
        
        if not self._claude_sonnet:
            logger.warning("[QAGENTT-v2] No Sonnet client for weekly evolution")
            return
        
        # Gather weekly stats
        accumulated_knowledge = ""
        for key_name in ("symbol_knowledge", "metric_impacts", "etf_correlations",
                         "fill_quality", "recommendations"):
            redis_key = REDIS_KEYS.get(key_name)
            if redis_key:
                stored = await self._load_from_redis(redis_key)
                if stored:
                    accumulated_knowledge += f"\n[{key_name}]\n{stored[:3000]}"
        
        weekly_learnings = "\n".join(self._learned_patterns[-50:]) if self._learned_patterns else "Henüz pattern yok."
        
        prompt = EVOLUTION_PROMPT.format(
            total_scans=self._scan_count,
            total_deeps=self._deep_v2_count,
            total_learnings=len(self._learned_patterns),
            outperform_pct="N/A",  # TODO: compute from fill_quality data
            weekly_learnings=weekly_learnings,
            accumulated_knowledge=accumulated_knowledge[:5000],
            recommendations_and_outcomes="Otomatik takip henüz aktif değil.",
        )
        
        try:
            response = await self._claude_sonnet.analyze(
                prompt=prompt,
                system_prompt=LEARNING_AGENT_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=3000,
            )
            
            if response and "[CLAUDE ERROR]" not in response:
                parsed = self._try_parse_json(response)
                
                # Store weekly evolution in Redis
                await self._save_to_redis(
                    REDIS_KEYS.get("weekly_evolution", "qagentt:v2:weekly_evolution"),
                    json.dumps({
                        "timestamp": datetime.now().isoformat(),
                        "cycle": self._cycle_count,
                        "result": parsed if parsed else response[:2000],
                    }, ensure_ascii=False, default=str),
                    ttl=0,  # Never expire
                )
                
                # Backup knowledge after evolution
                await self._backup_knowledge_to_disk()
                
                logger.info(
                    f"[QAGENTT-v2] 🏆 Weekly evolution complete | "
                    f"Patterns: {len(self._learned_patterns)} | "
                    f"Scans: {self._scan_count} | Deeps: {self._deep_v2_count}"
                )
            else:
                logger.error(f"[QAGENTT-v2] Weekly evolution failed: {response[:200] if response else 'empty'}")
                
        except Exception as e:
            logger.error(f"[QAGENTT-v2] Weekly evolution error: {e}", exc_info=True)

    # ═══════════════════════════════════════════════════════════
    # KNOWLEDGE PERSISTENCE — Disk Backup (Redis restart koruması)
    # ═══════════════════════════════════════════════════════════

    KNOWLEDGE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "qagentt_knowledge"
    )

    async def _backup_knowledge_to_disk(self):
        """
        Dump all evolving knowledge from Redis to disk.
        Called twice daily + on stop. Protects against Redis restart.
        
        Storage: ~2 MB/day → ~1.5 GB over 2 years.
        """
        try:
            os.makedirs(self.KNOWLEDGE_DIR, exist_ok=True)
            
            knowledge = {}
            evolving_keys = [
                "learned_patterns", "symbol_knowledge", "metric_impacts",
                "etf_correlations", "fill_quality", "recommendations",
                "weekly_evolution", "group_dynamics",
            ]
            
            for key_name in evolving_keys:
                redis_key = REDIS_KEYS.get(key_name)
                if redis_key:
                    raw = await self._load_from_redis(redis_key)
                    if raw:
                        try:
                            knowledge[key_name] = json.loads(raw)
                        except (json.JSONDecodeError, ValueError):
                            knowledge[key_name] = raw
            
            if not knowledge:
                return
            
            # Save timestamped backup
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            backup_file = os.path.join(self.KNOWLEDGE_DIR, f"knowledge_{ts}.json")
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump({
                    "backup_time": datetime.now().isoformat(),
                    "cycle": self._cycle_count,
                    "scan_count": self._scan_count,
                    "deep_count": self._deep_v2_count,
                    "pattern_count": len(self._learned_patterns),
                    "knowledge": knowledge,
                }, f, ensure_ascii=False, indent=2, default=str)
            
            # Also save as "latest" for easy restore
            latest_file = os.path.join(self.KNOWLEDGE_DIR, "knowledge_latest.json")
            with open(latest_file, "w", encoding="utf-8") as f:
                json.dump({
                    "backup_time": datetime.now().isoformat(),
                    "knowledge": knowledge,
                }, f, ensure_ascii=False, indent=2, default=str)
            
            # Cleanup old backups (keep last 60 = 30 days)
            self._cleanup_old_backups(keep=60)
            
            size_kb = os.path.getsize(backup_file) / 1024
            logger.info(
                f"[QAGENTT-v2] 💾 Knowledge backup: {backup_file} "
                f"({size_kb:.1f} KB, {len(knowledge)} keys)"
            )
            
        except Exception as e:
            logger.error(f"[QAGENTT-v2] Backup failed: {e}")

    def _cleanup_old_backups(self, keep: int = 60):
        """Keep only the N most recent backup files."""
        try:
            files = sorted([
                f for f in os.listdir(self.KNOWLEDGE_DIR)
                if f.startswith("knowledge_") and f != "knowledge_latest.json"
            ])
            if len(files) > keep:
                for old in files[:-keep]:
                    os.remove(os.path.join(self.KNOWLEDGE_DIR, old))
        except Exception:
            pass

    async def _restore_knowledge_from_disk(self):
        """
        Restore knowledge from disk backup if Redis is empty.
        Called on startup. Enables seamless recovery after Redis restart.
        """
        latest_file = os.path.join(self.KNOWLEDGE_DIR, "knowledge_latest.json")
        if not os.path.exists(latest_file):
            return
        
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                backup = json.load(f)
            
            knowledge = backup.get("knowledge", {})
            restored_count = 0
            
            for key_name, data in knowledge.items():
                redis_key = REDIS_KEYS.get(key_name)
                if not redis_key:
                    continue
                
                # Only restore if Redis is empty for this key
                existing = await self._load_from_redis(redis_key)
                if existing:
                    continue  # Redis already has data, don't overwrite
                
                ttl = REDIS_TTL.get(key_name, 86400)
                value = json.dumps(data, ensure_ascii=False, default=str)
                await self._save_to_redis(redis_key, value, ttl=ttl)
                restored_count += 1
            
            if restored_count > 0:
                # Also restore learned_patterns to memory
                patterns_data = knowledge.get("learned_patterns")
                if patterns_data and isinstance(patterns_data, list):
                    self._learned_patterns = patterns_data
                
                backup_time = backup.get("backup_time", "?")
                logger.info(
                    f"[QAGENTT-v2] 🔄 Knowledge restored from disk backup "
                    f"({restored_count} keys, backup from {backup_time})"
                )
            
        except Exception as e:
            logger.error(f"[QAGENTT-v2] Restore from disk failed: {e}")

    # ═══════════════════════════════════════════════════════════
    # v1 LEGACY MAIN LOOP
    # ═══════════════════════════════════════════════════════════

    async def _observation_loop(self):
        """Multi-frequency observation loop (v1 legacy)."""
        logger.info("[QAGENTT] Observation loop started (v1)")

        while self._running:
            try:
                now = time.time()
                self._cycle_count += 1

                # Collect snapshot
                snapshot = self.collector.collect_snapshot()
                snapshot["cycle"] = self._cycle_count
                snapshot["agent_time"] = datetime.now().isoformat()

                # Buffer snapshot
                self._snapshot_buffer.append(snapshot)
                if len(self._snapshot_buffer) > 72:
                    self._snapshot_buffer = self._snapshot_buffer[-72:]

                # Determine analysis type based on intervals
                analysis_done = False

                # Deep Analysis (every 2 hours)
                if now - self._last_deep_time >= self.deep_interval:
                    await self._run_deep_analysis(snapshot)
                    self._last_deep_time = now
                    analysis_done = True

                # Trend Analysis (every 30 minutes)
                elif now - self._last_trend_time >= self.trend_interval:
                    await self._run_trend_analysis(snapshot)
                    self._last_trend_time = now
                    analysis_done = True

                # Quick Check (every 5 minutes)
                elif now - self._last_quick_time >= self.quick_interval:
                    await self._run_quick_check(snapshot)
                    self._last_quick_time = now
                    analysis_done = True

                if analysis_done:
                    # Store snapshot
                    await self._save_to_redis(
                        REDIS_KEYS["snapshot_history"],
                        json.dumps(self._snapshot_buffer[-12:], default=str),
                        ttl=REDIS_TTL["snapshot_history"],
                    )

                # Sleep until next check (minimum interval is quick_check)
                await asyncio.sleep(min(60, self.quick_interval))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[QAGENTT] Observation error: {e}", exc_info=True)
                await asyncio.sleep(30)

    # ═══════════════════════════════════════════════════════════
    # AI CALL — Gemini → Claude Haiku fallback
    # ═══════════════════════════════════════════════════════════

    async def _call_ai(self, prompt: str, system_prompt: str,
                       temperature: float = 0.3, max_tokens: int = 1500) -> tuple:
        """
        Call AI with Gemini → Claude fallback.
        Returns (response_text, provider_name).
        """
        # Try Gemini first (if not quota-exhausted)
        if self.gemini and not self._gemini_quota_exhausted:
            try:
                result = await self.gemini.analyze(
                    prompt=prompt, system_prompt=system_prompt,
                    temperature=temperature, max_tokens=max_tokens,
                )
                if result and "[GEMINI ERROR]" in result:
                    if "429" in result or "503" in result or "RESOURCE_EXHAUSTED" in result:
                        logger.warning("[QAGENTT] 🔄 Gemini quota exhausted — switching to Claude Haiku")
                        self._gemini_quota_exhausted = True
                        self._gemini_quota_retry_at = datetime.now()
                    else:
                        logger.warning(f"[QAGENTT] Gemini error: {result[:200]}")
                else:
                    self._active_provider = "gemini"
                    return result, "gemini"
            except Exception as e:
                logger.warning(f"[QAGENTT] Gemini call failed: {e}")
        elif self._gemini_quota_exhausted and self._gemini_quota_retry_at:
            # Retry Gemini every 30 minutes
            elapsed = (datetime.now() - self._gemini_quota_retry_at).total_seconds()
            if elapsed > 1800:
                logger.info("[QAGENTT] 🔄 Retrying Gemini (30 min since quota exhaust)")
                self._gemini_quota_exhausted = False
                return await self._call_ai(prompt, system_prompt, temperature, max_tokens)

        # Fallback: Claude Haiku
        if self.claude:
            try:
                result = await self.claude.analyze(
                    prompt=prompt, system_prompt=system_prompt,
                    temperature=temperature, max_tokens=max_tokens,
                )
                if result and "[CLAUDE ERROR]" not in result:
                    self._active_provider = "claude"
                    return result, "claude"
                else:
                    logger.error(f"[QAGENTT] Claude also failed: {result[:200] if result else 'empty'}")
                    return result or "", "claude_error"
            except Exception as e:
                logger.error(f"[QAGENTT] Claude call failed: {e}")
                return f"[ERROR] Both providers failed: {e}", "error"

        return "[ERROR] No AI provider available", "none"

    # ═══════════════════════════════════════════════════════════
    # ANALYSIS METHODS
    # ═══════════════════════════════════════════════════════════

    async def _run_quick_check(self, snapshot: Dict[str, Any]):
        """5-minute quick anomaly scan."""
        self._quick_count += 1

        prompt = QUICK_CHECK_PROMPT.format(
            snapshot=json.dumps(snapshot, indent=2, default=str, ensure_ascii=False)
        )

        response, provider = await self._call_ai(
            prompt=prompt,
            system_prompt=LEARNING_AGENT_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=TOKEN_LIMITS["quick_check"],
        )

        insight = {
            "type": "quick_check",
            "cycle": self._cycle_count,
            "quick_number": self._quick_count,
            "timestamp": datetime.now().isoformat(),
            "raw_response": response,
            "parsed": self._try_parse_json(response),
            "provider": provider,
        }

        self._store_insight(insight)
        logger.info(
            f"[QAGENTT] ⚡ Quick Check #{self._quick_count} | "
            f"Provider: {provider} | "
            f"Gemini: {self.gemini.stats['daily_calls']}/1500 calls today"
        )

    async def _run_trend_analysis(self, snapshot: Dict[str, Any]):
        """30-minute trend analysis."""
        self._trend_count += 1

        # Get snapshot from 30 minutes ago
        previous = self._get_snapshot_ago(minutes=30)

        prompt = TREND_ANALYSIS_PROMPT.format(
            current_snapshot=json.dumps(snapshot, indent=2, default=str, ensure_ascii=False),
            previous_snapshot=json.dumps(previous, indent=2, default=str, ensure_ascii=False)
            if previous
            else "Önceki snapshot yok (ilk trend analizi)",
        )

        response, provider = await self._call_ai(
            prompt=prompt,
            system_prompt=LEARNING_AGENT_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=TOKEN_LIMITS["trend_analysis"],
        )

        insight = {
            "type": "trend_analysis",
            "cycle": self._cycle_count,
            "trend_number": self._trend_count,
            "timestamp": datetime.now().isoformat(),
            "raw_response": response,
            "parsed": self._try_parse_json(response),
            "provider": provider,
        }

        self._store_insight(insight)
        logger.info(
            f"[QAGENTT] 📊 Trend Analysis #{self._trend_count} | "
            f"Provider: {provider} | "
            f"Gemini: {self.gemini.stats['daily_calls']}/1500 calls today"
        )

    async def _run_deep_analysis(self, snapshot: Dict[str, Any]):
        """2-hour deep strategy analysis."""
        self._deep_count += 1

        # Get snapshot from 2 hours ago
        previous = self._get_snapshot_ago(minutes=120)

        # Compile memory
        memory = "\n".join(self._learned_patterns[-20:]) if self._learned_patterns else "Henüz öğrenilmiş pattern yok."

        # Compile directives
        directives = "\n".join(self._directives) if self._directives else "Aktif direktif yok."

        prompt = DEEP_ANALYSIS_PROMPT.format(
            current_snapshot=json.dumps(snapshot, indent=2, default=str, ensure_ascii=False),
            previous_snapshot=json.dumps(previous, indent=2, default=str, ensure_ascii=False)
            if previous
            else "Önceki snapshot yok",
            memory=memory,
            directives=directives,
        )

        response, provider = await self._call_ai(
            prompt=prompt,
            system_prompt=LEARNING_AGENT_SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=TOKEN_LIMITS["deep_analysis"],
        )

        insight = {
            "type": "deep_analysis",
            "cycle": self._cycle_count,
            "deep_number": self._deep_count,
            "timestamp": datetime.now().isoformat(),
            "raw_response": response,
            "parsed": self._try_parse_json(response),
            "provider": provider,
        }

        # Extract learnings from parsed response
        parsed = insight.get("parsed", {})
        if isinstance(parsed, dict):
            learnings = parsed.get("ogrendiklerim", [])
            if learnings:
                for learning in learnings:
                    if learning not in self._learned_patterns:
                        self._learned_patterns.append(learning)
                        logger.info(f"[QAGENTT] 🎓 Yeni öğrenme: {learning}")

                # Persist patterns
                await self._save_to_redis(
                    REDIS_KEYS["learned_patterns"],
                    json.dumps(self._learned_patterns, ensure_ascii=False),
                    ttl=REDIS_TTL["learned_patterns"],
                )

        self._store_insight(insight)
        logger.info(
            f"[QAGENTT] 🔬 Deep Analysis #{self._deep_count} | "
            f"Provider: {provider} | "
            f"Patterns: {len(self._learned_patterns)} | "
            f"Gemini: {self.gemini.stats['daily_calls']}/1500 calls today"
        )

        # Also run truth tick deep analysis during deep analysis cycle
        try:
            await self._run_truth_tick_analysis()
        except Exception as e:
            logger.warning(f"[QAGENTT] Truth tick analysis skipped: {e}")

    async def _run_truth_tick_analysis(self, lookback_days: int = 5, top_n: int = 3):
        """
        Truth tick 30-dakikalık window analizi.

        Her DOS grubundaki hisseler için:
        - 5 günlük truth tick serisini çeker
        - 30'ar dk'lık periyotlara böler
        - Volume/AVG_ADV oranıyla karşılaştırır
        - Her grupta en ilgi çekici 3 hisseyi seçer
        - Sonucu Gemini'ye gönderip portfolio/MM model önerisi alır
        """
        self._tt_analysis_count += 1
        logger.info(f"[QAGENTT] 🔬 Truth Tick Analysis #{self._tt_analysis_count} starting...")

        from app.agent.truth_tick_analyzer import run_truth_tick_deep_analysis

        result = await run_truth_tick_deep_analysis(
            lookback_days=lookback_days,
            top_n=top_n,
        )

        if result.get("error"):
            logger.warning(f"[QAGENTT] Truth tick analysis error: {result['error']}")
            return result

        self._last_tt_analysis = result

        # Store as insight
        insight = {
            "type": "truth_tick_analysis",
            "cycle": self._cycle_count,
            "tt_number": self._tt_analysis_count,
            "timestamp": datetime.now().isoformat(),
            "raw_response": result.get("gemini_interpretation", ""),
            "parsed": self._try_parse_json(result.get("gemini_interpretation", "")),
            "stats": {
                "total_symbols": result.get("raw_analysis", {}).get("total_symbols_analyzed"),
                "total_groups": result.get("raw_analysis", {}).get("total_groups"),
                "elapsed": result.get("raw_analysis", {}).get("elapsed_seconds"),
            },
        }

        # Extract learnings
        parsed = insight.get("parsed", {})
        if isinstance(parsed, dict):
            learnings = parsed.get("öğrendiklerim", parsed.get("ogrendiklerim", []))
            for learning in learnings:
                if learning not in self._learned_patterns:
                    self._learned_patterns.append(learning)
                    logger.info(f"[QAGENTT] 🎓 TT Öğrenme: {learning}")

        self._store_insight(insight)
        logger.info(
            f"[QAGENTT] ✅ Truth Tick Analysis #{self._tt_analysis_count} complete | "
            f"{insight['stats'].get('total_symbols', 0)} symbols, "
            f"{insight['stats'].get('total_groups', 0)} groups"
        )
        return result

    async def run_truth_tick_analysis_manual(self, lookback_days: int = 5, top_n: int = 3):
        """Public method for on-demand truth tick analysis (called from API)."""
        return await self._run_truth_tick_analysis(lookback_days=lookback_days, top_n=top_n)

    # ═══════════════════════════════════════════════════════════
    # DIRECTIVE SYSTEM
    # ═══════════════════════════════════════════════════════════

    async def add_directive(self, directive: str):
        """
        Sahibinden (Taha) bir direktif ekle.

        Örnekler:
            "Bugün NLY-PD'ye dikkat et, ex-div yaklaşıyor"
            "CONY short kesinlikle gitme, likidite sıfır"
            "Exposure %85'i geçmesin bugün, piyasa kötü görünüyor"
        """
        timestamp = datetime.now().strftime("%H:%M")
        tagged = f"[{timestamp}] {directive}"
        self._directives.append(tagged)

        # Max 20 active directives
        if len(self._directives) > 20:
            self._directives = self._directives[-20:]

        # Persist
        await self._save_to_redis(
            REDIS_KEYS["directives"],
            json.dumps(self._directives, ensure_ascii=False),
            ttl=REDIS_TTL["directives"],
        )

        logger.info(f"[QAGENTT] 📋 Direktif eklendi: {directive}")

    async def clear_directives(self):
        """Tüm aktif direktifleri temizle."""
        self._directives.clear()
        await self._save_to_redis(REDIS_KEYS["directives"], "[]")
        logger.info("[QAGENTT] 📋 Tüm direktifler temizlendi")

    # ═══════════════════════════════════════════════════════════
    # FEEDBACK SYSTEM
    # ═══════════════════════════════════════════════════════════

    async def record_trade_outcome(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        notes: str = "",
    ):
        """
        Bir işlem sonucunu kaydet — agent bundan öğrenecek.

        Args:
            symbol: "NLY-PD"
            action: "LONG" veya "SHORT"
            entry_price: Giriş fiyatı
            exit_price: Çıkış fiyatı
            pnl: Kâr/Zarar ($)
            notes: Ek notlar
        """
        outcome = {
            "symbol": symbol,
            "action": action,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_pct": round((exit_price - entry_price) / entry_price * 100, 2)
            if action == "LONG"
            else round((entry_price - exit_price) / entry_price * 100, 2),
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
        }

        # Store in Redis list
        r = self._get_redis_sync()
        if r:
            try:
                r.rpush(REDIS_KEYS["trade_outcomes"], json.dumps(outcome, ensure_ascii=False))
                r.ltrim(REDIS_KEYS["trade_outcomes"], -100, -1)  # Keep last 100
            except Exception as e:
                logger.error(f"[QAGENTT] Trade outcome Redis error: {e}")

        result = "✅ BAŞARILI" if pnl > 0 else "❌ BAŞARISIZ"
        logger.info(
            f"[QAGENTT] 📝 Trade outcome: {symbol} {action} | "
            f"PnL: ${pnl:.2f} | {result}"
        )

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _store_insight(self, insight: Dict[str, Any]):
        """Store insight in memory and Redis."""
        self._latest_insight = insight
        self._insights_history.append(insight)

        # Keep last 50 insights in memory
        if len(self._insights_history) > 50:
            self._insights_history = self._insights_history[-50:]

        # Persist to Redis (fire and forget)
        asyncio.ensure_future(self._save_to_redis(
            REDIS_KEYS["last_analysis"],
            json.dumps(insight, default=str, ensure_ascii=False),
            ttl=REDIS_TTL["last_analysis"],
        ))

    def _get_snapshot_ago(self, minutes: int) -> Optional[Dict[str, Any]]:
        """Get a snapshot from approximately N minutes ago."""
        if not self._snapshot_buffer:
            return None

        target_time = datetime.now() - timedelta(minutes=minutes)
        best = None
        best_diff = float("inf")

        for snap in self._snapshot_buffer:
            snap_time_str = snap.get("agent_time", "")
            if not snap_time_str:
                continue
            try:
                snap_time = datetime.fromisoformat(snap_time_str)
                diff = abs((snap_time - target_time).total_seconds())
                if diff < best_diff:
                    best_diff = diff
                    best = snap
            except (ValueError, TypeError):
                continue

        return best

    def _try_parse_json(self, raw: str) -> Any:
        """Try to parse JSON from Gemini response."""
        if not raw:
            return {}

        # Strip markdown code block
        text = raw.strip()
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"raw_text": raw[:1000]}

    def _get_redis_sync(self):
        """Get Redis sync client."""
        try:
            from app.core.redis_client import get_redis
            return get_redis()
        except Exception:
            return None

    async def _save_to_redis(self, key: str, value: str, ttl: int = 86400):
        """Save a value to Redis (async — no event loop blocking)."""
        try:
            from app.core.redis_client import redis_client
            r = await redis_client.async_client()
            if r:
                if ttl and ttl > 0:
                    await r.set(key, value, ex=ttl)
                else:
                    await r.set(key, value)  # TTL=0 means no expiry
        except Exception as e:
            logger.error(f"[QAGENTT] Redis save error ({key}): {e}")

    async def _load_state_from_redis(self):
        """Load persisted state from Redis on startup."""
        try:
            # Load learned patterns
            patterns_raw = await self._load_from_redis(REDIS_KEYS["learned_patterns"])
            if patterns_raw:
                self._learned_patterns = json.loads(patterns_raw)
                logger.info(
                    f"[QAGENTT] 🧠 Loaded {len(self._learned_patterns)} learned patterns from Redis"
                )

            # Load directives
            directives_raw = await self._load_from_redis(REDIS_KEYS["directives"])
            if directives_raw:
                self._directives = json.loads(directives_raw)
                logger.info(
                    f"[QAGENTT] 📋 Loaded {len(self._directives)} active directives from Redis"
                )
        except Exception as e:
            logger.error(f"[QAGENTT] Redis load error: {e}")

    async def _save_daily_summary(self):
        """Save end-of-day summary."""
        summary = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_cycles": self._cycle_count,
            "quick_checks": self._quick_count,
            "trend_analyses": self._trend_count,
            "deep_analyses": self._deep_count,
            "patterns_learned": len(self._learned_patterns),
            "directives_received": len(self._directives),
            "gemini_calls": self.gemini.stats["daily_calls"] if self.gemini else 0,
            "active_provider": self._active_provider,
            "gemini_quota_exhausted": self._gemini_quota_exhausted,
            "uptime_hours": round(
                (datetime.now() - self._start_time).total_seconds() / 3600, 1
            )
            if self._start_time
            else 0,
        }

        await self._save_to_redis(
            REDIS_KEYS["daily_summary"],
            json.dumps(summary, ensure_ascii=False),
            ttl=REDIS_TTL["daily_summary"],
        )
        logger.info(f"[QAGENTT] 📊 Daily summary saved: {summary}")

    # ═══════════════════════════════════════════════════════════
    # PUBLIC PROPERTIES
    # ═══════════════════════════════════════════════════════════

    @property
    def latest_insight(self) -> Optional[Dict[str, Any]]:
        """Get the most recent analysis result."""
        return self._latest_insight

    @property
    def insights_history(self) -> List[Dict[str, Any]]:
        """Get insight history (most recent last)."""
        return self._insights_history

    @property
    def learned_patterns(self) -> List[str]:
        """Get all learned patterns."""
        return self._learned_patterns

    @property
    def active_directives(self) -> List[str]:
        """Get active directives from Taha."""
        return self._directives

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_tt_analysis(self) -> Optional[Dict[str, Any]]:
        """Get the last truth tick analysis result."""
        return self._last_tt_analysis

    @property
    def status(self) -> Dict[str, Any]:
        """Get comprehensive agent status."""
        base = {
            "running": self._running,
            "mode": self._mode,
            "uptime": str(datetime.now() - self._start_time) if self._start_time else "N/A",
            "total_cycles": self._cycle_count,
            "patterns_learned": len(self._learned_patterns),
            "active_directives": len(self._directives),
            "snapshot_buffer_size": len(self._snapshot_buffer),
            "last_insight_type": self._latest_insight.get("type") if self._latest_insight else None,
            "last_insight_time": self._latest_insight.get("timestamp") if self._latest_insight else None,
        }
        
        if self._mode == "v2":
            haiku_stats = self._claude_haiku.stats if self._claude_haiku else None
            sonnet_stats = self._claude_sonnet.stats if self._claude_sonnet else None
            haiku_cost = haiku_stats.get("daily_cost_usd", 0) if haiku_stats else 0
            sonnet_cost = sonnet_stats.get("daily_cost_usd", 0) if sonnet_stats else 0
            
            base.update({
                "v2_scan_count": self._scan_count,
                "v2_deep_count": self._deep_v2_count,
                "v2_daily_deep_calls": self._daily_deep_calls,
                "v2_daily_deep_limit": SMART_HYBRID_CONFIG["max_deep_per_day"],
                "v2_haiku_stats": haiku_stats,
                "v2_sonnet_stats": sonnet_stats,
                "v2_daily_cost_usd": round(haiku_cost + sonnet_cost, 4),
                "v2_last_scan_status": self._last_scan_result.get("status") if self._last_scan_result else None,
            })
        else:
            base.update({
                "active_provider": self._active_provider,
                "gemini_quota_exhausted": self._gemini_quota_exhausted,
                "quick_checks": self._quick_count,
                "trend_analyses": self._trend_count,
                "deep_analyses": self._deep_count,
                "tt_analyses": self._tt_analysis_count,
                "gemini_stats": self.gemini.stats if self.gemini else None,
                "claude_stats": self.claude.stats if self.claude else None,
                "last_tt_analysis_time": self._last_tt_analysis.get("timestamp") if self._last_tt_analysis else None,
            })
        
        return base


# ═══════════════════════════════════════════════════════════════
# GLOBAL INSTANCE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

_learning_agent: Optional[PreferredStockLearningAgent] = None


def get_learning_agent() -> Optional[PreferredStockLearningAgent]:
    """Get the global learning agent instance."""
    return _learning_agent


async def start_learning_agent(
    api_key: Optional[str] = None,
    claude_api_key: Optional[str] = None,
    quick_interval: int = INTERVALS["quick_check"],
    trend_interval: int = INTERVALS["trend_analysis"],
    deep_interval: int = INTERVALS["deep_analysis"],
    auto_start: bool = True,
    mode: str = "v1",  # "v1" or "v2"
) -> PreferredStockLearningAgent:
    """
    Create and optionally start the global learning agent.

    Modes:
      v1 (legacy): Gemini Flash (free) → Claude Haiku fallback.
      v2 (smart hybrid): Haiku SCAN every 5min + Sonnet DEEP on anomaly.

    Args:
        api_key: Gemini API key. Tries Redis → env var if None.
        claude_api_key: Claude API key. Tries Redis → env var if None.
        quick_interval: Seconds between quick checks (default 300 = 5 min)
        trend_interval: Seconds between trend analyses (default 1800 = 30 min)
        deep_interval: Seconds between deep analyses (default 7200 = 2 hours)
        auto_start: Auto-start the observation loop
        mode: "v1" for legacy Gemini, "v2" for Smart Hybrid (Haiku+Sonnet)

    Returns:
        PreferredStockLearningAgent instance
    """
    global _learning_agent

    if _learning_agent and _learning_agent.is_running:
        logger.info("[QAGENTT] Already running, returning existing instance")
        return _learning_agent

    # Resolve API keys
    key = api_key or _resolve_gemini_key()
    if not key:
        # For v2, Gemini is optional (we have Claude)
        if mode == "v2":
            key = "not-used-in-v2"  # Placeholder; v2 uses Claude directly
        else:
            raise ValueError(
                "Gemini API key required. Pass api_key, set GEMINI_API_KEY env var, "
                "or store in Redis at psfalgo:agent:gemini_api_key"
            )

    _learning_agent = PreferredStockLearningAgent(
        api_key=key,
        claude_api_key=claude_api_key,
        quick_interval=quick_interval,
        trend_interval=trend_interval,
        deep_interval=deep_interval,
        mode=mode,
    )

    if auto_start:
        await _learning_agent.start()

    return _learning_agent


async def stop_learning_agent():
    """Stop the global learning agent."""
    global _learning_agent
    if _learning_agent:
        await _learning_agent.stop()
        _learning_agent = None


def _resolve_gemini_key() -> Optional[str]:
    """Try to find Gemini API key from Redis → env var."""
    try:
        from app.core.redis_client import get_redis_sync
        r = get_redis_sync()
        if r:
            key = r.get("psfalgo:agent:gemini_api_key")
            if key:
                logger.info("[QAGENTT] Gemini API key found in Redis")
                return key if isinstance(key, str) else key.decode("utf-8")
    except Exception:
        pass

    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        logger.info("[QAGENTT] Gemini API key found in GEMINI_API_KEY env var")
        return env_key

    return None


def _resolve_claude_key() -> Optional[str]:
    """Try to find Claude API key from Redis → env var."""
    try:
        from app.core.redis_client import get_redis_sync
        r = get_redis_sync()
        if r:
            key = r.get("psfalgo:agent:claude_api_key")
            if key:
                logger.info("[QAGENTT] Claude API key found in Redis")
                return key if isinstance(key, str) else key.decode("utf-8")
    except Exception:
        pass

    env_key = os.getenv("ANTHROPIC_API_KEY")
    if env_key:
        logger.info("[QAGENTT] Claude API key found in ANTHROPIC_API_KEY env var")
        return env_key

    return None
