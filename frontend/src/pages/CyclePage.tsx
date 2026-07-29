import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getCycle, getPendingReview, submitDecision } from '../store/api'
import { CheckCircle, XCircle, Clock, AlertCircle, ArrowLeft, RefreshCw, TrendingUp, TrendingDown, Shield, Cpu, Activity, Play } from 'lucide-react'
import clsx from 'clsx'

const AGENT_PIPELINE = [
  { id: 'cio',           label: 'CIO',              layer: 'Strategy',   color: 'border-purple-500/30 bg-purple-500/5 text-purple-500' },
  { id: 'research',      label: 'Research Layer',   layer: 'Research',   color: 'border-blue-500/30 bg-blue-500/5 text-blue-500' },
  { id: 'analysis',      label: 'Analysis Layer',   layer: 'Analysis',   color: 'border-teal-500/30 bg-teal-500/5 text-teal-500' },
  { id: 'risk',          label: 'Risk Manager',      layer: 'Gatekeeper', color: 'border-warning/30 bg-warning/5 text-warning' },
  { id: 'trade_desk',    label: 'Trade Desk',        layer: 'Execution',  color: 'border-primary/30 bg-primary/5 text-primary' },
  { id: 'human_gate',    label: 'Human Gate',        layer: 'Approval',   color: 'border-danger/30 bg-danger/5 text-danger' },
  { id: 'execution',     label: 'Execution Algo',   layer: 'Execution',  color: 'border-primary/30 bg-primary/5 text-primary' },
  { id: 'post_trade',    label: 'Post-Trade',        layer: 'Monitoring', color: 'border-success/30 bg-success/5 text-success' },
]

function getActiveNode(cycle: any): string {
  if (!cycle) return ''
  const s = cycle.status
  if (s === 'running' && !cycle.market_intel) return 'cio'
  if (s === 'running' && !cycle.proposals?.length) return 'research'
  if (s === 'running' && !cycle.risk_assessments?.length) return 'analysis'
  if (s === 'running' && cycle.risk_assessments?.length) return 'risk'
  if (s === 'awaiting_human') return 'human_gate'
  if (s === 'executed') return 'post_trade'
  return ''
}

