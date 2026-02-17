const { ipcRenderer } = require('electron');

// State
let currentView = 'sessions';

// DOM Elements
const views = {
    sessions: document.getElementById('sessions'),
    proxies: document.getElementById('proxies'),
    warmup: document.getElementById('warmup'),
    mailer: document.getElementById('mailer'),
    ai: document.getElementById('ai-core'),
    settings: document.getElementById('settings')
};

const navItems = {
    sessions: document.getElementById('nav-sessions'),
    proxies: document.getElementById('nav-proxies'),
    warmup: document.getElementById('nav-warmup'),
    mailer: document.getElementById('nav-mailer'),
    ai: document.getElementById('nav-ai'),
    settings: document.getElementById('nav-settings')
};

// Navigation Logic
Object.keys(navItems).forEach(key => {
    navItems[key].addEventListener('click', () => switchView(key));
});

function switchView(viewName) {
    // Update Nav
    Object.values(navItems).forEach(el => el.classList.remove('active'));
    navItems[viewName].classList.add('active');

    // Update View
    Object.values(views).forEach(el => el.classList.remove('active'));
    views[viewName].classList.add('active');

    currentView = viewName;
    refreshCurrentView();
}

async function refreshCurrentView() {
    updateStatusBar();
    if (currentView === 'sessions') loadSessions();
    if (currentView === 'proxies') loadProxies();
    if (currentView === 'warmup') loadWarmupQueue();
    if (currentView === 'ai') loadAICore();
    if (currentView === 'settings') loadSettings();
}

// --- AI CORE VIEW ---
async function loadAICore() {
    const slots = await ipcRenderer.invoke('ai-get-keys');
    const container = document.getElementById('ai-key-grid');
    container.innerHTML = '';

    let activeCount = 0;

    slots.forEach((slot, index) => {
        if (slot.active && slot.key) activeCount++;

        // Calculate battery
        const maxUsage = 1000; // Visual cap
        const usage = slot.usage || 0;
        const width = Math.max(0, Math.min(100, 100 - (usage / maxUsage * 100)));

        let levelClass = '';
        if (width < 50) levelClass = 'low';
        if (width < 20) levelClass = 'critical';

        const div = document.createElement('div');
        div.className = `ai-slot ${slot.active && slot.key ? 'active' : ''}`;
        div.innerHTML = `
            <div class="ai-slot-number">${index + 1 < 10 ? '0' + (index + 1) : index + 1}</div>
            <div class="ai-input-group">
                <input type="password" class="ai-key-input" 
                    value="${slot.key || ''}" 
                    placeholder="ENTER_API_KEY..."
                    onchange="updateAIKey(${index}, this.value)"
                >
                <div class="battery-container">
                    <div class="battery-level ${levelClass}" style="width: ${width}%"></div>
                </div>
                <div class="usage-text">
                    <span>PWR: ${Math.floor(width)}%</span>
                    <span>USE: ${usage}</span>
                </div>
            </div>
            <div class="slot-actions">
                <button class="btn btn-icon" onclick="clearAIKey(${index})"><i class="fas fa-trash"></i></button>
            </div>
        `;
        container.appendChild(div);
    });

    document.getElementById('ai-active-count').textContent = `${activeCount}/10`;
}

window.updateAIKey = async (index, key) => {
    await ipcRenderer.invoke('ai-add-key', { key, index });
    loadAICore(); // Refresh to show active state
};

window.clearAIKey = async (index) => {
    await ipcRenderer.invoke('ai-remove-key', index);
    loadAICore();
};


// --- STATUS BAR ---
async function updateStatusBar() {
    const stats = await ipcRenderer.invoke('get-statistics');
    document.getElementById('sb-total').textContent = stats.accounts.total || 0;
    document.getElementById('sb-warmed').textContent = stats.accounts.warmed || 0;
    // Mock threads for now
    document.getElementById('sb-threads').textContent = '0';
}

