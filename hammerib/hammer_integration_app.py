import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging
from datetime import datetime
import pandas as pd

from hammer_pro_client import HammerProClient
from final_bb_integration import FinalBBScoreCalculator, HammerWatchlistManager

class HammerIntegrationApp:
    """
    Main application for Hammer Pro integration with FINAL BB scoring
    """
    
    def __init__(self):
        self.setup_logging()
        
        # Initialize Hammer Pro client
        self.hammer_client = HammerProClient(
            host="127.0.0.1",
            port=8080,  # Update with your Hammer Pro API port
            password="your_password"  # Update with your Hammer Pro password
        )
        
        # Initialize scoring and watchlist managers
        self.score_calculator = FinalBBScoreCalculator(self.hammer_client)
        self.watchlist_manager = HammerWatchlistManager(self.hammer_client)
        
        # Setup GUI
        self.setup_gui()
        
        # Connection status
        self.connected = False
        
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('hammer_integration.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_gui(self):
        """Setup the main GUI"""
        self.root = tk.Tk()
        self.root.title("Hammer Pro FINAL BB Integration")
        self.root.geometry("1200x800")
        
        # Create main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create tabs
        self.setup_connection_tab()
        self.setup_scoring_tab()
        self.setup_watchlist_tab()
        self.setup_trading_tab()
        
    def setup_connection_tab(self):
        """Setup connection management tab"""
        connection_frame = ttk.Frame(self.notebook)
        self.notebook.add(connection_frame, text="Connection")
        
        # Connection controls
        ttk.Label(connection_frame, text="Hammer Pro Connection", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Connection frame
        conn_frame = ttk.LabelFrame(connection_frame, text="Connection Settings")
        conn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, padx=5, pady=5)
        self.host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(conn_frame, textvariable=self.host_var).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(conn_frame, text="Port:").grid(row=1, column=0, padx=5, pady=5)
        self.port_var = tk.StringVar(value="8080")
        ttk.Entry(conn_frame, textvariable=self.port_var).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(conn_frame, text="Password:").grid(row=2, column=0, padx=5, pady=5)
        self.password_var = tk.StringVar()
        ttk.Entry(conn_frame, textvariable=self.password_var, show="*").grid(row=2, column=1, padx=5, pady=5)
        
        # Connection buttons
        btn_frame = ttk.Frame(connection_frame)
        btn_frame.pack(pady=10)
        
        self.connect_btn = ttk.Button(btn_frame, text="Connect to Hammer Pro", command=self.connect_to_hammer)
        self.connect_btn.pack(side='left', padx=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="Disconnect", command=self.disconnect_from_hammer, state='disabled')
        self.disconnect_btn.pack(side='left', padx=5)
        
        # Status
        self.status_label = ttk.Label(connection_frame, text="Status: Disconnected", foreground="red")
        self.status_label.pack(pady=10)
        
    def setup_scoring_tab(self):
        """Setup FINAL BB scoring tab"""
        scoring_frame = ttk.Frame(self.notebook)
        self.notebook.add(scoring_frame, text="FINAL BB Scoring")
        
        ttk.Label(scoring_frame, text="FINAL BB Score Management", font=("Arial", 14, "bold")).pack(pady=10)
        
        # CSV data loading
        csv_frame = ttk.LabelFrame(scoring_frame, text="CSV Data Loading")
        csv_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(csv_frame, text="SSFI CSV File:").pack(anchor='w', padx=5, pady=2)
        self.csv_var = tk.StringVar(value="ssfinekheldkuponlu.csv")
        ttk.Entry(csv_frame, textvariable=self.csv_var, width=50).pack(fill='x', padx=5, pady=2)
        
        ttk.Button(csv_frame, text="Load CSV Data", command=self.load_csv_data).pack(pady=5)
        
        # Score calculation
        calc_frame = ttk.LabelFrame(scoring_frame, text="Score Calculation")
        calc_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(calc_frame, text="Calculate All FINAL BB Scores", command=self.calculate_all_scores).pack(pady=5)
        ttk.Button(calc_frame, text="Create Score-Based Watchlists", command=self.create_score_watchlists).pack(pady=5)
        
        # Score display
        score_frame = ttk.LabelFrame(scoring_frame, text="Score Results")
        score_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Create treeview for scores
        columns = ('Symbol', 'FINAL_THG', 'FINAL_BB_Score', 'Rank')
        self.score_tree = ttk.Treeview(score_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.score_tree.heading(col, text=col)
            self.score_tree.column(col, width=100)
            
        self.score_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Scrollbar
        score_scrollbar = ttk.Scrollbar(score_frame, orient='vertical', command=self.score_tree.yview)
        score_scrollbar.pack(side='right', fill='y')
        self.score_tree.configure(yscrollcommand=score_scrollbar.set)
        
    def setup_watchlist_tab(self):
        """Setup watchlist management tab"""
        watchlist_frame = ttk.Frame(self.notebook)
        self.notebook.add(watchlist_frame, text="Watchlists")
        
        ttk.Label(watchlist_frame, text="Watchlist Management", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Watchlist controls
        wl_frame = ttk.LabelFrame(watchlist_frame, text="Watchlist Operations")
        wl_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(wl_frame, text="Setup Auto Watchlists", command=self.setup_auto_watchlists).pack(pady=5)
        ttk.Button(wl_frame, text="Refresh All Watchlists", command=self.refresh_watchlists).pack(pady=5)
        
        # Watchlist display
        wl_display_frame = ttk.LabelFrame(watchlist_frame, text="Active Watchlists")
        wl_display_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Create treeview for watchlists
        wl_columns = ('Watchlist Name', 'Symbol Count', 'Last Updated')
        self.watchlist_tree = ttk.Treeview(wl_display_frame, columns=wl_columns, show='headings', height=15)
        
        for col in wl_columns:
            self.watchlist_tree.heading(col, text=col)
            self.watchlist_tree.column(col, width=150)
            
        self.watchlist_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
    def setup_trading_tab(self):
        """Setup trading operations tab"""
        trading_frame = ttk.Frame(self.notebook)
        self.notebook.add(trading_frame, text="Trading")
        
        ttk.Label(trading_frame, text="Trading Operations", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Trading account management
        account_frame = ttk.LabelFrame(trading_frame, text="Trading Account")
        account_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(account_frame, text="Get Trading Accounts", command=self.get_trading_accounts).pack(pady=5)
        ttk.Button(account_frame, text="Start Trading Account", command=self.start_trading_account).pack(pady=5)
        
        # Order management
        order_frame = ttk.LabelFrame(trading_frame, text="Order Management")
        order_frame.pack(fill='x', padx=10, pady=5)
        
        # Order entry
        ttk.Label(order_frame, text="Symbol:").grid(row=0, column=0, padx=5, pady=5)
        self.order_symbol_var = tk.StringVar()
        ttk.Entry(order_frame, textvariable=self.order_symbol_var).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(order_frame, text="Quantity:").grid(row=1, column=0, padx=5, pady=5)
        self.order_qty_var = tk.StringVar()
        ttk.Entry(order_frame, textvariable=self.order_qty_var).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(order_frame, text="Action:").grid(row=2, column=0, padx=5, pady=5)
        self.order_action_var = tk.StringVar(value="Buy")
        ttk.Combobox(order_frame, textvariable=self.order_action_var, values=["Buy", "Sell"]).grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(order_frame, text="Order Type:").grid(row=3, column=0, padx=5, pady=5)
        self.order_type_var = tk.StringVar(value="Limit")
        ttk.Combobox(order_frame, textvariable=self.order_type_var, values=["Market", "Limit"]).grid(row=3, column=1, padx=5, pady=5)
        
        ttk.Label(order_frame, text="Limit Price:").grid(row=4, column=0, padx=5, pady=5)
        self.order_price_var = tk.StringVar()
        ttk.Entry(order_frame, textvariable=self.order_price_var).grid(row=4, column=1, padx=5, pady=5)
        
        ttk.Button(order_frame, text="Place Order", command=self.place_order).grid(row=5, column=0, columnspan=2, pady=10)
        
    async def connect_to_hammer_async(self):
        """Async connection to Hammer Pro"""
        try:
            # Update client settings
            self.hammer_client.ws_url = f"ws://{self.host_var.get()}:{self.port_var.get()}"
            self.hammer_client.password = self.password_var.get()
            
            await self.hammer_client.connect()
            self.connected = self.hammer_client.connected
            
            if self.connected:
                self.logger.info("Successfully connected to Hammer Pro")
                # Setup message handlers
                self.setup_message_handlers()
                
        except Exception as e:
            self.logger.error(f"Failed to connect to Hammer Pro: {e}")
            self.connected = False
            
    def connect_to_hammer(self):
        """Connect to Hammer Pro (threaded)"""
        def connect_thread():
            asyncio.run(self.connect_to_hammer_async())
            
        threading.Thread(target=connect_thread, daemon=True).start()
        
        # Update UI
        self.connect_btn.config(state='disabled')
        self.disconnect_btn.config(state='normal')
        self.status_label.config(text="Status: Connecting...", foreground="orange")
        
        # Check connection status after a delay
        self.root.after(2000, self.check_connection_status)
        
    def check_connection_status(self):
        """Check and update connection status"""
        if self.connected:
            self.status_label.config(text="Status: Connected", foreground="green")
        else:
            self.status_label.config(text="Status: Connection Failed", foreground="red")
            self.connect_btn.config(state='normal')
            self.disconnect_btn.config(state='disabled')
            
    async def disconnect_from_hammer_async(self):
        """Async disconnect from Hammer Pro"""
        try:
            await self.hammer_client.close()
            self.connected = False
            self.logger.info("Disconnected from Hammer Pro")
        except Exception as e:
            self.logger.error(f"Error disconnecting: {e}")
            
    def disconnect_from_hammer(self):
        """Disconnect from Hammer Pro (threaded)"""
        def disconnect_thread():
            asyncio.run(self.disconnect_from_hammer_async())
            
        threading.Thread(target=disconnect_thread, daemon=True).start()
        
        # Update UI
        self.connect_btn.config(state='normal')
        self.disconnect_btn.config(state='disabled')
        self.status_label.config(text="Status: Disconnected", foreground="red")
        
    def setup_message_handlers(self):
        """Setup message handlers for Hammer Pro"""
        # Handle L1 updates
        self.hammer_client.register_handler("L1Update", self.handle_l1_update)
        
        # Handle portfolio updates
        self.hammer_client.register_handler("enumPorts", self.handle_portfolios_update)
        
        # Handle symbol snapshots
        self.hammer_client.register_handler("getSymbolSnapshot", self.handle_symbol_snapshot)
        
    async def handle_l1_update(self, data):
        """Handle L1 market data updates"""
        symbol = data.get('result', {}).get('sym', '')
        if symbol:
            self.logger.debug(f"L1 Update for {symbol}: {data}")
            
    async def handle_portfolios_update(self, data):
        """Handle portfolio list updates"""
        portfolios = data.get('result', {}).get('ports', [])
        self.logger.info(f"Portfolios updated: {len(portfolios)} portfolios")
        
    async def handle_symbol_snapshot(self, data):
        """Handle symbol snapshot updates"""
        symbol = data.get('result', {}).get('sym', '')
        if symbol:
            self.hammer_client.market_data[symbol] = data.get('result', {})
            
    def load_csv_data(self):
        """Load CSV data for scoring"""
        csv_path = self.csv_var.get()
        try:
            self.score_calculator.load_ssfi_data(csv_path)
            messagebox.showinfo("Success", f"Loaded CSV data from {csv_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load CSV data: {e}")
            
    def calculate_all_scores(self):
        """Calculate all FINAL BB scores"""
        def calc_thread():
            async def calculate():
                try:
                    # Get symbols from loaded CSV
                    if self.score_calculator.ssfi_data is not None:
                        symbols = self.score_calculator.ssfi_data['PREF IBKR'].dropna().unique().tolist()
                        scores = await self.score_calculator.calculate_all_scores(symbols)
                        
                        # Update GUI with results
                        self.update_score_display(scores)
                        
                except Exception as e:
                    self.logger.error(f"Error calculating scores: {e}")
                    
            asyncio.run(calculate())
            
        threading.Thread(target=calc_thread, daemon=True).start()
        
    def update_score_display(self, scores):
        """Update the score display treeview"""
        # Clear existing items
        for item in self.score_tree.get_children():
            self.score_tree.delete(item)
            
        # Add new scores
        for i, (symbol, score) in enumerate(sorted(scores, key=lambda x: x[1], reverse=True)):
            # Get FINAL_THG from CSV data
            final_thg = 0
            if self.score_calculator.ssfi_data is not None:
                symbol_data = self.score_calculator.ssfi_data[self.score_calculator.ssfi_data['PREF IBKR'] == symbol]
                if not symbol_data.empty:
                    final_thg = symbol_data.iloc[0].get('FINAL_THG', 0)
                    
            self.score_tree.insert('', 'end', values=(symbol, final_thg, f"{score:.2f}", i+1))
            
    def create_score_watchlists(self):
        """Create score-based watchlists"""
        def create_thread():
            async def create():
                try:
                    watchlists = await self.score_calculator.create_score_based_watchlists()
                    messagebox.showinfo("Success", f"Created {len(watchlists)} watchlists")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create watchlists: {e}")
                    
            asyncio.run(create())
            
        threading.Thread(target=create_thread, daemon=True).start()
        
    def setup_auto_watchlists(self):
        """Setup automatic watchlists"""
        def setup_thread():
            async def setup():
                try:
                    await self.watchlist_manager.setup_auto_watchlists()
                    messagebox.showinfo("Success", "Auto watchlists setup complete")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to setup auto watchlists: {e}")
                    
            asyncio.run(setup())
            
        threading.Thread(target=setup_thread, daemon=True).start()
        
    def refresh_watchlists(self):
        """Refresh all watchlists"""
        def refresh_thread():
            async def refresh():
                try:
                    # This would update all watchlists with new scores
                    await self.score_calculator.create_final_bb_watchlist()
                    messagebox.showinfo("Success", "Watchlists refreshed")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to refresh watchlists: {e}")
                    
            asyncio.run(refresh())
            
        threading.Thread(target=refresh_thread, daemon=True).start()
        
    def get_trading_accounts(self):
        """Get available trading accounts"""
        def get_thread():
            async def get():
                try:
                    accounts = await self.hammer_client.get_trading_accounts()
                    messagebox.showinfo("Trading Accounts", f"Found {len(accounts)} accounts")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to get trading accounts: {e}")
                    
            asyncio.run(get())
            
        threading.Thread(target=get_thread, daemon=True).start()
        
    def start_trading_account(self):
        """Start trading account"""
        # This would need account selection UI
        messagebox.showinfo("Info", "Please implement account selection")
        
    def place_order(self):
        """Place a trading order"""
        def place_thread():
            async def place():
                try:
                    symbol = self.order_symbol_var.get()
                    quantity = int(self.order_qty_var.get())
                    action = self.order_action_var.get()
                    order_type = self.order_type_var.get()
                    limit_price = float(self.order_price_var.get()) if self.order_price_var.get() else None
                    
                    # This would need account selection
                    account_key = "YOUR_ACCOUNT_KEY"  # Get from UI
                    
                    await self.hammer_client.place_order(
                        account_key, symbol, quantity, action, order_type, limit_price
                    )
                    
                    messagebox.showinfo("Success", f"Order placed for {symbol}")
                    
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to place order: {e}")
                    
            asyncio.run(place())
            
        threading.Thread(target=place_thread, daemon=True).start()
        
    def run(self):
        """Run the application"""
        self.root.mainloop()
        
    def close(self):
        """Close the application"""
        if self.connected:
            asyncio.run(self.hammer_client.close())
        self.root.destroy()

if __name__ == "__main__":
    app = HammerIntegrationApp()
    try:
        app.run()
    except KeyboardInterrupt:
        app.close() 