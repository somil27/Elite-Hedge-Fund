import { useEffect, useState } from 'react'
import api from '../store/api'
import {
  TrendingUp, TrendingDown, Bell, BellOff, RefreshCw,
  Link, Unlink, BarChart2, AlertTriangle, Brain, ChevronRight,
  IndianRupee, Shield, PieChart, Activity, Briefcase,
} from 'lucide-react'
import clsx from 'clsx'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
         PieChart as RechartsPie, Pie, Cell } from 'recharts'
import { format } from 'date-fns'

const BROKERS = [
  { key: 'zerodha', label: 'Zerodha', color: '#387ed1', desc: 'Kite Connect' },
  { key: 'upstox',  label: 'Upstox',  color: '#6f42c1', desc: 'API v2' },
]
const COLORS = ['#6366f1','#8b5cf6','#f59e0b','#3b82f6','#ec4899','#10b981','#ff9800','#ef4444']

export default function IndiaPage() {
  const [connections, setConnections]   = useState<any[]>([])
  const [activeBroker, setActiveBroker] = useState<string | null>(null)
  const [portfolio, setPortfolio]       = useState<any>(null)
  const [analysis, setAnalysis]         = useState<any>(null)
  const [alerts, setAlerts]             = useState<any[]>([])
  const [history, setHistory]           = useState<any[]>([])
  const [loading, setLoading]           = useState(false)
  const [analysing, setAnalysing]       = useState(false)
  const [tab, setTab]                   = useState<'portfolio'|'analysis'|'alerts'|'orders'>('portfolio')
  const [orders, setOrders]             = useState<any[]>([])
  const [toast, setToast]               = useState<string | null>(null)

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 3500) }

  useEffect(() => { loadConnections() }, [])

  useEffect(() => {
    if (activeBroker) {
      loadPortfolio(activeBroker)
      loadAlerts(activeBroker)
      loadHistory(activeBroker)
    }
  }, [activeBroker])

  const loadConnections = async () => {
    try {
      const data = await api.get('/india/connections').then(r => r.data)
      setConnections(data)
      const active = data.find((c: any) => c.is_active)
      if (active && !activeBroker) setActiveBroker(active.broker)
    } catch {}
  }

  const loadPortfolio = async (broker: string) => {
    setLoading(true)
    try {
      const data = await api.get(`/india/${broker}/portfolio`).then(r => r.data)
      setPortfolio(data)
    } catch (e: any) {
      showToast(`❌ ${e?.response?.data?.detail || 'Failed to load portfolio'}`)
    } finally { setLoading(false) }
  }

  const loadAlerts = async (broker: string) => {
    try {
      const data = await api.get(`/india/${broker}/alerts`).then(r => r.data)
      setAlerts(data)
    } catch {}
  }

  const loadHistory = async (broker: string) => {
    try {
      const data = await api.get(`/india/${broker}/snapshot/history?days=30`).then(r => r.data)
      setHistory(data)
    } catch {}
  }

  const loadOrders = async (broker: string) => {
    try {
      const data = await api.get(`/india/${broker}/orders`).then(r => r.data)
      setOrders(data)
    } catch {}
  }

  const runAnalysis = async (broker: string) => {
    setAnalysing(true)
    try {
      const data = await api.get(`/india/${broker}/analysis`).then(r => r.data)
      setAnalysis(data)
      setTab('analysis')
    } catch (e: any) {
      showToast('❌ Analysis failed')
    } finally { setAnalysing(false) }
  }

  const runAlertCheck = async (broker: string) => {
    try {
      const data = await api.post(`/india/${broker}/alerts/check`).then(r => r.data)
      showToast(`✅ ${data.new_alerts} new alert(s) found`)
      await loadAlerts(broker)
    } catch { showToast('❌ Alert check failed') }
  }

  const markRead = async (broker: string, alertId: string) => {
    try {
      await api.post(`/india/${broker}/alerts/read`, { alert_ids: [alertId] })
      setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, is_read: true } : a))
    } catch {}
  }

  const connected = connections.filter(c => c.is_active)
  const unreadAlerts = alerts.filter(a => !a.is_read)

  return (
    <div className="space-y-8 animate-fade-in pb-12">
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
            <div className="w-10 h-10 rounded-xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center">
              <IndianRupee size={20} className="text-orange-500" />
            </div>
            India Markets
          </h1>
          <p className="text-text-secondary text-sm mt-2">
            Connect Zerodha & Upstox for automated trading and AI-powered portfolio analytics.
          </p>
        </div>
        {activeBroker && (
          <div className="flex items-center gap-3">
            <button onClick={() => runAlertCheck(activeBroker)}
              className="btn-ghost h-9 flex items-center gap-2 text-[13px] relative">
              <Bell size={14} /> Check Alerts
              {unreadAlerts.length > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-danger text-white text-[10px] font-bold flex items-center justify-center shadow-sm">
                  {unreadAlerts.length}
                </span>
              )}
            </button>
            <button onClick={() => runAnalysis(activeBroker)} disabled={analysing}
              className="btn-primary h-9 flex items-center gap-2 text-[13px] shadow-glow">
              {analysing ? <RefreshCw size={14} className="animate-spin" /> : <Brain size={14} />}
              {analysing ? 'Analysing…' : 'AI Analysis'}
            </button>
          </div>
        )}
      </div>

      {/* Broker connection cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {BROKERS.map(b => {
          const conn = connections.find(c => c.broker === b.key)
          const isConnected = conn?.is_active
          const backendUrl = import.meta.env.VITE_API_URL?.replace(/\/api$/, '') || 'http://localhost:8000';
          
          return (
            <div key={b.key} className={clsx(
              'card flex items-center justify-between transition-all duration-300 relative overflow-hidden group',
              isConnected && activeBroker === b.key ? 'border-primary/50 shadow-glow bg-gradient-to-r from-surface to-primary/5' : 'hover:border-border-bright',
              isConnected ? 'cursor-pointer' : ''
            )}
              onClick={() => isConnected && setActiveBroker(b.key)}>
              {isConnected && activeBroker === b.key && (
                <div className="absolute top-0 left-0 w-1 h-full bg-primary" />
              )}
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center font-bold text-lg text-white shadow-sm"
                  style={{ background: b.color }}>
                  {b.label[0]}
                </div>
                <div>
                  <p className="text-[15px] font-semibold text-text-primary">{b.label}</p>
                  <p className="text-[12px] text-text-secondary mt-0.5">{b.desc}</p>
                  {isConnected && (
                    <p className="text-[12px] font-mono text-primary font-medium mt-1">
                      {conn.broker_user_name || conn.broker_user_id}
                    </p>
                  )}
                </div>
              </div>
              {isConnected ? (
                <div className="flex items-center gap-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-success bg-success/10 px-2 py-1 rounded flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" /> Connected
                  </span>
                  <a href={`${backendUrl}/api/india/${b.key}/connections`}
                    onClick={async (e) => {
                      e.stopPropagation()
                      try {
                        await api.delete(`/india/connections/${b.key}`)
                        showToast(`${b.label} disconnected`)
                        await loadConnections()
                        if (activeBroker === b.key) setActiveBroker(null)
                      } catch {}
                    }}
                    className="p-1.5 text-text-muted hover:text-danger hover:bg-danger/10 rounded-md transition-colors opacity-0 group-hover:opacity-100">
                    <Unlink size={14} />
                  </a>
                </div>
              ) : (
                <a href={`${backendUrl}/api/india/${b.key}/login`}
                  className="btn-primary text-[13px] flex items-center gap-2 h-9 px-4">
                  <Link size={14} /> Connect
                </a>
              )}
            </div>
          )
        })}
      </div>

      {/* Content area — only show if a broker is active and portfolio loaded */}
      {activeBroker && portfolio && (
        <div className="space-y-6 animate-fade-in">
          {/* Portfolio summary */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Portfolio Value',
                value: `₹${(portfolio.summary.total_current_value + portfolio.funds.available_cash).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`,
                highlight: true },
              { label: 'Total P&L',
                value: `₹${portfolio.summary.total_pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`,
                pct:   `${portfolio.summary.total_pnl_pct.toFixed(2)}%`,
                pos:   portfolio.summary.total_pnl >= 0 },
              { label: 'Day P&L',
                value: `₹${portfolio.summary.day_pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`,
                pos:   portfolio.summary.day_pnl >= 0 },
              { label: 'Available Cash',
                value: `₹${portfolio.funds.available_cash.toLocaleString('en-IN', { maximumFractionDigits: 0 })}` },
            ].map(({ label, value, highlight, pos, pct }: any) => (
              <div key={label} className={clsx('card flex flex-col justify-center relative overflow-hidden', highlight && 'border-primary/30 bg-gradient-to-br from-surface to-primary/10')}>
                {highlight && <div className="absolute top-0 right-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl -mr-12 -mt-12" />}
                <p className="text-[12px] font-medium text-text-secondary mb-1.5 relative z-10">{label}</p>
                <div className="flex items-baseline gap-2 relative z-10">
                  <p className={clsx('font-mono text-xl font-semibold',
                    highlight ? 'text-primary' :
                    pos === true ? 'text-success' :
                    pos === false ? 'text-danger' : 'text-text-primary'
                  )}>{value}</p>
                  {pct && (
                    <span className={clsx('text-[12px] font-mono font-medium',
                      pos ? 'text-success' : 'text-danger')}>{pos ? '+' : ''}{pct}</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div className="flex gap-2 border-b border-border pb-px overflow-x-auto custom-scrollbar">
            {[
              { key: 'portfolio', label: 'Holdings', icon: PieChart },
              { key: 'analysis',  label: 'AI Analysis', icon: Brain },
              { key: 'alerts',    label: `Alerts${unreadAlerts.length ? ` (${unreadAlerts.length})` : ''}`, icon: Bell },
              { key: 'orders',    label: 'Orders', icon: BarChart2 },
            ].map(({ key, label, icon: Icon }) => (
              <button key={key}
                onClick={() => {
                  setTab(key as any)
                  if (key === 'orders' && orders.length === 0) loadOrders(activeBroker)
                }}
                className={clsx(
                  'flex items-center gap-2 text-[13px] font-medium px-4 py-2.5 rounded-t-lg transition-all border-b-2 whitespace-nowrap',
                  tab === key
                    ? 'bg-surface border-primary text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                )}>
                <Icon size={16} className={clsx(tab === key ? "text-primary" : "opacity-70")} /> {label}
              </button>
            ))}
          </div>

          <div className="pt-2">
            {/* Portfolio tab */}
            {tab === 'portfolio' && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Holdings table */}
                <div className="lg:col-span-2 card p-0 overflow-hidden flex flex-col max-h-[600px]">
                  <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-surface/50 shrink-0">
                    <h2 className="text-[14px] font-semibold text-text-primary flex items-center gap-2">
                      <Briefcase size={16} className="text-primary" /> Holdings
                    </h2>
                    <div className="flex items-center gap-3">
                      <span className="badge-muted">{portfolio.holdings.length} Assets</span>
                      <button onClick={() => loadPortfolio(activeBroker)} className="text-text-muted hover:text-primary transition-colors">
                        <RefreshCw size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="overflow-x-auto overflow-y-auto custom-scrollbar flex-1">
                    <table className="w-full text-left border-collapse min-w-[600px]">
                      <thead className="sticky top-0 bg-surface border-b border-border z-10">
                        <tr>
                          {['Symbol','Qty','Avg / LTP','Current Value','Total P&L','Day P&L'].map(h => (
                            <th key={h} className="px-5 py-3 text-[11px] font-semibold text-text-secondary uppercase tracking-wider">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {portfolio.holdings.map((h: any) => (
                          <tr key={h.symbol} className="hover:bg-surface-hover/50 transition-colors group">
                            <td className="px-5 py-3.5">
                              <div>
                                <p className="font-mono text-[14px] font-semibold text-text-primary">{h.symbol}</p>
                                <p className="text-[11px] text-text-muted mt-0.5">{h.exchange}</p>
                              </div>
                            </td>
                            <td className="px-5 py-3.5 font-mono text-[13px] font-medium text-text-secondary">{h.quantity}</td>
                            <td className="px-5 py-3.5">
                              <p className="font-mono text-[13px] text-text-secondary">₹{h.avg_price?.toFixed(2)}</p>
                              <p className="font-mono text-[13px] text-text-primary mt-0.5">₹{h.ltp?.toFixed(2)}</p>
                            </td>
                            <td className="px-5 py-3.5 font-mono text-[13px] font-medium text-text-primary">
                              ₹{h.current_value?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                            </td>
                            <td className="px-5 py-3.5">
                              <p className={clsx('font-mono text-[13px] font-semibold', h.pnl >= 0 ? 'text-success' : 'text-danger')}>
                                {h.pnl >= 0 ? '+' : ''}₹{Math.abs(h.pnl).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                              </p>
                              <p className={clsx('font-mono text-[11px] font-medium mt-0.5', h.pnl_pct >= 0 ? 'text-success/80' : 'text-danger/80')}>
                                {h.pnl_pct >= 0 ? '+' : ''}{h.pnl_pct?.toFixed(2)}%
                              </p>
                            </td>
                            <td className="px-5 py-3.5">
                              <span className={clsx('inline-flex items-center gap-1 font-mono text-[12px] font-semibold px-2 py-1 rounded border',
                                h.day_change_pct >= 0 ? 'text-success bg-success/10 border-success/20' : 'text-danger bg-danger/10 border-danger/20')}>
                                {h.day_change_pct >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                {Math.abs(h.day_change_pct)?.toFixed(2)}%
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Allocation pie + value chart */}
                <div className="space-y-6">
                  <div className="card">
                    <h3 className="text-[12px] font-semibold text-text-secondary uppercase tracking-wider mb-4">Allocation Breakdown</h3>
                    <div className="h-[200px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <RechartsPie>
                          <Pie data={portfolio.holdings.map((h: any) => ({
                            name: h.symbol, value: h.current_value
                          }))} cx="50%" cy="50%" innerRadius={60} outerRadius={85}
                            paddingAngle={3} dataKey="value" stroke="none">
                            {portfolio.holdings.map((_: any, i: number) => (
                              <Cell key={i} fill={COLORS[i % COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip 
                            contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', fontSize: '12px', color: '#fafafa', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                            itemStyle={{ color: '#fafafa', fontWeight: 600 }}
                            formatter={(v: any) => [`₹${Number(v).toLocaleString('en-IN')}`, 'Value']} 
                          />
                        </RechartsPie>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Portfolio value history */}
                  {history.length > 1 && (
                    <div className="card">
                      <h3 className="text-[12px] font-semibold text-text-secondary uppercase tracking-wider mb-4">30-Day Trajectory</h3>
                      <div className="h-[140px] w-full ml-[-10px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={history} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                            <defs>
                              <linearGradient id="indiaGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                              </linearGradient>
                            </defs>
                            <XAxis dataKey="snapped_at"
                              tickFormatter={v => format(new Date(v), 'MMM d')}
                              tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} dy={5} minTickGap={20} />
                            <YAxis hide domain={['auto', 'auto']} />
                            <Tooltip 
                              contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', fontSize: '12px', color: '#fafafa', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                              formatter={(v: any) => [`₹${Number(v).toLocaleString('en-IN')}`, 'Value']} 
                            />
                            <Area type="monotone" dataKey="total_value" stroke="#6366f1" strokeWidth={2} fill="url(#indiaGrad)" activeDot={{ r: 4, fill: '#6366f1', stroke: '#18181b', strokeWidth: 2 }} />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Analysis tab */}
            {tab === 'analysis' && (
              <div className="space-y-6">
                {!analysis ? (
                  <div className="card text-center py-20 border-dashed border-2 border-border bg-surface/30">
                    <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
                      <Brain size={32} className="text-primary" />
                    </div>
                    <h3 className="text-lg font-semibold text-text-primary mb-2">AI Portfolio Diagnostics</h3>
                    <p className="text-text-secondary text-[14px] mb-6 max-w-md mx-auto">
                      Run an automated deep-dive on your holdings. Get instant insights on concentration risk, sector balance, and actionable rebalancing advice.
                    </p>
                    <button onClick={() => runAnalysis(activeBroker)} disabled={analysing}
                      className="btn-primary mx-auto flex items-center gap-2 h-11 px-6 shadow-glow">
                      {analysing ? <RefreshCw size={16} className="animate-spin" /> : <Brain size={16} />}
                      {analysing ? 'Generating Analysis…' : 'Start Diagnostics'}
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-fade-in">
                    <div className="space-y-6">
                      {/* Health banner */}
                      <div className={clsx('card border-l-4 p-5 flex flex-col justify-center',
                        analysis.summary?.overall_health === 'excellent' ? 'border-l-success bg-success/5' :
                        analysis.summary?.overall_health === 'good' ? 'border-l-primary bg-primary/5' :
                        analysis.summary?.overall_health === 'average' ? 'border-l-warning bg-warning/5' : 'border-l-danger bg-danger/5')}>
                        <div className="flex items-start justify-between">
                          <div>
                            <p className="text-[12px] font-medium text-text-secondary uppercase tracking-wider mb-1">Portfolio Health Rating</p>
                            <p className={clsx('text-2xl font-semibold capitalize',
                              analysis.summary?.overall_health === 'excellent' ? 'text-success' : 
                              analysis.summary?.overall_health === 'good' ? 'text-primary' : 
                              analysis.summary?.overall_health === 'average' ? 'text-warning' : 'text-danger'
                            )}>{analysis.summary?.overall_health}</p>
                            <p className="text-[13px] text-text-muted mt-2 leading-relaxed">{analysis.summary?.health_reason}</p>
                          </div>
                          <div className="text-right flex flex-col gap-2">
                            <div className="bg-background px-3 py-1.5 rounded-lg border border-border">
                              <p className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">Top Performer</p>
                              <p className="font-mono font-medium text-success text-[13px] mt-0.5">{analysis.summary?.best_performer}</p>
                            </div>
                            <div className="bg-background px-3 py-1.5 rounded-lg border border-border">
                              <p className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">Laggard</p>
                              <p className="font-mono font-medium text-danger text-[13px] mt-0.5">{analysis.summary?.worst_performer}</p>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Insights */}
                      {analysis.insights?.length > 0 && (
                        <div className="card">
                          <h3 className="text-[13px] font-semibold text-text-primary flex items-center gap-2 mb-4">
                            <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center">
                              <Brain size={14} className="text-primary" />
                            </div>
                            Key Discoveries
                          </h3>
                          <div className="space-y-3">
                            {analysis.insights.map((ins: string, i: number) => (
                              <div key={i} className="flex gap-3 text-[13px] text-text-secondary leading-relaxed bg-surface-hover/50 p-3 rounded-lg">
                                <span className="text-primary shrink-0 mt-0.5 font-bold">•</span>
                                <p>{ins}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="space-y-6">
                      {/* Rebalancing */}
                      {analysis.rebalancing_suggestions?.length > 0 && (
                        <div className="card">
                          <h3 className="text-[13px] font-semibold text-text-primary flex items-center gap-2 mb-4">
                            <div className="w-6 h-6 rounded-md bg-warning/10 flex items-center justify-center">
                              <Shield size={14} className="text-warning" />
                            </div>
                            Actionable Steps
                          </h3>
                          <div className="space-y-3">
                            {analysis.rebalancing_suggestions.map((s: any, i: number) => (
                              <div key={i} className="flex items-start gap-3 p-3 bg-background border border-border rounded-lg hover:border-border-bright transition-colors">
                                <span className={clsx('text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider shrink-0 w-16 text-center',
                                  s.action === 'buy'    ? 'text-success bg-success/10 border border-success/20' :
                                  s.action === 'sell'   ? 'text-danger bg-danger/10 border border-danger/20' :
                                  s.action === 'reduce' ? 'text-warning bg-warning/10 border border-warning/20' :
                                  'text-text-muted border-border bg-surface')}>
                                  {s.action}
                                </span>
                                <div className="flex-1">
                                  <span className="font-mono text-[14px] font-semibold text-text-primary">{s.symbol}</span>
                                  <p className="text-[12px] text-text-muted mt-1 leading-relaxed">{s.reason}</p>
                                </div>
                                <span className={clsx('text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider shrink-0',
                                  s.priority === 'high' ? 'text-danger bg-danger/10' :
                                  s.priority === 'medium' ? 'text-warning bg-warning/10' : 'text-text-muted bg-surface')}>
                                  {s.priority} PRIORITY
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Sector analysis */}
                      {analysis.sector_analysis && (
                        <div className="card">
                          <h3 className="text-[13px] font-semibold text-text-primary mb-4">
                            Sector Distribution
                          </h3>
                          <div className="space-y-3.5">
                            {Object.entries(analysis.sector_analysis).map(([sector, data]: any) => (
                              <div key={sector}>
                                <div className="flex items-center justify-between mb-1.5">
                                  <p className="text-[13px] font-medium text-text-secondary">{sector}</p>
                                  <div className="flex items-center gap-3">
                                    <p className={clsx('text-[12px] font-mono font-medium', data.avg_return_pct >= 0 ? 'text-success' : 'text-danger')}>
                                      {data.avg_return_pct >= 0 ? '+' : ''}{data.avg_return_pct?.toFixed(1)}% rtn
                                    </p>
                                    <p className="text-[13px] font-mono font-semibold text-text-primary w-12 text-right">
                                      {data.allocation_pct?.toFixed(0)}%
                                    </p>
                                  </div>
                                </div>
                                <div className="h-1.5 bg-background rounded-full overflow-hidden border border-border/50">
                                  <div className="h-full bg-primary rounded-full transition-all duration-1000"
                                    style={{ width: `${Math.min(data.allocation_pct, 100)}%` }} />
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Alerts tab */}
            {tab === 'alerts' && (
              <div className="max-w-4xl mx-auto space-y-3">
                {alerts.length === 0 ? (
                  <div className="card text-center py-20 border-dashed border-2 border-border bg-surface/30">
                    <div className="w-16 h-16 rounded-full bg-surface-hover flex items-center justify-center mx-auto mb-4">
                      <BellOff size={32} className="text-text-muted" />
                    </div>
                    <h3 className="text-lg font-semibold text-text-primary mb-2">No Active Alerts</h3>
                    <p className="text-text-secondary text-[14px] mb-6">You're all caught up! Run a check to sync the latest signals.</p>
                    <button onClick={() => runAlertCheck(activeBroker)}
                      className="btn-primary mx-auto flex items-center gap-2 h-10">
                      <Bell size={14} /> Scan for Alerts
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="flex justify-end mb-4">
                       <button onClick={() => runAlertCheck(activeBroker)} className="btn-ghost text-[12px] flex items-center gap-1.5 h-8">
                         <RefreshCw size={12} /> Sync Alerts
                       </button>
                    </div>
                    {alerts.map(alert => (
                      <div key={alert.id}
                        className={clsx('card p-4 flex items-start justify-between gap-4 transition-all duration-300',
                          !alert.is_read ? 'border-primary/30 bg-primary/5 shadow-sm' : 'opacity-70 hover:opacity-100'
                        )}>
                        <div className="flex items-start gap-4">
                          <div className={clsx('w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm border',
                            alert.alert_type === 'circuit_upper' || alert.alert_type === 'circuit_lower'
                              ? 'bg-danger/10 text-danger border-danger/20' :
                            alert.alert_type === 'pnl_above' ? 'bg-success/10 text-success border-success/20' : 'bg-warning/10 text-warning border-warning/20'
                          )}>
                            <AlertTriangle size={18} />
                          </div>
                          <div>
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className="font-mono text-[14px] font-semibold text-text-primary">
                                {alert.symbol}
                              </span>
                              <span className="text-[10px] font-bold uppercase tracking-wider text-text-secondary bg-background border border-border px-1.5 py-0.5 rounded">
                                {alert.alert_type.replace('_', ' ')}
                              </span>
                              <span className="text-[10px] font-bold uppercase tracking-wider text-text-muted bg-surface-hover px-1.5 py-0.5 rounded">
                                {alert.broker}
                              </span>
                            </div>
                            <p className="text-[13px] text-text-secondary leading-relaxed">{alert.message}</p>
                            <p className="text-[11px] text-text-muted mt-2 font-medium">
                              {alert.triggered_at ? format(new Date(alert.triggered_at), 'MMM d, yyyy • HH:mm') : ''}
                            </p>
                          </div>
                        </div>
                        {!alert.is_read && (
                          <button onClick={() => markRead(activeBroker, alert.id)}
                            className="btn-ghost text-[11px] h-8 shrink-0 px-3 border-border">
                            Mark Read
                          </button>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}

            {/* Orders tab */}
            {tab === 'orders' && (
              <div className="card p-0 overflow-hidden max-w-5xl mx-auto flex flex-col max-h-[700px]">
                <div className="px-5 py-4 border-b border-border bg-surface/50 flex items-center justify-between shrink-0">
                  <h2 className="text-[14px] font-semibold text-text-primary flex items-center gap-2">
                    <Activity size={16} className="text-primary" /> Today's Activity
                  </h2>
                  <span className="badge-muted">{orders.length} Orders</span>
                </div>
                <div className="overflow-y-auto custom-scrollbar flex-1">
                  {orders.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 text-text-muted">
                      <BarChart2 size={32} className="mb-3 opacity-20" />
                      <p className="text-[14px] text-text-secondary">No orders found for today.</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-border">
                      {orders.map((o: any) => (
                        <div key={o.order_id} className="px-5 py-4 hover:bg-surface-hover/50 transition-colors">
                          <div className="flex items-center justify-between gap-4">
                            <div className="flex items-center gap-4">
                              <div className={clsx('w-10 h-10 rounded-full flex items-center justify-center shrink-0 border',
                                o.transaction_type === 'BUY' ? 'bg-success/10 text-success border-success/20' : 'bg-danger/10 text-danger border-danger/20')}>
                                {o.transaction_type === 'BUY' ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
                              </div>
                              <div>
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="font-mono text-[15px] font-semibold text-text-primary">
                                    {o.tradingsymbol}
                                  </span>
                                  <span className={clsx('text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider',
                                    o.transaction_type === 'BUY' ? 'text-success bg-success/10' : 'text-danger bg-danger/10')}>
                                    {o.transaction_type}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2 text-[12px] text-text-secondary font-medium">
                                  <span>{o.filled_quantity} / {o.quantity} Qty</span>
                                  <span className="w-1 h-1 rounded-full bg-border" />
                                  <span>{o.product}</span>
                                  <span className="w-1 h-1 rounded-full bg-border" />
                                  <span>{o.order_type}</span>
                                  {o.average_price > 0 && (
                                    <>
                                      <span className="w-1 h-1 rounded-full bg-border" />
                                      <span className="font-mono">Avg: ₹{o.average_price.toFixed(2)}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>
                            <span className={clsx('text-[11px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider shrink-0 border',
                              o.status === 'COMPLETE' ? 'text-success bg-success/10 border-success/20' :
                              o.status === 'OPEN'     ? 'text-warning bg-warning/10 border-warning/20' :
                              o.status === 'CANCELLED'? 'text-text-muted bg-background border-border' :
                              'text-danger bg-danger/10 border-danger/20')}>
                              {o.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!activeBroker && connected.length === 0 && (
        <div className="card text-center py-24 border-dashed border-2 border-border bg-surface/30 mt-8">
          <div className="w-20 h-20 rounded-full bg-surface-hover flex items-center justify-center mx-auto mb-6">
            <IndianRupee size={36} className="text-text-muted" />
          </div>
          <h2 className="text-xl font-semibold text-text-primary mb-3">Connect Your Broker</h2>
          <p className="text-text-secondary text-[14px] max-w-md mx-auto leading-relaxed mb-8">
            Link your Zerodha or Upstox account to unlock live portfolio analytics, automated trading capabilities, and AI-powered market alerts.
          </p>
          <div className="flex justify-center gap-4">
            {BROKERS.map(b => {
              const backendUrl = import.meta.env.VITE_API_URL?.replace(/\/api$/, '') || 'http://localhost:8000';
              return (
                <a key={b.key} href={`${backendUrl}/api/india/${b.key}/login`}
                  className="btn-primary h-11 px-6 flex items-center gap-2 shadow-sm">
                  <Link size={16} /> Connect {b.label}
                </a>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
