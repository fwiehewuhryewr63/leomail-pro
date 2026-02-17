const BaseRegistrar = require('./base-registrar');
const logger = require('../utils/logger');
const { v4: uuidv4 } = require('uuid');

/**
 * Outlook Registrar
 * Handles Outlook/Hotmail-specific registration flow
 */
class OutlookRegistrar extends BaseRegistrar {
    constructor(database, browserLauncher, proxyManager, smsService, captchaService, config) {
        super(database, browserLauncher, proxyManager, smsService, captchaService, config);
        this.provider = 'outlook';
    }

    /**
     * Register Outlook account
     */
    async registerAccount() {
        let browser, page, proxy, fingerprint;
        const accountId = uuidv4();

        try {
            logger.info('Starting Outlook registration...');

            const setup = await this.setupBrowser(accountId, 'desktop');
            browser = setup.browser;
            page = setup.page;
            proxy = setup.proxy;
            fingerprint = setup.fingerprint;

            const profile = this.formFiller.generateProfile();
            const username = this.formFiller.generateUsername(profile.firstName, profile.lastName);

            await page.goto('https://signup.live.com/signup', {
                waitUntil: 'networkidle2',
                timeout: 60000
            });

            // Step 1: Username
            await page.waitForSelector('#MemberName', { timeout: 10000 });
            await page.type('#MemberName', `${username}@outlook.com`, { delay: 100 });
            await page.click('#iSignupAction');

            // Step 2: Password
            await page.waitForSelector('#PasswordInput', { timeout: 10000 });
            await page.type('#PasswordInput', profile.password, { delay: 100 });
            await page.click('#iSignupAction');

            // Step 3: Name
            await page.waitForSelector('#FirstName', { timeout: 10000 });
            await page.type('#FirstName', profile.firstName, { delay: 100 });
            await page.type('#LastName', profile.lastName, { delay: 100 });
            await page.click('#iSignupAction');

            // Step 4: Birth date
            await page.waitForSelector('#BirthMonth', { timeout: 10000 });
            await page.select('#BirthMonth', profile.birthDate.month.toString());
            await page.select('#BirthDay', profile.birthDate.day.toString());
            await page.type('#BirthYear', profile.birthDate.year.toString(), { delay: 100 });
            await page.click('#iSignupAction');

            // Outlook often shows FunCaptcha here
            logger.info('Waiting for Outlook verification (Captcha/SMS)...');

            // Handle potential SMS or Captcha
            // This part is complex for Outlook and depends on current AI/Captcha setup
            // For now, we wait for human intervention or automated bypass
            await this.randomDelay(5000, 10000);

            const success = await page.evaluate(() => {
                return window.location.href.includes('account.microsoft.com') || document.body.innerText.includes('Keep me signed in');
            });

            if (success) {
                const accountData = {
                    id: uuidv4(),
                    email: `${username}@outlook.com`,
                    password: profile.password,
                    provider: 'outlook',
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

                logger.success(`Outlook account created: ${accountData.email}`);
                await this.logActivity('Registration', 'success', `Created Outlook account: ${accountData.email}`);

                await browser.close();
                return { success: true, account: accountData };
            } else {
                throw new Error('Outlook registration failed - Success indicator not found');
            }

        } catch (error) {
            logger.error('Outlook registration failed', error);
            await this.logActivity('Registration', 'failed', `Outlook error: ${error.message}`);
            if (browser) await browser.close();
            return { success: false, error: error.message };
        }
    }
}

module.exports = OutlookRegistrar;
