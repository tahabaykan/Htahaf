import React, { useState, useEffect } from 'react'
import TradingPanels from './TradingPanels'
import './TradingPanelsOverlay.css'

function TradingPanelsOverlay({ isOpen, onClose, tradingMode, panelType = 'positions' }) {
  const [activeTab, setActiveTab] = useState(panelType)

  useEffect(() => {
    setActiveTab(panelType)
  }, [panelType])

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
    if (mode === 'HAMMER_TRADING') return 'Hammer Pro'
    if (mode === 'IBKR_PED') return 'IBKR PED'
    if (mode === 'IBKR_GUN') return 'IBKR GUN (Live)'
    return mode.replace('_', ' ')
  }

  return (
    <>
      {/* Backdrop */}
      <div className="trading-overlay-backdrop" onClick={onClose} />

      {/* Overlay Panel */}
      <div className="trading-overlay-panel">
        <div className="trading-overlay-header">
          <h2>Trading Account: {getModeLabel(tradingMode)}</h2>
          <button className="close-button" onClick={onClose} title="Close (Esc)">
            ×
          </button>
        </div>

        <div className="trading-overlay-content">
          <TradingPanels
            tradingMode={tradingMode}
            initialTab={activeTab}
            onTabChange={setActiveTab}
          />
        </div>
      </div>
    </>
  )
}

export default TradingPanelsOverlay
