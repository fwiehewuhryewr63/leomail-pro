const fs = require('fs');
const path = require('path');

/**
 * Configuration Manager
 * Manages application settings and configuration
 */

class Config {
    constructor() {
        this.configDir = path.join(process.env.APPDATA || process.env.HOME, 'GmailAutoReg');
        this.configFile = path.join(this.configDir, 'config.json');
        this.config = this.loadConfig();
    }

    getDefaultConfig() {
        return {
            // General settings
            app: {
                headless: false,
                maxParallelWorkers: 35,
                registrationTimeout: 180000, // 3 minutes
                retryAttempts: 3
            },

            // Registration settings
            registration: {
                preferMobileProxies: true,
                enableSMSBypass: true,
                enableCaptchaBypass: true,
                autoCreateRecoveryEmail: true,
                userDataGeneration: {
                    ageMin: 18,
                    ageMax: 45,
                    locales: ['en_US', 'en_GB', 'en_CA']
                }
            },

            // Warmup settings
            warmup: {
                enabled: true,
                durationDays: 3,
                emailsPerDay: {
                    day1: 2,
                    day2: 4,
                    day3: 6
                },
                activities: {
                    login: true,
                    readEmails: true,
                    sendEmails: true,
                    createFolders: true,
                    markImportant: true
                }
            },

            // AI settings
            ai: {
                provider: 'groq', // 'groq', 'huggingface', or 'openai'
                apiKey: '',
                model: 'mixtral-8x7b-32768',
                temperature: 0.7
            },

            // SMS services
            // SMS services
            smsServices: {
                priority: ['grizzly', 'simsms'], // Default priority
                services: {
                    'grizzly': { apiKey: '', enabled: false },
                    'simsms': { apiKey: '', enabled: false }
                }
            },

            // Captcha services
            captchaServices: {
                enabled: true,
                provider: 'capguru', // Default to Cap.Guru as requested
                apiKey: ''
            },

            // Proxy settings
            proxy: {
                rotationStrategy: 'least-used', // 'least-used', 'round-robin', 'random'
                healthCheckInterval: 3600000, // 1 hour
                warmupBeforeUse: false
            },

            // Export settings
            export: {
                defaultFormat: 'email:password:recovery_email:recovery_password',
                includeMetadata: true
            },

            // UI settings
            ui: {
                theme: 'dark',
                showNotifications: true,
                autoRefreshInterval: 5000
            }
        };
    }

    loadConfig() {
        try {
            if (fs.existsSync(this.configFile)) {
                const data = fs.readFileSync(this.configFile, 'utf-8');
                const loadedConfig = JSON.parse(data);

                // Merge with defaults (in case new settings were added)
                return this.mergeDeep(this.getDefaultConfig(), loadedConfig);
            }
        } catch (error) {
            console.error('Failed to load config, using defaults:', error);
        }

        return this.getDefaultConfig();
    }

    saveConfig() {
        try {
            if (!fs.existsSync(this.configDir)) {
                fs.mkdirSync(this.configDir, { recursive: true });
            }

            fs.writeFileSync(this.configFile, JSON.stringify(this.config, null, 2), 'utf-8');
            console.log('✅ Configuration saved');
            return true;
        } catch (error) {
            console.error('Failed to save config:', error);
            return false;
        }
    }

    get(key) {
        const keys = key.split('.');
        let value = this.config;

        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                return undefined;
            }
        }

        return value;
    }

    set(key, value) {
        const keys = key.split('.');
        let obj = this.config;

        for (let i = 0; i < keys.length - 1; i++) {
            const k = keys[i];
            if (!(k in obj) || typeof obj[k] !== 'object') {
                obj[k] = {};
            }
            obj = obj[k];
        }

        obj[keys[keys.length - 1]] = value;
        this.saveConfig();
    }

    getAll() {
        return this.config;
    }

    reset() {
        this.config = this.getDefaultConfig();
        this.saveConfig();
        console.log('✅ Configuration reset to defaults');
    }

    mergeDeep(target, source) {
        const output = Object.assign({}, target);

        if (this.isObject(target) && this.isObject(source)) {
            Object.keys(source).forEach(key => {
                if (this.isObject(source[key])) {
                    if (!(key in target)) {
                        Object.assign(output, { [key]: source[key] });
                    } else {
                        output[key] = this.mergeDeep(target[key], source[key]);
                    }
                } else {
                    Object.assign(output, { [key]: source[key] });
                }
            });
        }

        return output;
    }

    isObject(item) {
        return item && typeof item === 'object' && !Array.isArray(item);
    }
}

// Singleton instance
const config = new Config();

module.exports = config;
