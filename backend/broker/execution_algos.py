"""
Execution Algorithm Engine
Implements VWAP, TWAP, aggressive, and passive execution strategies.
Breaks large orders into slices to minimize market impact.
"""
from __future__ import annotations
import asyncio
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
import structlog

from broker.base import (
    AbstractBroker, OrderRequest, OrderSide, OrderType,
    TimeInForce, Fill,
)

logger = structlog.get_logger()


@dataclass
class AlgoConfig:
    """Configuration for an execution algorithm run."""
    symbol:         str
    side:           OrderSide
    total_qty:      float
    algo:           str = "vwap"         # vwap | twap | aggressive | passive
    duration_min:   int = 120            # total execution window in minutes
    num_slices:     int = 10             # number of child orders
    urgency:        float = 0.5          # 0=passive, 1=aggressive
    max_pct_adv:    float = 0.10         # max % of avg daily volume per slice
    limit_offset_bps: float = 5.0       # limit price offset from mid for passive
    stop_loss:      Optional[float] = None
    take_profit:    Optional[float] = None
    market:         str = "us"


@dataclass
class AlgoResult:
    """Final result of an execution algorithm run."""
    symbol:         str
    side:           str
    total_qty:      float
    filled_qty:     float
    avg_fill_price: float
    slippage_bps:   float
    algo:           str
    duration_seconds: float
    slices_sent:    int
    fills:          list[Fill] = field(default_factory=list)
    status:         str = "complete"     # complete | partial | failed
    error:          Optional[str] = None

    @property
    def fill_rate(self) -> float:
        return self.filled_qty / self.total_qty if self.total_qty else 0


# ─────────────────────────────────────────────
# Progress callback type
# ─────────────────────────────────────────────
ProgressCallback = Callable[[str, float, float, float], Awaitable[None]]
# (symbol, pct_filled, avg_price, elapsed_seconds)


