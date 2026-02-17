const { v4: uuidv4 } = require('uuid');

/**
 * Desktop Device Fingerprint Generator (Fallback)
 * Generates realistic Windows/Mac desktop fingerprints
 */

class DesktopFingerprintGenerator {
    constructor() {
        this.windowsVersions = [
            'Windows NT 10.0; Win64; x64',
            'Windows NT 11.0; Win64; x64'
        ];

        this.macVersions = [
            'Macintosh; Intel Mac OS X 10_15_7',
            'Macintosh; Intel Mac OS X 13_0_0',
            'Macintosh; Intel Mac OS X 14_0_0'
        ];

        this.chromeVersions = ['119.0.0.0', '120.0.0.0', '121.0.0.0', '122.0.0.0'];

        this.screenResolutions = [
            { width: 1920, height: 1080, dpr: 1.0 },
            { width: 2560, height: 1440, dpr: 1.0 },
            { width: 1920, height: 1080, dpr: 1.25 },
            { width: 3840, height: 2160, dpr: 1.5 }
        ];
    }

    /**
     * Generate Windows fingerprint
     */
    generateWindows() {
        const os = this.windowsVersions[Math.floor(Math.random() * this.windowsVersions.length)];
        const chromeVersion = this.chromeVersions[Math.floor(Math.random() * this.chromeVersions.length)];
        const screen = this.screenResolutions[Math.floor(Math.random() * this.screenResolutions.length)];

        const userAgent = `Mozilla/5.0 (${os}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chromeVersion} Safari/537.36`;

        const fingerprint = {
            id: uuidv4(),
            device_type: 'desktop',
            os: os.includes('11.0') ? 'Windows 11' : 'Windows 10',
            browser: `Chrome ${chromeVersion.split('.')[0]}`,
            user_agent: userAgent,
            screen_width: screen.width,
            screen_height: screen.height,
            device_pixel_ratio: screen.dpr,
            fingerprint_data: JSON.stringify({
                platform: 'Win32',
                vendor: 'Google Inc.',
                renderer: 'ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)',
                hardwareConcurrency: 8,
                deviceMemory: 8,
                maxTouchPoints: 0,
                languages: ['en-US', 'en'],
                timezone: this.getRandomTimezone(),
                webgl: {
                    vendor: 'Google Inc. (NVIDIA)',
                    renderer: 'ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)'
                },
                canvas: this.generateCanvasFingerprint(),
                audio: this.generateAudioFingerprint(),
                fonts: this.getWindowsFonts(),
                plugins: this.getChromePlugins(),
                mimeTypes: []
            })
        };

        return fingerprint;
    }

    /**
     * Generate Mac fingerprint
     */
    generateMac() {
        const os = this.macVersions[Math.floor(Math.random() * this.macVersions.length)];
        const chromeVersion = this.chromeVersions[Math.floor(Math.random() * this.chromeVersions.length)];
        const screen = this.screenResolutions[Math.floor(Math.random() * this.screenResolutions.length)];

        const userAgent = `Mozilla/5.0 (${os}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chromeVersion} Safari/537.36`;

        const fingerprint = {
            id: uuidv4(),
            device_type: 'desktop',
            os: `macOS ${os.split('X ')[1].replace(/_/g, '.')}`,
            browser: `Chrome ${chromeVersion.split('.')[0]}`,
            user_agent: userAgent,
            screen_width: screen.width,
            screen_height: screen.height,
            device_pixel_ratio: screen.dpr,
            fingerprint_data: JSON.stringify({
                platform: 'MacIntel',
                vendor: 'Google Inc.',
                renderer: 'ANGLE (Apple, Apple M1, OpenGL 4.1)',
                hardwareConcurrency: 8,
                deviceMemory: 8,
                maxTouchPoints: 0,
                languages: ['en-US', 'en'],
                timezone: this.getRandomTimezone(),
                webgl: {
                    vendor: 'Google Inc. (Apple)',
                    renderer: 'ANGLE (Apple, Apple M1, OpenGL 4.1)'
                },
                canvas: this.generateCanvasFingerprint(),
                audio: this.generateAudioFingerprint(),
                fonts: this.getMacFonts(),
                plugins: this.getChromePlugins(),
                mimeTypes: []
            })
        };

        return fingerprint;
    }

    /**
     * Generate random desktop fingerprint (60% Windows, 40% Mac)
     */
    generate() {
        const isWindows = Math.random() < 0.6;
        return isWindows ? this.generateWindows() : this.generateMac();
    }

    generateCanvasFingerprint() {
        return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    }

    generateAudioFingerprint() {
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
            'Europe/Berlin'
        ];
        return timezones[Math.floor(Math.random() * timezones.length)];
    }

    getWindowsFonts() {
        return [
            'Arial',
            'Calibri',
            'Cambria',
            'Consolas',
            'Courier New',
            'Georgia',
            'Segoe UI',
            'Tahoma',
            'Times New Roman',
            'Trebuchet MS',
            'Verdana'
        ];
    }

    getMacFonts() {
        return [
            'Arial',
            'Helvetica',
            'Helvetica Neue',
            'SF Pro Text',
            'SF Pro Display',
            'Times New Roman',
            'Courier New',
            'Monaco',
            'Menlo'
        ];
    }

    getChromePlugins() {
        return [
            'PDF Viewer',
            'Chrome PDF Viewer',
            'Chromium PDF Viewer',
            'Microsoft Edge PDF Viewer',
            'WebKit built-in PDF'
        ];
    }
}

module.exports = DesktopFingerprintGenerator;
