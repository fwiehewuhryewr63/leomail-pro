const { faker } = require('@faker-js/faker');
const { v4: uuidv4 } = require('uuid');

/**
 * Mobile Device Fingerprint Generator
 * Generates realistic Android and iOS device fingerprints
 */

class MobileFingerprintGenerator {
    constructor() {
        this.androidDevices = [
            // Samsung devices
            { brand: 'Samsung', model: 'Galaxy S23', width: 1080, height: 2340, dpr: 3.0, os: 'Android 13' },
            { brand: 'Samsung', model: 'Galaxy S23 Ultra', width: 1440, height: 3088, dpr: 3.5, os: 'Android 13' },
            { brand: 'Samsung', model: 'Galaxy A54', width: 1080, height: 2340, dpr: 2.5, os: 'Android 13' },
            { brand: 'Samsung', model: 'Galaxy S22', width: 1080, height: 2340, dpr: 3.0, os: 'Android 12' },

            // Google Pixel devices
            { brand: 'Google', model: 'Pixel 8 Pro', width: 1344, height: 2992, dpr: 3.0, os: 'Android 14' },
            { brand: 'Google', model: 'Pixel 8', width: 1080, height: 2400, dpr: 2.625, os: 'Android 14' },
            { brand: 'Google', model: 'Pixel 7a', width: 1080, height: 2400, dpr: 2.5, os: 'Android 13' },

            // Xiaomi devices
            { brand: 'Xiaomi', model: 'Redmi Note 12 Pro', width: 1080, height: 2400, dpr: 2.5, os: 'Android 12' },
            { brand: 'Xiaomi', model: 'Mi 13', width: 1080, height: 2400, dpr: 3.0, os: 'Android 13' },

            // OnePlus devices
            { brand: 'OnePlus', model: 'OnePlus 11', width: 1440, height: 3216, dpr: 3.0, os: 'Android 13' },
            { brand: 'OnePlus', model: 'OnePlus Nord 3', width: 1080, height: 2412, dpr: 2.5, os: 'Android 13' }
        ];

        this.iosDevices = [
            { brand: 'Apple', model: 'iPhone 15 Pro Max', width: 1290, height: 2796, dpr: 3.0, os: 'iOS 17.2' },
            { brand: 'Apple', model: 'iPhone 15 Pro', width: 1179, height: 2556, dpr: 3.0, os: 'iOS 17.2' },
            { brand: 'Apple', model: 'iPhone 15', width: 1179, height: 2556, dpr: 3.0, os: 'iOS 17.2' },
            { brand: 'Apple', model: 'iPhone 14 Pro', width: 1179, height: 2556, dpr: 3.0, os: 'iOS 16.6' },
            { brand: 'Apple', model: 'iPhone 14', width: 1170, height: 2532, dpr: 3.0, os: 'iOS 16.6' },
            { brand: 'Apple', model: 'iPhone 13', width: 1170, height: 2532, dpr: 3.0, os: 'iOS 16.3' },
            { brand: 'Apple', model: 'iPhone SE (3rd gen)', width: 750, height: 1334, dpr: 2.0, os: 'iOS 16.3' }
        ];

        this.chromeVersions = ['119.0.0.0', '120.0.0.0', '121.0.0.0', '122.0.0.0'];
        this.safariVersions = ['17.2', '17.1', '16.6', '16.5'];
    }

