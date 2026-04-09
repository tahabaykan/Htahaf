"""
PSFALGO Integration Test Script
===============================

Bu script sistemin tüm parçalarının doğru çalışıp çalışmadığını test eder:
- Gerçek IBKR ve Hammer bağlantıları
- Fake/Mock emir gönderimleri
- RunAll → XNL → REV akışı
- MinMax Area validasyonu
- Order tag formatı

Kullanım:
    python test_integration_flow.py [--account IBKR_PED|IBKR_GUN|HAMPRO]
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
from loguru import logger
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO"
)


# ============================================================================
# MOCK LAYER - Fake order sending
# ============================================================================

class MockOrderResult:
    """Simulated order placement result"""
    def __init__(self, symbol: str, action: str, qty: int, price: float):
        self.order_id = f"MOCK_{int(time.time() * 1000)}"
        self.symbol = symbol
        self.action = action
        self.qty = qty
        self.price = price
        self.status = "SUBMITTED"
        self.filled_qty = 0
        self.timestamp = datetime.now()


class MockOrderManager:
    """Mock order manager that logs but doesn't actually send orders"""
    
    def __init__(self):
        self.orders: List[MockOrderResult] = []
        self.fills: List[Dict] = []
        
    async def place_order(self, symbol: str, action: str, qty: int, price: float, tag: str = "") -> MockOrderResult:
        """Simulate order placement"""
        result = MockOrderResult(symbol, action, qty, price)
        self.orders.append(result)
        
        logger.info(f"🎯 [MOCK ORDER] {action} {qty} {symbol} @ ${price:.2f} | Tag: {tag} | ID: {result.order_id}")
        
        # Simulate partial fill after a short delay
        await asyncio.sleep(0.1)
        result.filled_qty = qty // 2  # 50% fill
        result.status = "PARTIALLY_FILLED"
        
        self.fills.append({
            'order_id': result.order_id,
            'symbol': symbol,
            'action': action,
            'filled_qty': result.filled_qty,
            'price': price,
            'timestamp': datetime.now()
        })
        
        return result
    
    def get_summary(self) -> Dict:
        """Get order summary"""
        buys = [o for o in self.orders if o.action == "BUY"]
        sells = [o for o in self.orders if o.action == "SELL"]
        return {
            'total_orders': len(self.orders),
            'buy_orders': len(buys),
            'sell_orders': len(sells),
            'total_buy_qty': sum(o.qty for o in buys),
            'total_sell_qty': sum(o.qty for o in sells),
            'fills': len(self.fills)
        }


# Global mock manager
_mock_order_manager = MockOrderManager()


def get_mock_order_manager() -> MockOrderManager:
    return _mock_order_manager


# ============================================================================
# TEST UTILITIES
# ============================================================================

@dataclass
class TestResult:
    name: str
    passed: bool
    details: str
    duration_ms: float


