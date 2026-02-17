const logger = require('./logger');

/**
 * Balance Calculator
 * Predicts costs and checks provider balances
 */
class BalanceCalculator {
    constructor(config, smsService, captchaService) {
        this.config = config;
        this.smsService = smsService;
        this.captchaService = captchaService;
    }

    /**
     * Estimate costs for a registration task
     */
    async estimateTaskCosts(count, provider) {
        const smsCostPerAcc = await this.smsService.getEstimate(provider) || 0;
        const captchaCostPerAcc = await this.captchaService.getEstimate() || 0;

        const totalSMS = smsCostPerAcc * count;
        const totalCaptcha = captchaCostPerAcc * count;

        return {
            totalSMS,
            totalCaptcha,
            totalEstimated: totalSMS + totalCaptcha,
            perAccount: smsCostPerAcc + captchaCostPerAcc
        };
    }

    /**
     * Check if current balances are enough for the task
     */
    async checkFeasibility(count, provider) {
        const estimation = await this.estimateTaskCosts(count, provider);
        const balances = {
            sms: await this.smsService.getBalance(),
            captcha: await this.captchaService.getBalance()
        };

        const issues = [];
        if (balances.sms < estimation.totalSMS) {
            issues.push(`Insufficient SMS balance: Have ${balances.sms}, Need ${estimation.totalSMS.toFixed(2)}`);
        }
        if (balances.captcha < estimation.totalCaptcha) {
            issues.push(`Insufficient Captcha balance: Have ${balances.captcha}, Need ${estimation.totalCaptcha.toFixed(2)}`);
        }

        return {
            isFeasible: issues.length === 0,
            estimation,
            balances,
            issues
        };
    }
}

module.exports = BalanceCalculator;
