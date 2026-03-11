# CFD Trading Bot - Project Plan

## Overview
Real-time CFD trading bot for Gold, Silver, and Nasdaq-100 with signal generation, news sentiment analysis, and paper trading simulation.

**Broker Integration:** XTB (prices matched to XTB CFDs)

---

## Current Status (2026-02-02)

### ✅ Implemented
- **Backend:**
  - FastAPI server (port 8001)
  - Realistic price feeder matching XTB CFD prices
  - Technical indicators (RSI, MACD, ATR, Momentum)
  - Signal scoring system (technical + price action)
  - Account management ($1000 starting balance)
  - Dry run / Simulate mode toggle
  - Brave Search news integration (with rate limiting)
  - Alpha Vantage API client (currently unused, using realistic prices instead)
  
- **Frontend:**
  - React + TypeScript dashboard (port 5173)
  - Real-time clock display
  - Sidebar with account stats
  - Signals grid with live scores
  - Console logs
  - Mode toggle (🧪 SIMULATE / ⚡ LIVE)
  - SCANNING/IDLE indicator
  - Last scan timestamp (updates every second)
  
- **Infrastructure:**
  - GitHub repo: https://github.com/pinchr/cfd-trading-bot
  - Auto-monitoring script (checks health every 5 min)
  - Ngrok public URL: https://unramped-melania-benzylidene.ngrok-free.dev
  - Git commits with descriptive messages

### 🚧 In Progress
- **News Tab:**
  - Backend endpoint exists: `/api/news/{symbol}`
  - Brave Search integration with sentiment analysis
  - **Missing:** Frontend News tab UI
  - **Missing:** News score integration into signal calculation
  
- **Position Tracking:**
  - Backend models exist (Signal, Account)
  - **Missing:** Actual position entry/exit logic
  - **Missing:** P&L tracking for trades
  - **Missing:** Trade history storage

### ❌ Not Implemented Yet
- **Trading Execution:**
  - Position creation from signals (auto or manual)
  - TP/SL tracking and auto-close
  - Real trade execution (live mode)
  - Order management
  
- **Dashboard Features:**
  - Trade history tab
  - Performance metrics (win rate, Sharpe ratio)
  - Position management UI
  - News tab with sentiment display
  - Chart/candlestick visualizations
  
- **Advanced Features:**
  - Backtesting framework
  - Risk management (position sizing)
  - Stop-loss automation
  - Multiple timeframes
  - Correlation analysis

---

## Feature Checklist (From UI Ideas)

### UI Reference Designs
Located in: `ui_ideas/` (5 images)
- IMG_0336/0337: Polymarket scanner UI (terminal style, green on black)
- IMG_0338: Twitter post showing bot UI
- IMG_0340: Mahoraga portfolio tracker UI

