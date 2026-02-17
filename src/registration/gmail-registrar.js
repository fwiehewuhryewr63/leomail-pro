const BaseRegistrar = require('./base-registrar');
const { v4: uuidv4 } = require('uuid');
const logger = require('../utils/logger');
const FormFiller = require('./form-filler');
const BypassStrategies = require('./bypass-strategies');

/**
 * Gmail Registrar
 * Handles Gmail-specific registration flow
 */
class GmailRegistrar extends BaseRegistrar {
    constructor(database, browserLauncher, proxyManager, smsService, captchaService, config) {
        super(database, browserLauncher, proxyManager, smsService, captchaService, config);
        this.provider = 'gmail';
    }

    /**
     * Register a single Gmail account
     */
    async registerAccount(fingerprintId = null, proxyId = null) {
        const accountId = uuidv4();
        let browser = null;
        let smsActivation = null;

        try {
            logger.info(`Starting registration for account ${accountId}`);

            // Get fingerprint
            const fingerprint = fingerprintId
                ? await this.db.get('SELECT * FROM fingerprints WHERE id = ?', [fingerprintId])
                : await this.getOrCreateFingerprint();

            // Get proxy
            const proxy = proxyId
                ? await this.db.get('SELECT * FROM proxies WHERE id = ?', [proxyId])
                : await this.proxyManager.getNextProxy(true); // Prefer mobile

            // Pre-registration checks
            const checks = await this.bypassStrategies.performPreRegistrationChecks(proxy, fingerprint);
            logger.info('Pre-registration checks completed', checks);

            // Generate user profile
            const userProfile = this.formFiller.generateUserProfile();

            // Create recovery email if enabled
            if (this.config.get('registration.autoCreateRecoveryEmail')) {
                userProfile.recoveryEmail = await this.createRecoveryEmail();
            }

            // Launch browser
            const launchResult = await this.browserLauncher.launch(fingerprint, accountId, proxy);
            browser = launchResult.browser;
            const page = launchResult.page;

            // Navigate to Gmail signup
            logger.info('Navigating to Gmail signup page...');
            await page.goto('https://accounts.google.com/signup', {
                waitUntil: 'networkidle2',
                timeout: 60000
            });

            // Natural behavior simulation
            await this.bypassStrategies.simulateNaturalBehavior(page);

            // Fill first name
            logger.info('Filling first name...');
            await this.formFiller.typeHuman(page, 'input[name="firstName"]', userProfile.firstName);
            await this.formFiller.randomDelay(500, 1000);

            // Fill last name
            logger.info('Filling last name...');
            await this.formFiller.typeHuman(page, 'input[name="lastName"]', userProfile.lastName);
            await this.formFiller.randomDelay(500, 1000);

            // Click Next
            await this.formFiller.clickHuman(page, 'button:has-text("Next")');
            await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

            // Fill birth date and gender
            logger.info('Filling birth date and gender...');
            await this.formFiller.selectDropdown(page, 'select#month', userProfile.birthDate.month);
            await this.formFiller.typeHuman(page, 'input#day', userProfile.birthDate.day.toString());
            await this.formFiller.typeHuman(page, 'input#year', userProfile.birthDate.year.toString());
            await this.formFiller.selectDropdown(page, 'select#gender', userProfile.gender === 'male' ? '1' : '2');
            await this.formFiller.randomDelay(500, 1000);

            // Click Next
            await this.formFiller.clickHuman(page, 'button:has-text("Next")');
            await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

            // Choose username
            logger.info('Choosing username...');

            // Try to use custom username first
            const createOwnButton = await page.$('button:has-text("Create your own")');
            if (createOwnButton) {
                await createOwnButton.click();
                await this.formFiller.randomDelay(1000, 2000);
            }

            await this.formFiller.typeHuman(page, 'input[name="Username"]', userProfile.username);
            await this.formFiller.randomDelay(500, 1000);

            // Click Next
            await this.formFiller.clickHuman(page, 'button:has-text("Next")');
            await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

            // Check if username is taken
            const errorText = await page.evaluate(() => document.body.innerText);
            if (errorText.includes('already taken') || errorText.includes('not available')) {
                logger.warning('Username taken, trying with number suffix...');
                userProfile.username += Math.floor(Math.random() * 10000);
                await page.goto('https://accounts.google.com/signup', { waitUntil: 'networkidle2' });
                // Restart the process with new username
                // (simplified for now - in production, implement proper retry logic)
            }

            // Fill password
            logger.info('Setting password...');
            await this.formFiller.typeHuman(page, 'input[name="Passwd"]', userProfile.password);
            await this.formFiller.typeHuman(page, 'input[name="ConfirmPasswd"]', userProfile.password);
            await this.formFiller.randomDelay(500, 1000);

            // Click Next
            await this.formFiller.clickHuman(page, 'button:has-text("Next")');
            await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

            // Handle phone verification
            const smsRequired = await this.bypassStrategies.isSMSRequired(page);

            if (smsRequired) {
                logger.info('Phone verification required');

                // Try to skip first
                const skipped = await this.bypassStrategies.attemptSMSSkip(page);

                if (!skipped) {
                    logger.info('SMS bypass failed, using SMS service...');

                    // 4. Phone Verification
                    logger.info('Starting phone verification with Smart Price Strategy...');
                    let phoneRecord;
                    try {
                        // The new SMSService handles the 3-attempt/price-ladder logic internally
                        phoneRecord = await this.smsService.getPhoneNumber('any', 'google');
                    } catch (e) {
                        logger.error('Failed to get number even after price ladders');
                        throw e;
                    }

                    const phoneNumber = phoneRecord.number;
                    const activationId = phoneRecord.activationId;
                    const service = phoneRecord.service;

                    // Set smsActivation for later cancellation if needed
                    smsActivation = { number: phoneNumber, activationId, service };

                    // Enter phone number
                    await this.formFiller.typeHuman(page, 'input[type="tel"]', phoneNumber);
                    await this.formFiller.clickHuman(page, 'button:has-text("Next")');
                    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

                    // Wait for SMS code
                    logger.info('Waiting for SMS code...');
                    const smsCode = await this.smsService.getSMSCode(service, activationId);

                    // Enter verification code
                    await this.formFiller.typeHuman(page, 'input[name="code"]', smsCode);
                    await this.formFiller.clickHuman(page, 'button:has-text("Verify")');
                    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });
                }
            }

