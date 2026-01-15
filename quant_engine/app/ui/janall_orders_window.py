"""
Janall Orders Window
====================
Replicates the 'My Orders' window from Janall.
Features:
- 'Pending' tab with Checkbox selection
- 'Select All', 'Cancel Selected'
- 'Completed' tab
- Auto-refresh
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class JanallOrdersWindow(tk.Toplevel):
    def __init__(self, parent, trading_client, bulk_manager):
        super().__init__(parent)
        self.title("Orders (Janall Style)")
        self.geometry("1000x600")
        
        self.trading_client = trading_client
        self.bulk_manager = bulk_manager
        
        self.setup_ui()
        self.refresh_timer_id = None
        self.start_auto_refresh()

    def setup_ui(self):
        # Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.pending_frame = ttk.Frame(self.notebook)
        self.completed_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.pending_frame, text="Pending Orders")
        self.notebook.add(self.completed_frame, text="Completed")
        
        self.setup_pending_tab()
        self.setup_completed_tab()

    def setup_pending_tab(self):
        # Toolbar
        toolbar = ttk.Frame(self.pending_frame)
        toolbar.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(toolbar, text="Refresh", command=self.refresh_orders).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Select All", command=self.select_all).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Deselect All", command=self.deselect_all).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Cancel Selected", command=self.cancel_selected, style='Danger.TButton').pack(side='left', padx=10)
        
        # Grid
        columns = ('select', 'id', 'symbol', 'action', 'qty', 'filled', 'price', 'status', 'time')
        self.pending_tree = ttk.Treeview(self.pending_frame, columns=columns, show='headings')
        
        self.pending_tree.heading('select', text='[x]')
        self.pending_tree.heading('id', text='Order ID')
        self.pending_tree.heading('symbol', text='Symbol')
        self.pending_tree.heading('action', text='Side')
        self.pending_tree.heading('qty', text='Qty')
        self.pending_tree.heading('filled', text='Filled')
        self.pending_tree.heading('price', text='Price')
        self.pending_tree.heading('status', text='Status')
        self.pending_tree.heading('time', text='Time')
        
        self.pending_tree.column('select', width=40, anchor='center')
        self.pending_tree.column('id', width=80)
        self.pending_tree.column('symbol', width=80)
        self.pending_tree.column('action', width=60)
        self.pending_tree.column('qty', width=60)
        
        # Scrollbar
        sb = ttk.Scrollbar(self.pending_frame, orient="vertical", command=self.pending_tree.yview)
        self.pending_tree.configure(yscrollcommand=sb.set)
        
        self.pending_tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        
        # Click handler for checkbox
        self.pending_tree.bind('<ButtonRelease-1>', self.on_tree_click)

    def setup_completed_tab(self):
        # Similar grid but read-only
        columns = ('symbol', 'action', 'filled', 'price', 'time', 'value')
        self.completed_tree = ttk.Treeview(self.completed_frame, columns=columns, show='headings')
        
        for col in columns:
            self.completed_tree.heading(col, text=col.title())
            
        self.completed_tree.pack(fill='both', expand=True)

    def on_tree_click(self, event):
        region = self.pending_tree.identify("region", event.x, event.y)
        if region == "heading":
            return
            
        col = self.pending_tree.identify_column(event.x)
        # Assuming 'select' is the first column #1
        if col == '#1':
            item_id = self.pending_tree.identify_row(event.y)
            if item_id:
                current_vals = self.pending_tree.item(item_id, 'values')
                # Toggle check
                new_check = '☐' if current_vals[0] == '☑' else '☑'
                new_vals = list(current_vals)
                new_vals[0] = new_check
                self.pending_tree.item(item_id, values=new_vals)

    def select_all(self):
        for item_id in self.pending_tree.get_children():
            vals = list(self.pending_tree.item(item_id, 'values'))
            vals[0] = '☑'
            self.pending_tree.item(item_id, values=vals)

    def deselect_all(self):
        for item_id in self.pending_tree.get_children():
            vals = list(self.pending_tree.item(item_id, 'values'))
            vals[0] = '☐'
            self.pending_tree.item(item_id, values=vals)

    def refresh_orders(self):
        # Fetch from client (assuming methods exist or need adaptation)
        try:
            # We assume trading_client has get_open_orders()
            orders = self.trading_client.get_open_orders()
            
            # Preserve selection state if possible? 
            # For simplicity in V1, we clear. In V2, we can map IDs.
            self.pending_tree.delete(*self.pending_tree.get_children())
            
            for o in orders:
                vals = (
                    '☐',
                    o.get('order_id', ''),
                    o.get('symbol', ''),
                    o.get('action', ''),
                    o.get('qty', 0),
                    o.get('filled', 0),
                    o.get('price', 0),
                    o.get('status', 'Open'),
                    o.get('time', '')
                )
                self.pending_tree.insert('', 'end', values=vals)
                
            # Completed orders
            fills = self.trading_client.get_todays_filled_orders()
            self.completed_tree.delete(*self.completed_tree.get_children())
            for f in fills:
                 # Calculate value
                price = f.get('price', 0)
                qty = f.get('qty', 0)
                value = price * qty
                vals = (
                    f.get('symbol', ''),
                    f.get('action', ''),
                    qty,
                    price,
                    f.get('time', ''),
                    f"{value:.2f}"
                )
                self.completed_tree.insert('', 'end', values=vals)

        except Exception as e:
            logger.error(f"Refresh failed: {e}")

    def start_auto_refresh(self):
        self.refresh_orders()
        self.refresh_timer_id = self.after(5000, self.start_auto_refresh)

    def cancel_selected(self):
        selected_ids = []
        selected_items = []
        
        for item_id in self.pending_tree.get_children():
            vals = self.pending_tree.item(item_id, 'values')
            if vals[0] == '☑':
                selected_ids.append(vals[1]) # Order ID
                selected_items.append(item_id)
                
        if not selected_ids:
            messagebox.showinfo("Info", "No orders selected.")
            return
            
        confirm = messagebox.askyesno("Confirm", f"Cancel {len(selected_ids)} orders?")
        if not confirm:
            return
            
        success_count = 0
        for oid in selected_ids:
            try:
                # Call backend cancel logic
                # Support both Native and Insync implicitly via client adapter
                if self.trading_client.cancel_order(oid):
                    success_count += 1
            except Exception as e:
                logger.error(f"Cancel failed for {oid}: {e}")
                
        messagebox.showinfo("Result", f"Sent cancel request for {success_count} orders.")
        # Trigger immediate refresh
        self.after(500, self.refresh_orders)
