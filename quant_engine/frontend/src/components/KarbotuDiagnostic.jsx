import React, { useState, useEffect } from 'react';
import './KarbotuDiagnostic.css';

/**
 * UNIVERSAL DECISION COMPASS (Formerly Karbotu Diagnostic)
 * 
 * Shows detailed decision logic for ALL engines:
 * - LT Trim (Executive)
 * - Karbotu (Macro)
 * - Reducemore (Risk)
 * - AddNewPos (JFIN)
 */
function UniversalDecisionReport() {
    const [data, setData] = useState(null);
    const [activeTab, setActiveTab] = useState('LT_TRIM');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 5000); // 5s refresh
        return () => clearInterval(interval);
    }, []);

    const fetchData = async () => {
        try {
            const res = await fetch('/api/runall/diagnostic/universal');
            const json = await res.json();
            if (json.status === 'ok') {
                setData(json.report || {});
            } else {
                console.warn('Universal Diagnostic returned non-ok status:', json);
                if (!data) setData({}); // Ensure we don't stay in loading state
            }
        } catch (error) {
            console.error('Error fetching Universal Diagnostic:', error);
            if (!data) setData({}); // Ensure we don't stay in loading state
        }
        setLoading(false);
    };

    if (!data) return <div className="karbotu-diagnostic"><h2>Loading Universal Report...</h2></div>;

    const lt = data.lt_trim || {};
    const karbotu = data.karbotu || {};
    // const reducemore = data.reducemore || {};

    const renderLtTrimTab = () => {
        if (!lt || !lt.details) {
            return (
                <div style={{ padding: '20px', textAlign: 'center', color: '#888' }}>
                    <h3>⏳ Waiting for LT Trim Data...</h3>
                    <p>Run a cycle (Start RUNALL) to generate data.</p>
                </div>
            );
        }

        // Filter by meaningful status
        const skipped = lt.details.filter(d => d.status.startsWith('SKIP'));
        const generated = lt.details.filter(d => d.status === 'INTENT_GENERATED');
        const rejected = lt.details.filter(d => d.status === 'NO_ACTION' && !d.status.startsWith('SKIP'));

        return (
            <div className="engine-report">
                <div className="stats-grid">
                    <div className="stat-card">
                        <div className="stat-label">Analyzed</div>
                        <div className="stat-value">{lt.analyzed_count}</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-label">Generated</div>
                        <div className="stat-value highlight-success">{lt.generated_count}</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-label">Skipped (Rules)</div>
                        <div className="stat-value">{skipped.length}</div>
                    </div>
                </div>

                <h3>✅ Generated Orders ({generated.length})</h3>
                {generated.length === 0 ? <p className="empty-text">No orders generated this cycle.</p> : (
                    <table className="diagnostic-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Action</th>
                                <th>Qty</th>
                                <th>Score</th>
                                <th>Spread</th>
                                <th>Befday</th>
                                <th>Intensity</th>
                                <th>Reasons (WHY)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {generated.map((g, i) => (
                                <tr key={i} className="row-success">
                                    <td><strong>{g.symbol}</strong></td>
                                    <td>SELL</td>
                                    <td>{g.qty}</td>
                                    <td>{g.score !== null && g.score !== undefined ? g.score.toFixed(3) : 'N/A'}</td>
                                    <td>{g.debug_info?.spread ? `$${g.debug_info.spread.toFixed(2)}` : 'N/A'}</td>
                                    <td>{g.debug_info?.befday || 'N/A'}</td>
                                    <td>{g.intensity?.toFixed(2) || '1.0'}</td>
                                    <td className="reason-cell">
                                        {g.reasons && g.reasons.length > 0 ? (
                                            <div style={{ fontSize: '11px' }}>
                                                {g.reasons.map((r, idx) => <div key={idx}>✓ {r}</div>)}
                                            </div>
                                        ) : 'NO_REASON'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}

                <h3>🚫 Blocking Reasons (Detailed)</h3>
                <div className="scrollable-list">
                    <table className="diagnostic-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Status</th>
                                <th>Qty</th>
                                <th>Score (Ask_sell_pahalilik)</th>
                                <th>Spread</th>
                                <th>Befday</th>
                                <th>Why Blocked?</th>
                                <th>Threshold</th>
                            </tr>
                        </thead>
                        <tbody>
                            {lt.details.filter(d => d.status !== 'INTENT_GENERATED').map((d, i) => {
                                const score = d.debug_info?.score !== null && d.debug_info?.score !== undefined
                                    ? d.debug_info.score.toFixed(3)
                                    : 'N/A';
                                const spread = d.debug_info?.spread !== null && d.debug_info?.spread !== undefined
                                    ? `$${d.debug_info.spread.toFixed(2)}`
                                    : 'N/A';
                                const befday = d.debug_info?.befday || 'N/A';

                                // Parse reasons to show human-readable blocking info
                                let whyBlocked = 'N/A';
                                let threshold = '';
                                if (d.reasons && d.reasons.length > 0) {
                                    whyBlocked = d.reasons.join(', ');

                                    // Extract threshold from reason if present
                                    const match = whyBlocked.match(/([<>]=?\s*[-\d.]+)/);
                                    if (match) {
                                        threshold = match[1];
                                    }
                                } else if (d.status === 'NO_ACTION') {
                                    whyBlocked = 'NO_STAGES_MET';
                                }

                                return (
                                    <tr key={i}>
                                        <td className="symbol-cell">{d.symbol}</td>
                                        <td><span className={`status-badge status-${d.status}`}>{d.status}</span></td>
                                        <td>{d.qty || 0}</td>
                                        <td>{score}</td>
                                        <td>{spread}</td>
                                        <td>{befday}</td>
                                        <td className="reason-cell">{whyBlocked}</td>
                                        <td>{threshold}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    };

    const renderKarbotuTab = () => {
        if (!karbotu.total_positions) return <p>No Karbotu data available.</p>;
        const d = karbotu;
        return (
            <div className="engine-report">
                <div className="stats-grid">
                    <div className="stat-card">
                        <div className="stat-label">Analyzed</div>
                        <div className="stat-value">{d.total_positions}</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-label">Triggered</div>
                        <div className="stat-value highlight-warn">{d.triggered_count}</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-label">Generated</div>
                        <div className="stat-value highlight-success">{d.intent_generated}</div>
                    </div>
                </div>

                <h3>✅ Intents Generated ({d.blocking_details?.filter(b => b.status === 'INTENT_GENERATED').length || 0})</h3>
                {d.blocking_details && d.blocking_details.filter(b => b.status === 'INTENT_GENERATED').length > 0 ? (
                    <table className="diagnostic-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Qty</th>
                                <th>Step</th>
                                <th>GORT</th>
                                <th>FBtot</th>
                                <th>Ask_sell_pahalilik</th>
                                <th>Calculation</th>
                            </tr>
                        </thead>
                        <tbody>
                            {d.blocking_details.filter(b => b.status === 'INTENT_GENERATED').map((b, i) => (
                                <tr key={i} className="row-success">
                                    <td><strong>{b.symbol}</strong></td>
                                    <td>{b.side}</td>
                                    <td>{b.sell_qty || b.cover_qty}</td>
                                    <td>Step {b.step_triggered || 'N/A'}</td>
                                    <td>{b.gort !== null && b.gort !== undefined ? b.gort.toFixed(3) : 'N/A'}</td>
                                    <td>{b.fbtot !== null && b.fbtot !== undefined ? b.fbtot.toFixed(3) : 'N/A'}</td>
                                    <td>{b.ask_sell_pahalilik !== null && b.ask_sell_pahalilik !== undefined ? b.ask_sell_pahalilik.toFixed(3) : 'N/A'}</td>
                                    <td className="detail-cell">{b.calculation || 'N/A'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <p className="empty-text">No intents generated this cycle.</p>
                )}

                <h3>🚫 Blocking Reasons (Detailed)</h3>
                {d.blocking_details && d.blocking_details.filter(b => b.status !== 'INTENT_GENERATED').length > 0 ? (
                    <table className="diagnostic-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Why Blocked?</th>
                                <th>Threshold</th>
                            </tr>
                        </thead>
                        <tbody>
                            {d.blocking_details.filter(b => b.status !== 'INTENT_GENERATED').map((b, i) => (
                                <tr key={i}>
                                    <td>{b.symbol}</td>
                                    <td className="reason-text">{b.reasons?.join(', ') || 'NO_REASON'}</td>
                                    <td>{b.threshold}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <p className="empty-text">All positions passed filters - nothing blocked!</p>
                )}
            </div>
        );
    };

    return (
        <div className="karbotu-diagnostic">
            <div className="header-row">
                <h2>🧭 UNIVERSAL DECISION COMPASS</h2>
                <div className="last-update">Last Update: {data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : 'Waiting for Cycle...'}</div>
            </div>

            <div className="tabs">
                <button
                    className={`tab-btn ${activeTab === 'LT_TRIM' ? 'active' : ''}`}
                    onClick={() => setActiveTab('LT_TRIM')}
                >
                    ✂️ LT TRIM (Executive)
                </button>
                <button
                    className={`tab-btn ${activeTab === 'KARBOTU' ? 'active' : ''}`}
                    onClick={() => setActiveTab('KARBOTU')}
                >
                    🤖 KARBOTU (Macro)
                </button>
            </div>

            <div className="tab-content">
                {activeTab === 'LT_TRIM' && renderLtTrimTab()}
                {activeTab === 'KARBOTU' && renderKarbotuTab()}
            </div>
        </div>
    );
}

// Keep export name for compatibility
export default UniversalDecisionReport;
