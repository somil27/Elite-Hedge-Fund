"""
Market data tools used by research agents.
Uses yfinance for price data with Polygon.io as optional upgrade.
"""
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import structlog

logger = structlog.get_logger()


def _format_yf_symbol(symbol: str, market: str = None) -> str:
    """Format symbol for yfinance, appending .NS if in Indian market."""
    if symbol.endswith(".NS") or symbol.endswith(".BO") or symbol.startswith("^"):
        return symbol
    if market == "india":
        return f"{symbol}.NS"
    return symbol


_session = None

def get_session():
    global _session
    if _session is None:
        import requests
        _session = requests.Session()
        _session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        })
    return _session


def yf_ticker(symbol: str, market: str = None) -> yf.Ticker:
    """Get a yfinance Ticker instance with proper suffix and headers."""
    yf_sym = _format_yf_symbol(symbol, market)
    return yf.Ticker(yf_sym, session=get_session())


async def get_market_snapshot(symbols: list[str], market: str = None) -> dict:
    """Get current price, volume, and 1-day change for a list of symbols."""
    def _fetch():
        result = {}
        for sym in symbols:
            try:
                ticker = yf_ticker(sym, market)
                
                # Fetch history first (highly reliable chart endpoint)
                try:
                    hist = ticker.history(period="2d")
                except Exception as he:
                    logger.warning("snapshot_history_error", symbol=sym, error=str(he))
                    hist = pd.DataFrame()

                # Try to access fast_info safely
                info = None
                try:
                    info = ticker.fast_info
                except Exception as ie:
                    logger.warning("snapshot_fast_info_init_error", symbol=sym, error=str(ie))

                # Extract price information
                if not hist.empty:
                    curr_close = float(hist["Close"].iloc[-1])
                    if len(hist) >= 2:
                        prev_close = float(hist["Close"].iloc[-2])
                        change_pct = (curr_close - prev_close) / prev_close * 100
                    else:
                        prev_close = curr_close
                        change_pct = 0.0
                else:
                    # Fallback to fast_info last_price if history is empty
                    curr_close = 0.0
                    if info is not None:
                        try:
                            curr_close = float(info.last_price)
                        except Exception:
                            pass
                    prev_close = curr_close
                    change_pct = 0.0

                # Extract volume safely
                volume = 0
                if info is not None:
                    try:
                        volume = int(info.three_month_average_volume or 0)
                    except Exception:
                        pass
                if volume == 0 and not hist.empty:
                    try:
                        volume = int(hist["Volume"].iloc[-1])
                    except Exception:
                        pass

                # Extract market cap safely
                market_cap = None
                if info is not None:
                    try:
                        market_cap = getattr(info, "market_cap", None)
                    except Exception:
                        pass

                result[sym] = {
                    "price": round(curr_close, 2),
                    "prev_close": round(prev_close, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": volume,
                    "market_cap": market_cap,
                }
            except Exception as e:
                logger.warning("snapshot_error", symbol=sym, error=str(e))
                result[sym] = {"price": 0, "error": str(e)}
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def get_fundamental_data(symbol: str, market: str = None) -> dict:
    """Fetch fundamental financial data for a symbol."""
    def _fetch():
        try:
            ticker = yf_ticker(symbol, market)
            info = ticker.info
            return {
                "symbol": symbol,
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
                "market_cap": info.get("marketCap"),
                "pe_trailing": info.get("trailingPE"),
                "pe_forward": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "price_to_book": info.get("priceToBook"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "gross_margins": info.get("grossMargins"),
                "operating_margins": info.get("operatingMargins"),
                "profit_margins": info.get("profitMargins"),
                "return_on_equity": info.get("returnOnEquity"),
                "debt_to_equity": info.get("debtToEquity"),
                "free_cashflow": info.get("freeCashflow"),
                "total_revenue": info.get("totalRevenue"),
                "recommendation": info.get("recommendationKey"),
                "target_mean_price": info.get("targetMeanPrice"),
                "analyst_count": info.get("numberOfAnalystOpinions"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "beta": info.get("beta"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
            }
        except Exception as e:
            logger.warning("fundamental_fetch_error", symbol=symbol, error=str(e))
            return {"symbol": symbol, "error": str(e), "current_price": 100.0}

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def get_price_history(symbol: str, period: str = "60d", market: str = None) -> pd.DataFrame:
    """Fetch OHLCV history for a symbol."""
    def _fetch():
        try:
            ticker = yf_ticker(symbol, market)
            hist = ticker.history(period=period, interval="1d")
            return hist
        except Exception as e:
            logger.warning("history_fetch_error", symbol=symbol, error=str(e))
            return pd.DataFrame()

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute common technical indicators from OHLCV data."""
    if df.empty or len(df) < 20:
        return {"error": "insufficient data", "bars": 0}

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # Moving averages
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(min(50, len(close))).mean()
    ma200 = close.rolling(min(200, len(close))).mean()

    # RSI (14-period)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # MACD (12/26/9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    # Bollinger Bands (20, 2)
    bb_mid = ma20
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # ATR (14-period)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # Volume analysis
    avg_volume = volume.rolling(20).mean()
    vol_ratio = volume / avg_volume

    curr = close.iloc[-1]
    prev = close.iloc[-2] if len(close) > 1 else curr

    def safe(val):
        if val is None:
            return None
        try:
            v = float(val)
            return round(v, 4) if not (np.isnan(v) or np.isinf(v)) else None
        except Exception:
            return None

    return {
        "symbol": df.index.name or "unknown",
        "bars": len(df),
        "current_price": safe(curr),
        "prev_close": safe(prev),
        "change_pct": safe((curr - prev) / prev * 100) if prev else None,
        "ma20": safe(ma20.iloc[-1]),
        "ma50": safe(ma50.iloc[-1]),
        "ma200": safe(ma200.iloc[-1]),
        "price_vs_ma20_pct": safe((curr - ma20.iloc[-1]) / ma20.iloc[-1] * 100),
        "price_vs_ma50_pct": safe((curr - ma50.iloc[-1]) / ma50.iloc[-1] * 100),
        "rsi_14": safe(rsi.iloc[-1]),
        "macd": safe(macd.iloc[-1]),
        "macd_signal": safe(macd_signal.iloc[-1]),
        "macd_histogram": safe(macd_hist.iloc[-1]),
        "bb_upper": safe(bb_upper.iloc[-1]),
        "bb_lower": safe(bb_lower.iloc[-1]),
        "bb_pct": safe((curr - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])),
        "atr_14": safe(atr.iloc[-1]),
        "volume_ratio": safe(vol_ratio.iloc[-1]),
        "52w_high": safe(high.tail(252).max()),
        "52w_low": safe(low.tail(252).min()),
        "pct_from_52w_high": safe((curr - high.tail(252).max()) / high.tail(252).max() * 100),
        "recent_closes": [safe(x) for x in close.tail(10).tolist()],
    }
