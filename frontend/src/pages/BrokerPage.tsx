import { useEffect, useState } from 'react'
import {
  getBrokerAccount, getMarketClock, listPositions, listOrders,
  closePosition, cancelOrder, cancelAllOrders, placeManualOrder,
} from '../store/brokerApi'
import {
  Activity, Clock, TrendingUp, TrendingDown, X, RefreshCw,
  AlertTriangle, PlusCircle, ChevronDown, ChevronUp, Briefcase, Zap
} from 'lucide-react'
import clsx from 'clsx'
import { format } from 'date-fns'

export default function BrokerPage() {
  const [account, setAccount]     = useState<any>(null)
  const [clock, setClock]         = useState<any>(null)
  const [positions, setPositions] = useState<any[]>([])
  const [orders, setOrders]       = useState<any[]>([])
  const [loading, setLoading]     = useState(true)
  const [orderTab, setOrderTab]   = useState<'open' | 'closed'>('open')
  const [showManual, setShowManual] = useState(false)
  const [manualForm, setManualForm] = useState({
    symbol: '', side: 'buy', qty: '', order_type: 'market',
    limit_price: '', stop_price: '', time_in_force: 'day', note: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3500)
  }

  const refresh = async () => {
    try {
      const [acc, clk, pos, ord] = await Promise.all([
        getBrokerAccount(),
        getMarketClock(),
        listPositions(),
        listOrders(orderTab),
      ])
      setAccount(acc)
      setClock(clk)
      setPositions(pos)
      setOrders(ord)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [orderTab])
  useEffect(() => {
    const t = setInterval(refresh, 15_000)
    return () => clearInterval(t)
  }, [orderTab])

  const handleClosePosition = async (symbol: string) => {
    if (!confirm(`Close full position in ${symbol}?`)) return
    try {
      await closePosition(symbol)
      showToast(`✅ Close order placed for ${symbol}`)
      await refresh()
    } catch { showToast('❌ Failed to close position') }
  }

  const handleCancelOrder = async (orderId: string) => {
    try {
      await cancelOrder(orderId)
      showToast('✅ Order cancelled')
      await refresh()
    } catch { showToast('❌ Failed to cancel order') }
  }

  const handleCancelAll = async () => {
    if (!confirm('Cancel all open orders?')) return
    try {
      const r = await cancelAllOrders()
      showToast(`✅ Cancelled ${r.cancelled} orders`)
      await refresh()
    } catch { showToast('❌ Failed') }
  }

  const handleManualOrder = async () => {
    setSubmitting(true)
    try {
      await placeManualOrder({
        symbol:        manualForm.symbol.toUpperCase(),
        side:          manualForm.side,
        qty:           parseFloat(manualForm.qty),
        order_type:    manualForm.order_type,
        limit_price:   manualForm.limit_price ? parseFloat(manualForm.limit_price) : undefined,
        stop_price:    manualForm.stop_price  ? parseFloat(manualForm.stop_price)  : undefined,
        time_in_force: manualForm.time_in_force,
        note:          manualForm.note || 'Manual order via dashboard',
      })
      showToast(`✅ Order placed: ${manualForm.side.toUpperCase()} ${manualForm.qty} ${manualForm.symbol.toUpperCase()}`)
      setShowManual(false)
      setManualForm({ symbol: '', side: 'buy', qty: '', order_type: 'market',
                      limit_price: '', stop_price: '', time_in_force: 'day', note: '' })
      await refresh()
    } catch (e: any) {
      showToast(`❌ Order failed: ${e?.response?.data?.detail || e?.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-text-muted">
      <RefreshCw size={18} className="animate-spin mr-2" /> Loading broker data…
    </div>
  )

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 bg-surface border border-border rounded-xl
                        px-4 py-3 text-[13px] font-medium text-text-primary shadow-xl z-50 animate-slide-in">
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center">
              <Briefcase size={20} className="text-accent" />
            </div>
            Broker Integrations
          </h1>
          <p className="text-text-secondary text-sm mt-2">
            Live Alpaca account, positions, and order management.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {clock && (
            <div className={clsx(
              'flex items-center gap-2 px-3 py-1.5 rounded-full border text-[11px] font-semibold uppercase tracking-wider',
              clock.is_open
                ? 'text-success border-success/30 bg-success/10'
                : 'text-text-muted border-border bg-surface'
            )}>
              <div className={clsx("w-2 h-2 rounded-full", clock.is_open ? "bg-success animate-pulse" : "bg-text-muted")} />
              {clock.is_open ? 'Market Open' : 'Market Closed'}
            </div>
          )}
          <button onClick={refresh} className="btn-ghost p-2 text-text-muted hover:text-text-primary"><RefreshCw size={16} /></button>
          <button onClick={() => setShowManual(!showManual)} className="btn-primary h-9 flex items-center gap-2 text-[13px]">
            <PlusCircle size={16} /> Manual Order
            {showManual ? <ChevronUp size={14} className="opacity-70" /> : <ChevronDown size={14} className="opacity-70" />}
          </button>
        </div>
      </div>

      {/* Account summary */}
      {account && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Portfolio Value', value: `$${account.portfolio_value?.toLocaleString('en', { minimumFractionDigits: 2 })}`, highlight: true },
            { label: 'Cash Balance', value: `$${account.cash?.toLocaleString('en', { minimumFractionDigits: 2 })}` },
            { label: 'Buying Power', value: `$${account.buying_power?.toLocaleString('en', { minimumFractionDigits: 2 })}` },
            { label: 'Day Trades', value: account.day_trade_count ?? 0, danger: account.pattern_day_trader },
          ].map(({ label, value, highlight, danger }: any) => (
            <div key={label} className={clsx('card flex flex-col justify-center', highlight && 'border-accent/30 bg-accent/5')}>
              <p className="text-[12px] font-medium text-text-secondary mb-1">{label}</p>
              <p className={clsx('font-mono text-xl font-semibold',
                highlight ? 'text-accent' : danger ? 'text-danger' : 'text-text-primary'
              )}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Manual order form */}
      {showManual && (
        <div className="card border-accent/20 bg-gradient-to-br from-surface to-accent/5 animate-slide-in space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Zap size={14} className="text-accent" /> Place Manual Order
            </h3>
            <button onClick={() => setShowManual(false)} className="text-text-muted hover:text-text-primary"><X size={16} /></button>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { key: 'symbol', label: 'Symbol', placeholder: 'AAPL' },
              { key: 'qty',    label: 'Quantity', placeholder: '10', type: 'number' },
            ].map(({ key, label, placeholder, type = 'text' }) => (
              <div key={key}>
                <label className="text-[12px] font-medium text-text-secondary block mb-1.5">{label}</label>
                <input type={type} placeholder={placeholder} value={(manualForm as any)[key]} onChange={e => setManualForm(f => ({ ...f, [key]: e.target.value }))} className="input-field font-mono" />
              </div>
            ))}
            <div>
              <label className="text-[12px] font-medium text-text-secondary block mb-1.5">Side</label>
              <select value={manualForm.side} onChange={e => setManualForm(f => ({ ...f, side: e.target.value }))} className="input-field cursor-pointer">
                <option value="buy">Buy (Long)</option>
                <option value="sell">Sell (Short/Close)</option>
              </select>
            </div>
            <div>
              <label className="text-[12px] font-medium text-text-secondary block mb-1.5">Order Type</label>
              <select value={manualForm.order_type} onChange={e => setManualForm(f => ({ ...f, order_type: e.target.value }))} className="input-field cursor-pointer">
                <option value="market">Market</option>
                <option value="limit">Limit</option>
                <option value="stop">Stop</option>
                <option value="stop_limit">Stop Limit</option>
              </select>
            </div>
            <div>
              <label className="text-[12px] font-medium text-text-secondary block mb-1.5">Time In Force</label>
              <select value={manualForm.time_in_force} onChange={e => setManualForm(f => ({ ...f, time_in_force: e.target.value }))} className="input-field uppercase cursor-pointer">
                <option value="day">Day</option>
                <option value="gtc">GTC</option>
                <option value="ioc">IOC</option>
                <option value="fok">FOK</option>
              </select>
            </div>
            {['limit', 'stop_limit'].includes(manualForm.order_type) && (
              <div>
                <label className="text-[12px] font-medium text-text-secondary block mb-1.5">Limit Price</label>
                <input type="number" placeholder="150.00" value={manualForm.limit_price} onChange={e => setManualForm(f => ({ ...f, limit_price: e.target.value }))} className="input-field font-mono" />
              </div>
            )}
            {['stop', 'stop_limit'].includes(manualForm.order_type) && (
              <div>
                <label className="text-[12px] font-medium text-text-secondary block mb-1.5">Stop Price</label>
                <input type="number" placeholder="145.00" value={manualForm.stop_price} onChange={e => setManualForm(f => ({ ...f, stop_price: e.target.value }))} className="input-field font-mono" />
              </div>
            )}
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-border">
            <button onClick={() => setShowManual(false)} className="btn-ghost">Cancel</button>
            <button onClick={handleManualOrder} disabled={submitting || !manualForm.symbol || !manualForm.qty} className="btn-primary flex items-center gap-2">
              {submitting ? <><RefreshCw size={14} className="animate-spin" /> Placing…</> : 'Submit Order'}
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Positions */}
        <div className="card p-0 overflow-hidden flex flex-col max-h-[600px]">
          <div className="px-5 py-4 border-b border-border bg-surface/50 flex items-center justify-between shrink-0">
            <h2 className="text-[14px] font-semibold text-text-primary flex items-center gap-2">
              <TrendingUp size={16} className="text-primary" /> Open Positions
            </h2>
            <span className="badge-muted">{positions.length}</span>
          </div>
          <div className="overflow-y-auto custom-scrollbar flex-1">
            {positions.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-text-muted">
                <Briefcase size={24} className="mb-2 opacity-20" />
                <p className="text-[13px]">No open positions</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {positions.map((pos: any) => (
                  <div key={pos.symbol} className="px-5 py-4 hover:bg-surface-hover/50 transition-colors group">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className={clsx('w-8 h-8 rounded-full flex items-center justify-center',
                          pos.side === 'long' ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger')}>
                          {pos.side === 'long' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                        </div>
                        <div>
                          <p className="font-mono text-[14px] font-semibold text-text-primary tracking-tight">{pos.symbol}</p>
                          <p className="text-[12px] text-text-secondary mt-0.5">
                            {pos.qty} shs @ ${pos.avg_entry_price?.toFixed(2)}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className={clsx('font-mono text-[14px] font-semibold',
                          pos.unrealized_pnl >= 0 ? 'text-success' : 'text-danger')}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl?.toFixed(2)}
                        </p>
                        <p className={clsx('text-[12px] font-mono mt-0.5 font-medium',
                          pos.unrealized_pnl_pct >= 0 ? 'text-success/80' : 'text-danger/80')}>
                          {(pos.unrealized_pnl_pct * 100).toFixed(2)}%
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-border/50">
                      <p className="text-[12px] font-medium text-text-muted">
                        MV: <span className="font-mono text-text-primary">${pos.market_value?.toLocaleString('en', { maximumFractionDigits: 0 })}</span>
                      </p>
                      <button onClick={() => handleClosePosition(pos.symbol)}
                        className="text-[12px] font-medium text-danger hover:text-danger/80 transition-colors flex items-center gap-1.5 opacity-0 group-hover:opacity-100">
                        <X size={12} /> Close Position
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Orders */}
        <div className="card p-0 overflow-hidden flex flex-col max-h-[600px]">
          <div className="px-5 py-4 border-b border-border bg-surface/50 flex items-center justify-between shrink-0">
            <div className="flex gap-2 p-1 bg-background rounded-lg border border-border">
              {(['open', 'closed'] as const).map(tab => (
                <button key={tab} onClick={() => setOrderTab(tab)}
                  className={clsx('text-[12px] font-semibold px-3 py-1.5 rounded-md capitalize transition-all',
                    orderTab === tab ? 'bg-surface border-border shadow-sm text-text-primary' : 'text-text-secondary hover:text-text-primary')}>
                  {tab}
                </button>
              ))}
            </div>
            {orderTab === 'open' && orders.length > 0 && (
              <button onClick={handleCancelAll} className="text-[12px] font-medium text-danger hover:text-danger/80 flex items-center gap-1.5 bg-danger/10 px-2.5 py-1.5 rounded-md">
                <AlertTriangle size={12} /> Cancel All
              </button>
            )}
          </div>
          <div className="overflow-y-auto custom-scrollbar flex-1">
            {orders.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-text-muted">
                <Activity size={24} className="mb-2 opacity-20" />
                <p className="text-[13px]">No {orderTab} orders</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {orders.map((order: any) => (
                  <div key={order.order_id} className="px-5 py-4 hover:bg-surface-hover/50 transition-colors group">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2.5">
                          <span className="font-mono text-[14px] font-semibold text-text-primary">
                            {order.symbol}
                          </span>
                          <span className={clsx('text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider',
                            order.side === 'buy' ? 'text-success bg-success/10 border border-success/20' : 'text-danger bg-danger/10 border border-danger/20')}>
                            {order.side}
                          </span>
                          <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider bg-surface px-1.5 py-0.5 rounded border border-border">{order.order_type}</span>
                        </div>
                        <p className="text-[12px] text-text-muted mt-2">
                          <span className="text-text-primary">{order.filled_qty}</span> / {order.qty} filled
                          {order.limit_price && ` @ $${order.limit_price}`}
                        </p>
                      </div>
                      <div className="text-right shrink-0 flex flex-col items-end">
                        <span className={clsx('text-[11px] font-semibold px-2 py-1 rounded-full capitalize tracking-wide',
                          order.status === 'filled'    ? 'text-success bg-success/10' :
                          order.status === 'submitted' ? 'text-primary bg-primary/10' :
                          order.status === 'cancelled' ? 'text-text-muted bg-surface' :
                          'text-danger bg-danger/10')}>
                          {order.status}
                        </span>
                        {order.status === 'submitted' && (
                          <button onClick={() => handleCancelOrder(order.order_id)}
                            className="mt-2 text-[11px] font-semibold text-danger hover:text-danger/80 uppercase tracking-wider opacity-0 group-hover:opacity-100 transition-opacity">
                            Cancel
                          </button>
                        )}
                      </div>
                    </div>
                    {order.avg_fill_price && (
                      <div className="mt-3 pt-3 border-t border-border/50">
                        <p className="text-[12px] text-text-muted font-mono">
                          Filled @ <span className="text-text-primary">${order.avg_fill_price?.toFixed(2)}</span>
                          {order.slippage_bps != null && ` · ${order.slippage_bps.toFixed(1)} bps slippage`}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Market clock detail */}
      {clock && (
        <div className="flex items-center justify-center gap-6 text-[12px] font-medium text-text-muted pt-4">
          <div className="flex items-center gap-2"><Clock size={14} /> Timezone: <span className="text-text-secondary">{clock.timezone}</span></div>
          <div className="w-1 h-1 rounded-full bg-border" />
          <div>Next open: <span className="text-text-secondary">{format(new Date(clock.next_open), 'MMM d, HH:mm')}</span></div>
          <div className="w-1 h-1 rounded-full bg-border" />
          <div>Next close: <span className="text-text-secondary">{format(new Date(clock.next_close), 'MMM d, HH:mm')}</span></div>
        </div>
      )}
    </div>
  )
}
