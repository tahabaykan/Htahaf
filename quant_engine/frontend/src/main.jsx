import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter, Routes, Route } from 'react-router-dom'
import ScannerPage from './pages/ScannerPage'
import PSFALGOPage from './pages/PSFALGOPage'
import TradingPositions from './pages/TradingPositions'
import TradingOrders from './pages/TradingOrders'
import TradingExposure from './pages/TradingExposure'
import PortAdjusterPage from './pages/PortAdjusterPage'
import TickerAlertsPage from './pages/TickerAlertsPage'
import PSFALGOIntentionsPage from './pages/PSFALGOIntentionsPage'
import PSFALGORulesPage from './pages/PSFALGORulesPage'
import DeeperAnalysisPage from './pages/DeeperAnalysisPage'
import DecisionHelperPage from './pages/DecisionHelperPage'
import DecisionHelperV2Page from './pages/DecisionHelperV2Page'
import TruthTicksPage from './pages/TruthTicksPage'
import AuraMMPage from './pages/AuraMMPage'
import LogViewerPage from './pages/LogViewerPage'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <Routes>
        <Route path="/" element={<ScannerPage />} />
        <Route path="/scanner" element={<ScannerPage />} />
        <Route path="/psfalgo" element={<PSFALGOPage />} />
        <Route path="/trading/positions" element={<TradingPositions />} />
        <Route path="/trading/orders" element={<TradingOrders />} />
        <Route path="/trading/exposure" element={<TradingExposure />} />
        <Route path="/port-adjuster" element={<PortAdjusterPage />} />
        <Route path="/ticker-alerts" element={<TickerAlertsPage />} />
        <Route path="/psfalgo-intentions" element={<PSFALGOIntentionsPage />} />
        <Route path="/psfalgo-rules" element={<PSFALGORulesPage />} />
        <Route path="/deeper-analysis" element={<DeeperAnalysisPage />} />
        <Route path="/decision-helper" element={<DecisionHelperPage />} />
        <Route path="/decision-helper-v2" element={<DecisionHelperV2Page />} />
        <Route path="/truth-ticks" element={<TruthTicksPage />} />
        <Route path="/aura-mm" element={<AuraMMPage />} />
        <Route path="/logs" element={<LogViewerPage />} />
      </Routes>
    </HashRouter>
  </React.StrictMode>
)
