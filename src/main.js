const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const Database = require('./database/db');
const BrowserLauncher = require('./emulation/browser-launcher');
const ProxyManager = require('./proxy/proxy-manager');
const SMSService = require('./services/sms-service');
const CaptchaService = require('./services/captcha-service');
const GmailRegistrar = require('./registration/gmail-registrar');
const YahooRegistrar = require('./registration/yahoo-registrar');
const OutlookRegistrar = require('./registration/outlook-registrar');
const MailClient = require('./mailer/mail-client');
const WarmupScheduler = require('./warmup/warmup-scheduler');
const TaskQueue = require('./queue/task-queue');
const FarmManager = require('./database/farm-manager');
const AccountExporter = require('./export/account-exporter');
const BalanceCalculator = require('./utils/balance-calculator');
const config = require('./utils/config');
const logger = require('./utils/logger');

/**
 * Main Electron Application - LEOmail
 */

let mainWindow;
let db;
let browserLauncher;
let proxyManager;
let smsService;
let captchaService;
let registrars = {};
let warmupScheduler;
let taskQueue;
let farmManager;
let balanceCalculator;
let accountExporter;

async function createWindow() {
    console.log('🖥️ Creating main window...');
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false
        },
        backgroundColor: '#0a0a0a',
        title: 'LEOmail - Advanced Multi-Provider Email Platform',
        icon: path.join(__dirname, '../resources/icon.ico')
    });

    mainWindow.loadFile(path.join(__dirname, 'ui/index.html'));
    // ...
}

async function initializeApp() {
    try {
        console.log('🚀 Starting initialization...');
        logger.info('Initializing LEOmail Pro...');

        // Initialize database
        console.log('📂 Initializing database...');
        db = new Database();
        await db.initialize();

        // Initialize components
        browserLauncher = new BrowserLauncher();
        proxyManager = new ProxyManager(db);
        smsService = new SMSService(config);
        captchaService = new CaptchaService(config);

        // Initialize registrars
        registrars.gmail = new GmailRegistrar(db, browserLauncher, proxyManager, smsService, captchaService, config);
        registrars.yahoo = new YahooRegistrar(db, browserLauncher, proxyManager, smsService, captchaService, config);
        registrars.outlook = new OutlookRegistrar(db, browserLauncher, proxyManager, smsService, captchaService, config);

        warmupScheduler = new WarmupScheduler(db, browserLauncher, config);
        taskQueue = new TaskQueue(db, registrars, config);
        farmManager = new FarmManager(db);
        balanceCalculator = new BalanceCalculator(config, smsService, captchaService);
        accountExporter = new AccountExporter(db);

        console.log('✨ Components initialized');
        logger.success('LEOmail initialized successfully');

        // Start pending warmups
        console.log('🔥 Starting warmups...');
        await warmupScheduler.startAllPendingWarmups();
        console.log('✅ Initialization complete');

    } catch (error) {
        logger.error('Failed to initialize application', error);
        app.quit();
    }
}

