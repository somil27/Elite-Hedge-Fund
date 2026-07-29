# Phase 1 + 2 — Integration Guide

This package adds Phase 1 (Intelligence Layer) and Phase 2 (Strategy & Learning)
to the existing AlphaDesk trading system.

---

## What's included

### Phase 1 — Intelligence Layer (4 new agents)

| Agent | File | What it does |
|---|---|---|
| News & Sentiment | `agents/news_sentiment.py` | Live news, earnings transcripts, per-symbol sentiment scores, event detection |
| Macro Intelligence | `agents/macro_intel.py` | Fed/RBI decisions, yield curve, CPI, auto-adjusts CIO risk budget |
| Options Flow | `agents/options_flow.py` | IV spikes, unusual call/put volume, smart money signals, India F&O PCR |
| Earnings Calendar | `agents/earnings_calendar.py` | Upcoming earnings tracking, pre-earnings size reduction, post-earnings action |

### Phase 2 — Strategy & Learning

| Component | File | What it does |
|---|---|---|
| Strategy Library | `strategies/strategy_library.py` | 7 pluggable strategies, auto-selected by macro regime |
| Backtesting Engine | `backtest/engine.py` | Full agent pipeline replay on historical data, walk-forward validation |
| RL Weight Optimiser | `strategies/rl_optimiser.py` | UCB1 bandit auto-adjusts signal weights from live trade outcomes |
| Multi-Portfolio Manager | `strategies/multi_portfolio.py` | Run Growth + Value + India portfolios simultaneously |

---

## File placement

Copy files to your project exactly as shown:

```
trading-system/backend/
├── agents/
│   ├── news_sentiment.py       ← NEW  (agents/news_sentiment.py)
│   ├── macro_intel.py          ← NEW  (agents/macro_intel.py)
│   ├── options_flow.py         ← NEW  (agents/options_flow.py)
│   ├── earnings_calendar.py    ← NEW  (agents/earnings_calendar.py)
│   └── cio.py                  ← REPLACE  (cio_updated.py → agents/cio.py)
├── strategies/                 ← NEW directory
│   ├── __init__.py
│   ├── strategy_library.py     ← NEW
│   ├── rl_optimiser.py         ← NEW
│   └── multi_portfolio.py      ← NEW
├── backtest/                   ← NEW directory
│   ├── __init__.py
│   └── engine.py               ← NEW
├── graph/
│   └── trading_graph.py        ← REPLACE  (trading_graph.py)
├── core/
│   └── schemas.py              ← REPLACE  (schemas.py)
├── api/
│   ├── main.py                 ← UPDATE  (add router import)
│   └── phase12_router.py       ← NEW  (api/phase12_router.py)
├── db/versions/
│   └── 004_phase12.py          ← NEW  (db/versions/004_phase12.py)
└── tests/
    └── test_phase12.py         ← NEW

trading-system/frontend/src/pages/
└── Phase12Page.tsx              ← NEW
```

---

## Step-by-step setup

### 1 — Copy all files

Place each file as shown in the table above.
The two REPLACE files fully overwrite the existing ones.

### 2 — Create empty `__init__.py` files

```bash
touch backend/strategies/__init__.py
touch backend/backtest/__init__.py
```

### 3 — Run the new DB migration

```bash
docker-compose exec backend alembic upgrade head
```

This creates 5 new tables:
- `rl_signal_weights`       — UCB1 bandit state
- `backtest_results`        — stored backtest runs
- `backtest_trades`         — individual backtest trades
- `portfolio_definitions`   — multi-portfolio configs
- `news_events`             — news event cache

### 4 — Register the new API router in `api/main.py`

Add these two lines after the existing router registrations:

```python
from api.phase12_router import router as phase12_router
app.include_router(phase12_router)
```

### 5 — Add the new page to the frontend

In `frontend/src/App.tsx`:

```tsx
import Phase12Page from './pages/Phase12Page'
// Add to nav:
{ to: '/intelligence', label: 'Intelligence', icon: Brain }
// Add to routes:
<Route path="/intelligence" element={<Phase12Page />} />
```

### 6 — Rebuild Docker images (if running containerised)

```bash
docker-compose up -d --build
```

---

## New API endpoints

### Strategy endpoints

