import React from 'react'
import './PSFALGOApproveModal.css'

function PSFALGOApproveModal({ cycle, onConfirm, onCancel }) {
  if (!cycle) return null

  // Calculate action breakdown
  const actionBreakdown = {}
  let totalLotImpact = 0

  cycle.actions?.forEach(action => {
    const actionType = action.psfalgo_action
    if (!actionBreakdown[actionType]) {
      actionBreakdown[actionType] = { count: 0, totalLots: 0 }
    }
    actionBreakdown[actionType].count++
    actionBreakdown[actionType].totalLots += action.size_lot_estimate || 0

    // Calculate net lot impact
    if (actionType === 'ADD_LONG' || actionType === 'ADD_SHORT') {
      totalLotImpact += action.size_lot_estimate || 0
    } else if (actionType === 'REDUCE_LONG' || actionType === 'REDUCE_SHORT') {
      totalLotImpact -= action.size_lot_estimate || 0
    }
  })

  // Check for risk flags
  const riskFlags = []
  cycle.actions?.forEach(action => {
    const snapshot = action.position_snapshot
    const guardStatus = action.guard_status

    // MAXALW capped
    if (guardStatus && Array.isArray(guardStatus) && guardStatus.includes('BLOCK_ADD')) {
      riskFlags.push({
        symbol: action.symbol,
        type: 'MAXALW_CAPPED',
        message: `${action.symbol}: MAXALW limit reached`
      })
    }

    // 3H limit warning (if change_3h_remaining is low)
    // This would need to come from guard_reason, but for now we'll check guard_status
    if (guardStatus && Array.isArray(guardStatus) && guardStatus.includes('BLOCK_3H')) {
      riskFlags.push({
        symbol: action.symbol,
        type: '3H_LIMIT',
        message: `${action.symbol}: 3H change limit reached`
      })
    }
  })

  const exposureBefore = cycle.exposure_before
  const exposureAfter = cycle.exposure_after || cycle.exposure_before // Fallback if not yet calculated

  return (
    <div className="psfalgo-modal-overlay" onClick={onCancel}>
      <div className="psfalgo-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="psfalgo-modal-header">
          <h3>⚠️ Confirm Cycle Approval</h3>
          <button className="psfalgo-modal-close" onClick={onCancel}>×</button>
        </div>

        <div className="psfalgo-modal-body">
          {/* Cycle Info */}
          <div className="modal-section">
            <div className="modal-section-title">Cycle Information</div>
            <div className="modal-info-grid">
              <div className="modal-info-item">
                <span className="modal-info-label">Cycle ID:</span>
                <span className="modal-info-value">{cycle.cycle_id || 'N/A'}</span>
              </div>
              <div className="modal-info-item">
                <span className="modal-info-label">Total Actions:</span>
                <span className="modal-info-value">{cycle.action_count || 0}</span>
              </div>
              <div className="modal-info-item">
                <span className="modal-info-label">Net Lot Impact:</span>
                <span className={`modal-info-value ${totalLotImpact > 0 ? 'positive' : totalLotImpact < 0 ? 'negative' : ''}`}>
                  {totalLotImpact > 0 ? '+' : ''}{totalLotImpact}
                </span>
              </div>
            </div>
          </div>

          {/* Actions List (Compact Single Line) */}
          <div className="modal-section">
            <div className="modal-section-title">Proposed Actions ({cycle.actions?.length || 0})</div>
            <div className="actions-list-container" style={{ maxHeight: '400px', overflowY: 'auto' }}>
              <table className="actions-compact-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85em' }}>
                <thead style={{ position: 'sticky', top: 0, backgroundColor: '#1e1e1e', zIndex: 1 }}>
                  <tr style={{ textAlign: 'left', borderBottom: '1px solid #444' }}>
                    <th style={{ padding: '4px' }}>Symbol</th>
                    <th style={{ padding: '4px' }}>Side</th>
                    <th style={{ padding: '4px', textAlign: 'right' }}>Qty</th>
                    <th style={{ padding: '4px', textAlign: 'right' }}>Price</th>
                    <th style={{ padding: '4px' }}>Reason</th>
                    <th style={{ padding: '4px' }}>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {cycle.actions?.map((action, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #333' }}>
                      <td style={{ padding: '4px', fontWeight: 'bold' }}>{action.symbol}</td>
                      <td style={{ padding: '4px' }}>
                        <span className={`side-badge ${action.action === 'BUY' ? 'buy' : 'sell'}`}>
                          {action.action}
                        </span>
                      </td>
                      <td style={{ padding: '4px', textAlign: 'right' }}>{action.qty}</td>
                      <td style={{ padding: '4px', textAlign: 'right' }}>${action.price?.toFixed(2)}</td>
                      <td style={{ padding: '4px', color: '#aaa', maxWidth: '200px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {action.reason}
                      </td>
                      <td style={{ padding: '4px', color: '#888' }}>
                        {/* Optional extra details like Score if available in metadata */}
                        {action.metadata?.score ? `S:${action.metadata.score}` : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Exposure Change */}
          {(exposureBefore || exposureAfter) && (
            <div className="modal-section">
              <div className="modal-section-title">Exposure Impact</div>
              <div className="exposure-comparison">
                <div className="exposure-item">
                  <span className="exposure-label">Before:</span>
                  <span className="exposure-value">
                    ${exposureBefore?.net_value?.toFixed(2) || '0.00'}
                  </span>
                </div>
                <div className="exposure-arrow">→</div>
                <div className="exposure-item">
                  <span className="exposure-label">After:</span>
                  <span className="exposure-value">
                    ${exposureAfter?.net_value?.toFixed(2) || '0.00'}
                  </span>
                </div>
                {exposureBefore && exposureAfter && (
                  <div className="exposure-delta">
                    <span className="exposure-label">Delta:</span>
                    <span className={`exposure-value ${exposureAfter.net_value - exposureBefore.net_value > 0 ? 'positive' : 'negative'}`}>
                      {exposureAfter.net_value - exposureBefore.net_value > 0 ? '+' : ''}
                      ${(exposureAfter.net_value - exposureBefore.net_value).toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Risk Flags */}
          {riskFlags.length > 0 && (
            <div className="modal-section">
              <div className="modal-section-title">⚠️ Risk Flags</div>
              <div className="risk-flags-list">
                {riskFlags.map((flag, index) => (
                  <div key={index} className="risk-flag-item">
                    <span className="risk-flag-icon">⚠️</span>
                    <span className="risk-flag-message">{flag.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Warning Message */}
          <div className="modal-warning">
            <div className="warning-icon">⚠️</div>
            <div className="warning-text">
              <strong>Important:</strong> This cycle will be approved and written to the execution ledger.
              {cycle.execution_results?.executed_count > 0 && (
                <span className="warning-execution">
                  {' '}If execution mode is SEMI_AUTO, real orders may be sent to the broker.
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="psfalgo-modal-footer">
          <button className="psfalgo-modal-btn cancel-btn" onClick={onCancel}>
            Cancel
          </button>
          <button className="psfalgo-modal-btn confirm-btn" onClick={onConfirm}>
            Confirm & Approve
          </button>
        </div>
      </div>
    </div>
  )
}

export default PSFALGOApproveModal





