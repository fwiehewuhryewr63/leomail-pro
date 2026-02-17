const puppeteer = require('puppeteer-core');
const puppeteerExtra = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const path = require('path');
const fs = require('fs');

// Add stealth plugin
puppeteerExtra.use(StealthPlugin());

/**
 * Browser Launcher with Anti-Detection
 * Launches Puppeteer with custom fingerprints and stealth measures
 */

class BrowserLauncher {
    constructor() {
        this.chromePath = this.findChromePath();
    }

    findChromePath() {
        const possiblePaths = [
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
            process.env.LOCALAPPDATA + '\\Google\\Chrome\\Application\\chrome.exe',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser'
        ];

        for (const chromePath of possiblePaths) {
            if (fs.existsSync(chromePath)) {
                return chromePath;
            }
        }

        throw new Error('Chrome not found. Please install Google Chrome.');
    }

    /**
     * Launch browser with fingerprint and session persistence
     */
    async launch(fingerprint, accountId, proxy = null) {
        const fingerprintData = JSON.parse(fingerprint.fingerprint_data);
        const isMobile = fingerprint.device_type === 'mobile';
        const profileDir = this.createProfileDir(accountId);

        // Build launch args
        const args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-web-security',
            `--user-data-dir=${profileDir}`
        ];

        // Add proxy if provided
        if (proxy) {
            args.push(`--proxy-server=${proxy.type}://${proxy.host}:${proxy.port}`);
        }

        // Mobile-specific args
        if (isMobile) {
            args.push('--user-agent=' + fingerprint.user_agent);
        }

        const launchOptions = {
            executablePath: this.chromePath,
            headless: false, // Set to true for production
            args,
            ignoreDefaultArgs: ['--enable-automation'],
            defaultViewport: null
        };

        const browser = await puppeteerExtra.launch(launchOptions);
        const page = await browser.newPage();

        // Apply fingerprint
        await this.applyFingerprint(page, fingerprint, fingerprintData);

        // Set proxy authentication if needed
        if (proxy && proxy.username && proxy.password) {
            await page.authenticate({
                username: proxy.username,
                password: proxy.password
            });
        }

        return { browser, page };
    }

    /**
     * Apply fingerprint to page
     */
    async applyFingerprint(page, fingerprint, fingerprintData) {
        // Set viewport
        await page.setViewport({
            width: fingerprint.screen_width,
            height: fingerprint.screen_height,
            deviceScaleFactor: fingerprint.device_pixel_ratio,
            isMobile: fingerprint.device_type === 'mobile',
            hasTouch: fingerprint.device_type === 'mobile'
        });

        // Set user agent
        await page.setUserAgent(fingerprint.user_agent);

        // Override navigator properties
        await page.evaluateOnNewDocument((data) => {
            // Platform
            Object.defineProperty(navigator, 'platform', {
                get: () => data.platform
            });

            // Hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => data.hardwareConcurrency
            });

            // Device memory
            if (data.deviceMemory !== undefined) {
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => data.deviceMemory
                });
            }

            // Max touch points
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => data.maxTouchPoints
            });

            // Languages
            Object.defineProperty(navigator, 'languages', {
                get: () => data.languages
            });

            // Vendor
            Object.defineProperty(navigator, 'vendor', {
                get: () => data.vendor
            });

            // WebDriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });

            // Plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => data.plugins
            });

            // Chrome object (for detection bypass)
            if (!window.chrome) {
                window.chrome = {
                    runtime: {}
                };
            }

            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

        }, fingerprintData);

        // Override WebGL
        await page.evaluateOnNewDocument((webgl) => {
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function (parameter) {
                if (parameter === 37445) {
                    return webgl.vendor;
                }
                if (parameter === 37446) {
                    return webgl.renderer;
                }
                return getParameter.apply(this, [parameter]);
            };
        }, fingerprintData.webgl);

        // Override Canvas fingerprint
        await page.evaluateOnNewDocument((canvasHash) => {
            const toBlob = HTMLCanvasElement.prototype.toBlob;
            const toDataURL = HTMLCanvasElement.prototype.toDataURL;
            const getImageData = CanvasRenderingContext2D.prototype.getImageData;

            // Add slight noise to canvas
            const noisify = function (canvas, context) {
                const shift = {
                    'r': Math.floor(Math.random() * 10) - 5,
                    'g': Math.floor(Math.random() * 10) - 5,
                    'b': Math.floor(Math.random() * 10) - 5,
                    'a': Math.floor(Math.random() * 10) - 5
                };

                const width = canvas.width;
                const height = canvas.height;
                if (width && height) {
                    const imageData = getImageData.apply(context, [0, 0, width, height]);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i + 0] = imageData.data[i + 0] + shift.r;
                        imageData.data[i + 1] = imageData.data[i + 1] + shift.g;
                        imageData.data[i + 2] = imageData.data[i + 2] + shift.b;
                        imageData.data[i + 3] = imageData.data[i + 3] + shift.a;
                    }
                    context.putImageData(imageData, 0, 0);
                }
            };

            Object.defineProperty(HTMLCanvasElement.prototype, 'toBlob', {
                value: function () {
                    noisify(this, this.getContext('2d'));
                    return toBlob.apply(this, arguments);
                }
            });

            Object.defineProperty(HTMLCanvasElement.prototype, 'toDataURL', {
                value: function () {
                    noisify(this, this.getContext('2d'));
                    return toDataURL.apply(this, arguments);
                }
            });
        }, fingerprintData.canvas);

        // Set timezone
        await page.emulateTimezone(fingerprintData.timezone);

        // Set geolocation (based on timezone)
        const geolocations = {
            'America/New_York': { latitude: 40.7128, longitude: -74.0060 },
            'America/Chicago': { latitude: 41.8781, longitude: -87.6298 },
            'America/Los_Angeles': { latitude: 34.0522, longitude: -118.2437 },
            'Europe/London': { latitude: 51.5074, longitude: -0.1278 },
            'Europe/Paris': { latitude: 48.8566, longitude: 2.3522 },
            'Asia/Tokyo': { latitude: 35.6762, longitude: 139.6503 }
        };

        const geo = geolocations[fingerprintData.timezone] || geolocations['America/New_York'];
        await page.setGeolocation({
            latitude: geo.latitude,
            longitude: geo.longitude,
            accuracy: 100
        });

        console.log(`✅ Browser launched with ${fingerprint.device_type} fingerprint (${fingerprint.os})`);
    }

    /**
     * Create isolated profile directory
     */
    createProfileDir(accountId) {
        const profileDir = path.join(
            process.env.APPDATA || process.env.HOME,
            'GmailAutoReg',
            'profiles',
            accountId
        );

        if (!fs.existsSync(profileDir)) {
            fs.mkdirSync(profileDir, { recursive: true });
        }

        return profileDir;
    }
}

module.exports = BrowserLauncher;
