import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})
import { useWebSocket } from './hooks/useWebSocket'
import { useStore } from './store/store'
import Dashboard from './pages/Dashboard'
import CyclePage from './pages/CyclePage'
import TradesPage from './pages/TradesPage'
import PortfolioPage from './pages/PortfolioPage'
import BrokerPage from './pages/BrokerPage'
import IndiaPage from './pages/IndiaPage'
import Phase12Page from './pages/Phase12Page'
import { Activity, BarChart3, BookOpen, Layers, Wifi, WifiOff, Terminal, IndianRupee, Brain } from 'lucide-react'
import clsx from 'clsx'

import { useAuthStore } from './store/authStore'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import { LogOut, User as UserIcon } from 'lucide-react'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <LoginPage />
  return <>{children}</>
}

function Layout({ children }: { children: React.ReactNode }) {
  const { wsConnected, notifications } = useStore()
  const { user, logout } = useAuthStore()
  const [provider, setProvider] = useState<string | null>(null)

  useEffect(() => {
    const backendUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
    const providerUrl = backendUrl.replace(/\/api$/, '') + '/api/provider';
    fetch(providerUrl).then(r => r.json())
      .then(d => setProvider(d.provider))
      .catch(() => { })
  }, [])

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Top bar */}
      <header className="h-14 border-b border-border/60 bg-background/80 backdrop-blur-md flex items-center px-6 gap-8 sticky top-0 z-50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-[8px] bg-primary-glow border border-primary/20 flex items-center justify-center shadow-glow">
            <Activity size={16} className="text-primary" />
          </div>
          <span className="font-sans font-semibold text-text-primary tracking-tight text-sm">AlphaDesk</span>
        </div>

        <nav className="flex items-center gap-1 flex-1">
          {[
            { to: '/', label: 'Dashboard', icon: Layers },
            { to: '/portfolio', label: 'Portfolio', icon: BarChart3 },
            { to: '/trades', label: 'Trades', icon: BookOpen },
            { to: '/broker', label: 'Broker', icon: Terminal },
            { to: '/india', label: 'India', icon: IndianRupee },
            { to: '/intelligence', label: 'Intelligence', icon: Brain },
          ].map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'}
              className={({ isActive }) => clsx(
                'flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-all duration-200',
                isActive
                  ? 'bg-surface text-primary border border-border shadow-sm'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover border border-transparent'
              )}>
              {({ isActive }) => (
                <>
                  <Icon size={14} className={clsx(isActive ? 'text-primary' : 'opacity-70')} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-4">
          {provider && (
            <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold px-2.5 py-1 rounded-full
                            border border-accent/20 bg-accent/10 text-accent">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-slow"></span>
              <span>
                {provider === 'anthropic' ? 'Claude' :
                  provider === 'openai' ? 'GPT-4o' :
                    provider === 'gemini' ? 'Gemini' : provider}
              </span>
            </div>
          )}
          
          <div className={clsx(
            'flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold px-2.5 py-1 rounded-full border',
            wsConnected
              ? 'text-success border-success/20 bg-success-dim'
              : 'text-text-muted border-border'
          )}>
            {wsConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
            <span>{wsConnected ? 'Live' : 'Offline'}</span>
          </div>

          {user && (
            <div className="flex items-center gap-3 pl-4 border-l border-border/60">
              <div className="flex flex-col items-end">
                <span className="text-sm font-medium text-text-primary leading-none mb-1">{user.name || 'Trader'}</span>
                <span className="text-[10px] text-text-muted leading-none">{user.email}</span>
              </div>
              <div className="w-8 h-8 rounded-full bg-surface-hover border border-border flex items-center justify-center overflow-hidden">
                <UserIcon size={14} className="text-text-secondary" />
              </div>
              <button onClick={logout} className="ml-1 p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-danger-dim transition-colors" title="Log out">
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Notifications bar */}
      {notifications.length > 0 && (
        <div className="border-b border-border bg-surface-2/50 px-6 py-1.5 overflow-hidden">
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted shrink-0">ALERTS</span>
            <div className="text-xs text-text-secondary truncate">{notifications[0]}</div>
          </div>
        </div>
      )}

      <main className="flex-1 p-6 max-w-screen-xl mx-auto w-full">
        {children}
      </main>
    </div>
  )
}
export default function App() {
  const fetchUser = useAuthStore(s => s.fetchUser)
  const setToken = useAuthStore(s => s.setToken)
  
  useEffect(() => {
    // Check if we just returned from Google OAuth
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    if (token) {
      setToken(token);
      // Clean up URL
      window.history.replaceState({}, document.title, window.location.pathname);
    }
    
    fetchUser()
  }, [])
  
  useWebSocket()
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/*" element={
            <ProtectedRoute>
              <Layout>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/cycle/:id" element={<CyclePage />} />
                  <Route path="/trades" element={<TradesPage />} />
                  <Route path="/portfolio" element={<PortfolioPage />} />
                  <Route path="/broker" element={<BrokerPage />} />
                  <Route path="/india" element={<IndiaPage />} />
                  <Route path="/intelligence" element={<Phase12Page />} />
                </Routes>
              </Layout>
            </ProtectedRoute>
          } />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
