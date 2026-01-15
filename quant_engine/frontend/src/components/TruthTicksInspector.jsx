import React, { useState, useEffect } from 'react'
import './TruthTicksInspector.css'

const API_BASE = 'http://localhost:8000/api'

// Price-Time Chart Component
function PriceTimeChart({ data, overlayBands, markers, buckets, formatNumber, formatTimestamp }) {
  const chartHeight = 400
  const chartPadding = { top: 20, right: 60, bottom: 60, left: 80 }
  const chartWidth = 800
  
  if (!data || data.length === 0) {
    return <div className="no-chart-data">No data available</div>
  }
  
  // Sort by timestamp
  const sortedData = [...data].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
  
  // Calculate price range
  const prices = sortedData.map(d => d.price).filter(p => p != null)
  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const priceRange = maxPrice - minPrice || 0.01
  const pricePadding = priceRange * 0.1
  
  // Calculate time range
  const timestamps = sortedData.map(d => d.timestamp).filter(t => t != null)
  const minTime = Math.min(...timestamps)
  const maxTime = Math.max(...timestamps)
  const timeRange = maxTime - minTime || 1
  
  // Scale functions
  const scaleX = (timestamp) => {
    return chartPadding.left + ((timestamp - minTime) / timeRange) * (chartWidth - chartPadding.left - chartPadding.right)
  }
  const scaleY = (price) => {
    return chartPadding.top + ((maxPrice + pricePadding - price) / (priceRange + pricePadding * 2)) * (chartHeight - chartPadding.top - chartPadding.bottom)
  }
  
  // Generate path for price line
  const pathData = sortedData
    .filter(d => d.price != null && d.timestamp != null)
    .map((d, idx) => `${idx === 0 ? 'M' : 'L'} ${scaleX(d.timestamp)} ${scaleY(d.price)}`)
    .join(' ')
  
  return (
    <div className="price-time-chart-container">
      <svg width={chartWidth} height={chartHeight + 80} className="chart-svg">
        {/* Grid lines - Price */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const price = minPrice - pricePadding + (priceRange + pricePadding * 2) * (1 - ratio)
          const y = scaleY(price)
          return (
            <g key={`price-grid-${ratio}`}>
              <line
                x1={chartPadding.left}
                y1={y}
                x2={chartWidth - chartPadding.right}
                y2={y}
                stroke="#e0e0e0"
                strokeWidth="1"
                strokeDasharray="2,2"
              />
              <text
                x={chartWidth - chartPadding.right + 10}
                y={y + 4}
                textAnchor="start"
                fontSize="11"
                fill="#000"
              >
                ${formatNumber(price, 2)}
              </text>
            </g>
          )
        })}
        
        {/* Overlay bands (Volav levels) */}
        {overlayBands && overlayBands.map((band, idx) => {
          const y = scaleY(band.price)
          return (
            <g key={`band-${idx}`}>
              <line
                x1={chartPadding.left}
                y1={y}
                x2={chartWidth - chartPadding.right}
                y2={y}
                stroke="#007bff"
                strokeWidth="2"
                strokeDasharray="5,5"
                opacity="0.6"
              />
              <text
                x={chartPadding.left + 5}
                y={y + 4}
                fontSize="10"
                fill="#000"
                fontWeight="600"
              >
                {band.level} (${formatNumber(band.price, 2)})
              </text>
            </g>
          )
        })}
        
        {/* Price line */}
        <path
          d={pathData}
          fill="none"
          stroke="#000"
          strokeWidth="1.5"
          className="price-line"
          opacity="0.3"
        />
        
        {/* Volume Buckets - Volume-proportional circles at bucket VWAP prices */}
        {buckets && buckets.length > 0 && (() => {
          const maxBucketVolume = Math.max(...buckets.map(b => b.volume || 0), 1)
          // Reduced circle sizes
          const minRadius = 5
          const maxRadius = 15
          
          return buckets.map((bucket, idx) => {
            const bucketPrice = bucket.price
            const bucketVolume = bucket.volume || 0
            const bucketRadius = minRadius + ((bucketVolume / maxBucketVolume) * (maxRadius - minRadius))
            const y = scaleY(bucketPrice)
            
            // Find ticks that belong to this bucket (price within bucket range)
            // Bucket size is dynamic, but we'll use a reasonable tolerance (e.g., 0.05 cent)
            const bucketTolerance = 0.05
            const bucketTicks = sortedData.filter(d => 
              d.price != null && 
              d.timestamp != null && 
              Math.abs(d.price - bucketPrice) <= bucketTolerance
            )
            
            // Calculate bucket's real time position from its ticks
            let bucketTimestamp
            if (bucketTicks.length > 0) {
              // Use average timestamp of ticks in this bucket
              const avgTimestamp = bucketTicks.reduce((sum, tick) => sum + tick.timestamp, 0) / bucketTicks.length
              bucketTimestamp = avgTimestamp
            } else {
              // Fallback: use middle of time range if no matching ticks found
              bucketTimestamp = (minTime + maxTime) / 2
            }
            
            const x = scaleX(bucketTimestamp)
            
            return (
              <g key={`bucket-${idx}`} className="bucket-circle-group">
                {/* Outer glow for larger volumes (reduced size) */}
                {bucketVolume > maxBucketVolume * 0.3 && (
                  <circle
                    cx={x}
                    cy={y}
                    r={bucketRadius + 2}
                    fill="#007bff"
                    opacity="0.15"
                  />
                )}
                {/* Main bucket circle */}
                <circle
                  cx={x}
                  cy={y}
                  r={bucketRadius}
                  fill="#007bff"
                  stroke="white"
                  strokeWidth="2"
                  className="bucket-circle"
                  opacity="0.7"
                  style={{
                    filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.3))'
                  }}
                />
                {/* Bucket label - price */}
                <text
                  x={x}
                  y={y - bucketRadius - 6}
                  textAnchor="middle"
                  fontSize="9"
                  fill="#000"
                  fontWeight="600"
                >
                  ${formatNumber(bucketPrice, 2)}
                </text>
                {/* Bucket label - volume */}
                <text
                  x={x}
                  y={y + bucketRadius + 12}
                  textAnchor="middle"
                  fontSize="8"
                  fill="#000"
                  fontWeight="500"
                >
                  {formatNumber(bucketVolume, 0)}
                </text>
              </g>
            )
          })
        })()}
        
        {/* Individual tick points (small, subtle) */}
        {sortedData.filter(d => d.price != null && d.timestamp != null).map((d, idx) => {
          const x = scaleX(d.timestamp)
          const y = scaleY(d.price)
          
          return (
            <g key={`point-${idx}`} className="data-point-group">
              <circle
                cx={x}
                cy={y}
                r="1.5"
                fill="#000"
                className="data-point"
                opacity="0.4"
              />
            </g>
          )
        })}
        
        {/* Markers */}
        {markers && markers.map((marker, idx) => {
          if (!marker.timestamp || !marker.price) return null
          const x = scaleX(marker.timestamp)
          const y = scaleY(marker.price)
          const isStart = marker.type === 'volav1_start'
          
          return (
            <g key={`marker-${idx}`}>
              <circle
                cx={x}
                cy={y}
                r="6"
                fill={isStart ? "#28a745" : "#ffc107"}
                stroke="white"
                strokeWidth="2"
              />
              <text
                x={x}
                y={y - 10}
                textAnchor="middle"
                fontSize="10"
                fill="#000"
                fontWeight="600"
              >
                {isStart ? 'Start' : 'End'}
              </text>
            </g>
          )
        })}
        
        {/* X-axis labels */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const timestamp = minTime + timeRange * ratio
          const x = scaleX(timestamp)
          return (
            <g key={`time-label-${ratio}`}>
              <line
                x1={x}
                y1={chartHeight - chartPadding.bottom}
                x2={x}
                y2={chartHeight - chartPadding.bottom + 5}
                stroke="#000"
                strokeWidth="1"
              />
              <text
                x={x}
                y={chartHeight - chartPadding.bottom + 20}
                textAnchor="middle"
                fontSize="10"
                fill="#000"
              >
                {formatTimestamp(timestamp)}
              </text>
            </g>
          )
        })}
      </svg>
      
      {/* Legend */}
      <div className="chart-legend">
        <div className="legend-item">
          <span className="legend-color" style={{background: '#000'}}></span>
          <span>Fiyat Çizgisi</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{background: '#007bff', opacity: 0.6}}></span>
          <span>Volav Seviyeleri</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{background: '#28a745'}}></span>
          <span>Volav1 Start</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{background: '#ffc107'}}></span>
          <span>Volav1 End</span>
        </div>
      </div>
    </div>
  )
}

