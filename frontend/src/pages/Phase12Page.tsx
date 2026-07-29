import { useEffect, useState } from 'react'
import api from '../store/api'
import {
  Brain, BarChart2, TrendingUp, RefreshCw, Play, Plus,
  ChevronDown, ChevronUp, Activity, Target, Zap,
} from 'lucide-react'
import clsx from 'clsx'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'

const TABS = [
  { key: 'strategies', label: 'Strategies',   icon: Zap },
  { key: 'backtest',   label: 'Backtest',      icon: BarChart2 },
  { key: 'rl',         label: 'RL Weights',    icon: Brain },
  { key: 'portfolios', label: 'Multi-Portfolio', icon: Activity },
]

const STRATEGY_COLORS: Record<string, string> = {
  momentum:         '#6366f1', // primary (indigo)
  mean_reversion:   '#8b5cf6', // accent (violet)
  sector_rotation:  '#f59e0b', // warning (amber)
  earnings_play:    '#3b82f6', // blue
  value_investing:  '#ec4899', // pink
  defensive:        '#10b981', // success (emerald)
  india_momentum:   '#ff9800', // orange
}

function Badge({ label, color = '#71717a' }: { label: string; color?: string }) {
  return (
    <span style={{
      fontSize: 10, padding: '2px 8px', borderRadius: 6,
      border: `1px solid ${color}30`, background: `${color}10`,
      color, fontFamily: 'inherit', letterSpacing: '0.05em', fontWeight: 600, textTransform: 'uppercase'
    }}>{label}</span>
  )
}

// ── Strategies Tab ─────────────────────────────────────────────