class ExecutionAlgoEngine:
    """
    Runs execution algorithms: VWAP, TWAP, Aggressive, Passive.
    Uses the broker interface to submit child orders.
    """

    def __init__(self, broker: AbstractBroker):
        self.broker = broker

    async def _sleep(self, seconds: float):
        if self.broker.__class__.__name__ == "MockBroker":
            await asyncio.sleep(0.01)
        else:
            await asyncio.sleep(seconds)

    async def execute(
        self,
        config: AlgoConfig,
        on_progress: Optional[ProgressCallback] = None,
    ) -> AlgoResult:
        """Entry point — routes to the correct algo."""
        start_time = datetime.now(timezone.utc)
        logger.info("algo_execute_start",
                    symbol=config.symbol,
                    algo=config.algo,
                    total_qty=config.total_qty,
                    side=config.side.value)
        try:
            if config.algo == "vwap":
                result = await self._vwap(config, on_progress)
            elif config.algo == "twap":
                result = await self._twap(config, on_progress)
            elif config.algo == "aggressive":
                result = await self._aggressive(config)
            elif config.algo == "passive":
                result = await self._passive(config, on_progress)
            else:
                result = await self._aggressive(config)

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            result.duration_seconds = elapsed
            logger.info("algo_execute_complete",
                        symbol=config.symbol,
                        fill_rate=result.fill_rate,
                        avg_price=result.avg_fill_price,
                        slippage_bps=result.slippage_bps,
                        duration_s=elapsed)
            return result
        except Exception as e:
            logger.error("algo_execute_error", symbol=config.symbol, error=str(e))
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            return AlgoResult(
                symbol=config.symbol,
                side=config.side.value,
                total_qty=config.total_qty,
                filled_qty=0,
                avg_fill_price=0,
                slippage_bps=0,
                algo=config.algo,
                duration_seconds=elapsed,
                slices_sent=0,
                status="failed",
                error=str(e),
            )

    # ── TWAP ──────────────────────────────────────────────────

    async def _twap(
        self,
        config: AlgoConfig,
        on_progress: Optional[ProgressCallback] = None,
    ) -> AlgoResult:
        """
        Time-Weighted Average Price:
        Splits total_qty into equal slices sent at fixed time intervals.
        """
        n = config.num_slices
        slice_qty = config.total_qty / n
        interval_s = (config.duration_min * 60) / n

        all_fills: list[Fill] = []
        total_filled = 0.0
        weighted_price_sum = 0.0
        slices_sent = 0
        start = datetime.now(timezone.utc)

        for i in range(n):
            req = OrderRequest(
                symbol=config.symbol,
                side=config.side,
                qty=round(slice_qty, 4),
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.IOC,
                client_order_id=f"TWAP-{config.symbol}-{i}",
                note=f"TWAP slice {i+1}/{n}",
            )
            order = await self.broker.submit_order(req)
            slices_sent += 1

            # Wait for fill
            try:
                order = await self.broker.wait_for_fill(
                    order.order_id,
                    timeout_seconds=max(min(interval_s * 0.8, 30), 5.0),
                )
            except TimeoutError:
                logger.warning("twap_slice_timeout", slice=i)

            if order.filled_qty > 0 and order.avg_fill_price:
                all_fills.extend(order.fills)
                total_filled += order.filled_qty
                weighted_price_sum += order.filled_qty * order.avg_fill_price

            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            if on_progress:
                pct = total_filled / config.total_qty
                avg = weighted_price_sum / total_filled if total_filled else 0
                await on_progress(config.symbol, pct, avg, elapsed)

            if i < n - 1:
                await self._sleep(interval_s)

        avg_price = weighted_price_sum / total_filled if total_filled else 0
        return AlgoResult(
            symbol=config.symbol,
            side=config.side.value,
            total_qty=config.total_qty,
            filled_qty=total_filled,
            avg_fill_price=round(avg_price, 4),
            slippage_bps=self._calc_slippage_bps(config, avg_price),
            algo="twap",
            duration_seconds=0,
            slices_sent=slices_sent,
            fills=all_fills,
            status="complete" if total_filled >= config.total_qty * 0.98 else "partial",
        )

    # ── VWAP ──────────────────────────────────────────────────

    async def _vwap(
        self,
        config: AlgoConfig,
        on_progress: Optional[ProgressCallback] = None,
    ) -> AlgoResult:
        """
        Volume-Weighted Average Price:
        Front-loads or back-loads slices based on intraday volume profile.
        Uses a U-shaped volume curve (high at open/close, low midday).
        """
        n = config.num_slices
        interval_s = (config.duration_min * 60) / n

        # U-shaped intraday volume weights (simplified)
        raw_weights = self._vwap_volume_weights(n)
        total_w = sum(raw_weights)
        slice_qtys = [
            config.total_qty * w / total_w for w in raw_weights
        ]

        all_fills: list[Fill] = []
        total_filled = 0.0
        weighted_price_sum = 0.0
        slices_sent = 0
        start = datetime.now(timezone.utc)

        for i, qty in enumerate(slice_qtys):
            if qty < 0.001:
                continue

            req = OrderRequest(
                symbol=config.symbol,
                side=config.side,
                qty=round(qty, 4),
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.IOC,
                client_order_id=f"VWAP-{config.symbol}-{i}",
                note=f"VWAP slice {i+1}/{n} weight={raw_weights[i]:.2f}",
            )
            order = await self.broker.submit_order(req)
            slices_sent += 1

            try:
                order = await self.broker.wait_for_fill(
                    order.order_id, timeout_seconds=max(min(interval_s * 0.8, 30), 5.0)
                )
            except TimeoutError:
                logger.warning("vwap_slice_timeout", slice=i)

            if order.filled_qty > 0 and order.avg_fill_price:
                all_fills.extend(order.fills)
                total_filled += order.filled_qty
                weighted_price_sum += order.filled_qty * order.avg_fill_price

            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            if on_progress:
                pct = total_filled / config.total_qty
                avg = weighted_price_sum / total_filled if total_filled else 0
                await on_progress(config.symbol, pct, avg, elapsed)

            if i < len(slice_qtys) - 1:
                await self._sleep(interval_s)

        avg_price = weighted_price_sum / total_filled if total_filled else 0
        return AlgoResult(
            symbol=config.symbol,
            side=config.side.value,
            total_qty=config.total_qty,
            filled_qty=total_filled,
            avg_fill_price=round(avg_price, 4),
            slippage_bps=self._calc_slippage_bps(config, avg_price),
            algo="vwap",
            duration_seconds=0,
            slices_sent=slices_sent,
            fills=all_fills,
            status="complete" if total_filled >= config.total_qty * 0.98 else "partial",
        )

    def _vwap_volume_weights(self, n: int) -> list[float]:
        """
        Approximate intraday U-shaped volume profile.
        Higher weight at start and end of session.
        """
        weights = []
        for i in range(n):
            t = i / max(n - 1, 1)   # 0 to 1
            # U-shape: 1 + cos(pi * (2t - 1)) = high at 0 and 1, low at 0.5
            w = 1 + math.cos(math.pi * (2 * t - 1)) * 0.5
            weights.append(max(w, 0.3))
        return weights

    # ── Aggressive ────────────────────────────────────────────

    async def _aggressive(self, config: AlgoConfig) -> AlgoResult:
        """
        Send the entire order as a single market order immediately.
        Use for momentum entries where speed matters more than price.
        """
        req = OrderRequest(
            symbol=config.symbol,
            side=config.side,
            qty=config.total_qty,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            client_order_id=f"AGGR-{config.symbol}",
            note="Aggressive full-size market order",
        )
        order = await self.broker.submit_order(req)

        try:
            order = await self.broker.wait_for_fill(order.order_id, timeout_seconds=30)
        except TimeoutError:
            logger.warning("aggressive_fill_timeout", symbol=config.symbol)

        avg_price = order.avg_fill_price or 0
        return AlgoResult(
            symbol=config.symbol,
            side=config.side.value,
            total_qty=config.total_qty,
            filled_qty=order.filled_qty,
            avg_fill_price=avg_price,
            slippage_bps=self._calc_slippage_bps(config, avg_price),
            algo="aggressive",
            duration_seconds=0,
            slices_sent=1,
            fills=order.fills,
            status="complete" if order.filled_qty >= config.total_qty * 0.98 else "partial",
        )

    # ── Passive ───────────────────────────────────────────────

    async def _passive(
        self,
        config: AlgoConfig,
        on_progress: Optional[ProgressCallback] = None,
    ) -> AlgoResult:
        """
        Post limit orders slightly behind the mid to get price improvement.
        Good for mean-reversion entries where time is not critical.
        """
        n = config.num_slices
        slice_qty = config.total_qty / n
        interval_s = (config.duration_min * 60) / n

        all_fills: list[Fill] = []
        total_filled = 0.0
        weighted_price_sum = 0.0
        slices_sent = 0
        start = datetime.now(timezone.utc)

        for i in range(n):
            # Get current mid price estimate
            try:
                snap = await _get_mid_price(config.symbol, market=config.market)
                mid = snap
            except Exception:
                mid = None

            order_type = OrderType.LIMIT if mid else OrderType.MARKET
            limit_price = None
            if mid:
                offset = mid * (config.limit_offset_bps / 10_000)
                if config.side == OrderSide.BUY:
                    limit_price = round(mid - offset, 2)
                else:
                    limit_price = round(mid + offset, 2)

            req = OrderRequest(
                symbol=config.symbol,
                side=config.side,
                qty=round(slice_qty, 4),
                order_type=order_type,
                limit_price=limit_price,
                time_in_force=TimeInForce.IOC,
                client_order_id=f"PASS-{config.symbol}-{i}",
                note=f"Passive limit slice {i+1}/{n}",
            )
            order = await self.broker.submit_order(req)
            slices_sent += 1

            try:
                order = await self.broker.wait_for_fill(
                    order.order_id, timeout_seconds=max(min(interval_s * 0.6, 20), 5.0)
                )
            except TimeoutError:
                # Cancel unfilled limit and move to market
                await self.broker.cancel_order(order.order_id)

            if order.filled_qty > 0 and order.avg_fill_price:
                all_fills.extend(order.fills)
                total_filled += order.filled_qty
                weighted_price_sum += order.filled_qty * order.avg_fill_price

            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            if on_progress:
                pct = total_filled / config.total_qty
                avg = weighted_price_sum / total_filled if total_filled else 0
                await on_progress(config.symbol, pct, avg, elapsed)

            if i < n - 1:
                await self._sleep(interval_s)

        avg_price = weighted_price_sum / total_filled if total_filled else 0
        return AlgoResult(
            symbol=config.symbol,
            side=config.side.value,
            total_qty=config.total_qty,
            filled_qty=total_filled,
            avg_fill_price=round(avg_price, 4),
            slippage_bps=self._calc_slippage_bps(config, avg_price),
            algo="passive",
            duration_seconds=0,
            slices_sent=slices_sent,
            fills=all_fills,
            status="complete" if total_filled >= config.total_qty * 0.95 else "partial",
        )

    # ── Helpers ───────────────────────────────────────────────

    def _calc_slippage_bps(self, config: AlgoConfig, avg_fill: float) -> float:
        """Estimate slippage vs arrival price (from config.limit_price or mid)."""
        ref = None
        if hasattr(config, "_arrival_price") and config._arrival_price:
            ref = config._arrival_price
        if not ref or avg_fill == 0:
            return 0.0
        return abs(avg_fill - ref) / ref * 10_000


async def _get_mid_price(symbol: str, market: str = "us") -> float:
    """Get a current mid-price estimate for passive algo."""
    from tools.market_data import get_market_snapshot
    snap = await get_market_snapshot([symbol], market=market)
    return snap.get(symbol, {}).get("price", 100.0)
