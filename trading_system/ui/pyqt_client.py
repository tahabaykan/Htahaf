"""ui/pyqt_client.py

Basit PyQt client skeleton. Bu örnek Redis pub/sub veya WebSocket üzerinden
trading sistem özetlerini gösterir.

Bu modül:
    - PyQt5 GUI ile trading terminal arayüzü
    - Redis pub/sub veya WebSocket ile real-time data
    - Positions, orders, executions özeti
    - System health monitoring

Kullanım:
    python ui/pyqt_client.py

Environment Variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379)
    WS_URL: WebSocket URL (optional, Redis pub/sub kullanılır)
    UPDATE_INTERVAL: UI update interval (ms, default: 500)
"""

import sys
import asyncio
import json
import time
import os
from typing import Dict, Any, Optional, List
from threading import Thread

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QListWidget, QPushButton, QTableWidget,
        QTableWidgetItem, QTabWidget, QTextEdit, QSplitter
    )
    from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
    from PyQt5.QtGui import QFont
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    print("PyQt5 not available. Install with: pip install PyQt5")

from aioredis import from_url
from utils.logging_config import setup_logging, get_logger

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
WS_URL = os.getenv('WS_URL', None)  # WebSocket URL (optional)
UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', '500'))  # ms

# Redis channels/streams
SUMMARY_CHANNEL = 'ui_summary'
EXEC_STREAM = 'execs'
POSITIONS_CHANNEL = 'positions'
ORDERS_CHANNEL = 'orders'

