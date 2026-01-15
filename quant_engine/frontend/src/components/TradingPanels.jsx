import React, { useState, useEffect, useMemo } from 'react'
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

  // Bulk Selection State
  const [selectedOrders, setSelectedOrders] = useState(new Set())

  // Sorting State
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'ascending' })

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

    // Auto-refresh orders if tab is active
    let interval = null
    if (activeTab === 'orders') {
      interval = setInterval(loadData, 2000)
    }
    return () => { if (interval) clearInterval(interval) }
  }, [tradingMode, activeTab])

  const loadData = async () => {
    // Silent load for auto-refresh to avoid flickering if already loaded once?
    // For now simple load.
    if (!orders.length && activeTab === 'orders') setLoading(true)
    else if (activeTab !== 'orders') setLoading(true)

    try {
      if (activeTab === 'positions') {
        const response = await fetch(`/api/trading/positions?_t=${Date.now()}`)
        const result = await response.json()
        if (result.success) {
          setPositions(result.positions || [])
        }
      } else if (activeTab === 'shadow-positions') {
        const response = await fetch(`/api/psfalgo/shadow/positions?_t=${Date.now()}`)
        const result = await response.json()
        if (result.success) {
          setShadowPositions(result.positions || [])
        }
        // Also load shadow exposure
        const exposureResponse = await fetch(`/api/psfalgo/shadow/exposure?_t=${Date.now()}`)
        const exposureResult = await exposureResponse.json()
        if (exposureResult.success) {
          setShadowExposure(exposureResult.summary || null)
        }
      } else if (activeTab === 'orders') {
        // Use Janall endpoint for Native visibility
        const response = await fetch(`/api/janall/orders?_t=${Date.now()}`)
        const result = await response.json()
        if (result) {
          // Janall routes return { open_orders: [], filled_orders: [] } usually
          const open = result.open_orders || result.orders || []
          setOrders(open)
        }
      } else if (activeTab === 'exposure') {
        const response = await fetch(`/api/trading/exposure?_t=${Date.now()}`)
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
      const allIds = new Set(orders.map(o => o.order_id || `temp-${orders.indexOf(o)}`))
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
        // Clear selection and refresh
        setSelectedOrders(new Set())
        loadData()
        alert(result.message)
      } else {
        alert('Failed: ' + result.message)
      }
    } catch (err) {
      alert('Error cancelling: ' + err)
    }
  }


  // Sorting Logic
  const requestSort = (key) => {
    let direction = 'ascending'
    if (sortConfig.key === key && sortConfig.direction === 'ascending') {
      direction = 'descending'
    }
    setSortConfig({ key, direction })
  }

  const sortedPositions = useMemo(() => {
    let sortableItems = [...positions]
    if (sortConfig.key !== null) {
      sortableItems.sort((a, b) => {
        let aValue = a[sortConfig.key]
        let bValue = b[sortConfig.key]

        // Special handling for derived columns
        if (sortConfig.key === 'quantity') {
          aValue = a.display_qty !== undefined ? a.display_qty : a.qty
          bValue = b.display_qty !== undefined ? b.display_qty : b.qty
        }

        if (aValue < bValue) {
          return sortConfig.direction === 'ascending' ? -1 : 1
        }
        if (aValue > bValue) {
          return sortConfig.direction === 'ascending' ? 1 : -1
        }
        return 0
      })
    }
    return sortableItems
  }, [positions, sortConfig])

  const getSortIndicator = (key) => {
    if (sortConfig.key !== key) return ''
    return sortConfig.direction === 'ascending' ? ' ▲' : ' ▼'
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
        {loading && activeTab !== 'orders' && ( // Don't show generic loading for orders refresh
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
                    <th onClick={() => requestSort('symbol')} className="sortable-header">
                      Symbol <span className="sort-icon">{getSortIndicator('symbol')}</span>
                    </th>
                    <th onClick={() => requestSort('quantity')} className="sortable-header">
                      Quantity <span className="sort-icon">{getSortIndicator('quantity')}</span>
                    </th>
                    <th onClick={() => requestSort('avg_price')} className="sortable-header">
                      Avg Price <span className="sort-icon">{getSortIndicator('avg_price')}</span>
                    </th>
                    <th onClick={() => requestSort('intraday_cost')} className="sortable-header">
                      Intra Cost <span className="sort-icon">{getSortIndicator('intraday_cost')}</span>
                    </th>
                    <th onClick={() => requestSort('intraday_pnl')} className="sortable-header">
                      Intra P&L <span className="sort-icon">{getSortIndicator('intraday_pnl')}</span>
                    </th>
                    <th onClick={() => requestSort('current_price')} className="sortable-header">
                      Current Price <span className="sort-icon">{getSortIndicator('current_price')}</span>
                    </th>
                    <th onClick={() => requestSort('unrealized_pnl')} className="sortable-header">
                      Unrealized P&L <span className="sort-icon">{getSortIndicator('unrealized_pnl')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPositions.map((pos, idx) => {
                    const isLong = (pos.display_qty || pos.qty) > 0
                    const isMixed = pos.display_bucket === 'MIXED'

                    return (
                      <tr key={idx}>
                        <td>
                          <div className="symbol-cell">
                            <span className="symbol-text">
                              {pos.symbol}
                            </span>
                            {/* Taxonomy Badge */}
                            {pos.full_taxonomy ? (
                              <span className={`taxonomy-badge ${pos.strategy_type?.toLowerCase() || 'lt'}`}>
                                {pos.full_taxonomy}
                              </span>
                            ) : (
                              <span className="taxonomy-badge lt">LT OV {isLong ? 'Long' : 'Short'}</span>
                            )}
                            {pos.group && <span className="group-badge">{pos.group}</span>}
                          </div>
                        </td>
                        <td>
                          <div className="qty-cell">
                            <span className={isLong ? 'quantity-long' : 'quantity-short'}>
                              {pos.display_qty !== undefined ? pos.display_qty : pos.qty}
                            </span>
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
                          {pos.intraday_cost ? `$${pos.intraday_cost.toFixed(2)}` : '-'}
                        </td>
                        <td className={pos.intraday_pnl >= 0 ? 'positive' : 'negative'}>
                          {pos.intraday_pnl ? `$${pos.intraday_pnl.toFixed(2)}` : '-'}
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

        {/* --- ORDERS PANEL WITH ACTIONS --- */}
        {activeTab === 'orders' && (
          <div className="orders-panel">
            <div className="orders-actions" style={{ marginBottom: '10px' }}>
              {orders.length > 0 && (
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <h3 style={{ margin: 0 }}>Active Orders ({orders.length})</h3>
                  {selectedOrders.size > 0 && (
                    <button
                      className="cancel-button"
                      onClick={handleBulkCancel}
                      style={{
                        backgroundColor: '#ef4444',
                        color: 'white',
                        border: 'none',
                        padding: '6px 16px',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontWeight: 'bold',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
                      }}
                    >
                      Cancel Selected ({selectedOrders.size})
                    </button>
                  )}
                </div>
              )}
            </div>

            {orders.length === 0 ? (
              <div className="empty-state">
                No orders in {tradingMode}
              </div>
            ) : (
              <table className="orders-table">
                <thead>
                  <tr>
                    <th style={{ width: '40px', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={orders.length > 0 && selectedOrders.size === orders.length}
                        onChange={toggleSelectAll}
                        style={{ cursor: 'pointer', transform: 'scale(1.2)' }}
                      />
                    </th>
                    <th>Tag</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Status</th>
                    <th>Time</th>
                    <th>ID</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order, idx) => {
                    const oid = order.order_id || `temp-${idx}`
                    // Determine color
                    const isBuy = (order.action || order.side || '').toUpperCase() === 'BUY'

                    return (
                      <tr key={oid} className={selectedOrders.has(oid) ? 'selected-row' : ''} style={selectedOrders.has(oid) ? { backgroundColor: 'rgba(239, 68, 68, 0.1)' } : {}}>
                        <td style={{ textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            checked={selectedOrders.has(oid)}
                            onChange={() => toggleSelect(oid)}
                            style={{ cursor: 'pointer', transform: 'scale(1.2)' }}
                          />
                        </td>
                        <td>
                          <span className={`order-tag tag-${(order.tag || 'unknown').toLowerCase().replace(/_/g, '-')}`}>
                            {order.tag || 'N/A'}
                          </span>
                        </td>
                        <td><strong>{order.symbol}</strong></td>
                        <td style={{ color: isBuy ? '#22c55e' : '#ef4444', fontWeight: 'bold' }}>
                          {order.action || order.side}
                        </td>
                        <td>{order.qty || order.quantity}</td>
                        <td>{order.price ? `$${order.price.toFixed(2)}` : order.order_type}</td>
                        <td>
                          <span className={`status-badge ${(order.status || '').toLowerCase()}`}>
                            {order.status}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.85em', color: '#666' }}>
                          {order.timestamp ? new Date(order.timestamp * 1000).toLocaleTimeString() : '-'}
                        </td>
                        <td style={{ fontSize: '0.8em', color: '#888', maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {oid}
                        </td>
                      </tr>
                    )
                  })}
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
