import axios from 'axios'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api' })

// Inject JWT token into every request
api.interceptors.request.use((config) => {
  // We have to read from localStorage because Zustand persist saves it there
  const authStateStr = localStorage.getItem('alphadesk-auth');
  if (authStateStr) {
    try {
      const authState = JSON.parse(authStateStr);
      if (authState?.state?.token) {
        config.headers.Authorization = `Bearer ${authState.state.token}`;
      }
    } catch (e) {
      console.error('Failed to parse auth token', e);
    }
  }
  return config;
});

export const startCycle = (
  mode: string,
  autoMode: boolean,
  market: string = 'us',
  indianBroker: string = 'zerodha',
  userId: string = '00000000-0000-0000-0000-000000000001',
) =>
  api.post('/cycles/start', {
    mode,
    auto_mode: autoMode,
    market,
    indian_broker: indianBroker,
    user_id: userId,
  }).then(r => r.data)

export const getCycle = (id: string) =>
  api.get(`/cycles/${id}`).then(r => r.data)

export const listCycles = () =>
  api.get('/cycles').then(r => r.data)

export const getPendingReview = (cycleId: string) =>
  api.get(`/cycles/${cycleId}/review`).then(r => r.data)

export const submitDecision = (
  cycleId: string,
  decision: string,
  overrideWeight?: number,
  notes?: string,
) =>
  api.post(`/cycles/${cycleId}/decide`, {
    decision, override_weight: overrideWeight, notes,
  }).then(r => r.data)

export const getPortfolio = () =>
  api.get('/portfolio').then(r => r.data)

export const listTrades = () =>
  api.get('/trades').then(r => r.data)

export default api
