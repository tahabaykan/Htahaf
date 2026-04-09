import React from 'react'
import './OrderConfirmModal.css'

/**
 * OrderConfirmModal - Order confirmation modal for JFIN 
 * 
 * Shows list of orders before execution and requires user confirmation.
 */
function OrderConfirmModal({
    isOpen,
    onClose,
    onConfirm,
    orders = [],
    poolType = 'BB',
    percentage = 50,
    loading = false
}) {
    if (!isOpen) return null

    // Calculate totals
    const totalOrders = orders.length
    const totalLots = orders.reduce((sum, o) => sum + (o.final_lot || o.qty || 0), 0)
    const totalValue = orders.reduce((sum, o) => {
        const qty = o.final_lot || o.qty || 0
        const price = o.order_price || o.price || 0
        return sum + (qty * price)
    }, 0)

    // Determine action based on pool type
    const isLong = poolType === 'BB' || poolType === 'FB'
    const action = isLong ? 'BUY' : 'SELL'
    const actionColor = isLong ? '#4caf50' : '#f44336'

    return (
        <div className="order-modal-overlay" onClick={onClose}>
            <div className="order-modal-content" onClick={e => e.stopPropagation()}>
                <div className="order-modal-header">
                    <h3>📋 Emir Onayı - JFIN {percentage}% ({poolType})</h3>
                    <button className="order-modal-close" onClick={onClose}>×</button>
                </div>

                <div className="order-modal-summary">
                    <div className="summary-item">
                        <span className="summary-label">Toplam Emir:</span>
                        <span className="summary-value">{totalOrders}</span>
                    </div>
                    <div className="summary-item">
                        <span className="summary-label">Toplam Lot:</span>
                        <span className="summary-value">{totalLots.toLocaleString()}</span>
                    </div>
                    <div className="summary-item">
                        <span className="summary-label">Tahmini Değer:</span>
                        <span className="summary-value">${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <div className="summary-item">
                        <span className="summary-label">Aksiyon:</span>
                        <span className="summary-value" style={{ color: actionColor, fontWeight: 'bold' }}>{action}</span>
                    </div>
                </div>

                <div className="order-modal-table-container">
                    <table className="order-modal-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Grup</th>
                                <th>Lot</th>
                                <th>Fiyat</th>
                                <th>Değer</th>
                                <th>GORT</th>
                            </tr>
                        </thead>
                        <tbody>
                            {orders.map((order, idx) => {
                                const qty = order.final_lot || order.qty || 0
                                const price = order.order_price || order.price || 0
                                const value = qty * price

                                return (
                                    <tr key={order.symbol || idx}>
                                        <td className="symbol-cell">{order.symbol}</td>
                                        <td>{order.group || '-'}</td>
                                        <td className={isLong ? 'long-cell' : 'short-cell'}>
                                            {isLong ? '' : '-'}{qty.toLocaleString()}
                                        </td>
                                        <td className="price-cell">${price.toFixed(2)}</td>
                                        <td className="value-cell">${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                                        <td>{order.gort?.toFixed(2) || '-'}</td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>

                <div className="order-modal-actions">
                    <button
                        className="order-modal-cancel"
                        onClick={onClose}
                        disabled={loading}
                    >
                        ❌ İptal
                    </button>
                    <button
                        className="order-modal-confirm"
                        onClick={onConfirm}
                        disabled={loading || orders.length === 0}
                    >
                        {loading ? '⏳ Gönderiliyor...' : `✅ ${totalOrders} Emri Onayla`}
                    </button>
                </div>
            </div>
        </div>
    )
}

export default OrderConfirmModal
