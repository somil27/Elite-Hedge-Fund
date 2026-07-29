"""
Execution Algorithm Agent
Routes to the correct broker (US or Indian) based on state.market,
then executes via VWAP/TWAP/aggressive/passive algorithms.
"""
import asyncpg
from agents.base import BaseAgent
import structlog

logger = structlog.get_logger()

# Demo user ID — replace with real auth in production
DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"


class ExecutionAgent(BaseAgent):
    def __init__(self):
        super().__init__("execution_algo", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        cycle_id  = state.get("cycle_id")
        order     = state.get("order")
        human_dec = state.get("human_decision", {})
        market    = state.get("market", "us")

        if not order:
            return {"final_status": "failed", "errors": ["No order to execute"]}

        # Apply human resize
        if human_dec and human_dec.get("override_weight"):
            portfolio_value = state.get("portfolio_snapshot", {}).get("total_value", 100_000)
            new_notional    = portfolio_value * human_dec["override_weight"]
            tech            = (state.get("technical_assessments") or [{}])[0]
            entry_approx    = order.get("limit_price") or tech.get("entry_zone_high", 100)
            if entry_approx and entry_approx > 0:
                order["qty"] = round(new_notional / entry_approx, 4)
            logger.info("order_resized_by_human", new_qty=order["qty"])

        if market == "india":
            return await self._execute_indian(state, order, conn, cycle_id)
        return await self._execute_us(state, order, conn, cycle_id)

    # ── US execution (Alpaca / IBKR / Mock) ──────────────────

    async def _execute_us(self, state, order, conn, cycle_id):
        from broker import (
            get_broker, OrderRequest, OrderSide, OrderType, TimeInForce,
            AlgoConfig, ExecutionAlgoEngine,
        )

        symbol    = order.get("symbol", "AAPL")
        direction = order.get("direction", "long")
        qty       = float(order.get("qty", 1))
        algo_name = order.get("algo", "vwap")
        side      = OrderSide.BUY if direction == "long" else OrderSide.SELL
        market    = state.get("market", "us")

        try:
            broker = await get_broker()
            clock  = await broker.get_market_clock()
            if not clock.is_open:
                logger.warning("us_market_closed", symbol=symbol)

            algo_config = AlgoConfig(
                symbol=symbol, side=side, total_qty=qty,
                algo=algo_name,
                duration_min=_parse_duration(order.get("time_horizon", "2h")),
                num_slices=_num_slices(algo_name, qty),
                stop_loss=order.get("stop_loss"),
                take_profit=order.get("take_profit"),
                market=market,
            )
            engine = ExecutionAlgoEngine(broker)
            result = await engine.execute(algo_config)

            if result.status == "failed":
                return {"errors": [f"Execution failed: {result.error}"], "final_status": "failed"}

            # Persist to DB
            from broker.persistence import save_algo_result
            await save_algo_result(conn, result, cycle_id=cycle_id)

            # Auto stop-loss GTC order
            stop_order_id = None
            if result.filled_qty > 0 and order.get("stop_loss"):
                from broker import OrderRequest, OrderType, TimeInForce
                stop_req = OrderRequest(
                    symbol=symbol,
                    side=OrderSide.SELL if direction == "long" else OrderSide.BUY,
                    qty=result.filled_qty,
                    order_type=OrderType.STOP,
                    stop_price=order["stop_loss"],
                    time_in_force=TimeInForce.GTC,
                    client_order_id=f"SL-{cycle_id[:8]}",
                    note="Auto stop-loss",
                )
                try:
                    sl = await broker.submit_order(stop_req)
                    stop_order_id = sl.order_id
                    logger.info("us_stop_loss_placed", symbol=symbol, stop=order["stop_loss"])
                except Exception as e:
                    logger.warning("us_stop_loss_failed", error=str(e))

            fill_report = _build_us_fill_report(order, result, stop_order_id, cycle_id)
            await self._store_memory(conn, fill_report, cycle_id, algo_name)
            return {"execution_report": fill_report, "broker_order_id": fill_report["order_id"], "final_status": "executed"}

        except Exception as e:
            logger.error("us_execution_error", error=str(e))
            return {"errors": [f"US execution error: {e}"], "final_status": "failed"}

    # ── Indian execution (Zerodha / Upstox) ──────────────────

    async def _execute_indian(self, state, order, conn, cycle_id):
        from broker.indian.base_indian import (
            IndianOrderRequest, Exchange, ProductType, Validity,
        )
        from broker.registry import get_indian_broker_for_agents

        indian_broker = state.get("indian_broker", "zerodha")
        user_id       = state.get("user_id", DEMO_USER_ID)
        symbol        = order.get("symbol", "RELIANCE")
        direction     = order.get("direction", "long")
        qty           = int(order.get("qty", 1))    # India: whole numbers only
        algo_name     = order.get("algo", "market")

        # Map algo → Indian order type
        # VWAP/TWAP aren't available natively — use MARKET for aggressive,
        # LIMIT for passive strategies
        order_type_map = {
            "aggressive": "MARKET",
            "vwap":       "MARKET",
            "twap":       "LIMIT",
            "passive":    "LIMIT",
        }
        indian_order_type = order_type_map.get(algo_name, "MARKET")

        # Determine product type from state mode
        mode = state.get("mode", "short_term")
        product = ProductType.MIS if mode == "short_term" else ProductType.CNC

        # Build limit price for LIMIT orders
        price = 0.0
        if indian_order_type == "LIMIT":
            tech = (state.get("technical_assessments") or [{}])[0]
            price = order.get("limit_price") or tech.get("entry_zone_high", 0) or 0.0

        try:
            client = await get_indian_broker_for_agents(user_id, indian_broker, conn)

            # Check market open
            if not client.is_market_open():
                logger.warning("indian_market_closed", symbol=symbol)
                # Fall back to AMO (After Market Order)
                from broker.indian.base_indian import OrderVariety
                variety = OrderVariety.AMO
            else:
                from broker.indian.base_indian import OrderVariety
                variety = OrderVariety.REGULAR

            req = IndianOrderRequest(
                exchange=Exchange.NSE,
                tradingsymbol=symbol.upper(),
                transaction_type="BUY" if direction == "long" else "SELL",
                quantity=qty,
                product=product,
                order_type=indian_order_type,
                price=price,
                trigger_price=0.0,
                validity=Validity.DAY,
                variety=variety,
                tag=f"alphadeskv1-{cycle_id[:8]}",
            )

            order_id = await client.place_order(req)
            logger.info("indian_order_placed",
                        broker=indian_broker, symbol=symbol,
                        order_id=order_id, product=product.value)

            # Poll for fill (up to 60s for market orders, 300s for limits)
            fill_report = await self._poll_indian_fill(
                client, order_id, symbol, direction, qty,
                timeout=60 if indian_order_type == "MARKET" else 300,
            )

            # Place GTT stop-loss (Zerodha) or limit stop (Upstox)
            if fill_report.get("avg_fill_price") and order.get("stop_loss"):
                await self._place_indian_stop_loss(
                    client, indian_broker, symbol, direction,
                    qty, fill_report["avg_fill_price"], order["stop_loss"],
                )

            # Persist to broker_orders table
            await self._persist_indian_order(conn, cycle_id, indian_broker,
                                              order_id, req, fill_report)

            await self._store_memory(conn, fill_report, cycle_id, algo_name)
            return {
                "execution_report": fill_report,
                "broker_order_id":  order_id,
                "final_status":     "executed",
            }

        except Exception as e:
            logger.error("indian_execution_error", broker=indian_broker, error=str(e))
            return {"errors": [f"Indian execution error: {e}"], "final_status": "failed"}

    async def _poll_indian_fill(
        self, client, order_id, symbol, direction, qty, timeout=60
    ) -> dict:
        """Poll the Indian broker order book until filled or timeout."""
        import asyncio
        from datetime import datetime, timezone

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                order_obj = await client.get_order(order_id)
                if order_obj.is_complete:
                    avg_price = order_obj.average_price or 0
                    filled    = order_obj.filled_quantity
                    return {
                        "order_id":       order_id,
                        "symbol":         symbol,
                        "direction":      direction,
                        "qty_filled":     filled,
                        "avg_fill_price": avg_price,
                        "slippage_bps":   order_obj.slippage_bps,
                        "status":         order_obj.status.lower() if hasattr(order_obj.status, 'lower') else str(order_obj.status),
                        "fills":          [],
                        "market":         "india",
                        "timestamp":      datetime.now(timezone.utc).isoformat(),
                    }
            except Exception:
                pass
            await asyncio.sleep(2)

        # Timeout — return partial info
        logger.warning("indian_fill_timeout", order_id=order_id)
        return {
            "order_id":       order_id,
            "symbol":         symbol,
            "direction":      direction,
            "qty_filled":     0,
            "avg_fill_price": 0,
            "slippage_bps":   0,
            "status":         "timeout",
            "fills":          [],
            "market":         "india",
        }

    async def _place_indian_stop_loss(
        self, client, broker_name, symbol, direction,
        qty, fill_price, stop_price,
    ):
        """Place a stop-loss after Indian order fills."""
        try:
            if broker_name == "zerodha":
                # Use GTT (Good-Till-Triggered) for persistent stop-loss
                gtt_id = await client.place_gtt(
                    tradingsymbol=symbol,
                    exchange=__import__("broker.indian.base_indian",
                                        fromlist=["Exchange"]).Exchange.NSE,
                    trigger_type="single",
                    trigger_price=stop_price,
                    last_price=fill_price,
                    orders=[{
                        "transaction_type": "SELL" if direction == "long" else "BUY",
                        "quantity": qty,
                        "order_type": "MARKET",
                        "product": "CNC",
                        "price": 0,
                    }],
                )
                logger.info("zerodha_gtt_stop_placed",
                            symbol=symbol, gtt_id=gtt_id, stop=stop_price)
            else:
                # Upstox: place a SL-M order (stop-loss market)
                from broker.indian.base_indian import (
                    IndianOrderRequest, Exchange, ProductType, Validity,
                )
                sl_req = IndianOrderRequest(
                    exchange=Exchange.NSE,
                    tradingsymbol=symbol,
                    transaction_type="SELL" if direction == "long" else "BUY",
                    quantity=qty,
                    product=ProductType.CNC,
                    order_type="SL-M",
                    trigger_price=stop_price,
                    validity=Validity.DAY,
                    tag="alphadeskv1-sl",
                )
                sl_id = await client.place_order(sl_req)
                logger.info("upstox_sl_placed", symbol=symbol, order_id=sl_id, stop=stop_price)
        except Exception as e:
            logger.warning("indian_stop_loss_failed", error=str(e))

    async def _persist_indian_order(self, conn, cycle_id, broker_name,
                                     order_id, req, fill_report):
        """Save Indian order to broker_orders table."""
        try:
            await conn.execute("""
                INSERT INTO broker_orders
                    (broker_order_id, cycle_id, symbol, side, order_type,
                     qty, filled_qty, avg_fill_price, status, algo, source,
                     submitted_at, filled_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, 'agent', now(), now())
                ON CONFLICT (broker_order_id) DO UPDATE SET
                    filled_qty     = EXCLUDED.filled_qty,
                    avg_fill_price = EXCLUDED.avg_fill_price,
                    status         = EXCLUDED.status
            """,
                order_id,
                cycle_id,
                req.tradingsymbol,
                req.transaction_type.lower(),
                req.order_type,
                float(req.quantity),
                float(fill_report.get("qty_filled", 0)),
                float(fill_report.get("avg_fill_price", 0)),
                fill_report.get("status", "unknown"),
                f"indian_{broker_name}",
            )
        except Exception as e:
            logger.warning("indian_order_persist_error", error=str(e))

    async def _store_memory(self, conn, fill_report, cycle_id, algo_name):
        symbol    = fill_report.get("symbol", "")
        direction = fill_report.get("direction", "")
        price     = fill_report.get("avg_fill_price", 0)
        qty       = fill_report.get("qty_filled", 0)
        slip      = fill_report.get("slippage_bps", 0)
        market    = fill_report.get("market", "us")

        await self.remember(
            conn, "observation",
            f"[{market.upper()}] Executed {symbol} {direction} qty={qty:.2f} "
            f"@ {price:.2f}, slippage={slip:.1f}bps via {algo_name}",
            metadata=fill_report,
            cycle_id=cycle_id,
            importance=0.8,
        )


# ── Helpers ───────────────────────────────────────────────────

def _build_us_fill_report(order, result, stop_order_id, cycle_id) -> dict:
    return {
        "order_id":         f"ALGO-{cycle_id[:8]}",
        "symbol":           order.get("symbol"),
        "direction":        order.get("direction"),
        "qty_filled":       result.filled_qty,
        "avg_fill_price":   result.avg_fill_price,
        "slippage_bps":     result.slippage_bps,
        "status":           result.status,
        "algo":             result.algo,
        "slices_sent":      result.slices_sent,
        "fill_rate":        result.fill_rate,
        "duration_seconds": result.duration_seconds,
        "stop_loss_order_id": stop_order_id,
        "market":           "us",
        "fills": [
            {"fill_id": f.fill_id, "price": f.price, "qty": f.qty,
             "timestamp": f.timestamp.isoformat(), "commission": f.commission}
            for f in result.fills
        ],
    }


def _parse_duration(horizon: str) -> int:
    """Convert '2h', '30min', 'eod' to minutes."""
    h = horizon.lower().strip()
    if "h" in h:
        return int(float(h.replace("h", "")) * 60)
    if "min" in h:
        return int(h.replace("min", ""))
    return 120


def _num_slices(algo: str, qty: float) -> int:
    if algo == "aggressive":
        return 1
    if algo == "twap":
        return max(5, min(20, int(qty / 10)))
    if algo == "vwap":
        return max(8, min(15, int(qty / 8)))
    return 10
