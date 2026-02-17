const config = require('../utils/config');

class AIKeyManager {
    constructor() {
        this.MODEL_MAX_USAGE = 1000; // Visual limit for battery
    }

    getKeys() {
        const pool = config.get('ai.keyPool') || [];
        // Ensure 10 slots structure for UI
        const slots = [];
        for (let i = 0; i < 10; i++) {
            slots.push(pool[i] || { key: '', usage: 0, active: false });
        }
        return slots;
    }

    addKey(key, index) {
        if (!key) return;
        const pool = config.get('ai.keyPool') || [];

        // If index provided, replace at index (for UI slots)
        if (typeof index === 'number' && index >= 0 && index < 10) {
            pool[index] = { key, usage: 0, active: true, addedAt: Date.now() };
        } else {
            // Push if space
            if (pool.length < 10) pool.push({ key, usage: 0, active: true, addedAt: Date.now() });
        }

        config.set('ai.keyPool', pool);
        return this.getKeys();
    }

    removeKey(index) {
        const pool = config.get('ai.keyPool') || [];
        if (pool[index]) {
            pool.splice(index, 1); // Remove
            config.set('ai.keyPool', pool);
        }
        return this.getKeys();
    }

    getNextKey() {
        const pool = config.get('ai.keyPool') || [];
        const activeKeys = pool.filter(k => k.active && k.key);

        if (activeKeys.length === 0) return null;

        // Round-robin or random? User asked for "takes one".
        // Let's pick random for better distribution or sort by least used.
        // Least used is better for balancing batteries.
        activeKeys.sort((a, b) => a.usage - b.usage);

        const selected = activeKeys[0];

        // Find index in main pool to update usage
        const index = pool.findIndex(k => k.key === selected.key);
        if (index !== -1) {
            pool[index].usage = (pool[index].usage || 0) + 1;
            config.set('ai.keyPool', pool);
        }

        return selected.key;
    }

    getBatteryLevel(usage) {
        const remaining = Math.max(0, this.MODEL_MAX_USAGE - (usage || 0));
        return Math.floor((remaining / this.MODEL_MAX_USAGE) * 100);
    }
}

module.exports = new AIKeyManager();
