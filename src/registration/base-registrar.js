const logger = require('../utils/logger');
const FormFiller = require('./form-filler');
const BypassStrategies = require('./bypass-strategies');

/**
 * Base Registrar Class
 * Abstract base for all email provider registrars
 */
class BaseRegistrar {
    constructor(database, browserLauncher, proxyManager, smsService, captchaService, config) {
        this.db = database;
        this.browserLauncher = browserLauncher;
        this.proxyManager = proxyManager;
        this.smsService = smsService;
        this.captchaService = captchaService;
        this.config = config;
        this.formFiller = new FormFiller();
        this.bypass = new BypassStrategies();
        this.provider = 'base';
    }

    /**
     * Main registration method to be implemented by children
     */
    async registerAccount() {
        throw new Error('registerAccount() must be implemented by subclass');
    }

    /**
     * Common setup for any registration
     */
    async setupBrowser(accountId, fingerprintType = 'mobile') {
        // Try to get permanently bound proxy first
        let proxy = await this.proxyManager.getAccountProxy(accountId);

        // If no permanent proxy, get a new one from the pool
        if (!proxy) {
            proxy = await this.proxyManager.getNextProxy();
        }

        const fingerprint = await this.browserLauncher.generateFingerprint(fingerprintType);

        const { browser, page } = await this.browserLauncher.launch(fingerprint, accountId, proxy);
        return { browser, page, proxy, fingerprint };
    }

    /**
     * Log activity to database
     */
    async logActivity(action, status, details = null) {
        await this.db.run(
            'INSERT INTO activity_logs (id, action, status, details) VALUES (?, ?, ?, ?)',
            [require('uuid').v4(), action, status, details]
        );
    }

    async randomDelay(min, max) {
        const delay = Math.floor(Math.random() * (max - min + 1)) + min;
        return new Promise(resolve => setTimeout(resolve, delay));
    }
}

module.exports = BaseRegistrar;
