"""
Simulation Controller - Central control for simulation mode

Features:
- Enable/disable simulation mode
- Safety checks (only in LIFELESS mode)
- State tracking
- Prevent real order execution in simulation

Safety:
- Simulation ONLY allowed when LIFELESS mode is active
- Multiple safety checks before allowing simulation
- Clear state indicators
"""
from typing import Optional
from loguru import logger


class SimulationController:
    """
    Controls simulation mode for testing.
    
    This is a critical safety component that ensures:
    1. Simulation only runs in LIFELESS mode
    2. Real trading is NEVER affected
    3. Clear state tracking
    
    Usage:
        controller = get_simulation_controller()
        controller.set_lifeless_mode(True)
        controller.enable_simulation()
        
        if controller.is_simulation_mode():
            # Use fake orders
        else:
            # Use real orders
    """
    
    def __init__(self):
        self.simulation_active = False
        self.lifeless_active = False
        logger.info("[SimulationController] Initialized (simulation: OFF, lifeless: OFF)")
    
    def set_lifeless_mode(self, active: bool):
        """
        Set LIFELESS mode state.
        
        Called by the LIFELESS mode toggle in UI.
        If disabling LIFELESS, also disables simulation.
        """
        self.lifeless_active = active
        
        if not active and self.simulation_active:
            # Disable simulation if LIFELESS is turned off
            logger.warning("[SimulationController] LIFELESS disabled, auto-disabling simulation")
            self.simulation_active = False
        
        logger.info(f"[SimulationController] LIFELESS mode: {'ON' if active else 'OFF'}")
    
    def enable_simulation(self) -> bool:
        """
        Enable simulation mode.
        
        Safety check: Only allows if LIFELESS mode is active.
        
        Returns:
            True if enabled, raises error otherwise
        """
        if not self.lifeless_active:
            error_msg = "⚠️ SAFETY CHECK FAILED: Simulation only allowed in LIFELESS mode!"
            logger.error(f"[SimulationController] {error_msg}")
            raise ValueError(error_msg)
        
        self.simulation_active = True
        logger.warning("[SimulationController] 🎭 SIMULATION MODE ENABLED - Orders will be FAKE")
        return True
    
    def disable_simulation(self):
        """Disable simulation mode"""
        self.simulation_active = False
        logger.info("[SimulationController] Simulation mode disabled")
    
    def is_simulation_mode(self) -> bool:
        """
        Check if simulation mode is active.
        
        Returns True only if BOTH:
        1. Simulation is enabled
        2. LIFELESS mode is active
        """
        return self.simulation_active and self.lifeless_active
    
    def get_status(self) -> dict:
        """Get current status"""
        return {
            'simulation_active': self.simulation_active,
            'lifeless_active': self.lifeless_active,
            'is_simulation_mode': self.is_simulation_mode(),
            'mode_display': '🎭 SIMULATION' if self.is_simulation_mode() else '💰 REAL'
        }
    
    def assert_simulation_mode(self):
        """Assert that simulation mode is active (for safety)"""
        if not self.is_simulation_mode():
            raise RuntimeError("This operation requires simulation mode!")
    
    def assert_real_mode(self):
        """Assert that we are NOT in simulation mode (for safety)"""
        if self.is_simulation_mode():
            raise RuntimeError("This operation cannot run in simulation mode!")


# Global instance
_simulation_controller: Optional[SimulationController] = None


def get_simulation_controller() -> SimulationController:
    """Get global simulation controller"""
    global _simulation_controller
    if _simulation_controller is None:
        _simulation_controller = SimulationController()
    return _simulation_controller
