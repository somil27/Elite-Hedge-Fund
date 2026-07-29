import { useEffect } from 'react'
import { useStore } from '../store/store'
import { listTrades } from '../store/api'
import { TrendingUp, TrendingDown, Target, Activity, CheckCircle, XCircle } from 'lucide-react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

export default function TradesPage() {
  const { trades, setTrades } = useStore()

  useEffect(() => {
    listTrades().then(setTrades).catch(console.error)
  }, [])

  const closedTrades = trades.filter(t => t.pnl_realized != null)
  const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl_realized || 0), 0)
  const winRate = closedTrades.length > 0
    ? closedTrades.filter(t => (t.pnl_realized || 0) > 0).length / closedTrades.length
    : 0

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shadow-sm">
              <Activity size={20} className="text-primary" />
            </div>
            Trade History
          </h1>
          <p className="text-text-secondary text-sm mt-2">All executed trades, outcomes, and performance metrics.</p>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
        {[
          { label: 'Total Trades', value: trades.length },
          { label: 'Closed Trades', value: closedTrades.length },
          { label: 'Total P&L', value: `$${totalPnl.toFixed(2)}`, accent: totalPnl > 0, danger: totalPnl < 0 },
          { label: 'Win Rate', value: `${(winRate * 100).toFixed(1)}%`, accent: winRate > 0.5 },
        ].map(({ label, value, accent, danger }) => (
          <div key={label} className={clsx('card relative overflow-hidden', (accent || danger) && 'shadow-sm')}>
            {(accent || danger) && <div className={clsx('absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl -mr-8 -mt-8', accent ? 'bg-success/5' : 'bg-danger/5')} />}
            <p className="text-[12px] font-medium text-text-secondary uppercase tracking-wider mb-2">{label}</p>
            <p className={clsx('font-mono text-2xl font-semibold tracking-tight',
              accent ? 'text-success' : danger ? 'text-danger' : 'text-text-primary'
            )}>{value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trades table */}
        <div className="lg:col-span-2 card p-0 overflow-hidden flex flex-col max-h-[600px]">
          <div className="px-5 py-4 border-b border-border bg-surface/50 flex items-center justify-between shrink-0">
            <h2 className="text-[14px] font-semibold text-text-primary flex items-center gap-2">
              <Target size={16} className="text-primary" /> Trade Log
            </h2>
          </div>
          <div className="overflow-x-auto overflow-y-auto custom-scrollbar flex-1">
            {trades.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-text-muted">
                <Target size={32} className="mb-3 opacity-20" />
                <p className="text-[14px]">No trades found.</p>
              </div>
            ) : (
              <table className="w-full text-left min-w-[700px]">
                <thead className="sticky top-0 bg-surface border-b border-border z-10">
                  <tr>
                    {['Asset', 'Direction', 'Entry / Exit', 'Qty', 'P&L', 'Trigger', 'Time'].map(h => (
                      <th key={h} className="px-5 py-3 text-[11px] font-semibold text-text-secondary uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {trades.map(trade => (
                    <tr key={trade.id} className="hover:bg-surface-hover/50 transition-colors group">
                      <td className="px-5 py-4 font-mono text-[14px] font-semibold text-text-primary">
                        {trade.symbol}
                      </td>
                      <td className="px-5 py-4">
                        <span className={clsx('inline-flex items-center gap-1.5 text-[11px] font-bold px-2 py-1 rounded uppercase tracking-wider border',
                          trade.direction === 'long' ? 'text-success bg-success/10 border-success/20' : 'text-danger bg-danger/10 border-danger/20')}>
                          {trade.direction === 'long' ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                          {trade.direction}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <p className="font-mono text-[13px] text-text-secondary">${trade.entry_price?.toFixed(2)}</p>
                        <p className="font-mono text-[13px] text-text-primary mt-0.5">{trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '—'}</p>
                      </td>
                      <td className="px-5 py-4 font-mono text-[13px] text-text-secondary">{trade.qty?.toFixed(2)}</td>
                      <td className="px-5 py-4 font-mono text-[14px] font-medium">
                        {trade.pnl_realized != null ? (
                          <div className="flex items-center gap-2">
                            {trade.pnl_realized >= 0 ? <CheckCircle size={14} className="text-success" /> : <XCircle size={14} className="text-danger" />}
                            <span className={trade.pnl_realized >= 0 ? 'text-success' : 'text-danger'}>
                              {trade.pnl_realized >= 0 ? '+' : ''}${trade.pnl_realized.toFixed(2)}
                            </span>
                          </div>
                        ) : (
                          <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted bg-background border border-border px-2 py-1 rounded">Open</span>
                        )}
                      </td>
                      <td className="px-5 py-4 text-[12px]">
                        {trade.human_decision ? (
                          <span className="text-text-secondary bg-surface-hover px-2 py-1 rounded capitalize">{trade.human_decision}</span>
                        ) : (
                          <span className="text-text-muted font-medium uppercase tracking-wider text-[10px]">Auto</span>
                        )}
                      </td>
                      <td className="px-5 py-4 text-[12px] text-text-muted font-medium">
                        {trade.opened_at ? format(new Date(trade.opened_at), 'MMM d, HH:mm') : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* P&L chart */}
        <div className="card flex flex-col">
          <h2 className="text-[13px] font-semibold text-text-secondary uppercase tracking-wider mb-6">P&L per Trade</h2>
          {closedTrades.length > 0 ? (
            <div className="flex-1 min-h-[200px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={closedTrades.map((t, i) => ({
                  name: t.symbol || `T${i}`,
                  pnl: t.pnl_realized || 0,
                }))}>
                  <XAxis dataKey="name" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} dy={10} />
                  <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} dx={-10} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', fontSize: '12px', color: '#fafafa', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                    itemStyle={{ color: '#fafafa', fontWeight: 600 }}
                    formatter={(v: any) => [`$${Number(v).toFixed(2)}`, 'P&L']}
                    cursor={{ fill: '#27272a', opacity: 0.4 }}
                  />
                  <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                    {closedTrades.map((t, i) => (
                      <Cell key={i} fill={(t.pnl_realized || 0) >= 0 ? '#10b981' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 text-text-muted">
              <Activity size={32} className="mb-3 opacity-20" />
              <p className="text-[14px]">No closed trades for charting.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
