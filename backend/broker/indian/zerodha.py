"""
Zerodha Kite Connect Broker Implementation
Full integration using kiteconnect SDK + KiteTicker WebSocket.

OAuth flow:
  1. Direct user to: GET /api/broker/zerodha/login?user_id=<uid>
  2. User logs in at Zerodha and is redirected to your callback URL
  3. Callback receives request_token → exchange for access_token
  4. Access token stored encrypted in DB, valid until next trading day

Requires:
  pip install kiteconnect
  ZERODHA_API_KEY and ZERODHA_API_SECRET in .env
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
import structlog

from broker.indian.base_indian import (
    IndianOrderRequest, IndianOrder, IndianPosition, Holding,
    MarketQuote, IndianFunds, Exchange, ProductType, MARKET_OPEN_IST, MARKET_CLOSE_IST, NSE_HOLIDAYS_2025,
)

logger = structlog.get_logger()

OrderUpdateCallback = Callable[[IndianOrder], Awaitable[None]]


class ZerodhaBroker:
    """
    Zerodha Kite Connect broker.
    One instance per authenticated user.
    """

    def __init__(self, api_key: str, api_secret: str, access_token: str = ""):
        self.api_key      = api_key
        self.api_secret   = api_secret
        self.access_token = access_token
        self._kite        = None
        self._ticker      = None
        self._ticker_task: Optional[asyncio.Task] = None
        self._order_callbacks: list[OrderUpdateCallback] = []
        self._connected   = False

    # ── OAuth helpers ─────────────────────────────────────────

    def get_login_url(self) -> str:
        """Return the Zerodha login URL for OAuth flow."""
        try:
            from kiteconnect import KiteConnect
            kite = KiteConnect(api_key=self.api_key)
            return kite.login_url()
        except ImportError:
            raise ImportError("pip install kiteconnect")

    async def exchange_token(self, request_token: str) -> str:
        """
        Exchange the request_token received after user login
        for a session access_token. Call this in the OAuth callback.
        Returns the access_token (store it encrypted in DB).
        """
        def _exchange():
            from kiteconnect import KiteConnect
            kite = KiteConnect(api_key=self.api_key)
            session = kite.generate_session(request_token, api_secret=self.api_secret)
            return session["access_token"]

        token = await asyncio.get_event_loop().run_in_executor(None, _exchange)
        self.access_token = token
        logger.info("zerodha_token_exchanged")
        return token

    # ── Connection ────────────────────────────────────────────

    async def connect(self) -> None:
        if not self.access_token:
            raise RuntimeError("No access_token. Complete OAuth flow first.")
        try:
            from kiteconnect import KiteConnect
        except ImportError:
            raise ImportError("pip install kiteconnect")

        def _init():
            kite = KiteConnect(api_key=self.api_key)
            kite.set_access_token(self.access_token)
            # Verify token is valid
            profile = kite.profile()
            return kite, profile

        self._kite, profile = await asyncio.get_event_loop().run_in_executor(None, _init)
        self._connected = True
        logger.info("zerodha_connected", user=profile.get("user_name", "unknown"))

    async def disconnect(self) -> None:
        if self._ticker_task:
            self._ticker_task.cancel()
        if self._ticker:
            self._ticker.close()
        self._connected = False
        logger.info("zerodha_disconnected")

    def _ensure(self):
        if not self._kite:
            raise RuntimeError("ZerodhaBroker not connected.")

    # ── Funds & Account ───────────────────────────────────────

    async def get_funds(self) -> IndianFunds:
        self._ensure()
        def _fetch():
            return self._kite.margins()
        margins = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        equity = margins.get("equity", {})
        return IndianFunds(
            available_cash=equity.get("available", {}).get("cash", 0),
            available_intraday=equity.get("available", {}).get("intraday_payin", 0),
            available_margin=equity.get("available", {}).get("live_balance", 0),
            used_margin=equity.get("utilised", {}).get("debits", 0),
            collateral=equity.get("available", {}).get("collateral", 0),
            net=equity.get("net", 0),
            payin=equity.get("available", {}).get("payin", 0),
        )

    async def get_profile(self) -> dict:
        self._ensure()
        def _fetch():
            return self._kite.profile()
        return await asyncio.get_event_loop().run_in_executor(None, _fetch)

    # ── Orders ────────────────────────────────────────────────

    async def place_order(self, req: IndianOrderRequest) -> str:
        """Place order. Returns Zerodha order_id string."""
        self._ensure()
        def _place():
            return self._kite.place_order(
                variety=req.variety.value,
                exchange=req.exchange.value,
                tradingsymbol=req.tradingsymbol,
                transaction_type=req.transaction_type,
                quantity=req.quantity,
                product=req.product.value,
                order_type=req.order_type,
                price=req.price if req.order_type == "LIMIT" else None,
                trigger_price=req.trigger_price if req.trigger_price else None,
                validity=req.validity.value,
                disclosed_quantity=req.disclosed_quantity or None,
                tag=req.tag or None,
            )
        order_id = await asyncio.get_event_loop().run_in_executor(None, _place)
        logger.info("zerodha_order_placed",
                    order_id=order_id,
                    symbol=req.tradingsymbol,
                    txn=req.transaction_type,
                    qty=req.quantity,
                    product=req.product.value)
        return str(order_id)

    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
        validity: Optional[str] = None,
        variety: str = "regular",
    ) -> str:
        self._ensure()
        def _modify():
            kwargs = {"variety": variety, "order_id": order_id}
            if quantity:      kwargs["quantity"]      = quantity
            if price:         kwargs["price"]         = price
            if trigger_price: kwargs["trigger_price"] = trigger_price
            if order_type:    kwargs["order_type"]    = order_type
            if validity:      kwargs["validity"]      = validity
            return self._kite.modify_order(**kwargs)
        return str(await asyncio.get_event_loop().run_in_executor(None, _modify))

    async def cancel_order(self, order_id: str, variety: str = "regular") -> str:
        self._ensure()
        def _cancel():
            return self._kite.cancel_order(variety=variety, order_id=order_id)
        return str(await asyncio.get_event_loop().run_in_executor(None, _cancel))

    async def get_orders(self) -> list[IndianOrder]:
        self._ensure()
        def _fetch():
            return self._kite.orders()
        raw_orders = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [self._parse_order(o) for o in raw_orders]

    async def get_order(self, order_id: str) -> IndianOrder:
        self._ensure()
        def _fetch():
            return self._kite.order_history(order_id=order_id)
        history = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        if not history:
            raise ValueError(f"Order {order_id} not found")
        return self._parse_order(history[-1])   # latest state

    async def get_order_trades(self, order_id: str) -> list[dict]:
        """Get individual trade executions (fills) for an order."""
        self._ensure()
        def _fetch():
            return self._kite.order_trades(order_id=order_id)
        return await asyncio.get_event_loop().run_in_executor(None, _fetch)

    # ── Positions & Holdings ──────────────────────────────────

    async def get_positions(self) -> dict[str, list[IndianPosition]]:
        """
        Returns {"net": [...], "day": [...]}
        net = overnight + intraday combined
        day = today's intraday positions only
        """
        self._ensure()
        def _fetch():
            return self._kite.positions()
        raw = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return {
            "net": [self._parse_position(p) for p in raw.get("net", [])],
            "day": [self._parse_position(p) for p in raw.get("day", [])],
        }

    async def get_holdings(self) -> list[Holding]:
        """Long-term delivery holdings (CNC portfolio)."""
        self._ensure()
        def _fetch():
            return self._kite.holdings()
        raw = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [self._parse_holding(h) for h in raw]

    async def close_position(
        self,
        tradingsymbol: str,
        exchange: Exchange,
        product: ProductType,
        quantity: int,
    ) -> str:
        """Place a closing order for an open position."""
        positions = await self.get_positions()
        net = positions.get("net", [])
        pos = next(
            (p for p in net if p.tradingsymbol == tradingsymbol and
             p.exchange == exchange.value and p.product == product.value),
            None,
        )
        if not pos:
            raise ValueError(f"No position found for {tradingsymbol}")

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

    async def get_quote(self, instruments: list[str]) -> dict[str, MarketQuote]:
        """
        Get live quotes.
        instruments: list of "NSE:RELIANCE", "BSE:500325", etc.
        """
        self._ensure()
        def _fetch():
            return self._kite.quote(instruments)
        raw = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        result = {}
        for key, q in raw.items():
            ohlc = q.get("ohlc", {})
            depth = q.get("depth", {})
            bids  = depth.get("buy", [{}])
            asks  = depth.get("sell", [{}])
            result[key] = MarketQuote(
                instrument_token=q.get("instrument_token", 0),
                tradingsymbol=q.get("tradingsymbol", ""),
                last_price=q.get("last_price", 0),
                open=ohlc.get("open", 0),
                high=ohlc.get("high", 0),
                low=ohlc.get("low", 0),
                close=ohlc.get("close", 0),
                volume=q.get("volume", 0),
                oi=q.get("oi", 0),
                upper_circuit=q.get("upper_circuit_limit", 0),
                lower_circuit=q.get("lower_circuit_limit", 0),
                change=q.get("net_change", 0),
                change_pct=q.get("net_change", 0) / ohlc.get("close", 1) * 100
                          if ohlc.get("close") else 0,
                bid=bids[0].get("price", 0) if bids else 0,
                ask=asks[0].get("price", 0) if asks else 0,
                timestamp=datetime.now(timezone.utc),
            )
        return result

    async def get_historical(
        self,
        instrument_token: int,
        from_date: str,          # "YYYY-MM-DD"
        to_date: str,
        interval: str = "day",   # minute|3minute|5minute|15minute|30minute|60minute|day|week|month
        continuous: bool = False,
    ) -> list[dict]:
        """Fetch historical OHLCV candles."""
        self._ensure()
        def _fetch():
            return self._kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval,
                continuous=continuous,
            )
        return await asyncio.get_event_loop().run_in_executor(None, _fetch)

    async def search_instruments(
        self,
        exchange: str,
        query: str,
    ) -> list[dict]:
        """Search instruments by name/symbol."""
        self._ensure()
        def _fetch():
            return self._kite.instruments(exchange=exchange)
        instruments = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        query_lower = query.lower()
        return [
            i for i in instruments
            if query_lower in i.get("tradingsymbol", "").lower()
            or query_lower in i.get("name", "").lower()
        ][:20]

    # ── GTT (Good-Till-Triggered) orders ─────────────────────

    async def place_gtt(
        self,
        tradingsymbol: str,
        exchange: Exchange,
        trigger_type: str,         # "single" | "two-leg"
        trigger_price: float,
        last_price: float,
        orders: list[dict],        # [{transaction_type, quantity, order_type, product, price}]
    ) -> int:
        """Place a GTT (Good-Till-Triggered) order — stop-loss or target."""
        self._ensure()
        def _place():
            return self._kite.place_gtt(
                trigger_type=trigger_type,
                tradingsymbol=tradingsymbol,
                exchange=exchange.value,
                trigger_values=[trigger_price],
                last_price=last_price,
                orders=orders,
            )
        gtt_id = await asyncio.get_event_loop().run_in_executor(None, _place)
        logger.info("gtt_placed", gtt_id=gtt_id, symbol=tradingsymbol,
                    trigger=trigger_price)
        return gtt_id

    async def get_gtts(self) -> list[dict]:
        self._ensure()
        def _fetch():
            return self._kite.get_gtts()
        return await asyncio.get_event_loop().run_in_executor(None, _fetch)

    async def delete_gtt(self, gtt_id: int) -> dict:
        self._ensure()
        def _delete():
            return self._kite.delete_gtt(gtt_id=gtt_id)
        return await asyncio.get_event_loop().run_in_executor(None, _delete)

    # ── WebSocket ticker ──────────────────────────────────────

    async def subscribe_ticks(
        self,
        instrument_tokens: list[int],
        on_tick: Callable,
        mode: str = "full",      # "ltp" | "quote" | "full"
    ) -> None:
        """Start KiteTicker WebSocket for live market data."""
        try:
            from kiteconnect import KiteTicker
        except ImportError:
            raise ImportError("pip install kiteconnect")

        def _run_ticker():
            ticker = KiteTicker(self.api_key, self.access_token)

            def on_ticks(ws, ticks):
                for tick in ticks:
                    asyncio.run_coroutine_threadsafe(on_tick(tick), asyncio.get_event_loop())

            def on_connect(ws, response):
                ws.subscribe(instrument_tokens)
                ws.set_mode(ws.MODE_FULL if mode == "full"
                            else ws.MODE_QUOTE if mode == "quote"
                            else ws.MODE_LTP, instrument_tokens)

            def on_error(ws, code, reason):
                logger.error("kite_ticker_error", code=code, reason=reason)

            ticker.on_ticks   = on_ticks
            ticker.on_connect = on_connect
            ticker.on_error   = on_error
            ticker.connect(threaded=True)
            self._ticker = ticker

        await asyncio.get_event_loop().run_in_executor(None, _run_ticker)
        logger.info("kite_ticker_subscribed", tokens=instrument_tokens)

    async def subscribe_order_updates(self, callback: OrderUpdateCallback) -> None:
        """
        Subscribe to order update postbacks.
        Zerodha sends postbacks to a registered URL; here we poll as fallback.
        """
        self._order_callbacks.append(callback)

    # ── Market clock ─────────────────────────────────────────

    def is_market_open(self) -> bool:
        from datetime import datetime
        import pytz
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(ist)
        today_str = now_ist.strftime("%Y-%m-%d")
        if today_str in NSE_HOLIDAYS_2025:
            return False
        if now_ist.weekday() >= 5:   # Saturday=5, Sunday=6
            return False
        t = now_ist.time()
        return MARKET_OPEN_IST <= t <= MARKET_CLOSE_IST

    # ── Internal parsers ──────────────────────────────────────

    def _parse_order(self, o: dict) -> IndianOrder:
        return IndianOrder(
            order_id=str(o.get("order_id", "")),
            exchange=str(o.get("exchange", "")),
            tradingsymbol=str(o.get("tradingsymbol", "")),
            transaction_type=str(o.get("transaction_type", "")),
            quantity=int(o.get("quantity", 0)),
            filled_quantity=int(o.get("filled_quantity", 0)),
            pending_quantity=int(o.get("pending_quantity", 0)),
            product=str(o.get("product", "CNC")),
            order_type=str(o.get("order_type", "MARKET")),
            price=float(o.get("price", 0)),
            trigger_price=float(o.get("trigger_price", 0)),
            average_price=float(o.get("average_price", 0)),
            status=str(o.get("status", "OPEN")),
            status_message=str(o.get("status_message", "")),
            order_timestamp=o.get("order_timestamp"),
            exchange_timestamp=o.get("exchange_timestamp"),
            variety=str(o.get("variety", "regular")),
            validity=str(o.get("validity", "DAY")),
            tag=str(o.get("tag", "")),
        )

    def _parse_position(self, p: dict) -> IndianPosition:
        return IndianPosition(
            exchange=str(p.get("exchange", "")),
            tradingsymbol=str(p.get("tradingsymbol", "")),
            product=str(p.get("product", "")),
            quantity=int(p.get("quantity", 0)),
            overnight_quantity=int(p.get("overnight_quantity", 0)),
            buy_quantity=int(p.get("buy_quantity", 0)),
            sell_quantity=int(p.get("sell_quantity", 0)),
            buy_price=float(p.get("buy_price", 0)),
            sell_price=float(p.get("sell_price", 0)),
            last_price=float(p.get("last_price", 0)),
            close_price=float(p.get("close_price", 0)),
            pnl=float(p.get("pnl", 0)),
            unrealised=float(p.get("unrealised", 0)),
            realised=float(p.get("realised", 0)),
            multiplier=int(p.get("multiplier", 1)),
        )

    def _parse_holding(self, h: dict) -> Holding:
        close = float(h.get("close_price", 0)) or float(h.get("average_price", 1))
        last  = float(h.get("last_price", 0))
        avg   = float(h.get("average_price", 0))
        qty   = int(h.get("quantity", 0))
        return Holding(
            tradingsymbol=str(h.get("tradingsymbol", "")),
            exchange=str(h.get("exchange", "NSE")),
            isin=str(h.get("isin", "")),
            quantity=qty,
            t1_quantity=int(h.get("t1_quantity", 0)),
            average_price=avg,
            last_price=last,
            close_price=close,
            pnl=float(h.get("pnl", 0)),
            day_change=last - close,
            day_change_pct=(last - close) / close * 100 if close else 0,
        )
