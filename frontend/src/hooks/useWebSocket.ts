import { useEffect, useRef } from 'react'
import { useStore } from '../store/store'

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null)
  const { setWsConnected, updateCycle, addNotification } = useStore()

  useEffect(() => {
    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const socket = new WebSocket(`${proto}://${window.location.host}/ws`)
      ws.current = socket

      socket.onopen = () => {
        setWsConnected(true)
        console.log('[WS] connected')
      }

      socket.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          handleMessage(msg)
        } catch {}
      }

      socket.onclose = () => {
        setWsConnected(false)
        setTimeout(connect, 3000)   // auto-reconnect
      }

      socket.onerror = () => socket.close()
    }

    const handleMessage = (msg: any) => {
      switch (msg.event) {
        case 'cycle_started':
          addNotification(`🚀 Cycle started: ${msg.mode} mode`)
          break
        case 'cycle_update':
          updateCycle(msg.cycle_id, {
            status: msg.status,
            awaiting_human: msg.awaiting_human,
            execution_report: msg.execution_report,
          })
          if (msg.awaiting_human)
            addNotification(`⏳ Awaiting approval: ${msg.symbol}`)
          if (msg.status === 'executed')
            addNotification(`✅ Executed: ${msg.symbol}`)
          if (msg.status === 'rejected')
            addNotification(`❌ Cycle rejected`)
          break
        case 'cycle_error':
          addNotification(`⚠️ Error in cycle: ${msg.error}`)
          break
      }
    }

    connect()
    return () => ws.current?.close()
  }, [])
}
