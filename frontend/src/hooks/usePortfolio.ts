import { useQuery } from '@tanstack/react-query'
import { getPortfolio, listTrades } from '../store/api'

export function usePortfolio(pollInterval = 15000) {
  const { data: portfolio, isLoading: loadingPortfolio } = useQuery({
    queryKey: ['portfolio'],
    queryFn: getPortfolio,
    refetchInterval: pollInterval
  })

  const { data: trades = [], isLoading: loadingTrades } = useQuery({
    queryKey: ['trades'],
    queryFn: listTrades,
    refetchInterval: pollInterval
  })

  const loading = loadingPortfolio || loadingTrades

  const closedTrades = trades.filter((t: any) => t.pnl_realized != null)
  const totalPnl = closedTrades.reduce((s: number, t: any) => s + (t.pnl_realized || 0), 0)
  const winRate = closedTrades.length > 0
    ? closedTrades.filter((t: any) => (t.pnl_realized || 0) > 0).length / closedTrades.length
    : 0

  return { portfolio, trades, closedTrades, totalPnl, winRate, loading }
}
