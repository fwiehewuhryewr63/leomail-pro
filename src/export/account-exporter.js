const { v4: uuidv4 } = require('uuid');
const logger = require('../utils/logger');

/**
 * Account Exporter
 * Export accounts in multiple formats
 */

class AccountExporter {
    constructor(database) {
        this.db = database;
    }

    /**
     * Export accounts
     */
    async exportAccounts(format = 'email:password', filter = {}) {
        try {
            let query = 'SELECT * FROM accounts WHERE 1=1';
            const params = [];

            // Apply filters
            if (filter.status) {
                query += ' AND status = ?';
                params.push(filter.status);
            }

            if (filter.warmupStatus) {
                query += ' AND warmup_status = ?';
                params.push(filter.warmupStatus);
            }

            if (filter.createdAfter) {
                query += ' AND created_at >= ?';
                params.push(filter.createdAfter);
            }

            const accounts = await this.db.all(query, params);

            logger.info(`Exporting ${accounts.length} accounts in format: ${format}`);

            let output = '';

            switch (format) {
                case 'email:password':
                    output = accounts.map(acc => `${acc.email}:${acc.password}`).join('\n');
                    break;

                case 'email:password:recovery':
                    output = accounts.map(acc =>
                        `${acc.email}:${acc.password}:${acc.recovery_email || ''}:${acc.recovery_password || ''}`
                    ).join('\n');
                    break;

                case 'email:password:proxy':
                    output = await this.exportWithProxy(accounts);
                    break;

                case 'json':
                    output = JSON.stringify(accounts, null, 2);
                    break;

                case 'csv':
                    output = this.exportAsCSV(accounts);
                    break;

                default:
                    throw new Error(`Unknown format: ${format}`);
            }

            logger.success(`Exported ${accounts.length} accounts`);
            return output;
        } catch (error) {
            logger.error('Export failed', error);
            throw error;
        }
    }

    /**
     * Export with proxy information
     */
    async exportWithProxy(accounts) {
        const lines = [];

        for (const account of accounts) {
            if (account.proxy_id) {
                const proxy = await this.db.get('SELECT * FROM proxies WHERE id = ?', [account.proxy_id]);
                if (proxy) {
                    const proxyStr = `${proxy.host}:${proxy.port}:${proxy.username || ''}:${proxy.password || ''}`;
                    lines.push(`${account.email}:${account.password}:${proxyStr}`);
                } else {
                    lines.push(`${account.email}:${account.password}:::`);
                }
            } else {
                lines.push(`${account.email}:${account.password}:::`);
            }
        }

        return lines.join('\n');
    }

    /**
     * Export as CSV
     */
    exportAsCSV(accounts) {
        const headers = ['Email', 'Password', 'Recovery Email', 'Recovery Password', 'Phone', 'Status', 'Warmup Status', 'Created At'];
        const rows = accounts.map(acc => [
            acc.email,
            acc.password,
            acc.recovery_email || '',
            acc.recovery_password || '',
            acc.phone_number || '',
            acc.status,
            acc.warmup_status,
            acc.created_at
        ]);

        const csvLines = [
            headers.join(','),
            ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
        ];

        return csvLines.join('\n');
    }

    /**
     * Save export to file
     */
    async saveToFile(content, filename) {
        const fs = require('fs');
        const path = require('path');

        const exportDir = path.join(process.env.APPDATA || process.env.HOME, 'GmailAutoReg', 'exports');

        if (!fs.existsSync(exportDir)) {
            fs.mkdirSync(exportDir, { recursive: true });
        }

        const filePath = path.join(exportDir, filename);
        fs.writeFileSync(filePath, content, 'utf-8');

        logger.success(`Exported to: ${filePath}`);
        return filePath;
    }

    /**
     * Get export statistics
     */
    async getExportStats() {
        const stats = await this.db.get(`
      SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN warmup_status = 'completed' THEN 1 ELSE 0 END) as warmed,
        SUM(CASE WHEN warmup_status = 'pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN warmup_status = 'active' THEN 1 ELSE 0 END) as warming
      FROM accounts
    `);

        return stats;
    }
}

module.exports = AccountExporter;
