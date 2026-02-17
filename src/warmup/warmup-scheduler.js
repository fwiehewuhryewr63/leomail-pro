const cron = require('node-cron');
const { v4: uuidv4 } = require('uuid');
const logger = require('../utils/logger');
const AIEmailGenerator = require('./ai-email-generator');
const GmailAutomator = require('./gmail-automator');

/**
 * Warmup Scheduler
 * Schedules and executes warm-up activities over 3-7 days
 */

class WarmupScheduler {
    constructor(database, browserLauncher, config) {
        this.db = database;
        this.browserLauncher = browserLauncher;
        this.config = config;
        this.aiGenerator = new AIEmailGenerator(config);
        this.gmailAutomator = new GmailAutomator(browserLauncher);
        this.activeWarmups = new Map();
    }

    /**
     * Start warm-up for an account
     */
    async startWarmup(accountId) {
        try {
            const account = await this.db.get('SELECT * FROM accounts WHERE id = ?', [accountId]);

            if (!account) {
                throw new Error('Account not found');
            }

            if (account.warmup_status === 'completed') {
                logger.warning(`Account ${account.email} already warmed up`);
                return;
            }

            logger.info(`Starting warm-up for ${account.email}`);

            // Update status
            await this.db.run(
                'UPDATE accounts SET warmup_status = ?, warmup_day = ? WHERE id = ?',
                ['active', 0, accountId]
            );

            // Schedule warm-up tasks
            this.scheduleWarmupTasks(accountId);

            logger.success(`Warm-up started for ${account.email}`);
        } catch (error) {
            logger.error('Failed to start warm-up', error);
        }
    }

    /**
     * Schedule warm-up tasks
     */
    scheduleWarmupTasks(accountId) {
        // Run warm-up activities 2-3 times per day
        const schedule = '0 */8 * * *'; // Every 8 hours

        const task = cron.schedule(schedule, async () => {
            await this.performWarmupActivity(accountId);
        });

        this.activeWarmups.set(accountId, task);
    }

    /**
     * Perform warm-up activity for a day
     */
    async performWarmupActivity(accountId) {
        let browser = null;

        try {
            const account = await this.db.get('SELECT * FROM accounts WHERE id = ?', [accountId]);

            if (!account) {
                logger.error(`Account ${accountId} not found`);
                return;
            }

            const currentDay = account.warmup_day + 1;
            const maxDays = this.config.get('warmup.durationDays') || 3;

            logger.info(`Performing Day ${currentDay} warm-up for ${account.email}`);

            // Get fingerprint and proxy
            const fingerprint = await this.db.get('SELECT * FROM fingerprints WHERE id = ?', [account.fingerprint_id]);
            const proxy = await this.db.get('SELECT * FROM proxies WHERE id = ?', [account.proxy_id]);

            // Login
            const loginResult = await this.gmailAutomator.login(account, fingerprint, proxy);
            browser = loginResult.browser;
            const page = loginResult.page;

            // Perform activities based on day
            if (currentDay === 1) {
                await this.day1Activities(account, browser, page);
            } else if (currentDay === 2) {
                await this.day2Activities(account, browser, page);
            } else if (currentDay >= 3) {
                await this.day3PlusActivities(account, browser, page);
            }

            // Update progress
            await this.db.run(
                'UPDATE accounts SET warmup_day = ?, last_login = CURRENT_TIMESTAMP WHERE id = ?',
                [currentDay, accountId]
            );

            // Log activity
            await this.db.run(
                'INSERT INTO warmup_progress (id, account_id, day, activity_type, activity_data) VALUES (?, ?, ?, ?, ?)',
                [uuidv4(), accountId, currentDay, 'daily_warmup', JSON.stringify({ completed: true })]
            );

            // Check if warm-up is complete
            if (currentDay >= maxDays) {
                await this.completeWarmup(accountId);
            }

            await this.gmailAutomator.logout(browser);
            logger.success(`Day ${currentDay} warm-up completed for ${account.email}`);

        } catch (error) {
            logger.error(`Warm-up activity failed for account ${accountId}`, error);

            if (browser) {
                await browser.close();
            }
        }
    }

    /**
     * Day 1 activities: Basic login/logout, inbox viewing
     */
    async day1Activities(account, browser, page) {
        logger.info('Day 1: Basic activity');

        // Read a few emails (if any)
        await this.gmailAutomator.readEmails(page, 2);
        await this.randomDelay(2000, 5000);

        // Random mouse movements
        await this.gmailAutomator.performRandomActivity(page);
        await this.randomDelay(3000, 6000);

        // Stay logged in for a bit
        await this.randomDelay(5000, 10000);
    }

