import React, { useState, useEffect } from 'react'
import './TradingSidebar.css'

function TradingSidebar({ tradingMode }) {
  const [activeTab, setActiveTab] = useState('positions')
  const [positions, setPositions] = useState([])
  const [orders, setOrders] = useState([])
  const [exposure, setExposure] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Reload data when trading mode changes
    loadData()
  }, [tradingMode, activeTab])

  const loadData = async () => {
    setLoading(true)
    try {
      if (activeTab === 'positions') {
        const response = await fetch('/api/trading/positions')
        const result = await response.json()
        if (result.success) {
          setPositions(result.positions || [])
        }
      } else if (activeTab === 'orders') {
        const response = await fetch('/api/trading/orders')
        const result = await response.json()
        if (result.success) {
          setOrders(result.orders || [])
        }
      } else if (activeTab === 'exposure') {
        const response = await fetch('/api/trading/exposure')
        const result = await response.json()
        if (result.success) {
          setExposure(result.exposure || null)
        }
      }
    } catch (err) {
      console.error(`Error loading ${activeTab}:`, err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="trading-sidebar">
      {/* Trading Account Badge */}
      <div className="sidebar-header">
        <div className={`trading-mode-badge ${tradingMode === 'HAMMER_TRADING' ? 'hammer-badge' : ''}`}>
          {tradingMode === 'HAMMER_TRADING' ? 'Hammer Account' : tradingMode}
        </div>
      </div>

      {/* Tabs */}
      <div className="sidebar-tabs">
        <button
          className={`sidebar-tab ${activeTab === 'positions' ? 'active' : ''}`}
          onClick={() => setActiveTab('positions')}
        >
          Positions
        </button>
        <button
          className={`sidebar-tab ${activeTab === 'orders' ? 'active' : ''}`}
          onClick={() => setActiveTab('orders')}
        >
          Orders
        </button>
        <button
          className={`sidebar-tab ${activeTab === 'exposure' ? 'active' : ''}`}
          onClick={() => setActiveTab('exposure')}
        >
          Exposure
        </button>
      </div>

      {/* Content */}
      <div className="sidebar-content">
        {loading && (
          <div className="loading-message">Loading...</div>
        )}

        {!loading && activeTab === 'positions' && (
          <div className="positions-panel">
            {positions.length === 0 ? (
              <div className="empty-state">
                No positions in {tradingMode}
              </div>
            ) : (
              <table className="positions-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side/Qty</th>
                    <th>Avg</th>
                    <th>Last</th>
                    <th>P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos, idx) => (
                    <tr key={idx}>
                      <td className="symbol-cell">{pos.symbol}</td>
                      <td>{pos.side} {pos.quantity}</td>
                      <td>${pos.avg_price?.toFixed(2)}</td>
                      <td>${pos.current_price ? pos.current_price.toFixed(2) : 'N/A'}</td>
                      <td className={pos.unrealized_pnl >= 0 ? 'positive' : 'negative'}>
                        ${pos.unrealized_pnl ? pos.unrealized_pnl.toFixed(2) : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {!loading && activeTab === 'orders' && (
          <div className="orders-panel">
            {orders.length === 0 ? (
              <div className="empty-state">
                No orders in {tradingMode}
              </div>
            ) : (
              <table className="orders-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Status</th>
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
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {!loading && activeTab === 'exposure' && (
          <div className="exposure-panel">
            {exposure ? (
              <div className="exposure-metrics">
                <div className="metric-item">
                  <span className="metric-label">Total Exposure:</span>
                  <span className="metric-value">${exposure.total_exposure?.toFixed(2)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Long:</span>
                  <span className="metric-value positive">${exposure.long_exposure?.toFixed(2)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Short:</span>
                  <span className="metric-value negative">${exposure.short_exposure?.toFixed(2)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Net:</span>
                  <span className={`metric-value ${exposure.net_exposure >= 0 ? 'positive' : 'negative'}`}>
                    ${exposure.net_exposure?.toFixed(2)}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Positions:</span>
                  <span className="metric-value">{exposure.position_count}</span>
                </div>
              </div>
            ) : (
              <div className="empty-state">
                No exposure data for {tradingMode}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default TradingSidebar








