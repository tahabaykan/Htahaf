import React, { useState, useEffect } from 'react'
import './EngineStatusPanel.css'

function EngineStatusPanel() {
    const [diagnostic, setDiagnostic] = useState(null)
    const [loading, setLoading] = useState(false)
    const [expanded, setExpanded] = useState(false)
    const [error, setError] = useState(null)

    useEffect(() => {
        if (expanded) {
            loadDiagnostic()
            const interval = setInterval(loadDiagnostic, 10000)  // Every 10s
            return () => clearInterval(interval)
        }
    }, [expanded])

    const loadDiagnostic = async () => {
        try {
            setLoading(true)
            setError(null)
            const response = await fetch('/api/psfalgo/engines/diagnostic')
            const data = await response.json()
            if (data.success) {
                setDiagnostic(data.diagnostic)
            } else {
                setError('Failed to load diagnostic data')
            }
        } catch (err) {
            console.error('[ENGINE STATUS] Load error:', err)
            setError(`Error: ${err.message}`)
        } finally {
            setLoading(false)
        }
    }

    if (!expanded) {
        return (
            <div className="engine-status-collapsed" onClick={() => setExpanded(true)}>
                <span className="expand-icon">▶</span>
                <span>Engine Diagnostics</span>
                <span className="hint">(Click to expand)</span>
            </div>
        )
    }

    return (
        <div className="engine-status-panel">
            <div className="engine-status-header" onClick={() => setExpanded(false)}>
                <span className="expand-icon">▼</span>
                <h3>Engine Status & Diagnostics</h3>
                {loading && <span className="loading-indicator">Loading...</span>}
            </div>

            {error && (
                <div className="error-message">
                    {error}
                </div>
            )}

            {diagnostic && (
                <div className="engine-status-content">
                    {/* RUNALL Status */}
                    <div className="engine-group">
                        <h4>🎯 RUNALL Orchestrator</h4>
                        <div className="status-row">
                            <span className="label">Running:</span>
                            <span className={diagnostic.runall.loop_running ? 'status-active' : 'status-inactive'}>
                                {diagnostic.runall.loop_running ? '🟢 Active' : '🔴 Stopped'}
                            </span>
                        </div>
                        <div className="status-row">
                            <span className="label">Cycle Count:</span>
                            <span className="value">{diagnostic.runall.loop_count}</span>
                        </div>
                        <div className="status-row">
                            <span className="label">Active Engines:</span>
                            <span className="value">{diagnostic.runall.active_engines.join(', ') || 'None'}</span>
                        </div>
                    </div>

                    {/* KARBOTU Status */}
                    <div className="engine-group">
                        <h4>📊 KARBOTU Engine</h4>
                        <div className="status-row">
                            <span className="label">Status:</span>
                            <span className={diagnostic.karbotu.status === 'ENABLED' ? 'status-enabled' : 'status-disabled'}>
                                {diagnostic.karbotu.status}
                            </span>
                        </div>
                        {diagnostic.karbotu.last_diagnostic ? (
                            <>
                                <div className="status-row">
                                    <span className="label">Positions Analyzed:</span>
                                    <span className="value">{diagnostic.karbotu.last_diagnostic.positions_analyzed}</span>
                                </div>
                                <div className="status-row">
                                    <span className="label">Eligible:</span>
                                    <span className="value highlight">
                                        {diagnostic.karbotu.last_diagnostic.eligible_count}/{diagnostic.karbotu.last_diagnostic.positions_analyzed}
                                    </span>
                                </div>
                                <div className="status-row">
                                    <span className="label">Triggered:</span>
                                    <span className="value highlight">
                                        {diagnostic.karbotu.last_diagnostic.triggered_count}/{diagnostic.karbotu.last_diagnostic.positions_analyzed}
                                    </span>
                                </div>
                                <div className="status-row">
                                    <span className="label">Intents Generated:</span>
                                    <span className={diagnostic.karbotu.last_diagnostic.intent_generated === 0 ? 'value warning' : 'value success'}>
                                        {diagnostic.karbotu.last_diagnostic.intent_generated}
                                        {diagnostic.karbotu.last_diagnostic.intent_generated === 0 ? ' ⚠️' : ' ✅'}
                                    </span>
                                </div>

                                {/* Blocking Summary */}
                                <div className="blocking-summary">
                                    <strong>Blocking Reasons:</strong>
                                    <ul>
                                        {diagnostic.karbotu.last_diagnostic.blocked_by_gort > 0 && (
                                            <li>GORT: {diagnostic.karbotu.last_diagnostic.blocked_by_gort}</li>
                                        )}
                                        {diagnostic.karbotu.last_diagnostic.blocked_by_too_cheap > 0 && (
                                            <li>Too Cheap: {diagnostic.karbotu.last_diagnostic.blocked_by_too_cheap}</li>
                                        )}
                                        {diagnostic.karbotu.last_diagnostic.blocked_by_too_expensive > 0 && (
                                            <li>Too Expensive: {diagnostic.karbotu.last_diagnostic.blocked_by_too_expensive}</li>
                                        )}
                                        {diagnostic.karbotu.last_diagnostic.no_metrics > 0 && (
                                            <li>No Metrics: {diagnostic.karbotu.last_diagnostic.no_metrics}</li>
                                        )}
                                    </ul>
                                </div>

                                {/* Blocking Details */}
                                {diagnostic.karbotu.last_diagnostic.blocking_details && diagnostic.karbotu.last_diagnostic.blocking_details.length > 0 && (
                                    <div className="blocking-details">
                                        <strong>Top Blockers:</strong>
                                        <ul>
                                            {diagnostic.karbotu.last_diagnostic.blocking_details.slice(0, 3).map((b, i) => (
                                                <li key={i}>
                                                    <code>{b.symbol}</code> ({b.side}): {b.reason}
                                                    <br />
                                                    <small>
                                                        Value: {b.gort || b.ask_sell_pahalilik || b.bid_buy_ucuzluk},
                                                        Threshold: {b.threshold}
                                                    </small>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </>
                        ) : (
                            <div className="no-data">No diagnostic data yet</div>
                        )}
                    </div>

                    {/* REDUCEMORE Status */}
                    <div className="engine-group">
                        <h4>🛡️ REDUCEMORE Engine</h4>
                        <div className="status-row">
                            <span className="label">Status:</span>
                            <span className={diagnostic.reducemore.status === 'ENABLED' ? 'status-enabled' : 'status-disabled'}>
                                {diagnostic.reducemore.status}
                            </span>
                        </div>
                        {diagnostic.reducemore.last_diagnostic ? (
                            <>
                                <div className="status-row">
                                    <span className="label">Exposure Ratio:</span>
                                    <span className="value highlight">
                                        {(diagnostic.reducemore.last_diagnostic.exposure_ratio * 100).toFixed(1)}%
                                    </span>
                                </div>
                                <div className="status-row">
                                    <span className="label">Threshold:</span>
                                    <span className="value">
                                        {(diagnostic.reducemore.last_diagnostic.threshold * 100).toFixed(1)}%
                                    </span>
                                </div>
                                <div className="status-row">
                                    <span className="label">Regime:</span>
                                    <span className={`regime regime-${diagnostic.reducemore.last_diagnostic.regime.toLowerCase()}`}>
                                        {diagnostic.reducemore.last_diagnostic.regime}
                                    </span>
                                </div>
                                <div className="status-row">
                                    <span className="label">Multiplier:</span>
                                    <span className="value">{diagnostic.reducemore.last_diagnostic.base_multiplier}x</span>
                                </div>
                                <div className="status-row">
                                    <span className="label">Triggered:</span>
                                    <span className={diagnostic.reducemore.last_diagnostic.triggered ? 'status-active' : 'status-inactive'}>
                                        {diagnostic.reducemore.last_diagnostic.triggered ? '✅ Yes' : '❌ No'}
                                    </span>
                                </div>
                                {diagnostic.reducemore.last_diagnostic.trigger_reason && diagnostic.reducemore.last_diagnostic.trigger_reason.length > 0 && (
                                    <div className="trigger-reasons">
                                        <strong>Trigger Reasons:</strong>
                                        <ul>
                                            {diagnostic.reducemore.last_diagnostic.trigger_reason.map((r, i) => (
                                                <li key={i}>{r}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                                <div className="status-row">
                                    <span className="label">Intents Generated:</span>
                                    <span className={diagnostic.reducemore.last_diagnostic.intent_generated === 0 ? 'value warning' : 'value success'}>
                                        {diagnostic.reducemore.last_diagnostic.intent_generated}
                                        {diagnostic.reducemore.last_diagnostic.intent_generated === 0 ? ' ⚠️' : ' ✅'}
                                    </span>
                                </div>
                            </>
                        ) : (
                            <div className="no-data">No diagnostic data yet</div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

export default EngineStatusPanel