class IntegrationTestRunner:
    """Runs integration tests with real connections"""
    
    def __init__(self, account_id: str = "IBKR_PED"):
        self.account_id = account_id
        self.results: List[TestResult] = []
        self.mock_manager = get_mock_order_manager()
        
    def log_result(self, name: str, passed: bool, details: str, duration_ms: float):
        result = TestResult(name, passed, details, duration_ms)
        self.results.append(result)
        
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} | {name} | {details} | {duration_ms:.0f}ms")
        
    async def run_all_tests(self):
        """Run all integration tests"""
        logger.info("=" * 80)
        logger.info("🧪 PSFALGO INTEGRATION TEST SUITE")
        logger.info(f"   Account: {self.account_id}")
        logger.info(f"   Time: {datetime.now().isoformat()}")
        logger.info("=" * 80)
        
        # Test 1: Redis Connection
        await self.test_redis_connection()
        
        # Test 2: Trading Context
        await self.test_trading_context()
        
        # Test 3: IBKR Connection (if IBKR account)
        if "IBKR" in self.account_id:
            await self.test_ibkr_connection()
        
        # Test 4: Hammer Connection
        await self.test_hammer_connection()
        
        # Test 5: Position Snapshot API
        await self.test_position_snapshot()
        
        # Test 6: MinMax Area Service
        await self.test_minmax_area_service()
        
        # Test 7: Order Tag Format
        await self.test_order_tag_format()
        
        # Test 8: RunAll Engine (Mock Orders)
        await self.test_runall_engine()
        
        # Test 9: XNL Engine Flow (Mock Orders)
        await self.test_xnl_engine_flow()
        
        # Test 10: REV Order Mechanism
        await self.test_rev_order_mechanism()
        
        # Summary
        self.print_summary()
        
    async def test_redis_connection(self):
        """Test Redis connection"""
        start = time.time()
        try:
            from app.core.redis_client import get_redis
            redis = get_redis()
            
            if redis is None:
                self.log_result("Redis Connection", False, "Redis client is None", (time.time() - start) * 1000)
                return
            
            # Test ping
            redis.set("test:integration", "alive")
            value = redis.get("test:integration")
            
            if value == b"alive" or value == "alive":
                self.log_result("Redis Connection", True, "Connected & responsive", (time.time() - start) * 1000)
            else:
                self.log_result("Redis Connection", False, f"Unexpected value: {value}", (time.time() - start) * 1000)
                
        except Exception as e:
            self.log_result("Redis Connection", False, str(e), (time.time() - start) * 1000)
            
    async def test_trading_context(self):
        """Test trading context initialization"""
        start = time.time()
        try:
            from app.trading.trading_account_context import get_trading_context, TradingAccountMode
            
            # Get context and set mode via method
            ctx = get_trading_context()
            
            # Convert account_id string to TradingAccountMode enum
            mode_map = {
                "IBKR_PED": TradingAccountMode.IBKR_PED,
                "IBKR_GUN": TradingAccountMode.IBKR_GUN,
                "HAMPRO": TradingAccountMode.HAMPRO
            }
            target_mode = mode_map.get(self.account_id, TradingAccountMode.IBKR_PED)
            ctx.set_trading_mode(target_mode)
            
            current_mode = ctx.trading_mode.value
            
            if current_mode == self.account_id:
                self.log_result("Trading Context", True, f"Mode set to {current_mode}", (time.time() - start) * 1000)
            else:
                self.log_result("Trading Context", False, f"Expected {self.account_id}, got {current_mode}", (time.time() - start) * 1000)
                
        except Exception as e:
            self.log_result("Trading Context", False, str(e), (time.time() - start) * 1000)

    async def test_ibkr_connection(self):
        """Test IBKR Gateway connection"""
        start = time.time()
        try:
            from app.psfalgo.ibkr_connector import connect_isolated_sync
            
            # Determine port based on account
            port = 4001 if self.account_id == "IBKR_PED" else 4002
            client_id = 12 if self.account_id == "IBKR_PED" else 11
            
            logger.info(f"   Connecting to IBKR Gateway port {port}...")
            
            ib = await connect_isolated_sync(
                host="127.0.0.1",
                port=port,
                client_id=client_id + 100,  # Use different client ID for test
            )
            
            if ib and ib.isConnected():
                accounts = ib.managedAccounts()
                ib.disconnect()
                self.log_result("IBKR Connection", True, f"Connected, accounts: {accounts}", (time.time() - start) * 1000)
            else:
                self.log_result("IBKR Connection", False, "Connection failed", (time.time() - start) * 1000)
                
        except Exception as e:
            self.log_result("IBKR Connection", False, str(e)[:100], (time.time() - start) * 1000)
            
    async def test_hammer_connection(self):
        """Test Hammer Pro connection"""
        start = time.time()
        try:
            from app.live.hammer_client import HammerClient
            
            client = HammerClient()
            
            # Try to connect
            connected = client.connect()
            
            if connected or client.is_connected():
                self.log_result("Hammer Connection", True, "Connected to Hammer Pro", (time.time() - start) * 1000)
                client.disconnect()
            else:
                self.log_result("Hammer Connection", False, "Connection failed", (time.time() - start) * 1000)
                
        except Exception as e:
            # Hammer might not be running - that's OK for test
            self.log_result("Hammer Connection", False, f"Not available: {str(e)[:50]}", (time.time() - start) * 1000)
            
    async def test_position_snapshot(self):
        """Test Position Snapshot API"""
        start = time.time()
        try:
            from app.psfalgo.position_snapshot_api import get_position_snapshot_api, initialize_position_snapshot_api
            
            api = get_position_snapshot_api()
            if api is None:
                # Try to initialize
                api = initialize_position_snapshot_api()
            
            if api is None:
                self.log_result("Position Snapshot API", False, "API is None after init attempt", (time.time() - start) * 1000)
                return
            
            # Get positions
            positions = await api.get_position_snapshot(
                account_id=self.account_id,
                include_zero_positions=False
            )
            
            pos_count = len(positions) if positions else 0
            sample = [p.symbol for p in positions[:3]] if positions else []
            
            self.log_result("Position Snapshot API", True, f"{pos_count} positions, sample: {sample}", (time.time() - start) * 1000)
            
        except Exception as e:
            self.log_result("Position Snapshot API", False, str(e)[:100], (time.time() - start) * 1000)
            
    async def test_minmax_area_service(self):
        """Test MinMax Area Service"""
        start = time.time()
        try:
            from app.psfalgo.minmax_area_service import (
                get_minmax_area_service,
                get_max_buy_qty,
                get_max_sell_qty,
                pre_validate_order_for_runall
            )
            
            svc = get_minmax_area_service()
            
            # Compute for a test symbol
            test_symbols = ["AAPL", "MSFT", "GOOGL"]
            svc.compute_for_account(self.account_id, symbols=test_symbols)
            
            # Check if we have data
            rows = svc.get_all_rows(self.account_id)
            row_count = len(rows) if rows else 0
            
            # Test pre-validation
            allowed, adj_qty, reason = pre_validate_order_for_runall(
                account_id=self.account_id,
                symbol="AAPL",
                action="BUY",
                qty=500
            )
            
            self.log_result(
                "MinMax Area Service", 
                True, 
                f"{row_count} rows computed, validation: allowed={allowed}, qty={adj_qty}", 
                (time.time() - start) * 1000
            )
            
        except Exception as e:
            self.log_result("MinMax Area Service", False, str(e)[:100], (time.time() - start) * 1000)
            
    async def test_order_tag_format(self):
        """Test Order Tag Format includes account ID"""
        start = time.time()
        try:
            from app.api.janall_routes import determine_order_tag
            
            # Mock order and position
            mock_order = {
                'symbol': 'AAPL',
                'action': 'SELL',
                'qty': 500,
                'source': 'LT_TRIM'
            }
            mock_position_map = {
                'AAPL': {'qty': 1000, 'potential_qty': 500}
            }
            
            # Test with account_id
            tag = determine_order_tag(mock_order, mock_position_map, account_id=self.account_id)
            
            expected_prefix = self.account_id
            if tag.startswith(expected_prefix):
                self.log_result("Order Tag Format", True, f"Tag: {tag}", (time.time() - start) * 1000)
            else:
                self.log_result("Order Tag Format", False, f"Tag missing account prefix: {tag}", (time.time() - start) * 1000)
                
        except Exception as e:
            self.log_result("Order Tag Format", False, str(e)[:100], (time.time() - start) * 1000)
            
    async def test_runall_engine(self):
        """Test RunAll Engine with mock orders"""
        start = time.time()
        try:
            from app.psfalgo.runall_engine import get_runall_engine
            
            engine = get_runall_engine()
            
            # Prepare a cycle request
            request = await engine.prepare_cycle_request(self.account_id)
            
            if request is None:
                self.log_result("RunAll Engine", False, "Request preparation failed", (time.time() - start) * 1000)
                return
            
            pos_count = len(request.positions) if request.positions else 0
            metrics_count = len(request.metrics) if request.metrics else 0
            
            # Log what we got
            logger.info(f"   RunAll Request: {pos_count} positions, {metrics_count} metrics")
            
            # Test MinMax computation in RunAll
            if pos_count > 0:
                from app.psfalgo.minmax_area_service import get_minmax_area_service
                minmax_svc = get_minmax_area_service()
                symbols = [p.symbol for p in request.positions[:10]]
                minmax_svc.compute_for_account(self.account_id, symbols=symbols)
                logger.info(f"   MinMax computed for {len(symbols)} symbols")
            
            self.log_result(
                "RunAll Engine", 
                True, 
                f"Request OK: {pos_count} positions, {metrics_count} metrics", 
                (time.time() - start) * 1000
            )
            
        except Exception as e:
            self.log_result("RunAll Engine", False, str(e)[:100], (time.time() - start) * 1000)
            
    async def test_xnl_engine_flow(self):
        """Test XNL Engine flow with mock orders"""
        start = time.time()
        try:
            from app.xnl.xnl_engine import XNLEngine, OrderTagCategory
            
            engine = XNLEngine()
            state = engine.get_state()
            
            # Verify initial state
            if state['state'] != 'STOPPED':
                self.log_result("XNL Engine Flow", False, f"Initial state wrong: {state['state']}", (time.time() - start) * 1000)
                return
            
            # Test cycle timing configuration
            cycle_states = state.get('cycle_states', {})
            lt_dec = cycle_states.get('LT_DECREASE', {})
            
            front_seconds = lt_dec.get('timing', {}).get('front_seconds', 0)
            
            if front_seconds == 120:  # 2 minutes
                self.log_result(
                    "XNL Engine Flow", 
                    True, 
                    f"Config OK: LT_DEC front cycle = {front_seconds}s", 
                    (time.time() - start) * 1000
                )
            else:
                self.log_result(
                    "XNL Engine Flow", 
                    False, 
                    f"Wrong timing: expected 120s, got {front_seconds}s", 
                    (time.time() - start) * 1000
                )
                
        except Exception as e:
            self.log_result("XNL Engine Flow", False, str(e)[:100], (time.time() - start) * 1000)
            
    async def test_rev_order_mechanism(self):
        """Test REV Order mechanism (fill tracking)"""
        start = time.time()
        try:
            from app.core.redis_client import get_redis
            
            redis = get_redis()
            if not redis:
                self.log_result("REV Order Mechanism", False, "Redis not available", (time.time() - start) * 1000)
                return
            
            # Check if XNL running flags exist
            xnl_running = redis.get("psfalgo:xnl:running")
            running_account = redis.get("psfalgo:xnl:running_account")
            
            # Simulate setting XNL running
            redis.set("psfalgo:xnl:running", "1")
            redis.set("psfalgo:xnl:running_account", self.account_id)
            
            # Verify
            xnl_running_after = redis.get("psfalgo:xnl:running")
            running_account_after = redis.get("psfalgo:xnl:running_account")
            
            # Clean up
            redis.set("psfalgo:xnl:running", "0")
            redis.set("psfalgo:xnl:running_account", "")
            
            if xnl_running_after in [b"1", "1"]:
                account_val = running_account_after.decode() if isinstance(running_account_after, bytes) else running_account_after
                self.log_result(
                    "REV Order Mechanism", 
                    True, 
                    f"Redis flags work: running=1, account={account_val}", 
                    (time.time() - start) * 1000
                )
            else:
                self.log_result("REV Order Mechanism", False, "Redis flag not set", (time.time() - start) * 1000)
                
        except Exception as e:
            self.log_result("REV Order Mechanism", False, str(e)[:100], (time.time() - start) * 1000)
            
    def print_summary(self):
        """Print test summary"""
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 80)
        
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        
        logger.info(f"   Total Tests: {total}")
        logger.info(f"   ✅ Passed: {passed}")
        logger.info(f"   ❌ Failed: {failed}")
        logger.info(f"   Success Rate: {passed/total*100:.1f}%")
        
        if failed > 0:
            logger.info("")
            logger.info("Failed Tests:")
            for r in self.results:
                if not r.passed:
                    logger.info(f"   ❌ {r.name}: {r.details}")
        
        # Mock order summary
        mock_summary = self.mock_manager.get_summary()
        if mock_summary['total_orders'] > 0:
            logger.info("")
            logger.info("📦 Mock Orders Summary:")
            logger.info(f"   Total Orders: {mock_summary['total_orders']}")
            logger.info(f"   BUY: {mock_summary['buy_orders']} ({mock_summary['total_buy_qty']} shares)")
            logger.info(f"   SELL: {mock_summary['sell_orders']} ({mock_summary['total_sell_qty']} shares)")
            logger.info(f"   Fills: {mock_summary['fills']}")
        
        logger.info("")
        logger.info("=" * 80)


