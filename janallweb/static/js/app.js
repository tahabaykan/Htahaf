// ==================== CONFIGURATION ====================
const API_BASE_URL = 'http://127.0.0.1:5000/api';
const WS_URL = 'http://127.0.0.1:5000';

// ==================== STATE MANAGEMENT ====================
const state = {
    socket: null,
    connected: false,
    hammerConnected: false,
    stocks: [],          // Tüm hisse verileri
    positions: [],       // Açık pozisyonlar
    orders: [],          // Bekleyen emirler
    completedOrders: [], // Tamamlanan emirler
    selectedStocks: new Set(), // Seçili hisse indeksleri
    
    // Pagination
    currentPage: 1,
    itemsPerPage: 15,
    totalPages: 1,
    
    // Settings
    currentMode: 'HAMPRO',
    lot: 200,
    
    // Market Data Cache
    marketDataCache: new Map(), // symbol -> { bid, ask, last, ... }
    
    // UI State
    activePage: 'dashboard',
    activePanel: null,
    searchQuery: '',
    sortColumn: null,
    sortDirection: 'asc'
};

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', () => {
    console.log("Uygulama başlatılıyor...");
    initializeApp();
});

async function initializeApp() {
    setupNavigation();
    setupEventListeners();
    setupSocketIO();
    
    // Initial data fetch
    console.log("Uygulama verileri yükleniyor...");
    await loadCSVGroupButtons(); // CSV butonlarını önce yükle
    await checkConnectionStatus();
    
    // Check local storage for settings
    const savedMode = localStorage.getItem('janall_mode');
    if (savedMode) {
        state.currentMode = savedMode;
        const modeSelect = document.getElementById('modeSelect');
        if (modeSelect) modeSelect.value = savedMode;
        updateModeUI(savedMode);
    }
}

// ==================== SOCKET.IO (REAL-TIME) ====================
function setupSocketIO() {
    try {
        state.socket = io(WS_URL, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 5
        });

        state.socket.on('connect', () => {
            console.log('✅ WebSocket Connected');
            state.connected = true;
            updateConnectButton(state.hammerConnected);
            const indicator = document.getElementById('connectionStatus');
            if (indicator) {
                const dot = indicator.querySelector('.status-dot');
                const text = indicator.querySelector('.status-text');
                if (state.hammerConnected) {
                    dot.classList.add('connected');
                    text.textContent = 'Bağlı (Hammer)';
                }
            }
            showToast('Sunucu bağlantısı kuruldu', 'success');
        });

        state.socket.on('disconnect', () => {
            console.log('❌ WebSocket Disconnected');
            state.connected = false;
            updateConnectButton(false);
            const indicator = document.getElementById('connectionStatus');
            if (indicator) {
                const dot = indicator.querySelector('.status-dot');
                dot.classList.remove('connected');
                indicator.querySelector('.status-text').textContent = 'Bağlantı Yok';
            }
            showToast('Sunucu bağlantısı koptu', 'error');
        });

        state.socket.on('market_data_update', (data) => {
            handleMarketDataUpdate(data);
        });

        state.socket.on('positions_update', (data) => {
            console.log("Pozisyon güncellemesi:", data);
            state.positions = data.positions || [];
            renderPositions(); // Her güncellemede render et (eğer sayfa açıksa zaten renderPositions kontrol eder)
        });

        state.socket.on('fill_update', (data) => {
            showToast(`Emir Gerçekleşti`, 'success');
        });
        
    } catch (e) {
        console.error("SocketIO hatası:", e);
    }
}

