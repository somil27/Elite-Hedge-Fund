import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import StatusDot from '../common/StatusDot'
import clsx from 'clsx'

interface CycleCardProps {
  cycle: {
    cycle_id: string
    mode: string
    status: string
    auto_mode: boolean
    started_at?: string
    completed_at?: string
  }
}

export default function CycleCard({ cycle }: CycleCardProps) {
  const navigate = useNavigate()

  return (
    <button
      onClick={() => navigate(`/cycle/${cycle.cycle_id}`)}
      className="w-full flex items-center gap-3 p-3 rounded-lg bg-surface-2
                 hover:bg-surface-3 border border-transparent hover:border-border
                 transition-all text-left group"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono text-xs text-text-muted">
            {cycle.cycle_id.slice(0, 8)}…
          </span>
          <span className={clsx(
            'text-xs px-1.5 py-0.5 rounded-full border font-medium',
            cycle.mode === 'short_term'
              ? 'text-accent border-accent/20 bg-accent/5'
              : 'text-gold border-gold/20 bg-gold/5'
          )}>
            {cycle.mode === 'short_term' ? '⚡ ST' : '📈 LT'}
          </span>
          {cycle.auto_mode && (
            <span className="text-xs text-text-muted">🤖</span>
          )}
        </div>
        <StatusDot status={cycle.status} />
      </div>

      <div className="text-right shrink-0">
        <p className="text-xs text-text-muted">
          {cycle.started_at
            ? formatDistanceToNow(new Date(cycle.started_at), { addSuffix: true })
            : '—'}
        </p>
        {cycle.completed_at && (
          <p className="text-xs text-text-muted/60 mt-0.5">
            {Math.round(
              (new Date(cycle.completed_at).getTime() -
                new Date(cycle.started_at!).getTime()) / 1000
            )}s
          </p>
        )}
      </div>

      <ChevronRight
        size={13}
        className="text-text-muted group-hover:text-text-secondary transition-colors"
      />
    </button>
  )
}
