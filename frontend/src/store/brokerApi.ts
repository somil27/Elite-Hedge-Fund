// Broker-specific API calls (orders, positions, account, clock)
import api from './api'

export const getBrokerAccount  = () => api.get('/broker/account').then(r => r.data)
export const getMarketClock    = () => api.get('/broker/clock').then(r => r.data)
export const getBrokerPortfolio = () => api.get('/broker/portfolio').then(r => r.data)

// Positions
export const listPositions     = () => api.get('/broker/positions').then(r => r.data)
export const getPositionSymbol = (sym: string) => api.get(`/broker/positions/${sym}`).then(r => r.data)
export const closePosition     = (sym: string, qty?: number) =>
  api.delete(`/broker/positions/${sym}`, { params: qty ? { qty } : {} }).then(r => r.data)
export const closeAllPositions = () => api.delete('/broker/positions').then(r => r.data)

// Orders
export const listOrders  = (status = 'open') =>
  api.get('/broker/orders', { params: { status } }).then(r => r.data)
export const getOrder    = (id: string)  => api.get(`/broker/orders/${id}`).then(r => r.data)
export const cancelOrder = (id: string)  => api.delete(`/broker/orders/${id}`).then(r => r.data)
export const cancelAllOrders = ()        => api.delete('/broker/orders').then(r => r.data)

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
}) => api.post('/broker/orders', order).then(r => r.data)
