/**
 * Deeper Analysis Panel - SLOW PATH Component
 * 
 * 🔵 SLOW PATH - Tick-by-tick data (GOD, ROD, GRPAN)
 * 
 * This panel is for advanced analysis only.
 * It does NOT affect the main trading algo (RUNALL, ADDNEWPOS, KARBOTU).
 * 
 * Features:
 * - Enable/disable tick-by-tick collection
 * - View GOD (Group Outlier Detection)
 * - View ROD (Relative Outlier Detection)
 * - View GRPAN (Group Analysis)
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import './DeeperAnalysisPanel.css';

const API_BASE = 'http://localhost:8000/api/market-data';

const DeeperAnalysisPanel = ({ selectedSymbol: initialSelectedSymbol = null, workerResult = null }) => {
  // Load enabled state from localStorage on mount
  const [isEnabled, setIsEnabled] = useState(false);
  const [deepData, setDeepData] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState(initialSelectedSymbol);
  
  // Sorting state
  const [sortColumn, setSortColumn] = useState(null); // 'god', 'rod', 'grpan', 'tick_count', 'symbol', 'dos_grup', 'srpan_score', 'spread'
  const [sortDirection, setSortDirection] = useState('asc'); // 'asc' or 'desc'
  
  // Filter state
  const [groupFilter, setGroupFilter] = useState('');
  
  // Static data cache (GROUP, CGRUP)
  const [staticDataCache, setStaticDataCache] = useState({});
  
  // Update deepData when workerResult changes
  useEffect(() => {
    if (!workerResult) {
      console.log('⚠️ No worker result');
      return;
    }
    
    console.log('📊 Raw workerResult:', {
      keys: Object.keys(workerResult),
      hasData: !!workerResult.data,
      dataType: typeof workerResult.data,
      isArray: Array.isArray(workerResult.data),
      dataKeys: workerResult.data && typeof workerResult.data === 'object' ? Object.keys(workerResult.data).slice(0, 5) : null,
      fullStructure: JSON.stringify(workerResult).substring(0, 500)
    });
    
    // workerResult format from endpoint: {success: true, job_id: ..., data: {symbol: {...}}, processed_count: 440, ...}
    // We need the 'data' field which contains {symbol: {...}}
    let symbolsData = workerResult.data;
    
    if (!symbolsData || typeof symbolsData !== 'object') {
      console.log('⚠️ No valid data in workerResult.data:', { workerResult, symbolsData });
      return;
    }
    
    // If symbolsData has a 'data' field (nested), use that
    if (symbolsData.data && typeof symbolsData.data === 'object') {
      symbolsData = symbolsData.data;
    }
    
    // Skip if it's an array or doesn't look like symbol data
    if (Array.isArray(symbolsData)) {
      console.log('⚠️ symbolsData is an array, not an object');
      return;
    }
    
    console.log('📊 Symbols data:', {
      symbolCount: Object.keys(symbolsData).length,
      firstSymbol: Object.keys(symbolsData)[0],
      firstSymbolData: symbolsData[Object.keys(symbolsData)[0]],
      sampleKeys: Object.keys(symbolsData).slice(0, 10)
    });
    
    // Convert worker result format to panel format
    const convertedData = {};
    let skippedCount = 0;
    
    for (const [symbol, symbolData] of Object.entries(symbolsData)) {
      // Skip if symbol is a metadata key (not a real symbol)
      if (['success', 'job_id', 'processed_count', 'total_symbols', 'timestamp'].includes(symbol)) {
        skippedCount++;
        continue;
      }
      
      if (symbolData && typeof symbolData === 'object' && !symbolData.error) {
        // Handle grpan field - can be object {value: ..., all_windows: ...} or just value
        let grpanValue = null;
        if (symbolData.grpan) {
          if (typeof symbolData.grpan === 'object' && symbolData.grpan.value != null) {
            grpanValue = symbolData.grpan.value;
          } else if (typeof symbolData.grpan === 'number') {
            grpanValue = symbolData.grpan;
          }
        }
        
        // Handle SRPAN data
        let srpanData = null;
        if (symbolData.srpan && typeof symbolData.srpan === 'object') {
          srpanData = {
            srpan_score: symbolData.srpan.srpan_score || 0,
            grpan1: symbolData.srpan.grpan1,
            grpan1_conf: symbolData.srpan.grpan1_conf || 0,
            grpan2: symbolData.srpan.grpan2,
            grpan2_conf: symbolData.srpan.grpan2_conf || 0,
            spread: symbolData.srpan.spread || 0,
            direction: symbolData.srpan.direction || 'N/A',
            balance_score: symbolData.srpan.balance_score || 0,
            total_score: symbolData.srpan.total_score || 0,
            spread_score: symbolData.srpan.spread_score || 0
          };
        }
        
        convertedData[symbol] = {
          god: symbolData.god != null ? symbolData.god : null,
          rod: symbolData.rod != null ? symbolData.rod : null,
          grpan: grpanValue,
          tick_count: symbolData.tick_count || 0,
          srpan: srpanData
        };
      } else {
        skippedCount++;
      }
    }
    
    console.log('📊 Converted data:', {
      symbolCount: Object.keys(convertedData).length,
      skippedCount: skippedCount,
      firstSymbol: Object.keys(convertedData)[0],
      firstSymbolData: convertedData[Object.keys(convertedData)[0]],
      sampleSymbols: Object.keys(convertedData).slice(0, 5)
    });
    
    if (Object.keys(convertedData).length > 0) {
      setDeepData(convertedData);
      setLastUpdate(new Date());
      setIsEnabled(true); // Worker result means tick-by-tick is enabled
      console.log('✅ Updated deepData with', Object.keys(convertedData).length, 'symbols');
      
      // Fetch static data (GROUP, CGRUP) for all symbols
      fetchStaticData(Object.keys(convertedData));
    } else {
      console.log('⚠️ No symbols converted, all were skipped or invalid');
    }
  }, [workerResult]);
  
  // Fetch static data (GROUP, CGRUP) from merged endpoint
  const fetchStaticData = useCallback(async (symbols) => {
    try {
      const response = await fetch(`${API_BASE}/merged`);
      const data = await response.json();
      
      if (data.success && data.data) {
        const cache = {};
        for (const record of data.data) {
          const symbol = record.PREF_IBKR;
          if (symbol) {
            cache[symbol] = {
              GROUP: record.GROUP || record.group || record.file_group,
              CGRUP: record.CGRUP || record.cgrup
            };
          }
        }
        setStaticDataCache(cache);
        console.log('✅ Loaded static data for', Object.keys(cache).length, 'symbols');
      }
    } catch (err) {
      console.error('Error fetching static data:', err);
    }
  }, []);
  
  // Auto-enable on mount if it was enabled before (only once)
  useEffect(() => {
    const savedEnabled = localStorage.getItem('deeper_analysis_enabled') === 'true'
    if (savedEnabled) {
      // Auto-enable tick-by-tick analysis if it was enabled before
      const enableIt = async () => {
        try {
          const response = await fetch(`${API_BASE}/deep-analysis/enable?enabled=true`, {
            method: 'POST'
          });
          const data = await response.json();
          if (data.success) {
            setIsEnabled(true);
          }
        } catch (err) {
          console.error('Auto-enable error:', err);
        }
      }
      enableIt()
    }
  }, []) // Only run once on mount

  // Fetch deep analysis status
  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/deep-analysis/all`);
      const data = await response.json();
      
      if (data.success) {
        setIsEnabled(data.enabled);
        setDeepData(data.data || {});
        setLastUpdate(new Date());
        setError(null);
      }
    } catch (err) {
      setError('Failed to fetch deep analysis status');
      console.error('Deep analysis fetch error:', err);
    }
  }, []);

  // Toggle tick-by-tick collection
  const toggleEnabled = useCallback(async (forceValue = null) => {
    setLoading(true);
    try {
      const newEnabled = forceValue !== null ? forceValue : !isEnabled;
      const response = await fetch(`${API_BASE}/deep-analysis/enable?enabled=${newEnabled}`, {
        method: 'POST'
      });
      const data = await response.json();
      
      if (data.success) {
        const enabledState = data.tick_by_tick_enabled !== undefined ? data.tick_by_tick_enabled : newEnabled;
        setIsEnabled(enabledState);
        // Save to localStorage
        localStorage.setItem('deeper_analysis_enabled', enabledState.toString());
        setError(null);
        // Refresh data after enabling
        if (enabledState) {
          setTimeout(() => fetchStatus(), 1000);
        }
      } else {
        setError(data.message || 'Failed to toggle deep analysis');
      }
    } catch (err) {
      setError('Failed to toggle deep analysis: ' + err.message);
      console.error('Toggle error:', err);
    } finally {
      setLoading(false);
    }
  }, [isEnabled, fetchStatus]);

  // Fetch data periodically when enabled (only if no worker result)
  useEffect(() => {
    // Only fetch from API if worker result is not available
    if (!workerResult || !workerResult.data) {
      fetchStatus();
      
      const interval = setInterval(() => {
        if (isEnabled && (!workerResult || !workerResult.data)) {
          fetchStatus();
        }
      }, 5000); // Refresh every 5 seconds when enabled

      return () => clearInterval(interval);
    }
  }, [isEnabled, fetchStatus, workerResult]);
  
  // Fix: Remove duplicate useEffect that was causing issues

  // Update selectedSymbol when prop changes
  useEffect(() => {
    if (initialSelectedSymbol) {
      setSelectedSymbol(initialSelectedSymbol);
    }
  }, [initialSelectedSymbol]);
  
  // Get data for selected symbol
  const selectedData = selectedSymbol ? deepData[selectedSymbol] : null;
  
  // Format DOS GRUP (heldkuponlu-c500 format) - helper function
  const formatDosGrup = (symbol) => {
    const staticData = staticDataCache[symbol];
    if (!staticData) return '-';
    
    const group = staticData.GROUP;
    if (!group) return '-';
    
    // Kuponlu gruplar için CGRUP ekle
    const kuponluGroups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta'];
    if (kuponluGroups.includes(group?.toLowerCase())) {
      const cgrup = staticData.CGRUP;
      if (cgrup) {
        return `${group}-${cgrup.toLowerCase()}`;
      }
    }
    
    return group;
  };
  
  // Filter and sort data
  const sortedData = useMemo(() => {
    let entries = Object.entries(deepData);
    
    // Apply group filter
    if (groupFilter.trim()) {
      const filterLower = groupFilter.toLowerCase().trim();
      entries = entries.filter(([symbol, data]) => {
        const dosGrup = formatDosGrup(symbol).toLowerCase();
        return dosGrup.includes(filterLower);
      });
    }
    
    // Apply sorting
    if (sortColumn) {
      entries = [...entries].sort(([symbolA, dataA], [symbolB, dataB]) => {
        let a, b;
        
        switch (sortColumn) {
          case 'symbol':
            a = symbolA;
            b = symbolB;
            break;
          case 'dos_grup':
            a = formatDosGrup(symbolA);
            b = formatDosGrup(symbolB);
            break;
          case 'god':
            a = dataA.god != null ? dataA.god : -Infinity;
            b = dataB.god != null ? dataB.god : -Infinity;
            break;
          case 'rod':
            a = dataA.rod != null ? dataA.rod : -Infinity;
            b = dataB.rod != null ? dataB.rod : -Infinity;
            break;
          case 'grpan':
            a = dataA.grpan != null ? dataA.grpan : -Infinity;
            b = dataB.grpan != null ? dataB.grpan : -Infinity;
            break;
          case 'tick_count':
            a = dataA.tick_count || 0;
            b = dataB.tick_count || 0;
            break;
          case 'srpan_score':
            a = dataA.srpan?.srpan_score || 0;
            b = dataB.srpan?.srpan_score || 0;
            break;
          case 'spread':
            a = dataA.srpan?.spread || 0;
            b = dataB.srpan?.spread || 0;
            break;
          default:
            return 0;
        }
        
        if (a < b) return sortDirection === 'asc' ? -1 : 1;
        if (a > b) return sortDirection === 'asc' ? 1 : -1;
        return 0;
      });
    }
    
    return entries;
  }, [deepData, sortColumn, sortDirection, groupFilter, staticDataCache]);
  
  // Handle header click for sorting
  const handleSort = (column) => {
    if (sortColumn === column) {
      // Toggle direction if same column
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      // New column, default to ascending
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  return (
    <div className="deeper-analysis-panel">
      <div className="deeper-analysis-header">
        <div className="header-left">
          <span className="path-badge slow">🔵 SLOW PATH</span>
          <h3>Deeper Analysis</h3>
        </div>
        <div className="header-right">
          <button 
            className={`toggle-btn ${isEnabled ? 'enabled' : 'disabled'}`}
            onClick={() => toggleEnabled()}
            disabled={loading}
          >
            {loading ? '...' : isEnabled ? '✓ Enabled' : '○ Disabled'}
          </button>
        </div>
      </div>

      {!isEnabled && (
        <div className="not-enabled-message">
          <p>⚠️ Tick-by-tick analysis is disabled</p>
          <p className="hint">
            Enable to collect GOD, ROD, and GRPAN data.
            <br />
            <small>Note: This does NOT affect trading algo (RUNALL, ADDNEWPOS, KARBOTU)</small>
          </p>
        </div>
      )}

      {isEnabled && (
        <>
          <div className="analysis-info">
            <span className="symbol-count">
              {sortedData.length} / {Object.keys(deepData).length} symbols
              {groupFilter && ` (filtered: ${groupFilter})`}
            </span>
            {lastUpdate && (
              <span className="last-update">
                Updated: {lastUpdate.toLocaleTimeString()}
              </span>
            )}
          </div>
          
          {/* Group Filter */}
          <div className="group-filter-container">
            <input
              type="text"
              placeholder="Filter by DOS GRUP (e.g., heldkuponlu-c500, heldff, titrek)..."
              value={groupFilter}
              onChange={(e) => setGroupFilter(e.target.value)}
              className="group-filter-input"
            />
            {groupFilter && (
              <button
                onClick={() => setGroupFilter('')}
                className="clear-filter-btn"
                title="Clear filter"
              >
                ✕
              </button>
            )}
          </div>

          {selectedSymbol && selectedData ? (
            <div className="symbol-analysis">
              <h4>{selectedSymbol}</h4>
              <div className="metrics-grid">
                <div className="metric-card">
                  <label>GOD</label>
                  <span className="value">
                    {selectedData.god != null ? selectedData.god.toFixed(4) : 'N/A'}
                  </span>
                  <small>Group Outlier Detection</small>
                </div>
                <div className="metric-card">
                  <label>ROD</label>
                  <span className="value">
                    {selectedData.rod != null ? selectedData.rod.toFixed(4) : 'N/A'}
                  </span>
                  <small>Relative Outlier Detection</small>
                </div>
                <div className="metric-card">
                  <label>GRPAN</label>
                  <span className="value">
                    {selectedData.grpan != null ? selectedData.grpan.toFixed(4) : 'N/A'}
                  </span>
                  <small>Group Analysis</small>
                </div>
                <div className="metric-card">
                  <label>Tick Count</label>
                  <span className="value">{selectedData.tick_count || 0}</span>
                  <small>Collected ticks</small>
                </div>
                {selectedData.srpan && (
                  <>
                    <div className="metric-card">
                      <label>SRPAN</label>
                      <span className="value">
                        {selectedData.srpan.srpan_score != null ? selectedData.srpan.srpan_score.toFixed(1) : 'N/A'}
                      </span>
                      <small>Spread Quality Score</small>
                    </div>
                    <div className="metric-card">
                      <label>G1 / G2</label>
                      <span className="value">
                        {selectedData.srpan.grpan1 != null ? `$${selectedData.srpan.grpan1.toFixed(2)}` : 'N/A'} / {' '}
                        {selectedData.srpan.grpan2 != null ? `$${selectedData.srpan.grpan2.toFixed(2)}` : 'N/A'}
                      </span>
                      <small>
                        {selectedData.srpan.grpan1_conf != null ? `${selectedData.srpan.grpan1_conf.toFixed(0)}%` : '-'} / {' '}
                        {selectedData.srpan.grpan2_conf != null ? `${selectedData.srpan.grpan2_conf.toFixed(0)}%` : '-'}
                      </small>
                    </div>
                    <div className="metric-card">
                      <label>Spread</label>
                      <span className="value">
                        {selectedData.srpan.spread != null ? `$${selectedData.srpan.spread.toFixed(2)}` : 'N/A'}
                      </span>
                      <small>{selectedData.srpan.direction || 'N/A'}</small>
                    </div>
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="no-selection">
              <p>Select a symbol to view detailed analysis</p>
            </div>
          )}

          <div className="analysis-table-container">
            <div className="analysis-table">
              <table>
                <thead>
                  <tr>
                    <th 
                      className={sortColumn === 'symbol' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('symbol')}
                    >
                      Symbol {sortColumn === 'symbol' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'dos_grup' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('dos_grup')}
                    >
                      DOS GRUP {sortColumn === 'dos_grup' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'god' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('god')}
                    >
                      GOD {sortColumn === 'god' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'rod' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('rod')}
                    >
                      ROD {sortColumn === 'rod' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'grpan' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('grpan')}
                    >
                      GRPAN {sortColumn === 'grpan' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'tick_count' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('tick_count')}
                    >
                      Ticks {sortColumn === 'tick_count' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'srpan_score' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('srpan_score')}
                    >
                      SRPAN {sortColumn === 'srpan_score' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th>G1</th>
                    <th>G1%</th>
                    <th>G2</th>
                    <th>G2%</th>
                    <th 
                      className={sortColumn === 'spread' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('spread')}
                    >
                      Spread {sortColumn === 'spread' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th>Dir</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedData.map(([symbol, data]) => {
                    const srpan = data.srpan || {};
                    const getSrpanColor = (score) => {
                      if (score >= 70) return '#32CD32'; // Lime green
                      if (score >= 50) return '#90EE90'; // Light green
                      if (score >= 30) return '#FFFFE0'; // Light yellow
                      return '#FFD700'; // Gold
                    };
                    
                    return (
                      <tr 
                        key={symbol} 
                        className={symbol === selectedSymbol ? 'selected' : ''}
                        onClick={() => setSelectedSymbol(symbol)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td className="symbol">{symbol}</td>
                        <td>{formatDosGrup(symbol)}</td>
                        <td>{data.god != null ? data.god.toFixed(2) : '-'}</td>
                        <td>{data.rod != null ? data.rod.toFixed(2) : '-'}</td>
                        <td>{data.grpan != null ? data.grpan.toFixed(2) : '-'}</td>
                        <td>{data.tick_count || 0}</td>
                        <td style={{ 
                          backgroundColor: srpan.srpan_score != null ? getSrpanColor(srpan.srpan_score) : 'transparent',
                          fontWeight: 'bold'
                        }}>
                          {srpan.srpan_score != null ? srpan.srpan_score.toFixed(1) : '-'}
                        </td>
                        <td>{srpan.grpan1 != null ? `$${srpan.grpan1.toFixed(2)}` : '-'}</td>
                        <td>{srpan.grpan1_conf != null ? `${srpan.grpan1_conf.toFixed(0)}%` : '-'}</td>
                        <td>{srpan.grpan2 != null ? `$${srpan.grpan2.toFixed(2)}` : '-'}</td>
                        <td>{srpan.grpan2_conf != null ? `${srpan.grpan2_conf.toFixed(0)}%` : '-'}</td>
                        <td>{srpan.spread != null ? `$${srpan.spread.toFixed(2)}` : '-'}</td>
                        <td>{srpan.direction || '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}
    </div>
  );
};

export default DeeperAnalysisPanel;