// ==================== EVENT LISTENERS ====================
function setupEventListeners() {
    // Top Bar Actions
    document.getElementById('refreshBtn')?.addEventListener('click', () => {
        window.location.reload();
    });

    // Lot Controls
    document.getElementById('lotInput')?.addEventListener('input', (e) => {
        state.lot = parseInt(e.target.value) || 0;
    });

    document.querySelectorAll('[data-lot]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const percent = parseInt(e.currentTarget.dataset.lot);
            showToast(`Lot %${percent} seçildi (Henüz aktif değil)`, 'info');
        });
    });

    // Selection Controls
    document.getElementById('selectAllBtn')?.addEventListener('click', selectAllStocks);
    document.getElementById('deselectAllBtn')?.addEventListener('click', deselectAllStocks);

    // Search & Sort
    document.getElementById('searchInput')?.addEventListener('input', (e) => {
        state.searchQuery = e.target.value.toLowerCase();
        state.currentPage = 1;
        renderStocks();
    });

    // Pagination
    document.getElementById('prevPage')?.addEventListener('click', () => changePage(-1));
    document.getElementById('nextPage')?.addEventListener('click', () => changePage(1));

    // Side Panel Close
    document.getElementById('closeSidePanel')?.addEventListener('click', closeSidePanel);
    
    // Order Buttons
    document.querySelectorAll('[data-order]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const orderType = e.currentTarget.dataset.order;
            // placeBulkOrder(orderType); // TODO: Implement placeBulkOrder
            showToast(`${orderType} emri gönderiliyor...`, 'info');
        });
    });
    
    // Mode Selection
    document.getElementById('modeSelect')?.addEventListener('change', (e) => {
        changeMode(e.target.value);
    });
    
    // Manual CSV List Refresh
    document.getElementById('loadCsvBtn')?.addEventListener('click', () => {
        loadCSVGroupButtons();
        showToast('CSV listesi yenileniyor...', 'info');
    });

    // Mini450
    document.getElementById('mini450Btn')?.addEventListener('click', async () => {
        if (state.stocks.length === 0) {
            showToast('Önce CSV yükleyin', 'warning');
            return;
        }
        state.itemsPerPage = 1000;
        state.currentPage = 1;
        const table = document.getElementById('stockTable');
        if (table) table.classList.add('mini-view');
        renderStocks();
        toggleLiveData();
        showToast('Mini450 Görünümü Aktif', 'info');
    });
}

function setupNavigation() {
    document.querySelectorAll('.nav-item[data-page]').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const pageId = e.currentTarget.dataset.page;
            switchPage(pageId);
            document.querySelectorAll('.nav-item[data-page]').forEach(nav => nav.classList.remove('active'));
            e.currentTarget.classList.add('active');
            
            // Sayfa değişiminde ilgili veriyi render et
            if (pageId === 'positions') renderPositions();
        });
    });

    document.querySelectorAll('.nav-item[data-panel]').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const panelId = e.currentTarget.dataset.panel;
            openSidePanel(panelId);
        });
    });
}

// ==================== CONNECTION & MODE ====================

async function toggleHammerConnection() {
    console.log("toggleHammerConnection tetiklendi");
    
    if (state.hammerConnected) {
        if (!confirm('Hammer Pro bağlantısını kesmek istediğinize emin misiniz?')) return;
        
        showLoading(true);
        try {
            const result = await apiCall('/connection/hammer/disconnect', 'POST');
            if (result.success) {
                state.hammerConnected = false;
                updateConnectButton(false);
                showToast('Bağlantı kesildi', 'info');
            }
        } catch (e) {
            console.error("Bağlantı kesme hatası:", e);
            showToast('Bağlantı kesilemedi', 'error');
        } finally {
            showLoading(false);
        }
    } else {
        const password = prompt('Hammer Pro şifresi:', '');
        if (password === null) return;
        
        showLoading(true);
        try {
            const result = await apiCall('/connection/hammer/connect', 'POST', { password });
            if (result.success) {
                state.hammerConnected = true;
                updateConnectButton(true);
                showToast('Hammer Pro bağlantısı başarılı', 'success');
            } else {
                showToast(`Bağlantı hatası: ${result.error}`, 'error');
            }
        } catch (e) {
            console.error("Bağlantı hatası:", e);
            showToast('Bağlantı kurulamadı', 'error');
        } finally {
            showLoading(false);
        }
    }
}