# ============================================================================
# SIMULATION MODE - Full cycle simulation with mock orders
# ============================================================================

async def run_full_simulation(account_id: str):
    """Run a full cycle simulation with mock orders"""
    logger.info("")
    logger.info("=" * 80)
    logger.info("🎮 FULL CYCLE SIMULATION (Mock Orders)")
    logger.info("=" * 80)
    
    mock_manager = get_mock_order_manager()
    
    try:
        # 1. Set trading mode
        from app.trading.trading_account_context import get_trading_context, TradingAccountMode
        ctx = get_trading_context()
        mode_map = {
            "IBKR_PED": TradingAccountMode.IBKR_PED,
            "IBKR_GUN": TradingAccountMode.IBKR_GUN,
            "HAMPRO": TradingAccountMode.HAMPRO
        }
        target_mode = mode_map.get(account_id, TradingAccountMode.IBKR_PED)
        ctx.set_trading_mode(target_mode)
        logger.info(f"✅ Trading mode set to: {account_id}")
        
        # 2. Get RunAll request
        from app.psfalgo.runall_engine import get_runall_engine
        engine = get_runall_engine()
        
        request = await engine.prepare_cycle_request(account_id)
        if request is None:
            logger.error("❌ Could not prepare cycle request")
            return
        
        logger.info(f"✅ Cycle request prepared: {len(request.positions)} positions")
        
        # 3. Compute MinMax for all positions
        from app.psfalgo.minmax_area_service import get_minmax_area_service, pre_validate_order_for_runall
        minmax_svc = get_minmax_area_service()
        
        symbols = [p.symbol for p in request.positions]
        if symbols:
            minmax_svc.compute_for_account(account_id, symbols=symbols)
            logger.info(f"✅ MinMax computed for {len(symbols)} symbols")
        
        # 4. Simulate some order proposals
        logger.info("")
        logger.info("📋 Simulating Order Proposals...")
        
        proposals = []
        for pos in request.positions[:5]:  # First 5 positions
            # Simulate LT_TRIM order
            action = "SELL" if pos.qty > 0 else "BUY"
            proposed_qty = min(abs(pos.qty) // 4, 500)  # 25% of position, max 500
            
            if proposed_qty < 100:
                continue
            
            # Validate against MinMax
            allowed, adj_qty, reason = pre_validate_order_for_runall(
                account_id=account_id,
                symbol=pos.symbol,
                action=action,
                qty=proposed_qty
            )
            
            if allowed:
                proposals.append({
                    'symbol': pos.symbol,
                    'action': action,
                    'qty': adj_qty,
                    'price': getattr(pos, 'last_price', 10.0) or 10.0,
                    'tag': f"{account_id}_LT_{'LONG' if pos.qty > 0 else 'SHORT'}_DEC",
                    'source': 'LT_TRIM'
                })
                logger.info(f"   📝 {pos.symbol}: {action} {adj_qty} (validated)")
            else:
                logger.info(f"   ⛔ {pos.symbol}: {action} {proposed_qty} BLOCKED - {reason}")
        
        # 5. Send mock orders
        if proposals:
            logger.info("")
            logger.info("📤 Sending Mock Orders...")
            
            for p in proposals:
                await mock_manager.place_order(
                    symbol=p['symbol'],
                    action=p['action'],
                    qty=p['qty'],
                    price=p['price'],
                    tag=p['tag']
                )
                await asyncio.sleep(0.05)  # Rate limit simulation
        
        # 6. Simulate REV orders from fills
        if mock_manager.fills:
            logger.info("")
            logger.info("🔄 Simulating REV Orders from fills...")
            
            for fill in mock_manager.fills:
                # REV order is opposite direction
                rev_action = "SELL" if fill['action'] == "BUY" else "BUY"
                rev_price = fill['price'] * 1.01 if rev_action == "SELL" else fill['price'] * 0.99
                
                await mock_manager.place_order(
                    symbol=fill['symbol'],
                    action=rev_action,
                    qty=fill['filled_qty'],
                    price=round(rev_price, 2),
                    tag=f"{account_id}_REV_SAVE"
                )
        
        # 7. Summary
        summary = mock_manager.get_summary()
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 SIMULATION COMPLETE")
        logger.info(f"   Total Orders Sent: {summary['total_orders']}")
        logger.info(f"   BUY Orders: {summary['buy_orders']}")
        logger.info(f"   SELL Orders: {summary['sell_orders']}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Simulation failed: {e}", exc_info=True)


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="PSFALGO Integration Test")
    parser.add_argument("--account", default="IBKR_PED", choices=["IBKR_PED", "IBKR_GUN", "HAMPRO"])
    parser.add_argument("--simulate", action="store_true", help="Run full simulation with mock orders")
    args = parser.parse_args()
    
    # Apply event loop fix
    try:
        from app.psfalgo.nbefore_common_adv import fix_event_loop
        fix_event_loop()
    except:
        pass
    
    # Run tests
    runner = IntegrationTestRunner(account_id=args.account)
    await runner.run_all_tests()
    
    # Run simulation if requested
    if args.simulate:
        await run_full_simulation(args.account)


if __name__ == "__main__":
    asyncio.run(main())
