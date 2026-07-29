import clsx from 'clsx'

interface StatusDotProps {
  status: string
  showLabel?: boolean
}

const CONFIG: Record<string, { color: string; label: string; pulse?: boolean }> = {
  running:        { color: 'bg-gold',        label: 'Running',        pulse: true },
  awaiting_human: { color: 'bg-gold',        label: 'Needs Review',   pulse: true },
  executed:       { color: 'bg-accent',      label: 'Executed' },
  approved:       { color: 'bg-accent',      label: 'Approved' },
  rejected:       { color: 'bg-danger',      label: 'Rejected' },
  failed:         { color: 'bg-text-muted',  label: 'Failed' },
  pending:        { color: 'bg-gold',        label: 'Pending',        pulse: true },
  filled:         { color: 'bg-accent',      label: 'Filled' },
  partial:        { color: 'bg-gold',        label: 'Partial' },
}

export default function StatusDot({ status, showLabel = true }: StatusDotProps) {
  const cfg = CONFIG[status] ?? { color: 'bg-text-muted', label: status }
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={clsx(
        'w-1.5 h-1.5 rounded-full',
        cfg.color,
        cfg.pulse && 'animate-pulse',
      )} />
      {showLabel && (
        <span className="text-xs text-text-secondary">{cfg.label}</span>
      )}
    </span>
  )
}
