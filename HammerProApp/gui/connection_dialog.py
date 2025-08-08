import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

class ConnectionDialog(tk.Toplevel):
    """Dialog for Hammer Pro connection settings"""
    
    def __init__(self, parent, config, on_connect: Optional[Callable] = None):
        super().__init__(parent)
        self.config = config
        self.on_connect = on_connect
        self.result = None
        
        # Window setup
        self.title("Hammer Pro Bağlantı Ayarları")
        self.geometry("400x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.center_window()
        
        # Setup UI
        self.setup_ui()
        
        # Load current config
        self.load_config()
    
    def center_window(self):
        """Center the dialog on screen"""
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.winfo_screenheight() // 2) - (300 // 2)
        self.geometry(f"400x300+{x}+{y}")
    
    def setup_ui(self):
        """Setup the dialog UI"""
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
        self.host_var = tk.StringVar()
        self.host_entry = ttk.Entry(settings_frame, textvariable=self.host_var, width=30)
        self.host_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Port
        ttk.Label(settings_frame, text="Port:").grid(row=1, column=0, sticky="w", pady=5)
        self.port_var = tk.StringVar()
        self.port_entry = ttk.Entry(settings_frame, textvariable=self.port_var, width=30)
        self.port_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Password
        ttk.Label(settings_frame, text="Şifre:").grid(row=2, column=0, sticky="w", pady=5)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(settings_frame, textvariable=self.password_var, 
                                      show="*", width=30)
        self.password_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Streamer ID
        ttk.Label(settings_frame, text="Streamer ID:").grid(row=3, column=0, sticky="w", pady=5)
        self.streamer_var = tk.StringVar()
        self.streamer_entry = ttk.Entry(settings_frame, textvariable=self.streamer_var, width=30)
        self.streamer_entry.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Configure grid weights
        settings_frame.columnconfigure(1, weight=1)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(0, 10))
        
        # Test connection button
        self.test_btn = ttk.Button(button_frame, text="Bağlantıyı Test Et", 
                                  command=self.test_connection)
        self.test_btn.pack(side="left", padx=(0, 10))
        
        # Connect button
        self.connect_btn = ttk.Button(button_frame, text="Bağlan", 
                                    command=self.connect)
        self.connect_btn.pack(side="left", padx=(0, 10))
        
        # Save button
        self.save_btn = ttk.Button(button_frame, text="Ayarları Kaydet", 
                                  command=self.save_settings)
        self.save_btn.pack(side="left", padx=(0, 10))
        
        # Cancel button
        self.cancel_btn = ttk.Button(button_frame, text="İptal", 
                                   command=self.cancel)
        self.cancel_btn.pack(side="right")
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="", font=("Arial", 10))
        self.status_label.pack(pady=(10, 0))
    
    def load_config(self):
        """Load current configuration"""
        hammer_config = self.config.get_hammer_pro_config()
        
        self.host_var.set(hammer_config.get('host', '127.0.0.1'))
        self.port_var.set(str(hammer_config.get('port', 8080)))
        self.password_var.set(hammer_config.get('password', ''))
        self.streamer_var.set(hammer_config.get('streamer_id', 'AMTD'))
    
    def save_settings(self):
        """Save current settings to config"""
        try:
            host = self.host_var.get().strip()
            port = int(self.port_var.get().strip())
            password = self.password_var.get()
            streamer_id = self.streamer_var.get().strip()
            
            if not host:
                messagebox.showerror("Hata", "Host adresi boş olamaz!")
                return
            
            if port <= 0 or port > 65535:
                messagebox.showerror("Hata", "Port numarası 1-65535 arasında olmalıdır!")
                return
            
            # Save to config
            self.config.set_hammer_pro_config(host, port, password, streamer_id)
            
            self.status_label.config(text="Ayarlar kaydedildi!", foreground="green")
            
        except ValueError:
            messagebox.showerror("Hata", "Port numarası geçerli bir sayı olmalıdır!")
        except Exception as e:
            messagebox.showerror("Hata", f"Ayarlar kaydedilirken hata oluştu: {e}")
    
    def test_connection(self):
        """Test the connection with current settings"""
        try:
            from ..data.hammer_pro_client import HammerProClient
            
            host = self.host_var.get().strip()
            port = int(self.port_var.get().strip())
            password = self.password_var.get()
            
            self.status_label.config(text="Bağlantı test ediliyor...", foreground="blue")
            self.update()
            
            # Create test client
            client = HammerProClient(host=host, port=port, password=password)
            
            # Try to connect
            client.connect()
            
            if client.is_connected():
                self.status_label.config(text="✅ Bağlantı başarılı!", foreground="green")
                client.disconnect()
            else:
                self.status_label.config(text="❌ Bağlantı başarısız!", foreground="red")
                
        except Exception as e:
            self.status_label.config(text=f"❌ Hata: {str(e)}", foreground="red")
    
    def connect(self):
        """Connect with current settings"""
        try:
            host = self.host_var.get().strip()
            port = int(self.port_var.get().strip())
            password = self.password_var.get()
            streamer_id = self.streamer_var.get().strip()
            
            # Save settings first
            self.config.set_hammer_pro_config(host, port, password, streamer_id)
            
            # Call the connect callback
            if self.on_connect:
                self.on_connect(host, port, password, streamer_id)
            
            self.result = True
            self.destroy()
            
        except ValueError:
            messagebox.showerror("Hata", "Port numarası geçerli bir sayı olmalıdır!")
        except Exception as e:
            messagebox.showerror("Hata", f"Bağlantı hatası: {e}")
    
    def cancel(self):
        """Cancel the dialog"""
        self.result = False
        self.destroy() 