import clsx from 'clsx'

interface SignalBadgeProps {
  label: string
  value?: number | string
  type?: 'score' | 'rating' | 'regime' | 'direction'
  size?: 'sm' | 'md'
}

function scoreColor(v: number) {
  if (v >= 0.7) return 'text-accent border-accent/30 bg-accent/8'
  if (v >= 0.4) return 'text-gold border-gold/30 bg-gold/8'
  if (v >= 0) return 'text-text-secondary border-border bg-surface-3'
  if (v >= -0.4) return 'text-gold border-gold/30 bg-gold/8'
  return 'text-danger border-danger/30 bg-danger/8'
}

function ratingColor(r: string) {
  if (['strong_buy', 'buy'].includes(r)) return 'text-accent border-accent/30 bg-accent/8'
  if (r === 'hold') return 'text-gold border-gold/30 bg-gold/8'
  return 'text-danger border-danger/30 bg-danger/8'
}

function regimeColor(r: string) {
  if (r === 'risk_on') return 'text-accent border-accent/30 bg-accent/8'
  if (r === 'crisis') return 'text-danger border-danger/30 bg-danger/8'
  if (r === 'risk_off') return 'text-gold border-gold/30 bg-gold/8'
  return 'text-text-secondary border-border bg-surface-3'
}

export default function SignalBadge({ label, value, type = 'score', size = 'sm' }: SignalBadgeProps) {
  let colorClass = 'text-text-secondary border-border bg-surface-3'
  let displayVal = value !== undefined ? String(value) : ''

  if (type === 'score' && typeof value === 'number') {
    colorClass = scoreColor(value)
    displayVal = value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)
  } else if (type === 'rating' && typeof value === 'string') {
    colorClass = ratingColor(value)
    displayVal = value.replace('_', ' ')
  } else if (type === 'regime' && typeof value === 'string') {
    colorClass = regimeColor(value)
    displayVal = value.replace('_', '-')
  } else if (type === 'direction') {
    colorClass = value === 'long'
      ? 'text-accent border-accent/30 bg-accent/8'
      : 'text-danger border-danger/30 bg-danger/8'
  }

  const sizeClass = size === 'sm'
    ? 'text-xs px-1.5 py-0.5'
    : 'text-sm px-2 py-1'

  return (
    <span className={clsx(
      'inline-flex items-center gap-1 rounded-full border font-mono font-medium',
      sizeClass, colorClass,
    )}>
      <span className="text-text-muted font-sans font-normal">{label}</span>
      {displayVal && <span>{displayVal}</span>}
    </span>
  )
}
