const fs = require('fs');
const path = require('path');

/**
 * Logger utility
 * Handles application logging with different levels
 */

class Logger {
    constructor() {
        this.logDir = path.join(process.env.APPDATA || process.env.HOME, 'GmailAutoReg', 'logs');
        this.ensureLogDirectory();
        this.logFile = path.join(this.logDir, `app-${this.getDateString()}.log`);
    }

    ensureLogDirectory() {
        if (!fs.existsSync(this.logDir)) {
            fs.mkdirSync(this.logDir, { recursive: true });
        }
    }

    getDateString() {
        const now = new Date();
        return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    }

    getTimestamp() {
        return new Date().toISOString();
    }

    formatMessage(level, message, data = null) {
        const timestamp = this.getTimestamp();
        let logMessage = `[${timestamp}] [${level}] ${message}`;

        if (data) {
            logMessage += ` | ${JSON.stringify(data)}`;
        }

        return logMessage;
    }

    writeToFile(message) {
        try {
            fs.appendFileSync(this.logFile, message + '\n', 'utf-8');
        } catch (error) {
            console.error('Failed to write to log file:', error);
        }
    }

    info(message, data = null) {
        const logMessage = this.formatMessage('INFO', message, data);
        console.log(`ℹ️  ${message}`, data || '');
        this.writeToFile(logMessage);
    }

    success(message, data = null) {
        const logMessage = this.formatMessage('SUCCESS', message, data);
        console.log(`✅ ${message}`, data || '');
        this.writeToFile(logMessage);
    }

    warning(message, data = null) {
        const logMessage = this.formatMessage('WARNING', message, data);
        console.warn(`⚠️  ${message}`, data || '');
        this.writeToFile(logMessage);
    }

    error(message, error = null) {
        const errorData = error ? {
            message: error.message,
            stack: error.stack
        } : null;

        const logMessage = this.formatMessage('ERROR', message, errorData);
        console.error(`❌ ${message}`, error || '');
        this.writeToFile(logMessage);
    }

    debug(message, data = null) {
        const logMessage = this.formatMessage('DEBUG', message, data);
        console.log(`🔍 ${message}`, data || '');
        this.writeToFile(logMessage);
    }

    // Log registration attempt
    logRegistration(accountEmail, status, details = null) {
        this.info(`Registration: ${accountEmail} - ${status}`, details);
    }

    // Log warmup activity
    logWarmup(accountEmail, activity, details = null) {
        this.info(`Warmup: ${accountEmail} - ${activity}`, details);
    }

    // Clean old logs (keep last 30 days)
    cleanOldLogs() {
        try {
            const files = fs.readdirSync(this.logDir);
            const now = Date.now();
            const thirtyDaysAgo = now - (30 * 24 * 60 * 60 * 1000);

            files.forEach(file => {
                const filePath = path.join(this.logDir, file);
                const stats = fs.statSync(filePath);

                if (stats.mtimeMs < thirtyDaysAgo) {
                    fs.unlinkSync(filePath);
                    console.log(`🗑️  Deleted old log: ${file}`);
                }
            });
        } catch (error) {
            this.error('Failed to clean old logs', error);
        }
    }
}

// Singleton instance
const logger = new Logger();

module.exports = logger;
