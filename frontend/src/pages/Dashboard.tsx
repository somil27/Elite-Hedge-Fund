import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../store/store'
import { startCycle, listCycles, getPortfolio } from '../store/api'
import { Play, Zap, Clock, CheckCircle, XCircle, AlertCircle, ChevronRight, TrendingUp } from 'lucide-react'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'

const STATUS_CONFIG: Record<string, { icon: any; color: string; label: string }> = {
  running: { icon: Clock, color: 'text-gold', label: 'Running' },
  awaiting_human: { icon: AlertCircle, color: 'text-gold', label: 'Needs Review' },
  executed: { icon: CheckCircle, color: 'text-accent', label: 'Executed' },
  rejected: { icon: XCircle, color: 'text-danger', label: 'Rejected' },
  failed: { icon: XCircle, color: 'text-text-muted', label: 'Failed' },
  approved: { icon: CheckCircle, color: 'text-accent', label: 'Approved' },
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { cycles, setCycles, setPortfolio, portfolio } = useStore()
  const [launching, setLaunching] = useState(false)
  const [mode, setMode] = useState<'short_term' | 'long_term'>('short_term')
  const [autoMode, setAutoMode] = useState(false)
  const [market, setMarket] = useState<'us' | 'india'>('us')
  const [indianBroker, setIndianBroker] = useState<'zerodha' | 'upstox'>('zerodha')

  useEffect(() => {
    listCycles().then(setCycles).catch(console.error)
    getPortfolio().then(setPortfolio).catch(console.error)
    const t = setInterval(() => {
      listCycles().then(setCycles).catch(() => { })
    }, 5000)
    return () => clearInterval(t)
  }, [])

  const handleLaunch = async () => {
    setLaunching(true)
    try {
      const result = await startCycle(mode, autoMode, market, indianBroker)
      await listCycles().then(setCycles)
      navigate(`/cycle/${result.cycle_id}`)
    } catch (e) {
      console.error(e)
    } finally {
      setLaunching(false)
    }
  }

  const pendingReviews = cycles.filter(c => c.status === 'awaiting_human')

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">Dashboard</h1>
          <p className="text-text-secondary text-sm mt-1">Multi-agent AI brokerage system overview</p>
        </div>
      </div>

      {/* Portfolio summary strip */}
      {portfolio && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Portfolio Value', value: `$${portfolio.total_value?.toLocaleString('en', { minimumFractionDigits: 2 })}`, accent: true },
            { label: 'Cash Available', value: `$${portfolio.cash?.toLocaleString('en', { minimumFractionDigits: 2 })}` },
            { label: 'Open Positions', value: portfolio.positions?.length ?? 0 },
            { label: 'Drawdown', value: `${(portfolio.current_drawdown * 100).toFixed(2)}%`, danger: portfolio.current_drawdown > 0.05 },
          ].map(({ label, value, accent, danger }) => (
            <div key={label} className={clsx(
              'card relative overflow-hidden group',
              accent && 'border-primary/30 shadow-[0_0_15px_rgba(99,102,241,0.05)]'
            )}>
              {accent && <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none transition-opacity group-hover:opacity-100 opacity-50" />}
              <p className="text-text-secondary text-[13px] font-medium mb-1.5 relative z-10">{label}</p>
              <p className={clsx('font-sans text-2xl font-semibold tracking-tight relative z-10',
                accent ? 'text-primary' : danger ? 'text-danger' : 'text-text-primary'
              )}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Pending reviews alert */}
      {pendingReviews.length > 0 && (
        <div className="border border-warning/30 bg-warning/5 rounded-xl p-4 flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-warning/10 flex items-center justify-center shrink-0">
              <AlertCircle size={20} className="text-warning" />
            </div>
            <div>
              <p className="text-sm font-semibold text-text-primary">
                {pendingReviews.length} trade{pendingReviews.length > 1 ? 's' : ''} awaiting approval
              </p>
              <p className="text-[13px] text-text-secondary mt-0.5">Review and approve before expiry</p>
            </div>
          </div>
          <button onClick={() => navigate(`/cycle/${pendingReviews[0].cycle_id}`)}
            className="px-4 py-2 rounded-md bg-warning text-white text-sm font-medium hover:bg-amber-600 transition-colors shadow-sm flex items-center gap-1.5 focus:ring-2 focus:ring-warning/50">
            Review <ChevronRight size={16} />
          </button>
        </div>
      )}

      {/* Launch panel + recent cycles */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Launch panel */}
        <div className="card space-y-6 lg:col-span-1 flex flex-col">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
              <Zap size={16} className="text-primary" />
            </div>
            <h2 className="text-lg font-semibold tracking-tight text-text-primary">New Cycle</h2>
          </div>

          {/* Mode selector */}
          <div className="space-y-3">
            <p className="text-[13px] font-medium text-text-secondary">Trading Mode</p>
            <div className="grid grid-cols-2 gap-2 bg-background p-1 rounded-lg border border-border">
              {(['short_term', 'long_term'] as const).map(m => (
                <button key={m} onClick={() => setMode(m)}
                  className={clsx(
                    'py-2 rounded-md text-[13px] font-medium transition-all duration-200 flex justify-center items-center gap-1.5',
                    mode === m
                      ? 'bg-surface shadow-sm text-text-primary border border-border/50'
                      : 'text-text-muted hover:text-text-primary transparent border border-transparent'
                  )}>
                  {m === 'short_term' ? '⚡ Short Term' : '📈 Long Term'}
                </button>
              ))}
            </div>
            <p className="text-[12px] text-text-muted">
              {mode === 'short_term'
                ? 'Days to weeks. Quant + momentum signals dominant.'
                : 'Weeks to months. Fundamental + macro analysis dominant.'}
            </p>
          </div>

          {/* Market selector */}
          <div className="space-y-3">
            <p className="text-[13px] font-medium text-text-secondary">Market</p>
            <div className="grid grid-cols-2 gap-2 bg-background p-1 rounded-lg border border-border">
              {(['us', 'india'] as const).map(m => (
                <button key={m} onClick={() => setMarket(m)}
                  className={clsx(
                    'py-2 rounded-md text-[13px] font-medium transition-all duration-200',
                    market === m
                      ? 'bg-surface shadow-sm text-text-primary border border-border/50'
                      : 'text-text-muted hover:text-text-primary border border-transparent'
                  )}>
                  {m === 'us' ? '🇺🇸 US (Alpaca)' : '🇮🇳 India'}
                </button>
              ))}
            </div>
            {market === 'india' && (
              <div className="flex gap-2 mt-3">
                {(['zerodha', 'upstox'] as const).map(b => (
                  <button key={b} onClick={() => setIndianBroker(b)}
                    className={clsx(
                      'flex-1 py-1.5 rounded-md text-[12px] font-medium border transition-all duration-200 capitalize',
                      indianBroker === b
                        ? 'border-warning/40 bg-warning/10 text-warning'
                        : 'border-border bg-background text-text-secondary hover:border-border-bright hover:bg-surface'
                    )}>
                    {b}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Auto mode toggle */}
          <div className="flex items-center justify-between py-4 border-t border-border mt-auto">
            <div>
              <p className="text-sm font-medium text-text-primary">Auto Execute</p>
              <p className="text-[12px] text-text-muted mt-0.5">Skip human approval gate</p>
            </div>
            <button onClick={() => setAutoMode(!autoMode)}
              className={clsx(
                'w-11 h-6 rounded-full transition-all relative focus:outline-none focus:ring-2 focus:ring-primary/50',
                autoMode ? 'bg-primary' : 'bg-surface-active'
              )}>
              <div className={clsx(
                'w-4 h-4 rounded-full bg-white absolute top-1 transition-all shadow-sm',
                autoMode ? 'left-6' : 'left-1'
              )} />
            </button>
          </div>

          <button onClick={handleLaunch} disabled={launching}
            className="btn-primary w-full flex items-center justify-center gap-2 h-11 text-[15px]">
            {launching ? (
              <><span className="animate-spin">⟳</span> Launching...</>
            ) : (
              <><Play size={16} fill="currentColor" className="opacity-80" /> Launch Cycle</>
            )}
          </button>
        </div>

        {/* Recent cycles */}
        <div className="card lg:col-span-2 flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                <TrendingUp size={16} className="text-primary" />
              </div>
              <h2 className="text-lg font-semibold tracking-tight text-text-primary">Recent Cycles</h2>
            </div>
            <span className="badge-muted">{cycles.length} Total</span>
          </div>

          {cycles.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center py-16 border border-dashed border-border rounded-lg bg-background/50">
              <div className="w-12 h-12 rounded-full bg-surface-hover flex items-center justify-center mb-4">
                <Zap size={20} className="text-text-muted" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary mb-1">No cycles yet</h3>
              <p className="text-[13px] text-text-secondary max-w-[200px]">Configure your settings on the left and launch your first AI trading cycle.</p>
            </div>
          ) : (
            <div className="space-y-2 flex-1 overflow-y-auto pr-2 -mr-2">
              {cycles.slice(0, 8).map(cycle => {
                const cfg = STATUS_CONFIG[cycle.status] ?? STATUS_CONFIG.failed
                const Icon = cfg.icon
                return (
                  <button key={cycle.cycle_id}
                    onClick={() => navigate(`/cycle/${cycle.cycle_id}`)}
                    className="w-full flex items-center gap-4 p-3.5 rounded-lg bg-background border border-transparent hover:border-border hover:bg-surface-hover transition-all text-left group">
                    <div className={clsx('w-9 h-9 rounded-full flex items-center justify-center shrink-0 border bg-surface', 
                      cycle.status === 'executed' ? 'border-success/20 text-success' : 
                      cycle.status === 'awaiting_human' ? 'border-warning/20 text-warning' :
                      cycle.status === 'running' ? 'border-primary/20 text-primary' : 'border-border text-text-muted'
                    )}>
                      <Icon size={16} className="opacity-80" />
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2.5 mb-1">
                        <span className="text-[13px] font-mono text-text-primary font-medium tracking-wide">
                          {cycle.cycle_id.split('-')[0]}
                        </span>
                        <span className={clsx(
                          'text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded-md border',
                          cycle.mode === 'short_term'
                            ? 'text-primary border-primary/20 bg-primary/5'
                            : 'text-warning border-warning/20 bg-warning/5'
                        )}>
                          {cycle.mode === 'short_term' ? 'Short Term' : 'Long Term'}
                        </span>
                      </div>
                      <p className={clsx('text-[12px] font-medium', cfg.color)}>{cfg.label}</p>
                    </div>
                    
                    <div className="text-right shrink-0 flex flex-col items-end gap-1">
                      <p className="text-[12px] text-text-muted">
                        {cycle.started_at
                          ? formatDistanceToNow(new Date(cycle.started_at), { addSuffix: true })
                          : '—'}
                      </p>
                      <div className="w-6 h-6 rounded-full flex items-center justify-center bg-surface group-hover:bg-background border border-transparent group-hover:border-border transition-colors">
                        <ChevronRight size={14} className="text-text-muted group-hover:text-text-primary" />
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
