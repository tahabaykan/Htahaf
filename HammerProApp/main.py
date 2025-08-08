import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gui.main_window import MainWindow
except ImportError as e:
    print(f"Error: Could not import MainWindow from gui.main_window: {e}")
    sys.exit(1)

if __name__ == "__main__":
    app = MainWindow()
    
    # Set up window closing handler
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    app.mainloop() 