import React from 'react'
import './AccountSidebar.css'

function AccountSidebar({ tradingMode, onOpenOverlay }) {
  const handleIconClick = (panelType) => {
    if (onOpenOverlay) {
      // Open overlay in same window
      onOpenOverlay(panelType)
    } else {
      // Fallback: Open in new tab using hash routing
      const currentUrl = window.location.href.split('#')[0]
      window.open(`${currentUrl}#/trading/${panelType}`, '_blank')
    }
  }

  return (
    <div className="account-sidebar">
      {/* Trading Pages Icons */}
      <div className="sidebar-section">
        <div 
          className="page-icon"
          title="Positions"
          onClick={() => handleIconClick('positions')}
        >
          📊
        </div>
        <div 
          className="page-icon"
          title="Orders"
          onClick={() => handleIconClick('orders')}
        >
          📑
        </div>
        <div 
          className="page-icon"
          title="Exposure"
          onClick={() => handleIconClick('exposure')}
        >
          ⚖️
        </div>
      </div>
      
      {/* Trading Mode Indicator */}
      <div className="sidebar-section">
        <div 
          className={`mode-indicator ${tradingMode === 'HAMMER_TRADING' ? 'hammer' : 'ibkr'}`}
          title={`${tradingMode === 'HAMMER_TRADING' ? 'Hammer' : 'IBKR'} Account`}
        >
          {tradingMode === 'HAMMER_TRADING' ? '🟢' : '🟣'}
        </div>
      </div>
    </div>
  )
}

export default AccountSidebar

