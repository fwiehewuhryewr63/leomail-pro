const { ipcRenderer } = require('electron');

// Navigation
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

        item.classList.add('active');
        const pageId = item.id.replace('nav-', '');
        document.getElementById(pageId).classList.add('active');

        // Refresh specific pages
        if (pageId === 'accounts') loadAccounts();
        if (pageId === 'warmup') loadWarmup();
        if (pageId === 'settings') loadSettings();
        if (pageId === 'proxies') loadProxies();
        if (pageId === 'mailer') loadMailer();
    });
});

// Dashboard
async function loadDashboard() {
    const stats = await ipcRenderer.invoke('get-statistics');

    document.getElementById('stat-total-accounts').textContent = stats.accounts.total || 0;
    document.getElementById('stat-warmed-accounts').textContent = stats.accounts.warmed || 0;
    document.getElementById('stat-active-proxies').textContent = stats.proxies.active || 0;
    document.getElementById('stat-emails-sent').textContent = `${stats.emails.sent || 0} (${stats.emails.successRate || 0}%)`;

    // Load recent activity
    const activityList = document.getElementById('activity-list');
    activityList.innerHTML = '';

    stats.recentActivity.slice(0, 10).forEach(activity => {
        const item = document.createElement('div');
        item.className = 'activity-item';

        const icon = activity.status === 'success' ? '✅' : '❌';
        const time = new Date(activity.created_at).toLocaleTimeString();

        item.innerHTML = `
            <span class="activity-icon">${icon}</span>
            <span class="activity-text">${activity.action}: ${activity.details || 'Completed'}</span>
            <span class="activity-time">${time}</span>
        `;

        activityList.appendChild(item);
    });
}

// Proxies
async function loadProxies() {
    const proxies = await ipcRenderer.invoke('get-proxies');
    const tbody = document.getElementById('proxies-tbody');
    tbody.innerHTML = '';

    proxies.forEach(proxy => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${proxy.host}</td>
            <td>${proxy.port}</td>
            <td>${proxy.protocol}</td>
            <td>${proxy.is_mobile ? 'Yes' : 'No'}</td>
            <td>${proxy.success_rate}%</td>
            <td><span class="status-badge status-${proxy.status}">${proxy.status}</span></td>
            <td>
                <button class="btn-icon delete-proxy" data-id="${proxy.id}">🗑️</button>
            </td>
        `;
        tbody.appendChild(row);
    });

    document.querySelectorAll('.delete-proxy').forEach(btn => {
        btn.addEventListener('click', (e) => deleteProxy(e.target.closest('button').dataset.id));
    });
}

async function deleteProxy(id) {
    if (confirm('Delete this proxy?')) {
        await ipcRenderer.invoke('delete-proxy', id);
        loadProxies();
    }
}

// Proxy Modal Logic
const modal = document.getElementById('sphere-modal');
const modalInput = document.getElementById('modal-input');
const modalActionBtn = document.getElementById('modal-action-btn');

document.getElementById('add-proxy-btn').addEventListener('click', () => {
    modal.style.display = 'flex';
    modalInput.value = '';
    modalInput.focus();
});

document.getElementById('modal-close').addEventListener('click', () => {
    modal.style.display = 'none';
});

modalActionBtn.addEventListener('click', async () => {
    const content = modalInput.value.trim();
    if (!content) return;

    const lines = content.split('\n');
    let count = 0;

    for (const line of lines) {
        if (line.trim()) {
            await ipcRenderer.invoke('add-proxy', line.trim());
            count++;
        }
    }

    alert(`Added ${count} proxies successfully.`);
    modal.style.display = 'none';
    loadProxies();
});

// Accounts
async function loadAccounts() {
    const accounts = await ipcRenderer.invoke('get-accounts');
    const tbody = document.getElementById('accounts-tbody');
    tbody.innerHTML = '';

    accounts.forEach(acc => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${acc.email}</td>
            <td>${acc.password.substring(0, 8)}...</td>
            <td>${acc.recovery_email || '-'}</td>
            <td><span class="status-badge status-${acc.status}">${acc.status}</span></td>
            <td>${acc.warmup_status}</td>
            <td>${new Date(acc.created_at).toLocaleDateString()}</td>
            <td>
                <button class="btn-icon run-warmup" data-id="${acc.id}">🔥</button>
                <button class="btn-icon delete-account" data-id="${acc.id}">🗑️</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// Settings (CLEANED v5)
async function loadSettings() {
    const config = await ipcRenderer.invoke('get-config');

    document.getElementById('sms-grizzly-key').value = config.smsServices?.services?.['grizzly']?.apiKey || '';
    document.getElementById('sms-simsms-key').value = config.smsServices?.services?.['simsms']?.apiKey || '';
    document.getElementById('captcha-key').value = config.captchaServices?.apiKey || '';
    document.getElementById('groq-key').value = config.ai?.apiKey || '';
    document.getElementById('max-workers').value = config.app?.maxParallelWorkers || 35;
}

document.getElementById('save-settings').addEventListener('click', async () => {
    await ipcRenderer.invoke('update-config', 'smsServices.services.grizzly.apiKey', document.getElementById('sms-grizzly-key').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.grizzly.enabled', !!document.getElementById('sms-grizzly-key').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.simsms.apiKey', document.getElementById('sms-simsms-key').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.simsms.enabled', !!document.getElementById('sms-simsms-key').value);

    await ipcRenderer.invoke('update-config', 'captchaServices.apiKey', document.getElementById('captcha-key').value);

    await ipcRenderer.invoke('update-config', 'ai.apiKey', document.getElementById('groq-key').value);
    await ipcRenderer.invoke('update-config', 'app.maxParallelWorkers', parseInt(document.getElementById('max-workers').value));

    alert('Settings saved successfully!');
});

// Registration
document.getElementById('start-reg-btn').addEventListener('click', async () => {
    const count = parseInt(document.getElementById('reg-count').value);
    if (count < 1) return alert('Invalid count');

    await ipcRenderer.invoke('start-registration', count, 'google');
    alert(`Started registration for ${count} accounts`);
});

document.getElementById('stop-reg-btn').addEventListener('click', async () => {
    await ipcRenderer.invoke('stop-registration');
    alert('Stopped');
});

// Export
document.getElementById('export-btn').addEventListener('click', async () => {
    const format = document.getElementById('export-format').value;
    const filePath = await ipcRenderer.invoke('export-accounts', format, {});
    alert(`Exported to: ${filePath}`);
});

// Initial load
loadDashboard();
setInterval(() => {
    if (document.getElementById('dashboard').classList.contains('active')) loadDashboard();
}, 5000);
