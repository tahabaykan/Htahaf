import React, { useState, useEffect } from 'react';
import './ExcludedListModal.css';

function ExcludedListModal({ isOpen, onClose }) {
    const [excludedList, setExcludedList] = useState([]);
    const [newSymbols, setNewSymbols] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (isOpen) {
            loadExcludedList();
        }
    }, [isOpen]);

    const loadExcludedList = async () => {
        setLoading(true);
        try {
            const response = await fetch('/api/excluded-list');
            const data = await response.json();
            if (data.success) {
                setExcludedList(data.list || []);
            } else {
                setError(data.message || 'Failed to load list');
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setLoading(true);
        try {
            // Split by comma/newline, trim, uppercase
            const symbolsToAdd = newSymbols
                .split(/[\n,]+/)
                .map(s => s.trim().toUpperCase())
                .filter(s => s.length > 0);

            if (symbolsToAdd.length === 0 && excludedList.length === 0) {
                // Allow empty save if list is cleared
            }

            // Merge with existing
            const updatedList = Array.from(new Set([...excludedList, ...symbolsToAdd]));

            // Save to backend
            const response = await fetch('/api/excluded-list/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbols: updatedList })
            });

            const result = await response.json();
            if (result.success) {
                setExcludedList(updatedList);
                setNewSymbols(''); // Clear input
            } else {
                setError(result.message);
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const removeSymbol = async (symbolToRemove) => {
        // Optimistic update
        const newList = excludedList.filter(s => s !== symbolToRemove);
        setExcludedList(newList);

        // Save immediately
        try {
            const response = await fetch('/api/excluded-list/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbols: newList })
            });
            if (!response.ok) throw new Error("Save failed");
        } catch (err) {
            setError("Failed to save removal");
            // Revert on error
            setExcludedList(prev => [...prev, symbolToRemove]);
        }
    }

    const handleClearAll = async () => {
        if (!window.confirm("Are you sure you want to clear the entire excluded list?")) return;

        try {
            const response = await fetch('/api/excluded-list/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbols: [] })
            });
            if (response.ok) {
                setExcludedList([]);
            }
        } catch (err) {
            setError("Failed to clear list");
        }
    }

    if (!isOpen) return null;

    return (
        <div className="excluded-list-modal-overlay">
            <div className="excluded-list-modal">
                <div className="modal-header">
                    <h3>🚫 Excluded Stocks List</h3>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>

                <div className="modal-body">
                    <p className="modal-description">
                        Stocks in this list are completely excluded from ALL calculations, suggestions, and tables.
                        Values will be set to N/A. (Saved to <code>qe_excluded.csv</code>)
                    </p>

                    {error && <div className="error-banner">{error}</div>}

                    <div className="add-section">
                        <label>Add Symbols (comma or newline separated):</label>
                        <textarea
                            value={newSymbols}
                            onChange={(e) => setNewSymbols(e.target.value)}
                            placeholder="AGM PRG, SOJD, SOJE..."
                            rows={3}
                        />
                        <button className="add-btn" onClick={handleSave} disabled={loading}>
                            {loading ? 'Saving...' : 'Add & Save'}
                        </button>
                    </div>

                    <div className="list-section">
                        <div className="list-header">
                            <h4>Current List ({excludedList.length})</h4>
                            <button className="clear-all-btn" onClick={handleClearAll}>Clear All</button>
                        </div>
                        <div className="symbols-grid">
                            {excludedList.map(sym => (
                                <div key={sym} className="symbol-tag">
                                    {sym}
                                    <span className="remove-x" onClick={() => removeSymbol(sym)}>×</span>
                                </div>
                            ))}
                            {excludedList.length === 0 && <div className="empty-message">No excluded stocks.</div>}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default ExcludedListModal;
