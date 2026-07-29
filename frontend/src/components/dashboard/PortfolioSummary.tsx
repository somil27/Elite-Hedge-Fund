import { DollarSign, TrendingDown, Briefcase, Zap } from 'lucide-react'
import clsx from 'clsx'

interface PortfolioSummaryProps {
  portfolio: {
    total_value: number
    cash: number
    buying_power: number
    current_drawdown: number
    positions: any[]
  }
}

export default function PortfolioSummary({ portfolio }: PortfolioSummaryProps) {
  const positionValue = portfolio.total_value - portfolio.cash
  const allocationPct = portfolio.total_value > 0
    ? (positionValue / portfolio.total_value) * 100
    : 0

  const metrics = [
    {
      icon: DollarSign,
      label: 'Portfolio Value',
      value: `$${portfolio.total_value.toLocaleString('en', { minimumFractionDigits: 2 })}`,
      accent: true,
    },
    {
      icon: Zap,
      label: 'Buying Power',
      value: `$${portfolio.cash.toLocaleString('en', { minimumFractionDigits: 2 })}`,
    },
    {
      icon: Briefcase,
      label: 'Invested',
      value: `${allocationPct.toFixed(1)}%`,
    },
    {
      icon: TrendingDown,
      label: 'Drawdown',
      value: `${(portfolio.current_drawdown * 100).toFixed(2)}%`,
      danger: portfolio.current_drawdown > 0.05,
    },
  ]

  return (
    <div className="grid grid-cols-4 gap-3">
      {metrics.map(({ icon: Icon, label, value, accent, danger }) => (
        <div key={label} className={clsx(
          'card flex items-start gap-3',
          accent && 'border-accent/20',
          danger && 'border-danger/20',
        )}>
          <div className={clsx(
            'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
            accent ? 'bg-accent/10' : danger ? 'bg-danger/10' : 'bg-surface-3'
          )}>
            <Icon size={15} className={
              accent ? 'text-accent' : danger ? 'text-danger' : 'text-text-muted'
            } />
          </div>
          <div>
            <p className="text-xs text-text-muted">{label}</p>
            <p className={clsx(
              'font-mono text-base font-semibold mt-0.5',
              accent ? 'text-accent' : danger ? 'text-danger' : 'text-text-primary'
            )}>{value}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
