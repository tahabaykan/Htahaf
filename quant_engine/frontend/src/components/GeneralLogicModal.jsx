import React, { useState, useEffect, useCallback, useRef } from 'react';
import './GeneralLogicModal.css';

/**
 * GeneralLogicModal - QE General Logic Formulas Editor
 * Displays ALL configurable formula parameters exactly as specified
 */
const GeneralLogicModal = ({ isOpen, onClose }) => {
  const [config, setConfig] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoSaveStatus, setAutoSaveStatus] = useState(null); // 'saving' | 'saved' | 'error'
  const autoSaveTimer = useRef(null);

  // Section definitions with exact names from spec
  const sections = [
    { id: 'exposure', name: '2️⃣ EXPOSURE MODU & THRESHOLD\'LAR', icon: '📊' },
    { id: 'karbotu', name: '3️⃣ KARBOTU ENGINE - KÂR ALMA MOTORU', icon: '💰' },
    { id: 'reducemore', name: '4️⃣ REDUCEMORE ENGINE - RİSK AZALTMA', icon: '⚠️' },
    { id: 'lt_trim', name: '5️⃣ LT TRIM ENGINE - EXECUTION', icon: '✂️' },
    { id: 'addnewpos', name: '6️⃣ ADDNEWPOS ENGINE - YENİ POZİSYON', icon: '➕' },
    { id: 'mm', name: '7️⃣ MM ENGINE - MARKET MAKING', icon: '🔄' },
    { id: 'jfin', name: '8️⃣ JFIN ENGINE - TUM CSV SEÇİCİ', icon: '🎯' },
    { id: 'proposal', name: '9️⃣ PROPOSAL & APPROVAL AKIŞI', icon: '📋' },
    { id: 'risk', name: '🔟 RISK REGİMELERİ', icon: '🛡️' },
    { id: 'order_lifecycle', name: '⏱️ ORDER LIFECYCLE (TTL)', icon: '⏱️' },
  ];

  // Fetch config from backend
  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/general-logic');
      const data = await response.json();
      if (data.success) {
        setConfig(data.config);
      } else {
        setError('Failed to load configuration');
      }
    } catch (err) {
      setError(`Error loading config: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchConfig();
    }
    return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current); };
  }, [isOpen, fetchConfig]);

  // Auto-save to backend (debounced)
  const doAutoSave = useCallback(async (configToSave) => {
    try {
      setAutoSaveStatus('saving');
      const updates = {};
      Object.entries(configToSave).forEach(([key, data]) => {
        updates[key] = parseValue(data.value, data.type);
      });

      const response = await fetch('/api/general-logic/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates })
      });

      const result = await response.json();
      if (result.success) {
        setAutoSaveStatus('saved');
        setTimeout(() => setAutoSaveStatus(null), 1500);
      } else {
        setAutoSaveStatus('error');
        setTimeout(() => setAutoSaveStatus(null), 3000);
      }
    } catch (err) {
      setAutoSaveStatus('error');
      setTimeout(() => setAutoSaveStatus(null), 3000);
    }
  }, []);

  const scheduleAutoSave = useCallback((newConfig) => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => doAutoSave(newConfig), 800);
  }, [doAutoSave]);

  // Handle value change + auto-save
  const handleValueChange = (key, newValue) => {
    setConfig(prev => {
      const updated = {
        ...prev,
        [key]: {
          ...prev[key],
          value: newValue
        }
      };
      scheduleAutoSave(updated);
      return updated;
    });
  };

  // Parse value based on type
  const parseValue = (value, type) => {
    if (type === 'json') {
      try {
        return typeof value === 'string' ? JSON.parse(value) : value;
      } catch {
        return value;
      }
    } else if (type === 'float') {
      return parseFloat(value) || 0;
    } else if (type === 'int') {
      return parseInt(value, 10) || 0;
    } else if (type === 'bool') {
      return value === true || value === 'true';
    }
    return value;
  };

  // parseValue is needed before doAutoSave, but it's already defined above

  // Reset to defaults
  const handleReset = async () => {
    if (!window.confirm('Reset all values to defaults? This cannot be undone.')) {
      return;
    }
    setError(null);
    try {
      setAutoSaveStatus('saving');
      const response = await fetch('/api/general-logic/reset', { method: 'POST' });
      const result = await response.json();
      if (result.success) {
        setAutoSaveStatus('saved');
        fetchConfig();
        setTimeout(() => setAutoSaveStatus(null), 1500);
      } else {
        setError(result.detail || 'Failed to reset');
        setAutoSaveStatus('error');
      }
    } catch (err) {
      setError(`Reset error: ${err.message}`);
      setAutoSaveStatus('error');
    }
  };

  // Get params for a section
  const getParamsForSection = (sectionId) => {
    const params = {};
    Object.entries(config).forEach(([key, data]) => {
      if (key.startsWith(sectionId + '.')) {
        params[key] = data;
      }
    });
    return params;
  };

  // Render input based on type and key
  const renderInput = (key, data) => {
    const { value, type } = data;

    // Special: Spread threshold tables (2D arrays)
    if (key.includes('spread_thresholds') && Array.isArray(value)) {
      return (
        <div className="threshold-table-container">
          <table className="threshold-table">
            <thead>
              <tr>
                <th>Spread ($)</th>
                <th>Min Score</th>
              </tr>
            </thead>
            <tbody>
              {value.map((row, idx) => (
                <tr key={idx}>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row[0]}
                      onChange={(e) => {
                        const newValue = [...value];
                        newValue[idx] = [parseFloat(e.target.value) || 0, row[1]];
                        handleValueChange(key, newValue);
                      }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row[1]}
                      onChange={(e) => {
                        const newValue = [...value];
                        newValue[idx] = [row[0], parseFloat(e.target.value) || 0];
                        handleValueChange(key, newValue);
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    // Special: Portfolio thresholds (array of objects)
    if (key.includes('rules.thresholds') && Array.isArray(value)) {
      return (
        <div className="threshold-table-container">
          <table className="threshold-table portfolio-rules">
            <thead>
              <tr>
                <th>Max Port %</th>
                <th>MAXALW Mult</th>
                <th>Port %</th>
              </tr>
            </thead>
            <tbody>
              {value.map((row, idx) => (
                <tr key={idx}>
                  <td>
                    <input
                      type="number"
                      step="1"
                      value={row.max_portfolio_percent}
                      onChange={(e) => {
                        const newValue = [...value];
                        newValue[idx] = { ...row, max_portfolio_percent: parseInt(e.target.value) || 0 };
                        handleValueChange(key, newValue);
                      }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.maxalw_multiplier}
                      onChange={(e) => {
                        const newValue = [...value];
                        newValue[idx] = { ...row, maxalw_multiplier: parseFloat(e.target.value) || 0 };
                        handleValueChange(key, newValue);
                      }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.1"
                      value={row.portfolio_percent}
                      onChange={(e) => {
                        const newValue = [...value];
                        newValue[idx] = { ...row, portfolio_percent: parseFloat(e.target.value) || 0 };
                        handleValueChange(key, newValue);
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    // Simple array (like modes, engines_throttled, special_cgrups)
    if (type === 'json' && Array.isArray(value) && value.length > 0 && typeof value[0] === 'string') {
      return (
        <input
          type="text"
          className="array-input"
          value={JSON.stringify(value)}
          onChange={(e) => {
            try {
              const parsed = JSON.parse(e.target.value);
              handleValueChange(key, parsed);
            } catch {
              // Keep editing
            }
          }}
        />
      );
    }

    // Boolean
    if (type === 'bool') {
      return (
        <label className="bool-toggle">
          <input
            type="checkbox"
            checked={value === true || value === 'true'}
            onChange={(e) => handleValueChange(key, e.target.checked)}
          />
          <span className={value ? 'on' : 'off'}>{value ? 'ON' : 'OFF'}</span>
        </label>
      );
    }

    // Float
    if (type === 'float') {
      return (
        <input
          type="number"
          step="0.01"
          value={value}
          onChange={(e) => handleValueChange(key, parseFloat(e.target.value) || 0)}
        />
      );
    }

    // Int
    if (type === 'int') {
      return (
        <input
          type="number"
          step="1"
          value={value}
          onChange={(e) => handleValueChange(key, parseInt(e.target.value, 10) || 0)}
        />
      );
    }

    // Default string
    return (
      <input
        type="text"
        value={value}
        onChange={(e) => handleValueChange(key, e.target.value)}
      />
    );
  };

  // Format key for display
  const formatKeyName = (key) => {
    // Remove section prefix and format nicely
    const parts = key.split('.');
    const name = parts.slice(1).join('.');
    return name
      .replace(/_/g, ' ')
      .replace(/\./g, ' → ')
      .toUpperCase();
  };

  if (!isOpen) return null;

  return (
    <div className="gl-modal-overlay" onClick={onClose}>
      <div className="gl-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="gl-header">
          <div className="gl-title">
            <span className="gl-icon">⚡</span>
            <h2>QE GENERAL LOGIC FORMULAS</h2>
          </div>
          <div className="gl-subtitle">
            All configurable parameters • Saved to qegenerallogic.csv
          </div>
          <button className="gl-close" onClick={onClose}>×</button>
        </div>

        {/* Toolbar */}
        <div className="gl-toolbar">
          {autoSaveStatus === 'saving' && <span className="gl-autosave saving">⏳ Saving...</span>}
          {autoSaveStatus === 'saved' && <span className="gl-autosave saved">✓ Saved</span>}
          {autoSaveStatus === 'error' && <span className="gl-autosave error">⚠️ Save failed</span>}
          <button
            className="gl-btn reset"
            onClick={handleReset}
          >
            🔄 RESET DEFAULT
          </button>
          <button
            className="gl-btn refresh"
            onClick={fetchConfig}
            disabled={loading}
          >
            🔃 Reload
          </button>
        </div>

        {/* Messages */}
        {error && <div className="gl-error">❌ {error}</div>}

        {/* Content */}
        <div className="gl-content">
          {loading ? (
            <div className="gl-loading">Loading configuration...</div>
          ) : (
            <div className="gl-sections">
              {sections.map(section => {
                const sectionParams = getParamsForSection(section.id);
                const paramCount = Object.keys(sectionParams).length;

                if (paramCount === 0) return null;

                return (
                  <div key={section.id} className="gl-section">
                    <div className="gl-section-header">
                      <span className="section-icon">{section.icon}</span>
                      <span className="section-name">{section.name}</span>
                      <span className="section-count">{paramCount}</span>
                    </div>
                    <div className="gl-section-content">
                      {Object.entries(sectionParams).map(([key, data]) => (
                        <div key={key} className="gl-param">
                          <div className="param-key">{formatKeyName(key)}</div>
                          <div className="param-value">
                            {renderInput(key, data)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="gl-footer">
          <span>📁 qegenerallogic.csv</span>
          <span>•</span>
          <span>Changes apply on next engine cycle</span>
        </div>
      </div>
    </div>
  );
};

export default GeneralLogicModal;