# Logging
setup_logging(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = get_logger(__name__)


class RedisSubscriber(QThread):
    """Redis pub/sub subscriber thread"""
    
    data_received = pyqtSignal(dict)
    
    def __init__(self, channel: str, redis_url: str):
        super().__init__()
        self.channel = channel
        self.redis_url = redis_url
        self.running = False
    
    def run(self):
        """Thread main loop"""
        asyncio.run(self._subscribe_loop())
    
    async def _subscribe_loop(self):
        """Redis subscribe loop"""
        r = await from_url(self.redis_url, decode_responses=True)
        pubsub = r.pubsub()
        
        try:
            await pubsub.subscribe(self.channel)
            self.running = True
            
            while self.running:
                try:
                    message = await pubsub.get_message(timeout=1.0)
                    if message and message['type'] == 'message':
                        try:
                            data = json.loads(message['data'])
                            self.data_received.emit(data)
                        except json.JSONDecodeError:
                            pass
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Redis subscribe error: {e}")
                    await asyncio.sleep(1)
        finally:
            await pubsub.unsubscribe(self.channel)
            await pubsub.close()
            await r.close()
    
    def stop(self):
        """Thread'i durdur"""
        self.running = False


class StreamReader(QThread):
    """Redis Stream reader thread"""
    
    data_received = pyqtSignal(dict)
    
    def __init__(self, stream: str, redis_url: str):
        super().__init__()
        self.stream = stream
        self.redis_url = redis_url
        self.running = False
        self.last_id = '0-0'
    
    def run(self):
        """Thread main loop"""
        asyncio.run(self._read_loop())
    
    async def _read_loop(self):
        """Redis stream read loop"""
        r = await from_url(self.redis_url, decode_responses=False)
        
        try:
            self.running = True
            
            while self.running:
                try:
                    msgs = await r.xread({self.stream: self.last_id}, count=10, block=1000)
                    
                    if msgs:
                        for stream, items in msgs:
                            for msg_id, data in items:
                                self.last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                                
                                # Decode data
                                decoded = {}
                                for k, v in data.items():
                                    key = k.decode() if isinstance(k, bytes) else k
                                    val = v.decode() if isinstance(v, bytes) else v
                                    decoded[key] = val
                                
                                self.data_received.emit(decoded)
                    
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Stream read error: {e}")
                    await asyncio.sleep(1)
        finally:
            await r.close()
    
    def stop(self):
        """Thread'i durdur"""
        self.running = False


class TradingTerminal(QWidget):
    """Main trading terminal window"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_data_sources()
        
        # Data storage
        self.positions: List[Dict] = []
        self.orders: List[Dict] = []
        self.executions: List[Dict] = []
        self.summary: Dict = {}
        
        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(UPDATE_INTERVAL)
    
    def init_ui(self):
        """UI'yi başlat"""
        self.setWindowTitle('Trading Terminal - PyQt Client')
        self.resize(1200, 800)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Status bar
        status_layout = QHBoxLayout()
        self.status_label = QLabel('Status: Connecting...')
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px;")
        status_layout.addWidget(self.status_label)
        
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.clicked.connect(self.manual_refresh)
        status_layout.addWidget(self.refresh_btn)
        
        main_layout.addLayout(status_layout)
        
        # Tabs
        tabs = QTabWidget()
        
        # Summary tab
        summary_widget = self.create_summary_tab()
        tabs.addTab(summary_widget, 'Summary')
        
        # Positions tab
        positions_widget = self.create_positions_tab()
        tabs.addTab(positions_widget, 'Positions')
        
        # Orders tab
        orders_widget = self.create_orders_tab()
        tabs.addTab(orders_widget, 'Orders')
        
        # Executions tab
        executions_widget = self.create_executions_tab()
        tabs.addTab(executions_widget, 'Executions')
        
        # Logs tab
        logs_widget = self.create_logs_tab()
        tabs.addTab(logs_widget, 'Logs')
        
        main_layout.addWidget(tabs)
        self.setLayout(main_layout)
    
    def create_summary_tab(self) -> QWidget:
        """Summary tab oluştur"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Summary text
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFont(QFont("Courier", 10))
        layout.addWidget(self.summary_text)
        
        widget.setLayout(layout)
        return widget
    
    def create_positions_tab(self) -> QWidget:
        """Positions tab oluştur"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Positions table
        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(6)
        self.positions_table.setHorizontalHeaderLabels([
            'Symbol', 'Quantity', 'Avg Cost', 'Market Price', 'P&L', 'Value'
        ])
        self.positions_table.setAlternatingRowColors(True)
        layout.addWidget(self.positions_table)
        
        widget.setLayout(layout)
        return widget
    
    def create_orders_tab(self) -> QWidget:
        """Orders tab oluştur"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Orders table
        self.orders_table = QTableWidget()
        self.orders_table.setColumnCount(6)
        self.orders_table.setHorizontalHeaderLabels([
            'Symbol', 'Action', 'Quantity', 'Price', 'Status', 'Filled'
        ])
        self.orders_table.setAlternatingRowColors(True)
        layout.addWidget(self.orders_table)
        
        widget.setLayout(layout)
        return widget
    
    def create_executions_tab(self) -> QWidget:
        """Executions tab oluştur"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Executions list
        self.executions_list = QListWidget()
        layout.addWidget(self.executions_list)
        
        widget.setLayout(layout)
        return widget
    
    def create_logs_tab(self) -> QWidget:
        """Logs tab oluştur"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Logs text
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setFont(QFont("Courier", 9))
        layout.addWidget(self.logs_text)
        
        widget.setLayout(layout)
        return widget
    
    def setup_data_sources(self):
        """Data source'ları başlat (Redis subscribers)"""
        # Summary subscriber
        self.summary_subscriber = RedisSubscriber(SUMMARY_CHANNEL, REDIS_URL)
        self.summary_subscriber.data_received.connect(self.on_summary_data)
        self.summary_subscriber.start()
        
        # Executions stream reader
        self.exec_reader = StreamReader(EXEC_STREAM, REDIS_URL)
        self.exec_reader.data_received.connect(self.on_execution_data)
        self.exec_reader.start()
        
        self.status_label.setText('Status: Connected')
        self.log_message("UI initialized, data sources connected")
    
    def on_summary_data(self, data: Dict):
        """Summary data callback"""
        self.summary = data
        self.update_summary_display()
    
    def on_execution_data(self, data: Dict):
        """Execution data callback"""
        self.executions.insert(0, data)
        if len(self.executions) > 1000:
            self.executions = self.executions[:1000]
        self.update_executions_display()
    
    def update_display(self):
        """Periodic display update"""
        self.update_summary_display()
        # Diğer tab'lar timer ile güncellenebilir
    
    def update_summary_display(self):
        """Summary display'i güncelle"""
        summary_text = "=== Trading System Summary ===\n\n"
        
        if self.summary:
            summary_text += f"Timestamp: {self.summary.get('ts', 'N/A')}\n"
            summary_text += f"Total Positions: {self.summary.get('total_positions', 0)}\n"
            summary_text += f"Total Orders: {self.summary.get('total_orders', 0)}\n"
            summary_text += f"Total P&L: ${self.summary.get('total_pnl', 0):.2f}\n"
            summary_text += f"Account Value: ${self.summary.get('account_value', 0):.2f}\n"
        else:
            summary_text += "No summary data available\n"
            summary_text += "Waiting for data from engine...\n"
        
        summary_text += f"\n=== System Status ===\n"
        summary_text += f"Executions received: {len(self.executions)}\n"
        summary_text += f"Last update: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        self.summary_text.setText(summary_text)
    
    def update_positions_display(self):
        """Positions table'ı güncelle"""
        self.positions_table.setRowCount(len(self.positions))
        
        for i, pos in enumerate(self.positions):
            self.positions_table.setItem(i, 0, QTableWidgetItem(pos.get('symbol', '')))
            self.positions_table.setItem(i, 1, QTableWidgetItem(str(pos.get('qty', 0))))
            self.positions_table.setItem(i, 2, QTableWidgetItem(f"${pos.get('avg_cost', 0):.2f}"))
            self.positions_table.setItem(i, 3, QTableWidgetItem(f"${pos.get('market_price', 0):.2f}"))
            self.positions_table.setItem(i, 4, QTableWidgetItem(f"${pos.get('unrealized_pnl', 0):.2f}"))
            self.positions_table.setItem(i, 5, QTableWidgetItem(f"${pos.get('market_value', 0):.2f}"))
    
    def update_orders_display(self):
        """Orders table'ı güncelle"""
        self.orders_table.setRowCount(len(self.orders))
        
        for i, order in enumerate(self.orders):
            self.orders_table.setItem(i, 0, QTableWidgetItem(order.get('symbol', '')))
            self.orders_table.setItem(i, 1, QTableWidgetItem(order.get('action', '')))
            self.orders_table.setItem(i, 2, QTableWidgetItem(str(order.get('quantity', 0))))
            self.orders_table.setItem(i, 3, QTableWidgetItem(f"${order.get('price', 0):.2f}"))
            self.orders_table.setItem(i, 4, QTableWidgetItem(order.get('status', '')))
            self.orders_table.setItem(i, 5, QTableWidgetItem(str(order.get('filled', 0))))
    
    def update_executions_display(self):
        """Executions list'i güncelle"""
        self.executions_list.clear()
        
        for exec_data in self.executions[:100]:  # Son 100 execution
            symbol = exec_data.get('symbol', 'N/A')
            status = exec_data.get('status', 'N/A')
            price = exec_data.get('price', '0')
            ts = exec_data.get('ts', '')
            
            item_text = f"[{ts}] {symbol} | {status} | ${price}"
            self.executions_list.addItem(item_text)
    
    def manual_refresh(self):
        """Manual refresh"""
        self.log_message("Manual refresh triggered")
        self.update_display()
    
    def log_message(self, message: str):
        """Log mesajı ekle"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"
        self.logs_text.append(log_entry)
    
    def closeEvent(self, event):
        """Window close event - cleanup"""
        self.summary_subscriber.stop()
        self.exec_reader.stop()
        self.timer.stop()
        event.accept()


def main():
    """Main entry point"""
    if not PYQT_AVAILABLE:
        print("PyQt5 not available. Install with: pip install PyQt5")
        sys.exit(1)
    
    app = QApplication(sys.argv)
    
    # Style
    app.setStyle('Fusion')
    
    window = TradingTerminal()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()








