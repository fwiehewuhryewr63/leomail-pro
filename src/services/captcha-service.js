const axios = require('axios');
const logger = require('../utils/logger');

/**
 * Captcha Service Integration
 * Supports Cap.Guru only (v5 Clean)
 */

class CaptchaService {
    constructor(config) {
        this.config = config;
        this.provider = 'capguru';
        this.apiKey = config.get('captchaServices.apiKey') || '';
    }

    /**
     * Solve reCAPTCHA v2
     */
    async solve(page, siteKey) {
        const pageUrl = page.url();
        let token;

        try {
            // Force Cap.Guru as it's the only one supported in v5
            token = await this.solveCapGuruV2(siteKey, pageUrl);
            return token;
        } catch (error) {
            logger.error(`Captcha solving failed`, error);
            throw error;
        }
    }

    /**
     * Cap.Guru solver (2captcha compatible)
     */
    async solveCapGuruV2(siteKey, pageUrl) {
        try {
            const submitResponse = await axios.get('https://api.cap.guru/in.php', {
                params: {
                    key: this.apiKey,
                    method: 'userrecaptcha',
                    googlekey: siteKey,
                    pageurl: pageUrl,
                    json: 1
                }
            });

            if (submitResponse.data.status !== 1) throw new Error(submitResponse.data.request);
            const captchaId = submitResponse.data.request;

            let attempts = 0;
            while (attempts < 60) {
                await new Promise(resolve => setTimeout(resolve, 5000));
                const resultResponse = await axios.get('https://api.cap.guru/res.php', {
                    params: { key: this.apiKey, action: 'get', id: captchaId, json: 1 }
                });

                if (resultResponse.data.status === 1) return resultResponse.data.request;
                if (resultResponse.data.request !== 'CAPCHA_NOT_READY') throw new Error(resultResponse.data.request);
                attempts++;
            }
            throw new Error('Cap.Guru timeout');
        } catch (error) {
            logger.error('Cap.Guru failed', error);
            throw error;
        }
    }
}

module.exports = CaptchaService;
