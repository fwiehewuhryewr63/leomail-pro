const { ipcRenderer } = require('electron');

/**
 * Frontend Application Logic
 */

// Page Navigation
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        const page = item.dataset.page;

        // Update active nav item
        document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
        item.classList.add('active');

        // Update active page
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.getElementById(page).classList.add('active');

        // Load page data
        loadPageData(page);
    });
});

// Load page data
async function loadPageData(page) {
    switch (page) {
        case 'dashboard':
            await loadDashboard();
            break;
        case 'registration':
            await loadRegistrationStatus();
            break;
        case 'warmup':
            await loadWarmupStatus();
            break;
        case 'accounts':
            await loadAccounts();
            break;
        case 'proxies':
            await loadProxies();
            break;
        case 'settings':
            await loadSettings();
            break;
    }
}

// Dashboard
async function loadDashboard() {
    const stats = await ipcRenderer.invoke('get-statistics');

    document.getElementById('stat-total-accounts').textContent = stats.accounts.total || 0;
    document.getElementById('stat-warmed-accounts').textContent = stats.accounts.warmed || 0;
    // Renamed to Active Proxies as requested
    document.getElementById('stat-active-proxies').textContent = stats.proxies.active || 0;
    // Added Emails Sent stats
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

// ... (Rest of file unchanged)

// Settings
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

    alert('Settings saved successfully! Sphere v5 active.');
});

// Registration
document.getElementById('start-reg-btn').addEventListener('click', async () => {
    const count = parseInt(document.getElementById('reg-count').value);
    const provider = document.getElementById('reg-provider').value;

    if (count < 1 || count > 1000) {
        alert('Please enter a number between 1 and 1000');
        return;
    }

    await ipcRenderer.invoke('start-registration', count, provider);
    alert(`Started registration for ${count} ${provider} accounts`);

    // Start polling for status
    startRegistrationPolling();
});

document.getElementById('stop-reg-btn').addEventListener('click', async () => {
    await ipcRenderer.invoke('stop-registration');
    alert('Registration stopped');
});

// Mailer Logic
let selectedAccountId = null;
let currentMailTab = 'inbox';

async function loadMailer() {
    const accounts = await ipcRenderer.invoke('get-accounts');
    const list = document.getElementById('mailer-accounts-list');
    list.innerHTML = '';

    accounts.forEach(account => {
        const item = document.createElement('div');
        item.className = `mailer-account-item ${selectedAccountId === account.id ? 'active' : ''}`;
        item.innerHTML = `
            <div class="email">${account.email}</div>
            <div class="provider">${account.provider}</div>
        `;
        item.onclick = () => selectAccount(account.id);
        list.appendChild(item);
    });
}

async function selectAccount(accountId) {
    selectedAccountId = accountId;
    document.getElementById('mail-no-selection').style.display = 'none';
    document.getElementById('mail-active-panel').style.display = 'flex';

    // Update active class in list
    document.querySelectorAll('.mailer-account-item').forEach(item => {
        item.classList.remove('active');
        if (item.querySelector('.email').textContent.includes(accountId)) { // Simplified check
            item.classList.add('active');
        }
    });

    // Refresh inbox for selected account
    await refreshInbox();
    loadMailer(); // To refresh active state in sidebar
}

async function refreshInbox() {
    if (!selectedAccountId) return;

    const inboxList = document.getElementById('inbox-list');
    inboxList.innerHTML = '<p style="padding: 20px; color: var(--text-secondary);">Loading emails...</p>';

    const result = await ipcRenderer.invoke('get-inbox', selectedAccountId, 20);

    if (result.success) {
        inboxList.innerHTML = '';
        if (result.emails.length === 0) {
            inboxList.innerHTML = '<p style="padding: 20px; color: var(--text-secondary);">Inbox is empty</p>';
            return;
        }

        result.emails.forEach(email => {
            const item = document.createElement('div');
            item.className = 'inbox-item';
            item.innerHTML = `
                <div class="from">${email.from}</div>
                <div class="subject">${email.subject || '(No Subject)'}</div>
                <div class="date">${new Date(email.date).toLocaleString()}</div>
            `;
            inboxList.appendChild(item);
        });
    } else {
        inboxList.innerHTML = `<p style="padding: 20px; color: var(--error);">Error: ${result.error}</p>`;
    }
}

// Mail Tabs
document.querySelectorAll('.mail-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const target = tab.dataset.tab;
        currentMailTab = target;

        document.querySelectorAll('.mail-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        document.querySelectorAll('.mail-tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(`mail-${target}-tab`).classList.add('active');
    });
});

