# AlphaDesk — Multi-Agent AI Trading System

A production-grade, multi-agent AI trading system modeled as a brokerage firm. Each agent acts as a specialist employee with a defined role, long-term memory, and structured communication with other agents. The system supports both short-term (momentum/quant) and long-term (fundamental/macro) trading strategies, with an optional human-in-the-loop approval gate before execution.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Agent Roster](#agent-roster)
3. [Tech Stack](#tech-stack)
4. [Project Structure](#project-structure)
5. [Prerequisites](#prerequisites)
6. [Setup Guide](#setup-guide)
7. [Running the System](#running-the-system)
8. [API Reference](#api-reference)
9. [Memory System](#memory-system)
10. [Trading Modes](#trading-modes)
11. [Human-in-the-Loop Gate](#human-in-the-loop-gate)
12. [Database Schema](#database-schema)
13. [Configuration Reference](#configuration-reference)
14. [Going to Production](#going-to-production)
15. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The system is structured as a LangGraph directed graph. Each node in the graph is an AI agent powered by Claude. Agents communicate via a typed message schema (Pydantic models) that flows through the graph state. Long-term memory is stored in PostgreSQL with pgvector for semantic retrieval.

```
Market Trigger / Schedule
        │
        ▼
   ┌─────────┐
   │   CIO   │  Sets mandate, watchlist, mode, agent weights
   └─────────┘
        │  (fan-out, async parallel)
   ┌────┴────┬──────────────┐
   ▼         ▼              ▼
Market    Fundamental    Quant
Intel     Analyst        Researcher
   └────┬────┴──────────────┘
        │  (fan-in)
   ┌────┴──────────────┐
   │  Portfolio        │
   │  Strategist       │  Sizes and proposes trades
   └────────────────────┘
        │  (parallel)
   ┌────┴────┬──────────────┐
   ▼         ▼              ▼
Technical  Risk Manager  (veto path)
Analyst    [GATEKEEPER]
   └────┬────┘
        │
        ▼
   Trade Desk (OMS)
        │
        ▼
   ┌─────────────────────┐
   │  Human Gate         │  ◄── Pause here in manual mode
   │  (Approve/Reject)   │
   └─────────────────────┘
        │
        ▼
   Execution Algorithm  (VWAP/TWAP)
        │
   ┌────┴────┬──────────────┐
   ▼         ▼              ▼
Compliance  Portfolio   Reporting
Monitor     Monitor     Agent
```

**Key design decisions:**
- **Async fan-out**: Research agents run in parallel; analysis layer also parallel
- **Synchronous gates**: Risk Manager veto and Human Gate are synchronous checkpoints
- **Long-term memory**: Every agent writes observations and learns from past outcomes via pgvector semantic search
- **Both modes**: Short-term boosts quant/technical weights; long-term boosts fundamental/macro weights

---

## Agent Roster

| Agent | Role | Model | Key Tools |
|---|---|---|---|
| **CIO** | Orchestrator. Sets mandate, theme, watchlist, risk budget | claude-opus-4-5 | Memory, portfolio snapshot |
| **Market Intelligence** | Reads news, macro data, sentiment. Determines market regime | claude-sonnet-4-5 | Web data, news APIs, memory |
| **Fundamental Analyst** | Earnings, DCF valuation, buy/sell ratings | claude-sonnet-4-5 | yfinance financials, memory |
| **Quant Researcher** | Momentum, mean-reversion, factor signals, backtesting | claude-sonnet-4-5 | OHLCV data, indicator engine, memory |
| **Portfolio Strategist** | Synthesizes research into sized proposals | claude-sonnet-4-5 | Proposal builder, memory |
| **Technical Analyst** | Chart patterns, entry zones, stop-loss, take-profit | claude-sonnet-4-5 | OHLCV, indicator engine, memory |
| **Risk Manager** | VaR, concentration, drawdown gatekeeper with veto power | claude-opus-4-5 | Risk rules DB, memory |
| **Trade Desk (OMS)** | Converts approved proposals to order instructions | claude-sonnet-4-5 | Order builder, human notifier |
| **Execution Algorithm** | VWAP/TWAP smart order execution | claude-sonnet-4-5 | Alpaca API, fill tracker |
| **Compliance Monitor** | Post-trade regulatory checks | claude-sonnet-4-5 | Rules DB, alert publisher |
| **Portfolio Monitor** | Live P&L tracking, drift detection | claude-sonnet-4-5 | Broker API, memory |
| **Reporting Agent** | Audit log, cycle summary, reflection trigger | claude-sonnet-4-5 | DB writer, reflection engine |

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Agent framework** | LangGraph 0.2 | Full control over graph topology, conditional routing, human interrupt |
| **LLM** | Anthropic Claude (Sonnet 4 / Opus 4) | Best reasoning for financial analysis |
| **Long-term memory** | PostgreSQL 16 + pgvector | Persistent semantic search; no separate vector DB needed |
| **Message bus** | Redis Streams | Async fan-out, persistent, dead-letter queues |
| **Market data** | yfinance (dev) / Polygon.io (prod) | Free tier for dev; institutional grade for prod |
| **Execution** | Alpaca (paper trading → live) | Clean SDK, paper trading, WebSocket fills |
| **API server** | FastAPI + Uvicorn | Async, fast, WebSocket support |
| **Frontend** | React 18 + Vite + Tailwind | Fast dev, typed, beautiful UI |
| **Migrations** | Alembic | Version-controlled DB schema |
| **Infra (dev)** | Docker Compose | One command to start everything |
| **Observability** | structlog | Structured JSON logs |

---

## Project Structure

```
trading-system/
├── backend/
│   ├── agents/
│   │   ├── base.py              # BaseAgent class (LLM + memory methods)
│   │   ├── cio.py               # Chief Investment Officer
│   │   ├── market_intel.py      # Market Intelligence
│   │   ├── fundamental.py       # Fundamental Analyst
│   │   ├── quant.py             # Quantitative Researcher
│   │   ├── strategist.py        # Portfolio Strategist
│   │   ├── technical.py         # Technical Analyst
│   │   ├── risk_manager.py      # Risk Manager (gatekeeper)
│   │   ├── trade_desk.py        # Trade Desk / OMS
│   │   ├── execution.py         # Execution Algorithm
│   │   └── post_trade.py        # Compliance + Monitor + Reporting
│   ├── api/
│   │   └── main.py              # FastAPI app + WebSocket
│   ├── core/
│   │   ├── config.py            # Pydantic settings
│   │   ├── memory.py            # pgvector read/write service
│   │   └── schemas.py           # All Pydantic message models + TradingState
│   ├── db/
│   │   ├── database.py          # SQLAlchemy async engine
│   │   ├── models.py            # ORM models
│   │   ├── env.py               # Alembic env
│   │   └── migrations/
│   │       └── 001_initial.py   # Full schema with pgvector
│   ├── graph/
│   │   └── trading_graph.py     # LangGraph graph definition
│   ├── tools/
│   │   ├── market_data.py       # yfinance + technical indicators
│   │   └── broker.py            # Alpaca paper trading client
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx    # Cycle launcher + recent cycles
│   │   │   ├── CyclePage.tsx    # Live agent pipeline + human gate UI
│   │   │   ├── TradesPage.tsx   # Trade history + P&L chart
│   │   │   └── PortfolioPage.tsx # Live positions + allocation
│   │   ├── store/
│   │   │   ├── api.ts           # Axios API client
│   │   │   └── store.ts         # Zustand state store
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts  # Live updates via WebSocket
│   │   ├── styles/
│   │   │   └── globals.css      # Tailwind + custom design tokens
│   │   ├── App.tsx              # Router + layout
│   │   └── main.tsx             # Entry point
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── Dockerfile
│   └── index.html
├── docker-compose.yml
└── README.md
```

---

## Prerequisites

- **Docker + Docker Compose** (recommended) OR:
  - Python 3.12+
  - Node.js 20+
  - PostgreSQL 16 with pgvector extension
  - Redis 7+
- **Anthropic API key** (required) — get one at https://console.anthropic.com
- **Alpaca account** (optional for paper trading) — get one at https://alpaca.markets
- **Polygon.io API key** (optional, falls back to yfinance) — https://polygon.io

---

## Setup Guide

### Option A — Docker Compose (Recommended)

**Step 1: Clone and configure**
```bash
git clone <your-repo>
cd trading-system

cp backend/.env.example backend/.env
# Edit backend/.env and add your ANTHROPIC_API_KEY at minimum
```

**Step 2: Start all services**
```bash
docker-compose up -d
```

This starts PostgreSQL (with pgvector), Redis, the FastAPI backend, and the React frontend.

**Step 3: Run database migrations**
```bash
docker-compose exec backend alembic upgrade head
```

**Step 4: Open the UI**

Navigate to http://localhost:5173

---

### Option B — Manual Setup

**Step 1: Start infrastructure**
```bash
# PostgreSQL with pgvector (Docker)
docker run -d \
  --name trading_postgres \
  -e POSTGRES_USER=trader \
  -e POSTGRES_PASSWORD=trader_pass \
  -e POSTGRES_DB=trading_system \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Redis
docker run -d --name trading_redis -p 6379:6379 redis:7-alpine
```

**Step 2: Backend setup**
```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys

# Run migrations
alembic upgrade head

# Start the server
uvicorn api.main:app --reload --port 8000
```

**Step 3: Frontend setup**
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Running the System

### Launching a Trading Cycle

**Via the UI:**
1. Go to http://localhost:5173
2. Select trading mode (Short Term or Long Term)
3. Toggle Auto Execute on/off
4. Click "Launch Cycle"

**Via API:**
```bash
# Short-term cycle, human approval required
curl -X POST http://localhost:8000/api/cycles/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "short_term", "auto_mode": false}'

# Long-term cycle, fully automated
curl -X POST http://localhost:8000/api/cycles/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "long_term", "auto_mode": true}'
```

### Approving a Trade

When a cycle reaches the human gate (auto_mode=false), it pauses and waits. You'll see the "Needs Review" alert on the dashboard.

**Via the UI:** Go to the cycle page, review the trade details, and click Approve, Resize, or Reject.

**Via API:**
```bash
# Approve at proposed size
curl -X POST http://localhost:8000/api/cycles/{cycle_id}/decide \
  -H "Content-Type: application/json" \
  -d '{"decision": "approved"}'

# Resize to 2% allocation before approving
curl -X POST http://localhost:8000/api/cycles/{cycle_id}/decide \
  -H "Content-Type: application/json" \
  -d '{"decision": "resized", "override_weight": 0.02, "notes": "Reducing size due to earnings risk"}'

# Reject
curl -X POST http://localhost:8000/api/cycles/{cycle_id}/decide \
  -H "Content-Type: application/json" \
  -d '{"decision": "rejected", "notes": "Market conditions unfavorable"}'
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/cycles/start` | Start a new trading cycle |
| GET | `/api/cycles` | List recent cycles |
| GET | `/api/cycles/{id}` | Get cycle state and all agent outputs |
| GET | `/api/cycles/{id}/review` | Get pending human review details |
| POST | `/api/cycles/{id}/decide` | Submit human approval decision |
| GET | `/api/portfolio` | Current portfolio from broker |
| GET | `/api/trades` | Trade history and outcomes |
| GET | `/api/health` | Health check |
| WS | `/ws` | WebSocket for live cycle updates |

### WebSocket Events

Connect to `ws://localhost:8000/ws` to receive live events:

```json
{ "event": "cycle_started",  "cycle_id": "...", "mode": "short_term" }
{ "event": "cycle_update",   "cycle_id": "...", "status": "awaiting_human", "symbol": "NVDA" }
{ "event": "cycle_update",   "cycle_id": "...", "status": "executed", "execution_report": {...} }
{ "event": "cycle_error",    "cycle_id": "...", "error": "..." }
```

---

## Memory System

Each agent maintains long-term memory in PostgreSQL + pgvector. Memory persists across cycles and allows agents to learn from past experience.

### Memory Types

| Type | Written by | Used for |
|---|---|---|
| `observation` | Market Intel, Execution, Monitor | Raw facts: price levels, regime, news |
| `analysis` | All analysis agents | Agent's reasoned conclusions and trade theses |
| `signal` | Quant Researcher | Scored trading signals with entry triggers |
| `reflection` | Post-trade job (auto) | Lessons learned from trade outcomes |

### How Retrieval Works

At the start of each cycle, every agent queries its own memory namespace using semantic search (cosine similarity on 1536-dim embeddings). For example:

- CIO queries: "investment mandate short_term trading"
- Fundamental Analyst (analyzing NVDA) queries: "NVDA fundamental valuation earnings"
- Risk Manager queries: "risk assessment VaR drawdown position sizing"

The top-k results are injected into the agent's prompt as context, allowing it to reference past decisions and outcomes.

### Reflections

After each closed trade, the Reporting Agent automatically writes reflections for the Portfolio Strategist, Risk Manager, and Quant Researcher. These reflections include the trade outcome (P&L, close reason, agent signals at entry) and are stored with importance scores scaled by trade magnitude. Agents read these reflections at the next cycle start.

---

## Trading Modes

### Short-Term Mode

- **Horizon**: 3–10 days
- **Dominant signals**: Quant (momentum, breakouts), Technical (entry timing)
- **Agent weights**: Quant 50%, Technical 30%, Fundamental 20%
- **Risk limits**: Tighter VaR budget, faster stop-loss triggers
- **Best for**: Momentum plays, earnings reactions, technical breakouts

### Long-Term Mode

- **Horizon**: 3–6 months
- **Dominant signals**: Fundamental (DCF, valuation), Market Intelligence (macro themes)
- **Agent weights**: Fundamental 50%, Market Intel 30%, Quant 20%
- **Risk limits**: Wider stops, position building over time
- **Best for**: Value investing, macro thematic plays, sector rotation

---

## Human-in-the-Loop Gate

The system supports two execution modes that can be set per cycle:

### Manual Mode (human_in_loop = true)

The graph pauses at the human gate after the Trade Desk generates an order. A `HumanReviewRequest` is stored in the database and surfaced in the UI. The human has three options:

- **Approve**: Execute at the risk-manager-approved size
- **Resize + Approve**: Override the position size (enter a custom weight), then execute
- **Reject**: Cancel the trade; cycle terminates with status "rejected"

The review expires after 30 minutes. Expired reviews auto-reject.

### Auto Mode (auto_mode = true)

The human gate is bypassed. The Trade Desk still generates the `HumanReviewRequest` (for audit logging), but the graph immediately proceeds to execution. Use this for systematic strategies or during market hours when speed matters.

**Future roadmap**: The codebase is structured to easily support a third mode — "notification only" — where trades auto-execute but the human receives a push notification with the rationale.

---

## Database Schema

### `trade_cycles`
Tracks each CIO-initiated analysis cycle.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| mode | text | short_term or long_term |
| status | text | running, awaiting_human, executed, rejected, failed |
| cio_mandate | JSONB | Theme, watchlist, weights |
| auto_mode | boolean | Skip human gate |
| started_at | timestamptz | Cycle start time |
| completed_at | timestamptz | Cycle end time |

### `agent_memories`
All agent observations, analyses, signals, and reflections.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| agent_id | text | e.g. "quant_researcher" |
| cycle_id | UUID FK | Nullable (cross-cycle reflections have no cycle) |
| memory_type | text | observation, analysis, signal, reflection |
| content | text | Natural language memory content |
| embedding | vector(1536) | Semantic embedding for similarity search |
| importance_score | float | 0–1; scaled by trade outcome magnitude |
| metadata | JSONB | Agent-specific structured data |
| expires_at | timestamptz | Nullable; observation memories expire in 48–72h |

### `trade_outcomes`
Ground truth record of every executed trade.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| cycle_id | UUID FK | Parent cycle |
| symbol | text | Ticker symbol |
| direction | text | long or short |
| entry_price | float | Average fill price at open |
| exit_price | float | Average fill price at close (null if open) |
| qty | float | Shares/contracts |
| pnl_realized | float | Dollar P&L (null until closed) |
| pnl_pct | float | Percentage return (null until closed) |
| agent_signals | JSONB | Snapshot of all agent scores at entry |
| human_decision | text | approved, rejected, resized, or null (auto) |

### `human_reviews`
Audit record of every human gate interaction.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| cycle_id | UUID FK | Parent cycle |
| proposal_data | JSONB | Full trade proposal |
| technical_data | JSONB | Technical assessment |
| risk_data | JSONB | Risk assessment |
| estimated_notional | float | Dollar value of proposed trade |
| status | text | pending, approved, rejected, resized, expired |
| expires_at | timestamptz | Auto-reject deadline |

---

## Configuration Reference

All settings are environment variables loaded from `backend/.env`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | — | Your Anthropic API key |
| `DATABASE_URL` | ✅ | — | Async PostgreSQL URL |
| `DATABASE_URL_SYNC` | ✅ | — | Sync PostgreSQL URL (for Alembic) |
| `REDIS_URL` | — | redis://localhost:6379/0 | Redis connection URL |
| `ALPACA_API_KEY` | — | — | Alpaca paper trading key (falls back to mock) |
| `ALPACA_SECRET_KEY` | — | — | Alpaca secret key |
| `ALPACA_BASE_URL` | — | paper API | Alpaca base URL |
| `POLYGON_API_KEY` | — | — | Polygon.io key (falls back to yfinance) |
| `CIO_MODEL` | — | claude-opus-4-5 | Model for CIO agent |
| `RESEARCH_MODEL` | — | claude-sonnet-4-5 | Model for research agents |
| `RISK_MODEL` | — | claude-opus-4-5 | Model for risk manager |
| `EXECUTION_MODEL` | — | claude-sonnet-4-5 | Model for execution agents |
| `FRONTEND_URL` | — | http://localhost:5173 | CORS allowed origin |

---

## Going to Production

### 1. Switch from yfinance to Polygon.io
Set `POLYGON_API_KEY` in your environment. The market data tools will automatically prefer Polygon for real-time data.

### 2. Switch from paper to live trading
Change `ALPACA_BASE_URL` to `https://api.alpaca.markets` and use your live Alpaca keys. **Test thoroughly in paper mode first.**

### 3. Add OpenAI embeddings for memory
The memory service has a stub for OpenAI `text-embedding-3-small`. Set `OPENAI_API_KEY` and uncomment the real embedding call in `core/memory.py`. This dramatically improves memory retrieval quality over the deterministic fallback.

### 4. Deploy infrastructure
- **Database**: AWS RDS PostgreSQL 16 with pgvector extension enabled
- **Redis**: AWS ElastiCache or Upstash Redis
- **Backend**: AWS ECS, Railway, or Fly.io
- **Frontend**: Vercel or Netlify

### 5. Add a job scheduler
Use APScheduler (already in requirements) to run cycles on a schedule:
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler()
scheduler.add_job(run_daily_cycle, 'cron', hour=9, minute=30)  # market open
scheduler.start()
```

### 6. Add LangSmith tracing
Set `LANGCHAIN_API_KEY` and `LANGCHAIN_TRACING_V2=true` to get full agent trace visibility in LangSmith.

---

## Troubleshooting

**"pgvector extension not found"**
Your PostgreSQL install doesn't have pgvector. Use the Docker image `pgvector/pgvector:pg16` which has it pre-installed.

**"No module named 'anthropic'"**
Run `pip install -r requirements.txt` inside your virtual environment.

**Agents returning generic/incorrect analysis**
This usually means market data couldn't be fetched (rate limits or connectivity). Check yfinance is accessible from your machine. The agents will still run with whatever data is available.

**Human gate times out immediately**
The review expires after 30 minutes by default. If testing, approve the trade quickly or extend `expires_in_hours` in `trade_desk.py`.

**Frontend can't connect to backend**
Check that Vite's proxy config in `vite.config.ts` points to `http://localhost:8000`. If using Docker, ensure both containers are on the same network.

**Redis connection refused**
Start Redis: `docker run -d --name trading_redis -p 6379:6379 redis:7-alpine`

---

## License

MIT — use freely, trade responsibly.

> ⚠️ **Disclaimer**: This system is for educational and research purposes. It is not financial advice. Past performance of backtested signals does not guarantee future results. Always paper trade before going live with real capital.

---

## Indian Broker Integration — Zerodha & Upstox

### Overview

AlphaDesk supports two Indian brokers natively. Users connect their own Zerodha or Upstox account via OAuth2. Once connected, the system provides:

- Live portfolio with holdings, positions, and funds
- AI-powered portfolio analysis (sector allocation, concentration risk, rebalancing)
- Stock-level deep insight (hold/reduce/exit recommendation)
- Real-time alerts (circuit filters, P&L targets, stop-loss breaches, volume spikes)
- Order placement, modification, and cancellation
- GTT (Good-Till-Triggered) orders for Zerodha
- Portfolio value history charts
- WebSocket market data via KiteTicker / Upstox WS v2

### How OAuth Works

**Zerodha:**
1. User visits `GET /api/india/zerodha/login`
2. Redirected to Kite login portal — user enters Zerodha credentials + TOTP
3. Kite redirects back to `/api/india/zerodha/callback?request_token=XXX`
4. System exchanges `request_token` for `access_token`, stores encrypted in DB
5. Token is valid until 3:30 AM IST next day (Zerodha's policy)

**Upstox:**
1. User visits `GET /api/india/upstox/login`
2. Redirected to Upstox OAuth portal
3. Upstox redirects to `/api/india/upstox/callback?code=XXX`
4. System exchanges `code` for `access_token`, stores encrypted in DB
5. Token expires at 3:30 AM IST next day

**Direct token inject (for testing):**
```bash
# Zerodha
curl -X POST http://localhost:8000/api/india/zerodha/connect \
  -H "Content-Type: application/json" \
  -d '{"access_token": "your_token_here"}'

# Upstox
curl -X POST http://localhost:8000/api/india/upstox/connect \
  -H "Content-Type: application/json" \
  -d '{"access_token": "your_token_here"}'
```

### Indian Broker API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/india/zerodha/login` | Start Zerodha OAuth flow |
| GET | `/api/india/zerodha/callback` | OAuth callback (Kite redirect URL) |
| POST | `/api/india/zerodha/connect` | Direct token inject |
| GET | `/api/india/upstox/login` | Start Upstox OAuth flow |
| GET | `/api/india/upstox/callback` | OAuth callback (Upstox redirect URL) |
| POST | `/api/india/upstox/connect` | Direct token inject |
| GET | `/api/india/connections` | List all connected brokers |
| DELETE | `/api/india/connections/{broker}` | Disconnect a broker |
| GET | `/api/india/{broker}/portfolio` | Full portfolio (holdings + positions + funds) |
| GET | `/api/india/{broker}/holdings` | Delivery holdings (CNC) |
| GET | `/api/india/{broker}/positions` | Open intraday / F&O positions |
| GET | `/api/india/{broker}/funds` | Account funds & margin |
| GET | `/api/india/{broker}/orders` | Today's order book |
| POST | `/api/india/{broker}/orders` | Place an order |
| PUT | `/api/india/{broker}/orders/{id}` | Modify an order |
| DELETE | `/api/india/{broker}/orders/{id}` | Cancel an order |
| GET | `/api/india/{broker}/orders/{id}/trades` | Individual fills for an order |
| GET | `/api/india/{broker}/quote?symbols=NSE:RELIANCE` | Live quotes |
| GET | `/api/india/{broker}/market/open` | Market open/closed status |
| GET | `/api/india/{broker}/analysis` | AI portfolio analysis (Claude) |
| GET | `/api/india/{broker}/analysis/{symbol}` | AI insight for one stock |
| GET | `/api/india/{broker}/alerts` | Portfolio alerts |
| POST | `/api/india/{broker}/alerts/check` | Trigger manual alert scan |
| POST | `/api/india/{broker}/alerts/read` | Mark alerts as read |
| POST | `/api/india/{broker}/snapshot` | Save portfolio snapshot |
| GET | `/api/india/{broker}/snapshot/history` | Value history for charting |
| GET | `/api/india/zerodha/gtt` | List GTT orders (Zerodha) |
| DELETE | `/api/india/zerodha/gtt/{id}` | Delete GTT (Zerodha) |

### Place an Order (Indian)

```bash
curl -X POST http://localhost:8000/api/india/zerodha/orders \
  -H "Content-Type: application/json" \
  -d '{
    "exchange": "NSE",
    "tradingsymbol": "RELIANCE",
    "transaction_type": "BUY",
    "quantity": 5,
    "product": "CNC",
    "order_type": "LIMIT",
    "price": 2550.00,
    "validity": "DAY"
  }'
```

### Product Types

| Product | Full Name | Use Case |
|---|---|---|
| `CNC` | Cash and Carry | Delivery / long-term equity |
| `MIS` | Margin Intraday Square-off | Intraday only — auto-closed at 3:20 PM |
| `NRML` | Normal | F&O overnight positions |

### Order Types

| Type | When to use |
|---|---|
| `MARKET` | Immediate fill at best available price |
| `LIMIT` | Fill only at specified price or better |
| `SL` | Stop-Loss with limit price |
| `SL-M` | Stop-Loss Market (trigger → market order) |

### Alert Types

| Alert | Trigger |
|---|---|
| `price_above` | LTP crosses above a user-defined level |
| `price_below` | LTP drops below a user-defined level |
| `pnl_above` | Stock P&L exceeds +25% (configurable) |
| `pnl_below` | Stock P&L falls below -15% (configurable) |
| `circuit_upper` | Upper circuit filter hit (buying halted) |
| `circuit_lower` | Lower circuit filter hit (selling halted) |
| `volume_spike` | Unusual intraday volume detected |
| `ai_insight` | Claude-generated portfolio insight |

### Kite App Setup (Zerodha)

1. Register at https://developers.kite.trade
2. Create an app → get API Key and API Secret
3. Set redirect URL to: `http://localhost:8000/api/india/zerodha/callback`
4. Add to `.env`:
```
ZERODHA_API_KEY=your_key
ZERODHA_API_SECRET=your_secret
ZERODHA_REDIRECT_URI=http://localhost:8000/api/india/zerodha/callback
```

### Upstox App Setup

1. Register at https://developer.upstox.com
2. Create an app → get API Key and Secret
3. Set redirect URL to: `http://localhost:8000/api/india/upstox/callback`
4. Add to `.env`:
```
UPSTOX_API_KEY=your_key
UPSTOX_API_SECRET=your_secret
UPSTOX_REDIRECT_URI=http://localhost:8000/api/india/upstox/callback
```

### Security

User access tokens are encrypted with AES-256-GCM before storage. The encryption key is derived from `SECRET_KEY` in `.env`. Install the `cryptography` package (already in requirements.txt) for full encryption — without it, the system falls back to base64 (NOT secure for production).

```bash
pip install cryptography   # already included in requirements.txt
```

Always use a strong, random `SECRET_KEY` in production:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Indian Market Schedule

- **Pre-open**: 9:00–9:15 AM IST
- **Regular session**: 9:15 AM–3:30 PM IST
- **Post-close**: 3:40–4:00 PM IST
- **After Market Orders (AMO)**: Available outside market hours with `variety=amo`
- **F&O expiry**: Last Thursday of every month
- **Settlement**: T+1 for equity (from 2023)

NSE holidays for 2025 are pre-loaded in `broker/indian/base_indian.py` and are used to determine market open/closed status.
