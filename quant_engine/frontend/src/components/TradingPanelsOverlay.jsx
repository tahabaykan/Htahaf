import React, { useState, useEffect } from 'react'
import TradingPanels from './TradingPanels'
import './TradingPanelsOverlay.css'

function TradingPanelsOverlay({ isOpen, onClose, tradingMode, panelType = 'positions' }) {
  const [activeTab, setActiveTab] = useState(panelType)
  // LOCAL account state — isolated from dual process poll override
  const [localMode, setLocalMode] = useState(tradingMode || 'HAMMER_PRO')

  useEffect(() => {
    setActiveTab(panelType)
  }, [panelType])

  // Sync localMode from parent ONLY when overlay opens (not during)
  useEffect(() => {
    if (isOpen && tradingMode) {
      setLocalMode(tradingMode)
    }
  }, [isOpen]) // intentionally only on isOpen change

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return

    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, onClose])

  if (!isOpen) return null

  // Helper to format trading mode for display
  const getModeLabel = (mode) => {
    if (mode === 'HAMMER_TRADING' || mode === 'HAMMER_PRO' || mode === 'HAMPRO') return 'Hammer Pro'
    if (mode === 'IBKR_PED') return 'IBKR PED'
    if (mode === 'IBKR_GUN') return 'IBKR GUN (Live)'
    return (mode || '').replace('_', ' ')
  }

  const accountOptions = [
    { key: 'HAMPRO', label: '🟢 HAM PRO' },
    { key: 'IBKR_PED', label: '🔵 IBKR PED' },
    { key: 'IBKR_GUN', label: '🟠 IBKR GUN' },
  ]

  // Normalize for comparison (HAMMER_PRO → HAMPRO)
  const normalizedMode = (localMode === 'HAMMER_PRO' || localMode === 'HAMMER_TRADING') ? 'HAMPRO' : localMode

  return (
    <>
      {/* Backdrop */}
      <div className="trading-overlay-backdrop" onClick={onClose} />

      {/* Overlay Panel */}
      <div className="trading-overlay-panel">
        <div className="trading-overlay-header">
          <h2>Trading Account: {getModeLabel(localMode)}</h2>
          {/* Account Switcher Buttons — stays inside overlay, immune to dual process */}
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            {accountOptions.map(opt => (
              <button
                key={opt.key}
                onClick={() => setLocalMode(opt.key)}
                style={{
                  padding: '5px 12px',
                  borderRadius: '4px',
                  border: normalizedMode === opt.key ? '2px solid #60a5fa' : '1px solid #444',
                  background: normalizedMode === opt.key ? '#1e40af' : '#1e293b',
                  color: normalizedMode === opt.key ? '#fff' : '#94a3b8',
                  cursor: 'pointer',
                  fontWeight: normalizedMode === opt.key ? 'bold' : 'normal',
                  fontSize: '12px',
                  transition: 'all 0.15s ease',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button className="close-button" onClick={onClose} title="Close (Esc)">
            ×
          </button>
        </div>

        <div className="trading-overlay-content">
          <TradingPanels
            tradingMode={localMode}
            initialTab={activeTab}
            onTabChange={setActiveTab}
          />
        </div>
      </div>
    </>
  )
}

export default TradingPanelsOverlay