document.getElementById('refresh-inbox-btn').addEventListener('click', refreshInbox);

document.getElementById('send-mail-btn').addEventListener('click', async () => {
    if (!selectedAccountId) return;

    const to = document.getElementById('mail-to').value;
    const subject = document.getElementById('mail-subject').value;
    const body = document.getElementById('mail-body').value;

    if (!to || !subject || !body) {
        alert('Please fill all fields');
        return;
    }

    const btn = document.getElementById('send-mail-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';

    const result = await ipcRenderer.invoke('send-mail', selectedAccountId, to, subject, body);

    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-paper-plane"></i> Send Email';

    if (result.success) {
        alert('Email sent successfully!');
        document.getElementById('mail-to').value = '';
        document.getElementById('mail-subject').value = '';
        document.getElementById('mail-body').value = '';
    } else {
        alert(`Failed to send email: ${result.error}`);
    }
});

document.getElementById('ai-generate-body').addEventListener('click', async () => {
    const subject = document.getElementById('mail-subject').value;
    const prompt = subject || 'Write a professional email';

    const btn = document.getElementById('ai-generate-body');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-robot"></i> Generating...';

    // In a real app we'd call the AI module, for now simplified simulation or direct call if available
    // For now we'll use a placeholder or call Groq if configured
    const result = await ipcRenderer.invoke('update-config', 'ai.prompt', prompt); // Placeholder trigger

    document.getElementById('mail-body').value = "Hello,\n\nI hope this email finds you well.\n\n[This feature will use the Groq AI module to generate unique relevant content based on your subject]\n\nBest regards,\nLEOmail AI";

    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-robot"></i> AI Generate';
});

let registrationInterval;

function startRegistrationPolling() {
    if (registrationInterval) {
        clearInterval(registrationInterval);
    }

    registrationInterval = setInterval(async () => {
        await loadRegistrationStatus();
    }, 2000);
}

async function loadRegistrationStatus() {
    const status = await ipcRenderer.invoke('get-queue-status');

    document.getElementById('queue-length').textContent = status.queueLength;
    document.getElementById('queue-progress').textContent = status.stats.inProgress;
    document.getElementById('queue-completed').textContent = status.stats.completed;
    document.getElementById('queue-failed').textContent = status.stats.failed;

    const successRate = status.stats.total > 0
        ? ((status.stats.completed / status.stats.total) * 100).toFixed(1)
        : 0;
    document.getElementById('queue-success-rate').textContent = successRate + '%';

    // Update progress bar
    const progress = status.stats.total > 0
        ? ((status.stats.completed + status.stats.failed) / status.stats.total) * 100
        : 0;
    document.getElementById('registration-progress').style.width = progress + '%';

    // Stop polling if not processing
    if (!status.isProcessing && registrationInterval) {
        clearInterval(registrationInterval);
        registrationInterval = null;
    }
}

// Warmup
async function loadWarmupStatus() {
    const status = await ipcRenderer.invoke('get-warmup-status');

    document.getElementById('warmup-pending').textContent = status.pending || 0;
    document.getElementById('warmup-active').textContent = status.active || 0;
    document.getElementById('warmup-completed').textContent = status.completed || 0;
}

// Accounts
async function loadAccounts() {
    const accounts = await ipcRenderer.invoke('get-accounts');
    const tbody = document.getElementById('accounts-tbody');
    tbody.innerHTML = '';

    accounts.forEach(account => {
        const row = document.createElement('tr');

        const statusBadge = account.status === 'created'
            ? '<span class="badge success">Active</span>'
            : '<span class="badge error">Failed</span>';

        const warmupBadge = account.warmup_status === 'completed'
            ? '<span class="badge success">Completed</span>'
            : account.warmup_status === 'active'
                ? '<span class="badge warning">Active</span>'
                : '<span class="badge">Pending</span>';

        row.innerHTML = `
            <td>${account.email}</td>
            <td>${account.password.substring(0, 8)}***</td>
            <td>${account.recovery_email || 'N/A'}</td>
            <td>${statusBadge}</td>
            <td>${warmupBadge}</td>
            <td>${new Date(account.created_at).toLocaleDateString()}</td>
            <td>
                <button class="btn btn-secondary" onclick="deleteAccount('${account.id}')">Delete</button>
            </td>
        `;

        tbody.appendChild(row);
    });
}

async function deleteAccount(accountId) {
    if (confirm('Are you sure you want to delete this account?')) {
        await ipcRenderer.invoke('delete-account', accountId);
        await loadAccounts();
    }
}

// Proxies
async function loadProxies() {
    const proxies = await ipcRenderer.invoke('get-proxies');
    const tbody = document.getElementById('proxies-tbody');
    tbody.innerHTML = '';

    proxies.forEach(proxy => {
        const row = document.createElement('tr');

        const mobileBadge = proxy.is_mobile
            ? '<span class="badge success">Mobile</span>'
            : '<span class="badge">Residential</span>';

        const statusBadge = proxy.is_active
            ? '<span class="badge success">Active</span>'
            : '<span class="badge error">Inactive</span>';

        const successRate = proxy.success_count + proxy.fail_count > 0
            ? ((proxy.success_count / (proxy.success_count + proxy.fail_count)) * 100).toFixed(0)
            : 0;

        row.innerHTML = `
            <td>${proxy.host}</td>
            <td>${proxy.port}</td>
            <td>${proxy.type.toUpperCase()}</td>
            <td>${mobileBadge}</td>
            <td>${successRate}%</td>
            <td>${statusBadge}</td>
            <td>
                <button class="btn btn-secondary" onclick="testProxy('${proxy.id}')">Test</button>
                <button class="btn btn-secondary" onclick="deleteProxy('${proxy.id}')">Delete</button>
            </td>
        `;

        tbody.appendChild(row);
    });
}

async function testProxy(proxyId) {
    const result = await ipcRenderer.invoke('test-proxy', proxyId);

    if (result.success) {
        alert(`Proxy is working! IP: ${result.ip}`);
    } else {
        alert(`Proxy test failed: ${result.error}`);
    }
}

async function deleteProxy(proxyId) {
    if (confirm('Are you sure you want to delete this proxy?')) {
        await ipcRenderer.invoke('delete-proxy', proxyId);
        await loadProxies();
    }
}

// Export
document.getElementById('export-btn').addEventListener('click', async () => {
    const format = document.getElementById('export-format').value;
    const filterValue = document.getElementById('export-filter').value;

    const filter = filterValue ? { warmupStatus: filterValue } : {};

    const filePath = await ipcRenderer.invoke('export-accounts', format, filter);

    document.getElementById('export-result').innerHTML = `
        <div class="success-message">
            ✅ Accounts exported successfully!<br>
            <strong>File:</strong> ${filePath}
        </div>
    `;
});

// Settings
async function loadSettings() {
    const config = await ipcRenderer.invoke('get-config');

    document.getElementById('sms-activate-key').value = config.smsServices?.services?.['sms-activate']?.apiKey || '';
    document.getElementById('sms-5sim-key').value = config.smsServices?.services?.['5sim']?.apiKey || '';
    document.getElementById('sms-grizzly-key').value = config.smsServices?.services?.['grizzly']?.apiKey || '';
    document.getElementById('sms-simsms-key').value = config.smsServices?.services?.['simsms']?.apiKey || '';
    document.getElementById('captcha-provider').value = config.captchaServices?.provider || 'capguru';
    document.getElementById('captcha-key').value = config.captchaServices?.apiKey || '';
    document.getElementById('groq-key').value = config.ai?.apiKey || '';
    document.getElementById('max-workers').value = config.app?.maxParallelWorkers || 35;
}

document.getElementById('save-settings').addEventListener('click', async () => {
    await ipcRenderer.invoke('update-config', 'smsServices.services.grizzly.apiKey', document.getElementById('sms-grizzly-key').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.grizzly.enabled', !!document.getElementById('sms-grizzly-key').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.simsms.apiKey', document.getElementById('sms-simsms-key').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.simsms.enabled', !!document.getElementById('sms-simsms-key').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.sms-activate.apiKey', document.getElementById('sms-activate-key').value);
    await ipcRenderer.invoke('update-config', 'smsServices.services.5sim.apiKey', document.getElementById('sms-5sim-key').value);

    await ipcRenderer.invoke('update-config', 'captchaServices.provider', document.getElementById('captcha-provider').value);
    await ipcRenderer.invoke('update-config', 'captchaServices.apiKey', document.getElementById('captcha-key').value);

    await ipcRenderer.invoke('update-config', 'ai.apiKey', document.getElementById('groq-key').value);
    await ipcRenderer.invoke('update-config', 'app.maxParallelWorkers', parseInt(document.getElementById('max-workers').value));

    alert('Settings saved successfully! Optimized v3 configuration active.');
});

// Auto-refresh dashboard
setInterval(async () => {
    const activePage = document.querySelector('.page.active');
    if (activePage && activePage.id === 'dashboard') {
        await loadDashboard();
    }
}, 5000);

// Initial load
loadDashboard();
