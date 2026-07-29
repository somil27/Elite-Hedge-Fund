from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── LLM Provider ─────────────────────────────────────────
    # Set ONE of the three keys below. The system auto-detects which to use.
    # Override auto-detection with LLM_PROVIDER=anthropic|openai|gemini
    llm_provider: str = ""          # leave blank for auto-detect

    anthropic_api_key: str = ""     # → uses Claude (opus for strong, sonnet for fast)
    openai_api_key: str    = ""     # → uses GPT-4o (gpt-4o for strong, gpt-4o-mini for fast)
    gemini_api_key: str    = ""     # → uses Gemini (1.5-pro for strong, 1.5-flash for fast)

    # ── Database ──────────────────────────────────────────────
    database_url:      str = "postgresql+asyncpg://trader:trader_pass@postgres:5432/trading_system"
    
    @property
    def database_url_sync(self) -> str:
        # Generate sync URL dynamically from the async/injected URL
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql://", 1)
        return url

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Broker Selection ──────────────────────────────────────
    broker:       str   = "mock"   # mock | alpaca | ibkr
    alpaca_paper: bool  = True

    # Alpaca
    alpaca_api_key:    str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url:   str = "https://paper-api.alpaca.markets"

    # IBKR
    ibkr_paper: bool = True
    ibkr_host:  str  = "127.0.0.1"
    ibkr_port:  int  = 7497

    # Mock broker
    mock_initial_cash: float = 100_000.0
    mock_slippage_bps: float = 2.0

    # ── India Broker APIs ─────────────────────────────────────
    zerodha_api_key: str = ""
    zerodha_api_secret: str = ""
    
    @property
    def zerodha_redirect_uri(self) -> str:
        import os
        render_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_url:
            return f"{render_url}/api/india/zerodha/callback"
        return "http://localhost:8000/api/india/zerodha/callback"
        
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    
    @property
    def upstox_redirect_uri(self) -> str:
        import os
        render_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_url:
            return f"{render_url}/api/india/upstox/callback"
        return "http://localhost:8000/api/india/upstox/callback"

    # Market data
    polygon_api_key: str = ""

    # ── App ───────────────────────────────────────────────────
    app_env:      str = "development"
    log_level:    str = "INFO"
    secret_key:   str = "changeme-use-a-random-32-char-string"
    frontend_url: str = "http://localhost:5173"

    # ── Google OAuth ──────────────────────────────────────────
    google_client_id:     str = ""
    google_client_secret: str = ""
    
    @property
    def google_redirect_uri(self) -> str:
        import os
        render_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_url:
            return f"{render_url}/api/auth/google/callback"
        return "http://localhost:8000/api/auth/google/callback"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
