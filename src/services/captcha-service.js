const axios = require('axios');
const logger = require('../utils/logger');

/**
 * Captcha Service Integration
 * Supports 2captcha, anti-captcha, and capmonster
 */

class CaptchaService {
    constructor(config) {
        this.config = config;
        this.provider = config.get('captchaServices.provider') || '2captcha';
        this.apiKey = config.get('captchaServices.apiKey') || '';
    }

    /**
     * Solve reCAPTCHA v2
     */
    async solve(page, siteKey) {
        const pageUrl = page.url();
        let token;

        try {
            switch (this.provider) {
                case 'capguru':
                    token = await this.solveCapGuruV2(siteKey, pageUrl);
                    break;
                default:
                    throw new Error(`Unknown captcha provider: ${this.provider}`);
            }
            return token;
        } catch (error) {
            logger.error(`Captcha solving failed for provider ${this.provider}`, error);
            throw error;
        }
    }

    /**
     * 2Captcha reCAPTCHA v2 solver
     */
    async solve2CaptchaV2(siteKey, pageUrl) {
        try {
            // Submit captcha
            const submitResponse = await axios.get('https://2captcha.com/in.php', {
                params: {
                    key: this.apiKey,
                    method: 'userrecaptcha',
                    googlekey: siteKey,
                    pageurl: pageUrl,
                    json: 1
                }
            });

            if (submitResponse.data.status !== 1) {
                throw new Error(submitResponse.data.request);
            }

            const captchaId = submitResponse.data.request;
            logger.info('Captcha submitted', { captchaId });

            // Poll for result
            let attempts = 0;
            while (attempts < 60) {
                await new Promise(resolve => setTimeout(resolve, 5000));

                const resultResponse = await axios.get('https://2captcha.com/res.php', {
                    params: {
                        key: this.apiKey,
                        action: 'get',
                        id: captchaId,
                        json: 1
                    }
                });

                if (resultResponse.data.status === 1) {
                    logger.success('Captcha solved');
                    return resultResponse.data.request;
                }

                if (resultResponse.data.request !== 'CAPCHA_NOT_READY') {
                    throw new Error(resultResponse.data.request);
                }

                attempts++;
            }

            throw new Error('Captcha solving timeout');
        } catch (error) {
            logger.error('2Captcha solving failed', error);
            throw error;
        }
    }

    /**
     * Anti-Captcha reCAPTCHA v2 solver
     */
    async solveAntiCaptchaV2(siteKey, pageUrl) {
        try {
            const createTaskResponse = await axios.post('https://api.anti-captcha.com/createTask', {
                clientKey: this.apiKey,
                task: {
                    type: 'NoCaptchaTaskProxyless',
                    websiteURL: pageUrl,
                    websiteKey: siteKey
                }
            });

            if (createTaskResponse.data.errorId !== 0) {
                throw new Error(createTaskResponse.data.errorDescription);
            }

            const taskId = createTaskResponse.data.taskId;
            logger.info('Captcha task created', { taskId });

            // Poll for result
            let attempts = 0;
            while (attempts < 60) {
                await new Promise(resolve => setTimeout(resolve, 5000));

                const resultResponse = await axios.post('https://api.anti-captcha.com/getTaskResult', {
                    clientKey: this.apiKey,
                    taskId: taskId
                });

                if (resultResponse.data.status === 'ready') {
                    logger.success('Captcha solved');
                    return resultResponse.data.solution.gRecaptchaResponse;
                }

                attempts++;
            }

            throw new Error('Captcha solving timeout');
        } catch (error) {
            logger.error('Anti-Captcha solving failed', error);
            throw error;
        }
    }

    /**
     * CapMonster reCAPTCHA v2 solver
     */
    async solveCapMonsterV2(siteKey, pageUrl) {
        try {
            const createTaskResponse = await axios.post('https://api.capmonster.cloud/createTask', {
                clientKey: this.apiKey,
                task: {
                    type: 'NoCaptchaTaskProxyless',
                    websiteURL: pageUrl,
                    websiteKey: siteKey
                }
            });

            if (createTaskResponse.data.errorId !== 0) {
                throw new Error(createTaskResponse.data.errorDescription);
            }

            const taskId = createTaskResponse.data.taskId;
            logger.info('Captcha task created', { taskId });

            // Poll for result
            let attempts = 0;
            while (attempts < 60) {
                await new Promise(resolve => setTimeout(resolve, 5000));

                const resultResponse = await axios.post('https://api.capmonster.cloud/getTaskResult', {
                    clientKey: this.apiKey,
                    taskId: taskId
                });

                if (resultResponse.data.status === 'ready') {
                    logger.success('Captcha solved');
                    return resultResponse.data.solution.gRecaptchaResponse;
                }

                attempts++;
            }

            throw new Error('Captcha solving timeout');
        } catch (error) {
            logger.error('CapMonster solving failed', error);
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
    async injectSolution(page, solution) {
        await page.evaluate((token) => {
            document.getElementById('g-recaptcha-response').innerHTML = token;
        }, solution);

        logger.success('Captcha solution injected');
    }
}

module.exports = CaptchaService;