### ✅ Implemented from UI Ideas
1. Dark theme (black #0a0e27 background)
2. Neon green accents (#00ff41)
3. Monospace fonts
4. Left sidebar with account stats
5. Signals grid with scores
6. Console logs tab
7. Real-time updates (5-10 sec polling)
8. SCANNING indicator (green pulse when active)
9. Last scan timestamp

### ❌ Missing from UI Ideas
1. **Positions table** (open trades with live P&L)
2. **Trade history** (closed trades with outcomes)
3. **News sentiment panel** (headlines with buy/sell signals)
4. **Mini charts/sparklines** (price trends per symbol)
5. **Performance stats** (win rate, avg win/loss)
6. **Portfolio performance graph** (equity curve over time)
7. **Risk metrics** (margin used %, drawdown)

---

## Priority Fixes (User Requested 2026-02-02 14:01)

### 1. **Fix Sidebar Values** ✅
- **Issue:** Some values still showing mock data
- **Status:** DONE - Backend returns real account data
- **Verification needed:** Check if frontend displays correctly

### 2. **Fix Last Scan Display** ✅
- **Issue:** Shows static "2m ago" instead of real time
- **Status:** DONE - Updates every second with accurate countdown
- **Format:** "Now", "45s ago", "2m 13s ago", "1h 5m ago"

### 3. **News Tab Implementation** 🚧
- **Status:** Backend ready, frontend missing
- **Requirements:**
  - Select ticker (GC=F, SI=F, NQ=F)
  - Display: Single sentence headline
  - Show: Score (0-1 importance)
  - Show: Signal (BUY/SELL/NEUTRAL) with color
  - Use news in signal score calculation
  
### 4. **Integrate News into Signal Scoring** 🚧
- **Current:** Scores are 40% technical, 20% price action, 40% news (but news=0)
- **Needed:** Actually fetch news during signal generation
- **Needed:** Weight news sentiment into final score

---

## Architecture

### Instruments Tracked
1. **Gold** (GC=F) - XTB CFD GOLD ~$4,779
2. **Silver** (SI=F) - XTB CFD SILVER ~$83
3. **Nasdaq-100** (NQ=F) - XTB CFD US100 ~$25,494

### Signal Scoring Formula
```
Final Score = (Technical * 0.4) + (Price Action * 0.2) + (News * 0.4)

Technical:
  - RSI (14): oversold/overbought
  - MACD: trend direction
  - Momentum (10): price velocity

Price Action:
  - Support/resistance levels
  - Breakouts
  - Volume trends

News (via Brave Search):
  - Sentiment analysis (bullish/bearish keywords)
  - Recency weighting
  - Source credibility
```

### Score → Signal Mapping
- Score > 0.6 → STRONG BUY
- Score > 0.2 → BUY
- Score -0.2 to 0.2 → NEUTRAL
- Score < -0.2 → SELL
- Score < -0.6 → STRONG SELL

### Risk Management (Not Yet Implemented)
- Position size: % of available balance
- Max positions: 3 (one per symbol)
- Stop-loss: ATR * 2
- Take-profit: ATR * 3
- Risk/reward ratio: 1.5:1

---

## Data Flow

### Signal Generation
```
1. Realistic Price Feeder → Current price + variation
2. Generate 100 candles for technical analysis
3. Calculate indicators (RSI, MACD, ATR)
4. Fetch news from Brave Search (1 req/sec limit)
5. Calculate sentiment score
6. Weighted composite score
7. Determine direction (BUY/SELL/NEUTRAL)
8. Calculate TP/SL levels
9. Return Signal object
```

### Frontend Updates
```
1. Poll /api/signals every 10 seconds
2. Poll /api/account every 1 second
3. Poll /api/logs every 5 seconds
4. Display in dashboard
5. Show SCANNING when backend is fetching
```

---

## Files Structure

```
cfd-trading-bot/
├── backend/
│   ├── main.py                 # FastAPI server
│   ├── realistic_prices.py     # Price feeder (XTB-matched)
│   ├── alpha_vantage.py        # Alpha Vantage client (unused)
│   ├── news_client.py          # Brave Search + sentiment
│   ├── indicators.py           # Technical analysis
│   ├── models.py               # Pydantic models
│   ├── requirements.txt
│   └── .env                    # API keys
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.tsx   # Main container
│   │   │   ├── Sidebar.tsx     # Account + mode toggle
│   │   │   ├── SignalsGrid.tsx # Signals table
│   │   │   ├── ConsoleTab.tsx  # Event logs
│   │   │   └── ScoreGauge.tsx  # Score visualization
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.ts
│
├── ui_ideas/                   # Reference designs
├── monitor.sh                  # Auto-healing monitor
├── CFD-PROJECT.md             # This file
├── PROJECT.md                 # (Outdated - Polymarket bot)
├── README.md                  # Project overview
└── SETUP.md                   # Installation guide
```

---

## Next Steps (Priority Order)

### Immediate (Today)
1. ✅ Fix XTB price matching
2. ✅ Fix last scan display
3. ✅ Verify sidebar shows real data
4. **Create News Tab UI** (highest priority)
5. **Integrate news into signal scoring**

### Short-term (This Week)
6. Build position tracking system
7. Implement trade history
8. Add performance metrics
9. Create mini charts for signals
10. Test with paper trading

### Medium-term (Next Week)
11. Backtesting framework
12. Risk management automation
13. Multi-timeframe analysis
14. Email/SMS alerts
15. Live trading mode (XTB API integration)

---

## API Endpoints

### Current
- `GET /` - Health check
- `GET /api/signals` - Get trading signals
- `GET /api/logs` - Get console logs
- `GET /api/account` - Get account info
- `POST /api/account/mode` - Toggle simulate/live mode
- `GET /api/news/{symbol}` - Get news + sentiment
- `GET /api/quote/{symbol}` - Get current price

### Needed
- `POST /api/positions` - Create position from signal
- `GET /api/positions` - List open positions
- `PUT /api/positions/{id}` - Update/close position
- `GET /api/trades` - Get trade history
- `GET /api/performance` - Get performance metrics

---

## Questions to Answer

1. **Broker Integration:** Will we integrate XTB API for live trading?
2. **Position Sizing:** What % of balance per trade?
3. **Auto-Trading:** Should signals auto-create positions in live mode?
4. **Stop-Loss:** Manual or automatic?
5. **Notifications:** When to alert user (trade opened, TP/SL hit)?

---

*Last updated: 2026-02-02 14:05*
