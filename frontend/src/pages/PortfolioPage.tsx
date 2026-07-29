import { useEffect } from 'react'
import { useStore } from '../store/store'
import { getPortfolio } from '../store/api'
import { TrendingUp, TrendingDown, DollarSign, RefreshCw, Briefcase, Activity, PieChart as PieChartIcon } from 'lucide-react'
import clsx from 'clsx'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

const COLORS = ['#6366f1','#8b5cf6','#f59e0b','#3b82f6','#ec4899','#10b981','#ff9800','#ef4444']

export default function PortfolioPage() {
  const { portfolio, setPortfolio } = useStore()

  useEffect(() => {
    getPortfolio().then(setPortfolio).catch(console.error)
    const t = setInterval(() => getPortfolio().then(setPortfolio).catch(() => {}), 10000)
    return () => clearInterval(t)
  }, [])

  if (!portfolio) return (
    <div className="flex items-center justify-center h-[60vh] text-text-muted">
      <RefreshCw size={24} className="animate-spin mr-3 opacity-50" /> 
      <span className="text-[14px] font-medium">Loading Portfolio…</span>
    </div>
  )

  const positions = portfolio.positions || []
  const pieData = positions.map((p: any) => ({
    name: p.symbol, value: Math.abs(p.market_value || 0),
  }))

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shadow-sm">
              <Briefcase size={20} className="text-primary" />
            </div>
            Portfolio
          </h1>
          <p className="text-text-secondary text-sm mt-2">Live account positions and comprehensive equity summary.</p>
        </div>
        <button onClick={() => getPortfolio().then(setPortfolio)} className="btn-ghost h-9 flex items-center gap-2 text-[13px]">
          <RefreshCw size={14} /> Sync Data
        </button>
      </div>

      {/* Account summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {[
          { label: 'Total Equity Value', value: `$${(portfolio.total_value || 0).toLocaleString('en', { minimumFractionDigits: 2 })}`, highlight: true },
          { label: 'Available Cash', value: `$${(portfolio.cash || 0).toLocaleString('en', { minimumFractionDigits: 2 })}` },
          { label: 'Buying Power', value: `$${(portfolio.buying_power || 0).toLocaleString('en', { minimumFractionDigits: 2 })}` },
        ].map(({ label, value, highlight }: any) => (
          <div key={label} className={clsx('card flex flex-col justify-center relative overflow-hidden', highlight && 'border-primary/30 bg-gradient-to-br from-surface to-primary/10 shadow-glow')}>
            {highlight && <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-3xl -mr-16 -mt-16" />}
            <p className="text-[13px] font-medium text-text-secondary mb-2 relative z-10 uppercase tracking-wider">{label}</p>
            <p className={clsx('font-mono text-2xl font-semibold tracking-tight relative z-10',
              highlight ? 'text-primary' : 'text-text-primary'
            )}>{value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Positions table */}
        <div className="lg:col-span-2 card p-0 overflow-hidden flex flex-col max-h-[600px]">
          <div className="px-5 py-4 border-b border-border bg-surface/50 flex items-center justify-between shrink-0">
            <h2 className="text-[14px] font-semibold text-text-primary flex items-center gap-2">
              <Activity size={16} className="text-primary" /> Open Positions
            </h2>
            <span className="badge-muted">{positions.length} Assets</span>
          </div>
          <div className="overflow-x-auto overflow-y-auto custom-scrollbar flex-1">
            {positions.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-text-muted">
                <Briefcase size={32} className="mb-3 opacity-20" />
                <p className="text-[14px]">No open positions found.</p>
              </div>
            ) : (
              <table className="w-full text-left min-w-[500px]">
                <thead className="sticky top-0 bg-surface border-b border-border z-10">
                  <tr>
                    {['Asset','Quantity','Market Value','Unrealized P&L'].map(h => (
                      <th key={h} className="px-5 py-3 text-[11px] font-semibold text-text-secondary uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {positions.map((pos: any, i: number) => (
                    <tr key={i} className="hover:bg-surface-hover/50 transition-colors group">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className={clsx('w-9 h-9 rounded-full flex items-center justify-center shrink-0 border',
                            (pos.unrealized_pnl || 0) >= 0 ? 'bg-success/10 text-success border-success/20' : 'bg-danger/10 text-danger border-danger/20')}>
                            {(pos.unrealized_pnl || 0) >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                          </div>
                          <span className="font-mono text-[15px] font-semibold text-text-primary tracking-tight">{pos.symbol}</span>
                        </div>
                      </td>
                      <td className="px-5 py-4 font-mono text-[14px] font-medium text-text-secondary">{pos.qty}</td>
                      <td className="px-5 py-4 font-mono text-[14px] font-medium text-text-primary">
                        ${(pos.market_value || 0).toLocaleString('en', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex flex-col">
                          <span className={clsx('font-mono text-[14px] font-semibold', (pos.unrealized_pnl || 0) >= 0 ? 'text-success' : 'text-danger')}>
                            {(pos.unrealized_pnl || 0) >= 0 ? '+' : ''}${(pos.unrealized_pnl || 0).toFixed(2)}
                          </span>
                          <span className={clsx('font-mono text-[11px] font-medium mt-0.5', (pos.unrealized_pnl_pct || 0) >= 0 ? 'text-success/80' : 'text-danger/80')}>
                            {((pos.unrealized_pnl_pct || 0) * 100).toFixed(2)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Allocation pie */}
        <div className="card flex flex-col">
          <h2 className="text-[13px] font-semibold text-text-secondary uppercase tracking-wider mb-6">Asset Allocation</h2>
          {pieData.length > 0 ? (
            <div className="flex-1 flex flex-col">
              <div className="flex-1 min-h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={70} outerRadius={100}
                      paddingAngle={2} dataKey="value" stroke="none">
                      {pieData.map((_: any, i: number) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', fontSize: '12px', color: '#fafafa', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                      itemStyle={{ color: '#fafafa', fontWeight: 600 }}
                      formatter={(v: any) => [`$${Number(v).toLocaleString('en', { minimumFractionDigits: 2 })}`, 'Market Value']}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-3 mt-6 pt-6 border-t border-border">
                {pieData.map((d: any, i: number) => (
                  <div key={i} className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                    <span className="text-[13px] font-medium text-text-primary font-mono">{d.name}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-48 text-text-muted">
              <PieChartIcon size={32} className="mb-3 opacity-20" />
              <p className="text-[14px]">No allocation data</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
