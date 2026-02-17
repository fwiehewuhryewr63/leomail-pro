const { v4: uuidv4 } = require('uuid');
const logger = require('../utils/logger');

/**
 * Farm Manager
 * Manages logical groups of accounts (Farms)
 */
class FarmManager {
    constructor(database) {
        this.db = database;
    }

    /**
     * Create a new farm
     */
    async createFarm(name, description = '') {
        const id = uuidv4();
        await this.db.run(
            'INSERT INTO farms (id, name, description) VALUES (?, ?, ?)',
            [id, name, description]
        );
        logger.success(`Farm created: ${name}`);
        return id;
    }

    /**
     * Get all farms with account counts
     */
    async getAllFarms() {
        return await this.db.all(`
            SELECT f.*, COUNT(a.id) as account_count 
            FROM farms f
            LEFT JOIN accounts a ON f.id = a.farm_id
            GROUP BY f.id
            ORDER BY f.created_at DESC
        `);
    }

    /**
     * Add accounts to a farm
     */
    async addAccountsToFarm(farmId, accountIds) {
        const placeholders = accountIds.map(() => '?').join(',');
        await this.db.run(
            `UPDATE accounts SET farm_id = ? WHERE id IN (${placeholders})`,
            [farmId, ...accountIds]
        );
        logger.info(`Added ${accountIds.length} accounts to farm ${farmId}`);
    }

    /**
     * Get accounts in a farm
     */
    async getFarmAccounts(farmId) {
        return await this.db.all(
            'SELECT * FROM accounts WHERE farm_id = ? ORDER BY created_at DESC',
            [farmId]
        );
    }

    /**
     * Delete a farm (does not delete accounts, just ungroups them)
     */
    async deleteFarm(farmId) {
        await this.db.run('UPDATE accounts SET farm_id = NULL WHERE farm_id = ?', [farmId]);
        await this.db.run('DELETE FROM farms WHERE id = ?', [farmId]);
        logger.success(`Farm deleted: ${farmId}`);
    }
}

module.exports = FarmManager;