// IPC Handlers
function setupIPCHandlers() {
    // Registration
    ipcMain.handle('start-registration', async (event, count, provider) => {
        try {
            await taskQueue.addTask(count, provider);
            return { success: true };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    // Mailer
    ipcMain.handle('send-mail', async (event, accountId, to, subject, body) => {
        const account = await db.get('SELECT * FROM accounts WHERE id = ?', [accountId]);
        if (!account) return { success: false, error: 'Account not found' };

        const mailClient = new MailClient(account);
        return await mailClient.sendEmail(to, subject, body);
    });

    ipcMain.handle('get-inbox', async (event, accountId, limit) => {
        const account = await db.get('SELECT * FROM accounts WHERE id = ?', [accountId]);
        if (!account) return { success: false, error: 'Account not found' };

        const mailClient = new MailClient(account);
        try {
            const emails = await mailClient.getInbox(limit);
            return { success: true, emails };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('stop-registration', async () => {
        taskQueue.stopProcessing();
        return { success: true };
    });

    ipcMain.handle('get-queue-status', async () => {
        return taskQueue.getStatus();
    });

    // Farms
    ipcMain.handle('get-farms', async () => {
        return await farmManager.getAllFarms();
    });

    ipcMain.handle('create-farm', async (event, name, description) => {
        return await farmManager.createFarm(name, description);
    });

    ipcMain.handle('add-to-farm', async (event, farmId, accountIds) => {
        return await farmManager.addAccountsToFarm(farmId, accountIds);
    });

    ipcMain.handle('get-farm-accounts', async (event, farmId) => {
        return await farmManager.getFarmAccounts(farmId);
    });

    ipcMain.handle('delete-farm', async (event, farmId) => {
        return await farmManager.deleteFarm(farmId);
    });

    // Accounts
    ipcMain.handle('get-accounts', async () => {
        return await db.all('SELECT * FROM accounts ORDER BY created_at DESC');
    });

    ipcMain.handle('delete-account', async (event, accountId) => {
        await db.run('DELETE FROM accounts WHERE id = ?', [accountId]);
        return { success: true };
    });

    // Proxies
    ipcMain.handle('get-proxies', async () => {
        return await proxyManager.getAllProxies();
    });

    ipcMain.handle('add-proxy', async (event, proxyConfig) => {
        return await proxyManager.addProxy(proxyConfig);
    });

    ipcMain.handle('delete-proxy', async (event, proxyId) => {
        await proxyManager.deleteProxy(proxyId);
        return { success: true };
    });

    ipcMain.handle('check-proxy-expirations', async () => {
        return await proxyManager.checkLeaseExpirations();
    });

    ipcMain.handle('check-feasibility', async (event, count, provider) => {
        return await balanceCalculator.checkFeasibility(count, provider);
    });

    ipcMain.handle('test-proxy', async (event, proxyId) => {
        const proxy = await db.get('SELECT * FROM proxies WHERE id = ?', [proxyId]);
        return await proxyManager.testProxy(proxy);
    });

    ipcMain.handle('import-proxies', async (event, filePath, isMobile) => {
        return await proxyManager.importFromFile(filePath, isMobile);
    });

    // Warmup
    ipcMain.handle('start-warmup', async (event, accountId) => {
        await warmupScheduler.startWarmup(accountId);
        return { success: true };
    });

    ipcMain.handle('get-warmup-status', async () => {
        return await warmupScheduler.getWarmupStatus();
    });

    // Export
    ipcMain.handle('export-accounts', async (event, format, filter) => {
        const content = await accountExporter.exportAccounts(format, filter);
        const filename = `accounts_${Date.now()}.${format === 'json' ? 'json' : format === 'csv' ? 'csv' : 'txt'}`;
        return await accountExporter.saveToFile(content, filename);
    });

    ipcMain.handle('get-export-stats', async () => {
        return await accountExporter.getExportStats();
    });

    // Settings
    ipcMain.handle('get-config', async () => {
        return config.getAll();
    });

    ipcMain.handle('update-config', async (event, key, value) => {
        config.set(key, value);
        return { success: true };
    });

    // Statistics
    ipcMain.handle('get-statistics', async () => {
        const accounts = await db.get(`
      SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN status = 'created' THEN 1 ELSE 0 END) as created,
        SUM(CASE WHEN warmup_status = 'completed' THEN 1 ELSE 0 END) as warmed
      FROM accounts
    `);

        const proxies = await db.get(`
      SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN is_mobile = 1 THEN 1 ELSE 0 END) as mobile,
        SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active
      FROM proxies
    `);

        const recentActivity = await db.all(`
      SELECT * FROM activity_logs 
      ORDER BY created_at DESC 
      LIMIT 50
    `);

        return {
            accounts,
            proxies,
            recentActivity,
            queueStatus: taskQueue.getStatus()
        };
    });
}

// App lifecycle
app.whenReady().then(async () => {
    await initializeApp();
    setupIPCHandlers();
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('before-quit', async () => {
    logger.info('Application shutting down...');

    if (db) {
        await db.close();
    }

    logger.success('Application closed');
});
