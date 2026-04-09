import React, { useState, useEffect } from 'react';
import './SimulationPanel.css';

/**
 * Simulation Control Panel
 * 
 * Features:
 * - LIFELESS mode toggle
 * - Simulation mode toggle (only enabled if LIFELESS ON)
 * - "10 Min Later" button for fill simulation
 * - Mode indicator
 * - Fake order statistics
 */
function SimulationPanel() {
    const [lifelessMode, setLifelessMode] = useState(false);
    const [simulationMode, setSimulationMode] = useState(false);
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(false);
    const [pendingOrders, setPendingOrders] = useState([]);
    const [filledOrders, setFilledOrders] = useState([]);

    // Fetch status on mount and when modes change
    useEffect(() => {
        fetchStatus();
    }, []);

    // Poll for orders every 5 seconds when simulation mode is active
    useEffect(() => {
        if (simulationMode) {
            fetchOrders();
            const interval = setInterval(fetchOrders, 5000);
            return () => clearInterval(interval);
        }
    }, [simulationMode]);

    const fetchStatus = async () => {
        try {
            const response = await fetch('/api/simulation/status');
            const data = await response.json();
            setStatus(data);
            setLifelessMode(data.lifeless_active);
            setSimulationMode(data.simulation_active);
        } catch (error) {
            console.error('Error fetching simulation status:', error);
        }
    };

    const fetchOrders = async () => {
        if (!simulationMode) return;

        try {
            // Fetch pending orders
            const pendingRes = await fetch('/api/simulation/orders/pending');
            const pendingData = await pendingRes.json();
            if (pendingData.success) {
                setPendingOrders(pendingData.orders || []);
            }

            // Fetch filled orders
            const filledRes = await fetch('/api/simulation/orders/filled');
            const filledData = await filledRes.json();
            if (filledData.success) {
                setFilledOrders(filledData.orders || []);
            }
        } catch (error) {
            console.error('Error fetching orders:', error);
        }
    };

    const handleLifelessToggle = async () => {
        setLoading(true);
        try {
            const newValue = !lifelessMode;
            await fetch(`/api/simulation/set-lifeless?active=${newValue}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            setLifelessMode(newValue);
            if (!newValue) {
                setSimulationMode(false); // Auto-disable simulation
            }
            await fetchStatus();
        } catch (error) {
            console.error('Error toggling LIFELESS mode:', error);
            alert('Error toggling LIFELESS mode: ' + error.message);
        }
        setLoading(false);
    };

    const handleSimulationToggle = async () => {
        if (!lifelessMode) {
            alert('⚠️ LIFELESS mode must be enabled first!');
            return;
        }

        setLoading(true);
        try {
            const endpoint = simulationMode ? '/api/simulation/disable' : '/api/simulation/enable';
            await fetch(endpoint, { method: 'POST' });
            setSimulationMode(!simulationMode);
            await fetchStatus();
        } catch (error) {
            console.error('Error toggling simulation mode:', error);
            alert('Error: ' + error.message);
        }
        setLoading(false);
    };

    const handleSimulateFills = async () => {
        if (!simulationMode) {
            alert('⚠️ Simulation mode must be enabled!');
            return;
        }

        const pendingOrders = status?.pending_orders || 0;
        if (pendingOrders === 0) {
            alert('No pending orders to fill');
            return;
        }

        setLoading(true);
        try {
            const response = await fetch('/api/simulation/simulate-fills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    fill_percentage: 0.5,  // Fill 50% of orders
                    min_fills: 1,
                    max_slippage: 0.02
                })
            });

            const data = await response.json();
            alert(`✅ Filled ${data.filled_count} orders!\n\nCheck fake orders list below.`);
            await fetchStatus();
        } catch (error) {
            console.error('Error simulating fills:', error);
            alert('Error: ' + error.message);
        }
        setLoading(false);
    };

    const handleReset = async () => {
        if (!confirm('Reset all fake orders?')) return;

        setLoading(true);
        try {
            await fetch('/api/simulation/reset', { method: 'POST' });
            await fetchStatus();
            alert('✅ All fake orders cleared');
        } catch (error) {
            console.error('Error resetting simulation:', error);
        }
        setLoading(false);
    };

    const modeDisplay = status?.mode_display || 'Loading...';
    const isSimMode = status?.is_simulation_mode || false;

    return (
        <div className="simulation-panel">
            <div className="simulation-header">
                <h2>🎭 Simulation Mode</h2>
                <div className={`mode-indicator ${isSimMode ? 'simulation' : 'real'}`}>
                    {modeDisplay}
                </div>
            </div>

            <div className="simulation-controls">
                {/* LIFELESS Mode Toggle */}
                <div className="control-group">
                    <label className="toggle-label">
                        <span className="label-text">LIFELESS Mode</span>
                        <span className="label-desc">Random market data (for testing without live data)</span>
                    </label>
                    <button
                        className={`toggle-btn ${lifelessMode ? 'active' : ''}`}
                        onClick={handleLifelessToggle}
                        disabled={loading}
                    >
                        {lifelessMode ? '✅ ON' : '❌ OFF'}
                    </button>
                </div>

                {/* Simulation Mode Toggle */}
                <div className="control-group">
                    <label className="toggle-label">
                        <span className="label-text">Simulation Mode</span>
                        <span className="label-desc">Fake order execution (requires LIFELESS)</span>
                    </label>
                    <button
                        className={`toggle-btn ${simulationMode ? 'active' : ''}`}
                        onClick={handleSimulationToggle}
                        disabled={loading || !lifelessMode}
                    >
                        {simulationMode ? '🎭 ON' : '❌ OFF'}
                    </button>
                </div>

                {/* Statistics */}
                {status && (
                    <div className="stats-grid">
                        <div className="stat-card">
                            <div className="stat-value">{status.pending_orders}</div>
                            <div className="stat-label">Pending Orders</div>
                        </div>
                        <div className="stat-card">
                            <div className="stat-value">{status.filled_orders}</div>
                            <div className="stat-label">Filled Orders</div>
                        </div>
                        <div className="stat-card">
                            <div className="stat-value">{status.total_orders}</div>
                            <div className="stat-label">Total Orders</div>
                        </div>
                    </div>
                )}

                {/* Pending Orders Table */}
                {simulationMode && pendingOrders.length > 0 && (
                    <div className="orders-section">
                        <h3>📋 Pending Orders ({pendingOrders.length})</h3>
                        <div className="orders-table-container">
                            <table className="orders-table">
                                <thead>
                                    <tr>
                                        <th>Symbol</th>
                                        <th>Side</th>
                                        <th>Qty</th>
                                        <th>Price</th>
                                        <th>Current Bid</th>
                                        <th>Current Ask</th>
                                        <th>Tag</th>
                                        <th>Engine</th>
                                        <th>Time</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {pendingOrders.map((order, idx) => (
                                        <tr key={idx}>
                                            <td className="symbol">{order.symbol}</td>
                                            <td className={`side ${order.side?.toLowerCase()}`}>{order.side}</td>
                                            <td>{order.qty}</td>
                                            <td>${order.price?.toFixed(2) || 'MARKET'}</td>
                                            <td className="market-price">${order.current_bid?.toFixed(2) || 'N/A'}</td>
                                            <td className="market-price">${order.current_ask?.toFixed(2) || 'N/A'}</td>
                                            <td><span className="tag">{order.tag}</span></td>
                                            <td>{order.engine}</td>
                                            <td>{new Date(order.timestamp).toLocaleTimeString()}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {/* Filled Orders Table */}
                {simulationMode && filledOrders.length > 0 && (
                    <div className="orders-section">
                        <h3>✅ Filled Orders ({filledOrders.length})</h3>
                        <div className="orders-table-container">
                            <table className="orders-table">
                                <thead>
                                    <tr>
                                        <th>Symbol</th>
                                        <th>Side</th>
                                        <th>Qty</th>
                                        <th>Fill Price</th>
                                        <th>Fill Time</th>
                                        <th>Tag</th>
                                        <th>Engine</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filledOrders.map((order, idx) => (
                                        <tr key={idx}>
                                            <td className="symbol">{order.symbol}</td>
                                            <td className={`side ${order.side?.toLowerCase()}`}>{order.side}</td>
                                            <td>{order.fill_qty || order.qty}</td>
                                            <td className="fill-price">${order.fill_price?.toFixed(2)}</td>
                                            <td>{new Date(order.filled_at).toLocaleTimeString()}</td>
                                            <td><span className="tag">{order.tag}</span></td>
                                            <td>{order.engine}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {/* Action Buttons */}
                <div className="action-buttons">
                    <button
                        className="btn-simulate-fills"
                        onClick={handleSimulateFills}
                        disabled={!simulationMode || (status?.pending_orders === 0) || loading}
                    >
                        ⏭️ Simulate 10 Min Later ({status?.pending_orders || 0} pending)
                    </button>

                    <button
                        className="btn-reset"
                        onClick={handleReset}
                        disabled={!simulationMode || loading}
                    >
                        🗑️ Reset All
                    </button>
                </div>
            </div>

            {/* Safety Warning */}
            {!simulationMode && (
                <div className="safety-warning">
                    <strong>📡 LIVE DATA ACTIVE</strong><br />
                    Market data is real. Order execution depends on Global Execution Mode (Preview/Live).
                </div>
            )}

            {simulationMode && (
                <div className="safety-info">
                    <strong>🎭 SIMULATION MODE ACTIVE</strong><br />
                    Orders are FAKE and will NOT be sent to broker.
                </div>
            )}
        </div>
    );
}

export default SimulationPanel;