export default function CyclePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [cycle, setCycle] = useState<any>(null)
  const [review, setReview] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [deciding, setDeciding] = useState(false)
  const [overrideWeight, setOverrideWeight] = useState('')
  const [notes, setNotes] = useState('')

  const refresh = useCallback(async () => {
    if (!id) return
    try {
      const data = await getCycle(id)
      setCycle(data)
      if (data.awaiting_human) {
        const rev = await getPendingReview(id).catch(() => null)
        setReview(rev)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [refresh])

  const handleDecide = async (decision: string) => {
    if (!id) return
    setDeciding(true)
    try {
      await submitDecision(
        id, decision,
        overrideWeight ? parseFloat(overrideWeight) : undefined,
        notes || undefined,
      )
      await refresh()
    } catch (e) {
      console.error(e)
    } finally {
      setDeciding(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-[60vh] text-text-muted">
      <RefreshCw size={24} className="animate-spin mr-3 opacity-50" /> 
      <span className="text-[14px] font-medium">Loading Cycle…</span>
    </div>
  )

  const activeNode = getActiveNode(cycle)

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border pb-6">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/')} className="w-10 h-10 rounded-xl bg-surface-hover flex items-center justify-center hover:bg-surface-3 transition-colors border border-border">
            <ArrowLeft size={18} className="text-text-secondary" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
                Cycle Execution
              </h1>
              <span className="font-mono text-text-secondary bg-surface-hover px-2 py-0.5 rounded text-[14px] border border-border">
                {id?.slice(0, 8)}…
              </span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              <span className={clsx('text-[11px] font-bold px-2 py-1 rounded uppercase tracking-wider', cycle?.mode === 'short_term' ? 'text-primary bg-primary/10 border border-primary/20' : 'text-warning bg-warning/10 border border-warning/20')}>
                {cycle?.mode === 'short_term' ? '⚡ Short Term' : '📈 Long Term'}
              </span>
              <span className="text-[11px] font-bold px-2 py-1 rounded uppercase tracking-wider bg-surface-hover text-text-secondary border border-border">
                {cycle?.auto_mode ? '🤖 Auto' : '👤 Manual'}
              </span>
            </div>
          </div>
        </div>
        <button onClick={refresh} className="btn-ghost h-10 flex items-center gap-2 px-4 border border-border bg-surface-hover shadow-sm">
          <RefreshCw size={14} /> Sync State
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left: Agent pipeline */}
        <div className="lg:col-span-4 space-y-4">
          <h2 className="text-[13px] font-semibold text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
            <Activity size={14} /> Autonomous Pipeline
          </h2>
          <div className="bg-surface/50 border border-border rounded-xl p-5">
            <div className="relative">
              {/* Vertical line connecting nodes */}
              <div className="absolute top-4 bottom-4 left-[21px] w-px bg-border/50" />
              
              <div className="space-y-4">
                {AGENT_PIPELINE.map((node) => {
                  const isActive = activeNode === node.id
                  const isDone = isDoneNode(node.id, cycle)
                  return (
                    <div key={node.id} className="relative flex items-center gap-4 group">
                      <div className={clsx(
                        'w-11 h-11 rounded-full flex items-center justify-center shrink-0 border-2 z-10 transition-all duration-300',
                        isDone ? 'border-success bg-success/10 text-success shadow-[0_0_15px_rgba(16,185,129,0.2)]' :
                        isActive ? 'border-primary bg-primary/10 text-primary shadow-glow animate-pulse-slow' :
                        'border-border bg-surface text-text-muted'
                      )}>
                        {isDone ? <CheckCircle size={18} /> :
                         isActive ? <Play size={16} className="ml-1" /> :
                         <div className="w-2 h-2 rounded-full bg-border" />}
                      </div>
                      
                      <div className={clsx(
                        'flex-1 rounded-xl border p-3.5 transition-all duration-300',
                        isActive ? 'bg-surface shadow-glow border-primary/40' : 'bg-surface/50 border-border/50 group-hover:border-border'
                      )}>
                        <p className={clsx('text-[14px] font-semibold tracking-tight',
                          isDone ? 'text-text-primary' : isActive ? 'text-primary' : 'text-text-secondary'
                        )}>{node.label}</p>
                        <p className="text-[12px] font-medium text-text-muted uppercase tracking-wider mt-1">{node.layer}</p>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Right: Details */}
        <div className="lg:col-span-8 space-y-6">
          {/* Mandate */}
          {cycle?.mandate?.theme && (
            <div className="card shadow-sm border-l-4 border-l-purple-500/50 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/5 rounded-full blur-2xl -mr-16 -mt-16" />
              <h3 className="text-[12px] text-purple-500 uppercase font-bold tracking-wider mb-3 flex items-center gap-1.5 relative z-10">
                <Cpu size={14} /> CIO Mandate
              </h3>
              <p className="text-[16px] text-text-primary font-medium leading-relaxed relative z-10">{cycle.mandate.theme}</p>
              <div className="flex flex-wrap gap-2 mt-4 relative z-10">
                {cycle.mandate.watchlist?.map((s: string) => (
                  <span key={s} className="font-mono text-[11px] font-bold px-2 py-1 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded">{s}</span>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-4 mt-6 pt-4 border-t border-border/50 relative z-10">
                <div>
                  <p className="text-[11px] text-text-muted font-semibold uppercase tracking-wider mb-1">Risk Budget</p>
                  <p className="font-mono text-[14px] text-text-primary font-medium">{cycle.mandate.risk_budget}% VaR</p>
                </div>
                <div>
                  <p className="text-[11px] text-text-muted font-semibold uppercase tracking-wider mb-1">Time Horizon</p>
                  <p className="font-mono text-[14px] text-text-primary font-medium capitalize">{cycle.mandate.time_horizon?.replace('_', ' ')}</p>
                </div>
              </div>
            </div>
          )}

          {/* Market Intel */}
          {cycle?.market_intel && (
            <div className="card shadow-sm border-l-4 border-l-blue-500/50">
              <h3 className="text-[12px] text-blue-500 uppercase font-bold tracking-wider mb-3 flex items-center gap-1.5">
                <Activity size={14} /> Market Intel
              </h3>
              <div className="flex items-center gap-3 mb-4">
                <span className={clsx('text-[11px] font-bold px-2 py-1 rounded uppercase tracking-wider border',
                  cycle.market_intel.regime === 'risk_on' ? 'text-success bg-success/10 border-success/20' :
                  cycle.market_intel.regime === 'crisis' ? 'text-danger bg-danger/10 border-danger/20' : 'text-warning bg-warning/10 border-warning/20'
                )}>
                  {cycle.market_intel.regime?.replace('_', ' ')}
                </span>
                <span className="text-[12px] font-medium text-text-secondary bg-surface-hover px-2 py-1 rounded border border-border">
                  Sentiment Score: <span className="font-mono text-text-primary">{cycle.market_intel.sentiment_score?.toFixed(2)}</span>
                </span>
              </div>
              <p className="text-[14px] text-text-secondary leading-relaxed p-4 bg-surface-hover rounded-xl border border-border/50">{cycle.market_intel.macro_summary}</p>
            </div>
          )}

          {/* Proposals */}
          {cycle?.proposals?.length > 0 && (
            <div className="card shadow-sm border-l-4 border-l-teal-500/50 p-0 overflow-hidden">
              <div className="px-5 py-4 border-b border-border bg-surface/30">
                <h3 className="text-[12px] text-teal-500 uppercase font-bold tracking-wider flex items-center gap-1.5">
                  <Activity size={14} /> Trade Proposals
                </h3>
              </div>
              <div className="divide-y divide-border">
                {cycle.proposals.map((p: any, i: number) => {
                  const risk = cycle.risk_assessments?.find((r: any) => r.symbol === p.symbol)
                  return (
                    <div key={i} className="p-5 hover:bg-surface-hover/30 transition-colors">
                      <div className="flex items-start gap-4">
                        <div className={clsx(
                          'w-10 h-10 rounded-full flex items-center justify-center shrink-0 border',
                          p.direction === 'long' ? 'bg-success/10 text-success border-success/20' : 'bg-danger/10 text-danger border-danger/20'
                        )}>
                          {p.direction === 'long'
                            ? <TrendingUp size={18} />
                            : <TrendingDown size={18} />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3 mb-2">
                            <span className="font-mono text-[16px] font-semibold tracking-tight text-text-primary">{p.symbol}</span>
                            <span className={clsx('text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded',
                              p.direction === 'long' ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
                            )}>
                              {p.direction}
                            </span>
                            <span className="font-mono text-[12px] font-medium bg-surface-hover text-text-secondary px-2 py-0.5 rounded border border-border">
                              Wt: {(p.proposed_weight * 100).toFixed(1)}%
                            </span>
                            {risk && (
                              <span className={clsx('text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider border ml-auto',
                                risk.decision === 'approved' ? 'text-success bg-success/10 border-success/20' :
                                risk.decision === 'approved_resized' ? 'text-warning bg-warning/10 border-warning/20' :
                                'text-danger bg-danger/10 border-danger/20'
                              )}>
                                {risk.decision?.replace('_', ' ')}
                              </span>
                            )}
                          </div>
                          <p className="text-[13px] text-text-secondary leading-relaxed bg-surface/50 p-3 rounded-lg border border-border/50">{p.rationale}</p>
                          <div className="mt-3 flex items-center gap-2">
                            <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">Composite Score</span>
                            <span className="font-mono text-[13px] text-text-primary font-medium bg-background px-2 py-0.5 rounded border border-border">{p.composite_score?.toFixed(2)}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Human Review Gate */}
          {cycle?.awaiting_human && review && (
            <div className="card border-primary/50 shadow-glow relative overflow-hidden">
              <div className="absolute top-0 right-0 w-48 h-48 bg-primary/10 rounded-full blur-3xl -mr-24 -mt-24 pointer-events-none" />
              <h3 className="text-[14px] font-semibold text-primary flex items-center gap-2 mb-6">
                <AlertCircle size={18} /> Human Approval Required
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                <div className="bg-surface/80 border border-border rounded-xl p-4">
                  <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-2">Trade Details</p>
                  <p className="font-mono text-[15px] font-semibold text-text-primary mb-2">
                    {review.proposal?.symbol} <span className={clsx('text-[12px] uppercase ml-1', review.proposal?.direction === 'long' ? 'text-success' : 'text-danger')}>{review.proposal?.direction}</span>
                  </p>
                  <p className="text-[13px] text-text-secondary leading-relaxed">{review.proposal?.rationale}</p>
                </div>
                <div className="bg-surface/80 border border-border rounded-xl p-4">
                  <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-2">Risk Impact</p>
                  <div className="space-y-3 mt-3">
                    <div>
                      <p className="text-[12px] text-text-secondary mb-1">Post-Trade VaR</p>
                      <p className="font-mono text-[14px] text-text-primary font-medium">
                        {review.risk?.portfolio_var_after?.toFixed(2)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-[12px] text-text-secondary mb-1">Estimated Notional</p>
                      <p className="font-mono text-[14px] text-text-primary font-medium">
                        ${review.estimated_notional?.toLocaleString('en', { maximumFractionDigits: 0 })}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-4 mb-6 bg-surface-hover/50 p-4 rounded-xl border border-border/50">
                <div>
                  <label className="text-[12px] font-medium text-text-secondary block mb-1.5">Override Target Weight (Optional)</label>
                  <input
                    type="number" min="0" max="0.1" step="0.005"
                    value={overrideWeight}
                    onChange={e => setOverrideWeight(e.target.value)}
                    placeholder="e.g. 0.02 for 2%"
                    className="input-field py-2"
                  />
                </div>
                <div>
                  <label className="text-[12px] font-medium text-text-secondary block mb-1.5">Decision Notes (Optional)</label>
                  <input
                    type="text"
                    value={notes}
                    onChange={e => setNotes(e.target.value)}
                    placeholder="Reasoning for manual override…"
                    className="input-field py-2"
                  />
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <button onClick={() => handleDecide('approved')} disabled={deciding}
                  className="btn-primary flex-1 h-11 flex items-center justify-center gap-2 shadow-glow">
                  <CheckCircle size={16} /> Approve Trade
                </button>
                <button onClick={() => handleDecide('resized')} disabled={deciding || !overrideWeight}
                  className="flex-1 h-11 rounded-lg border border-warning/50 text-warning text-[14px] font-semibold
                             hover:bg-warning/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2">
                  <Shield size={16} /> Resize & Approve
                </button>
                <button onClick={() => handleDecide('rejected')} disabled={deciding}
                  className="btn-danger sm:w-32 h-11 flex items-center justify-center gap-2">
                  <XCircle size={16} /> Reject
                </button>
              </div>
            </div>
          )}

          {/* Execution report */}
          {cycle?.execution_report && (
            <div className="card border-l-4 border-l-success/50 relative overflow-hidden">
               <div className="absolute top-0 right-0 w-32 h-32 bg-success/5 rounded-full blur-2xl -mr-16 -mt-16 pointer-events-none" />
              <h3 className="text-[12px] text-success font-bold uppercase tracking-wider mb-4 flex items-center gap-1.5 relative z-10">
                <CheckCircle size={14} /> Execution Complete
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative z-10">
                {[
                  { label: 'Avg Fill Price', value: `$${cycle.execution_report.avg_fill_price?.toFixed(2)}` },
                  { label: 'Filled Quantity', value: cycle.execution_report.qty_filled?.toFixed(2) },
                  { label: 'Slippage', value: `${cycle.execution_report.slippage_bps?.toFixed(1)} bps` },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-surface/50 p-3 rounded-lg border border-border/50">
                    <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1">{label}</p>
                    <p className="font-mono text-[15px] font-semibold text-text-primary">{value}</p>
                  </div>
                ))}
              </div>
              {cycle.compliance_flags?.length > 0 && (
                <div className="mt-4 p-3 bg-danger/10 border border-danger/20 rounded-lg relative z-10">
                  <p className="text-[12px] text-danger font-bold uppercase tracking-wider mb-2 flex items-center gap-2">
                    <AlertCircle size={14} /> Compliance Flags
                  </p>
                  <ul className="space-y-1">
                    {cycle.compliance_flags.map((f: string, i: number) => (
                      <li key={i} className="text-[13px] text-danger/90 flex items-start gap-2">
                        <span className="mt-1">•</span> {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Errors */}
          {cycle?.errors?.length > 0 && (
            <div className="card border-l-4 border-l-danger/50 bg-danger/5">
              <h3 className="text-[12px] text-danger font-bold uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <AlertCircle size={14} /> System Errors
              </h3>
              <div className="space-y-2">
                {cycle.errors.map((e: string, i: number) => (
                  <p key={i} className="text-[13px] text-danger/90 font-mono bg-danger/10 p-2 rounded border border-danger/20">{e}</p>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function isDoneNode(nodeId: string, cycle: any): boolean {
  if (!cycle) return false
  const s = cycle.status
  switch (nodeId) {
    case 'cio': return !!cycle.mandate?.theme
    case 'research': return !!cycle.market_intel
    case 'analysis': return cycle.proposals?.length > 0
    case 'risk': return cycle.risk_assessments?.length > 0
    case 'trade_desk': return !!cycle.review_request || s === 'executed'
    case 'human_gate': return s === 'executed' || (!!cycle.human_decision && !cycle.awaiting_human)
    case 'execution': return !!cycle.execution_report
    case 'post_trade': return s === 'executed'
    default: return false
  }
}
