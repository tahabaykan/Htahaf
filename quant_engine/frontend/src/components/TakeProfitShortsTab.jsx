import React, { useState, useEffect } from 'react'
import './TakeProfitTab.css'

function TakeProfitShortsTab() {
  const [positions, setPositions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadShortPositions()
    const interval = setInterval(loadShortPositions, 5000)
    return () => clearInterval(interval)
  }, [])

  const loadShortPositions = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch('/api/psfalgo/take-profit/shorts')
      const result = await response.json()
      
      if (result.success && result.positions) {
        setPositions(result.positions)
      } else {
        setError(result.detail || result.error || 'Failed to load short positions')
      }
    } catch (err) {
      console.error('Take Profit Shorts: Error loading positions:', err)
      setError(err.message || 'Failed to load short positions')
    } finally {
      setLoading(false)
    }
  }

  const divideLotSize = (totalLot) => {
    // Janall logic: 0-399 lot: direkt, 400+: 200'ün katları + kalan
    if (totalLot <= 0) return []
    if (totalLot <= 399) return [totalLot]
    
    const lotParts = []
    let remaining = totalLot
    
    while (remaining >= 400) {
      lotParts.push(200)
      remaining -= 200
    }
    
    if (remaining > 0) {
      lotParts.push(remaining)
    }
    
    return lotParts
  }

  const handleSendOrder = async (symbol, side, qty, price, orderType) => {
    try {
      const response = await fetch('/api/psfalgo/take-profit/send-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          side,
          qty,
          price,
          order_type: orderType
        })
      })
      const result = await response.json()
      
      if (result.success) {
        alert(`Order sent: ${side} ${qty} ${symbol} @ $${price.toFixed(2)}`)
        loadShortPositions()
      } else {
        alert(`Error: ${result.detail || result.error || 'Failed to send order'}`)
      }
    } catch (err) {
      console.error('Take Profit Shorts: Error sending order:', err)
      alert(`Error: ${err.message || 'Failed to send order'}`)
    }
  }

  if (loading && positions.length === 0) {
    return <div className="take-profit-loading">Loading short positions...</div>
  }

  if (error) {
    return <div className="take-profit-error">⚠️ {error}</div>
  }

  if (positions.length === 0) {
    return <div className="take-profit-empty">No short positions</div>
  }

  return (
    <div className="take-profit-tab">
      <div className="take-profit-header">
        <h3>Take Profit Shorts - Short Positions</h3>
        <button className="btn btn-secondary" onClick={loadShortPositions} disabled={loading}>
          {loading ? '⏳ Loading...' : '🔄 Refresh'}
        </button>
      </div>

      <div className="take-profit-table-container">
        <table className="take-profit-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Quantity</th>
              <th>Avg Price</th>
              <th>Current Bid</th>
              <th>Current Ask</th>
              <th>Last</th>
              <th>LRPAN</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos, idx) => {
              const lotParts = divideLotSize(pos.quantity)
              return (
                <tr key={pos.symbol || idx}>
                  <td className="take-profit-symbol">{pos.symbol}</td>
                  <td>{pos.quantity?.toLocaleString() || 0}</td>
                  <td>${pos.avg_price?.toFixed(2) || '-'}</td>
                  <td>${pos.bid?.toFixed(2) || '-'}</td>
                  <td>${pos.ask?.toFixed(2) || '-'}</td>
                  <td>${pos.last?.toFixed(2) || '-'}</td>
                  <td>${pos.lrpan_price?.toFixed(2) || '-'}</td>
                  <td className="take-profit-actions">
                    <div className="take-profit-buttons">
                      <button
                        className="btn btn-small"
                        onClick={() => handleSendOrder(pos.symbol, 'BUY', lotParts[0] || pos.quantity, pos.bid, 'BID_BUY')}
                        title="Bid Buy"
                      >
                        Bid Buy
                      </button>
                      <button
                        className="btn btn-small"
                        onClick={() => handleSendOrder(pos.symbol, 'BUY', lotParts[0] || pos.quantity, pos.last - 0.01, 'FRONT_BUY')}
                        title="Front Buy"
                      >
                        Front Buy
                      </button>
                      <button
                        className="btn btn-small"
                        onClick={() => handleSendOrder(pos.symbol, 'BUY', lotParts[0] || pos.quantity, pos.last + 0.01, 'SOFTFRONT_BUY')}
                        title="SoftFront Buy"
                      >
                        SoftFront Buy
                      </button>
                      <button
                        className="btn btn-small"
                        onClick={() => handleSendOrder(pos.symbol, 'BUY', lotParts[0] || pos.quantity, pos.ask, 'ASK_BUY')}
                        title="Ask Buy"
                      >
                        Ask Buy
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default TakeProfitShortsTab





