# JanAllModern

Modernized version of the JanAll stock trading application.

## Overview

JanAllModern is a complete refactoring and modernization of the original JanAll application. It maintains 100% feature parity while providing:

- **Clean Architecture**: Separated UI, core logic, services, and utilities
- **Modern UI/UX**: Professional styling with consistent colors, fonts, and layout
- **PEP8 Compliance**: All code follows Python standards
- **Better Documentation**: Comprehensive docstrings and comments
- **Improved Maintainability**: Modular structure for easier updates

## Project Structure

```
janallmodern/
├── main.py                          # Application entry point
├── README.md                         # This file
├── REFACTORING_SUMMARY.md           # Detailed refactoring notes
└── janallmodernapp/
    ├── __init__.py
    ├── main_window.py               # Main application window (to be refactored)
    ├── ui/                          # UI Components
    │   ├── __init__.py
    │   ├── theme.py                 # Modern theme system
    │   └── ...
    ├── core/                        # Core Business Logic
    │   ├── __init__.py
    │   ├── mode_manager.py          # Trading mode management
    │   ├── exception_manager.py     # Exception list management
    │   └── ...
    ├── services/                    # External Service Integrations
    │   ├── __init__.py
    │   ├── hammer_client.py         # Hammer Pro API client
    │   ├── ibkr_client.py           # IBKR API client
    │   └── ...
    ├── utils/                       # Utility Functions
    │   └── __init__.py
    └── models/                      # Data Models
        └── __init__.py
```

## Installation

1. Ensure all dependencies from the original JanAll are installed
2. Run the application:
   ```bash
   python janallmodern/main.py
   ```

## Key Features

- **Trading Mode Management**: Switch between HAMPRO, IBKR GUN, and IBKR PED modes
- **Order Management**: Place orders with various order types (Bid, Ask, Front, SoftFront)
- **Portfolio Management**: Track positions and manage portfolio
- **ETF Panel**: Monitor ETF prices and changes
- **Exception List**: Manage tickers that should not be traded
- **BDATA Storage**: Track fills and positions

## File Path Rules

**IMPORTANT**: All CSV reading and writing operations must be done to the StockTracker directory, NOT to StockTracker/janall/ directory.

✅ **CORRECT**: `"janalldata.csv"` (in StockTracker directory)
❌ **WRONG**: `"janall/janalldata.csv"`

## Status

This is a work in progress. The modernization is being done incrementally:

- ✅ Project structure created
- ✅ Modern theme system
- ✅ Core modules modernized (mode_manager, exception_manager)
- 🔄 Copying and modernizing supporting modules
- ⏳ Main window refactoring
- ⏳ Complete UI modernization

## Notes

- Original janall folder is completely untouched
- All functionality is preserved exactly as in original
- Code is now more maintainable, readable, and professional



