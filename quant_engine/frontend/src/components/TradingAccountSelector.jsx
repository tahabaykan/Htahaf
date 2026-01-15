import React, { useState, useEffect } from 'react'
import './TradingAccountSelector.css'

function TradingAccountSelector({ onModeChange }) {
  const [accountMode, setAccountMode] = useState('HAMMER_PRO')
  const [ibkrGunConnected, setIbkrGunConnected] = useState(false)
  const [ibkrPedConnected, setIbkrPedConnected] = useState(false)
  const [hammerConnected, setHammerConnected] = useState(false)
  const [loading, setLoading] = useState(false)
  const [connectionError, setConnectionError] = useState(null)

  // Load account mode on mount
  useEffect(() => {
    fetchAccountMode()
    // Poll connection status every 5 seconds
    const interval = setInterval(fetchAccountMode, 5000)
    return () => clearInterval(interval)
  }, [])

  const fetchAccountMode = async () => {
    try {
      const response = await fetch('/api/psfalgo/account/mode')
      const result = await response.json()
      
      if (result.success) {
        setAccountMode(result.mode)
        setIbkrGunConnected(result.ibkr_gun_connected || false)
        setIbkrPedConnected(result.ibkr_ped_connected || false)
        setConnectionError(null)
        
        if (onModeChange) {
          onModeChange(result.mode)
        }
      }
      
      // Also fetch Hammer status
      try {
        const hammerResponse = await fetch('/api/psfalgo/account/hammer/status')
        const hammerResult = await hammerResponse.json()
        if (hammerResult.success) {
          setHammerConnected(hammerResult.connected || false)
        }
      } catch (err) {
        console.error('Error fetching Hammer status:', err)
      }
    } catch (err) {
      console.error('Error fetching account mode:', err)
    }
  }

  const handleModeChange = async (newMode) => {
    if (newMode === accountMode) return
    
    setLoading(true)
    setConnectionError(null)
    
    try {
      // Auto-connect is enabled by default
      const response = await fetch(`/api/psfalgo/account/mode?mode=${newMode}&auto_connect=true`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })
      
      const result = await response.json()
      
      if (result.success) {
        setAccountMode(result.new_mode)
        
        // Update connection status
        if (result.connected !== undefined) {
          if (result.new_mode === 'IBKR_GUN') {
            setIbkrGunConnected(result.connected)
          } else if (result.new_mode === 'IBKR_PED') {
            setIbkrPedConnected(result.connected)
          }
        }
        
        // Show connection error if any
        if (result.connection_error) {
          setConnectionError(result.connection_error)
          alert(`IBKR connection failed: ${result.connection_error}\n\nMake sure IBKR Gateway/TWS is running and API is enabled.`)
        } else if (result.new_mode !== 'HAMMER_PRO' && !result.connected) {
          setConnectionError('Connection failed. Check IBKR Gateway/TWS.')
        }
        
        if (onModeChange) {
          onModeChange(result.new_mode)
        }
      } else {
        alert(`Failed to switch account mode: ${result.error || 'Unknown error'}`)
      }
    } catch (err) {
      console.error('Error setting account mode:', err)
      alert('Error setting account mode. Check console for details.')
    } finally {
      setLoading(false)
    }
  }

  const getModeLabel = (mode) => {
    switch(mode) {
      case 'HAMMER_PRO': return 'HAM PRO'
      case 'IBKR_GUN': return 'IBKR GUN'
      case 'IBKR_PED': return 'IBKR PED'
      default: return mode
    }
  }

  const isModeActive = (mode) => accountMode === mode
  const isModeConnected = (mode) => {
    if (mode === 'HAMMER_PRO') return true // Hammer is always "connected" (no connection needed)
    if (mode === 'IBKR_GUN') return ibkrGunConnected
    if (mode === 'IBKR_PED') return ibkrPedConnected
    return false
  }

  const handleHammerConnect = async () => {
    setLoading(true)
    setConnectionError(null)
    
    try {
      const response = await fetch('/api/psfalgo/account/hammer/connect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })
      
      const result = await response.json()
      
      if (result.success) {
        setHammerConnected(result.connected)
        if (result.befday_tracked) {
          alert(`✅ Connected to Hammer Pro!\n\nBEFDAY tracked: ${result.positions_count} positions saved to befham.csv`)
        } else {
          alert(`✅ Connected to Hammer Pro!\n\n${result.message || 'BEFDAY already tracked today'}`)
        }
        fetchAccountMode()
      } else {
        setConnectionError(result.error || 'Failed to connect')
        alert(`❌ Failed to connect to Hammer Pro:\n\n${result.error || 'Unknown error'}`)
      }
    } catch (err) {
      console.error('Error connecting to Hammer Pro:', err)
      alert('Error connecting to Hammer Pro. Check console for details.')
    } finally {
      setLoading(false)
    }
  }

  const handleHammerDisconnect = async () => {
    setLoading(true)
    setConnectionError(null)
    
    try {
      const response = await fetch('/api/psfalgo/account/hammer/disconnect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })
      
      const result = await response.json()
      
      if (result.success) {
        setHammerConnected(false)
        alert('✅ Disconnected from Hammer Pro')
        fetchAccountMode()
      } else {
        setConnectionError(result.error || 'Failed to disconnect')
        alert(`❌ Failed to disconnect:\n\n${result.error || 'Unknown error'}`)
      }
    } catch (err) {
      console.error('Error disconnecting from Hammer Pro:', err)
      alert('Error disconnecting from Hammer Pro. Check console for details.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="trading-account-selector">
      <div className="market-data-indicator">
        <span className="indicator-label">Market Data:</span>
        <span className="indicator-value market-data-live">HAMMER (LIVE)</span>
        <div className="hammer-controls" style={{ marginLeft: '10px', display: 'inline-flex', gap: '5px' }}>
          {!hammerConnected ? (
            <button
              className="hammer-connect-btn"
              onClick={handleHammerConnect}
              disabled={loading}
              title="Connect to Hammer Pro and track BEFDAY positions"
              style={{
                padding: '4px 8px',
                fontSize: '10px',
                backgroundColor: '#4CAF50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: loading ? 'not-allowed' : 'pointer'
              }}
            >
              🔌 Connect Hammer
            </button>
          ) : (
            <button
              className="hammer-disconnect-btn"
              onClick={handleHammerDisconnect}
              disabled={loading}
              title="Disconnect from Hammer Pro"
              style={{
                padding: '4px 8px',
                fontSize: '10px',
                backgroundColor: '#f44336',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: loading ? 'not-allowed' : 'pointer'
              }}
            >
              🔌 Disconnect Hammer
            </button>
          )}
          {hammerConnected && (
            <span style={{ fontSize: '10px', color: '#4CAF50', marginLeft: '5px' }}>✓</span>
          )}
        </div>
      </div>
      
      <div className="trading-account-controls">
        <span className="control-label">Trading Account:</span>
        <div className="mode-buttons">
          <button
            className={`mode-button ${isModeActive('HAMMER_PRO') ? 'active' : ''} connected`}
            onClick={() => handleModeChange('HAMMER_PRO')}
            disabled={loading || isModeActive('HAMMER_PRO')}
            title="Hammer Pro account (default, automatic)"
          >
            HAM PRO
            {isModeActive('HAMMER_PRO') && <span className="checkmark">✓</span>}
          </button>
          
          <button
            className={`mode-button ${isModeActive('IBKR_GUN') ? 'active' : ''} ${isModeConnected('IBKR_GUN') ? 'connected' : 'disconnected'}`}
            onClick={() => handleModeChange('IBKR_GUN')}
            disabled={loading || isModeActive('IBKR_GUN')}
            title={isModeConnected('IBKR_GUN') ? 'IBKR GUN connected' : 'IBKR GUN - Click to connect (port 4001)'}
          >
            IBKR GUN
            {isModeActive('IBKR_GUN') && <span className="checkmark">✓</span>}
            {isModeConnected('IBKR_GUN') && <span className="connection-dot connected"></span>}
            {!isModeConnected('IBKR_GUN') && isModeActive('IBKR_GUN') && <span className="connection-dot disconnected"></span>}
          </button>
          
          <button
            className={`mode-button ${isModeActive('IBKR_PED') ? 'active' : ''} ${isModeConnected('IBKR_PED') ? 'connected' : 'disconnected'}`}
            onClick={() => handleModeChange('IBKR_PED')}
            disabled={loading || isModeActive('IBKR_PED')}
            title={isModeConnected('IBKR_PED') ? 'IBKR PED connected' : 'IBKR PED - Click to connect (port 4002)'}
          >
            IBKR PED
            {isModeActive('IBKR_PED') && <span className="checkmark">✓</span>}
            {isModeConnected('IBKR_PED') && <span className="connection-dot connected"></span>}
            {!isModeConnected('IBKR_PED') && isModeActive('IBKR_PED') && <span className="connection-dot disconnected"></span>}
          </button>
        </div>
        
        {connectionError && (
          <span className="connection-error" style={{ color: 'red', fontSize: '12px', marginLeft: '10px' }}>
            ⚠️ {connectionError}
          </span>
        )}
        
        {isModeActive('HAMMER_PRO') && (
          <span className="active-indicator hammer-active">
            Active: HAM PRO
          </span>
        )}
        {isModeActive('IBKR_GUN') && (
          <span className="active-indicator ibkr-active">
            Active: IBKR GUN {isModeConnected('IBKR_GUN') ? '✓' : '⚠️'}
          </span>
        )}
        {isModeActive('IBKR_PED') && (
          <span className="active-indicator ibkr-active">
            Active: IBKR PED {isModeConnected('IBKR_PED') ? '✓' : '⚠️'}
          </span>
        )}
      </div>
    </div>
  )
}

export default TradingAccountSelector



