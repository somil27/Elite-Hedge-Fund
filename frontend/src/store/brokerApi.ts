// Broker-specific API calls (orders, positions, account, clock)
import axios from 'axios'

const api = axios.create({ baseURL: (import.meta.env.VITE_API_URL || '/api') + '/broker' })

export const getBrokerAccount  = () => api.get('/account').then(r => r.data)
export const getMarketClock    = () => api.get('/clock').then(r => r.data)
export const getBrokerPortfolio = () => api.get('/portfolio').then(r => r.data)

// Positions
export const listPositions     = () => api.get('/positions').then(r => r.data)
export const getPositionSymbol = (sym: string) => api.get(`/positions/${sym}`).then(r => r.data)
export const closePosition     = (sym: string, qty?: number) =>
  api.delete(`/positions/${sym}`, { params: qty ? { qty } : {} }).then(r => r.data)
export const closeAllPositions = () => api.delete('/positions').then(r => r.data)

// Orders
export const listOrders  = (status = 'open') =>
  api.get('/orders', { params: { status } }).then(r => r.data)
export const getOrder    = (id: string)  => api.get(`/orders/${id}`).then(r => r.data)
export const cancelOrder = (id: string)  => api.delete(`/orders/${id}`).then(r => r.data)
export const cancelAllOrders = ()        => api.delete('/orders').then(r => r.data)

export const placeManualOrder = (order: {
  symbol: string
  side: string
  qty: number
  order_type?: string
  limit_price?: number
  stop_price?: number
  time_in_force?: string
  extended_hours?: boolean
  note?: string
}) => api.post('/orders', order).then(r => r.data)