function updateConnectButton(isConnected) {
    const btn = document.getElementById('connectBtn');
    if (!btn) return;
    
    if (isConnected) {
        btn.innerHTML = '<i class="fa-solid fa-link-slash"></i> Bağlantıyı Kes';
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-danger');
    } else {
        btn.innerHTML = '<i class="fa-solid fa-link"></i> Hammer Bağlan';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-primary');
    }
}

async function checkConnectionStatus() {
    try {
        const result = await apiCall('/connection/status');
        if (result.success && result.status) {
            state.hammerConnected = result.status.hammer;
            updateConnectButton(state.hammerConnected);
            
            const indicator = document.getElementById('connectionStatus');
            const dot = indicator.querySelector('.status-dot');
            const text = indicator.querySelector('.status-text');
            
            if (state.hammerConnected) {
                dot.classList.add('connected');
                text.textContent = 'Bağlı (Hammer)';
            } else {
                dot.classList.remove('connected');
                text.textContent = 'Bağlantı Yok';
            }
        }
    } catch (e) {
        console.error('Status check failed', e);
    }
}

async function toggleLiveData() {
    if (!state.hammerConnected) {
        showToast('Önce Hammer Pro bağlantısı kurun', 'warning');
        return;
    }
    
    showLoading(true);
    try {
        // Orijinal JanAll mantığı: Tek tuşla janalldata.csv yükle ve başlat
        const result = await apiCall('/market-data/start-live', 'POST');
        
        if (result.success) {
            state.stocks = result.data || [];
            state.currentPage = 1;
            renderStocks();
            
            showToast(result.message, 'success');
            const btn = document.getElementById('liveDataBtn');
            if (btn) {
                btn.innerHTML = '<i class="fa-solid fa-satellite-dish"></i> Live Aktif';
                btn.classList.add('active-pulse');
            }
        } else {
             showToast(result.error || 'Live data başlatılamadı', 'error');
        }
    } catch (e) {
        console.error("Live Data hatası:", e);
        showToast('Live data başlatma hatası', 'error');
    } finally {
        showLoading(false);
    }
}

async function changeMode(newMode) {
    try {
        const result = await apiCall('/mode/set', 'POST', { mode: newMode });
        if (result.success) {
            state.currentMode = newMode;
            localStorage.setItem('janall_mode', newMode);
            showToast(`Mod değiştirildi: ${newMode}`, 'success');
            updateModeUI(newMode);
        }
    } catch (e) {
        showToast('Mod değiştirilemedi', 'error');
    }
}

function updateModeUI(mode) {
    const body = document.body;
    if (mode === 'IBKR_PED') {
        body.style.setProperty('--ios-primary', '#FF9F0A');
    } else if (mode === 'IBKR_GUN') {
        body.style.setProperty('--ios-primary', '#30D158');
    } else {
        body.style.setProperty('--ios-primary', '#0A84FF');
    }
}