// Mini Chart Component for Volav Timeline
function VolavMiniChart({ timeline, volavType, formatNumber, formatTimestamp, formatTimestampShort }) {
  const chartHeight = 200
  const chartPadding = { top: 20, right: 40, bottom: 50, left: 70 }
  const chartWidth = Math.max(600, timeline.length * 100) // Responsive width
  
  // Filter valid data points
  const dataPoints = timeline
    .map((window, idx) => ({
      x: idx,
      price: window[volavType],
      volume: window.volav_levels?.find(v => v.rank === parseInt(volavType.replace('volav', '')))?.volume || 0,
      volumePct: window.volav_levels?.find(v => v.rank === parseInt(volavType.replace('volav', '')))?.pct_of_truth_volume || 0,
      timestamp: window.start_timestamp,
      windowIndex: window.window_index
    }))
    .filter(d => d.price !== null && d.price !== undefined)
  
  if (dataPoints.length === 0) {
    return <div className="no-chart-data">No {volavType} data available</div>
  }
  
  // Calculate price range
  const prices = dataPoints.map(d => d.price)
  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const priceRange = maxPrice - minPrice || 0.01
  const pricePadding = priceRange * 0.1
  
  // Calculate volume range for bar heights and sphere sizes
  const volumes = dataPoints.map(d => d.volume)
  const maxVolume = Math.max(...volumes, 1)
  
  // Scale functions
  const scaleX = (idx) => chartPadding.left + (idx / (dataPoints.length - 1 || 1)) * (chartWidth - chartPadding.left - chartPadding.right)
  const scaleY = (price) => chartPadding.top + ((maxPrice + pricePadding - price) / (priceRange + pricePadding * 2)) * (chartHeight - chartPadding.top - chartPadding.bottom)
  const scaleVolume = (vol) => (vol / maxVolume) * 30 // Max bar height 30px
  const scaleSphereRadius = (vol) => {
    // Sphere radius based on volume: min 4px, max 12px
    const minRadius = 4
    const maxRadius = 12
    if (maxVolume === 0) return minRadius
    return minRadius + ((vol / maxVolume) * (maxRadius - minRadius))
  }
  
  // Generate path for price line
  const pathData = dataPoints
    .map((d, idx) => `${idx === 0 ? 'M' : 'L'} ${scaleX(idx)} ${scaleY(d.price)}`)
    .join(' ')
  
  return (
    <div className="volav-mini-chart">
      <svg width={chartWidth} height={chartHeight + 60} className="chart-svg">
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const price = minPrice - pricePadding + (priceRange + pricePadding * 2) * (1 - ratio)
          const y = scaleY(price)
          return (
            <g key={ratio}>
              <line
                x1={chartPadding.left}
                y1={y}
                x2={chartWidth - chartPadding.right}
                y2={y}
                stroke="#e0e0e0"
                strokeWidth="1"
                strokeDasharray="2,2"
              />
              <text
                x={chartPadding.left - 10}
                y={y + 4}
                textAnchor="end"
                fontSize="10"
                fill="#000"
              >
                ${formatNumber(price, 2)}
              </text>
            </g>
          )
        })}
        
        {/* Volume bars */}
        {dataPoints.map((d, idx) => {
          const barHeight = scaleVolume(d.volume)
          const x = scaleX(idx) - 8
          const y = chartHeight - chartPadding.bottom
          return (
            <rect
              key={`vol-${idx}`}
              x={x}
              y={y - barHeight}
              width="16"
              height={barHeight}
              fill="#007bff"
              opacity="0.3"
              className="volume-bar"
            />
          )
        })}
        
        {/* Price line */}
        <path
          d={pathData}
          fill="none"
          stroke="#007bff"
          strokeWidth="2"
          className="price-line"
        />
        
        {/* Data points - Volume-proportional spheres */}
        {dataPoints.map((d, idx) => {
          const x = scaleX(idx)
          const y = scaleY(d.price)
          const prevPrice = idx > 0 ? dataPoints[idx - 1].price : d.price
          const isUp = d.price > prevPrice
          const isDown = d.price < prevPrice
          const sphereRadius = scaleSphereRadius(d.volume)
          
          return (
            <g key={`point-${idx}`} className="data-point-group">
              {/* Outer glow for larger volumes */}
              {d.volume > maxVolume * 0.5 && (
                <circle
                  cx={x}
                  cy={y}
                  r={sphereRadius + 2}
                  fill={isUp ? '#28a745' : isDown ? '#dc3545' : '#007bff'}
                  opacity="0.2"
                />
              )}
              {/* Main sphere */}
              <circle
                cx={x}
                cy={y}
                r={sphereRadius}
                fill={isUp ? '#28a745' : isDown ? '#dc3545' : '#007bff'}
                stroke="white"
                strokeWidth={sphereRadius > 8 ? 3 : 2}
                className="data-point volav-sphere"
                style={{
                  filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.3))'
                }}
              />
              {/* Tooltip on hover */}
              <g className="tooltip-group" opacity="0">
                <rect
                  x={x - 60}
                  y={y - 65}
                  width="120"
                  height="55"
                  fill="rgba(0,0,0,0.85)"
                  rx="4"
                />
                <text
                  x={x}
                  y={y - 45}
                  textAnchor="middle"
                  fontSize="11"
                  fill="white"
                  fontWeight="600"
                >
                  ${formatNumber(d.price, 2)}
                </text>
                <text
                  x={x}
                  y={y - 30}
                  textAnchor="middle"
                  fontSize="9"
                  fill="#fff"
                >
                  Hacim: {formatNumber(d.volume, 0)}
                </text>
                <text
                  x={x}
                  y={y - 15}
                  textAnchor="middle"
                  fontSize="8"
                  fill="#fff"
                >
                  {formatTimestamp(d.timestamp)}
                </text>
              </g>
            </g>
          )
        })}
        
        {/* X-axis labels */}
        {dataPoints.map((d, idx) => {
          const x = scaleX(idx)
          return (
            <g key={`label-${idx}`}>
              <line
                x1={x}
                y1={chartHeight - chartPadding.bottom}
                x2={x}
                y2={chartHeight - chartPadding.bottom + 5}
                stroke="#333"
                strokeWidth="1"
              />
              <text
                x={x}
                y={chartHeight - chartPadding.bottom + 20}
                textAnchor="middle"
                fontSize="9"
                fill="#000"
              >
                W{d.windowIndex + 1}
              </text>
              <text
                x={x}
                y={chartHeight - chartPadding.bottom + 32}
                textAnchor="middle"
                fontSize="8"
                fill="#000"
              >
                {formatTimestampShort ? formatTimestampShort(d.timestamp) : formatTimestamp(d.timestamp)}
              </text>
            </g>
          )
        })}
      </svg>
      
      {/* Legend */}
      <div className="chart-legend">
        <div className="legend-item">
          <span className="legend-color" style={{background: '#007bff'}}></span>
          <span>Fiyat Çizgisi</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{background: '#007bff', opacity: 0.3}}></span>
          <span>Hacim (Bar)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{background: '#28a745'}}></span>
          <span>Yükseliş</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{background: '#dc3545'}}></span>
          <span>Düşüş</span>
        </div>
      </div>
    </div>
  )
}

