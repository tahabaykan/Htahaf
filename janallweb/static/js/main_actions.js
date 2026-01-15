
// ==================== MODE & CONNECTION ====================

// --- Connection ---
async function toggleHammerConnection() {
    console.log("toggleHammerConnection çağrıldı");
    const btn = document.getElementById('connectBtn');
    
    if (state.hammerConnected) {
        console.log("Durum: Bağlı, Disconnect işlemi başlatılıyor...");
        // Disconnect
        if (!confirm('Hammer Pro bağlantısını kesmek istediğinize emin misiniz?')) return;
        
        showLoading(true);
        try {
            const result = await apiCall('/connection/hammer/disconnect', 'POST');
            if (result.success) {
                console.log("Bağlantı başarıyla kesildi");
                state.hammerConnected = false;
                updateConnectButton(false);
                showToast('Bağlantı kesildi', 'info');
            } else {
                console.error("Bağlantı kesme hatası:", result.error);
                showToast(`Hata: ${result.error}`, 'error');
                // Hata olsa bile state'i güncelle (zorla senkronizasyon)
                if (result.error === 'Aktif bağlantı yok') {
                    state.hammerConnected = false;
                    updateConnectButton(false);
                }
            }
        } catch (e) {
            console.error("API hatası:", e);
            showToast('Bağlantı kesilemedi', 'error');
        } finally {
            showLoading(false);
        }
    } else {
        console.log("Durum: Bağlı Değil, Connect işlemi başlatılıyor...");
        // Connect
        const password = prompt('Hammer Pro şifresi:');
        if (password === null) return;
        
        showLoading(true);
        try {
            const result = await apiCall('/connection/hammer/connect', 'POST', { password });
            if (result.success) {
                console.log("Bağlantı başarılı");
                state.hammerConnected = true;
                updateConnectButton(true);
                showToast('Hammer Pro bağlantısı başarılı', 'success');
            } else {
                console.error("Bağlantı hatası:", result.error);
                showToast(`Bağlantı hatası: ${result.error}`, 'error');
            }
        } catch (e) {
            console.error("API hatası:", e);
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
        console.log("Bağlantı durumu kontrol ediliyor...");
        const result = await apiCall('/connection/status');
        if (result.success && result.status) {
            console.log("Sunucu durumu:", result.status);
            state.hammerConnected = result.status.hammer;
            updateConnectButton(state.hammerConnected);
            
            // Eğer bağlıysa bağlantı göstergesini güncelle
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

// --- Live Data ---
async function toggleLiveData() {
    if (!state.hammerConnected) {
        showToast('Önce Hammer Pro bağlantısı kurun', 'warning');
        return;
    }
    
    // Tüm sembolleri al
    const symbols = state.stocks.map(s => s.ticker || s.symbol || s['PREF IBKR']).filter(Boolean);
    if (symbols.length === 0) {
        showToast('Abone olunacak hisse yok (CSV yükleyin)', 'warning');
        return;
    }
    
    showLoading(true);
    try {
        // Subscribe request
        const result = await apiCall('/market-data/subscribe', 'POST', { symbols });
        if (result.success) {
            showToast(`${symbols.length} hisse için canlı veri başlatıldı`, 'success');
            
            // Butonu güncelle
            const btn = document.getElementById('liveDataBtn');
            if (btn) {
                btn.innerHTML = '<i class="fa-solid fa-satellite-dish"></i> Live Aktif';
                btn.classList.add('active-pulse'); // CSS animasyonu eklenebilir
            }
        }
    } catch (e) {
        showToast('Live data başlatılamadı', 'error');
    } finally {
        showLoading(false);
    }
}

// --- Mode ---
async function changeMode(newMode) {
    try {
        const result = await apiCall('/mode/set', 'POST', { mode: newMode });
        if (result.success) {
            state.currentMode = newMode;
            localStorage.setItem('janall_mode', newMode);
            showToast(`Mod değiştirildi: ${newMode}`, 'success');
            
            // Arayüz güncellemeleri (renk değişimi vb.)
            updateModeUI(newMode);
        }
    } catch (e) {
        showToast('Mod değiştirilemedi', 'error');
    }
}

function updateModeUI(mode) {
    // Mod değişimine göre UI tepkileri
    const body = document.body;
    if (mode === 'IBKR_PED') {
        body.style.setProperty('--ios-primary', '#FF9F0A'); // Orange theme
    } else if (mode === 'IBKR_GUN') {
        body.style.setProperty('--ios-primary', '#30D158'); // Green theme
    } else {
        body.style.setProperty('--ios-primary', '#0A84FF'); // Blue theme (Default)
    }
}

// ==================== MINI450 & SPECIAL VIEWS ====================

// --- Mini450 ---
const mini450Btn = document.getElementById('mini450Btn');
if (mini450Btn) {
    mini450Btn.addEventListener('click', async () => {
        // Tüm hisseleri tek sayfada göster (küçük fontlarla)
        if (state.stocks.length === 0) {
            showToast('Önce CSV yükleyin', 'warning');
            return;
        }
        
        // UI Değişiklikleri
        state.itemsPerPage = 1000; // Tümünü göster
        state.currentPage = 1;
        
        const table = document.getElementById('stockTable');
        if (table) table.classList.add('mini-view'); // CSS ile küçük font ayarla
        
        renderStocks();
        
        // Tümüne subscribe ol (eğer olmadıysa)
        toggleLiveData();
        
        showToast('Mini450 Görünümü Aktif', 'info');
    });
}

// --- MAJBINA ---
const majbinaBtn = document.getElementById('majbinaBtn');
if (majbinaBtn) {
    majbinaBtn.addEventListener('click', () => {
        openSidePanel('majbina'); // Panel olarak açılacak
    });
}

// --- Port Adjuster ---
const portAdjusterBtn = document.getElementById('portAdjusterBtn');
if (portAdjusterBtn) {
    portAdjusterBtn.addEventListener('click', () => {
        openSidePanel('port-adjuster');
    });
}

// Expose functions
window.toggleHammerConnection = toggleHammerConnection;
window.toggleLiveData = toggleLiveData;
window.changeMode = changeMode;
window.checkConnectionStatus = checkConnectionStatus; // Global erişim