// ==================== CSV OPERATIONS ====================
async function loadCSVGroupButtons() {
    const defaultFiles = [
        'janek_ssfinekheldcilizyeniyedi.csv', 'janek_ssfinekheldcommonsuz.csv', 
        'janek_ssfinekhelddeznff.csv', 'janek_ssfinekheldff.csv', 
        'janek_ssfinekheldflr.csv', 'janek_ssfinekheldgarabetaltiyedi.csv',
        'janek_ssfinekheldkuponlu.csv', 'janek_ssfinekheldkuponlukreciliz.csv',
        'janek_ssfinekheldkuponlukreorta.csv', 'janek_ssfinekheldnff.csv',
        'janek_ssfinekheldotelremorta.csv', 'janek_ssfinekheldsolidbig.csv',
        'janek_ssfinekheldtitrekhc.csv', 'janek_ssfinekhighmatur.csv',
        'janek_ssfineknotbesmaturlu.csv', 'janek_ssfineknotcefilliquid.csv',
        'janek_ssfineknottitrekhc.csv', 'janek_ssfinekrumoreddanger.csv',
        'janek_ssfineksalakilliquid.csv', 'janek_ssfinekshitremhc.csv'
    ];

    let files = defaultFiles;

    try {
        const result = await apiCall('/csv/list');
        if (result.success && result.files && result.files.length > 0) {
            files = result.files;
        }
    } catch (e) {
        console.error('CSV listesi hatası:', e);
    }

    const container = document.getElementById('csvGroupButtons');
    if (!container) {
        console.error("HATA: csvGroupButtons bulunamadı!");
        return;
    }
    
    // Filtrelemeyi kaldır, tüm CSV'leri göster ama sırala
    let displayFiles = files.filter(f => f.toLowerCase().endsWith('.csv'));
    
    // janek_ssfinek ile başlayanları en başa al
    displayFiles.sort((a, b) => {
        const aIsJanek = a.toLowerCase().startsWith('janek_ssfinek');
        const bIsJanek = b.toLowerCase().startsWith('janek_ssfinek');
        if (aIsJanek && !bIsJanek) return -1;
        if (!aIsJanek && bIsJanek) return 1;
        return a.localeCompare(b);
    });
    
    // İlk 60 dosyayı göster (UI performansı için)
    displayFiles = displayFiles.slice(0, 60);
    
    const buttonsHtml = displayFiles.map(file => {
        // İsim kısaltma
        let shortName = file.replace('janek_ssfinek', '').replace('.csv', '');
        // Eğer isim hala çok uzunsa başını ve sonunu göster
        if (shortName.length > 25) {
            shortName = shortName.substring(0, 22) + '...';
        }
        return `<button class="btn btn-secondary csv-btn" onclick="loadCSV('${file}')" style="margin: 2px; font-size: 11px; padding: 4px 8px;">${shortName}</button>`;
    }).join('');

    if (!buttonsHtml.trim()) {
        container.innerHTML = '<div class="empty-state" style="padding: 10px;">Görüntülenecek CSV dosyası bulunamadı.</div>';
    } else {
        container.innerHTML = buttonsHtml;
    }
}

async function loadCSV(filename) {
    showLoading(true);
    try {
        const result = await apiCall('/csv/load', 'POST', { filename });
        if (result.success) {
            state.stocks = result.data || [];
            state.currentPage = 1;
            state.selectedStocks.clear();
            renderStocks();
            showToast(`${state.stocks.length} hisse yüklendi`, 'success');
        } else {
            showToast(`Hata: ${result.error}`, 'error');
        }
    } catch (e) {
        showToast('CSV yüklenirken hata oluştu', 'error');
    } finally {
        showLoading(false);
    }
}

