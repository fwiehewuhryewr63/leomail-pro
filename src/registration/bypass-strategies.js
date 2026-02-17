const logger = require('../utils/logger');

/**
 * Bypass Strategies
 * Techniques to bypass SMS and captcha verification
 */

class BypassStrategies {
    constructor() {
        this.strategies = {
            sms: [
                'high_quality_proxy',
                'aged_ip',
                'natural_behavior',
                'optimal_timing',
                'fingerprint_quality'
            ],
            captcha: [
                'stealth_mode',
                'human_behavior',
                'canvas_randomization',
                'webgl_spoofing'
            ]
        };
    }

    /**
     * Check if SMS verification is required
     */
    async isSMSRequired(page) {
        try {
            // Look for phone number input
            const phoneInput = await page.$('input[type="tel"]');
            const phoneText = await page.evaluate(() => {
                return document.body.innerText.toLowerCase();
            });

            return phoneInput !== null ||
                phoneText.includes('phone number') ||
                phoneText.includes('verify') ||
                phoneText.includes('phone');
        } catch (error) {
            return false;
        }
    }

    /**
     * Check if captcha is present
     */
    async isCaptchaPresent(page) {
        try {
            // Check for reCAPTCHA
            const recaptcha = await page.$('iframe[src*="recaptcha"]');
            const hcaptcha = await page.$('iframe[src*="hcaptcha"]');

            return recaptcha !== null || hcaptcha !== null;
        } catch (error) {
            return false;
        }
    }

    /**
     * Attempt to skip phone verification
     */
    async attemptSMSSkip(page) {
        logger.info('Attempting to skip SMS verification...');

        try {
            // Strategy 1: Look for "Skip" button
            const skipButton = await page.$('button:has-text("Skip")');
            if (skipButton) {
                await skipButton.click();
                await page.waitForTimeout(2000);
                logger.success('SMS verification skipped via Skip button');
                return true;
            }

            // Strategy 2: Look for "Try another way" or similar
            const alternativeButtons = await page.$$('button, a');
            for (const button of alternativeButtons) {
                const text = await page.evaluate(el => el.textContent, button);
                if (text.toLowerCase().includes('another way') ||
                    text.toLowerCase().includes('skip') ||
                    text.toLowerCase().includes('not now')) {
                    await button.click();
                    await page.waitForTimeout(2000);
                    logger.success('SMS verification skipped via alternative method');
                    return true;
                }
            }

            // Strategy 3: Check if we can proceed without phone
            const nextButton = await page.$('button:has-text("Next")');
            if (nextButton) {
                await nextButton.click();
                await page.waitForTimeout(2000);

                // Check if we moved forward
                const stillOnPhonePage = await this.isSMSRequired(page);
                if (!stillOnPhonePage) {
                    logger.success('SMS verification bypassed by proceeding');
                    return true;
                }
            }

            logger.warning('SMS bypass strategies failed');
            return false;
        } catch (error) {
            logger.error('Error during SMS bypass attempt', error);
            return false;
        }
    }

    /**
     * Natural behavior simulation before registration
     */
    async simulateNaturalBehavior(page) {
        logger.info('Simulating natural user behavior...');

        try {
            // Random mouse movements
            for (let i = 0; i < 3; i++) {
                const x = Math.floor(Math.random() * 800);
                const y = Math.floor(Math.random() * 600);
                await page.mouse.move(x, y, { steps: 10 });
                await this.randomDelay(300, 700);
            }

            // Random scrolling
            await page.evaluate(() => {
                window.scrollBy({
                    top: Math.random() * 200,
                    behavior: 'smooth'
                });
            });
            await this.randomDelay(500, 1000);

            // Hover over elements
            const elements = await page.$$('input, button');
            if (elements.length > 0) {
                const randomElement = elements[Math.floor(Math.random() * elements.length)];
                await randomElement.hover();
                await this.randomDelay(200, 500);
            }

            logger.success('Natural behavior simulation completed');
        } catch (error) {
            logger.error('Error during behavior simulation', error);
        }
    }

    /**
     * Optimal timing strategy
     * Avoid peak hours when Google is more strict
     */
    isOptimalTime() {
        const hour = new Date().getHours();

        // Avoid peak hours (9 AM - 5 PM in common timezones)
        // Best times: late night / early morning
        const optimalHours = [0, 1, 2, 3, 4, 5, 6, 22, 23];

        return optimalHours.includes(hour);
    }

    /**
     * Wait for optimal timing if needed
     */
    async waitForOptimalTiming(maxWaitMinutes = 60) {
        if (this.isOptimalTime()) {
            logger.success('Current time is optimal for registration');
            return true;
        }

        logger.warning(`Current time is not optimal. Optimal hours: late night/early morning`);
        return false;
    }

    /**
     * Pre-registration checks
     */
    async performPreRegistrationChecks(proxy, fingerprint) {
        const checks = {
            proxyQuality: false,
            fingerprintQuality: false,
            timing: false
        };

        // Check proxy quality
        if (proxy.is_mobile) {
            checks.proxyQuality = true;
            logger.success('Proxy quality: Mobile (High)');
        } else if (proxy.success_count > 5) {
            checks.proxyQuality = true;
            logger.success('Proxy quality: Proven (High)');
        } else {
            logger.warning('Proxy quality: Unproven (Medium)');
        }

        // Check fingerprint quality
        if (fingerprint.device_type === 'mobile') {
            checks.fingerprintQuality = true;
            logger.success('Fingerprint quality: Mobile (High)');
        } else {
            logger.warning('Fingerprint quality: Desktop (Medium)');
        }

        // Check timing
        checks.timing = this.isOptimalTime();

        const score = Object.values(checks).filter(Boolean).length;
        logger.info(`Pre-registration check score: ${score}/3`);

        return {
            checks,
            score,
            recommendation: score >= 2 ? 'proceed' : 'use_sms_service'
        };
    }

    randomDelay(min, max) {
        const delay = Math.floor(Math.random() * (max - min + 1)) + min;
        return new Promise(resolve => setTimeout(resolve, delay));
    }
}

module.exports = BypassStrategies;
