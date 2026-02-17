const { v4: uuidv4 } = require('uuid');
const axios = require('axios');

/**
 * Proxy Manager
 * Manages proxy pool, rotation, health checking, and warmup
 */

class ProxyManager {
    constructor(database) {
        this.db = database;
    }

    /**
     * Add proxy to pool
     */
    async addProxy(proxyConfig) {
        const proxy = {
            id: uuidv4(),
            type: proxyConfig.type || 'http',
            host: proxyConfig.host,
            port: proxyConfig.port,
            username: proxyConfig.username || null,
            password: proxyConfig.password || null,
            country: proxyConfig.country || null,
            is_mobile: proxyConfig.is_mobile || false,
            is_active: true,
            last_used: null,
            success_count: 0,
            fail_count: 0
        };

        await this.db.run(
            `INSERT INTO proxies (id, type, host, port, username, password, country, is_mobile, is_active, lease_end_date, auto_refresh, success_count, fail_count)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [proxy.id, proxy.type, proxy.host, proxy.port, proxy.username, proxy.password, proxy.country, proxy.is_mobile, proxy.is_active, proxyConfig.lease_end_date || null, proxyConfig.auto_refresh ? 1 : 0, proxy.success_count, proxy.fail_count]
        );

        console.log(`✅ Proxy added: ${proxy.host}:${proxy.port} (${proxy.is_mobile ? 'Mobile' : 'Residential'})`);
        return proxy;
    }

    /**
     * Get next available proxy (prioritize mobile, then least used)
     */
    async getNextProxy(preferMobile = true) {
        let query = `
      SELECT * FROM proxies 
      WHERE is_active = 1
    `;

        if (preferMobile) {
            query += ` ORDER BY is_mobile DESC, last_used ASC NULLS FIRST, (success_count - fail_count) DESC LIMIT 1`;
        } else {
            query += ` ORDER BY last_used ASC NULLS FIRST, (success_count - fail_count) DESC LIMIT 1`;
        }

        const proxy = await this.db.get(query);

        if (!proxy) {
            throw new Error('No available proxies in pool');
        }

        // Update last used
        await this.db.run(
            `UPDATE proxies SET last_used = CURRENT_TIMESTAMP WHERE id = ?`,
            [proxy.id]
        );

        return proxy;
    }

    /**
     * Test proxy health
     */
    async testProxy(proxy) {
        try {
            const proxyUrl = this.buildProxyUrl(proxy);

            const response = await axios.get('https://api.ipify.org?format=json', {
                proxy: false,
                httpsAgent: require('https-proxy-agent')(proxyUrl),
                timeout: 10000
            });

            console.log(`✅ Proxy ${proxy.host}:${proxy.port} is working. IP: ${response.data.ip}`);

            await this.recordSuccess(proxy.id);
            return { success: true, ip: response.data.ip };
        } catch (error) {
            console.log(`❌ Proxy ${proxy.host}:${proxy.port} failed: ${error.message}`);

            await this.recordFailure(proxy.id);
            return { success: false, error: error.message };
        }
    }

    /**
     * Warmup proxy (light browsing before registration)
     */
    async warmupProxy(proxy, browserLauncher) {
        console.log(`🔥 Warming up proxy ${proxy.host}:${proxy.port}...`);

        try {
            const MobileFingerprintGenerator = require('./mobile-fingerprints');
            const fingerprintGen = new MobileFingerprintGenerator();
            const fingerprint = fingerprintGen.generate();

            const { browser, page } = await browserLauncher.launch(fingerprint, 'proxy-warmup', proxy);

            // Visit a few safe sites
            const sites = [
                'https://www.google.com',
                'https://www.wikipedia.org',
                'https://www.youtube.com'
            ];

            for (const site of sites) {
                await page.goto(site, { waitUntil: 'networkidle2', timeout: 30000 });
                await this.randomDelay(2000, 5000);
            }

            await browser.close();
            console.log(`✅ Proxy warmed up successfully`);

            return true;
        } catch (error) {
            console.log(`❌ Proxy warmup failed: ${error.message}`);
            return false;
        }
    }

    /**
     * Record successful proxy usage
     */
    async recordSuccess(proxyId) {
        await this.db.run(
            `UPDATE proxies SET success_count = success_count + 1 WHERE id = ?`,
            [proxyId]
        );
    }

    /**
     * Record failed proxy usage
     */
    async recordFailure(proxyId) {
        await this.db.run(
            `UPDATE proxies SET fail_count = fail_count + 1 WHERE id = ?`,
            [proxyId]
        );

        // Deactivate if too many failures
        const proxy = await this.db.get(`SELECT * FROM proxies WHERE id = ?`, [proxyId]);
        if (proxy && proxy.fail_count > 5 && proxy.fail_count > proxy.success_count * 2) {
            await this.db.run(`UPDATE proxies SET is_active = 0 WHERE id = ?`, [proxyId]);
            console.log(`⚠️ Proxy ${proxy.host}:${proxy.port} deactivated due to high failure rate`);
        }
    }

    /**
     * Build proxy URL
     */
    buildProxyUrl(proxy) {
        const auth = proxy.username && proxy.password
            ? `${proxy.username}:${proxy.password}@`
            : '';
        return `${proxy.type}://${auth}${proxy.host}:${proxy.port}`;
    }

    /**
     * Get all proxies
     */
    async getAllProxies() {
        return await this.db.all(`SELECT * FROM proxies ORDER BY is_mobile DESC, created_at DESC`);
    }

    /**
     * Delete proxy
     */
    async deleteProxy(proxyId) {
        await this.db.run(`DELETE FROM proxies WHERE id = ?`, [proxyId]);
        console.log(`✅ Proxy deleted`);
    }

    /**
     * Random delay helper
     */
    randomDelay(min, max) {
        const delay = Math.floor(Math.random() * (max - min + 1)) + min;
        return new Promise(resolve => setTimeout(resolve, delay));
    }

    /**
     * Import proxies from text file (format: host:port:username:password or host:port)
     */
    async importFromFile(filePath, isMobile = false) {
        const fs = require('fs');
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n').filter(line => line.trim());

        let imported = 0;
        for (const line of lines) {
            const parts = line.trim().split(':');
            if (parts.length >= 2) {
                const proxyConfig = {
                    host: parts[0],
                    port: parseInt(parts[1]),
                    username: parts[2] || null,
                    password: parts[3] || null,
                    is_mobile: isMobile,
                    type: 'http'
                };

                try {
                    await this.addProxy(proxyConfig);
                    imported++;
                } catch (error) {
                    console.log(`Failed to import ${line}: ${error.message}`);
                }
            }
        }

        console.log(`✅ Imported ${imported} proxies from file`);
        return imported;
    }
}

module.exports = ProxyManager;