// ==================== RENDERING ====================
function renderStocks() {
    const tbody = document.getElementById('stockTableBody');
    const thead = document.getElementById('stockTableHead');
    if (!tbody || !thead) return;

    let displayStocks = state.stocks;
    if (state.searchQuery) {
        displayStocks = state.stocks.filter(s => {
            const ticker = (s['PREF IBKR'] || s.ticker || '').toLowerCase();
            return ticker.includes(state.searchQuery);
        });
    }

    if (displayStocks.length === 0) {
        tbody.innerHTML = `<tr><td colspan="100"><div class="empty-state"><div class="empty-icon"><i class="fa-solid fa-chart-simple"></i></div><p>Veri bulunamadı</p></div></td></tr>`;
        return;
    }

    // Headers
    if (state.stocks.length > 0 && thead.children.length === 0) {
        const headers = ['Seç', 'Symbol', 'Bid', 'Ask', 'Last', 'Score FB', 'Score SFS', 'BM Chg', 'Lot'];
        thead.innerHTML = `<tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>`;
    }

    const totalPages = Math.ceil(displayStocks.length / state.itemsPerPage);
    state.totalPages = totalPages;
    
    if (state.currentPage > totalPages) state.currentPage = 1;
    
    const startIdx = (state.currentPage - 1) * state.itemsPerPage;
    const endIdx = startIdx + state.itemsPerPage;
    const pageItems = displayStocks.slice(startIdx, endIdx);

    tbody.innerHTML = pageItems.map((stock, idx) => {
        const globalIndex = state.stocks.indexOf(stock);
        const isSelected = state.selectedStocks.has(globalIndex);
        const ticker = stock['PREF IBKR'] || stock.ticker || 'N/A';
        
        // Cache
        const marketData = state.marketDataCache.get(ticker) || {};
        const bid = marketData.bid || stock.Bid || 0;
        const ask = marketData.ask || stock.Ask || 0;
        const last = marketData.last || stock.Last || 0;
        
        return `
            <tr id="stock-row-${globalIndex}" class="${isSelected ? 'selected' : ''}" onclick="toggleRowSelection(${globalIndex})">
                <td onclick="event.stopPropagation()">
                    <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleRowSelection(${globalIndex})">
                </td>
                <td style="font-weight: 600;">${ticker}</td>
                <td class="col-bid text-success">${formatPrice(bid)}</td>
                <td class="col-ask text-danger">${formatPrice(ask)}</td>
                <td class="col-last">${formatPrice(last)}</td>
                <td>${formatNumber(stock.Final_FB_skor)}</td>
                <td>${formatNumber(stock.Final_SFS_skor)}</td>
                <td>${formatNumber(stock.Benchmark_Chg)}</td>
                <td>${stock.Lot || '-'}</td>
            </tr>
        `;
    }).join('');

    document.getElementById('currentPage').textContent = state.currentPage;
    document.getElementById('totalPages').textContent = totalPages;
    document.getElementById('prevPage').disabled = state.currentPage <= 1;
    document.getElementById('nextPage').disabled = state.currentPage >= totalPages;
    document.getElementById('selectedCount').textContent = state.selectedStocks.size;
}

function handleMarketDataUpdate(data) {
    const { symbol, data: marketData } = data;
    state.marketDataCache.set(symbol, marketData);
    
    // Sayfadaki görünür satırları kontrol et
    const startIdx = (state.currentPage - 1) * state.itemsPerPage;
    const endIdx = startIdx + state.itemsPerPage;
    
    // Sembol eşleştirme (Esnek)
    let stockIndex = state.stocks.findIndex(s => (s['PREF IBKR'] || s.ticker) === symbol);
    
    if (stockIndex === -1) {
        // İkinci şans: Trim ve format
        stockIndex = state.stocks.findIndex(s => {
             const stockSym = (s['PREF IBKR'] || s.ticker || '').trim();
             // JanAll formatı: CIM PRB -> Backend'den CIM PRB gelebilir veya CIM-B gelebilir
             // Basit karşılaştırma
             return stockSym === symbol.trim();
        });
    }

    if (stockIndex !== -1 && stockIndex >= startIdx && stockIndex < endIdx) {
        const rowId = `stock-row-${stockIndex}`;
        const row = document.getElementById(rowId);
        if (row) {
            const bidCell = row.querySelector('.col-bid');
            const askCell = row.querySelector('.col-ask');
            const lastCell = row.querySelector('.col-last');
            
            // Veri varsa güncelle ve renk ver
            if (bidCell && marketData.bid) bidCell.textContent = formatPrice(marketData.bid);
            if (askCell && marketData.ask) askCell.textContent = formatPrice(marketData.ask);
            if (lastCell && marketData.last) lastCell.textContent = formatPrice(marketData.last);
            
            row.classList.add('flash-update');
            setTimeout(() => row.classList.remove('flash-update'), 300);
        }
    }
}

// ==================== POSITIONS RENDERING ====================
function renderPositions() {
    const tbody = document.getElementById('positionsTableBody');
    // Eğer positions sayfasında değilsek veya tablo yoksa çık
    if (state.activePage !== 'positions' || !tbody) return;

    if (!state.positions || state.positions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state">Açık pozisyon yok</div></td></tr>`;
        return;
    }

    tbody.innerHTML = state.positions.map(pos => `
        <tr>
            <td style="font-weight: 600;">${pos.symbol}</td>
            <td>${pos.qty}</td>
            <td>${formatPrice(pos.avg_cost)}</td>
            <td>${formatPrice(pos.last_price)}</td>
            <td class="${pos.pnl >= 0 ? 'text-success' : 'text-danger'}">${formatPrice(pos.pnl)}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="closePosition('${pos.symbol}', ${pos.qty})">Kapat</button>
            </td>
        </tr>
    `).join('');
}

