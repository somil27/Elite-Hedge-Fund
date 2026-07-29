"""
Upstox v2 Broker Implementation
Full integration using Upstox Python SDK v2 + WebSocket market data feed.

OAuth flow:
  1. Direct user to: GET /api/broker/upstox/login?user_id=<uid>
  2. User authorises on Upstox portal → redirected to your callback URL
  3. Callback exchanges code for access_token (expires at 3:30 AM IST daily)
  4. Store encrypted access_token per user in DB

Requires:
  pip install upstox-python-sdk
  UPSTOX_API_KEY and UPSTOX_API_SECRET in .env
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
import structlog

from broker.indian.base_indian import (
    IndianOrderRequest, IndianOrder, IndianPosition, Holding,
    MarketQuote, IndianFunds, Exchange, ProductType,
    MARKET_OPEN_IST, MARKET_CLOSE_IST, NSE_HOLIDAYS_2025,
)

logger = structlog.get_logger()

OrderUpdateCallback = Callable[[IndianOrder], Awaitable[None]]

# Upstox product code mapping
PRODUCT_MAP = {
    "CNC":  "D",    # Delivery
    "MIS":  "I",    # Intraday
    "NRML": "M",    # Normal (F&O)
}

# Upstox exchange mapping
EXCHANGE_MAP = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FO",
    "BFO": "BSE_FO",
    "CDS": "NSE_CD",
    "MCX": "MCX_FO",
}


class UpstoxBroker:
    """
    Upstox v2 broker.
    One instance per authenticated user.
    """

    def __init__(self, api_key: str, api_secret: str,
                 redirect_uri: str, access_token: str = ""):
        self.api_key      = api_key
        self.api_secret   = api_secret
        self.redirect_uri = redirect_uri
        self.access_token = access_token
        self._order_api   = None
        self._portfolio_api = None
        self._market_api  = None
        self._user_api    = None
        self._ws          = None
        self._connected   = False
        self._order_callbacks: list[OrderUpdateCallback] = []

    # ── OAuth helpers ─────────────────────────────────────────

    def get_login_url(self, state: str = "") -> str:
        """Generate Upstox OAuth2 login URL."""
        base = "https://api.upstox.com/v2/login/authorization/dialog"
        return (
            f"{base}?response_type=code"
            f"&client_id={self.api_key}"
            f"&redirect_uri={self.redirect_uri}"
            f"&state={state}"
        )

    async def exchange_code(self, auth_code: str) -> str:
        """
        Exchange the OAuth2 authorization code for an access token.
        Returns the access_token string. Store it encrypted in DB.
        """
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.upstox.com/v2/login/authorization/token",
                data={
                    "code":          auth_code,
                    "client_id":     self.api_key,
                    "client_secret": self.api_secret,
                    "redirect_uri":  self.redirect_uri,
                    "grant_type":    "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            logger.info("upstox_token_exchanged")
            return self.access_token

    # ── Connection ────────────────────────────────────────────

    async def connect(self) -> None:
        if not self.access_token:
            raise RuntimeError("No access_token. Complete OAuth flow first.")
        try:
            import upstox_client
        except ImportError:
            raise ImportError("pip install upstox-python-sdk")

        config = upstox_client.Configuration()
        config.access_token = self.access_token

        api_client = upstox_client.ApiClient(config)
        self._order_api     = upstox_client.OrderApi(api_client)
        self._portfolio_api = upstox_client.PortfolioApi(api_client)
        self._market_api    = upstox_client.MarketQuoteApi(api_client)
        self._user_api      = upstox_client.UserApi(api_client)

        # Verify connection
        def _verify():
            return self._user_api.get_profile("2.0")
        profile = await asyncio.get_event_loop().run_in_executor(None, _verify)
        self._connected = True
        logger.info("upstox_connected",
                    user=getattr(profile.data, "email", "unknown"))

    async def disconnect(self) -> None:
        if self._ws:
            await self._ws.disconnect()
        self._connected = False
        logger.info("upstox_disconnected")

    def _ensure(self):
        if not self._connected:
            raise RuntimeError("UpstoxBroker not connected.")

    # ── Funds & Account ───────────────────────────────────────

    async def get_funds(self) -> IndianFunds:
        self._ensure()
        def _fetch():
            return self._user_api.get_user_fund_margin(api_version="2.0",
                                                       segment="SEC")
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        data = resp.data if resp.data else {}
        equity = data.equity if hasattr(data, "equity") else {}
        return IndianFunds(
            available_cash=getattr(equity, "available_margin", 0) or 0,
            available_margin=getattr(equity, "available_margin", 0) or 0,
            used_margin=getattr(equity, "used_margin", 0) or 0,
            net=getattr(equity, "net_margin", 0) or 0,
        )

    async def get_profile(self) -> dict:
        self._ensure()
        def _fetch():
            return self._user_api.get_profile("2.0")
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        d = resp.data
        return {
            "name":    getattr(d, "user_name", ""),
            "email":   getattr(d, "email", ""),
            "user_id": getattr(d, "user_id", ""),
            "broker":  "upstox",
        }

    # ── Orders ────────────────────────────────────────────────

    async def place_order(self, req: IndianOrderRequest) -> str:
        self._ensure()
        def _place():
            import upstox_client
            body = upstox_client.PlaceOrderRequest(
                quantity=req.quantity,
                product=PRODUCT_MAP.get(req.product.value, "D"),
                validity=req.validity.value,
                price=req.price,
                tag=req.tag or "alphadeskv1",
                instrument_token=f"{EXCHANGE_MAP.get(req.exchange.value, 'NSE_EQ')}|{req.tradingsymbol}",
                order_type=req.order_type,
                transaction_type=req.transaction_type,
                disclosed_quantity=req.disclosed_quantity,
                trigger_price=req.trigger_price,
                is_amo=req.variety == "amo",
            )
            resp = self._order_api.place_order(body, api_version="2.0")
            return resp.data.order_id
        order_id = await asyncio.get_event_loop().run_in_executor(None, _place)
        logger.info("upstox_order_placed",
                    order_id=order_id,
                    symbol=req.tradingsymbol,
                    txn=req.transaction_type,
                    qty=req.quantity)
        return str(order_id)

    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
        validity: Optional[str] = None,
    ) -> str:
        self._ensure()
        def _modify():
            import upstox_client
            body = upstox_client.ModifyOrderRequest(
                order_id=order_id,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                order_type=order_type,
                validity=validity or "DAY",
                disclosed_quantity=0,
            )
            resp = self._order_api.modify_order(body, api_version="2.0")
            return resp.data.order_id
        return str(await asyncio.get_event_loop().run_in_executor(None, _modify))

    async def cancel_order(self, order_id: str) -> str:
        self._ensure()
        def _cancel():
            resp = self._order_api.cancel_order(order_id, api_version="2.0")
            return resp.data.order_id
        return str(await asyncio.get_event_loop().run_in_executor(None, _cancel))

    async def get_orders(self) -> list[IndianOrder]:
        self._ensure()
        def _fetch():
            return self._order_api.get_order_book(api_version="2.0")
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [self._parse_order(o) for o in (resp.data or [])]

    async def get_order(self, order_id: str) -> IndianOrder:
        self._ensure()
        def _fetch():
            return self._order_api.get_order_details(
                order_id=order_id, api_version="2.0"
            )
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return self._parse_order(resp.data)

    async def get_order_trades(self, order_id: str) -> list[dict]:
        self._ensure()
        def _fetch():
            return self._order_api.get_trades_by_order(
                order_id=order_id, api_version="2.0"
            )
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [vars(t) for t in (resp.data or [])]

    # ── Positions & Holdings ──────────────────────────────────

    async def get_positions(self) -> list[IndianPosition]:
        self._ensure()
        def _fetch():
            return self._portfolio_api.get_positions(api_version="2.0")
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [self._parse_position(p) for p in (resp.data or [])]

    async def get_holdings(self) -> list[Holding]:
        self._ensure()
        def _fetch():
            return self._portfolio_api.get_holdings(api_version="2.0")
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [self._parse_holding(h) for h in (resp.data or [])]

    async def close_position(
        self,
        tradingsymbol: str,
        exchange: Exchange,
        product: ProductType,
        quantity: int,
    ) -> str:
        positions = await self.get_positions()
        pos = next(
            (p for p in positions
             if p.tradingsymbol == tradingsymbol
             and p.exchange in (exchange.value, EXCHANGE_MAP.get(exchange.value, ""))),
            None,
        )
        if not pos:
            raise ValueError(f"No position for {tradingsymbol}")
        txn = "SELL" if pos.quantity > 0 else "BUY"
        req = IndianOrderRequest(
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=txn,
            quantity=abs(quantity or pos.quantity),
            product=product,
            order_type="MARKET",
        )
        return await self.place_order(req)

    # ── Market Data ───────────────────────────────────────────

    async def get_quote(
        self,
        instrument_keys: list[str],   # ["NSE_EQ|RELIANCE", "BSE_EQ|500325"]
    ) -> dict[str, MarketQuote]:
        self._ensure()
        keys_str = ",".join(instrument_keys)
        def _fetch():
            return self._market_api.get_full_market_quote(
                symbol=keys_str, api_version="2.0"
            )
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        result = {}
        for key, q in (resp.data or {}).items():
            ohlc = getattr(q, "ohlc", None)
            result[key] = MarketQuote(
                instrument_token=0,
                tradingsymbol=key.split("|")[-1] if "|" in key else key,
                last_price=getattr(q, "last_price", 0) or 0,
                open=getattr(ohlc, "open", 0) if ohlc else 0,
                high=getattr(ohlc, "high", 0) if ohlc else 0,
                low=getattr(ohlc, "low", 0) if ohlc else 0,
                close=getattr(ohlc, "close", 0) if ohlc else 0,
                volume=getattr(q, "volume", 0) or 0,
                oi=getattr(q, "oi", 0) or 0,
                upper_circuit=getattr(q, "upper_circuit_limit", 0) or 0,
                lower_circuit=getattr(q, "lower_circuit_limit", 0) or 0,
                change=getattr(q, "net_change", 0) or 0,
                timestamp=datetime.now(timezone.utc),
            )
        return result

    async def get_historical(
        self,
        instrument_key: str,    # "NSE_EQ|RELIANCE"
        interval: str,          # 1minute|30minute|day|week|month
        from_date: str,         # "YYYY-MM-DD"
        to_date: str,
    ) -> list[dict]:
        self._ensure()
        def _fetch():
            return self._market_api.get_historical_candle_data1(
                instrument_key=instrument_key,
                interval=interval,
                to_date=to_date,
                from_date=from_date,
                api_version="2.0",
            )
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        candles = getattr(resp.data, "candles", []) if resp.data else []
        return [
            {
                "timestamp": c[0], "open": c[1], "high": c[2],
                "low": c[3], "close": c[4], "volume": c[5],
            }
            for c in candles
        ]

    # ── WebSocket market data ─────────────────────────────────

    async def subscribe_market_data(
        self,
        instrument_keys: list[str],
        on_tick: Callable,
        mode: str = "full",   # "ltpc" | "option_greek" | "full"
    ) -> None:
        """Subscribe to Upstox WebSocket market data feed v2."""
        try:
            import upstox_client
        except ImportError:
            raise ImportError("pip install upstox-python-sdk")

        streamer = upstox_client.MarketDataStreamer(
            upstox_client.ApiClient(
                upstox_client.Configuration(access_token=self.access_token)
            ),
            instrument_keys,
            mode,
        )

        async def on_message(message):
            await on_tick(message)

        streamer.on("message", on_message)
        streamer.on("error", lambda e: logger.error("upstox_ws_error", error=str(e)))
        asyncio.create_task(streamer.connect())
        self._ws = streamer
        logger.info("upstox_ws_subscribed", instruments=instrument_keys)

    async def subscribe_order_updates(self, callback: OrderUpdateCallback) -> None:
        """Subscribe to Upstox WebSocket order updates."""
        self._order_callbacks.append(callback)
        try:
            import upstox_client
            streamer = upstox_client.PortfolioDataStreamer(
                upstox_client.ApiClient(
                    upstox_client.Configuration(access_token=self.access_token)
                )
            )

            async def on_order_update(data):
                try:
                    order = self._parse_order(vars(data.get("data", {})))
                    for cb in self._order_callbacks:
                        await cb(order)
                except Exception as e:
                    logger.error("upstox_order_cb_error", error=str(e))

            streamer.on("message", on_order_update)
            asyncio.create_task(streamer.connect())
            logger.info("upstox_order_stream_started")
        except Exception as e:
            logger.warning("upstox_order_stream_error", error=str(e))

    def is_market_open(self) -> bool:
        import pytz
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(ist)
        today_str = now_ist.strftime("%Y-%m-%d")
        if today_str in NSE_HOLIDAYS_2025:
            return False
        if now_ist.weekday() >= 5:
            return False
        t = now_ist.time()
        return MARKET_OPEN_IST <= t <= MARKET_CLOSE_IST

    # ── Internal parsers ──────────────────────────────────────

    def _parse_order(self, o) -> IndianOrder:
        if hasattr(o, "__dict__"):
            o = vars(o)
        return IndianOrder(
            order_id=str(o.get("order_id", "") or ""),
            exchange=str(o.get("exchange", "") or ""),
            tradingsymbol=str(o.get("trading_symbol", o.get("tradingsymbol", "")) or ""),
            transaction_type=str(o.get("transaction_type", "") or ""),
            quantity=int(o.get("quantity", 0) or 0),
            filled_quantity=int(o.get("filled_quantity", 0) or 0),
            pending_quantity=int(o.get("quantity", 0) or 0) - int(o.get("filled_quantity", 0) or 0),
            product=str(o.get("product", "D") or "D"),
            order_type=str(o.get("order_type", "MARKET") or "MARKET"),
            price=float(o.get("price", 0) or 0),
            trigger_price=float(o.get("trigger_price", 0) or 0),
            average_price=float(o.get("average_price", 0) or 0),
            status=str(o.get("status", "open") or "open").upper(),
            status_message=str(o.get("status_message", "") or ""),
            order_timestamp=o.get("order_created_at") or o.get("order_timestamp"),
        )

    def _parse_position(self, p) -> IndianPosition:
        if hasattr(p, "__dict__"):
            p = vars(p)
        qty = int(p.get("quantity", 0) or 0)
        return IndianPosition(
            exchange=str(p.get("exchange", "") or ""),
            tradingsymbol=str(p.get("trading_symbol", p.get("tradingsymbol", "")) or ""),
            product=str(p.get("product", "") or ""),
            quantity=qty,
            buy_quantity=int(p.get("buy_quantity", 0) or 0),
            sell_quantity=int(p.get("sell_quantity", 0) or 0),
            buy_price=float(p.get("buy_price", 0) or 0),
            sell_price=float(p.get("sell_price", 0) or 0),
            last_price=float(p.get("last_price", 0) or 0),
            close_price=float(p.get("close_price", 0) or 0),
            pnl=float(p.get("pnl", 0) or 0),
            unrealised=float(p.get("unrealised", 0) or 0),
            realised=float(p.get("realised", 0) or 0),
        )

    def _parse_holding(self, h) -> Holding:
        if hasattr(h, "__dict__"):
            h = vars(h)
        avg   = float(h.get("average_price", 0) or 0)
        last  = float(h.get("last_price", 0) or 0)
        close = float(h.get("close_price", avg) or avg) or 1
        qty   = int(h.get("quantity", 0) or 0)
        return Holding(
            tradingsymbol=str(h.get("trading_symbol", h.get("tradingsymbol", "")) or ""),
            exchange=str(h.get("exchange", "NSE") or "NSE"),
            isin=str(h.get("isin", "") or ""),
            quantity=qty,
            t1_quantity=int(h.get("t1_quantity", 0) or 0),
            average_price=avg,
            last_price=last,
            close_price=close,
            pnl=float(h.get("pnl", 0) or 0),
            day_change=last - close,
            day_change_pct=(last - close) / close * 100,
        )