function StrategiesTab() {
  const [strategies, setStrategies] = useState<any[]>([])
  const [recommendation, setRecommendation] = useState<any>(null)
  const [regime, setRegime] = useState('NEUTRAL')
  const [mode, setMode]     = useState('short_term')
  const [market, setMarket] = useState('us')
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    api.get('/strategies').then(r => setStrategies(r.data)).catch(() => {})
  }, [])

  const getRecommendation = async () => {
    const r = await api.get('/strategies/recommend', { params: { macro_regime: regime, mode, market } })
    setRecommendation(r.data)
  }

  return (
    <div className="space-y-6">
      {/* Recommendation tool */}
      <div className="card border-primary/20 bg-gradient-to-br from-surface to-primary/5">
        <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center">
            <Target size={14} className="text-primary" />
          </div>
          Strategy Recommender
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
          {[
            { label: 'Macro Regime', key: 'regime', options: ['GOLDILOCKS','REFLATION','NEUTRAL','STAGFLATION','RATE_HIKE_CYCLE','RATE_CUT_CYCLE','DEFLATION_RISK'], val: regime, set: setRegime },
            { label: 'Mode', key: 'mode', options: ['short_term','long_term'], val: mode, set: setMode },
            { label: 'Market', key: 'market', options: ['us','india'], val: market, set: setMarket },
          ].map(({ label, options, val, set }) => (
            <div key={label}>
              <p className="text-xs font-medium text-text-secondary mb-1.5">{label}</p>
              <select value={val} onChange={e => set(e.target.value)} className="input-field cursor-pointer">
                {options.map(o => <option key={o} value={o}>{o.replace('_',' ')}</option>)}
              </select>
            </div>
          ))}
        </div>
        <button onClick={getRecommendation} className="btn-primary w-full md:w-auto text-[13px] flex items-center justify-center gap-2 h-9">
          <Brain size={14} /> Get Recommendation
        </button>
        {recommendation && (
          <div className="mt-4 p-4 bg-background rounded-lg border border-primary/20 shadow-sm animate-slide-in">
            <p className="text-[11px] font-medium text-text-secondary uppercase tracking-wider mb-1">Recommended strategy</p>
            <p className="font-semibold text-lg text-primary">{recommendation.recommended}</p>
            <p className="text-[13px] text-text-muted mt-2 leading-relaxed">{recommendation.reasoning}</p>
          </div>
        )}
      </div>

      {/* Strategy cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {strategies.map((s: any) => {
          const color = STRATEGY_COLORS[s.key] || '#71717a'
          const isOpen = expanded === s.key
          return (
            <div key={s.key} className="card cursor-pointer hover:border-border-bright hover:shadow-md transition-all group overflow-hidden"
              onClick={() => setExpanded(isOpen ? null : s.key)}>
              <div className="flex items-start justify-between gap-3 relative z-10">
                <div className="flex-1">
                  <div className="flex items-center gap-2.5 mb-2">
                    <span className="text-sm font-semibold text-text-primary tracking-tight">{s.name}</span>
                    <Badge label={s.mode === 'short_term' ? 'ST' : 'LT'} color={color} />
                    <Badge label={`min ${(s.min_conviction * 100).toFixed(0)}%`} color={color} />
                  </div>
                  <p className="text-[13px] text-text-muted leading-relaxed">
                    {isOpen ? s.description : s.description.slice(0, 90) + '…'}
                  </p>
                </div>
                <div className={clsx("w-6 h-6 rounded-full flex items-center justify-center bg-surface-hover transition-colors", isOpen ? "bg-primary/10" : "group-hover:bg-border")}>
                  {isOpen ? <ChevronUp size={14} className="text-primary" />
                         : <ChevronDown size={14} className="text-text-muted group-hover:text-text-primary" />}
                </div>
              </div>
              
              <div className={clsx(
                "transition-all duration-300 ease-in-out origin-top",
                isOpen ? "opacity-100 max-h-[500px] mt-4 pt-4 border-t border-border" : "opacity-0 max-h-0 overflow-hidden"
              )}>
                <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider mb-3">Agent Weights</p>
                <div className="space-y-2.5">
                  {Object.entries(s.agent_weights || {}).map(([k, v]: any) => (
                    <div key={k} className="flex items-center gap-3">
                      <p className="text-[12px] text-text-muted w-32 truncate">{k}</p>
                      <div className="flex-1 h-1.5 bg-background rounded-full overflow-hidden border border-border/50">
                        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${(v as number) * 100}%`, background: color }} />
                      </div>
                      <p className="text-[12px] font-mono font-medium text-text-primary w-10 text-right">{((v as number) * 100).toFixed(0)}%</p>
                    </div>
                  ))}
                </div>
                <div className="mt-5">
                  <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider mb-2">Regime Fit</p>
                  <div className="flex gap-2 flex-wrap">
                    {s.regime_fit?.map((r: string) => <Badge key={r} label={r} color={color} />)}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Backtest Tab ───────────────────────────────────────────────

function BacktestTab() {
  const [form, setForm] = useState({
    strategy: 'momentum', symbols: 'NVDA,AAPL,MSFT',
    start_date: '2024-01-01', end_date: '2024-12-31',
    mode: 'short_term', market: 'us',
    initial_capital: 100000, rebalance_freq: 'weekly',
  })
  const [running, setRunning]     = useState(false)
  const [backtestId, setBacktestId] = useState<string | null>(null)
  const [result, setResult]       = useState<any>(null)
  const [trades, setTrades]       = useState<any[]>([])
  const [history, setHistory]     = useState<any[]>([])
  const [polling, setPolling]     = useState(false)

  const runBacktest = async () => {
    setRunning(true)
    setResult(null)
    setTrades([])
    try {
      const r = await api.post('/backtest/run', {
        ...form,
        symbols: form.symbols.split(',').map(s => s.trim()),
        initial_capital: Number(form.initial_capital),
      })
      setBacktestId(r.data.backtest_id)
      setPolling(true)
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => {
    if (!polling || !backtestId) return
    const t = setInterval(async () => {
      try {
        const r = await api.get(`/backtest/${backtestId}`)
        setResult(r.data)
        const t2 = await api.get(`/backtest/${backtestId}/trades`)
        setTrades(t2.data)
        setPolling(false)
      } catch {
        // still running
      }
    }, 3000)
    return () => clearInterval(t)
  }, [polling, backtestId])

  useEffect(() => {
    api.get('/backtest').then(r => setHistory(r.data)).catch(() => {})
  }, [result])

  return (
    <div className="space-y-6">
      {/* Config form */}
      <div className="card space-y-5">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-accent/10 flex items-center justify-center">
            <BarChart2 size={14} className="text-accent" />
          </div>
          Configure Backtest
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <p className="text-[13px] font-medium text-text-secondary mb-1.5">Strategy</p>
            <select value={form.strategy} onChange={e => setForm(f => ({ ...f, strategy: e.target.value }))} className="input-field cursor-pointer">
              {['momentum','mean_reversion','sector_rotation','earnings_play','value_investing','defensive','india_momentum'].map(s => (
                <option key={s} value={s}>{s.replace('_', ' ')}</option>
              ))}
            </select>
          </div>
          <div>
            <p className="text-[13px] font-medium text-text-secondary mb-1.5">Symbols (comma-separated)</p>
            <input value={form.symbols} onChange={e => setForm(f => ({ ...f, symbols: e.target.value }))} className="input-field font-mono text-xs" />
          </div>
          <div>
            <p className="text-[13px] font-medium text-text-secondary mb-1.5">Initial Capital ($)</p>
            <input type="number" value={form.initial_capital} onChange={e => setForm(f => ({ ...f, initial_capital: Number(e.target.value) }))} className="input-field font-mono" />
          </div>
          <div>
            <p className="text-[13px] font-medium text-text-secondary mb-1.5">Start Date</p>
            <input type="date" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} className="input-field" />
          </div>
          <div>
            <p className="text-[13px] font-medium text-text-secondary mb-1.5">End Date</p>
            <input type="date" value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} className="input-field" />
          </div>
          <div>
            <p className="text-[13px] font-medium text-text-secondary mb-1.5">Rebalance</p>
            <select value={form.rebalance_freq} onChange={e => setForm(f => ({ ...f, rebalance_freq: e.target.value }))} className="input-field cursor-pointer">
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
        </div>
        
        <div className="flex flex-col sm:flex-row items-center gap-4 pt-2 border-t border-border">
          <button onClick={runBacktest} disabled={running || polling} className="btn-primary w-full sm:w-auto h-10 flex items-center justify-center gap-2">
            {running || polling ? <><RefreshCw size={14} className="animate-spin" /> Running Simulation…</>
                                : <><Play size={14} fill="currentColor" /> Run Backtest</>}
          </button>
          {polling && (
            <p className="text-[13px] text-text-muted animate-pulse">
              Engine running… polling every 3 seconds.
            </p>
          )}
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-6 animate-fade-in">
          {/* Key metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Total Return', value: `${result.total_return_pct > 0 ? '+' : ''}${result.total_return_pct?.toFixed(2)}%`, pos: result.total_return_pct >= 0 },
              { label: 'Sharpe Ratio', value: result.sharpe_ratio?.toFixed(2), pos: result.sharpe_ratio >= 1 },
              { label: 'Max Drawdown', value: `-${result.max_drawdown_pct?.toFixed(2)}%`, pos: false },
              { label: 'Win Rate', value: `${(result.win_rate * 100).toFixed(1)}%`, pos: result.win_rate >= 0.5 },
              { label: 'Annualised', value: `${result.annualised_return?.toFixed(2)}%`, pos: result.annualised_return >= 0 },
              { label: 'Profit Factor', value: result.profit_factor?.toFixed(2), pos: result.profit_factor >= 1 },
              { label: 'Total Trades', value: result.total_trades, pos: true },
              { label: 'Avg Hold Days', value: result.avg_hold_days?.toFixed(1), pos: true },
            ].map(({ label, value, pos }) => (
              <div key={label} className="card p-4 flex flex-col justify-center">
                <p className="text-[12px] font-medium text-text-secondary mb-1">{label}</p>
                <p className={clsx('font-mono text-xl font-semibold', pos ? 'text-success' : 'text-danger')}>{value}</p>
              </div>
            ))}
          </div>

          {/* Equity curve */}
          {result.equity_curve?.length > 1 && (
            <div className="card">
              <h4 className="text-[12px] font-semibold text-text-secondary uppercase tracking-wider mb-4">Equity Curve</h4>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={result.equity_curve} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="btGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => v.slice(5)} dy={10} minTickGap={30} />
                  <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} dx={-10} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', fontSize: '12px', color: '#fafafa', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                    itemStyle={{ color: '#6366f1', fontWeight: 600 }}
                    formatter={(v: any) => [`$${Number(v).toLocaleString(undefined, {minimumFractionDigits: 2})}`, 'NAV']} 
                    labelStyle={{ color: '#a1a1aa', marginBottom: '4px' }}
                  />
                  <ReferenceLine y={result.initial_capital} stroke="#3f3f46" strokeDasharray="4 4" />
                  <Area type="monotone" dataKey="nav" stroke="#6366f1" strokeWidth={2} fill="url(#btGrad)" activeDot={{ r: 4, fill: '#6366f1', stroke: '#18181b', strokeWidth: 2 }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Agent attribution */}
            {result.agent_attribution && Object.keys(result.agent_attribution).length > 0 && (
              <div className="card">
                <h4 className="text-[12px] font-semibold text-text-secondary uppercase tracking-wider mb-4">
                  Signal Attribution <span className="normal-case text-text-muted font-normal ml-1">(correlation with P&L)</span>
                </h4>
                <div className="space-y-3">
                  {Object.entries(result.agent_attribution).map(([k, v]: any) => (
                    <div key={k} className="flex items-center gap-3">
                      <p className="text-[13px] font-medium text-text-primary w-32 truncate">{k.replace('_score', '')}</p>
                      <div className="flex-1 h-2 bg-background rounded-full overflow-hidden border border-border/50">
                        <div className={clsx('h-full rounded-full transition-all duration-500', (v as number) >= 0 ? 'bg-success' : 'bg-danger')} style={{ width: `${Math.abs(v as number) * 100}%` }} />
                      </div>
                      <p className={clsx('text-[13px] font-mono font-medium w-16 text-right', (v as number) >= 0 ? 'text-success' : 'text-danger')}>
                        {(v as number) >= 0 ? '+' : ''}{(v as number).toFixed(3)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Walk-forward */}
            {result.walkforward?.length > 0 && (
              <div className="card">
                <h4 className="text-[12px] font-semibold text-text-secondary uppercase tracking-wider mb-4">
                  Walk-Forward Validation
                </h4>
                <div className="space-y-2">
                  {result.walkforward.map((wf: any) => (
                    <div key={wf.period} className="p-3 bg-background border border-border rounded-lg flex flex-col gap-2 hover:border-border-bright transition-colors">
                      <div className="flex justify-between items-center">
                        <span className="text-[13px] font-semibold text-text-primary">{wf.period}</span>
                        <span className={clsx('text-[14px] font-mono font-semibold', (wf.return || 0) >= 0 ? 'text-success' : 'text-danger')}>
                          {wf.return >= 0 ? '+' : ''}{wf.return?.toFixed(2)}%
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-[12px] text-text-muted">
                        <span className="flex items-center gap-1"><span className="text-text-secondary">Sharpe:</span> {wf.sharpe?.toFixed(2)}</span>
                        <span className="w-1 h-1 rounded-full bg-border" />
                        <span className="flex items-center gap-1"><span className="text-text-secondary">WR:</span> {(wf.win_rate * 100)?.toFixed(0)}%</span>
                        <span className="w-1 h-1 rounded-full bg-border" />
                        <span className="flex items-center gap-1"><span className="text-text-secondary">Trades:</span> {wf.trades}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Trade list */}
          {trades.length > 0 && (
            <div className="card p-0 overflow-hidden">
              <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-surface/50">
                <h4 className="text-[13px] font-semibold text-text-primary">Simulated Trades</h4>
                <span className="badge-muted">{trades.length} Total</span>
              </div>
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto custom-scrollbar">
                <table className="w-full text-left border-collapse">
                  <thead className="sticky top-0 bg-surface border-b border-border z-10">
                    <tr>
                      {['Symbol','Dir','Entry','Exit','Entry $','Exit $','P&L','Hold','Reason'].map(h => (
                        <th key={h} className="px-4 py-2.5 text-[11px] font-semibold text-text-secondary uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {trades.map((t: any) => (
                      <tr key={t.id} className="hover:bg-surface-hover/50 transition-colors group">
                        <td className="px-4 py-3 font-mono text-[13px] font-medium text-text-primary">{t.symbol}</td>
                        <td className="px-4 py-3">
                          <span className={clsx("text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border", t.direction === 'long' ? 'text-success border-success/20 bg-success/10' : 'text-danger border-danger/20 bg-danger/10')}>
                            {t.direction?.toUpperCase()}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-[12px] text-text-secondary whitespace-nowrap">{t.entry_date}</td>
                        <td className="px-4 py-3 text-[12px] text-text-secondary whitespace-nowrap">{t.exit_date || '—'}</td>
                        <td className="px-4 py-3 font-mono text-[13px] text-text-primary">${t.entry_price?.toFixed(2)}</td>
                        <td className="px-4 py-3 font-mono text-[13px] text-text-primary">{t.exit_price ? `$${t.exit_price?.toFixed(2)}` : '—'}</td>
                        <td className={clsx('px-4 py-3 font-mono text-[13px] font-semibold', t.pnl_pct >= 0 ? 'text-success' : 'text-danger')}>
                          {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct?.toFixed(2)}%
                        </td>
                        <td className="px-4 py-3 text-[12px] text-text-muted">{t.hold_days}d</td>
                        <td className="px-4 py-3 text-[12px] text-text-muted truncate max-w-[120px]" title={t.exit_reason}>{t.exit_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Past backtests */}
      {history.length > 0 && !result && (
        <div className="card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-border bg-surface/50">
            <h4 className="text-[13px] font-semibold text-text-primary">Past Backtests</h4>
          </div>
          <div className="divide-y divide-border">
            {history.slice(0, 10).map((bt: any) => (
              <div key={bt.id} className="px-5 py-4 flex items-center justify-between hover:bg-surface-hover transition-colors cursor-pointer group"
                onClick={async () => {
                  const r = await api.get(`/backtest/${bt.id}`)
                  setResult(r.data)
                  const t2 = await api.get(`/backtest/${bt.id}/trades`)
                  setTrades(t2.data)
                }}>
                <div className="flex gap-4 items-center">
                  <div className="w-10 h-10 rounded-full bg-background border border-border flex items-center justify-center group-hover:border-primary/50 transition-colors">
                    <BarChart2 size={16} className="text-text-muted group-hover:text-primary transition-colors" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-text-primary capitalize">{bt.strategy.replace('_', ' ')}</p>
                    <p className="text-[12px] text-text-secondary mt-0.5">{bt.start_date} → {bt.end_date} <span className="mx-1 opacity-50">|</span> <span className="uppercase">{bt.market}</span></p>
                  </div>
                </div>
                <div className="text-right flex items-center gap-6">
                  <div className="hidden md:block">
                    <p className="text-[12px] font-medium text-text-secondary">Trades</p>
                    <p className="text-[13px] font-mono text-text-primary mt-0.5">{bt.total_trades}</p>
                  </div>
                  <div className="hidden sm:block">
                    <p className="text-[12px] font-medium text-text-secondary">Sharpe</p>
                    <p className="text-[13px] font-mono text-text-primary mt-0.5">{bt.sharpe_ratio?.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-[12px] font-medium text-text-secondary text-right mb-0.5">Return</p>
                    <Badge label={`${(bt.total_return_pct || 0) >= 0 ? '+' : ''}${bt.total_return_pct?.toFixed(2)}%`} color={(bt.total_return_pct || 0) >= 0 ? '#10b981' : '#ef4444'} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── RL Weights Tab ─────────────────────────────────────────────

function RLTab() {
  const [data, setData]     = useState<any>(null)
  const [market, setMarket] = useState('us')
  const [resetting, setResetting] = useState(false)

  const load = async () => {
    const r = await api.get('/rl/weights', { params: { market } })
    setData(r.data)
  }

  const reset = async () => {
    setResetting(true)
    await api.post('/rl/reset', null, { params: { market } })
    await load()
    setResetting(false)
  }

  useEffect(() => { load() }, [market])

  const signalLabels: Record<string, string> = {
    quant_score:        'Quant / Technical',
    fundamental_score:  'Fundamental',
    technical_score:    'Chart Patterns',
    news_score:         'News & Sentiment',
    macro_score:        'Macro Intelligence',
    options_flow_score: 'Options Flow',
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <Brain size={18} className="text-primary" /> Reinforcement Learning Weights
          </h3>
          <p className="text-[13px] text-text-secondary mt-1 max-w-2xl">
            UCB1 bandit auto-adjusts weights based on live trade outcomes.
            Signals that predict profitable trades receive higher weightings dynamically over time.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select value={market} onChange={e => setMarket(e.target.value)} className="input-field py-1.5 w-32 uppercase text-xs font-semibold tracking-wider">
            <option value="us">US Market</option>
            <option value="india">India Market</option>
          </select>
          <button onClick={reset} disabled={resetting} className="btn-ghost flex items-center gap-2 py-1.5 border-danger/30 text-danger hover:bg-danger-dim hover:text-danger hover:border-danger">
            <RefreshCw size={14} className={resetting ? 'animate-spin' : ''} /> Reset
          </button>
        </div>
      </div>

      {data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="card bg-gradient-to-br from-surface to-primary/5 border-primary/20">
              <p className="text-[12px] font-semibold text-text-secondary uppercase tracking-wider mb-2">Dominant Signal</p>
              <p className="text-2xl font-semibold text-primary">{signalLabels[data.performance?.top_signal] || data.performance?.top_signal || 'None'}</p>
            </div>
            <div className="card">
              <p className="text-[12px] font-semibold text-text-secondary uppercase tracking-wider mb-2">Trades Learned From</p>
              <p className="text-2xl font-mono font-semibold text-text-primary">
                {data.performance?.total_trades_learned_from ?? 0}
              </p>
            </div>
          </div>

          <div className="card space-y-6">
            <h4 className="text-[13px] font-semibold text-text-primary">Current Weight Distribution</h4>
            <div className="space-y-5">
              {Object.entries(data.weights || {}).sort(([,a]: any, [,b]: any) => b - a).map(([key, weight]: any) => {
                const perf = data.performance?.signals?.find((s: any) => s.signal === key)
                return (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-[14px] font-medium text-text-primary">{signalLabels[key] || key}</p>
                      <div className="flex items-center gap-4">
                        {perf && (
                          <span className={clsx('text-[12px] font-mono font-medium px-2 py-0.5 rounded-full bg-background border', perf.avg_reward >= 0 ? 'text-success border-success/20' : 'text-danger border-danger/20')}>
                            Reward: {perf.avg_reward >= 0 ? '+' : ''}{perf.avg_reward?.toFixed(3)}
                          </span>
                        )}
                        <p className="text-[14px] font-mono font-semibold text-primary w-14 text-right">
                          {((weight as number) * 100).toFixed(1)}%
                        </p>
                      </div>
                    </div>
                    <div className="h-2.5 bg-background rounded-full overflow-hidden border border-border/50">
                      <div className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary transition-all duration-1000 ease-out"
                        style={{ width: `${(weight as number) * 100}%` }} />
                    </div>
                    {perf && (
                      <div className="flex items-center gap-3 mt-1.5">
                        <p className="text-[11px] text-text-muted font-medium uppercase tracking-wide">
                          Samples: <span className="text-text-secondary">{perf.trade_count}</span>
                        </p>
                        {perf.last_updated && (
                          <>
                            <span className="w-1 h-1 rounded-full bg-border" />
                            <p className="text-[11px] text-text-muted font-medium uppercase tracking-wide">
                              Updated: <span className="text-text-secondary">{new Date(perf.last_updated).toLocaleDateString()}</span>
                            </p>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── Multi-Portfolio Tab ────────────────────────────────────────

function PortfoliosTab() {
  const [portfolios, setPortfolios] = useState<any[]>([])
  const [launching, setLaunching]   = useState(false)
  const [showAdd, setShowAdd]       = useState(false)
  const [newPortfolio, setNewPortfolio] = useState({
    portfolio_id: '', name: '', strategy: 'momentum',
    allocation_pct: 0.2, mode: 'short_term', market: 'us',
    auto_mode: false, description: '',
  })

  const load = async () => {
    const r = await api.get('/portfolios')
    setPortfolios(r.data)
  }

  useEffect(() => { load() }, [])

  const launchAll = async () => {
    setLaunching(true)
    try {
      await api.post('/portfolios/run-all')
      setTimeout(load, 2000)
    } finally {
      setLaunching(false)
    }
  }

  const addPortfolio = async () => {
    await api.post('/portfolios', {
      ...newPortfolio,
      allocation_pct: Number(newPortfolio.allocation_pct),
    })
    setShowAdd(false)
    await load()
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <Activity size={18} className="text-primary" /> Multi-Portfolio Manager
          </h3>
          <p className="text-[13px] text-text-secondary mt-1">
            Run separate strategy portfolios simultaneously. Each gets its own isolated cycle and risk budget.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setShowAdd(!showAdd)} className="btn-ghost flex items-center gap-2 h-10">
            <Plus size={16} /> Add Portfolio
          </button>
          <button onClick={launchAll} disabled={launching} className="btn-primary flex items-center gap-2 h-10 shadow-glow">
            {launching ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" className="opacity-80" />}
            Launch All Active
          </button>
        </div>
      </div>

      {showAdd && (
        <div className="card border-primary/30 bg-primary/5 animate-slide-in">
          <div className="flex items-center justify-between mb-5">
            <h4 className="text-[14px] font-semibold text-text-primary">Create New Portfolio</h4>
            <button onClick={() => setShowAdd(false)} className="text-text-muted hover:text-text-primary"><Plus size={20} className="rotate-45" /></button>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
            <div>
              <p className="text-[12px] font-medium text-text-secondary mb-1.5">Portfolio ID</p>
              <input value={newPortfolio.portfolio_id} placeholder="e.g. swing_us" onChange={e => setNewPortfolio(p => ({ ...p, portfolio_id: e.target.value }))} className="input-field" />
            </div>
            <div>
              <p className="text-[12px] font-medium text-text-secondary mb-1.5">Display Name</p>
              <input value={newPortfolio.name} placeholder="e.g. US Swing Trades" onChange={e => setNewPortfolio(p => ({ ...p, name: e.target.value }))} className="input-field" />
            </div>
            <div>
              <p className="text-[12px] font-medium text-text-secondary mb-1.5">Strategy</p>
              <select value={newPortfolio.strategy} onChange={e => setNewPortfolio(p => ({ ...p, strategy: e.target.value }))} className="input-field">
                {['momentum','mean_reversion','sector_rotation','value_investing','defensive','india_momentum'].map(s => (
                  <option key={s} value={s}>{s.replace('_',' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <p className="text-[12px] font-medium text-text-secondary mb-1.5">Capital Allocation % (0.01 - 1.0)</p>
              <input type="number" min="0.01" max="1" step="0.05" value={newPortfolio.allocation_pct} onChange={e => setNewPortfolio(p => ({ ...p, allocation_pct: Number(e.target.value) }))} className="input-field font-mono" />
            </div>
            <div>
              <p className="text-[12px] font-medium text-text-secondary mb-1.5">Mode</p>
              <select value={newPortfolio.mode} onChange={e => setNewPortfolio(p => ({ ...p, mode: e.target.value }))} className="input-field">
                <option value="short_term">Short Term</option>
                <option value="long_term">Long Term</option>
              </select>
            </div>
            <div>
              <p className="text-[12px] font-medium text-text-secondary mb-1.5">Market</p>
              <select value={newPortfolio.market} onChange={e => setNewPortfolio(p => ({ ...p, market: e.target.value }))} className="input-field uppercase">
                <option value="us">US</option>
                <option value="india">India</option>
              </select>
            </div>
          </div>
          
          <div className="flex justify-end gap-3 pt-4 border-t border-border">
            <button onClick={() => setShowAdd(false)} className="btn-ghost">Cancel</button>
            <button onClick={addPortfolio} disabled={!newPortfolio.portfolio_id || !newPortfolio.name} className="btn-primary">Save Portfolio</button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {portfolios.map((p: any) => {
          const color = STRATEGY_COLORS[p.strategy] || '#71717a'
          return (
            <div key={p.portfolio_id} className="card relative overflow-hidden group">
              <div className="absolute top-0 left-0 w-1 h-full" style={{ backgroundColor: color }} />
              
              <div className="flex items-start justify-between mb-5 ml-2">
                <div>
                  <h4 className="text-lg font-semibold text-text-primary tracking-tight">{p.name}</h4>
                  <div className="flex gap-2 mt-2 flex-wrap">
                    <Badge label={p.strategy.replace('_',' ')} color={color} />
                    <Badge label={p.mode === 'short_term' ? 'Short Term' : 'Long Term'} />
                    <Badge label={p.market?.toUpperCase()} />
                    <Badge label={`${(p.allocation_pct * 100).toFixed(0)}% alloc`} />
                  </div>
                </div>
                <div className="flex items-center gap-2 bg-background px-3 py-1.5 rounded-full border border-border">
                  <div className={clsx('w-2 h-2 rounded-full', p.active ? 'bg-success animate-pulse' : 'bg-text-muted')} />
                  <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">{p.active ? 'Active' : 'Paused'}</span>
                </div>
              </div>
              
              <div className="grid grid-cols-3 gap-3 ml-2">
                {[
                  { label: 'Total Trades', value: p.total_trades ?? 0 },
                  { label: 'Win Rate', value: p.win_rate != null ? `${(p.win_rate * 100).toFixed(0)}%` : '—' },
                  { label: 'Net P&L', value: p.total_pnl != null ? `$${p.total_pnl.toFixed(0)}` : '—', colored: true, pos: (p.total_pnl ?? 0) >= 0 },
                ].map(({ label, value, colored, pos }) => (
                  <div key={label} className="bg-background rounded-lg p-3 border border-border group-hover:border-border-bright transition-colors">
                    <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider mb-1">{label}</p>
                    <p className={clsx('text-lg font-mono font-semibold',
                      colored ? (pos ? 'text-success' : 'text-danger') : 'text-text-primary'
                    )}>{value}</p>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────

export default function Phase12Page() {
  const [tab, setTab] = useState('strategies')
  const Tab = { strategies: StrategiesTab, backtest: BacktestTab, rl: RLTab, portfolios: PortfoliosTab }[tab] || StrategiesTab

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary-glow border border-primary/20 flex items-center justify-center">
              <Brain size={20} className="text-primary" />
            </div>
            Intelligence Hub
          </h1>
          <p className="text-text-secondary text-sm mt-2">
            Explore autonomous strategies, run historical backtests, and manage RL agent weights.
          </p>
        </div>
      </div>
      
      <div className="flex gap-2 border-b border-border pb-px overflow-x-auto custom-scrollbar">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={clsx('flex items-center gap-2 text-[13px] font-medium px-4 py-2.5 rounded-t-lg transition-all border-b-2 whitespace-nowrap',
              tab === key ? 'bg-surface border-primary text-primary' : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-surface-hover')}>
            <Icon size={16} className={clsx(tab === key ? "text-primary" : "opacity-70")} /> {label}
          </button>
        ))}
      </div>
      
      <div className="pt-2">
        <Tab />
      </div>
    </div>
  )
}
