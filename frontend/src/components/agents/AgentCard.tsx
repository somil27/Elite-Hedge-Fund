import clsx from 'clsx'
import { CheckCircle, Clock, XCircle, Minus } from 'lucide-react'

interface AgentCardProps {
  name: string
  layer: string
  status: 'idle' | 'running' | 'done' | 'error' | 'skipped'
  output?: string
  detail?: string
  className?: string
}

const STATUS_ICON = {
  idle:    <Minus size={11} className="text-text-muted" />,
  running: <Clock size={11} className="text-gold animate-pulse" />,
  done:    <CheckCircle size={11} className="text-accent" />,
  error:   <XCircle size={11} className="text-danger" />,
  skipped: <Minus size={11} className="text-text-muted" />,
}

const STATUS_BORDER: Record<string, string> = {
  idle:    'border-border',
  running: 'border-gold/50',
  done:    'border-accent/30',
  error:   'border-danger/30',
  skipped: 'border-border/40',
}

export default function AgentCard({
  name, layer, status, output, detail, className
}: AgentCardProps) {
  return (
    <div className={clsx(
      'rounded-lg border px-3 py-2 transition-all',
      STATUS_BORDER[status],
      status === 'running' && 'bg-gold/5',
      status === 'done'    && 'bg-accent/5',
      status === 'error'   && 'bg-danger/5',
      status === 'idle'    && 'bg-surface-2',
      className,
    )}>
      <div className="flex items-center gap-2">
        {STATUS_ICON[status]}
        <span className="text-xs font-medium text-text-primary">{name}</span>
        <span className="text-xs text-text-muted ml-auto">{layer}</span>
      </div>
      {output && (
        <p className="text-xs text-text-secondary mt-1 truncate">{output}</p>
      )}
      {detail && (
        <p className="text-xs text-text-muted mt-0.5 font-mono">{detail}</p>
      )}
    </div>
  )
}