    /**
     * Day 2 activities: More interaction, send first emails
     */
    async day2Activities(account, browser, page) {
        logger.info('Day 2: Increased activity');

        // Read more emails
        await this.gmailAutomator.readEmails(page, 3);
        await this.randomDelay(2000, 4000);

        // Send emails to other warm-up accounts
        const warmupAccounts = await this.db.all(
            'SELECT * FROM accounts WHERE warmup_status IN (?, ?) AND id != ? LIMIT 2',
            ['active', 'completed', account.id]
        );

        for (const recipient of warmupAccounts) {
            const email = await this.aiGenerator.generateEmail('personal');

            await this.gmailAutomator.sendEmail(browser, page, recipient.email, email.subject, email.body);

            // Save to database
            await this.db.run(
                'INSERT INTO warmup_emails (id, from_account_id, to_account_id, subject, body) VALUES (?, ?, ?, ?, ?)',
                [uuidv4(), account.id, recipient.id, email.subject, email.body]
            );

            await this.randomDelay(3000, 6000);
        }

        // Random activity
        await this.gmailAutomator.performRandomActivity(page);
    }

    /**
     * Day 3+ activities: Full engagement
     */
    async day3PlusActivities(account, browser, page) {
        logger.info('Day 3+: Full activity');

        // Read emails
        await this.gmailAutomator.readEmails(page, 5);
        await this.randomDelay(2000, 4000);

        // Send more emails
        const warmupAccounts = await this.db.all(
            'SELECT * FROM accounts WHERE warmup_status IN (?, ?) AND id != ? LIMIT 3',
            ['active', 'completed', account.id]
        );

        for (const recipient of warmupAccounts) {
            // Check if we have previous emails to reply to
            const previousEmail = await this.db.get(
                'SELECT * FROM warmup_emails WHERE from_account_id = ? AND to_account_id = ? ORDER BY sent_at DESC LIMIT 1',
                [recipient.id, account.id]
            );

            let email;
            if (previousEmail && Math.random() > 0.5) {
                // Reply to previous email
                email = await this.aiGenerator.generateReply(previousEmail);

                await this.db.run(
                    'INSERT INTO warmup_emails (id, from_account_id, to_account_id, subject, body, is_reply, parent_email_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    [uuidv4(), account.id, recipient.id, 'Re: ' + previousEmail.subject, email.body, 1, previousEmail.id]
                );
            } else {
                // Send new email
                email = await this.aiGenerator.generateEmail(Math.random() > 0.5 ? 'personal' : 'casual');

                await this.db.run(
                    'INSERT INTO warmup_emails (id, from_account_id, to_account_id, subject, body) VALUES (?, ?, ?, ?, ?)',
                    [uuidv4(), account.id, recipient.id, email.subject, email.body]
                );
            }

            await this.gmailAutomator.sendEmail(browser, page, recipient.email, email.subject, email.body);
            await this.randomDelay(3000, 6000);
        }

        // Mark some emails as important
        await this.gmailAutomator.markImportant(page);
        await this.randomDelay(2000, 4000);

        // Perform search
        await this.gmailAutomator.search(page, 'important');
        await this.randomDelay(2000, 4000);

        // Random activity
        await this.gmailAutomator.performRandomActivity(page);
    }

    /**
     * Complete warm-up
     */
    async completeWarmup(accountId) {
        await this.db.run(
            'UPDATE accounts SET warmup_status = ? WHERE id = ?',
            ['completed', accountId]
        );

        // Stop scheduled tasks
        const task = this.activeWarmups.get(accountId);
        if (task) {
            task.stop();
            this.activeWarmups.delete(accountId);
        }

        const account = await this.db.get('SELECT * FROM accounts WHERE id = ?', [accountId]);
        logger.success(`Warm-up completed for ${account.email}`);
    }

    /**
     * Start warm-up for all pending accounts
     */
    async startAllPendingWarmups() {
        const accounts = await this.db.all('SELECT * FROM accounts WHERE warmup_status = ?', ['pending']);

        logger.info(`Starting warm-up for ${accounts.length} accounts`);

        for (const account of accounts) {
            await this.startWarmup(account.id);
            await this.randomDelay(1000, 3000);
        }
    }

    /**
     * Get warm-up status
     */
    async getWarmupStatus() {
        const stats = await this.db.get(`
      SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN warmup_status = 'pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN warmup_status = 'active' THEN 1 ELSE 0 END) as active,
        SUM(CASE WHEN warmup_status = 'completed' THEN 1 ELSE 0 END) as completed
      FROM accounts
    `);

        return stats;
    }

    randomDelay(min, max) {
        const delay = Math.floor(Math.random() * (max - min + 1)) + min;
        return new Promise(resolve => setTimeout(resolve, delay));
    }
}

module.exports = WarmupScheduler;