// TODO: closePosition fonksiyonunu backend'e bağla
async function closePosition(symbol, qty) {
    if (!confirm(`${symbol} pozisyonunu kapatmak istiyor musunuz?`)) return;
    showToast(`${symbol} kapatılıyor...`, 'info');
    // Buraya backend API call gelecek
}

// ==================== SIDE PANELS ====================
async function openSidePanel(panelId) {
    const overlay = document.getElementById('sidePanelOverlay');
    const content = document.getElementById('sidePanelContent');
    const title = document.getElementById('sidePanelTitle');
    
    title.textContent = panelId.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    content.innerHTML = `<div class="spinner" style="margin: 50px auto;"></div>`;
    overlay.style.right = '0';
    
    try {
        const result = await apiCall(`/panels/${panelId}`);
        if (result.success) {
            content.innerHTML = result.html;
            if (result.script) {
                // Güvenli script çalıştırma (basit fonksiyonlar için)
                const scriptEl = document.createElement('script');
                scriptEl.textContent = result.script;
                content.appendChild(scriptEl);
            }
        } else {
            content.innerHTML = `<div class="empty-state"><p>Panel yüklenemedi: ${result.error}</p></div>`;
        }
    } catch (e) {
        content.innerHTML = `<div class="empty-state"><p>Bağlantı hatası</p></div>`;
    }
}

function closeSidePanel() {
    const overlay = document.getElementById('sidePanelOverlay');
    overlay.style.right = '-600px';
}

// ==================== HELPERS ====================
async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);
    
    const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
    return await response.json();
}

function formatPrice(price) {
    if (price === null || price === undefined || isNaN(price)) return '-';
    return parseFloat(price).toFixed(2);
}

function formatNumber(num) {
    if (num === null || num === undefined || isNaN(num)) return '0.00';
    return parseFloat(num).toFixed(2);
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    let icon = 'info-circle';
    if (type === 'success') icon = 'check-circle';
    if (type === 'error') icon = 'exclamation-circle';
    toast.innerHTML = `<i class="fa-solid fa-${icon}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function showLoading(show) {
    const overlay = document.getElementById('loadingOverlay');
    if (show) overlay.classList.add('active');
    else overlay.classList.remove('active');
}

function switchPage(pageId) {
    state.activePage = pageId;
    document.getElementById('pageTitle').textContent = pageId.charAt(0).toUpperCase() + pageId.slice(1);
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
    const targetPage = document.getElementById(`${pageId}Page`);
    if (targetPage) targetPage.classList.add('active');
}

function changePage(delta) {
    const newPage = state.currentPage + delta;
    if (newPage >= 1 && newPage <= state.totalPages) {
        state.currentPage = newPage;
        renderStocks();
    }
}

window.toggleRowSelection = (index) => {
    if (state.selectedStocks.has(index)) {
        state.selectedStocks.delete(index);
    } else {
        state.selectedStocks.add(index);
    }
    renderStocks(); // Re-render to update UI (checkbox state)
};

function selectAllStocks() {
    const startIdx = (state.currentPage - 1) * state.itemsPerPage;
    const endIdx = Math.min(startIdx + state.itemsPerPage, state.stocks.length);
    for (let i = startIdx; i < endIdx; i++) {
        state.selectedStocks.add(i);
    }
    renderStocks();
}

function deselectAllStocks() {
    state.selectedStocks.clear();
    renderStocks();
}

// Global functions
window.loadCSV = loadCSV;
window.toggleHammerConnection = toggleHammerConnection;
window.toggleLiveData = toggleLiveData;
window.closePosition = closePosition;