```
GET  /api/strategies                          → list all strategies
GET  /api/strategies/recommend?macro_regime=GOLDILOCKS&mode=short_term&market=us
```

### Backtest endpoints

```
POST /api/backtest/run                        → start backtest (background)
GET  /api/backtest/{id}                       → poll for results
GET  /api/backtest/{id}/trades                → individual simulated trades
GET  /api/backtest                            → list past backtests
```

### RL weight endpoints

```
GET  /api/rl/weights?market=us               → current UCB1 weights + performance
POST /api/rl/reset?market=us                 → reset to defaults
```

### Multi-portfolio endpoints

```
GET  /api/portfolios                          → list all portfolios + performance
POST /api/portfolios/run-all?auto_mode=false  → launch all portfolio cycles
POST /api/portfolios                          → add new portfolio
POST /api/portfolios/{id}/pause
POST /api/portfolios/{id}/resume
```

---

## How the new cycle flow works

```
Before Phase 1+2:
  CIO → Research → Analysis → Risk → Human Gate → Execution → Post-trade

After Phase 1+2:
  CIO → Phase1 (parallel) → Strategy Selection → RL Weight Load
      → Research → Analysis (with earnings adjustments) → Risk
      → Human Gate → Execution → Post-trade + RL Update
```

The `phase1` node runs all 4 intelligence agents in parallel alongside CIO,
then selects the best strategy from the library based on macro regime,
then blends RL-learned weights (70% strategy, 30% RL) into the mandate.

After every closed trade, the RL optimiser updates signal weights so
the system gets smarter over time.

---

## Starting a cycle with Phase 1+2

### Via dashboard
The Launch Cycle panel now shows a "Strategy" field. You can force a specific
strategy or leave it blank for auto-selection based on macro conditions.

### Via API

```bash
# Short-term momentum cycle (strategy auto-selected)
curl -X POST http://localhost:8000/api/cycles/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "short_term", "auto_mode": false, "market": "us"}'

# Force a specific strategy
curl -X POST http://localhost:8000/api/cycles/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "short_term", "auto_mode": false, "market": "us", "strategy": "earnings_play"}'

# India long-term value cycle
curl -X POST http://localhost:8000/api/cycles/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "long_term", "auto_mode": false, "market": "india", "indian_broker": "zerodha"}'
```

### Launch all portfolios at once

```bash
curl -X POST "http://localhost:8000/api/portfolios/run-all?auto_mode=false"
```

---

## Running a backtest

```bash
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "strategy":        "momentum",
    "symbols":         ["NVDA", "AAPL", "MSFT"],
    "start_date":      "2024-01-01",
    "end_date":        "2024-12-31",
    "mode":            "short_term",
    "market":          "us",
    "initial_capital": 100000,
    "rebalance_freq":  "weekly"
  }'
```

Returns `{"backtest_id": "...", "status": "running"}`.
Poll `GET /api/backtest/{id}` every few seconds. Takes 1–3 minutes for a full year.

---

## Running tests

```bash
cd backend
pytest tests/test_phase12.py -v
```

All 37 tests run without any API keys or network access.

---

## RL weight system explained

The RL optimiser uses a **UCB1 multi-armed bandit**. Each agent signal is an "arm".

**After every closed trade:**
1. Calculates a Sharpe-adjusted reward (profitable + fast = high reward)
2. Updates the total reward and pull count for each signal that contributed
3. Recalculates UCB1 scores: `avg_reward + 0.5 * sqrt(ln(total_pulls) / pulls)`
4. Normalises to sum to 1.0, applies floor (2%) and ceiling (60%)

**Effect over time:**
- After 20 trades: weights start to differentiate from defaults
- After 50 trades: meaningful signal ranking emerges
- After 100+ trades: weights reflect what actually predicts returns in your market

Reset weights with `POST /api/rl/reset` if you change strategy or market.

---

## Strategy auto-selection logic

```
Input:  macro_regime + mode + market
Output: StrategyConfig

GOLDILOCKS  + short_term → Momentum
STAGFLATION + short_term → Defensive
RATE_HIKE   + long_term  → Sector Rotation
RATE_CUT    + any        → Momentum or Value
india       + short_term → India Momentum
india       + long_term  → Value Investing
```

Override at cycle start with `"strategy": "earnings_play"` in the request body.
