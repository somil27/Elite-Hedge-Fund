BEGIN;

CREATE TABLE rl_signal_weights (
    id UUID DEFAULT uuid_generate_v4() NOT NULL, 
    signal_key VARCHAR(60) NOT NULL, 
    market VARCHAR(20) DEFAULT 'us' NOT NULL, 
    weight FLOAT DEFAULT '0.167' NOT NULL, 
    total_reward FLOAT DEFAULT '0.0' NOT NULL, 
    pull_count INTEGER DEFAULT '0' NOT NULL, 
    last_updated TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    CONSTRAINT uq_rl_signal_market UNIQUE (signal_key, market)
);

CREATE TABLE backtest_results (
    id UUID DEFAULT uuid_generate_v4() NOT NULL, 
    strategy VARCHAR(50) NOT NULL, 
    symbols JSONB NOT NULL, 
    start_date VARCHAR(10) NOT NULL, 
    end_date VARCHAR(10) NOT NULL, 
    mode VARCHAR(20) NOT NULL, 
    market VARCHAR(20) NOT NULL, 
    initial_capital FLOAT NOT NULL, 
    final_capital FLOAT NOT NULL, 
    total_return_pct FLOAT, 
    annualised_return FLOAT, 
    sharpe_ratio FLOAT, 
    max_drawdown_pct FLOAT, 
    win_rate FLOAT, 
    profit_factor FLOAT, 
    total_trades INTEGER, 
    avg_hold_days FLOAT, 
    equity_curve JSONB DEFAULT '[]', 
    agent_attribution JSONB DEFAULT '{}', 
    walkforward JSONB DEFAULT '[]', 
    run_by VARCHAR(100), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id)
);

CREATE INDEX ix_bt_strategy ON backtest_results (strategy);

CREATE INDEX ix_bt_created ON backtest_results (created_at);

CREATE TABLE backtest_trades (
    id UUID DEFAULT uuid_generate_v4() NOT NULL, 
    backtest_id UUID NOT NULL, 
    symbol VARCHAR(20) NOT NULL, 
    direction VARCHAR(10) NOT NULL, 
    entry_date VARCHAR(10) NOT NULL, 
    exit_date VARCHAR(10), 
    entry_price FLOAT NOT NULL, 
    exit_price FLOAT, 
    qty FLOAT NOT NULL, 
    pnl FLOAT DEFAULT '0', 
    pnl_pct FLOAT DEFAULT '0', 
    hold_days INTEGER DEFAULT '0', 
    exit_reason VARCHAR(50), 
    agent_signals JSONB DEFAULT '{}', 
    composite_score FLOAT DEFAULT '0', 
    PRIMARY KEY (id), 
    FOREIGN KEY(backtest_id) REFERENCES backtest_results (id) ON DELETE CASCADE
);

CREATE INDEX ix_btt_backtest ON backtest_trades (backtest_id);

CREATE INDEX ix_btt_symbol ON backtest_trades (symbol);

CREATE TABLE portfolio_definitions (
    id UUID DEFAULT uuid_generate_v4() NOT NULL, 
    portfolio_id VARCHAR(50) NOT NULL, 
    user_id UUID, 
    name VARCHAR(100) NOT NULL, 
    strategy VARCHAR(50) NOT NULL, 
    allocation_pct FLOAT NOT NULL, 
    mode VARCHAR(20) NOT NULL, 
    market VARCHAR(20) NOT NULL, 
    auto_mode BOOLEAN DEFAULT 'false', 
    active BOOLEAN DEFAULT 'true', 
    description TEXT, 
    max_drawdown_pct FLOAT DEFAULT '10.0', 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    updated_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    UNIQUE (portfolio_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE news_events (
    id UUID DEFAULT uuid_generate_v4() NOT NULL, 
    cycle_id UUID, 
    symbol VARCHAR(20), 
    event_type VARCHAR(50) NOT NULL, 
    headline TEXT NOT NULL, 
    sentiment FLOAT, 
    magnitude VARCHAR(10), 
    source VARCHAR(100), 
    metadata JSONB DEFAULT '{}', 
    event_time TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    FOREIGN KEY(cycle_id) REFERENCES trade_cycles (id) ON DELETE SET NULL
);

CREATE INDEX ix_news_symbol ON news_events (symbol);

CREATE INDEX ix_news_type ON news_events (event_type);

CREATE INDEX ix_news_time ON news_events (event_time);

COMMIT;
