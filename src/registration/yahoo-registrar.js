const BaseRegistrar = require('./base-registrar');
const logger = require('../utils/logger');
const { v4: uuidv4 } = require('uuid');

/**
 * Yahoo Registrar
 * Handles Yahoo-specific registration flow
 */
class YahooRegistrar extends BaseRegistrar {
    constructor(database, browserLauncher, proxyManager, smsService, captchaService, config) {
        super(database, browserLauncher, proxyManager, smsService, captchaService, config);
        this.provider = 'yahoo';
    }

    /**
     * Register Yahoo account
     */
    async registerAccount() {
        let browser, page, proxy, fingerprint;
        const accountId = uuidv4();

        try {
            logger.info('Starting Yahoo registration...');

            // Setup browser (prefer desktop for Yahoo as it's often more stable/cheaper)
            const setup = await this.setupBrowser(accountId, 'desktop');
            browser = setup.browser;
            page = setup.page;
            proxy = setup.proxy;
            fingerprint = setup.fingerprint;

            const profile = this.formFiller.generateProfile();
            const username = this.formFiller.generateUsername(profile.firstName, profile.lastName);

            await page.goto('https://login.yahoo.com/account/create', {
                waitUntil: 'networkidle2',
                timeout: 60000
            });

            // Fill basic info
            await page.type('#usernamereg-firstName', profile.firstName, { delay: 100 });
            await page.type('#usernamereg-lastName', profile.lastName, { delay: 100 });
            await page.type('#usernamereg-userId', username, { delay: 100 });
            await page.type('#usernamereg-password', profile.password, { delay: 100 });

            // Birth date
            await page.select('#usernamereg-month', profile.birthDate.month.toString());
            await page.type('#usernamereg-day', profile.birthDate.day.toString(), { delay: 100 });
            await page.type('#usernamereg-year', profile.birthDate.year.toString(), { delay: 100 });

            await this.randomDelay(1000, 2000);
            await page.click('#reg-submit-button');

            // Yahoo usually requires phone number
            if (await this.bypass.isSMSRequired(page)) {
                logger.info('Phone verification required for Yahoo');

                const smsResult = await this.smsService.getNumber('yahoo');
                await page.type('#usernamereg-phone', smsResult.phone, { delay: 100 });
                await page.click('#reg-submit-button');

                const code = await this.smsService.waitForCode(smsResult.id);
                await page.type('#verification-code-field', code, { delay: 100 });
                await page.click('#reg-submit-button');
            }

            // Check success
            await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

            const success = page.url().includes('success') || await page.$('.reg-success');

            if (success) {
                const accountData = {
                    id: uuidv4(),
                    email: `${username}@yahoo.com`,
                    password: profile.password,
                    provider: 'yahoo',
                    first_name: profile.firstName,
                    last_name: profile.lastName,
                    status: 'created',
                    fingerprint_id: fingerprint.id,
                    proxy_id: proxy ? proxy.id : null
                };

                await this.db.run(
                    'INSERT INTO accounts (id, email, password, provider, first_name, last_name, status, fingerprint_id, proxy_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    [accountData.id, accountData.email, accountData.password, accountData.provider, accountData.first_name, accountData.last_name, accountData.status, accountData.fingerprint_id, accountData.proxy_id]
                );

                logger.success(`Yahoo account created: ${accountData.email}`);
                await this.logActivity('Registration', 'success', `Created Yahoo account: ${accountData.email}`);

                await browser.close();
                return { success: true, account: accountData };
            } else {
                throw new Error('Yahoo registration failed - success indicator not found');
            }

        } catch (error) {
            logger.error('Yahoo registration failed', error);
            await this.logActivity('Registration', 'failed', `Yahoo error: ${error.message}`);
            if (browser) await browser.close();
            return { success: false, error: error.message };
        }
    }
}

module.exports = YahooRegistrar;
