"""
Session Worker

Publishes session clock events every 1 second.
Tracks market regime (OPEN/EARLY/MID/LATE/CLOSE) and minutes-to-close.
"""

import time
import signal
from datetime import datetime, timezone
from typing import Optional
from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.event_log import EventLog
from app.event_driven.contracts.events import SessionEvent
from app.event_driven.reporting.regime_transition_logger import RegimeTransitionLogger


class SessionWorker:
    """Worker that publishes session clock events"""
    
    def __init__(self, worker_name: str = "session_worker"):
        self.worker_name = worker_name
        self.running = False
        self.event_log: Optional[EventLog] = None
        self.publish_interval = 1.0  # 1 second
        
        # US Market hours (ET/EST)
        self.market_open_time = (9, 30)  # 9:30 AM
        self.market_close_time = (16, 0)  # 4:00 PM (16:00)
        
        # Track current regime for transition logging
        self.current_regime: Optional[str] = None
        self.regime_logger: Optional[RegimeTransitionLogger] = None
    
    def connect(self):
        """Connect to Redis"""
        try:
            redis_client = get_redis_client().sync
            if not redis_client:
                raise RuntimeError("Redis client not available")
            
            self.event_log = EventLog(redis_client=redis_client)
            self.regime_logger = RegimeTransitionLogger()
            logger.info(f"✅ [{self.worker_name}] Connected to Redis")
            return True
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to connect: {e}", exc_info=True)
            return False
    
    def _get_market_regime(self) -> tuple[str, bool, Optional[int]]:
        """
        Determine market regime based on current time (US ET/EST)
        
        Returns:
            (regime, market_open, minutes_to_close)
        """
        # Get current time in ET (simplified - uses local time)
        # In production, use proper timezone handling (pytz) for US ET/EST
        # For Sprint 1, we use local time and assume it's ET
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_time_minutes = current_hour * 60 + current_minute
        
        open_minutes = self.market_open_time[0] * 60 + self.market_open_time[1]  # 9:30 = 570
        close_minutes = self.market_close_time[0] * 60 + self.market_close_time[1]  # 16:00 = 960
        
        market_open = open_minutes <= current_time_minutes < close_minutes
        
        if not market_open:
            return ("CLOSED", False, None)
        
        # Determine regime
        if current_time_minutes < 600:  # Before 10:00
            regime = "OPEN"
        elif current_time_minutes < 720:  # Before 12:00
            regime = "EARLY"
        elif current_time_minutes < 900:  # Before 15:00
            regime = "MID"
        elif current_time_minutes < 975:  # Before 16:15
            regime = "LATE"
        else:  # 16:15 - 16:30
            regime = "CLOSE"
        
        minutes_to_close = close_minutes - current_time_minutes
        
        return (regime, market_open, minutes_to_close)
    
    def publish_session(self):
        """Publish session event"""
        try:
            regime, market_open, minutes_to_close = self._get_market_regime()
            
            # Log regime transition if changed
            if self.current_regime is not None and self.current_regime != regime:
                if self.regime_logger:
                    try:
                        # Get exposure data for context (optional)
                        from app.event_driven.state.store import StateStore
                        state_store = StateStore(redis_client=get_redis_client().sync)
                        exposure_data = state_store.get_state("exposure")
                        
                        self.regime_logger.log_regime_transition(
                            from_regime=self.current_regime,
                            to_regime=regime,
                            reason=f"Time-based regime change",
                            exposure_data=exposure_data
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ [{self.worker_name}] Failed to log regime transition: {e}")
            
            self.current_regime = regime
            
            event = SessionEvent.create(
                regime=regime,
                market_open=market_open,
                minutes_to_close=minutes_to_close,
            )
            
            msg_id = self.event_log.publish("session", event)
            if msg_id:
                if market_open:
                    logger.debug(
                        f"⏰ [{self.worker_name}] Published session: "
                        f"regime={regime}, minutes_to_close={minutes_to_close}"
                    )
                else:
                    logger.debug(f"⏰ [{self.worker_name}] Published session: market CLOSED")
            else:
                logger.warning(f"⚠️ [{self.worker_name}] Failed to publish session")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error publishing session: {e}", exc_info=True)
    
    def run(self):
        """Main worker loop"""
        try:
            logger.info(f"🚀 [{self.worker_name}] Starting...")
            
            if not self.connect():
                logger.error(f"❌ [{self.worker_name}] Cannot start: connection failed")
                return
            
            self.running = True
            logger.info(f"✅ [{self.worker_name}] Started (publish interval: {self.publish_interval}s)")
            
            # Main loop
            while self.running:
                self.publish_session()
                time.sleep(self.publish_interval)
        
        except KeyboardInterrupt:
            logger.info(f"🛑 [{self.worker_name}] Stopped by user")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        self.running = False
        logger.info(f"✅ [{self.worker_name}] Cleanup completed")


def main():
    """Main entry point"""
    worker = SessionWorker()
    
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{worker.worker_name}] Received SIGINT, shutting down...")
        worker.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    worker.run()


if __name__ == "__main__":
    main()

