"""
Janall Control Panel
====================
The main UI for the ported Janall mechanisms.
Features:
- Ticker Selection (from CSV or manual)
- Bulk Order Strategy Tagging (8 types)
- Tactical Execution Buttons
- Lot Size & Splitting Control
- Launch Orders Window
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import logging
from typing import List

from app.algo.janall_bulk_manager import JanallBulkOrderManager
from app.ui.janall_orders_window import JanallOrdersWindow
from app.psfalgo.execution_ledger import PSFALGOExecutionLedger

logger = logging.getLogger(__name__)

STRATEGY_TAGS = [
    "LT_LONG_INCREASE",
    "LT_SHORT_INCREASE",
    "LT_LONG_DECREASE",
    "LT_SHORT_DECREASE",
    "MM_LONG_INCREASE",
    "MM_SHORT_INCREASE",
    "MM_LONG_DECREASE",
    "MM_SHORT_DECREASE"
]

class JanallControlPanel(tk.Tk):
    def __init__(self, trading_client, market_data_service):
        super().__init__()
        self.title("Janall Port - Quant Engine")
        self.geometry("1100x700")
        
        self.trading_client = trading_client
        self.market_data = market_data_service
        self.ledger = PSFALGOExecutionLedger() # Initialize ledger
        
        self.bulk_manager = JanallBulkOrderManager(trading_client, market_data_service)
        
        self.selected_tickers = []
        self.df = pd.DataFrame()
        
        self.setup_ui()
        
    def setup_ui(self):
        # Top Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(toolbar, text="Load janalldata.csv", command=self.load_csv).pack(side='left', padx=5)
        ttk.Button(toolbar, text="Open Orders Window", command=self.open_orders_window).pack(side='left', padx=5)
        
        # Main Layout: Left (Ticker Grid), Right (Controls)
        main_pane = ttk.PanedWindow(self, orient='horizontal')
        main_pane.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Left: Ticker List
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=3)
        
        columns = ('select', 'ticker', 'bid', 'ask', 'last')
        self.tree = ttk.Treeview(left_frame, columns=columns, show='headings')
        self.tree.heading('select', text='[ ]', command=self.toggle_all_selection)
        self.tree.heading('ticker', text='Ticker')
        self.tree.heading('bid', text='Bid')
        self.tree.heading('ask', text='Ask')
        self.tree.heading('last', text='Last')
        
        self.tree.column('select', width=40, anchor='center')
        self.tree.column('ticker', width=80)
        self.tree.column('bid', width=60)
        self.tree.column('ask', width=60)
        self.tree.column('last', width=60)
        
        sb = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        
        self.tree.bind('<ButtonRelease-1>', self.on_tree_click)
        
        # Right: Operations
        right_frame = ttk.LabelFrame(main_pane, text="Bulk Operations")
        main_pane.add(right_frame, weight=1)
        
        # 1. Strategy Tag Selection (CRITICAL)
        tag_frame = ttk.LabelFrame(right_frame, text="1. Select Strategy Tag (Required)")
        tag_frame.pack(fill='x', padx=5, pady=10)
        
        self.strategy_var = tk.StringVar()
        self.strategy_combo = ttk.Combobox(tag_frame, textvariable=self.strategy_var, values=STRATEGY_TAGS, state="readonly")
        self.strategy_combo.pack(fill='x', padx=5, pady=5)
        self.strategy_combo.set(STRATEGY_TAGS[0]) # Default
        
        # 2. Lot Size & Settings
        settings_frame = ttk.LabelFrame(right_frame, text="2. Settings")
        settings_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Label(settings_frame, text="Total Lots:").pack(side='left', padx=5)
        self.lot_entry = ttk.Entry(settings_frame, width=8)
        self.lot_entry.pack(side='left', padx=5)
        self.lot_entry.insert(0, "500")
        
        self.divider_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Smart Divider (>399)", variable=self.divider_var, command=self.toggle_divider).pack(side='left', padx=5)
        
        # 3. Execution Buttons (Tactical)
        exec_frame = ttk.LabelFrame(right_frame, text="3. Execute Bulk Order")
        exec_frame.pack(fill='x', padx=5, pady=10)
        
        # Grid layout for buttons
        btn_grid = ttk.Frame(exec_frame)
        btn_grid.pack(padding=5)
        
        # Buy Buttons
        ttk.Button(btn_grid, text="Bid Buy (+0.15 spr)", command=lambda: self.execute_bulk('bid_buy')).grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(btn_grid, text="Front Buy (Last+0.01)", command=lambda: self.execute_bulk('front_buy')).grid(row=0, column=1, padx=2, pady=2)
        ttk.Button(btn_grid, text="Ask Buy (Ask+0.01)", command=lambda: self.execute_bulk('ask_buy')).grid(row=0, column=2, padx=2, pady=2)
        ttk.Button(btn_grid, text="Soft Front Buy", command=lambda: self.execute_bulk('soft_front_buy')).grid(row=0, column=3, padx=2, pady=2)
        
        # Sell Buttons
        ttk.Button(btn_grid, text="Bid Sell (Bid-0.01)", command=lambda: self.execute_bulk('bid_sell')).grid(row=1, column=0, padx=2, pady=2)
        ttk.Button(btn_grid, text="Front Sell (Last-0.01)", command=lambda: self.execute_bulk('front_sell')).grid(row=1, column=1, padx=2, pady=2)
        ttk.Button(btn_grid, text="Ask Sell (-0.15 spr)", command=lambda: self.execute_bulk('ask_sell')).grid(row=1, column=2, padx=2, pady=2)
        ttk.Button(btn_grid, text="Soft Front Sell", command=lambda: self.execute_bulk('soft_front_sell')).grid(row=1, column=3, padx=2, pady=2)

        # Log Area
        log_frame = ttk.LabelFrame(right_frame, text="Logs")
        log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.log_text = tk.Text(log_frame, height=10, width=40)
        self.log_text.pack(fill='both', expand=True)

    def log(self, message):
        self.log_text.insert('end', message + "\n")
        self.log_text.see('end')
        logger.info(message)

    def load_csv(self):
        try:
            # Try default path
            path = "c:/StockTracker/janall/janalldata.csv"
            self.df = pd.read_csv(path)
            
            # Clear tree
            self.tree.delete(*self.tree.get_children())
            
            # Populate
            # Assuming 'PREF IBKR' column exists
            if 'PREF IBKR' in self.df.columns:
                tickers = self.df['PREF IBKR'].dropna().unique()
                for t in tickers:
                    self.tree.insert('', 'end', values=('☐', t, '-', '-', '-'))
                self.log(f"Loaded {len(tickers)} tickers from {path}")
            else:
                self.log("Error: 'PREF IBKR' column not found in CSV")
                
        except Exception as e:
            self.log(f"Error loading CSV: {e}")
            messagebox.showerror("Error", str(e))

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "heading":
            return
        col = self.tree.identify_column(event.x)
        if col == '#1':
            item_id = self.tree.identify_row(event.y)
            if item_id:
                vals = list(self.tree.item(item_id, 'values'))
                vals[0] = '☑' if vals[0] == '☐' else '☐'
                self.tree.item(item_id, values=vals)

    def toggle_all_selection(self):
        # Identify current state of first item
        children = self.tree.get_children()
        if not children: return
        
        first_val = self.tree.item(children[0], 'values')[0]
        new_val = '☑' if first_val == '☐' else '☐'
        
        for item in children:
            vals = list(self.tree.item(item, 'values'))
            vals[0] = new_val
            self.tree.item(item, values=vals)

    def get_selected_tickers(self):
        selected = []
        for item in self.tree.get_children():
            vals = self.tree.item(item, 'values')
            if vals[0] == '☑':
                selected.append(vals[1])
        return selected

    def toggle_divider(self):
        self.bulk_manager.toggle_lot_divider(self.divider_var.get())

    def execute_bulk(self, order_type):
        tickers = self.get_selected_tickers()
        if not tickers:
            messagebox.showwarning("Warning", "No tickers selected")
            return
            
        try:
            total_lot = int(self.lot_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid Lot Size")
            return

        strategy_tag = self.strategy_var.get()
        if not strategy_tag:
            messagebox.showerror("Error", "Please select a Strategy Tag")
            return

        confirm = messagebox.askyesno(
            "Confirm Bulk Order",
            f"Send {order_type} for {len(tickers)} tickers?\nTag: {strategy_tag}\nTotal Lot: {total_lot}"
        )
        if not confirm:
            return

        self.log(f"Executing {order_type} for {len(tickers)} tickers...")
        
        # Execute via Manager
        results = self.bulk_manager.execute_bulk_orders(
            tickers=tickers,
            order_type=order_type,
            total_lot=total_lot,
            strategy_tag=strategy_tag,
            ledger=self.ledger
        )
        
        # Log results
        for res in results:
            self.log(f"{res['ticker']}: {res['status']}")
            
        self.log("Bulk execution completed.")

    def open_orders_window(self):
        JanallOrdersWindow(self, self.trading_client, self.bulk_manager)

if __name__ == "__main__":
    # Test stub
    root = JanallControlPanel(None, None)
    root.mainloop()
