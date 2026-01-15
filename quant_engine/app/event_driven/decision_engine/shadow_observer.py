
import logging
import time
from collections import defaultdict
from typing import Dict, List, Any, Optional
import numpy as np
from datetime import datetime

logger = logging.getLogger("shadow_observer")

class ShadowStatsCollector:
    """
    Collects KPIs for Shadow Mode observation.
    Saves metrics for:
    1. Snapshot V2 Age (p50, p90, max)
    2. Venue Coverage (FNRA, NSDQ, etc)
    3. Churn Behavior (Intents/min, freezes)
    4. V1 vs V2 Comparison (Price delta, decision changes)
    """
    def __init__(self):
        self.v2_ages: List[float] = []
        self.venue_counts = defaultdict(int)
        self.total_ticks = 0
        self.intents_count = 0
        self.throttle_rejects = 0
        self.stale_freeze_cycles = 0
        self.price_deltas: List[float] = []
        self.decision_flips = 0 # Cases where V2 would lead to different decision
        
        self.start_time = time.time()
        self.symbol_stats = defaultdict(lambda: {'intents': 0, 'freezes': 0})

    def record_snapshot_age(self, age: float):
        self.v2_ages.append(age)

    def record_venue_ticks(self, ticks: List[Dict[str, Any]]):
        for t in ticks:
            self.total_ticks += 1
            venue = t.get('venue', 'UNKNOWN')
            self.venue_counts[venue] += 1

    def record_churn_event(self, symbol: str, event_type: str):
        if event_type == 'INTENT':
            self.intents_count += 1
            self.symbol_stats[symbol]['intents'] += 1
        elif event_type == 'THROTTLE':
            self.throttle_rejects += 1
        elif event_type == 'STALE_FREEZE':
            self.stale_freeze_cycles += 1
            self.symbol_stats[symbol]['freezes'] += 1

    def record_comparison(self, v1_mid: float, v2_mid: float, would_flip: bool):
        delta = abs(v1_mid - v2_mid)
        self.price_deltas.append(delta)
        if would_flip:
            self.decision_flips += 1

    def generate_report(self, output_path: str = "SHADOW_RUN_REPORT.md"):
        now = time.time()
        duration_mins = (now - self.start_time) / 60.0
        
        lines = []
        lines.append("# SHADOW RUN REPORT")
        lines.append(f"Date: {datetime.now().isoformat()}")
        lines.append(f"Duration: {duration_mins:.2f} mins")
        lines.append("")
        
        # 1. Snapshot Age
        if self.v2_ages:
            p50 = np.percentile(self.v2_ages, 50)
            p90 = np.percentile(self.v2_ages, 90)
            mx = max(self.v2_ages)
            lines.append("## 1. Snapshot V2 Age (Seconds)")
            lines.append(f"- **p50**: {p50:.2f}s")
            lines.append(f"- **p90**: {p90:.2f}s")
            lines.append(f"- **Max**: {mx:.2f}s")
        
        # 2. Venue Coverage
        lines.append("\n## 2. Venue Coverage")
        venue_ratio = (sum(v for k,v in self.venue_counts.items() if k != 'UNKNOWN') / self.total_ticks * 100) if self.total_ticks else 0
        lines.append(f"- **Venue ID Ratio**: {venue_ratio:.1f}%")
        for venue, count in self.venue_counts.items():
            pct = (count / self.total_ticks * 100) if self.total_ticks else 0
            lines.append(f"- **{venue}**: {count} ({pct:.1f}%)")

        # 3. Churn Behavior
        lines.append("\n## 3. Churn Behavior")
        lines.append(f"- **Intents / Minute**: {self.intents_count / duration_mins:.2f}" if duration_mins > 0 else "-")
        lines.append(f"- **Throttle Rejects**: {self.throttle_rejects}")
        lines.append(f"- **Stale Freeze Cycles**: {self.stale_freeze_cycles}")

        # 4. Comparison (V1 vs V2)
        lines.append("\n## 4. Comparison (V1 Snap vs V2 Bulk)")
        if self.price_deltas:
            avg_delta = sum(self.price_deltas) / len(self.price_deltas)
            lines.append(f"- **Avg Price Delta**: ${avg_delta:.4f}")
            lines.append(f"- **Decision Flips**: {self.decision_flips} (Cases where V2 changed intent)")
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"📁 Shadow Report generated: {output_path}")

# Global Instance
shadow_observer = ShadowStatsCollector()
