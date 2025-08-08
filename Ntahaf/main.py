import os
import sys
import io
import locale

# Windows için konsol çıktı kodlamasını ayarla
if sys.platform == 'win32':
    # Konsol çıktısı için UTF-8 kodlamasını zorla
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    # Konsol kod sayfasını UTF-8 olarak ayarla
    if hasattr(sys, 'stdout') and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys, 'stderr') and hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    
    # Yerel ayarları UTF-8 olarak ayarla
    if sys.version_info >= (3, 7):
        locale.setlocale(locale.LC_ALL, 'turkish' if locale.getdefaultlocale()[0] == 'tr_TR' else '')

# Add the parent directory to path so we can import Ntahaf
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from Ntahaf.gui.main_window import MainWindow
except ImportError as e:
    print(f"Import error: {e}")
    print("Python path:", sys.path)
    print("Current directory:", os.getcwd())
    raise

if __name__ == "__main__":
    try:
        app = MainWindow()
        app.mainloop()
    except Exception as e:
        print(f"Uygulama hatası: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        input("Devam etmek için bir tuşa basın...")
