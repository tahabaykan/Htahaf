import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './TradingPage.css'

function TradingOrders() {
  const navigate = useNavigate()
  const [tradingMode, setTradingMode] = useState('HAMMER_TRADING')
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadTradingMode()
    loadOrders()
  }, [])

  useEffect(() => {
    loadOrders()
  }, [tradingMode])

  const loadTradingMode = async () => {
    try {
      const response = await fetch('/api/trading/mode')
      const result = await response.json()
      if (result.success) {
        setTradingMode(result.mode)
      }
    } catch (err) {
      console.error('Error loading trading mode:', err)
    }
  }

  const loadOrders = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/trading/orders')
      const result = await response.json()
      if (result.success) {
        setOrders(result.orders || [])
      }
    } catch (err) {
      console.error('Error loading orders:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="trading-page">
      <div className="trading-page-header">
        <h1>Orders</h1>
        <div className="trading-mode-badge">
          {tradingMode === 'HAMMER_TRADING' ? '🟢 Hammer Account' : '🟣 IBKR Account'}
        </div>
        <button className="back-button" onClick={() => navigate('/')}>
          ← Back to Scanner
        </button>
      </div>

      <div className="trading-page-content">
        {loading && (
          <div className="loading-message">Loading orders...</div>
        )}

        {!loading && orders.length === 0 && (
          <div className="empty-state">
            No orders in {tradingMode}
          </div>
        )}

        {!loading && orders.length > 0 && (
          <table className="trading-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Quantity</th>
                <th>Price/Type</th>
                <th>Status</th>
                <th>Order ID</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order, idx) => (
                <tr key={idx}>
                  <td className="symbol-cell">{order.symbol}</td>
                  <td>{order.side}</td>
                  <td>{order.quantity}</td>
                  <td>{order.price ? `$${order.price.toFixed(2)}` : order.order_type}</td>
                  <td>{order.status}</td>
                  <td className="order-id-cell">{order.order_id || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default TradingOrders








