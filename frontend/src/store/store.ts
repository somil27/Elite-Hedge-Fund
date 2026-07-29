import { create } from 'zustand'

interface Cycle {
  cycle_id: string
  mode: string
  status: string
  auto_mode: boolean
  started_at?: string
  completed_at?: string
  mandate?: any
  market_intel?: any
  proposals?: any[]
  risk_assessments?: any[]
  execution_report?: any
  awaiting_human?: boolean
  review_request?: any
  compliance_flags?: string[]
  errors?: string[]
}

interface Trade {
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
}

interface Portfolio {
  total_value: number
  cash: number
  buying_power: number
  positions: any[]
  current_drawdown: number
}

interface Store {
  cycles: Cycle[]
  activeCycle: Cycle | null
  trades: Trade[]
  portfolio: Portfolio | null
  wsConnected: boolean
  notifications: string[]

  setCycles: (c: Cycle[]) => void
  setActiveCycle: (c: Cycle | null) => void
  updateCycle: (id: string, patch: Partial<Cycle>) => void
  setTrades: (t: Trade[]) => void
  setPortfolio: (p: Portfolio) => void
  setWsConnected: (v: boolean) => void
  addNotification: (msg: string) => void
  clearNotifications: () => void
}

export const useStore = create<Store>((set) => ({
  cycles: [],
  activeCycle: null,
  trades: [],
  portfolio: null,
  wsConnected: false,
  notifications: [],

  setCycles: (cycles) => set({ cycles }),
  setActiveCycle: (activeCycle) => set({ activeCycle }),
  updateCycle: (id, patch) =>
    set((s) => ({
      cycles: s.cycles.map((c) => c.cycle_id === id ? { ...c, ...patch } : c),
      activeCycle: s.activeCycle?.cycle_id === id
        ? { ...s.activeCycle, ...patch } : s.activeCycle,
    })),
  setTrades: (trades) => set({ trades }),
  setPortfolio: (portfolio) => set({ portfolio }),
  setWsConnected: (wsConnected) => set({ wsConnected }),
  addNotification: (msg) =>
    set((s) => ({ notifications: [msg, ...s.notifications].slice(0, 20) })),
  clearNotifications: () => set({ notifications: [] }),
}))
