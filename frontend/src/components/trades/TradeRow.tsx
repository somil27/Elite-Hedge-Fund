import { TrendingUp, TrendingDown } from 'lucide-react'
import { format } from 'date-fns'
import clsx from 'clsx'

interface TradeRowProps {
  trade: {
    id: string
    symbol: string
    direction: string
    entry_price: number
    exit_price?: number
    qty: number
    pnl_realized?: number
    pnl_pct?: number
    human_decision?: string
    opened_at: string
    closed_at?: string
  }
}

export default function TradeRow({ trade }: TradeRowProps) {
  const isOpen = trade.exit_price == null
  const pnl = trade.pnl_realized ?? 0
  const pnlPct = trade.pnl_pct ?? 0

  return (
    <tr className="border-b border-border/40 hover:bg-surface-2 transition-colors">
      {/* Symbol + direction */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <div className={clsx(
            'w-6 h-6 rounded flex items-center justify-center',
            trade.direction === 'long' ? 'bg-accent/10' : 'bg-danger/10'
          )}>
            {trade.direction === 'long'
              ? <TrendingUp size={11} className="text-accent" />
              : <TrendingDown size={11} className="text-danger" />}
          </div>
          <span className="font-mono text-sm font-medium text-text-primary">
            {trade.symbol}
          </span>
        </div>
      </td>

      {/* Prices */}
      <td className="px-4 py-3 font-mono text-xs text-text-secondary">
        ${trade.entry_price?.toFixed(2)}
      </td>
      <td className="px-4 py-3 font-mono text-xs text-text-secondary">
        {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : (
          <span className="text-text-muted">Open</span>
        )}
      </td>
      <td className="px-4 py-3 font-mono text-xs text-text-secondary">
        {trade.qty?.toFixed(4)}
      </td>

      {/* P&L */}
      <td className="px-4 py-3">
        {isOpen ? (
          <span className="text-xs text-text-muted">—</span>
        ) : (
          <div>
            <p className={clsx('font-mono text-xs font-medium',
              pnl >= 0 ? 'text-accent' : 'text-danger'
            )}>
              {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
            </p>
            <p className={clsx('font-mono text-xs',
              pnlPct >= 0 ? 'text-accent/70' : 'text-danger/70'
            )}>
              {pnlPct >= 0 ? '+' : ''}{(pnlPct * 100).toFixed(2)}%
            </p>
          </div>
        )}
      </td>

      {/* Human decision */}
      <td className="px-4 py-3">
        {trade.human_decision ? (
          <span className={clsx(
            'text-xs px-1.5 py-0.5 rounded border font-medium',
            trade.human_decision === 'approved' || trade.human_decision === 'resized'
              ? 'text-accent border-accent/20 bg-accent/5'
              : 'text-danger border-danger/20 bg-danger/5'
          )}>
            {trade.human_decision}
          </span>
        ) : (
          <span className="text-xs text-text-muted">auto</span>
        )}
      </td>

      {/* Time */}
      <td className="px-4 py-3 text-xs text-text-muted">
        {trade.opened_at
          ? format(new Date(trade.opened_at), 'MMM d, HH:mm')
          : '—'}
      </td>
    </tr>
  )
}