            // Handle captcha if present
            const captchaPresent = await this.bypassStrategies.isCaptchaPresent(page);

            if (captchaPresent) {
                logger.info('Captcha detected, solving...');

                const siteKey = await page.evaluate(() => {
                    const iframe = document.querySelector('iframe[src*="recaptcha"]');
                    if (iframe) {
                        const src = iframe.getAttribute('src');
                        const match = src.match(/k=([^&]+)/);
                        return match ? match[1] : null;
                    }
                    return null;
                });

                if (siteKey) {
                    const solution = await this.captchaService.solveRecaptchaV2(siteKey, page.url());
                    await this.captchaService.injectSolution(page, solution);
                    await this.formFiller.randomDelay(1000, 2000);
                }
            }

            // Add recovery email if provided
            if (userProfile.recoveryEmail) {
                logger.info('Adding recovery email...');
                const recoveryInput = await page.$('input[type="email"]');
                if (recoveryInput) {
                    await this.formFiller.typeHuman(page, 'input[type="email"]', userProfile.recoveryEmail.email);
                    await this.formFiller.clickHuman(page, 'button:has-text("Next")');
                    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });
                }
            }

            // Skip remaining optional steps
            logger.info('Skipping optional steps...');
            const skipButtons = await page.$$('button:has-text("Skip"), button:has-text("Not now")');
            for (const button of skipButtons) {
                try {
                    await button.click();
                    await this.formFiller.randomDelay(1000, 2000);
                } catch (e) {
                    // Ignore errors
                }
            }

            // Accept terms
            logger.info('Accepting terms...');
            const agreeButton = await page.$('button:has-text("I agree"), button:has-text("Agree")');
            if (agreeButton) {
                await agreeButton.click();
                await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });
            }

            // Verify account creation
            await this.formFiller.randomDelay(3000, 5000);
            const currentUrl = page.url();
            const isSuccess = currentUrl.includes('myaccount.google.com') ||
                currentUrl.includes('mail.google.com') ||
                await page.evaluate(() => document.body.innerText.includes('Welcome'));

            if (isSuccess) {
                // Save account to database
                const finalEmail = `${userProfile.username}@gmail.com`;

                await this.db.run(
                    `INSERT INTO accounts (id, email, password, recovery_email, recovery_password, phone_number, fingerprint_id, proxy_id, status, warmup_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
                    [
                        accountId,
                        finalEmail,
                        userProfile.password,
                        userProfile.recoveryEmail?.email || null,
                        userProfile.recoveryEmail?.password || null,
                        smsActivation?.number || null,
                        fingerprint.id,
                        proxy.id,
                        'created',
                        'pending'
                    ]
                );

                // Log activity
                await this.db.run(
                    `INSERT INTO activity_logs (id, account_id, action, status)
           VALUES (?, ?, ?, ?)`,
                    [uuidv4(), accountId, 'registration', 'success']
                );

                // Update proxy success count
                await this.proxyManager.recordSuccess(proxy.id);

                logger.success(`Account created successfully: ${finalEmail}`);

                await browser.close();

                return {
                    success: true,
                    account: {
                        id: accountId,
                        email: finalEmail,
                        password: userProfile.password,
                        recoveryEmail: userProfile.recoveryEmail?.email,
                        recoveryPassword: userProfile.recoveryEmail?.password
                    }
                };
            } else {
                throw new Error('Account creation verification failed');
            }

        } catch (error) {
            logger.error('Registration failed', error);

            // Cancel SMS activation if active
            if (smsActivation) {
                await this.smsService.cancelActivation(smsActivation.service, smsActivation.activationId);
            }

            // Log failure
            await this.db.run(
                `INSERT INTO activity_logs (id, account_id, action, status, details)
         VALUES (?, ?, ?, ?, ?)`,
                [uuidv4(), accountId, 'registration', 'failed', error.message]
            );

            if (browser) {
                await browser.close();
            }

            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Get or create fingerprint
     */
    async getOrCreateFingerprint() {
        const MobileFingerprintGenerator = require('../emulation/mobile-fingerprints');
        const DesktopFingerprintGenerator = require('../emulation/desktop-fingerprints');

        const preferMobile = this.config.get('registration.preferMobileProxies');
        const generator = preferMobile ? new MobileFingerprintGenerator() : new DesktopFingerprintGenerator();

        const fingerprint = generator.generate();

        // Save to database
        await this.db.run(
            `INSERT INTO fingerprints (id, device_type, os, browser, user_agent, screen_width, screen_height, device_pixel_ratio, fingerprint_data)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [
                fingerprint.id,
                fingerprint.device_type,
                fingerprint.os,
                fingerprint.browser,
                fingerprint.user_agent,
                fingerprint.screen_width,
                fingerprint.screen_height,
                fingerprint.device_pixel_ratio,
                fingerprint.fingerprint_data
            ]
        );

        return fingerprint;
    }

    /**
     * Create recovery email
     */
    async createRecoveryEmail() {
        // For now, use a simple temp email service or create another Gmail
        // In production, implement proper recovery email creation
        const recoveryEmail = {
            email: `recovery.${Math.random().toString(36).substring(7)}@tempmail.com`,
            password: this.formFiller.generatePassword()
        };

        await this.db.run(
            `INSERT INTO recovery_emails (id, email, password)
       VALUES (?, ?, ?)`,
            [uuidv4(), recoveryEmail.email, recoveryEmail.password]
        );

        return recoveryEmail;
    }
}

module.exports = GmailRegistrar;
