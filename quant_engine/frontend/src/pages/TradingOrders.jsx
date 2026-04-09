import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './TradingPage.css'

function TradingOrders() {
  const navigate = useNavigate()
  const [tradingMode, setTradingMode] = useState('HAMMER_TRADING')
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedOrders, setSelectedOrders] = useState(new Set())

  useEffect(() => {
    loadTradingMode()
    loadOrders()
    const timer = setInterval(loadOrders, 2000)
    const modeInterval = setInterval(loadTradingMode, 5000)
    return () => { clearInterval(timer); clearInterval(modeInterval) }
  }, [])

  useEffect(() => {
    loadOrders()
  }, [tradingMode])

  const loadTradingMode = async () => {
    try {
      const response = await fetch('/api/trading/mode')
      const result = await response.json()
      if (result.success) {
        const m = result.trading_mode || result.mode || ''
        setTradingMode(m === 'HAMPRO' ? 'HAMMER_TRADING' : m)
      }
    } catch (err) {
      console.error('Error loading trading mode:', err)
    }
  }

  const loadOrders = async () => {
    try {
      // Use Janall endpoint ensuring we see Native Client orders
      const response = await fetch('/api/janall/orders')
      const result = await response.json() // returns { open_orders: [], filled_orders: [] }

      if (result) {
        // Merge or just show open orders? Janall usually shows pending.
        // Let's default to open_orders for the main table.
        // Note: result might be { orders: ... } if using trading_routes, but janall_routes returns { open_orders, filled_orders }
        // Let's handle both structures just in case, but prefer janall structure.
        const open = result.open_orders || result.orders || []
        setOrders(open)
      }
    } catch (err) {
      console.error('Error loading orders:', err)
    }
  }

  // Selection Logic
  const toggleSelect = (orderId) => {
    const newSelected = new Set(selectedOrders)
    if (newSelected.has(orderId)) {
      newSelected.delete(orderId)
    } else {
      newSelected.add(orderId)
    }
    setSelectedOrders(newSelected)
  }

  const toggleSelectAll = () => {
    if (selectedOrders.size === orders.length && orders.length > 0) {
      setSelectedOrders(new Set())
    } else {
      const allIds = new Set(orders.map(o => o.order_id))
      setSelectedOrders(allIds)
    }
  }

  const handleBulkCancel = async () => {
    if (selectedOrders.size === 0) return
    if (!confirm(`Cancel ${selectedOrders.size} selected orders?`)) return
    try {
      const response = await fetch('/api/janall/cancel-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_ids: Array.from(selectedOrders) })
      })
      const result = await response.json()
      if (result.success) {
        setSelectedOrders(new Set())
        loadOrders()
        alert(result.message)
      } else {
        alert('Failed: ' + result.message)
      }
    } catch (err) {
      alert('Error cancelling: ' + err)
    }
  }

  const handleCancelAll = async () => {
    if (orders.length === 0) return
    if (!confirm('Cancel ALL open orders on this account? (reqGlobalCancel)')) return
    try {
      const response = await fetch('/api/janall/cancel-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_ids: [] })
      })
      const result = await response.json()
      if (result.success) {
        setSelectedOrders(new Set())
        loadOrders()
        alert(result.message)
      } else {
        alert('Failed: ' + (result.message || 'Cancel all failed'))
      }
    } catch (err) {
      alert('Error: ' + err)
    }
  }

  return (
    <div className="trading-page">
      <div className="trading-page-header">
        <h1>Orders (Janall Style)</h1>
        <div className="trading-mode-badge">
          {tradingMode.includes('HAMMER') ? '🟢 Hammer' : '🟣 IBKR Native'}
        </div>

        {orders.length > 0 && (
          <button className="cancel-button" onClick={handleCancelAll} style={{ backgroundColor: '#b91c1c', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer', marginLeft: '8px' }}>
            Tümünü iptal ({orders.length})
          </button>
        )}
        {selectedOrders.size > 0 && (
          <button className="cancel-button" onClick={handleBulkCancel} style={{ backgroundColor: '#ef4444', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer', marginLeft: '8px' }}>
            Seçileni iptal ({selectedOrders.size})
          </button>
        )}

        <button className="back-button" onClick={() => navigate('/')}>
          ← Back to Scanner
        </button>
      </div>

      <div className="trading-page-content">
        {loading && orders.length === 0 && (
          <div className="loading-message">Loading orders...</div>
        )}

        {!loading && orders.length === 0 && (
          <div className="empty-state">
            No pending orders.
          </div>
        )}

        {orders.length > 0 && (
          <table className="trading-table">
            <thead>
              <tr>
                <th style={{ width: '40px' }}>
                  <input
                    type="checkbox"
                    checked={selectedOrders.size === orders.length && orders.length > 0}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Filled</th>
                <th>Price</th>
                <th>Status</th>
                <th>Client / İptal</th>
                <th>ID</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order, idx) => {
                const oid = order.order_id || `temp-${idx}`
                return (
                  <tr key={oid} className={selectedOrders.has(oid) ? 'selected-row' : ''}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedOrders.has(oid)}
                        onChange={() => toggleSelect(oid)}
                      />
                    </td>
                    <td className="symbol-cell">{order.symbol}</td>
                    <td style={{ color: order.action === 'BUY' ? '#22c55e' : '#ef4444', fontWeight: 'bold' }}>{order.action || order.side}</td>
                    <td>{order.qty || order.quantity}</td>
                    <td>{order.filled || 0}</td>
                    <td>{order.price ? `$${order.price.toFixed(2)}` : order.order_type}</td>
                    <td>{order.status}</td>
                    <td style={{ fontSize: '0.8em' }}>
                      {order.client_id_label != null && (
                        <span title={order.cancelable_by_this_session ? 'Bu oturumdan iptal edilebilir' : 'Başka oturum; Tümünü iptal gerekir'}>
                          {order.client_id_label}
                          {order.cancelable_by_this_session != null && (
                            <span style={{
                              display: 'inline-block',
                              marginLeft: 4,
                              padding: '1px 5px',
                              borderRadius: 4,
                              fontSize: '0.85em',
                              backgroundColor: order.cancelable_by_this_session ? '#dcfce7' : '#fed7aa',
                              color: order.cancelable_by_this_session ? '#166534' : '#9a3412'
                            }}>
                              {order.cancelable_by_this_session ? 'Bu oturum' : 'Başka'}
                            </span>
                          )}
                        </span>
                      )}
                    </td>
                    <td className="order-id-cell">{oid}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default TradingOrders
