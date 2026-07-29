import { useState } from 'react'
import { AlertCircle, CheckCircle, XCircle, Shield, Clock } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'
import SignalBadge from '../common/SignalBadge'

interface ReviewData {
  review_id: string
  cycle_id: string
  proposal: any
  technical: any
  risk: any
  estimated_notional: number
  expires_at: string
  status: string
}

interface HumanGatePanelProps {
  review: ReviewData
  onDecide: (decision: string, overrideWeight?: number, notes?: string) => Promise<void>
}

export default function HumanGatePanel({ review, onDecide }: HumanGatePanelProps) {
  const [deciding, setDeciding] = useState(false)
  const [overrideWeight, setOverrideWeight] = useState('')
  const [notes, setNotes] = useState('')
  const [activeTab, setActiveTab] = useState<'proposal' | 'technical' | 'risk'>('proposal')

  const expiresAt = new Date(review.expires_at)
  const isExpired = expiresAt < new Date()

  const handleDecide = async (decision: string) => {
    setDeciding(true)
    try {
      await onDecide(
        decision,
        overrideWeight ? parseFloat(overrideWeight) : undefined,
        notes || undefined,
      )
    } finally {
      setDeciding(false)
    }
  }

  return (
    <div className="card border-gold/40 glow-gold space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle size={16} className="text-gold" />
          <h3 className="text-sm font-semibold text-gold">Human Approval Required</h3>
        </div>
        <div className="flex items-center gap-1 text-xs text-text-muted">
          <Clock size={11} />
          {isExpired
            ? <span className="text-danger">Expired</span>
            : <span>Expires {formatDistanceToNow(expiresAt, { addSuffix: true })}</span>}
        </div>
      </div>

      {/* Trade summary */}
      <div className="grid grid-cols-3 gap-2 p-3 bg-surface-2 rounded-lg">
        <div>
          <p className="text-xs text-text-muted">Symbol</p>
          <p className="font-mono font-semibold text-text-primary mt-0.5">
            {review.proposal?.symbol}
          </p>
        </div>
        <div>
          <p className="text-xs text-text-muted">Direction</p>
          <SignalBadge
            label="" value={review.proposal?.direction}
            type="direction" size="sm"
          />
        </div>
        <div>
          <p className="text-xs text-text-muted">Notional</p>
          <p className="font-mono text-sm text-text-primary mt-0.5">
            ${review.estimated_notional?.toLocaleString('en', { maximumFractionDigits: 0 })}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border pb-2">
        {(['proposal', 'technical', 'risk'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={clsx(
              'text-xs px-3 py-1 rounded-md transition-colors capitalize',
              activeTab === tab
                ? 'bg-surface-3 text-text-primary'
                : 'text-text-muted hover:text-text-secondary'
            )}>
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="min-h-24 text-xs space-y-2">
        {activeTab === 'proposal' && (
          <>
            <p className="text-text-secondary leading-relaxed">
              {review.proposal?.rationale}
            </p>
            <div className="flex flex-wrap gap-2 mt-2">
              <SignalBadge label="score"
                value={review.proposal?.composite_score} type="score" />
              <SignalBadge label="weight"
                value={`${((review.proposal?.proposed_weight || 0) * 100).toFixed(1)}%`} />
            </div>
          </>
        )}
        {activeTab === 'technical' && (
          <div className="space-y-1.5">
            <div className="flex justify-between">
              <span className="text-text-muted">Setup quality</span>
              <span className={clsx('font-medium',
                review.technical?.setup_quality === 'excellent' ? 'text-accent' :
                review.technical?.setup_quality === 'good' ? 'text-gold' : 'text-danger'
              )}>{review.technical?.setup_quality}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Pattern</span>
              <span className="text-text-secondary">{review.technical?.pattern}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Entry zone</span>
              <span className="font-mono text-text-secondary">
                ${review.technical?.entry_zone_low}–${review.technical?.entry_zone_high}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Stop loss</span>
              <span className="font-mono text-danger">${review.technical?.stop_loss}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Take profit</span>
              <span className="font-mono text-accent">${review.technical?.take_profit_1}</span>
            </div>
          </div>
        )}
        {activeTab === 'risk' && (
          <div className="space-y-1.5">
            <div className="flex justify-between">
              <span className="text-text-muted">Risk decision</span>
              <span className={clsx('font-medium',
                review.risk?.decision === 'approved' ? 'text-accent' :
                review.risk?.decision === 'approved_resized' ? 'text-gold' : 'text-danger'
              )}>{review.risk?.decision?.replace('_', ' ')}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Approved weight</span>
              <span className="font-mono text-text-secondary">
                {((review.risk?.approved_weight || 0) * 100).toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">VaR after trade</span>
              <span className="font-mono text-text-secondary">
                {review.risk?.portfolio_var_after?.toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Drawdown headroom</span>
              <span className="font-mono text-text-secondary">
                {review.risk?.drawdown_headroom?.toFixed(2)}%
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Override fields */}
      <div className="space-y-2 pt-2 border-t border-border">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-text-muted block mb-1">
              Override weight (optional)
            </label>
            <input
              type="number" min="0.001" max="0.1" step="0.005"
              value={overrideWeight}
              onChange={e => setOverrideWeight(e.target.value)}
              placeholder="e.g. 0.02"
              className="w-full bg-surface-3 border border-border rounded-lg px-2.5 py-1.5
                         text-xs text-text-primary placeholder:text-text-muted
                         focus:outline-none focus:border-border-bright"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">Notes (optional)</label>
            <input
              type="text" value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Reason…"
              className="w-full bg-surface-3 border border-border rounded-lg px-2.5 py-1.5
                         text-xs text-text-primary placeholder:text-text-muted
                         focus:outline-none focus:border-border-bright"
            />
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => handleDecide('approved')}
          disabled={deciding || isExpired}
          className="btn-primary flex-1 flex items-center justify-center gap-1.5 text-xs"
        >
          <CheckCircle size={13} />
          Approve
        </button>
        <button
          onClick={() => handleDecide('resized')}
          disabled={deciding || isExpired || !overrideWeight}
          className="flex-1 py-2 rounded-lg border border-gold/40 text-gold text-xs font-semibold
                     hover:bg-gold/5 transition-colors disabled:opacity-40
                     flex items-center justify-center gap-1.5"
        >
          <Shield size={13} />
          Resize
        </button>
        <button
          onClick={() => handleDecide('rejected')}
          disabled={deciding || isExpired}
          className="btn-danger flex items-center justify-center gap-1.5 text-xs px-3"
        >
          <XCircle size={13} />
          Reject
        </button>
      </div>
    </div>
  )
}
