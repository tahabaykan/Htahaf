import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional
import json
import os

class HammerProDialog(tk.Toplevel):
    """Dialog for Hammer Pro connection settings"""
    
    def __init__(self, parent, on_connect: Optional[Callable] = None):
        super().__init__(parent)
        self.on_connect = on_connect
        self.result = None
        
        # Window setup
        self.title("Hammer Pro Bağlantı Ayarları")
        self.geometry("400x350")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.center_window()
        
        # Load config
        self.config = self.load_config()
        
        # Setup UI
        self.setup_ui()
        
        # Load current config
        self.load_current_config()
    
    def center_window(self):
        """Center the window on screen"""
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.winfo_screenheight() // 2) - (350 // 2)
        self.geometry(f"400x350+{x}+{y}")
    
    def load_config(self):
        """Load configuration from file"""
        config_file = "hammer_pro_config.json"
        default_config = {
            'host': '127.0.0.1',
            'port': 8080,
            'password': '',
            'streamer_id': 'AMTD'
        }
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except:
                return default_config
        return default_config
    
    def save_config(self):
        """Save configuration to file"""
        config_file = "hammer_pro_config.json"
        config = {
            'host': self.host_var.get(),
            'port': int(self.port_var.get()),
            'password': self.password_var.get(),
            'streamer_id': self.streamer_var.get()
        }
        
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            messagebox.showerror("Hata", f"Konfigürasyon kaydedilemedi: {e}")
    
    def setup_ui(self):
        """Setup the user interface"""
        # Main frame
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="Hammer Pro Bağlantı Ayarları", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 20))
        
        # Connection settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Bağlantı Ayarları", padding="10")
        settings_frame.pack(fill="x", pady=(0, 20))
        
        # Host
        ttk.Label(settings_frame, text="Host:").grid(row=0, column=0, sticky="w", pady=5)
        self.host_var = tk.StringVar(value=self.config['host'])
        host_entry = ttk.Entry(settings_frame, textvariable=self.host_var, width=20)
        host_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Port
        ttk.Label(settings_frame, text="Port:").grid(row=1, column=0, sticky="w", pady=5)
        self.port_var = tk.StringVar(value=str(self.config['port']))
        port_entry = ttk.Entry(settings_frame, textvariable=self.port_var, width=20)
        port_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Password
        ttk.Label(settings_frame, text="Şifre:").grid(row=2, column=0, sticky="w", pady=5)
        self.password_var = tk.StringVar(value=self.config['password'])
        password_entry = ttk.Entry(settings_frame, textvariable=self.password_var, 
                                 show="*", width=20)
        password_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Streamer ID
        ttk.Label(settings_frame, text="Streamer ID:").grid(row=3, column=0, sticky="w", pady=5)
        self.streamer_var = tk.StringVar(value=self.config['streamer_id'])
        streamer_entry = ttk.Entry(settings_frame, textvariable=self.streamer_var, width=20)
        streamer_entry.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Configure grid weights
        settings_frame.columnconfigure(1, weight=1)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill="x", pady=(0, 10))
        
        # Test connection button
        self.test_btn = ttk.Button(buttons_frame, text="Bağlantıyı Test Et", 
                                  command=self.test_connection)
        self.test_btn.pack(side="left", padx=(0, 10))
        
        # Connect button
        self.connect_btn = ttk.Button(buttons_frame, text="Bağlan", 
                                    command=self.connect_hammer_pro)
        self.connect_btn.pack(side="left", padx=(0, 10))
        
        # Cancel button
        cancel_btn = ttk.Button(buttons_frame, text="İptal", command=self.cancel)
        cancel_btn.pack(side="right")
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="", font=("Arial", 10))
        self.status_label.pack(pady=(10, 0))
    
    def load_current_config(self):
        """Load current configuration into UI"""
        self.host_var.set(self.config['host'])
        self.port_var.set(str(self.config['port']))
        self.password_var.set(self.config['password'])
        self.streamer_var.set(self.config['streamer_id'])
    
    def test_connection(self):
        """Test Hammer Pro connection"""
        try:
            from data.hammer_pro_client import HammerProClient
            
            host = self.host_var.get()
            port = int(self.port_var.get())
            password = self.password_var.get()
            
            self.status_label.config(text="Bağlantı test ediliyor...", foreground="blue")
            self.update()
            
            # Create test client
            client = HammerProClient(host, port, password)
            
            # Try to connect
            if client.connect():
                self.status_label.config(text="✅ Bağlantı başarılı!", foreground="green")
                client.disconnect()
            else:
                self.status_label.config(text="❌ Bağlantı başarısız!", foreground="red")
                
        except Exception as e:
            self.status_label.config(text=f"❌ Hata: {str(e)}", foreground="red")
    
    def connect_hammer_pro(self):
        """Connect to Hammer Pro with current settings"""
        try:
            # Validate inputs
            host = self.host_var.get().strip()
            if not host:
                messagebox.showerror("Hata", "Host adresi boş olamaz!")
                return
            
            try:
                port = int(self.port_var.get())
                if port <= 0 or port > 65535:
                    raise ValueError("Port geçersiz")
            except ValueError:
                messagebox.showerror("Hata", "Port numarası geçerli değil!")
                return
            
            password = self.password_var.get()
            streamer_id = self.streamer_var.get().strip()
            
            if not streamer_id:
                messagebox.showerror("Hata", "Streamer ID boş olamaz!")
                return
            
            # Save configuration
            self.save_config()
            
            # Return connection parameters
            self.result = {
                'host': host,
                'port': port,
                'password': password,
                'streamer_id': streamer_id
            }
            
            # Call callback if provided
            if self.on_connect:
                self.on_connect(self.result)
            
            self.destroy()
            
        except Exception as e:
            messagebox.showerror("Hata", f"Bağlantı hatası: {str(e)}")
    
    def cancel(self):
        """Cancel dialog"""
        self.result = None
        self.destroy() 