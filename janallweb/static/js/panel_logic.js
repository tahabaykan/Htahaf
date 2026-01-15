
// ==================== PANEL ACTIONS ====================

// --- Take Profit Longs ---
async function loadTakeProfitLongs() {
    // Backend'den hesaplanmış veriyi iste
    showLoading(true);
    try {
        const result = await apiCall('/panels/data/take-profit-longs');
        if (result.success) {
            renderTakeProfitTable('tpLongsBody', result.data, 'longs');
        }
    } catch (e) {
        showToast('Veri yüklenemedi', 'error');
    } finally {
        showLoading(false);
    }
}

function renderTakeProfitTable(tbodyId, data, type) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    
    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state">Veri yok</div></td></tr>`;
        return;
    }
    
    tbody.innerHTML = data.map(row => `
        <tr>
            <td>${row.symbol}</td>
            <td>${row.qty}</td>
            <td>${formatNumber(row.score)}</td>
            <td>${formatNumber(row.spread)}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="closePosition('${row.symbol}', ${row.qty}, '${type}')">Kapat</button>
            </td>
        </tr>
    `).join('');
}

async function executeCroplit6Longs() {
    if (!confirm('Croplit 6 (Longs) çalıştırılsın mı?')) return;
    startBackgroundTask('/algorithms/run', { algorithm_name: 'croplit6_longs' });
}

async function executeCroplit9Longs() {
    if (!confirm('Croplit 9 (Longs) çalıştırılsın mı?')) return;
    startBackgroundTask('/algorithms/run', { algorithm_name: 'croplit9_longs' });
}

// --- Take Profit Shorts ---
async function loadTakeProfitShorts() {
    showLoading(true);
    try {
        const result = await apiCall('/panels/data/take-profit-shorts');
        if (result.success) {
            renderTakeProfitTable('tpShortsBody', result.data, 'shorts');
        }
    } catch (e) {
        showToast('Veri yüklenemedi', 'error');
    } finally {
        showLoading(false);
    }
}

async function executeCroplit6Shorts() {
    if (!confirm('Croplit 6 (Shorts) çalıştırılsın mı?')) return;
    startBackgroundTask('/algorithms/run', { algorithm_name: 'croplit6_shorts' });
}

async function executeCroplit9Shorts() {
    if (!confirm('Croplit 9 (Shorts) çalıştırılsın mı?')) return;
    startBackgroundTask('/algorithms/run', { algorithm_name: 'croplit9_shorts' });
}

// --- Spreadkusu ---
async function loadSpreadkusu() {
    showLoading(true);
    try {
        const result = await apiCall('/panels/data/spreadkusu');
        if (result.success) {
            const tbody = document.getElementById('spreadkusuBody');
            if (tbody) {
                if (result.data.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state">Spread > 0.20 hisse yok</div></td></tr>`;
                } else {
                    tbody.innerHTML = result.data.map(row => `
                        <tr>
                            <td>${row.symbol}</td>
                            <td class="text-success">${formatNumber(row.spread)}</td>
                            <td>${formatNumber(row.bid)}</td>
                            <td>${formatNumber(row.ask)}</td>
                            <td><button class="btn btn-sm btn-primary" onclick="placeOrderForSpread('${row.symbol}')">İşlem</button></td>
                        </tr>
                    `).join('');
                }
            }
        }
    } catch (e) {
        showToast('Spreadkusu yüklenemedi', 'error');
    } finally {
        showLoading(false);
    }
}

async function runQpcal() {
    if (!confirm('Run Qpcal (Otomatik Spread Avcısı) başlatılsın mı?\nBu işlem uzun sürebilir.')) return;
    startBackgroundTask('/algorithms/run', { algorithm_name: 'qpcal' });
}

// --- Background Task Helper ---
async function startBackgroundTask(endpoint, data) {
    showToast('İşlem arka planda başlatıldı...', 'info');
    try {
        const result = await apiCall(endpoint, 'POST', data);
        if (result.success) {
            // SocketIO ile ilerleme dinlenecek
            console.log('Task started:', result.task_id);
        } else {
            showToast(`Hata: ${result.error}`, 'error');
        }
    } catch (e) {
        showToast('İşlem başlatılamadı', 'error');
    }
}

// --- Global Expose ---
window.loadTakeProfitLongs = loadTakeProfitLongs;
window.executeCroplit6Longs = executeCroplit6Longs;
window.executeCroplit9Longs = executeCroplit9Longs;
window.loadTakeProfitShorts = loadTakeProfitShorts;
window.executeCroplit6Shorts = executeCroplit6Shorts;
window.executeCroplit9Shorts = executeCroplit9Shorts;
window.loadSpreadkusu = loadSpreadkusu;
window.runQpcal = runQpcal;