// --- SESSIONS VIEW ---
async function loadSessions() {
    const sessions = await ipcRenderer.invoke('get-accounts');
    const tbody = document.getElementById('sessions-tbody');
    tbody.innerHTML = '';

    sessions.forEach(s => {
        const row = document.createElement('tr');
        const statusClass = s.status === 'ready' ? 'success' : (s.status === 'banned' ? 'danger' : 'neutral');

        row.innerHTML = `
            <td><input type="checkbox" class="session-check" value="${s.id}"></td>
            <td>${s.id}</td>
            <td>
                <div style="font-weight:600">${s.email}</div>
                <div style="color:var(--text-muted); font-size:11px">PW: ${s.password.substring(0, 6)}...</div>
            </td>
            <td><span class="status-dot dot-${statusClass}"></span>${s.status}</td>
            <td>${s.proxy_id ? 'Pro' : '-'}</td>
            <td>${s.warmup_status} <span style="color:var(--text-muted)">(${s.warmup_score || 0})</span></td>
            <td>${new Date(s.created_at).toLocaleDateString()}</td>
            <td>
                 <button class="btn-icon" onclick="deleteSession(${s.id})"><i class="fas fa-trash"></i></button>
                 <button class="btn-icon" onclick="openSession(${s.id})"><i class="fas fa-external-link-alt"></i></button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

document.getElementById('refresh-sessions').addEventListener('click', loadSessions);

// --- PROXIES VIEW ---
async function loadProxies() {
    const proxies = await ipcRenderer.invoke('get-proxies');
    const tbody = document.getElementById('proxies-tbody');
    tbody.innerHTML = '';

    proxies.forEach(p => {
        const row = document.createElement('tr');
        const statusClass = p.status === 'active' ? 'success' : 'danger';
        row.innerHTML = `
            <td>${p.host}</td>
            <td>${p.port}</td>
            <td>${p.protocol}</td>
            <td>${p.type || 'http'}</td>
            <td>${p.country || '-'}</td>
            <td><span class="status-dot dot-${statusClass}"></span>${p.status}</td>
            <td>
                <button class="btn-icon" onclick="deleteProxy(${p.id})"><i class="fas fa-trash"></i></button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

document.getElementById('btn-add-proxy').addEventListener('click', () => showModal('Add Proxies', `
    <textarea id="modal-proxy-input" class="sphere-input" rows="10" placeholder="host:port:user:pass"></textarea>
`, async () => {
    const content = document.getElementById('modal-proxy-input').value;
    const lines = content.split('\n');
    for (const line of lines) {
        if (line.trim()) await ipcRenderer.invoke('add-proxy', line.trim());
    }
    loadProxies();
}));

// --- SETTINGS VIEW ---
async function loadSettings() {
    const config = await ipcRenderer.invoke('get-config');
    document.getElementById('set-grizzly').value = config.smsServices?.services?.['grizzly']?.apiKey || '';
    document.getElementById('set-simsms').value = config.smsServices?.services?.['simsms']?.apiKey || '';
    document.getElementById('set-capguru').value = config.captchaServices?.apiKey || '';
    document.getElementById('set-groq').value = config.ai?.apiKey || '';
    document.getElementById('set-threads').value = config.app?.maxParallelWorkers || 35;
}

document.getElementById('btn-save-settings').addEventListener('click', async () => {
    await ipcRenderer.invoke('update-config', 'smsServices.services.grizzly.apiKey', document.getElementById('set-grizzly').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.simsms.apiKey', document.getElementById('set-simsms').value);
    await ipcRenderer.invoke('update-config', 'captchaServices.apiKey', document.getElementById('set-capguru').value);
    await ipcRenderer.invoke('update-config', 'ai.apiKey', document.getElementById('set-groq').value);
    await ipcRenderer.invoke('update-config', 'app.maxParallelWorkers', parseInt(document.getElementById('set-threads').value));

    // Show visual feedback
    const btn = document.getElementById('btn-save-settings');
    const originalText = btn.textContent;
    btn.textContent = 'Saved!';
    btn.classList.add('btn-primary'); // Highlight
    setTimeout(() => {
        btn.textContent = originalText;
        btn.classList.remove('btn-primary');
    }, 1500);
});

// --- WARMUP VIEW ---
async function loadWarmupQueue() {
    // Mock data for now or fetch from backend if available
    const tbody = document.getElementById('warmup-tbody');
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding: 20px;">>> TRAINING_QUEUE_EMPTY</td></tr>';

    // Update stats
    const stats = await ipcRenderer.invoke('get-statistics');
    document.getElementById('warmup-active-count').textContent = stats.warmup?.active || 0;
    document.getElementById('warmup-pending-count').textContent = stats.warmup?.pending || 0;
}

// --- MAILER VIEW ---
async function loadMailer() {
    const container = document.getElementById('mail-content-area');
    const accounts = await ipcRenderer.invoke('get-accounts');

    if (accounts.length === 0) {
        container.innerHTML = '<div class="empty-state">>> NO_CHARACTERS_FOUND</div>';
        return;
    }

    // Render Grid of Accounts to Select
    let html = '<div class="ai-grid" style="grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));">';
    accounts.forEach(acc => {
        html += `
            <div class="ai-slot" onclick="openMailInterface(${acc.id})" style="cursor:pointer; height:60px;">
                <div class="ai-slot-number"><i class="fas fa-user-secret"></i></div>
                <div class="ai-input-group">
                    <div style="color:var(--matrix-green)">${acc.email}</div>
                    <div style="font-size:10px; color:var(--text-muted)">ID: ${acc.id}</div>
                </div>
            </div>
        `;
    });
    html += '</div>';

    container.innerHTML = html;
}

window.openMailInterface = async (id) => {
    // Placeholder for actual mail interactions
    // In a real app, this would load the inbox for the selected ID
    alert(`OPENING_COMMS_LINK: ${id}`);
};

// --- MODAL SYSTEM ---
function showModal(title, htmlContent, onConfirm) {
    const overlay = document.getElementById('ui-modal');
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML = htmlContent;
    overlay.style.display = 'flex';

    const confirmBtn = document.getElementById('modal-confirm-btn');
    confirmBtn.onclick = async () => {
        if (onConfirm) await onConfirm();
        overlay.style.display = 'none';
    };

    document.querySelector('.modal-close').onclick = () => overlay.style.display = 'none';
}

// --- ACTIONS ---
window.deleteSession = async (id) => {
    if (confirm('Delete session?')) {
        await ipcRenderer.invoke('delete-account', id);
        loadSessions();
    }
};

window.openSession = async (id) => {
    await ipcRenderer.invoke('launch-browser', id);
};

window.deleteProxy = async (id) => {
    if (confirm('Delete proxy?')) {
        await ipcRenderer.invoke('delete-proxy', id);
        loadProxies();
    }
};

// Initial Load
switchView('sessions');
setInterval(updateStatusBar, 5000);
