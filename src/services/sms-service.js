const axios = require('axios');
const logger = require('../utils/logger');

/**
 * SMS Service Integration
 * Abstract interface for multiple SMS service providers
 */

class SMSService {
    constructor(config) {
        this.config = config;
        this.services = {
            'grizzly': new GrizzlySMSService(),
            'simsms': new SimSMSService()
        };
        this.priceHistory = {}; // Track success to reset price tier
    }

    /**
     * Get phone number from any available service
     */
    async getPhoneNumber(country = 'any', serviceType = 'google') {
        const priority = this.config.get('smsServices.priority') || ['grizzly', 'simsms'];

        for (const serviceName of priority) {
            const serviceConfig = this.config.get(`smsServices.services.${serviceName}`);
            if (!serviceConfig || !serviceConfig.enabled || !serviceConfig.apiKey) continue;

            const service = this.services[serviceName];
            service.setApiKey(serviceConfig.apiKey);

            try {
                // Smart Pricing Logic: Get prices and sort
                const prices = await service.getPrices(serviceType);
                const sortedCountries = Object.entries(prices)
                    .sort(([, a], [, b]) => (a.cost || a) - (b.cost || b));

                // Try each price tier
                for (const [countryCode, priceInfo] of sortedCountries) {
                    logger.info(`Trying ${serviceName} tier: ${countryCode} ($${priceInfo.cost || priceInfo})`);

                    // Try 3 attempts per price bracket
                    for (let attempt = 1; attempt <= 3; attempt++) {
                        try {
                            const phone = await service.getNumber(countryCode, serviceType);
                            if (phone) {
                                logger.success(`Phone obtained from ${serviceName} (${countryCode}) at attempt ${attempt}`);
                                return { service: serviceName, ...phone };
                            }
                        } catch (e) {
                            logger.warning(`Attempt ${attempt} failed for ${countryCode} on ${serviceName}`);
                        }
                    }
                }
            } catch (error) {
                logger.error(`Failed to process prices for ${serviceName}`, error);
            }
        }

        throw new Error('No SMS service available or all price tiers exhausted');
    }

    /**
     * Get SMS code
     */
    async getSMSCode(service, activationId, timeout = 180000) {
        const serviceInstance = this.services[service];

        if (!serviceInstance) {
            throw new Error(`Unknown SMS service: ${service}`);
        }

        return await serviceInstance.getCode(activationId, timeout);
    }

    /**
     * Cancel activation
     */
    async cancelActivation(service, activationId) {
        const serviceInstance = this.services[service];

        if (serviceInstance) {
            await serviceInstance.cancel(activationId);
        }
    }
}

/**
 * SMS-Activate.org Service
 */
class SMSActivateService {
    constructor() {
        this.apiKey = '';
        this.baseUrl = 'https://api.sms-activate.org/stubs/handler_api.php';
    }

    setApiKey(key) {
        this.apiKey = key;
    }

    async getNumber(country, service) {
        try {
            const response = await axios.get(this.baseUrl, {
                params: {
                    api_key: this.apiKey,
                    action: 'getNumber',
                    service: service === 'google' ? 'go' : service,
                    country: this.getCountryCode(country)
                }
            });

            const data = response.data;

            if (data.includes('ACCESS_NUMBER')) {
                const parts = data.split(':');
                return {
                    activationId: parts[1],
                    number: parts[2]
                };
            }

            throw new Error(data);
        } catch (error) {
            logger.error('SMS-Activate getNumber failed', error);
            throw error;
        }
    }

    async getCode(activationId, timeout) {
        const startTime = Date.now();

        while (Date.now() - startTime < timeout) {
            try {
                const response = await axios.get(this.baseUrl, {
                    params: {
                        api_key: this.apiKey,
                        action: 'getStatus',
                        id: activationId
                    number: response.data.number
                    };
                }

            throw new Error(response.data.msg || 'Failed to get number');
            } catch (error) {
                logger.error('OnlineSim getNumber failed', error);
                throw error;
            }
        }

    async getCode(activationId, timeout) {
            const startTime = Date.now();

            while (Date.now() - startTime < timeout) {
                try {
                    const response = await axios.get(`${this.baseUrl}/getState.php`, {
                        params: {
                            apikey: this.apiKey,
                            tzid: activationId
                        }
                    });

                    if (response.data[0] && response.data[0].msg) {
                        const code = response.data[0].msg.match(/\d{6}/);
                        if (code) {
                            logger.success('SMS code received', { code: code[0] });
                            return code[0];
                        }
                    }

                    await new Promise(resolve => setTimeout(resolve, 5000));
                } catch (error) {
                    logger.error('Error checking SMS status', error);
                }
            }

            throw new Error('SMS code timeout');
        }

    async cancel(activationId) {
            await axios.get(`${this.baseUrl}/setOperationRevise.php`, {
                params: {
                    apikey: this.apiKey,
                    tzid: activationId
                }
            });
        }

        getCountryCode(country) {
            const codes = {
                'us': 7,
                'uk': 44,
                'ca': 1
            };
            return codes[country.toLowerCase()] || 7;
        }
    }

/**
 * GrizzlySMS Service (Standard Handler API)
 * https://grizzlysms.com/docs
 */
class GrizzlySMSService extends BaseSMSTrotocol {
    constructor() {
        super();
        this.baseUrl = 'https://api.grizzlysms.com/stubs/handler_api.php';
    }

    async getPrices(service) {
        const response = await axios.get(this.baseUrl, {
            params: { api_key: this.apiKey, action: 'getPrices', service: service === 'google' ? 'go' : service }
        });
        // Grizzly returns nested object { country: { service: { cost: X, count: Y } } }
        const prices = {};
        for (const [countryId, services] of Object.entries(response.data)) {
            const srv = service === 'google' ? 'go' : service;
            if (services[srv]) {
                prices[countryId] = { cost: services[srv].cost, count: services[srv].count };
            }
        }
        return prices;
    }
}

/**
 * SimSMS.org Service
 */
class SimSMSService extends BaseSMSTrotocol {
    constructor() {
        super();
        this.baseUrl = 'https://simsms.org/stubs/handler_api.php';
    }

    async getPrices(service) {
        const response = await axios.get(this.baseUrl, {
            params: { api_key: this.apiKey, action: 'getPrices', service: service === 'google' ? 'go' : service }
        });
        return response.data; // SimSMS often returns direct pricing
    }
}

module.exports = SMSService;
