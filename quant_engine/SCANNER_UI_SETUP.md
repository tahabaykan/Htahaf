# Trading Scanner UI - Setup Guide

## Overview

A React-based trading scanner UI for quant_engine that provides:
- Real-time market data via WebSocket
- Virtualized table for 500+ symbols
- Filtering and sorting
- Color-coded scores
- No charts, no order entry, no strategy logic

## Architecture

### Backend (FastAPI)
- **REST API**: `/api/market-data/merged` - Get merged data
- **WebSocket**: `/ws` - Live market data updates
- **Static Data Store**: Loads CSV once per day
- **Derived Metrics Engine**: Computes scores in real-time

### Frontend (React + Vite)
- **Virtualized Table**: react-window for performance
- **WebSocket Client**: Real-time updates
- **Filtering**: Client-side filtering
- **Sorting**: Client-side sorting

## Setup Instructions

### 1. Backend Setup

The backend is already configured. Just start the API:

```bash
cd quant_engine
python main.py api
```

The API will run on http://localhost:8000

### 2. Frontend Setup

#### Prerequisites
- Node.js v18+ and npm

#### Install Dependencies

```bash
cd quant_engine/frontend
npm install
```

#### Start Development Server

```bash
npm run dev
```

The frontend will be available at http://localhost:3000

### 3. Usage

1. **Load CSV**: Click "Load CSV" button to load `janalldata.csv`
2. **View Data**: Table displays all symbols with static, live, and derived data
3. **Filter**: Type in filter box to filter by symbol, CMON, or CGRUP
4. **Sort**: Click column headers to sort
5. **Auto Refresh**: Toggle "Start Auto Refresh" for 2-second updates
6. **WebSocket**: Real-time updates appear automatically when connected

## Data Flow

1. **Static Data**: Loaded from CSV once per day
2. **Live Data**: Received from Hammer Pro via `hammer_feed.py`
3. **Derived Scores**: Computed in real-time using `DerivedMetricsEngine`
4. **WebSocket Broadcast**: Updates sent every 2 seconds to all connected clients
5. **Frontend Update**: React state updates trigger re-render of virtualized table

## Features

### Static Columns (CSV)
- PREF_IBKR, CMON, CGRUP, FINAL_THG, SHORT_FINAL
- AVG_ADV, SMI, SMA63_chg, SMA246_chg

### Live Columns (Hammer)
- prev_close, Bid, Ask, Last, Volume, Spread

### Derived Scores
- FrontBuyScore, FinalFBScore, BidBuyScore, AskBuyScore
- AskSellScore, FrontSellScore, BidSellScore

### Color Coding
- **Green**: Score > 0.5 (good)
- **Yellow**: Score > 0 (neutral)
- **Red**: Score <= 0 (poor)

## Performance

- **Virtualized Table**: Only renders visible rows (500+ symbols handled efficiently)
- **WebSocket**: Efficient binary protocol for real-time updates
- **Client-side Filtering/Sorting**: No server round-trips needed

## Production Build

```bash
cd quant_engine/frontend
npm run build
```

Built files will be in `dist/` directory. Serve with any static file server or integrate with FastAPI static file serving.








