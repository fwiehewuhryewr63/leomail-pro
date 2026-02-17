const { ipcRenderer } = require('electron');

// State
let currentView = 'sessions';

// DOM Elements
const views = {
    sessions: document.getElementById('sessions'),
    proxies: document.getElementById('proxies'),
    warmup: document.getElementById('warmup'),
    mailer: document.getElementById('mailer'),
    settings: document.getElementById('settings')
};

const navItems = {
    sessions: document.getElementById('nav-sessions'),
    proxies: document.getElementById('nav-proxies'),
    warmup: document.getElementById('nav-warmup'),
    mailer: document.getElementById('nav-mailer'),
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
    if (currentView === 'settings') loadSettings();
}

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

// Initial Load
switchView('sessions');
setInterval(updateStatusBar, 5000);
