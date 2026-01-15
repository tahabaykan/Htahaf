import React from 'react'
import './ControlBar.css'

function ControlBar({
  onLoadCsv,
  onRefresh,
  autoRefresh,
  onAutoRefreshChange,
  filter,
  onFilterChange,
  loading,
  stateFilter,
  onStateFilterChange,
  spreadMax,
  onSpreadMaxChange,
  avgAdvMin,
  onAvgAdvMinChange,
  finalThgMin,
  onFinalThgMinChange,
  shortFinalMin,
  onShortFinalMinChange,
  dosGrupFilter,
  onDosGrupFilterChange,
  bidBuyUcuzlukMax,
  onBidBuyUcuzlukMaxChange,
  askSellPahalilikMin,
  onAskSellPahalilikMinChange,
  finalBBMin,
  onFinalBBMinChange,
  finalSASMax,
  onFinalSASMaxChange,
  finalFBMin,
  onFinalFBMinChange,
  finalSFSMax,
  onFinalSFSMaxChange,
  gortMin,
  onGortMinChange,
  gortMax,
  onGortMaxChange,
  fbtotMin,
  onFbtotMinChange,
  sfstotMax,
  onSfstotMaxChange,
  presets,
  presetName,
  onPresetNameChange,
  onPresetSave,
  onPresetLoad,
  onPresetsLoad,
  onClearAllFilters,
  focusMode,
  onFocusModeChange,
  executionMode,
  onExecutionModeChange
}) {
  const handleStateToggle = (state) => {
    if (stateFilter.includes(state)) {
      onStateFilterChange(stateFilter.filter(s => s !== state))
    } else {
      onStateFilterChange([...stateFilter, state])
    }
  }

  return (
    <div className="control-bar">
      <div className="control-section">
        <div className="control-group">
          <button 
            onClick={onLoadCsv} 
            disabled={loading}
            className="btn btn-secondary"
            title="CSV is automatically loaded on startup. Use this to reload if CSV was updated."
          >
            {loading ? 'Reloading...' : 'Reload CSV'}
          </button>
          <button 
            onClick={onRefresh}
            className="btn btn-secondary"
          >
            Refresh
          </button>
          <button
            onClick={() => onAutoRefreshChange(!autoRefresh)}
            className={`btn ${autoRefresh ? 'btn-danger' : 'btn-success'}`}
            title="Auto refresh is fallback mode (only active when WebSocket is disconnected)"
          >
            {autoRefresh ? 'Stop Auto Refresh (Fallback)' : 'Start Auto Refresh (Fallback)'}
          </button>
        </div>
        
        <div className="control-group">
          <button
            onClick={() => onFocusModeChange(!focusMode)}
            className={`btn ${focusMode ? 'btn-active' : 'btn-inactive'}`}
          >
            Focus Mode: {focusMode ? 'ON' : 'OFF'}
          </button>
        </div>
        
        <div className="control-group">
          <label className="control-label">Execution Mode:</label>
          <select
            value={executionMode}
            onChange={(e) => onExecutionModeChange(e.target.value)}
            className="execution-mode-select"
          >
            <option value="PREVIEW">PREVIEW</option>
            <option value="SEMI_AUTO">SEMI_AUTO</option>
            <option value="FULL_AUTO">FULL_AUTO</option>
          </select>
        </div>
        
        {presets && (
          <div className="control-group preset-group">
            <label className="control-label preset-label">Preset:</label>
            <select
              value=""
              onChange={(e) => { if (e.target.value) onPresetLoad(e.target.value) }}
              className="preset-select"
            >
              <option value="">Select preset</option>
              {presets.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <input
              type="text"
              placeholder="Preset name"
              value={presetName}
              onChange={(e) => onPresetNameChange(e.target.value)}
              className="preset-name-input"
            />
            <button
              className="btn btn-secondary"
              onClick={onPresetSave}
              disabled={!presetName}
            >
              Save Preset
            </button>
          </div>
        )}
        
        {onClearAllFilters && (
          <div className="control-group">
            <button
              onClick={onClearAllFilters}
              className="btn btn-warning"
              title="Clear all filter values"
            >
              Clear All Filters
            </button>
          </div>
        )}
      </div>
      
      <div className="control-section">
        <div className="control-group">
          <input
            type="text"
            placeholder="Filter by symbol, CMON, or CGRUP..."
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
            className="filter-input"
          />
        </div>
      </div>
      
      <div className="control-section filters-section">
        <div className="filter-group">
          <label className="filter-label">State:</label>
          <div className="checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={stateFilter.includes('IDLE')}
                onChange={() => handleStateToggle('IDLE')}
              />
              IDLE
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={stateFilter.includes('WATCH')}
                onChange={() => handleStateToggle('WATCH')}
              />
              WATCH
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={stateFilter.includes('CANDIDATE')}
                onChange={() => handleStateToggle('CANDIDATE')}
              />
              CANDIDATE
            </label>
          </div>
        </div>
        
        <div className="filter-group">
          <label className="filter-label">Spread max (cents):</label>
          <input
            type="number"
            step="0.01"
            placeholder="e.g. 0.05"
            value={spreadMax}
            onChange={(e) => onSpreadMaxChange(e.target.value)}
            className="filter-number-input"
          />
        </div>
        
        <div className="filter-group">
          <label className="filter-label">AVG_ADV min:</label>
          <input
            type="number"
            step="1"
            placeholder="e.g. 5000"
            value={avgAdvMin}
            onChange={(e) => onAvgAdvMinChange(e.target.value)}
            className="filter-number-input"
          />
        </div>
        
        <div className="filter-group">
          <label className="filter-label">FINAL_THG min:</label>
          <input
            type="number"
            step="0.01"
            placeholder="e.g. 1.2"
            value={finalThgMin}
            onChange={(e) => onFinalThgMinChange(e.target.value)}
            className="filter-number-input"
          />
        </div>
        
        <div className="filter-group">
          <label className="filter-label">SHORT_FINAL min:</label>
          <input
            type="number"
            step="0.01"
            placeholder="e.g. 0.5"
            value={shortFinalMin}
            onChange={(e) => onShortFinalMinChange(e.target.value)}
            className="filter-number-input"
          />
        </div>
        
        {dosGrupFilter !== undefined && (
          <div className="filter-group">
            <label className="filter-label">DOS GRUP:</label>
            <input
              type="text"
              placeholder="Filter by DOS GRUP (e.g., titrek, heldff, heldkuponlu)..."
              value={dosGrupFilter}
              onChange={(e) => onDosGrupFilterChange(e.target.value)}
              className="filter-input"
            />
          </div>
        )}
        
        {bidBuyUcuzlukMax !== undefined && (
          <div className="filter-group">
            <label className="filter-label">BB Ucuz max:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 1.0"
              value={bidBuyUcuzlukMax}
              onChange={(e) => onBidBuyUcuzlukMaxChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {askSellPahalilikMin !== undefined && (
          <div className="filter-group">
            <label className="filter-label">AS Pahal min:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 1.0"
              value={askSellPahalilikMin}
              onChange={(e) => onAskSellPahalilikMinChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {finalBBMin !== undefined && (
          <div className="filter-group">
            <label className="filter-label">Final BB min:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 100"
              value={finalBBMin}
              onChange={(e) => onFinalBBMinChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {finalSASMax !== undefined && (
          <div className="filter-group">
            <label className="filter-label">Final SAS max:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 100"
              value={finalSASMax}
              onChange={(e) => onFinalSASMaxChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {finalFBMin !== undefined && (
          <div className="filter-group">
            <label className="filter-label">Final FB min:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 100"
              value={finalFBMin}
              onChange={(e) => onFinalFBMinChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {finalSFSMax !== undefined && (
          <div className="filter-group">
            <label className="filter-label">Final SFS max:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 100"
              value={finalSFSMax}
              onChange={(e) => onFinalSFSMaxChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {gortMin !== undefined && (
          <div className="filter-group">
            <label className="filter-label">GORT min:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 0.5"
              value={gortMin}
              onChange={(e) => onGortMinChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {gortMax !== undefined && (
          <div className="filter-group">
            <label className="filter-label">GORT max:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 2.0"
              value={gortMax}
              onChange={(e) => onGortMaxChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {fbtotMin !== undefined && (
          <div className="filter-group">
            <label className="filter-label">Fbtot min:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 1.0"
              value={fbtotMin}
              onChange={(e) => onFbtotMinChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
        
        {sfstotMax !== undefined && (
          <div className="filter-group">
            <label className="filter-label">SFStot max:</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 1.0"
              value={sfstotMax}
              onChange={(e) => onSfstotMaxChange(e.target.value)}
              className="filter-number-input"
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default ControlBar
