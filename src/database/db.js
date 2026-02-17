const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

class Database {
    constructor(dbPath) {
        this.dbPath = dbPath || path.join(process.env.APPDATA || process.env.HOME, 'GmailAutoReg', 'database.db');
        this.ensureDirectory();
        this.db = null;
    }

    ensureDirectory() {
        const dir = path.dirname(this.dbPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }

    async connect() {
        return new Promise((resolve, reject) => {
            this.db = new sqlite3.Database(this.dbPath, (err) => {
                if (err) reject(err);
                else {
                    console.log('✅ Database connected:', this.dbPath);
                    resolve();
                }
            });
        });
    }

    async initialize() {
        await this.connect();
        await this.createTables();
    }

    async createTables() {
        const tables = [
            // Farms table (Groups of accounts)
            `CREATE TABLE IF NOT EXISTS farms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,

            // Accounts table (updated with farm_id)
            `CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                provider TEXT NOT NULL,
                farm_id TEXT,
                first_name TEXT,
                last_name TEXT,
                recovery_email TEXT,
                recovery_password TEXT,
                phone_number TEXT,
                fingerprint_id TEXT,
                proxy_id TEXT,
                status TEXT DEFAULT 'pending', 
                warmup_status TEXT DEFAULT 'pending',
                warmup_day INTEGER DEFAULT 0,
                warmup_level INTEGER DEFAULT 0,
                cooldown_until DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME,
                notes TEXT,
                FOREIGN KEY (farm_id) REFERENCES farms(id),
                FOREIGN KEY (fingerprint_id) REFERENCES fingerprints(id),
                FOREIGN KEY (proxy_id) REFERENCES proxies(id)
            )`,

            // Proxies table (updated with lease info)
            `CREATE TABLE IF NOT EXISTS proxies (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT,
                password TEXT,
                country TEXT,
                is_mobile BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                lease_end_date DATETIME,
                auto_refresh BOOLEAN DEFAULT 0,
                last_used DATETIME,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,

            // Fingerprints table
            `CREATE TABLE IF NOT EXISTS fingerprints (
        id TEXT PRIMARY KEY,
        device_type TEXT NOT NULL,
        os TEXT NOT NULL,
        browser TEXT NOT NULL,
        user_agent TEXT NOT NULL,
        screen_width INTEGER,
        screen_height INTEGER,
        device_pixel_ratio REAL,
        fingerprint_data TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )`,

            // Warmup progress table
            `CREATE TABLE IF NOT EXISTS warmup_progress (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        day INTEGER NOT NULL,
        activity_type TEXT NOT NULL,
        activity_data TEXT,
        completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(id)
      )`,

            // Warmup emails table
            `CREATE TABLE IF NOT EXISTS warmup_emails (
        id TEXT PRIMARY KEY,
        from_account_id TEXT NOT NULL,
        to_account_id TEXT,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_reply BOOLEAN DEFAULT 0,
        parent_email_id TEXT,
        FOREIGN KEY (from_account_id) REFERENCES accounts(id),
        FOREIGN KEY (to_account_id) REFERENCES accounts(id),
        FOREIGN KEY (parent_email_id) REFERENCES warmup_emails(id)
      )`,

            // SMS services table
            `CREATE TABLE IF NOT EXISTS sms_services (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        api_key TEXT NOT NULL,
        is_active BOOLEAN DEFAULT 1,
        priority INTEGER DEFAULT 0,
        balance REAL DEFAULT 0,
        last_checked DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )`,

            // Settings table
            `CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )`,

            // Activity logs table
            `CREATE TABLE IF NOT EXISTS activity_logs (
        id TEXT PRIMARY KEY,
        account_id TEXT,
        action TEXT NOT NULL,
        details TEXT,
        status TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(id)
      )`,

            // Registration queue table
            `CREATE TABLE IF NOT EXISTS registration_queue (
        id TEXT PRIMARY KEY,
        status TEXT DEFAULT 'pending',
        fingerprint_id TEXT,
        proxy_id TEXT,
        started_at DATETIME,
        completed_at DATETIME,
        error TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (fingerprint_id) REFERENCES fingerprints(id),
        FOREIGN KEY (proxy_id) REFERENCES proxies(id)
      )`
        ];

        for (const sql of tables) {
            await this.run(sql);
        }

        console.log('✅ Database tables created');
    }

    run(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.run(sql, params, function (err) {
                if (err) reject(err);
                else resolve({ lastID: this.lastID, changes: this.changes });
            });
        });
    }

    get(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.get(sql, params, (err, row) => {
                if (err) reject(err);
                else resolve(row);
            });
        });
    }

    all(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.all(sql, params, (err, rows) => {
                if (err) reject(err);
                else resolve(rows);
            });
        });
    }

    async close() {
        return new Promise((resolve, reject) => {
            if (this.db) {
                this.db.close((err) => {
                    if (err) reject(err);
                    else {
                        console.log('✅ Database connection closed');
                        resolve();
                    }
                });
            } else {
                resolve();
            }
        });
    }
}

module.exports = Database;
