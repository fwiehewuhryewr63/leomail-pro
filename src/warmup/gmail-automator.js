const logger = require('../utils/logger');
const { v4: uuidv4 } = require('uuid');

/**
 * Gmail Automator
 * Automates Gmail actions for warm-up
 */

class GmailAutomator {
    constructor(browserLauncher) {
        this.browserLauncher = browserLauncher;
    }

    /**
     * Login to Gmail
     */
    async login(account, fingerprint, proxy) {
        const { browser, page } = await this.browserLauncher.launch(fingerprint, account.id, proxy);

        try {
            logger.info(`Logging into ${account.email}...`);

            await page.goto('https://accounts.google.com/signin', {
                waitUntil: 'networkidle2',
                timeout: 60000
            });

            // Enter email
            await page.waitForSelector('input[type="email"]', { timeout: 10000 });
            await page.type('input[type="email"]', account.email, { delay: 100 });
            await page.click('button:has-text("Next")');
            await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

            // Enter password
            await page.waitForSelector('input[type="password"]', { timeout: 10000 });
            await page.type('input[type="password"]', account.password, { delay: 100 });
            await page.click('button:has-text("Next")');
            await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

            // Check if logged in
            await page.waitForTimeout(3000);
            const url = page.url();

            if (url.includes('myaccount.google.com') || url.includes('mail.google.com')) {
                logger.success(`Successfully logged into ${account.email}`);
                return { browser, page };
            } else {
                throw new Error('Login verification failed');
            }
        } catch (error) {
            await browser.close();
            throw error;
        }
    }

    /**
     * Send email
     */
    async sendEmail(browser, page, toEmail, subject, body) {
        try {
            logger.info(`Sending email to ${toEmail}...`);

            // Navigate to Gmail if not already there
            if (!page.url().includes('mail.google.com')) {
                await page.goto('https://mail.google.com', { waitUntil: 'networkidle2' });
            }

            // Click compose
            await page.waitForSelector('div[role="button"]:has-text("Compose")', { timeout: 10000 });
            await page.click('div[role="button"]:has-text("Compose")');
            await page.waitForTimeout(2000);

            // Fill recipient
            await page.type('input[aria-label*="To"]', toEmail, { delay: 100 });
            await page.waitForTimeout(500);

            // Fill subject
            await page.type('input[name="subjectbox"]', subject, { delay: 100 });
            await page.waitForTimeout(500);

            // Fill body
            await page.type('div[aria-label="Message Body"]', body, { delay: 80 });
            await page.waitForTimeout(1000);

            // Send
            await page.click('div[role="button"]:has-text("Send")');
            await page.waitForTimeout(2000);

            logger.success(`Email sent to ${toEmail}`);
            return true;
        } catch (error) {
            logger.error('Failed to send email', error);
            return false;
        }
    }

    /**
     * Read emails
     */
    async readEmails(page, count = 5) {
        try {
            logger.info(`Reading ${count} emails...`);

            // Navigate to inbox
            if (!page.url().includes('mail.google.com')) {
                await page.goto('https://mail.google.com', { waitUntil: 'networkidle2' });
            }

            await page.waitForTimeout(2000);

            // Get email list
            const emails = await page.$$('tr[role="row"]');
            const readCount = Math.min(count, emails.length);

            for (let i = 0; i < readCount; i++) {
                try {
                    await emails[i].click();
                    await page.waitForTimeout(2000 + Math.random() * 2000);

                    // Go back to inbox
                    await page.goBack();
                    await page.waitForTimeout(1000);
                } catch (e) {
                    // Continue on error
                }
            }

            logger.success(`Read ${readCount} emails`);
            return readCount;
        } catch (error) {
            logger.error('Failed to read emails', error);
            return 0;
        }
    }

    /**
     * Mark email as important
     */
    async markImportant(page) {
        try {
            // Click star icon
            const starButton = await page.$('div[aria-label*="Star"]');
            if (starButton) {
                await starButton.click();
                await page.waitForTimeout(1000);
                logger.success('Marked email as important');
                return true;
            }
            return false;
        } catch (error) {
            logger.error('Failed to mark as important', error);
            return false;
        }
    }

    /**
     * Create folder/label
     */
    async createLabel(page, labelName) {
        try {
            logger.info(`Creating label: ${labelName}...`);

            // Click settings
            await page.click('button[aria-label*="Settings"]');
            await page.waitForTimeout(1000);

            // Click "See all settings"
            await page.click('button:has-text("See all settings")');
            await page.waitForNavigation({ waitUntil: 'networkidle2' });

            // Go to Labels tab
            await page.click('button:has-text("Labels")');
            await page.waitForTimeout(1000);

            // Create new label
            await page.click('button:has-text("Create new label")');
            await page.waitForTimeout(1000);

            await page.type('input[aria-label*="label name"]', labelName);
            await page.click('button:has-text("Create")');
            await page.waitForTimeout(2000);

            logger.success(`Label created: ${labelName}`);
            return true;
        } catch (error) {
            logger.error('Failed to create label', error);
            return false;
        }
    }

    /**
     * Search in Gmail
     */
    async search(page, query) {
        try {
            logger.info(`Searching for: ${query}...`);

            await page.type('input[aria-label*="Search"]', query);
            await page.keyboard.press('Enter');
            await page.waitForNavigation({ waitUntil: 'networkidle2' });
            await page.waitForTimeout(2000);

            logger.success('Search completed');
            return true;
        } catch (error) {
            logger.error('Failed to search', error);
            return false;
        }
    }

    /**
     * Perform random activity
     */
    async performRandomActivity(page) {
        const activities = [
            async () => await this.readEmails(page, 2),
            async () => await this.search(page, 'important'),
            async () => {
                // Scroll inbox
                await page.evaluate(() => window.scrollBy(0, 300));
                await page.waitForTimeout(1000);
            }
        ];

        const activity = activities[Math.floor(Math.random() * activities.length)];
        await activity();
    }

    /**
     * Logout
     */
    async logout(browser) {
        try {
            await browser.close();
            logger.success('Logged out successfully');
        } catch (error) {
            logger.error('Failed to logout', error);
        }
    }
}

module.exports = GmailAutomator;
