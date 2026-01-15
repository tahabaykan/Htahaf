"""
Mod Servisi
Uygulamanın çalışma modunu (HAMPRO, IBKR_GUN, IBKR_PED) yönetir.
"""

class ModeService:
    def __init__(self):
        self.current_mode = "HAMPRO"
        self.valid_modes = ["HAMPRO", "IBKR_GUN", "IBKR_PED"]
        
        # Bağlantı durumları
        self.connection_status = {
            "HAMPRO": False,
            "IBKR_GUN": False,
            "IBKR_PED": False
        }

    def set_mode(self, mode):
        """Modu değiştir"""
        if mode in self.valid_modes:
            self.current_mode = mode
            print(f"[ModeService] Mod değiştirildi: {mode}")
            return True
        return False

    def get_mode(self):
        """Mevcut modu döndür"""
        return self.current_mode

    def is_hampro_mode(self):
        return self.current_mode == "HAMPRO"

    def is_ibkr_mode(self):
        return self.current_mode in ["IBKR_GUN", "IBKR_PED"]

    def update_connection_status(self, service_name, status):
        """Bağlantı durumunu güncelle"""
        if service_name in self.connection_status:
            self.connection_status[service_name] = status

    def get_connection_status(self):
        return self.connection_status
