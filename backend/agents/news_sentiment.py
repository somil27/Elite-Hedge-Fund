"""
News & Sentiment Agent — Phase 1
Consumes live news feeds, earnings call transcripts, SEC filings.
Produces per-symbol NLP sentiment scores and fires event alerts.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
import httpx
from tools.market_data import yf_ticker
from agents.base import BaseAgent
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a financial news analyst at an AI trading firm.
You analyse news headlines, earnings call summaries, and market events
to produce sentiment scores and identify high-impact catalysts.

Your output is always structured JSON. You look for:
- Earnings surprises (beat/miss vs consensus)
- Management guidance changes (raised/lowered/withdrawn)
- Regulatory events (FDA approvals, SEBI orders, government policy)
- Macro catalysts (rate decisions, GDP prints, inflation data)
- Corporate actions (M&A, buybacks, insider transactions)
- Geopolitical events affecting specific sectors

Sentiment scale: -1.0 (strongly negative) to +1.0 (strongly positive).
Be precise. Base scores on facts, not speculation."""


class NewsSentimentAgent(BaseAgent):
    def __init__(self):
        super().__init__("news_sentiment", tier="fast")

    async def run(self, state: dict, conn) -> dict:
        mandate = state.get("mandate", {})
        watchlist = mandate.get("watchlist", [])
        cycle_id = state.get("cycle_id")
        market = state.get("market", "us")

        # Recall past news observations
        memories = await self.recall(
            conn, "news sentiment earnings event catalyst",
            memory_types=["observation", "reflection"], limit=4,
        )

        # Fetch news for watchlist symbols
        news_data = await self._fetch_news(watchlist, market)

        user_msg = f"""
Today: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC
Market: {market.upper()}
Watchlist: {watchlist}
Mode: {mandate.get('mode', 'short_term')}

Recent news and events fetched:
{json.dumps(news_data, indent=2)}

Past observations from memory:
{self._format_memories(memories)}

Analyse all news and produce a structured report.
Return JSON with this exact structure:
{{
  "overall_sentiment": 0.2,
  "market_moving_events": [
    {{
      "symbol": "NVDA",
      "event_type": "earnings_beat|earnings_miss|guidance_raised|guidance_lowered|regulatory|macro|corporate_action|analyst_upgrade|analyst_downgrade",
      "headline": "brief headline",
      "sentiment_score": 0.8,
      "magnitude": "high|medium|low",
      "trading_implication": "one sentence on how this affects trading",
      "source": "Reuters|Bloomberg|SEC|Earnings call"
    }}
  ],
  "symbol_sentiment": {{
    "NVDA": {{"score": 0.75, "articles_count": 3, "key_theme": "AI demand surge"}},
    "AAPL": {{"score": -0.1, "articles_count": 2, "key_theme": "China revenue risk"}}
  }},
  "sector_sentiment": {{
    "Technology": 0.4,
    "Energy": -0.2
  }},
  "macro_alerts": ["Fed meeting minutes hawkish", "CPI print above expectations"],
  "earnings_calendar": [
    {{"symbol": "MSFT", "expected_date": "2025-01-29", "consensus_eps": 3.12}}
  ],
  "watchlist_flags": {{
    "NVDA": "strong_positive_catalyst",
    "AAPL": "monitor_closely"
  }}
}}"""

        try:
            result = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=2500)
            result["cycle_id"] = cycle_id
            result["fetched_at"] = datetime.utcnow().isoformat()

            # Store significant events as memories
            for event in result.get("market_moving_events", [])[:3]:
                await self.remember(
                    conn, "observation",
                    f"[{event.get('event_type')}] {event.get('symbol')}: {event.get('headline')} "
                    f"(sentiment={event.get('sentiment_score')}, magnitude={event.get('magnitude')})",
                    metadata=event, cycle_id=cycle_id,
                    importance=0.8 if event.get("magnitude") == "high" else 0.5,
                    expires_in_hours=72,
                )

            logger.info("news_sentiment_complete",
                        events=len(result.get("market_moving_events", [])),
                        overall=result.get("overall_sentiment"))
            return {"news_sentiment": result}

        except Exception as e:
            logger.error("news_sentiment_error", error=str(e))
            return {"news_sentiment": {"error": str(e), "overall_sentiment": 0}}

    async def _fetch_news(self, symbols: list[str], market: str) -> dict:
        """Fetch news from yfinance and free RSS feeds."""
        news_data = {}

        async def fetch_symbol_news(symbol: str):
            try:
                def _sync():
                    ticker = yf_ticker(symbol, market)
                    news = ticker.news or []
                    return [
                        {
                            "title":     n.get("content", {}).get("title", n.get("title", "")),
                            "publisher": n.get("content", {}).get("provider", {}).get("displayName",
                                         n.get("publisher", "")),
                            "link":      n.get("content", {}).get("canonicalUrl", {}).get("url",
                                         n.get("link", "")),
                            "published": n.get("content", {}).get("pubDate",
                                         n.get("providerPublishTime", "")),
                        }
                        for n in news[:5]
                    ]
                return await asyncio.get_event_loop().run_in_executor(None, _sync)
            except Exception as e:
                logger.warning("news_fetch_failed", symbol=symbol, error=str(e))
                return []

        results = await asyncio.gather(*[fetch_symbol_news(s) for s in symbols[:6]])
        for symbol, articles in zip(symbols[:6], results):
            news_data[symbol] = articles

        # Also fetch general market news via RSS
        market_news = await self._fetch_rss_headlines(market)
        news_data["_market"] = market_news

        return news_data

    async def _fetch_rss_headlines(self, market: str) -> list[dict]:
        """Fetch general market headlines from free RSS."""
        feeds = {
            "us":    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",
            "india": "https://economictimes.indiatimes.com/markets/stocks/rss.cms",
        }
        url = feeds.get(market, feeds["us"])
        headlines = []
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(url, follow_redirects=True)
                if r.status_code == 200:
                    import re
                    titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', r.text)[:6]
                    if not titles:
                        titles = re.findall(r'<title>(.*?)</title>', r.text)[1:7]
                    headlines = [{"title": t.strip(), "publisher": "Market News"} for t in titles if t.strip()]
        except Exception as e:
            logger.debug("rss_fetch_failed", error=str(e))
        return headlines
