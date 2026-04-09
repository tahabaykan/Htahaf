import React, { useState, useEffect, useCallback } from 'react';
import './RevOrdersModal.css';

/**
 * REV Orders Modal - Shows active REV orders across accounts
 * REV orders are auto-generated recovery/take-profit orders from RevnBookCheck terminal
 */
const RevOrdersModal = ({ isOpen, onClose }) => {
    const [loading, setLoading] = useState(false);
    const [ordersData, setOrdersData] = useState(null);
    const [error, setError] = useState(null);
    const [selectedAccount, setSelectedAccount] = useState('ALL');

    const fetchRevOrders = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/rev-orders/');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            setOrdersData(data);
        } catch (err) {
            console.error('REV Orders fetch error:', err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (isOpen) {
            fetchRevOrders();
            // Auto-refresh every 15 seconds while open
            const interval = setInterval(fetchRevOrders, 15000);
            return () => clearInterval(interval);
        }
    }, [isOpen, fetchRevOrders]);

    if (!isOpen) return null;

    // Get orders to display based on selected account
    const getOrdersToDisplay = () => {
        if (!ordersData || !ordersData.accounts) return [];

        if (selectedAccount === 'ALL') {
            return Object.entries(ordersData.accounts).flatMap(([account, data]) =>
                (data.orders || []).map(order => ({ ...order, account }))
            );
        }

        const accountData = ordersData.accounts[selectedAccount];
        return (accountData?.orders || []).map(order => ({ ...order, account: selectedAccount }));
    };

    const displayOrders = getOrdersToDisplay();

    const getRevTypeBadgeClass = (revType) => {
        switch (revType) {
            case 'TP': return 'badge-tp';
            case 'RELOAD': return 'badge-reload';
            default: return 'badge-unknown';
        }
    };

    const getDirectionBadgeClass = (direction) => {
        switch (direction) {
            case 'LONG': return 'badge-long';
            case 'SHORT': return 'badge-short';
            default: return 'badge-unknown';
        }
    };

    const getActionClass = (action) => {
        return action === 'BUY' ? 'action-buy' : 'action-sell';
    };

    return (
        <div className="rev-orders-overlay" onClick={onClose}>
            <div className="rev-orders-modal" onClick={e => e.stopPropagation()}>
                <div className="rev-orders-header">
                    <h2>🔄 Active REV Orders</h2>
                    <div className="rev-orders-controls">
                        <select
                            value={selectedAccount}
                            onChange={(e) => setSelectedAccount(e.target.value)}
                            className="account-filter"
                        >
                            <option value="ALL">All Accounts</option>
                            <option value="HAMPRO">HAMPRO</option>
                            <option value="IBKR_PED">IBKR_PED</option>
                            <option value="IBKR_GUN">IBKR_GUN</option>
                        </select>
                        <button
                            className="refresh-btn"
                            onClick={fetchRevOrders}
                            disabled={loading}
                        >
                            {loading ? '⏳' : '🔄'} Refresh
                        </button>
                        <button className="close-btn" onClick={onClose}>✕</button>
                    </div>
                </div>

                {/* Summary Stats */}
                {ordersData && (
                    <div className="rev-orders-summary">
                        <div className="summary-stat">
                            <span className="stat-label">Total REV:</span>
                            <span className="stat-value">{ordersData.total_rev_orders || 0}</span>
                        </div>
                        {Object.entries(ordersData.accounts || {}).map(([account, data]) => (
                            <div key={account} className="summary-stat">
                                <span className="stat-label">{account}:</span>
                                <span className="stat-value">{data.count || 0}</span>
                            </div>
                        ))}
                    </div>
                )}

                {/* Error State */}
                {error && (
                    <div className="rev-orders-error">
                        ⚠️ Error fetching REV orders: {error}
                    </div>
                )}

                {/* Loading State */}
                {loading && !ordersData && (
                    <div className="rev-orders-loading">
                        Loading REV orders...
                    </div>
                )}

                {/* Orders Table */}
                {!loading && ordersData && (
                    <div className="rev-orders-table-container">
                        {displayOrders.length === 0 ? (
                            <div className="rev-orders-empty">
                                No active REV orders found
                            </div>
                        ) : (
                            <table className="rev-orders-table">
                                <thead>
                                    <tr>
                                        <th>Account</th>
                                        <th>Symbol</th>
                                        <th>Action</th>
                                        <th>Qty</th>
                                        <th>Price</th>
                                        <th>Type</th>
                                        <th>Direction</th>
                                        <th>Tag</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {displayOrders.map((order, idx) => (
                                        <tr key={`${order.account}-${order.order_id || idx}`}>
                                            <td className="account-cell">{order.account}</td>
                                            <td className="symbol-cell">{order.symbol}</td>
                                            <td className={`action-cell ${getActionClass(order.action)}`}>
                                                {order.action}
                                            </td>
                                            <td className="qty-cell">{order.quantity || order.qty}</td>
                                            <td className="price-cell">${parseFloat(order.price || 0).toFixed(2)}</td>
                                            <td className="type-cell">
                                                <span className={`badge ${getRevTypeBadgeClass(order.rev_type)}`}>
                                                    {order.rev_type || 'UNKNOWN'}
                                                </span>
                                            </td>
                                            <td className="direction-cell">
                                                <span className={`badge ${getDirectionBadgeClass(order.direction)}`}>
                                                    {order.direction || 'UNKNOWN'}
                                                </span>
                                            </td>
                                            <td className="tag-cell" title={order.tag}>
                                                {order.tag}
                                            </td>
                                            <td className="status-cell">{order.status || '-'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                )}

                <div className="rev-orders-footer">
                    <span className="last-updated">
                        {ordersData?.timestamp ? `Last updated: ${new Date(ordersData.timestamp).toLocaleTimeString()}` : ''}
                    </span>
                    <span className="auto-refresh-note">Auto-refreshes every 15s</span>
                </div>
            </div>
        </div>
    );
};

export default RevOrdersModal;
