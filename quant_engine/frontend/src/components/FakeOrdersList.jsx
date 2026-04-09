import React, { useState, useEffect } from 'react';
import './FakeOrdersList.css';

/**
 * Fake Orders Display
 * 
 * Shows all fake orders created in simulation mode
 * - Pending orders (waiting for fill)
 * - Filled orders (simulated fills)
 * - Order details (symbol, side, qty, price, tag, status)
 */
function FakeOrdersList() {
    const [orders, setOrders] = useState([]);
    const [filter, setFilter] = useState('ALL'); // ALL, PENDING, FILLED
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        fetchOrders();
        // Auto-refresh every 5 seconds
        const interval = setInterval(fetchOrders, 5000);
        return () => clearInterval(interval);
    }, [filter]);

    const fetchOrders = async () => {
        setLoading(true);
        try {
            let url = '/api/simulation/orders';
            if (filter !== 'ALL') {
                url += `?status=${filter}`;
            }

            const response = await fetch(url);
            const data = await response.json();
            setOrders(data.orders || []);
        } catch (error) {
            console.error('Error fetching fake orders:', error);
        }
        setLoading(false);
    };

    const getStatusBadge = (status) => {
        const badges = {
            'PENDING': { icon: '⏳', class: 'status-pending' },
            'FILLED': { icon: '✅', class: 'status-filled' },
            'CANCELLED': { icon: '❌', class: 'status-cancelled' }
        };
        const badge = badges[status] || { icon: '❓', class: '' };
        return (
            <span className={`status-badge ${badge.class}`}>
                {badge.icon} {status}
            </span>
        );
    };

    const getSideBadge = (side) => {
        const buyClass = side === 'BUY' ? 'side-buy' : 'side-sell';
        return <span className={`side-badge ${buyClass}`}>{side}</span>;
    };

    return (
        <div className="fake-orders-list">
            <div className="orders-header">
                <h3>🎭 Fake Orders ({orders.length})</h3>

                <div className="filter-buttons">
                    <button
                        className={filter === 'ALL' ? 'active' : ''}
                        onClick={() => setFilter('ALL')}
                    >
                        All
                    </button>
                    <button
                        className={filter === 'PENDING' ? 'active' : ''}
                        onClick={() => setFilter('PENDING')}
                    >
                        ⏳ Pending
                    </button>
                    <button
                        className={filter === 'FILLED' ? 'active' : ''}
                        onClick={() => setFilter('FILLED')}
                    >
                        ✅ Filled
                    </button>
                </div>

                <button className="btn-refresh" onClick={fetchOrders} disabled={loading}>
                    🔄 Refresh
                </button>
            </div>

            {orders.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-icon">📭</div>
                    <p>No fake orders yet</p>
                    <small>Run RUNALL in simulation mode to generate orders</small>
                </div>
            ) : (
                <div className="orders-table-container">
                    <table className="orders-table">
                        <thead>
                            <tr>
                                <th>Order ID</th>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Qty</th>
                                <th>Price</th>
                                <th>Fill Price</th>
                                <th>Tag</th>
                                <th>Status</th>
                                <th>Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            {orders.map((order) => (
                                <tr key={order.order_id} className={`order-row ${order.status.toLowerCase()}`}>
                                    <td className="order-id">{order.order_id}</td>
                                    <td className="symbol">{order.symbol}</td>
                                    <td>{getSideBadge(order.side)}</td>
                                    <td className="qty">{order.qty.toLocaleString()}</td>
                                    <td className="price">${order.price.toFixed(2)}</td>
                                    <td className="fill-price">
                                        {order.fill_price ? `$${order.fill_price.toFixed(2)}` : '-'}
                                    </td>
                                    <td className="tag">{order.tag}</td>
                                    <td>{getStatusBadge(order.status)}</td>
                                    <td className="time">
                                        {new Date(order.timestamp).toLocaleTimeString()}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

export default FakeOrdersList;
