import React, { useState, useEffect } from 'react'
import './TradingPanels.css'
import CleanLogsPanel from './CleanLogsPanel'

function TradingPanels({ tradingMode, initialTab = 'positions', onTabChange }) {
  const [activeTab, setActiveTab] = useState(initialTab)
  const [positions, setPositions] = useState([])
  const [shadowPositions, setShadowPositions] = useState([])
  const [shadowExposure, setShadowExposure] = useState(null)
  const [orders, setOrders] = useState([])
  const [exposure, setExposure] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Update active tab when initialTab prop changes
    if (initialTab && initialTab !== activeTab) {
      setActiveTab(initialTab)
    }
  }, [initialTab])

  const handleTabChange = (tab) => {
    setActiveTab(tab)
    if (onTabChange) {
      onTabChange(tab)
    }
  }

  useEffect(() => {
    // Reload data when trading mode or active tab changes
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
      } else if (activeTab === 'shadow-positions') {
        const response = await fetch('/api/psfalgo/shadow/positions')
        const result = await response.json()
        if (result.success) {
          setShadowPositions(result.positions || [])
        }
        // Also load shadow exposure
        const exposureResponse = await fetch('/api/psfalgo/shadow/exposure')
        const exposureResult = await exposureResponse.json()
        if (exposureResult.success) {
          setShadowExposure(exposureResult.summary || null)
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
    <div className="trading-panels">
      <div className="panel-tabs">
        <button
          className={`tab-button ${activeTab === 'positions' ? 'active' : ''}`}
          onClick={() => handleTabChange('positions')}
        >
          Positions
        </button>
        <button
          className={`tab-button ${activeTab === 'shadow-positions' ? 'active' : ''}`}
          onClick={() => handleTabChange('shadow-positions')}
        >
          Shadow Positions <span className="simulated-badge">SIMULATED</span>
        </button>
        <button
          className={`tab-button ${activeTab === 'orders' ? 'active' : ''}`}
          onClick={() => handleTabChange('orders')}
        >
          Orders
        </button>
        <button
          className={`tab-button ${activeTab === 'exposure' ? 'active' : ''}`}
          onClick={() => handleTabChange('exposure')}
        >
          Exposure
        </button>
        <button
          className={`tab-button ${activeTab === 'cleanlogs' ? 'active' : ''}`}
          onClick={() => handleTabChange('cleanlogs')}
        >
          Clean Logs
        </button>
        <div className="tab-indicator">
          <span className={`trading-mode-badge ${tradingMode === 'HAMMER_TRADING' ? 'hammer-badge' : ''}`}>
            {tradingMode === 'HAMMER_TRADING' ? 'Hammer Account' : tradingMode}
          </span>
        </div>
      </div>

      <div className="panel-content">
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
                    <th>Quantity</th>
                    <th>Avg Price</th>
                    <th>Current Price</th>
                    <th>Unrealized P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos, idx) => {
                    const isLong = (pos.display_qty || pos.qty) > 0
                    const isMixed = pos.display_bucket === 'MIXED'
                    const showBucket = pos.display_bucket && pos.display_bucket !== 'FLAT'

                    return (
                      <tr key={idx}>
                        <td>
                          <div className="symbol-cell">
                            {pos.symbol}
                            {pos.group && <span className="group-badge">{pos.group}</span>}
                          </div>
                        </td>
                        <td>
                          <div className="qty-cell">
                            <span className={isLong ? 'quantity-long' : 'quantity-short'}>
                              {pos.display_qty !== undefined ? pos.display_qty : pos.qty}
                            </span>
                            {showBucket && (
                              <span className={`bucket-badge ${pos.display_bucket.toLowerCase()}`}>
                                {pos.display_bucket}
                              </span>
                            )}
                            {isMixed && (
                              <div className="split-details">
                                LT:{pos.lt_qty_raw} MM:{pos.mm_qty_raw}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className={isLong ? 'quantity-long' : 'quantity-short'}>
                          ${pos.avg_price?.toFixed(2)}
                        </td>
                        <td>
                          {pos.price_status === 'NO_PRICE' ? (
                            <span className="price-warning" title="Price Missing">⚠️ 0.00</span>
                          ) : (
                            <span>${pos.current_price ? pos.current_price.toFixed(2) : 'N/A'}</span>
                          )}
                        </td>
                        <td className={pos.unrealized_pnl >= 0 ? 'positive' : 'negative'}>
                          ${pos.unrealized_pnl ? pos.unrealized_pnl.toFixed(2) : 'N/A'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {!loading && activeTab === 'shadow-positions' && (
          <div className="positions-panel">
            <div className="simulated-warning">
              <strong>⚠️ SIMULATED POSITIONS (DRY-RUN ONLY)</strong>
              <p>These positions are simulated based on PSFALGO execution ledger entries. No real broker execution has occurred.</p>
            </div>

            {shadowExposure && (
              <div className="shadow-exposure-summary">
                <h4>Exposure Summary</h4>
                <div className="exposure-stats">
                  <div className="stat-item">
                    <span className="stat-label">Total Exposure:</span>
                    <span className="stat-value">${shadowExposure.total_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Long Exposure:</span>
                    <span className="stat-value positive">${shadowExposure.long_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Short Exposure:</span>
                    <span className="stat-value negative">${shadowExposure.short_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Net Exposure:</span>
                    <span className={`stat-value ${shadowExposure.net_exposure >= 0 ? 'positive' : 'negative'}`}>
                      ${shadowExposure.net_exposure?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Total Long Value:</span>
                    <span className="stat-value positive">${shadowExposure.total_long_value?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Total Short Value:</span>
                    <span className="stat-value negative">${shadowExposure.total_short_value?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Net Market Value:</span>
                    <span className={`stat-value ${shadowExposure.net_value >= 0 ? 'positive' : 'negative'}`}>
                      ${shadowExposure.net_value?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Long Positions:</span>
                    <span className="stat-value">{shadowExposure.long_count || shadowExposure.symbol_count_long || 0}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Short Positions:</span>
                    <span className="stat-value">{shadowExposure.short_count || shadowExposure.symbol_count_short || 0}</span>
                  </div>
                </div>
              </div>
            )}

            {shadowPositions.length === 0 ? (
              <div className="empty-state">
                No shadow positions (no approved actions in ledger)
              </div>
            ) : (
              <table className="positions-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Long Qty</th>
                    <th>Short Qty</th>
                    <th>Market Price</th>
                    <th>Avg Cost (Long)</th>
                    <th>Avg Cost (Short)</th>
                    <th>Market Value (Net)</th>
                    <th>Exposure</th>
                    <th>Entry Count</th>
                  </tr>
                </thead>
                <tbody>
                  {shadowPositions.map((pos, idx) => (
                    <tr key={idx}>
                      <td>{pos.symbol}</td>
                      <td className={pos.current_qty >= 0 ? 'quantity-long' : 'quantity-short'}>
                        {pos.current_qty > 0 ? '+' : ''}{pos.current_qty}
                      </td>
                      <td className="quantity-long">{pos.long_qty || 0}</td>
                      <td className="quantity-short">{pos.short_qty || 0}</td>
                      <td>${pos.market_price_used?.toFixed(4) || 'N/A'}</td>
                      <td className="quantity-long">${pos.avg_cost_long?.toFixed(4) || 'N/A'}</td>
                      <td className="quantity-short">${pos.avg_cost_short?.toFixed(4) || 'N/A'}</td>
                      <td className={pos.market_value_net >= 0 ? 'positive' : 'negative'}>
                        ${pos.market_value_net?.toFixed(2) || '0.00'}
                      </td>
                      <td>${pos.exposure?.toFixed(2) || '0.00'}</td>
                      <td>{pos.entry_count || 0}</td>
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
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order, idx) => (
                    <tr key={idx}>
                      <td>{order.symbol}</td>
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
                  <span className="metric-label">Long Exposure:</span>
                  <span className="metric-value positive">${exposure.long_exposure?.toFixed(2)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Short Exposure:</span>
                  <span className="metric-value negative">${exposure.short_exposure?.toFixed(2)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Net Exposure:</span>
                  <span className={`metric-value ${exposure.net_exposure >= 0 ? 'positive' : 'negative'}`}>
                    ${exposure.net_exposure?.toFixed(2)}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Position Count:</span>
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

        {activeTab === 'cleanlogs' && (
          <CleanLogsPanel tradingMode={tradingMode} />
        )}
      </div>
    </div>
  )
}

export default TradingPanels