function TruthTicksInspector({ symbol, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('summary')

  useEffect(() => {
    if (!symbol) return

    setLoading(true)
    setError(null)

    fetch(`${API_BASE}/truth-ticks/inspect?symbol=${encodeURIComponent(symbol)}`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`)
        }
        return res.json()
      })
      .then(result => {
        if (result.success && result.data) {
          setData(result.data)
        } else {
          setError('No data available')
        }
      })
      .catch(err => {
        setError(err.message)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [symbol])

  const formatNumber = (val, decimals = 2) => {
    if (val == null || val === undefined) return 'N/A'
    return typeof val === 'number' ? val.toFixed(decimals) : val
  }

  const formatPercent = (val) => {
    if (val == null || val === undefined) return 'N/A'
    return typeof val === 'number' ? `${val.toFixed(1)}%` : val
  }

  const formatTimestamp = (ts) => {
    if (!ts) return 'N/A'
    try {
      const date = new Date(ts * 1000)
      return date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return String(ts)
    }
  }
  
  const formatTimestampShort = (ts) => {
    if (!ts) return 'N/A'
    try {
      const date = new Date(ts * 1000)
      return date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    } catch {
      return String(ts)
    }
  }
  
  const formatDate = (ts) => {
    if (!ts) return 'N/A'
    try {
      const date = new Date(ts * 1000)
      return date.toLocaleDateString('tr-TR', { year: 'numeric', month: '2-digit', day: '2-digit' })
    } catch {
      return String(ts)
    }
  }
  
  const formatDateTime = (ts) => {
    if (!ts) return 'N/A'
    try {
      const date = new Date(ts * 1000)
      return date.toLocaleString('tr-TR', { 
        year: 'numeric', 
        month: '2-digit', 
        day: '2-digit',
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit' 
      })
    } catch {
      return String(ts)
    }
  }
  
  const calculateTimeframe = (timeline) => {
    if (!timeline || timeline.length === 0) return null
    
    const firstWindow = timeline[0]
    const lastWindow = timeline[timeline.length - 1]
    
    if (!firstWindow.start_timestamp || !lastWindow.end_timestamp) return null
    
    const startTime = firstWindow.start_timestamp
    const endTime = lastWindow.end_timestamp
    const durationSeconds = endTime - startTime
    
    const days = Math.floor(durationSeconds / 86400)
    const hours = Math.floor((durationSeconds % 86400) / 3600)
    const minutes = Math.floor((durationSeconds % 3600) / 60)
    const seconds = durationSeconds % 60
    
    return {
      start: startTime,
      end: endTime,
      durationSeconds,
      days,
      hours,
      minutes,
      seconds,
      formatted: days > 0 
        ? `${days} gün ${hours} saat ${minutes} dakika`
        : hours > 0
        ? `${hours} saat ${minutes} dakika`
        : `${minutes} dakika ${seconds} saniye`
    }
  }

  if (loading) {
    return (
      <div className="truth-ticks-inspector">
        <div className="inspector-header">
          <h2>Truth Ticks Inspector: {symbol}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>
        <div className="inspector-content loading">
          <div>Loading inspection data...</div>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="truth-ticks-inspector">
        <div className="inspector-header">
          <h2>Truth Ticks Inspector: {symbol}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>
        <div className="inspector-content error">
          <div>Error: {error || 'No data available'}</div>
        </div>
      </div>
    )
  }

  const { summary, filtering_report, volav_details, time_segmentation, path_dataset, overlay_bands, markers, volav_timeline } = data

  return (
    <div className="truth-ticks-inspector">
      <div className="inspector-header">
        <h2>Truth Ticks Inspector: {symbol}</h2>
        <button onClick={onClose} className="close-btn">×</button>
      </div>

      <div className="inspector-tabs">
        <button
          className={activeTab === 'summary' ? 'active' : ''}
          onClick={() => setActiveTab('summary')}
        >
          Summary
        </button>
        <button
          className={activeTab === 'filtering' ? 'active' : ''}
          onClick={() => setActiveTab('filtering')}
        >
          Filtering Report
        </button>
        <button
          className={activeTab === 'volav' ? 'active' : ''}
          onClick={() => setActiveTab('volav')}
        >
          Volav Details
        </button>
        <button
          className={activeTab === 'segmentation' ? 'active' : ''}
          onClick={() => setActiveTab('segmentation')}
        >
          Time Segmentation
        </button>
        <button
          className={activeTab === 'timeline' ? 'active' : ''}
          onClick={() => setActiveTab('timeline')}
        >
          Volav Inspector
        </button>
        <button
          className={activeTab === 'chart' ? 'active' : ''}
          onClick={() => setActiveTab('chart')}
        >
          Price-Time Chart
        </button>
      </div>

      <div className="inspector-content">
        {activeTab === 'summary' && (
          <div className="tab-content">
            <h3>Summary Metrics</h3>
            <div className="metrics-grid">
              <div className="metric-item">
                <label>Symbol:</label>
                <span>{summary.symbol}</span>
              </div>
              <div className="metric-item">
                <label>AVG ADV:</label>
                <span>{formatNumber(summary.avg_adv, 0)}</span>
              </div>
              {volav_timeline && volav_timeline.length > 0 && (() => {
                const timeframe = calculateTimeframe(volav_timeline)
                return timeframe ? (
                  <>
                    <div className="metric-item">
                      <label>Timeframe (100 Truth Ticks):</label>
                      <span>{timeframe.formatted}</span>
                    </div>
                    <div className="metric-item">
                      <label>Başlangıç:</label>
                      <span>{formatDateTime(timeframe.start)}</span>
                    </div>
                    <div className="metric-item">
                      <label>Bitiş:</label>
                      <span>{formatDateTime(timeframe.end)}</span>
                    </div>
                    <div className="metric-item">
                      <label>Window Sayısı:</label>
                      <span>{volav_timeline.length}</span>
                    </div>
                  </>
                ) : null
              })()}
              <div className="metric-item">
                <label>Min Volav Gap:</label>
                <span>${formatNumber(summary.min_volav_gap_used)}</span>
              </div>
              <div className="metric-item">
                <label>Truth Ticks (150):</label>
                <span>{summary.truth_tick_count_150}</span>
              </div>
              <div className="metric-item">
                <label>Truth Ticks (100):</label>
                <span>{summary.truth_tick_count_100}</span>
              </div>
              <div className="metric-item">
                <label>Truth Volume (200):</label>
                <span>{formatNumber(summary.truth_volume_200, 0)}</span>
              </div>
              <div className="metric-item">
                <label>Truth Volume (100):</label>
                <span>{formatNumber(summary.truth_volume_100, 0)}</span>
              </div>
              <div className="metric-item">
                <label>ADV Fraction (100):</label>
                <span>{formatPercent((summary.truth_adv_fraction_100 || 0) * 100)}</span>
              </div>
              <div className="metric-item">
                <label>State:</label>
                <span className={`state-badge state-${summary.state?.toLowerCase()}`}>
                  {summary.state}
                </span>
              </div>
              <div className="metric-item">
                <label>State Confidence:</label>
                <span>{formatPercent((summary.state_confidence || 0) * 100)}</span>
              </div>
              <div className="metric-item">
                <label>Volav1 Start:</label>
                <span>${formatNumber(summary.volav1_start_price, 2)}</span>
              </div>
              <div className="metric-item">
                <label>Volav1 End:</label>
                <span>${formatNumber(summary.volav1_end_price, 2)}</span>
              </div>
              <div className="metric-item">
                <label>Volav Shift:</label>
                <span className={summary.volav_shift > 0 ? 'positive' : summary.volav_shift < 0 ? 'negative' : ''}>
                  ${formatNumber(summary.volav_shift, 2)}
                </span>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'filtering' && (
          <div className="tab-content">
            <h3>Filtering Report</h3>
            <div className="filtering-report">
              <div className="report-item">
                <label>Last 200 Raw Ticks:</label>
                <span>{filtering_report.last_200_raw_ticks_count}</span>
              </div>
              <div className="report-item">
                <label>Excluded (Size &lt; 19):</label>
                <span className="excluded">{filtering_report.excluded_small_size_count}</span>
              </div>
              <div className="report-item">
                <label>Excluded (FNRA non-100/200):</label>
                <span className="excluded">{filtering_report.excluded_fnra_non_100_200_count}</span>
              </div>
              <div className="report-item">
                <label>Included (Non-FNRA):</label>
                <span className="included">{filtering_report.included_non_fnra_count}</span>
              </div>
              <div className="report-item">
                <label>Included (FNRA 100/200):</label>
                <span className="included">{filtering_report.included_fnra_100_200_count}</span>
              </div>
              <div className="report-item">
                <label>Total Truth Ticks (200):</label>
                <span className="included">{filtering_report.total_truth_ticks_200}</span>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'volav' && (
          <div className="tab-content">
            <h3>Volav Levels</h3>
            <div className="volav-levels">
              {volav_details.volavs.map(volav => (
                <div key={volav.rank} className="volav-item">
                  <div className="volav-rank">Volav{volav.rank}</div>
                  <div className="volav-details">
                    <div>Price: ${formatNumber(volav.price, 2)}</div>
                    <div>Volume: {formatNumber(volav.volume, 0)}</div>
                    <div>% of Truth Volume: {formatPercent(volav.pct_of_truth_volume)}</div>
                    <div>Tick Count: {volav.tick_count}</div>
                  </div>
                </div>
              ))}
            </div>

            <h4>Top 10 Buckets (by Volume)</h4>
            <table className="buckets-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Price</th>
                  <th>Volume</th>
                  <th>%</th>
                  <th>Ticks</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {volav_details.top_buckets.map((bucket, idx) => {
                  const isSelected = volav_details.volavs.some(v => v.bucket_key === bucket.bucket_key)
                  const isSkipped = volav_details.skipped_buckets.some(s => s.bucket_key === bucket.bucket_key)
                  return (
                    <tr key={idx} className={isSelected ? 'selected' : isSkipped ? 'skipped' : ''}>
                      <td>{idx + 1}</td>
                      <td>${formatNumber(bucket.price, 2)}</td>
                      <td>{formatNumber(bucket.volume, 0)}</td>
                      <td>{formatPercent(bucket.pct_of_truth_volume)}</td>
                      <td>{bucket.tick_count}</td>
                      <td>
                        {isSelected ? '✓ Selected' : isSkipped ? '⚠ Skipped (gap)' : ''}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {volav_details.skipped_buckets.length > 0 && (
              <>
                <h4>Skipped Buckets (Gap Rule)</h4>
                <div className="skipped-buckets">
                  {volav_details.skipped_buckets.map((bucket, idx) => (
                    <div key={idx} className="skipped-item">
                      <div>Price: ${formatNumber(bucket.price, 2)}</div>
                      <div>Volume: {formatNumber(bucket.volume, 0)}</div>
                      <div className="reason">{bucket.skipped_reason}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'segmentation' && (
          <div className="tab-content">
            <h3>Time Segmentation</h3>
            <div className="segmentation">
              <div className="half-segment">
                <h4>First Half</h4>
                {time_segmentation.first_half ? (
                  <>
                    <div>Tick Count: {time_segmentation.first_half.tick_count}</div>
                    <div>Volume: {formatNumber(time_segmentation.first_half.volume, 0)}</div>
                    {time_segmentation.first_half.volav1 && (
                      <div>
                        <strong>Volav1 Start:</strong> ${formatNumber(time_segmentation.first_half.volav1.price, 2)}
                        <br />
                        <small>Volume: {formatNumber(time_segmentation.first_half.volav1.volume, 0)}, 
                        %: {formatPercent(time_segmentation.first_half.volav1.pct_of_truth_volume)}</small>
                      </div>
                    )}
                  </>
                ) : (
                  <div>No data</div>
                )}
              </div>
              <div className="half-segment">
                <h4>Second Half</h4>
                {time_segmentation.second_half ? (
                  <>
                    <div>Tick Count: {time_segmentation.second_half.tick_count}</div>
                    <div>Volume: {formatNumber(time_segmentation.second_half.volume, 0)}</div>
                    {time_segmentation.second_half.volav1 && (
                      <div>
                        <strong>Volav1 End:</strong> ${formatNumber(time_segmentation.second_half.volav1.price, 2)}
                        <br />
                        <small>Volume: {formatNumber(time_segmentation.second_half.volav1.volume, 0)}, 
                        %: {formatPercent(time_segmentation.second_half.volav1.pct_of_truth_volume)}</small>
                      </div>
                    )}
                  </>
                ) : (
                  <div>No data</div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="tab-content">
            <h3>Volav Inspector - Timeframe & Window Analysis</h3>
            
            {/* Timeframe Summary */}
            {volav_timeline && volav_timeline.length > 0 && (() => {
              const timeframe = calculateTimeframe(volav_timeline)
              return timeframe ? (
                <div className="timeframe-summary" style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f5f5f5', borderRadius: '5px' }}>
                  <h4>Timeframe Bilgisi (100 Truth Tick)</h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginTop: '10px' }}>
                    <div><strong>AVG ADV:</strong> {formatNumber(summary.avg_adv, 0)}</div>
                    <div><strong>Window Sayısı:</strong> {volav_timeline.length}</div>
                    <div><strong>Süre:</strong> {timeframe.formatted}</div>
                    <div><strong>Başlangıç:</strong> {formatDateTime(timeframe.start)}</div>
                    <div><strong>Bitiş:</strong> {formatDateTime(timeframe.end)}</div>
                    <div><strong>Toplam Truth Tick:</strong> {summary.truth_tick_count_100}</div>
                  </div>
                </div>
              ) : null
            })()}
            
            {/* Timeframe Summary */}
            {volav_timeline && volav_timeline.length > 0 && (() => {
              const timeframe = calculateTimeframe(volav_timeline)
              return timeframe ? (
                <div className="timeframe-summary" style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f5f5f5', borderRadius: '5px' }}>
                  <h4>Timeframe Bilgisi (100 Truth Tick)</h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginTop: '10px' }}>
                    <div><strong>AVG ADV:</strong> {formatNumber(summary.avg_adv, 0)}</div>
                    <div><strong>Window Sayısı:</strong> {volav_timeline.length}</div>
                    <div><strong>Süre:</strong> {timeframe.formatted}</div>
                    <div><strong>Başlangıç:</strong> {formatDateTime(timeframe.start)}</div>
                    <div><strong>Bitiş:</strong> {formatDateTime(timeframe.end)}</div>
                    <div><strong>Toplam Truth Tick:</strong> {summary.truth_tick_count_100}</div>
                  </div>
                </div>
              ) : null
            })()}
            
            <h4>Volav Mini Charts</h4>
            {volav_timeline && volav_timeline.length > 0 ? (
              <div className="volav-inspector-container">
                {/* Mini Chart - Volav1 Evolution */}
                <div className="mini-chart-section">
                  <h4>Volav1 Timeline</h4>
                    <VolavMiniChart timeline={volav_timeline} volavType="volav1" formatNumber={formatNumber} formatTimestamp={formatTimestamp} formatTimestampShort={formatTimestampShort} />
                </div>

                {/* Mini Chart - Volav2 Evolution */}
                {volav_timeline.some(w => w.volav2) && (
                  <div className="mini-chart-section">
                    <h4>Volav2 Timeline</h4>
                    <VolavMiniChart timeline={volav_timeline} volavType="volav2" formatNumber={formatNumber} formatTimestamp={formatTimestamp} formatTimestampShort={formatTimestampShort} />
                  </div>
                )}

                {/* Detailed Table */}
                <div className="timeline-details-table">
                  <h4>Detaylı Bilgiler</h4>
                  <table className="timeline-table">
                    <thead>
                      <tr>
                        <th>Window</th>
                        <th>Tarih</th>
                        <th>Zaman Aralığı</th>
                        <th>Truth Tick</th>
                        <th>Volume</th>
                        <th>Volav1</th>
                        <th>Volav2</th>
                        <th>Volav3</th>
                        <th>Volav4</th>
                      </tr>
                    </thead>
                    <tbody>
                      {volav_timeline.map((window, idx) => {
                        const volav1Data = window.volav_levels?.find(v => v.rank === 1)
                        const volav2Data = window.volav_levels?.find(v => v.rank === 2)
                        const volav3Data = window.volav_levels?.find(v => v.rank === 3)
                        const volav4Data = window.volav_levels?.find(v => v.rank === 4)
                        
                        // Calculate window duration
                        const windowDuration = window.end_timestamp && window.start_timestamp 
                          ? window.end_timestamp - window.start_timestamp 
                          : 0
                        const windowMinutes = Math.floor(windowDuration / 60)
                        const windowSeconds = windowDuration % 60
                        
                        return (
                          <tr key={idx} className={idx === 0 ? 'first-window' : idx === volav_timeline.length - 1 ? 'last-window' : ''}>
                            <td><strong>W{window.window_index + 1}</strong></td>
                            <td>
                              {window.start_timestamp ? formatDate(window.start_timestamp) : 'N/A'}
                            </td>
                            <td>
                              {window.start_timestamp && window.end_timestamp ? (
                                <>
                                  {formatTimestamp(window.start_timestamp)} → {formatTimestamp(window.end_timestamp)}
                                  <br />
                                  <small style={{ color: '#666' }}>({windowMinutes}dk {windowSeconds}sn)</small>
                                </>
                              ) : 'N/A'}
                            </td>
                            <td><strong>{window.tick_count || 0}</strong></td>
                            <td><strong>{formatNumber(window.volume || 0, 0)}</strong></td>
                            <td className={window.volav1 ? 'volav-price' : ''}>
                              {window.volav1 ? (
                                <>
                                  <strong>${formatNumber(window.volav1, 2)}</strong>
                                  {volav1Data && (
                                    <div className="volav-volume-info">
                                      <small>Vol: {formatNumber(volav1Data.volume, 0)} ({formatPercent(volav1Data.pct_of_truth_volume)})</small>
                                    </div>
                                  )}
                                </>
                              ) : '-'}
                            </td>
                            <td className={window.volav2 ? 'volav-price' : ''}>
                              {window.volav2 ? (
                                <>
                                  <strong>${formatNumber(window.volav2, 2)}</strong>
                                  {volav2Data && (
                                    <div className="volav-volume-info">
                                      <small>Vol: {formatNumber(volav2Data.volume, 0)} ({formatPercent(volav2Data.pct_of_truth_volume)})</small>
                                    </div>
                                  )}
                                </>
                              ) : '-'}
                            </td>
                            <td className={window.volav3 ? 'volav-price' : ''}>
                              {window.volav3 ? (
                                <>
                                  <strong>${formatNumber(window.volav3, 2)}</strong>
                                  {volav3Data && (
                                    <div className="volav-volume-info">
                                      <small>Vol: {formatNumber(volav3Data.volume, 0)} ({formatPercent(volav3Data.pct_of_truth_volume)})</small>
                                    </div>
                                  )}
                                </>
                              ) : '-'}
                            </td>
                            <td className={window.volav4 ? 'volav-price' : ''}>
                              {window.volav4 ? (
                                <>
                                  <strong>${formatNumber(window.volav4, 2)}</strong>
                                  {volav4Data && (
                                    <div className="volav-volume-info">
                                      <small>Vol: {formatNumber(volav4Data.volume, 0)} ({formatPercent(volav4Data.pct_of_truth_volume)})</small>
                                    </div>
                                  )}
                                </>
                              ) : '-'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="no-data">No timeline data available</div>
            )}
          </div>
        )}

        {activeTab === 'chart' && (
          <div className="tab-content">
            <h3>Price-Time-Volume Path</h3>
            <div className="chart-container">
              {path_dataset && path_dataset.length > 0 ? (
                <PriceTimeChart 
                  data={path_dataset} 
                  overlayBands={overlay_bands} 
                  markers={markers}
                  buckets={volav_details?.top_buckets || []}
                  formatNumber={formatNumber}
                  formatTimestamp={formatTimestamp}
                />
              ) : (
                <div className="chart-placeholder">
                  <p>No chart data available</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default TruthTicksInspector