    /**
     * Generate Android fingerprint
     */
    generateAndroid() {
        const device = this.androidDevices[Math.floor(Math.random() * this.androidDevices.length)];
        const chromeVersion = this.chromeVersions[Math.floor(Math.random() * this.chromeVersions.length)];

        const userAgent = `Mozilla/5.0 (Linux; Android ${device.os.split(' ')[1]}; ${device.model}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chromeVersion} Mobile Safari/537.36`;

        const fingerprint = {
            id: uuidv4(),
            device_type: 'mobile',
            os: device.os,
            browser: `Chrome ${chromeVersion.split('.')[0]}`,
            user_agent: userAgent,
            screen_width: device.width,
            screen_height: device.height,
            device_pixel_ratio: device.dpr,
            fingerprint_data: JSON.stringify({
                platform: 'Linux armv8l',
                vendor: 'Google Inc.',
                renderer: 'Adreno (TM) 730',
                hardwareConcurrency: 8,
                deviceMemory: 8,
                maxTouchPoints: 5,
                languages: ['en-US', 'en'],
                timezone: this.getRandomTimezone(),
                webgl: {
                    vendor: 'Qualcomm',
                    renderer: 'Adreno (TM) 730'
                },
                canvas: this.generateCanvasFingerprint(),
                audio: this.generateAudioFingerprint(),
                fonts: this.getAndroidFonts(),
                plugins: [],
                mimeTypes: [],
                device: {
                    brand: device.brand,
                    model: device.model
                }
            })
        };

        return fingerprint;
    }

    /**
     * Generate iOS fingerprint
     */
    generateIOS() {
        const device = this.iosDevices[Math.floor(Math.random() * this.iosDevices.length)];
        const safariVersion = this.safariVersions[Math.floor(Math.random() * this.safariVersions.length)];

        const userAgent = `Mozilla/5.0 (iPhone; CPU iPhone OS ${device.os.split(' ')[1].replace('.', '_')} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/${safariVersion} Mobile/15E148 Safari/604.1`;

        const fingerprint = {
            id: uuidv4(),
            device_type: 'mobile',
            os: device.os,
            browser: `Safari ${safariVersion}`,
            user_agent: userAgent,
            screen_width: device.width,
            screen_height: device.height,
            device_pixel_ratio: device.dpr,
            fingerprint_data: JSON.stringify({
                platform: 'iPhone',
                vendor: 'Apple Computer, Inc.',
                renderer: 'Apple GPU',
                hardwareConcurrency: 6,
                deviceMemory: undefined, // iOS doesn't expose this
                maxTouchPoints: 5,
                languages: ['en-US', 'en'],
                timezone: this.getRandomTimezone(),
                webgl: {
                    vendor: 'Apple Inc.',
                    renderer: 'Apple GPU'
                },
                canvas: this.generateCanvasFingerprint(),
                audio: this.generateAudioFingerprint(),
                fonts: this.getIOSFonts(),
                plugins: [],
                mimeTypes: [],
                device: {
                    brand: device.brand,
                    model: device.model
                }
            })
        };

        return fingerprint;
    }

    /**
     * Generate random mobile fingerprint (70% Android, 30% iOS)
     */
    generate() {
        const isAndroid = Math.random() < 0.7;
        return isAndroid ? this.generateAndroid() : this.generateIOS();
    }

    generateCanvasFingerprint() {
        // Generate unique canvas fingerprint hash
        return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    }

    generateAudioFingerprint() {
        // Generate unique audio context fingerprint
        return Math.random().toString(36).substring(2, 15);
    }

    getRandomTimezone() {
        const timezones = [
            'America/New_York',
            'America/Chicago',
            'America/Los_Angeles',
            'America/Denver',
            'Europe/London',
            'Europe/Paris',
            'Europe/Berlin',
            'Asia/Tokyo',
            'Asia/Shanghai',
            'Australia/Sydney'
        ];
        return timezones[Math.floor(Math.random() * timezones.length)];
    }

    getAndroidFonts() {
        return [
            'Roboto',
            'Noto Sans',
            'Droid Sans',
            'sans-serif',
            'serif',
            'monospace'
        ];
    }

    getIOSFonts() {
        return [
            'SF Pro Text',
            'SF Pro Display',
            'Helvetica Neue',
            'Arial',
            'Times New Roman',
            'Courier New'
        ];
    }
}

module.exports = MobileFingerprintGenerator;
