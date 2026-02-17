const { ipcRenderer } = require('electron');

// State
let currentView = 'sessions'; // maps to nav-sessions (Nodes)

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
    Object.values(navItems).forEach(el => el.classList.remove('active'));
    navItems[viewName].classList.add('active');
    Object.values(views).forEach(el => el.classList.remove('active'));
    views[viewName].classList.add('active');
    currentView = viewName;
    refreshCurrentView();
}

async function refreshCurrentView() {
    updateStatusBar();
    if (currentView === 'sessions') loadAgentNodes();
    if (currentView === 'proxies') loadIntelStreams();
    if (currentView === 'warmup') loadCapabilities();
    if (currentView === 'ai') loadAICore();
    if (currentView === 'settings') loadSettings();
}

// --- AGENT NODES VIEW ---
async function loadAgentNodes() {
    const tbody = document.getElementById('sessions-tbody');
    tbody.innerHTML = '';

    // Mock/Detection logic for OpenClaw process
    const nodes = [
        { id: 'OC_OVERLORD', name: 'OpenClaw_Main', status: 'ACTIVE', cpu: '2.4%', ram: '142MB', uptime: '14:22:05' }
    ];

    nodes.forEach(n => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${n.id}</td>
            <td style="font-weight:bold; color:var(--matrix-green)">${n.name}</td>
            <td><span class="status-dot dot-success"></span>${n.status}</td>
            <td>${n.cpu}</td>
            <td>${n.ram}</td>
            <td>${n.uptime}</td>
            <td>
                 <button class="btn btn-icon" onclick="restartAgent()"><i class="fas fa-sync"></i></button>
                 <button class="btn btn-icon" onclick="stopAgent()"><i class="fas fa-stop"></i></button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// --- INTEL STREAMS VIEW ---
async function loadIntelStreams() {
    const tbody = document.getElementById('proxies-tbody');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px;">>> SCANNING_INTELLIGENCE_STREAMS...</td></tr>';

    // Simulate finding streams
    setTimeout(() => {
        tbody.innerHTML = `
            <tr>
                <td>LOCAL_TERMINAL</td>
                <td>SYSTEM_SHELL</td>
                <td>< 1ms</td>
                <td>REAL_TIME</td>
                <td>ENCRYPTED</td>
                <td><i class="fas fa-link"></i></td>
            </tr>
            <tr>
                <td>GROK_API_UPLINK</td>
                <td>HTTPS/REST</td>
                <td>140ms</td>
                <td>STREAMING</td>
                <td>TLS_1.3</td>
                <td><i class="fas fa-link"></i></td>
            </tr>
        `;
    }, 1000);
}

// --- CAPABILITIES VIEW ---
async function loadCapabilities() {
    // Buttons/Info already in HTML for now
}

// --- AI CORE VIEW (10 Slots) ---
async function loadAICore() {
    const slots = await ipcRenderer.invoke('ai-get-keys');
    const container = document.getElementById('ai-key-grid');
    container.innerHTML = '';
    let activeCount = 0;

    slots.forEach((slot, index) => {
        if (slot.active && slot.key) activeCount++;
        const maxUsage = 1000;
        const usage = slot.usage || 0;
        const width = Math.max(0, Math.min(100, 100 - (usage / maxUsage * 100)));
        let levelClass = width < 50 ? (width < 20 ? 'critical' : 'low') : '';

        const div = document.createElement('div');
        div.className = `ai-slot ${slot.active && slot.key ? 'active' : ''}`;
        div.innerHTML = `
            <div class="ai-slot-number">${index + 1 < 10 ? '0' + (index + 1) : index + 1}</div>
            <div class="ai-input-group">
                <input type="password" class="ai-key-input" value="${slot.key || ''}" placeholder="API_KEY..." onchange="updateAIKey(${index}, this.value)">
                <div class="battery-container"><div class="battery-level ${levelClass}" style="width: ${width}%"></div></div>
                <div class="usage-text"><span>PWR: ${Math.floor(width)}%</span><span>USE: ${usage}</span></div>
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
    loadAICore();
};

window.clearAIKey = async (index) => {
    await ipcRenderer.invoke('ai-remove-key', index);
    loadAICore();
};

// --- SHELL TERMINAL ---
const termInput = document.getElementById('terminal-input');
const termOutput = document.getElementById('terminal-output');

if (termInput) {
    termInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const cmd = termInput.value;
            termInput.value = '';
            executeCommand(cmd);
        }
    });
}

function executeCommand(cmd) {
    const line = document.createElement('div');
    line.innerHTML = `<span style="color:var(--text-muted)">></span> ${cmd}`;
    termOutput.appendChild(line);

    // Simulate execution
    const response = document.createElement('div');
    response.style.color = 'var(--matrix-green)';
    response.innerHTML = `>> EXECUTING_ON_AGENT_NODE...<br>[i] CMD_RECEIVED: ${cmd}`;
    termOutput.appendChild(response);
    termOutput.scrollTop = termOutput.scrollHeight;
}

// --- SETTINGS ---
async function loadSettings() {
    const config = await ipcRenderer.invoke('get-config');
    document.getElementById('set-groq').value = config.ai?.apiKey || '';
}

document.getElementById('btn-save-settings').addEventListener('click', async () => {
    await ipcRenderer.invoke('update-config', 'ai.apiKey', document.getElementById('set-groq').value);
    const btn = document.getElementById('btn-save-settings');
    btn.textContent = 'SECURED';
    setTimeout(() => btn.textContent = 'COMMIT_CHANGES', 1500);
});

// --- STATUS BAR ---
async function updateStatusBar() {
    document.getElementById('sb-total').textContent = '1';
    document.getElementById('sb-warmed').textContent = 'ACTIVE';
    document.getElementById('sb-threads').textContent = 'GROK-3';
    document.getElementById('sb-version').textContent = 'OPENCLAW_CTRL_v1.0';
}

// Helpers
window.restartAgent = () => alert('RESTARTING_AGENT_NODE...');
window.stopAgent = () => alert('TERMINATING_AGENT_NODE...');

// Initial Load
switchView('sessions');
setInterval(updateStatusBar, 5000);
