import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './TradingPage.css'

function TradingPositions() {
  const navigate = useNavigate()
  const [tradingMode, setTradingMode] = useState('HAMMER_TRADING')
  const [positions, setPositions] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadTradingMode()
    loadPositions()
  }, [])

  useEffect(() => {
    loadPositions()
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

  const loadPositions = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/trading/positions')
      const result = await response.json()
      if (result.success) {
        setPositions(result.positions || [])
      }
    } catch (err) {
      console.error('Error loading positions:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="trading-page">
      <div className="trading-page-header">
        <h1>Positions</h1>
        <div className="trading-mode-badge">
          {tradingMode === 'HAMMER_TRADING' ? '🟢 Hammer Account' : '🟣 IBKR Account'}
        </div>
        <button className="back-button" onClick={() => navigate('/')}>
          ← Back to Scanner
        </button>
      </div>

      <div className="trading-page-content">
        {loading && (
          <div className="loading-message">Loading positions...</div>
        )}

        {!loading && positions.length === 0 && (
          <div className="empty-state">
            No positions in {tradingMode}
          </div>
        )}

        {!loading && positions.length > 0 && (
          <table className="trading-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Quantity</th>
                <th>Avg Price</th>
                <th>Current Price</th>
                <th>Unrealized P&L</th>
                <th>Market Value</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, idx) => {
                const isLong = pos.side === 'LONG' || (pos.quantity && pos.quantity > 0)
                const isShort = pos.side === 'SHORT' || (pos.quantity && pos.quantity < 0)
                const quantity = pos.quantity || pos.qty || 0
                const displayQuantity = isShort ? `-${Math.abs(quantity)}` : quantity
                
                return (
                  <tr key={idx}>
                    <td className="symbol-cell">{pos.symbol}</td>
                    <td className={isLong ? 'quantity-long' : isShort ? 'quantity-short' : ''}>
                      {displayQuantity}
                    </td>
                    <td className={isLong ? 'quantity-long' : isShort ? 'quantity-short' : ''}>
                      ${pos.avg_price?.toFixed(2)}
                    </td>
                    <td>${pos.current_price ? pos.current_price.toFixed(2) : 'N/A'}</td>
                    <td className={pos.unrealized_pnl >= 0 ? 'positive' : 'negative'}>
                      ${pos.unrealized_pnl ? pos.unrealized_pnl.toFixed(2) : 'N/A'}
                    </td>
                    <td>${pos.market_value ? pos.market_value.toFixed(2) : 'N/A'}</td>
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

export default TradingPositions


