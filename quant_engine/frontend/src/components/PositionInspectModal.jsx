import React from 'react'
import './PositionInspectModal.css'

const PositionInspectModal = ({ isOpen, onClose, position }) => {
    if (!isOpen || !position) return null

    // Ensure position_tags is a valid object
    const tags = position.position_tags || {}
    const hasTags = Object.keys(tags).length > 0

    // Helper to format quantity
    const fmtQty = (val) => {
        if (!val) return '0'
        return val > 0 ? `+${val}` : `${val}`
    }

    // Helper to determine badge class
    const getTagClass = (tag) => {
        const t = tag.toLowerCase()
        if (t.includes('lt_') && t.includes('ov')) return 'tag-lt-ov'
        if (t.includes('lt_') && t.includes('int')) return 'tag-lt-int'
        if (t.includes('mm_') && t.includes('ov')) return 'tag-mm-ov'
        if (t.includes('mm_') && t.includes('int')) return 'tag-mm-int'
        return 'tag-badge'
    }

    // Format readable tag name
    const getReadableTag = (tag) => {
        // e.g. LT_LONG_OV -> LT OV (Long)
        const parts = tag.split('_')
        if (parts.length >= 3) {
            const book = parts[0]
            const side = parts[1] === 'LONG' ? 'Long' : 'Short'
            const origin = parts[2]
            return `${book} ${origin} (${side})`
        }
        return tag
    }

    return (
        <div className="position-inspect-overlay" onClick={onClose}>
            <div className="position-inspect-modal" onClick={e => e.stopPropagation()}>
                <div className="inspect-header">
                    <div className="inspect-title">
                        <span className="inspect-symbol">{position.symbol}</span>
                        <span className={`taxonomy-badge ${position.strategy_type?.toLowerCase() || 'lt'}`}>
                            {position.full_taxonomy || 'Unknown'}
                        </span>
                    </div>
                    <button className="inspect-close-btn" onClick={onClose}>×</button>
                </div>

                <div className="inspect-body">
                    <div className="inspect-overview">
                        <div className="overview-item">
                            <span className="overview-label">Total Quantity</span>
                            <span className={`overview-value ${position.qty >= 0 ? 'qty-positive' : 'qty-negative'}`}>
                                {fmtQty(position.qty)}
                            </span>
                        </div>
                        <div className="overview-item">
                            <span className="overview-label">Unrealized P&L</span>
                            <span className={`overview-value ${position.unrealized_pnl >= 0 ? 'qty-positive' : 'qty-negative'}`}>
                                ${position.unrealized_pnl ? position.unrealized_pnl.toFixed(2) : '0.00'}
                            </span>
                        </div>
                        <div className="overview-item">
                            <span className="overview-label">Avg Price</span>
                            <span className="overview-value">${position.avg_price?.toFixed(2)}</span>
                        </div>
                    </div>

                    <div className="breakdown-section">
                        <h3>Position Breakdown (8-Tag Analysis)</h3>

                        {!hasTags && (
                            <div style={{ padding: '20px', textAlign: 'center', color: '#666' }}>
                                No breakdown tags available.
                            </div>
                        )}

                        {hasTags && (
                            <table className="breakdown-table">
                                <thead>
                                    <tr>
                                        <th>Tag Composition</th>
                                        <th style={{ textAlign: 'right' }}>Quantity</th>
                                        <th style={{ textAlign: 'right' }}>Share</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {Object.entries(tags).map(([tag, qty]) => {
                                        // Calculate share absolute
                                        const totalAbs = Math.abs(position.qty || 1)
                                        const share = totalAbs > 0 ? (qty / totalAbs * 100).toFixed(1) : 0

                                        return (
                                            <tr key={tag}>
                                                <td>
                                                    <span className={`tag-badge ${getTagClass(tag)}`}>
                                                        {getReadableTag(tag)}
                                                    </span>
                                                </td>
                                                <td style={{ textAlign: 'right', fontWeight: 'bold' }}>{qty}</td>
                                                <td style={{ textAlign: 'right', color: '#888' }}>{share}%</td>
                                            </tr>
                                        )
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>

                <div className="inspect-footer">
                    <button className="inspect-btn" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    )
}

export default PositionInspectModal
