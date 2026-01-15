# Quant Engine Trading Scanner - Frontend

React-based trading scanner UI for quant_engine.

## Setup

1. Install Node.js (v18 or higher) and npm

2. Install dependencies:
```bash
npm install
```

3. Start development server:
```bash
npm run dev
```

The frontend will be available at http://localhost:3000

## Features

- **Virtualized Table**: Handles 500+ rows efficiently using react-window
- **Real-time Updates**: WebSocket connection for live market data
- **Filtering**: Filter by symbol, CMON, or CGRUP
- **Sorting**: Click column headers to sort
- **Color-coded Scores**: Visual indicators for buy/sell scores
- **Auto Refresh**: Optional 2-second auto-refresh

## Data Categories

### Static (CSV)
- PREF_IBKR, CMON, CGRUP, FINAL_THG, SHORT_FINAL
- AVG_ADV, SMI, SMA63_chg, SMA246_chg

### Live (Hammer)
- prev_close, bid, ask, last, spread, volume

### Derived Scores
- FrontBuyScore, FinalFBScore, BidBuyScore, AskBuyScore
- AskSellScore, FrontSellScore, BidSellScore

## Build for Production

```bash
npm run build
```

The built files will be in the `dist` directory.








