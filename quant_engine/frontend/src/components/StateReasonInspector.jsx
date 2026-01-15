import React from 'react'
import './StateReasonInspector.css'

function StateReasonInspector({ selectedRow, onClose }) {
  if (!selectedRow) {
    return null
  }

  const { state, state_reason, transition_reason, intent, intent_reason, order_plan, queue_status, gate_status, user_action, user_note, execution_status, execution_reason, execution_mode, position_analytics, exposure_mode, befday_qty, current_qty, potential_qty, open_buy_qty, open_sell_qty, befday_cost_raw, befday_cost_adj, used_befday_cost, position_state, maxalw, maxalw_exceeded_current, maxalw_exceeded_potential, daily_add_used, daily_add_limit, daily_add_remaining, change_3h_net, change_3h_limit, change_3h_remaining, cross_blocked, cross_block_reason, guard_status, guard_reason, allowed_actions, psfalgo_action_plan, PREF_IBKR } = selectedRow
  
  const [actionNote, setActionNote] = React.useState(user_note || '')
  const [saving, setSaving] = React.useState(false)

  return (
    <div className="state-reason-inspector">
      <div className="inspector-header">
        <h3>State Reason Inspector</h3>
        <button className="close-button" onClick={onClose}>×</button>
      </div>
      
      <div className="inspector-content">
        <div className="symbol-name">
          <strong>Symbol:</strong> {PREF_IBKR}
        </div>
        
        <div className="state-display">
          <strong>STATE:</strong> {state || 'N/A'}
        </div>
        
        <div className="intent-display">
          <strong>INTENT:</strong> {intent || 'N/A'}
        </div>
        
        {intent_reason && Object.keys(intent_reason).length > 0 && (
          <div className="intent-reason-display">
            <strong>Intent Reason:</strong>
            <div className="reason-items">
              {Object.entries(intent_reason).map(([key, value]) => (
                <div key={key} className="reason-item">
                  <span className="reason-key">{key}:</span>
                  <span className="reason-value">
                    {value === null || value === undefined 
                      ? 'null' 
                      : typeof value === 'object' 
                        ? JSON.stringify(value, null, 2)
                        : String(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {order_plan && Object.keys(order_plan).length > 0 && (
          <div className="order-plan-display">
            <strong>Order Plan:</strong>
            <div className="plan-summary">
              <div className="plan-item">
                <span className="plan-key">Action:</span>
                <span className="plan-value">{order_plan.action || 'NONE'}</span>
              </div>
              {order_plan.style && (
                <div className="plan-item">
                  <span className="plan-key">Style:</span>
                  <span className="plan-value">{order_plan.style}</span>
                </div>
              )}
              {order_plan.price !== null && order_plan.price !== undefined && (
                <div className="plan-item">
                  <span className="plan-key">Price:</span>
                  <span className="plan-value">{order_plan.price.toFixed(2)}</span>
                </div>
              )}
              {order_plan.size !== null && order_plan.size !== undefined && (
                <div className="plan-item">
                  <span className="plan-key">Size:</span>
                  <span className="plan-value">{order_plan.size}</span>
                </div>
              )}
              {order_plan.urgency && (
                <div className="plan-item">
                  <span className="plan-key">Urgency:</span>
                  <span className="plan-value">{order_plan.urgency}</span>
                </div>
              )}
            </div>
            {order_plan.plan_reason && Object.keys(order_plan.plan_reason).length > 0 && (
              <div className="plan-reason-details">
                <strong>Plan Reason:</strong>
                <div className="reason-items">
                  {Object.entries(order_plan.plan_reason).map(([key, value]) => (
                    <div key={key} className="reason-item">
                      <span className="reason-key">{key}:</span>
                      <span className="reason-value">
                        {value === null || value === undefined 
                          ? 'null' 
                          : typeof value === 'object' 
                            ? JSON.stringify(value, null, 2)
                            : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        
        {/* GRPAN Hint Section */}
        {order_plan && order_plan.grpan_hint ? (
          <div className="inspector-section">
            <h3>GRPAN Hint</h3>
            {order_plan.grpan_hint.confidence === 'NONE' && !order_plan.grpan_hint.grpan_price ? (
              <div className="no-grpan-hint">
                No GRPAN hint available
              </div>
            ) : (
              <>
                <div className="inspector-field">
                  <span className="field-label">Confidence:</span>
                  <span className="field-value">{order_plan.grpan_hint.confidence || 'N/A'}</span>
                </div>
                {order_plan.grpan_hint.concentration_percent !== null && order_plan.grpan_hint.concentration_percent !== undefined && (
                  <div className="inspector-field">
                    <span className="field-label">Concentration (%):</span>
                    <span className="field-value">{order_plan.grpan_hint.concentration_percent.toFixed(2)}%</span>
                  </div>
                )}
                {order_plan.grpan_hint.grpan_price !== null && order_plan.grpan_hint.grpan_price !== undefined && (
                  <div className="inspector-field">
                    <span className="field-label">GRPAN Price:</span>
                    <span className="field-value">{order_plan.grpan_hint.grpan_price.toFixed(2)}</span>
                  </div>
                )}
                {order_plan.grpan_hint.distance_to_last !== null && order_plan.grpan_hint.distance_to_last !== undefined && (
                  <div className="inspector-field">
                    <span className="field-label">Distance to Last:</span>
                    <span className="field-value">{order_plan.grpan_hint.distance_to_last.toFixed(2)}</span>
                  </div>
                )}
                {order_plan.grpan_hint.distance_to_mid !== null && order_plan.grpan_hint.distance_to_mid !== undefined && (
                  <div className="inspector-field">
                    <span className="field-label">Distance to Mid:</span>
                    <span className="field-value">{order_plan.grpan_hint.distance_to_mid.toFixed(2)}</span>
                  </div>
                )}
                {(order_plan.grpan_hint.print_count !== null && order_plan.grpan_hint.print_count !== undefined) || 
                 (order_plan.grpan_hint.real_lot_count !== null && order_plan.grpan_hint.real_lot_count !== undefined) ? (
                  <div className="inspector-field">
                    <span className="field-label">Print Count / Real Lot Count:</span>
                    <span className="field-value">
                      {order_plan.grpan_hint.print_count || 0} / {order_plan.grpan_hint.real_lot_count || 0}
                    </span>
                  </div>
                ) : null}
                {order_plan.grpan_hint.message && (
                  <div className="inspector-field">
                    <span className="field-label">Message:</span>
                    <span className="field-value">{order_plan.grpan_hint.message}</span>
                  </div>
                )}
              </>
            )}
          </div>
        ) : order_plan ? (
          <div className="inspector-section">
            <h3>GRPAN Hint</h3>
            <div className="no-grpan-hint">
              No GRPAN hint available
            </div>
          </div>
        ) : null}
        
        {/* PSFALGO Section */}
        {(befday_qty !== null && befday_qty !== undefined) ||
         (current_qty !== null && current_qty !== undefined) ||
         (maxalw !== null && maxalw !== undefined) ? (
          <div className="inspector-section">
            <h3>PSFALGO</h3>
            
            {/* Position Snapshot */}
            <div className="reason-details">
              <strong>Position Snapshot:</strong>
              <div className="reason-items">
                {befday_qty !== null && befday_qty !== undefined && (
                  <div className="reason-item">
                    <span className="reason-key">Befday Qty:</span>
                    <span className="reason-value">{befday_qty.toFixed(2)}</span>
                  </div>
                )}
                {current_qty !== null && current_qty !== undefined && (
                  <div className="reason-item">
                    <span className="reason-key">Current Qty:</span>
                    <span className="reason-value">{current_qty.toFixed(2)}</span>
                  </div>
                )}
                {potential_qty !== null && potential_qty !== undefined && (
                  <div className="reason-item">
                    <span className="reason-key">Potential Qty:</span>
                    <span className="reason-value">{potential_qty.toFixed(2)}</span>
                  </div>
                )}
                {open_buy_qty !== null && open_buy_qty !== undefined && open_buy_qty !== 0 && (
                  <div className="reason-item">
                    <span className="reason-key">Open Buy Qty:</span>
                    <span className="reason-value">{open_buy_qty.toFixed(2)}</span>
                  </div>
                )}
                {open_sell_qty !== null && open_sell_qty !== undefined && open_sell_qty !== 0 && (
                  <div className="reason-item">
                    <span className="reason-key">Open Sell Qty:</span>
                    <span className="reason-value">{open_sell_qty.toFixed(2)}</span>
                  </div>
                )}
                {position_state && (
                  <div className="reason-item">
                    <span className="reason-key">Position State:</span>
                    <span className="reason-value">{position_state}</span>
                  </div>
                )}
                {befday_cost_raw !== null && befday_cost_raw !== undefined && (
                  <div className="reason-item">
                    <span className="reason-key">Befday Cost (Raw):</span>
                    <span className="reason-value">{befday_cost_raw.toFixed(2)}</span>
                  </div>
                )}
                {befday_cost_adj !== null && befday_cost_adj !== undefined && (
                  <div className="reason-item">
                    <span className="reason-key">Befday Cost (Adj):</span>
                    <span className="reason-value">{befday_cost_adj.toFixed(2)}</span>
                  </div>
                )}
                {used_befday_cost !== null && used_befday_cost !== undefined && (
                  <div className="reason-item">
                    <span className="reason-key">Used Befday Cost:</span>
                    <span className="reason-value">{used_befday_cost.toFixed(2)}</span>
                  </div>
                )}
              </div>
            </div>
            
            {/* Guards */}
            {maxalw !== null && maxalw !== undefined && (
              <div className="reason-details">
                <strong>Risk Guards:</strong>
                <div className="reason-items">
                  <div className="reason-item">
                    <span className="reason-key">MAXALW:</span>
                    <span className="reason-value">{maxalw.toFixed(2)}</span>
                  </div>
                  {maxalw_exceeded_current !== null && maxalw_exceeded_current !== undefined && (
                    <div className="reason-item">
                      <span className="reason-key">MAXALW Exceeded (Current):</span>
                      <span className="reason-value">{maxalw_exceeded_current ? 'Yes' : 'No'}</span>
                    </div>
                  )}
                  {maxalw_exceeded_potential !== null && maxalw_exceeded_potential !== undefined && (
                    <div className="reason-item">
                      <span className="reason-key">MAXALW Exceeded (Potential):</span>
                      <span className="reason-value">{maxalw_exceeded_potential ? 'Yes' : 'No'}</span>
                    </div>
                  )}
                  {daily_add_limit !== null && daily_add_limit !== undefined && (
                    <>
                      <div className="reason-item">
                        <span className="reason-key">Daily Add Used:</span>
                        <span className="reason-value">{daily_add_used?.toFixed(2) || '0.00'}</span>
                      </div>
                      <div className="reason-item">
                        <span className="reason-key">Daily Add Limit:</span>
                        <span className="reason-value">{daily_add_limit.toFixed(2)}</span>
                      </div>
                      {daily_add_remaining !== null && daily_add_remaining !== undefined && (
                        <div className="reason-item">
                          <span className="reason-key">Daily Add Remaining:</span>
                          <span className="reason-value">{daily_add_remaining.toFixed(2)}</span>
                        </div>
                      )}
                    </>
                  )}
                  {change_3h_limit !== null && change_3h_limit !== undefined && (
                    <>
                      <div className="reason-item">
                        <span className="reason-key">3H Net Change:</span>
                        <span className="reason-value">{change_3h_net?.toFixed(2) || '0.00'}</span>
                      </div>
                      <div className="reason-item">
                        <span className="reason-key">3H Limit:</span>
                        <span className="reason-value">{change_3h_limit.toFixed(2)}</span>
                      </div>
                      {change_3h_remaining !== null && change_3h_remaining !== undefined && (
                        <div className="reason-item">
                          <span className="reason-key">3H Remaining:</span>
                          <span className="reason-value">{change_3h_remaining.toFixed(2)}</span>
                        </div>
                      )}
                    </>
                  )}
                  {cross_blocked !== null && cross_blocked !== undefined && (
                    <div className="reason-item">
                      <span className="reason-key">Cross Blocked:</span>
                      <span className="reason-value">{cross_blocked ? 'Yes' : 'No'}</span>
                    </div>
                  )}
                  {cross_block_reason && (
                    <div className="reason-item">
                      <span className="reason-key">Cross Block Reason:</span>
                      <span className="reason-value">{cross_block_reason}</span>
                    </div>
                  )}
                  {guard_status && Array.isArray(guard_status) && guard_status.length > 0 && (
                    <div className="reason-item">
                      <span className="reason-key">Guard Status:</span>
                      <span className="reason-value">{guard_status.join(', ')}</span>
                    </div>
                  )}
                  {allowed_actions && Array.isArray(allowed_actions) && allowed_actions.length > 0 && (
                    <div className="reason-item">
                      <span className="reason-key">Allowed Actions:</span>
                      <span className="reason-value">{allowed_actions.join(', ')}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
            
            {/* Guard Reason (Explainable) */}
            {guard_reason && Object.keys(guard_reason).length > 0 && (
              <div className="reason-details">
                <strong>Guard Reason:</strong>
                <div className="reason-items">
                  {guard_reason.explanation && Array.isArray(guard_reason.explanation) && (
                    <div className="reason-item">
                      <span className="reason-key">Explanation:</span>
                      <span className="reason-value">{guard_reason.explanation.join('; ')}</span>
                    </div>
                  )}
                  {guard_reason.inputs && Object.keys(guard_reason.inputs).length > 0 && (
                    <>
                      <div className="reason-item">
                        <span className="reason-key">Inputs:</span>
                      </div>
                      {Object.entries(guard_reason.inputs).map(([key, value]) => (
                        <div key={key} className="reason-item" style={{ marginLeft: '20px' }}>
                          <span className="reason-key">{key}:</span>
                          <span className="reason-value">
                            {value === null || value === undefined ? 'null' : typeof value === 'number' ? value.toFixed(2) : String(value)}
                          </span>
                        </div>
                      ))}
                    </>
                  )}
                  {guard_reason.thresholds && Object.keys(guard_reason.thresholds).length > 0 && (
                    <>
                      <div className="reason-item">
                        <span className="reason-key">Thresholds:</span>
                      </div>
                      {Object.entries(guard_reason.thresholds).map(([key, value]) => (
                        <div key={key} className="reason-item" style={{ marginLeft: '20px' }}>
                          <span className="reason-key">{key}:</span>
                          <span className="reason-value">
                            {value === null || value === undefined ? 'null' : typeof value === 'number' ? value.toFixed(2) : String(value)}
                          </span>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}
        
        {/* PSFALGO Action Plan Section */}
        {psfalgo_action_plan && Object.keys(psfalgo_action_plan).length > 0 ? (
          <div className="inspector-section">
            <h3>PSFALGO Action Plan</h3>
            <div className="inspector-field">
              <span className="field-label">Action:</span>
              <span className="field-value">{psfalgo_action_plan.action || 'N/A'}</span>
            </div>
            {psfalgo_action_plan.size_percent !== null && psfalgo_action_plan.size_percent !== undefined && (
              <div className="inspector-field">
                <span className="field-label">Size Percent:</span>
                <span className="field-value">{psfalgo_action_plan.size_percent.toFixed(2)}%</span>
              </div>
            )}
            {psfalgo_action_plan.size_lot_estimate !== null && psfalgo_action_plan.size_lot_estimate !== undefined && (
              <div className="inspector-field">
                <span className="field-label">Size Lot Estimate:</span>
                <span className="field-value">{psfalgo_action_plan.size_lot_estimate}</span>
              </div>
            )}
            {psfalgo_action_plan.reason && (
              <div className="inspector-field">
                <span className="field-label">Reason:</span>
                <span className="field-value">{psfalgo_action_plan.reason}</span>
              </div>
            )}
            {psfalgo_action_plan.blocked !== null && psfalgo_action_plan.blocked !== undefined && (
              <div className="inspector-field">
                <span className="field-label">Blocked:</span>
                <span className="field-value">{psfalgo_action_plan.blocked ? 'Yes' : 'No'}</span>
              </div>
            )}
            {psfalgo_action_plan.block_reason && (
              <div className="inspector-field">
                <span className="field-label">Block Reason:</span>
                <span className="field-value">{psfalgo_action_plan.block_reason}</span>
              </div>
            )}
          </div>
        ) : null}
        
        {queue_status && Object.keys(queue_status).length > 0 && (
          <div className="queue-status-display">
            <strong>Queue Status:</strong>
            <div className="queue-summary">
              <div className="queue-item">
                <span className="queue-key">Status:</span>
                <span className="queue-value">{queue_status.queue_status || 'N/A'}</span>
              </div>
              {queue_status.queued !== undefined && (
                <div className="queue-item">
                  <span className="queue-key">Queued:</span>
                  <span className="queue-value">{queue_status.queued ? 'Yes' : 'No'}</span>
                </div>
              )}
              {queue_status.position_in_queue !== null && queue_status.position_in_queue !== undefined && (
                <div className="queue-item">
                  <span className="queue-key">Position:</span>
                  <span className="queue-value">#{queue_status.position_in_queue}</span>
                </div>
              )}
              {queue_status.scheduled_time && (
                <div className="queue-item">
                  <span className="queue-key">Scheduled:</span>
                  <span className="queue-value">
                    {new Date(queue_status.scheduled_time * 1000).toLocaleTimeString()}
                  </span>
                </div>
              )}
              {queue_status.reason && (
                <div className="queue-item">
                  <span className="queue-key">Reason:</span>
                  <span className="queue-value">{queue_status.reason}</span>
                </div>
              )}
            </div>
          </div>
        )}
        
        {gate_status && Object.keys(gate_status).length > 0 && (
          <div className="gate-status-display">
            <strong>Gate Status:</strong>
            <div className="gate-summary">
              <div className="gate-item">
                <span className="gate-key">Status:</span>
                <span className="gate-value">{gate_status.gate_status || 'N/A'}</span>
              </div>
              {gate_status.gate_reason && Object.keys(gate_status.gate_reason).length > 0 && (
                <div className="gate-reason-details">
                  <strong>Gate Reason:</strong>
                  <div className="reason-items">
                    {Object.entries(gate_status.gate_reason).map(([key, value]) => (
                      <div key={key} className="reason-item">
                        <span className="reason-key">{key}:</span>
                        <span className="reason-value">
                          {value === null || value === undefined 
                            ? 'null' 
                            : typeof value === 'object' 
                              ? JSON.stringify(value, null, 2)
                              : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        
        {execution_status && (
          <div className="execution-status-display">
            <strong>Execution Status:</strong>
            <div className="execution-summary">
              <div className="execution-item">
                <span className="execution-key">Status:</span>
                <span className="execution-value">{execution_status || 'N/A'}</span>
              </div>
              {execution_mode && (
                <div className="execution-item">
                  <span className="execution-key">Mode:</span>
                  <span className="execution-value">{execution_mode}</span>
                </div>
              )}
              {execution_reason && (
                <div className="execution-item">
                  <span className="execution-key">Reason:</span>
                  <span className="execution-value">{execution_reason}</span>
                </div>
              )}
            </div>
          </div>
        )}
        
        {execution_status && (
          <div className="execution-status-display">
            <strong>Execution Status:</strong>
            <div className="execution-summary">
              <div className="execution-item">
                <span className="execution-key">Status:</span>
                <span className="execution-value">{execution_status || 'N/A'}</span>
              </div>
              {execution_mode && (
                <div className="execution-item">
                  <span className="execution-key">Mode:</span>
                  <span className="execution-value">{execution_mode}</span>
                </div>
              )}
              {execution_reason && (
                <div className="execution-item">
                  <span className="execution-key">Reason:</span>
                  <span className="execution-value">{execution_reason}</span>
                </div>
              )}
            </div>
          </div>
        )}
        
        {transition_reason && Object.keys(transition_reason).length > 0 && (
          <div className="transition-display">
            <strong>Last Transition:</strong>
            <div className="transition-items">
              {Object.entries(transition_reason).map(([key, value]) => (
                <div key={key} className="transition-item">
                  <span className="transition-key">{key}:</span>
                  <span className="transition-value">
                    {value === null || value === undefined 
                      ? 'null' 
                      : typeof value === 'object' 
                        ? JSON.stringify(value, null, 2)
                        : String(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {state_reason && Object.keys(state_reason).length > 0 ? (
          <div className="reason-details">
            <strong>Reason:</strong>
            <div className="reason-items">
              {Object.entries(state_reason).map(([key, value]) => {
                // Skip threshold keys - we'll show them with their base keys
                if (key.endsWith('_threshold')) {
                  return null
                }
                
                // Check if this key has a threshold
                const threshold = state_reason[`${key}_threshold`]
                
                return (
                  <div key={key} className="reason-item">
                    <span className="reason-key">{key}:</span>
                    <span className="reason-value">
                      {value === null || value === undefined ? 'null' : String(value)}
                      {threshold !== null && threshold !== undefined && (
                        <span className="threshold"> (threshold: {threshold})</span>
                      )}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <div className="no-reason">
            No state reason available
          </div>
        )}
        
        {/* Signal Section */}
        {selectedRow?.signal && (
          <div className="inspector-section">
            <h3>Signal & Confidence</h3>
            <div className="inspector-field">
              <span className="field-label">Long Entry:</span>
              <span className="field-value">{selectedRow.signal.long_entry || 'NONE'}</span>
            </div>
            <div className="inspector-field">
              <span className="field-label">Long Exit:</span>
              <span className="field-value">{selectedRow.signal.long_exit || 'NONE'}</span>
            </div>
            <div className="inspector-field">
              <span className="field-label">Short Entry:</span>
              <span className="field-value">{selectedRow.signal.short_entry || 'NONE'}</span>
            </div>
            <div className="inspector-field">
              <span className="field-label">Short Cover:</span>
              <span className="field-value">{selectedRow.signal.short_cover || 'NONE'}</span>
            </div>
            <div className="inspector-field">
              <span className="field-label">Confidence:</span>
              <span className="field-value">{selectedRow.signal.confidence?.toFixed(2) || '0.00'}</span>
            </div>
            
            {/* Signal Reason */}
            {selectedRow.signal_reason && (
              <div className="inspector-subsection">
                <h4>Signal Reason</h4>
                
                {/* Inputs */}
                {selectedRow.signal_reason.inputs && (
                  <div className="inspector-field-group">
                    <div className="field-group-label">Inputs:</div>
                    {Object.entries(selectedRow.signal_reason.inputs).map(([key, value]) => (
                      <div key={key} className="inspector-field">
                        <span className="field-label">{key}:</span>
                        <span className="field-value">{value !== null && value !== undefined ? (typeof value === 'number' ? value.toFixed(2) : String(value)) : 'N/A'}</span>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Applied Rules */}
                {selectedRow.signal_reason.rules && selectedRow.signal_reason.rules.length > 0 && (
                  <div className="inspector-field-group">
                    <div className="field-group-label">Applied Rules:</div>
                    <ul className="rules-list">
                      {selectedRow.signal_reason.rules.map((rule, idx) => (
                        <li key={idx} className="rule-item">{rule}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Computed Components */}
                {selectedRow.signal_reason.computed && (
                  <div className="inspector-field-group">
                    <div className="field-group-label">Confidence Components:</div>
                    {selectedRow.signal_reason.computed.confidence_components && (
                      <>
                        <div className="inspector-field">
                          <span className="field-label">Trend (GORT):</span>
                          <span className="field-value">{selectedRow.signal_reason.computed.confidence_components.trend?.toFixed(3) || 'N/A'}</span>
                        </div>
                        <div className="inspector-field">
                          <span className="field-label">Rank:</span>
                          <span className="field-value">{selectedRow.signal_reason.computed.confidence_components.rank?.toFixed(3) || 'N/A'}</span>
                        </div>
                        <div className="inspector-field">
                          <span className="field-label">Liquidity:</span>
                          <span className="field-value">{selectedRow.signal_reason.computed.confidence_components.liquidity?.toFixed(3) || 'N/A'}</span>
                        </div>
                      </>
                    )}
                    {selectedRow.signal_reason.computed.liquidity_passed !== undefined && (
                      <div className="inspector-field">
                        <span className="field-label">Liquidity Passed:</span>
                        <span className="field-value">{selectedRow.signal_reason.computed.liquidity_passed ? 'Yes' : 'No'}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* GRPAN Section */}
        {selectedRow?.grpan_price !== null && selectedRow?.grpan_price !== undefined ? (
          <div className="inspector-section">
            <h3>GRPAN (Grouped Real Print Analyzer)</h3>
            
            {/* Latest PAN (Backward Compatible) */}
            <div className="inspector-field-group">
              <h4 style={{ marginTop: '10px', marginBottom: '10px', color: '#4CAF50', fontSize: '14px' }}>Latest PAN (Last 15 Prints)</h4>
              <div className="inspector-field">
                <span className="field-label">GRPAN Price:</span>
                <span className="field-value">${selectedRow.grpan_price?.toFixed(2) || 'N/A'}</span>
              </div>
              <div className="inspector-field">
                <span className="field-label">Concentration (±0.04):</span>
                <span className="field-value">{selectedRow.grpan_concentration_percent?.toFixed(2) || 'N/A'}%</span>
              </div>
              <div className="inspector-field">
                <span className="field-label">Real Lot Count:</span>
                <span className="field-value">{selectedRow.grpan_real_lot_count?.toFixed(2) || 'N/A'}</span>
              </div>
              <div className="inspector-field">
                <span className="field-label">Print Count:</span>
                <span className="field-value">{selectedRow.grpan_print_count || 'N/A'}</span>
              </div>
              {selectedRow.grpan_weighted_price_frequency && Object.keys(selectedRow.grpan_weighted_price_frequency).length > 0 && (
                <div className="inspector-field">
                  <span className="field-label">Top Prices (Weighted):</span>
                  <div className="field-value">
                    {Object.entries(selectedRow.grpan_weighted_price_frequency)
                      .slice(0, 5)
                      .map(([price, freq]) => (
                        <div key={price} className="price-freq-item">
                          ${parseFloat(price).toFixed(2)}: {parseFloat(freq).toFixed(2)}
                        </div>
                      ))}
                  </div>
                </div>
              )}
              {selectedRow.grpan_breakdown && (
                <div className="inspector-field">
                  <span className="field-label">Breakdown:</span>
                  <pre className="field-value breakdown-json">
                    {JSON.stringify(selectedRow.grpan_breakdown, null, 2)}
                  </pre>
                </div>
              )}
            </div>
            
            {/* Rolling Windows */}
            {selectedRow?.grpan_windows && (
              <div className="inspector-field-group" style={{ marginTop: '20px' }}>
                <h4 style={{ marginTop: '10px', marginBottom: '15px', color: '#2196F3', fontSize: '14px' }}>Rolling Windows</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '15px' }}>
                  {['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d', 'pan_3d'].map(windowName => {
                    const window = selectedRow.grpan_windows[windowName]
                    if (!window || window.grpan_price === null || window.grpan_price === undefined) {
                      return (
                        <div key={windowName} className="window-card" style={{ 
                          border: '1px solid #ccc', 
                          padding: '10px', 
                          borderRadius: '5px',
                          backgroundColor: '#f5f5f5',
                          opacity: 0.6
                        }}>
                          <div style={{ fontWeight: 'bold', marginBottom: '5px', fontSize: '12px' }}>{windowName.toUpperCase()}</div>
                          <div style={{ color: '#999', fontSize: '0.85em' }}>No data</div>
                        </div>
                      )
                    }
                    
                    const deviationVsLast = window.deviation_vs_last
                    const deviationColor = deviationVsLast !== null && deviationVsLast !== undefined
                      ? (deviationVsLast > 0 ? '#4CAF50' : deviationVsLast < 0 ? '#f44336' : '#999')
                      : '#999'
                    
                    return (
                      <div key={windowName} className="window-card" style={{ 
                        border: '1px solid #2196F3', 
                        padding: '10px', 
                        borderRadius: '5px',
                        backgroundColor: '#f0f8ff'
                      }}>
                        <div style={{ fontWeight: 'bold', marginBottom: '8px', color: '#2196F3', fontSize: '12px' }}>
                          {windowName.toUpperCase()}
                        </div>
                        <div style={{ fontSize: '0.85em', lineHeight: '1.6' }}>
                          <div><strong>Price:</strong> ${window.grpan_price?.toFixed(2) || 'N/A'}</div>
                          <div><strong>Concentration:</strong> {window.concentration_percent?.toFixed(2) || 'N/A'}%</div>
                          <div><strong>Prints:</strong> {window.print_count || 0}</div>
                          {deviationVsLast !== null && deviationVsLast !== undefined && (
                            <div style={{ color: deviationColor, marginTop: '3px' }}>
                              <strong>Dev vs Last:</strong> {deviationVsLast > 0 ? '+' : ''}{deviationVsLast.toFixed(2)}
                            </div>
                          )}
                          {window.deviation_vs_prev_window !== null && window.deviation_vs_prev_window !== undefined && (
                            <div style={{ fontSize: '0.8em', color: '#666', marginTop: '3px' }}>
                              <strong>Dev vs Prev:</strong> {window.deviation_vs_prev_window > 0 ? '+' : ''}{window.deviation_vs_prev_window.toFixed(2)}
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        ) : null}
        
        {/* RWVAP Section */}
        {selectedRow?.rwvap_windows && (
          <div className="inspector-section">
            <h3>RWVAP (Robust VWAP)</h3>
            <div className="inspector-field-group">
              <h4 style={{ marginTop: '10px', marginBottom: '15px', color: '#FF9800', fontSize: '14px' }}>RWVAP Windows (Excluding Extreme Volume)</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '15px' }}>
                {['rwvap_1d', 'rwvap_3d', 'rwvap_5d'].map(windowName => {
                  const window = selectedRow.rwvap_windows[windowName]
                  if (!window || window.rwvap === null || window.rwvap === undefined) {
                    return (
                      <div key={windowName} className="window-card" style={{ 
                        border: '1px solid #ccc', 
                        padding: '10px', 
                        borderRadius: '5px',
                        backgroundColor: '#f5f5f5',
                        opacity: 0.6
                      }}>
                        <div style={{ fontWeight: 'bold', marginBottom: '5px', fontSize: '12px' }}>{windowName.toUpperCase()}</div>
                        <div style={{ color: '#999', fontSize: '0.85em' }}>
                          {window?.status === 'COLLECTING' ? 'Collecting...' : window?.status === 'INSUFFICIENT_DATA' ? 'Insufficient data' : 'No data'}
                        </div>
                      </div>
                    )
                  }
                  
                  const deviationVsLast = window.deviation_vs_last
                  const deviationColor = deviationVsLast !== null && deviationVsLast !== undefined
                    ? (deviationVsLast > 0 ? '#4CAF50' : deviationVsLast < 0 ? '#f44336' : '#999')
                    : '#999'
                  
                  return (
                    <div key={windowName} className="window-card" style={{ 
                      border: '1px solid #FF9800', 
                      padding: '10px', 
                      borderRadius: '5px',
                      backgroundColor: '#fff3e0'
                    }}>
                      <div style={{ fontWeight: 'bold', marginBottom: '8px', color: '#FF9800', fontSize: '12px' }}>
                        {windowName.toUpperCase()}
                      </div>
                      <div style={{ fontSize: '0.85em', lineHeight: '1.6' }}>
                        <div><strong>RWVAP:</strong> ${window.rwvap?.toFixed(2) || 'N/A'}</div>
                        <div><strong>Effective Prints:</strong> {window.effective_print_count || 0}</div>
                        {window.excluded_print_count > 0 && (
                          <div style={{ fontSize: '0.8em', color: '#666', marginTop: '3px' }}>
                            <strong>Excluded:</strong> {window.excluded_print_count} prints
                            {window.excluded_volume_ratio > 0 && (
                              <span> ({((window.excluded_volume_ratio || 0) * 100).toFixed(1)}% vol)</span>
                            )}
                          </div>
                        )}
                        {deviationVsLast !== null && deviationVsLast !== undefined && (
                          <div style={{ color: deviationColor, marginTop: '3px' }}>
                            <strong>Dev vs Last:</strong> {deviationVsLast > 0 ? '+' : ''}{deviationVsLast.toFixed(2)}
                          </div>
                        )}
                        {window.status && (
                          <div style={{ fontSize: '0.8em', color: '#666', marginTop: '3px' }}>
                            <strong>Status:</strong> {window.status}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
        
        {/* Pricing Overlay Scores */}
        {selectedRow?.overlay_status && (
          <div className="inspector-section">
            <h3>Pricing Overlay Scores</h3>
            <div style={{ marginBottom: '10px' }}>
              <strong>Status:</strong> {selectedRow.overlay_status}
              {selectedRow.overlay_benchmark_type && (
                <span style={{ marginLeft: '10px' }}>
                  <strong>Benchmark Type:</strong> {selectedRow.overlay_benchmark_type}
                </span>
              )}
              {selectedRow.overlay_benchmark_chg !== null && selectedRow.overlay_benchmark_chg !== undefined && (
                <span style={{ marginLeft: '10px' }}>
                  <strong>Benchmark Chg:</strong> {selectedRow.overlay_benchmark_chg > 0 ? '+' : ''}{selectedRow.overlay_benchmark_chg.toFixed(4)}
                </span>
              )}
            </div>
            
            {selectedRow.overlay_status === 'OK' && (
              <div>
                <div style={{ marginBottom: '10px' }}>
                  <strong>Ucuzluk Skorları:</strong>
                  <div style={{ marginLeft: '10px', fontSize: '0.9em' }}>
                    <div>Bid Buy: {selectedRow.Bid_buy_ucuzluk_skoru !== null && selectedRow.Bid_buy_ucuzluk_skoru !== undefined ? (selectedRow.Bid_buy_ucuzluk_skoru > 0 ? '+' : '') + selectedRow.Bid_buy_ucuzluk_skoru.toFixed(2) : 'N/A'}</div>
                    <div>Front Buy: {selectedRow.Front_buy_ucuzluk_skoru !== null && selectedRow.Front_buy_ucuzluk_skoru !== undefined ? (selectedRow.Front_buy_ucuzluk_skoru > 0 ? '+' : '') + selectedRow.Front_buy_ucuzluk_skoru.toFixed(2) : 'N/A'}</div>
                    <div>Ask Buy: {selectedRow.Ask_buy_ucuzluk_skoru !== null && selectedRow.Ask_buy_ucuzluk_skoru !== undefined ? (selectedRow.Ask_buy_ucuzluk_skoru > 0 ? '+' : '') + selectedRow.Ask_buy_ucuzluk_skoru.toFixed(2) : 'N/A'}</div>
                  </div>
                </div>
                
                <div style={{ marginBottom: '10px' }}>
                  <strong>Pahalılık Skorları:</strong>
                  <div style={{ marginLeft: '10px', fontSize: '0.9em' }}>
                    <div>Ask Sell: {selectedRow.Ask_sell_pahalilik_skoru !== null && selectedRow.Ask_sell_pahalilik_skoru !== undefined ? (selectedRow.Ask_sell_pahalilik_skoru > 0 ? '+' : '') + selectedRow.Ask_sell_pahalilik_skoru.toFixed(2) : 'N/A'}</div>
                    <div>Front Sell: {selectedRow.Front_sell_pahalilik_skoru !== null && selectedRow.Front_sell_pahalilik_skoru !== undefined ? (selectedRow.Front_sell_pahalilik_skoru > 0 ? '+' : '') + selectedRow.Front_sell_pahalilik_skoru.toFixed(2) : 'N/A'}</div>
                    <div>Bid Sell: {selectedRow.Bid_sell_pahalilik_skoru !== null && selectedRow.Bid_sell_pahalilik_skoru !== undefined ? (selectedRow.Bid_sell_pahalilik_skoru > 0 ? '+' : '') + selectedRow.Bid_sell_pahalilik_skoru.toFixed(2) : 'N/A'}</div>
                  </div>
                </div>
                
                <div style={{ marginBottom: '10px' }}>
                  <strong>Final Skorlar:</strong>
                  <div style={{ marginLeft: '10px', fontSize: '0.9em' }}>
                    <div>Final BB: {selectedRow.Final_BB_skor !== null && selectedRow.Final_BB_skor !== undefined ? selectedRow.Final_BB_skor.toFixed(2) : 'N/A'}</div>
                    <div>Final FB: {selectedRow.Final_FB_skor !== null && selectedRow.Final_FB_skor !== undefined ? selectedRow.Final_FB_skor.toFixed(2) : 'N/A'}</div>
                    <div>Final AB: {selectedRow.Final_AB_skor !== null && selectedRow.Final_AB_skor !== undefined ? selectedRow.Final_AB_skor.toFixed(2) : 'N/A'}</div>
                    <div>Final AS: {selectedRow.Final_AS_skor !== null && selectedRow.Final_AS_skor !== undefined ? selectedRow.Final_AS_skor.toFixed(2) : 'N/A'}</div>
                    <div>Final FS: {selectedRow.Final_FS_skor !== null && selectedRow.Final_FS_skor !== undefined ? selectedRow.Final_FS_skor.toFixed(2) : 'N/A'}</div>
                    <div>Final BS: {selectedRow.Final_BS_skor !== null && selectedRow.Final_BS_skor !== undefined ? selectedRow.Final_BS_skor.toFixed(2) : 'N/A'}</div>
                    <div>Final SAS: {selectedRow.Final_SAS_skor !== null && selectedRow.Final_SAS_skor !== undefined ? selectedRow.Final_SAS_skor.toFixed(2) : 'N/A'}</div>
                    <div>Final SFS: {selectedRow.Final_SFS_skor !== null && selectedRow.Final_SFS_skor !== undefined ? selectedRow.Final_SFS_skor.toFixed(2) : 'N/A'}</div>
                    <div>Final SBS: {selectedRow.Final_SBS_skor !== null && selectedRow.Final_SBS_skor !== undefined ? selectedRow.Final_SBS_skor.toFixed(2) : 'N/A'}</div>
                  </div>
                </div>
                
                {selectedRow.overlay_spread !== null && selectedRow.overlay_spread !== undefined && (
                  <div>
                    <strong>Spread:</strong> {selectedRow.overlay_spread.toFixed(4)}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* Rank Section */}
        {(selectedRow?.fbtot_rank_raw !== null && selectedRow?.fbtot_rank_raw !== undefined) ||
         (selectedRow?.sfstot_rank_raw !== null && selectedRow?.sfstot_rank_raw !== undefined) ? (
          <div className="inspector-section">
            <h3>Rank (0–1)</h3>
            
            {/* Fbtot Rank */}
            {selectedRow.fbtot_rank_raw !== null && selectedRow.fbtot_rank_raw !== undefined && (
              <div className="inspector-field-group">
                <div className="field-group-label">Fbtot Rank:</div>
                <div className="inspector-field">
                  <span className="field-label">Raw Rank:</span>
                  <span className="field-value">{selectedRow.fbtot_rank_raw}</span>
                </div>
                <div className="inspector-field">
                  <span className="field-label">Normalized (0–1):</span>
                  <span className="field-value">
                    {selectedRow.fbtot_rank_norm !== null && selectedRow.fbtot_rank_norm !== undefined
                      ? selectedRow.fbtot_rank_norm.toFixed(2)
                      : 'N/A'}
                  </span>
                </div>
              </div>
            )}
            
            {/* SFStot Rank */}
            {selectedRow.sfstot_rank_raw !== null && selectedRow.sfstot_rank_raw !== undefined && (
              <div className="inspector-field-group">
                <div className="field-group-label">SFStot Rank:</div>
                <div className="inspector-field">
                  <span className="field-label">Raw Rank:</span>
                  <span className="field-value">{selectedRow.sfstot_rank_raw}</span>
                </div>
                <div className="inspector-field">
                  <span className="field-label">Normalized (0–1):</span>
                  <span className="field-value">
                    {selectedRow.sfstot_rank_norm !== null && selectedRow.sfstot_rank_norm !== undefined
                      ? selectedRow.sfstot_rank_norm.toFixed(2)
                      : 'N/A'}
                  </span>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
  
  async function handleAction(action) {
    if (saving) return
    
    setSaving(true)
    try {
      const response = await fetch('http://localhost:8000/api/market-data/order-action', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: PREF_IBKR,
          gate_status: gate_status?.gate_status || 'MANUAL_REVIEW',
          user_action: action,
          user_note: actionNote || null,
        }),
      })
      
      if (response.ok) {
        const result = await response.json()
        // Update local state
        selectedRow.user_action = action
        selectedRow.user_note = actionNote || null
        // Trigger parent refresh if needed
        window.location.reload() // Simple refresh for now
      } else {
        alert('Failed to save action')
      }
    } catch (error) {
      console.error('Error saving action:', error)
      alert('Error saving action')
    } finally {
      setSaving(false)
    }
  }
}

export default StateReasonInspector

