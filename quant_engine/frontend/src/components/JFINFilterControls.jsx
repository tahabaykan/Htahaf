import React from 'react'
import './JFINFilterControls.css'

/**
 * JFINFilterControls - Compact inline filter controls for JFIN pools
 * Matches AddnewposSettingsPanel style
 */
function JFINFilterControls({
    poolType,
    filters,
    onFilterChange,
    onApplyFilters,
    onClearFilters
}) {
    const isLong = poolType === 'BB' || poolType === 'FB'
    const scoreLabel = isLong ? 'FBtot' : 'SFStot'
    const scoreKey = isLong ? 'fbtot' : 'sfstot'

    return (
        <div className="jfin-filter-row">
            {/* GORT Range Filter */}
            <div className="jfin-filter-group">
                <label>GORT:</label>
                <input
                    type="number"
                    step="0.01"
                    placeholder="Min"
                    value={filters.gort_min}
                    onChange={(e) => onFilterChange({ ...filters, gort_min: e.target.value })}
                />
                <span className="sep">—</span>
                <input
                    type="number"
                    step="0.01"
                    placeholder="Max"
                    value={filters.gort_max}
                    onChange={(e) => onFilterChange({ ...filters, gort_max: e.target.value })}
                />
            </div>

            {/* FBtot/SFStot Filter */}
            <div className="jfin-filter-group">
                <label>{scoreLabel}:</label>
                <input
                    type="number"
                    step="0.01"
                    placeholder="Val"
                    value={filters[`${scoreKey}_value`]}
                    onChange={(e) => onFilterChange({
                        ...filters,
                        [`${scoreKey}_value`]: e.target.value
                    })}
                />
                <div className="jfin-mini-radio">
                    <label className={filters[`${scoreKey}_type`] === 'below' ? 'active' : ''}>
                        <input
                            type="radio"
                            name={`${poolType}-${scoreKey}-type`}
                            value="below"
                            checked={filters[`${scoreKey}_type`] === 'below'}
                            onChange={() => onFilterChange({ ...filters, [`${scoreKey}_type`]: 'below' })}
                        />
                        &lt;
                    </label>
                    <label className={filters[`${scoreKey}_type`] === 'above' ? 'active' : ''}>
                        <input
                            type="radio"
                            name={`${poolType}-${scoreKey}-type`}
                            value="above"
                            checked={filters[`${scoreKey}_type`] === 'above'}
                            onChange={() => onFilterChange({ ...filters, [`${scoreKey}_type`]: 'above' })}
                        />
                        &gt;
                    </label>
                </div>
            </div>

            {/* SMA63 chg Filter */}
            <div className="jfin-filter-group">
                <label>SMA63:</label>
                <input
                    type="number"
                    step="0.01"
                    placeholder="Val"
                    value={filters.sma63_value}
                    onChange={(e) => onFilterChange({ ...filters, sma63_value: e.target.value })}
                />
                <div className="jfin-mini-radio">
                    <label className={filters.sma63_type === 'below' ? 'active' : ''}>
                        <input
                            type="radio"
                            name={`${poolType}-sma63-type`}
                            value="below"
                            checked={filters.sma63_type === 'below'}
                            onChange={() => onFilterChange({ ...filters, sma63_type: 'below' })}
                        />
                        &lt;
                    </label>
                    <label className={filters.sma63_type === 'above' ? 'active' : ''}>
                        <input
                            type="radio"
                            name={`${poolType}-sma63-type`}
                            value="above"
                            checked={filters.sma63_type === 'above'}
                            onChange={() => onFilterChange({ ...filters, sma63_type: 'above' })}
                        />
                        &gt;
                    </label>
                </div>
            </div>

            {/* Action Buttons */}
            <div className="jfin-filter-actions">
                <button className="jfin-apply-btn" onClick={onApplyFilters}>
                    ✓ Uygula
                </button>
                <button className="jfin-clear-btn" onClick={onClearFilters}>
                    ✕ Clear
                </button>
            </div>
        </div>
    )
}

export default JFINFilterControls
