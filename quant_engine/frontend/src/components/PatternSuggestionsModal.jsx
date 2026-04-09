import React, { useState, useEffect, useCallback, useMemo } from 'react';
import './PatternSuggestionsModal.css';

function PatternSuggestionsModal({ isOpen, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [sortConfig, setSortConfig] = useState({ key: 'score', direction: 'desc' });
    const [filterSignal, setFilterSignal] = useState('ALL'); // ALL, BUY, HOLD, UPCOMING, SHORT

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/pattern-suggestions/active');
            if (!response.ok) {
                const errData = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(errData.detail || `HTTP ${response.status}`);
            }
            const result = await response.json();
            if (result.success) {
                setData(result);
            } else {
                throw new Error('Failed to load pattern suggestions');
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (isOpen) {
            fetchData();
        }
    }, [isOpen, fetchData]);

    const handleExclude = async (trade) => {
        try {
            const params = new URLSearchParams({
                ticker: trade.ticker,
                direction: trade.direction,
                entry_date: trade.entry_date,
            });
            const response = await fetch(`/api/pattern-suggestions/exclude?${params}`, {
                method: 'POST',
            });
            if (response.ok) {
                setData(prev => {
                    if (!prev) return prev;
                    const tradeKey = `${trade.ticker}_${trade.direction}_${trade.entry_date}`;
                    const movedTrade = { ...trade, excluded: true };
                    return {
                        ...prev,
                        included: prev.included.filter(t => `${t.ticker}_${t.direction}_${t.entry_date}` !== tradeKey),
                        excluded: [...prev.excluded, movedTrade],
                        included_count: prev.included_count - 1,
                        excluded_count: prev.excluded_count + 1,
                    };
                });
            }
        } catch (err) {
            console.error('Error excluding trade:', err);
        }
    };

    const handleInclude = async (trade) => {
        try {
            const params = new URLSearchParams({
                ticker: trade.ticker,
                direction: trade.direction,
                entry_date: trade.entry_date,
            });
            const response = await fetch(`/api/pattern-suggestions/include?${params}`, {
                method: 'POST',
            });
            if (response.ok) {
                setData(prev => {
                    if (!prev) return prev;
                    const tradeKey = `${trade.ticker}_${trade.direction}_${trade.entry_date}`;
                    const movedTrade = { ...trade, excluded: false };
                    return {
                        ...prev,
                        excluded: prev.excluded.filter(t => `${t.ticker}_${t.direction}_${t.entry_date}` !== tradeKey),
                        included: [...prev.included, movedTrade],
                        included_count: prev.included_count + 1,
                        excluded_count: prev.excluded_count - 1,
                    };
                });
            }
        } catch (err) {
            console.error('Error including trade:', err);
        }
    };

    const handleResetExcluded = async () => {
        if (!window.confirm('Reset all excluded suggestions? Everything will be re-included.')) return;
        try {
            const response = await fetch('/api/pattern-suggestions/exclude/reset', {
                method: 'POST',
            });
            if (response.ok) {
                fetchData();
            }
        } catch (err) {
            console.error('Error resetting excluded:', err);
        }
    };

    const handleSort = (key) => {
        setSortConfig(prev => ({
            key,
            direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc',
        }));
    };

    const sortTrades = (trades) => {
        if (!sortConfig.key || !trades) return trades;
        return [...trades].sort((a, b) => {
            let aVal = a[sortConfig.key];
            let bVal = b[sortConfig.key];
            const aNum = parseFloat(aVal);
            const bNum = parseFloat(bVal);

            if (!isNaN(aNum) && !isNaN(bNum)) {
                return sortConfig.direction === 'asc' ? aNum - bNum : bNum - aNum;
            }

            const aStr = String(aVal || '');
            const bStr = String(bVal || '');
            return sortConfig.direction === 'asc'
                ? aStr.localeCompare(bStr)
                : bStr.localeCompare(aStr);
        });
    };

    // Filter by signal type
    const filterTrades = (trades) => {
        if (!trades || filterSignal === 'ALL') return trades;
        return trades.filter(t => {
            const sig = t.signal || '';
            if (filterSignal === 'BUY') return sig === 'BUY_NOW';
            if (filterSignal === 'HOLD') return sig === 'HOLDING' || sig === 'HOLDING_SHORT';
            if (filterSignal === 'UPCOMING') return sig === 'UPCOMING' || sig === 'UPCOMING_SHORT';
            if (filterSignal === 'SHORT') return sig === 'SHORT_NOW';
            return true;
        });
    };

    const sortedIncluded = useMemo(
        () => sortTrades(filterTrades(data?.included || [])),
        [data?.included, sortConfig, filterSignal]
    );
    const sortedExcluded = useMemo(
        () => sortTrades(data?.excluded || []),
        [data?.excluded, sortConfig]
    );

    const getThClass = (key) => {
        if (sortConfig.key !== key) return '';
        return sortConfig.direction === 'asc' ? 'sorted-asc' : 'sorted-desc';
    };

    const formatMetric = (val) => {
        if (val === null || val === undefined || val === '') return '—';
        const n = parseFloat(val);
        if (isNaN(n)) return String(val);
        return n.toFixed(2);
    };

    const metricClass = (val) => {
        if (val === null || val === undefined || val === '') return 'neutral';
        const n = parseFloat(val);
        if (isNaN(n)) return 'neutral';
        if (n > 0) return 'positive';
        if (n < 0) return 'negative';
        return 'neutral';
    };

    const confidenceClass = (pct) => {
        if (pct >= 70) return 'ps-conf-high';
        if (pct >= 40) return 'ps-conf-med';
        return 'ps-conf-low';
    };

    const progressClass = (pct) => {
        if (pct <= 30) return 'early';
        if (pct <= 70) return 'mid';
        return 'late';
    };

    // Signal badge styling
    const signalBadge = (trade) => {
        const sig = trade.signal || '';
        const cls = {
            'BUY_NOW': 'ps-signal-buy',
            'SHORT_NOW': 'ps-signal-short',
            'HOLDING': 'ps-signal-hold',
            'HOLDING_SHORT': 'ps-signal-cover',
            'UPCOMING': 'ps-signal-upcoming',
            'UPCOMING_SHORT': 'ps-signal-upcoming-short',
        }[sig] || 'ps-signal-default';

        return (
            <span className={`ps-signal-badge ${cls}`}>
                {trade.action_label || sig}
            </span>
        );
    };

    const renderTradeTable = (trades, isExcludedSection) => {
        if (!trades || trades.length === 0) {
            return (
                <div className="ps-empty">
                    <div className="ps-empty-icon">{isExcludedSection ? '✅' : '📭'}</div>
                    {isExcludedSection
                        ? 'No excluded suggestions'
                        : 'No pattern suggestions matching filter'}
                </div>
            );
        }

        return (
            <div className="ps-table-wrapper">
                <table className="ps-table">
                    <thead>
                        <tr>
                            <th className={getThClass('ticker')} onClick={() => handleSort('ticker')}>Ticker</th>
                            <th className={getThClass('signal')} onClick={() => handleSort('signal')}>Signal</th>
                            <th className={getThClass('direction')} onClick={() => handleSort('direction')}>Dir</th>
                            <th className={getThClass('score')} onClick={() => handleSort('score')}>Score</th>
                            <th className={getThClass('confidence_pct')} onClick={() => handleSort('confidence_pct')}>Conf%</th>
                            <th className={getThClass('return_pct')} onClick={() => handleSort('return_pct')}>Ret%/30d</th>
                            <th className={getThClass('win_rate')} onClick={() => handleSort('win_rate')}>Win%</th>
                            <th className={getThClass('entry_date')} onClick={() => handleSort('entry_date')}>Entry</th>
                            <th className={getThClass('exit_date')} onClick={() => handleSort('exit_date')}>Exit</th>
                            <th>Progress</th>
                            <th className={getThClass('exdiv_date')} onClick={() => handleSort('exdiv_date')}>ExDiv</th>
                            <th className={getThClass('cycle_label')} onClick={() => handleSort('cycle_label')}>Cycle</th>
                            <th className={getThClass('FINAL_THG')} onClick={() => handleSort('FINAL_THG')}>THG</th>
                            <th className={getThClass('Final_BB')} onClick={() => handleSort('Final_BB')}>F.BB</th>
                            <th className={getThClass('Final_SAS')} onClick={() => handleSort('Final_SAS')}>F.SAS</th>
                            <th className={getThClass('Fbtot')} onClick={() => handleSort('Fbtot')}>Fbtot</th>
                            <th className={getThClass('SFStot')} onClick={() => handleSort('SFStot')}>SFStot</th>
                            <th className={getThClass('GORT')} onClick={() => handleSort('GORT')}>GORT</th>
                            <th className={getThClass('SMA63chg')} onClick={() => handleSort('SMA63chg')}>SMA63</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trades.map((trade) => {
                            const key = `${trade.ticker}_${trade.direction}_${trade.entry_date}`;
                            return (
                                <tr key={key} className={isExcludedSection ? 'excluded-row' : ''}>
                                    <td><span className="ps-ticker">{trade.ticker}</span></td>
                                    <td>{signalBadge(trade)}</td>
                                    <td>
                                        <span className={`ps-direction ${trade.direction.toLowerCase()}`}>
                                            {trade.direction === 'LONG' ? '🟢' : '🔴'} {trade.direction}
                                        </span>
                                    </td>
                                    <td>
                                        <span className="ps-score" title={trade.score_label || ''}>
                                            {trade.score?.toFixed(2) || '—'}
                                        </span>
                                    </td>
                                    <td>
                                        <span className={`ps-confidence ${confidenceClass(trade.confidence_pct || 0)}`}>
                                            {trade.confidence_pct?.toFixed(0) || 0}%
                                        </span>
                                    </td>
                                    <td>
                                        <span className={`ps-metric ${(trade.return_pct || 0) > 0 ? 'positive' : 'negative'}`}>
                                            {(trade.return_pct || 0) > 0 ? '+' : ''}{trade.return_pct?.toFixed(2) || 0}%
                                        </span>
                                    </td>
                                    <td>
                                        <span className={`ps-metric ${(trade.win_rate || 0) >= 60 ? 'positive' : (trade.win_rate || 0) >= 45 ? 'neutral' : 'negative'}`}>
                                            {trade.win_rate?.toFixed(0) || 0}%
                                        </span>
                                    </td>
                                    <td style={{ fontSize: '11px', color: '#8899aa' }}>{trade.entry_date}</td>
                                    <td style={{ fontSize: '11px', color: '#8899aa' }}>{trade.exit_date}</td>
                                    <td>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <div className="ps-progress-bar">
                                                <div
                                                    className={`ps-progress-fill ${progressClass(trade.progress_pct || 0)}`}
                                                    style={{ width: `${Math.min(100, trade.progress_pct || 0)}%` }}
                                                />
                                            </div>
                                            <span style={{ fontSize: '10px', color: '#667788', whiteSpace: 'nowrap' }}>
                                                {trade.days_remaining ?? 0}d
                                            </span>
                                        </div>
                                    </td>
                                    <td style={{ fontSize: '11px', color: '#8899aa' }}>
                                        {trade.exdiv_date || '—'}
                                    </td>
                                    <td>
                                        <span className="ps-cycle" title={trade.strategy || ''}>
                                            {trade.cycle_label || `${trade.entry_offset_label || ''}→${trade.exit_offset_label || ''}`}
                                        </span>
                                    </td>
                                    <td><span className={`ps-metric ${metricClass(trade.FINAL_THG)}`}>{formatMetric(trade.FINAL_THG)}</span></td>
                                    <td><span className={`ps-metric ${metricClass(trade.Final_BB)}`}>{formatMetric(trade.Final_BB)}</span></td>
                                    <td><span className={`ps-metric ${metricClass(trade.Final_SAS)}`}>{formatMetric(trade.Final_SAS)}</span></td>
                                    <td><span className={`ps-metric ${metricClass(trade.Fbtot)}`}>{formatMetric(trade.Fbtot)}</span></td>
                                    <td><span className={`ps-metric ${metricClass(trade.SFStot)}`}>{formatMetric(trade.SFStot)}</span></td>
                                    <td><span className={`ps-metric ${metricClass(trade.GORT)}`}>{formatMetric(trade.GORT)}</span></td>
                                    <td><span className={`ps-metric ${metricClass(trade.SMA63chg)}`}>{formatMetric(trade.SMA63chg)}</span></td>
                                    <td>
                                        {isExcludedSection ? (
                                            <button
                                                className="ps-action-btn include"
                                                onClick={() => handleInclude(trade)}
                                                title="Re-include this suggestion"
                                            >
                                                ↩ Include
                                            </button>
                                        ) : (
                                            <button
                                                className="ps-action-btn exclude"
                                                onClick={() => handleExclude(trade)}
                                                title="Exclude this suggestion"
                                            >
                                                ✕ Exclude
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        );
    };

    if (!isOpen) return null;

    // Signal filter counts
    const incl = data?.included || [];
    const buyCount = incl.filter(t => t.signal === 'BUY_NOW' || t.signal === 'SHORT_NOW').length;
    const holdCount = incl.filter(t => t.signal === 'HOLDING' || t.signal === 'HOLDING_SHORT').length;
    const upcomingCount = incl.filter(t => t.signal === 'UPCOMING' || t.signal === 'UPCOMING_SHORT').length;

    return (
        <div className="ps-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
            <div className="ps-modal">
                {/* Header */}
                <div className="ps-header">
                    <div className="ps-header-left">
                        <h2>🔮 Temettü Pattern Önerileri</h2>
                        {data && (
                            <div className="ps-meta-badges">
                                <span className="ps-meta-badge highlight">
                                    📅 {data.target_date}
                                </span>
                                <span className="ps-meta-badge">
                                    📈 {data.total_trades_in_report || (data.included_count + data.excluded_count)} toplam
                                </span>
                                <span className="ps-meta-badge highlight">
                                    🎯 {data.active_count || 0} aktif sinyal
                                </span>
                                <span className="ps-meta-badge">
                                    📦 {data.stats?.holding || 0} elde
                                </span>
                                <span className="ps-meta-badge">
                                    ⏳ {data.stats?.upcoming || 0} yaklaşan
                                </span>
                            </div>
                        )}
                    </div>
                    <button className="ps-close-btn" onClick={onClose}>×</button>
                </div>

                {/* Signal Filters */}
                {data && !loading && (
                    <div className="ps-signal-filters">
                        <button
                            className={`ps-filter-btn ${filterSignal === 'ALL' ? 'active' : ''}`}
                            onClick={() => setFilterSignal('ALL')}
                        >
                            Tümü ({data.included_count})
                        </button>
                        <button
                            className={`ps-filter-btn buy ${filterSignal === 'BUY' ? 'active' : ''}`}
                            onClick={() => setFilterSignal('BUY')}
                        >
                            🟢 BUY / SHORT ({buyCount})
                        </button>
                        <button
                            className={`ps-filter-btn hold ${filterSignal === 'HOLD' ? 'active' : ''}`}
                            onClick={() => setFilterSignal('HOLD')}
                        >
                            📦 HOLD ({holdCount})
                        </button>
                        <button
                            className={`ps-filter-btn upcoming ${filterSignal === 'UPCOMING' ? 'active' : ''}`}
                            onClick={() => setFilterSignal('UPCOMING')}
                        >
                            ⏳ Yaklaşan ({upcomingCount})
                        </button>
                    </div>
                )}

                {/* Body */}
                <div className="ps-body">
                    {loading && (
                        <div className="ps-loading">
                            <div className="spinner" />
                            Temettü pattern önerileri yükleniyor...
                        </div>
                    )}

                    {error && (
                        <div className="ps-error">
                            ⚠️ {error}
                        </div>
                    )}

                    {!loading && data && (
                        <>
                            {/* Included Section */}
                            <div className="ps-section">
                                <div className="ps-section-header">
                                    <span className="ps-section-title included">
                                        ✅ Aktif Öneriler
                                    </span>
                                    <span className="ps-section-count">
                                        {sortedIncluded.length} trade
                                        {' '}(
                                        {sortedIncluded.filter(t => t.direction === 'LONG').length}L
                                        {' / '}
                                        {sortedIncluded.filter(t => t.direction === 'SHORT').length}S
                                        )
                                    </span>
                                </div>
                                {renderTradeTable(sortedIncluded, false)}
                            </div>

                            {/* Divider */}
                            {data.excluded_count > 0 && <hr className="ps-divider" />}

                            {/* Excluded Section */}
                            {data.excluded_count > 0 && (
                                <div className="ps-section">
                                    <div className="ps-section-header">
                                        <span className="ps-section-title excluded">
                                            🚫 Hariç Tutulanlar
                                        </span>
                                        <span className="ps-section-count">
                                            {data.excluded_count} trade{data.excluded_count !== 1 ? 's' : ''}
                                        </span>
                                    </div>
                                    {renderTradeTable(sortedExcluded, true)}
                                </div>
                            )}
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="ps-footer">
                    <span className="ps-footer-info">
                        Kaynak: Pipeline v5.1 (janalldata.csv bazlı temettü döngüsü)
                    </span>
                    <div className="ps-footer-actions">
                        {data?.excluded_count > 0 && (
                            <button className="ps-reset-btn" onClick={handleResetExcluded}>
                                🔄 Hariç Tutulanları Sıfırla
                            </button>
                        )}
                        <button className="ps-refresh-btn" onClick={fetchData} disabled={loading}>
                            🔄 Yenile
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default PatternSuggestionsModal;
