import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    print("Attempting granular import...")
    import app
    print("app imported")
    import app.psfalgo
    print("app.psfalgo imported")
    import app.psfalgo.order_controller_debug
    print("app.psfalgo.order_controller_debug imported")
    print("Module file:", app.psfalgo.order_controller_debug.__file__)
    print("Attributes in module:", dir(app.psfalgo.order_controller_debug))
    
    if hasattr(app.psfalgo.order_controller_debug, 'get_order_controller'):
        print("get_order_controller FOUND")
    else:
        print("get_order_controller NOT FOUND")
        
except ImportError as e:
    print(f"Import failed: {e}")
except Exception as e:
    print(f"Other error: {e}")
