const { v4: uuidv4 } = require('uuid');
const logger = require('../utils/logger');

/**
 * Task Queue Manager
 * Manages parallel registration workers for 100 accounts/hour
 */

class TaskQueue {
    constructor(database, registrars, config) {
        this.db = database;
        this.registrars = registrars; // Map of provider -> registrar instance
        this.config = config;
        this.maxWorkers = config.get('app.maxParallelWorkers') || 35;
        this.activeWorkers = 0;
        this.queue = [];
        this.isProcessing = false;
        this.stats = {
            total: 0,
            completed: 0,
            failed: 0,
            inProgress: 0
        };
    }

    /**
     * Add registration task to queue
     */
    async addTask(count = 1, provider = 'gmail') {
        for (let i = 0; i < count; i++) {
            const taskId = require('uuid').v4();

            await this.db.run(
                'INSERT INTO registration_queue (id, status, provider) VALUES (?, ?, ?)',
                [taskId, 'pending', provider]
            );

            this.queue.push({ id: taskId, provider });
            this.stats.total++;
        }

        logger.info(`Added ${count} ${provider} tasks to queue. Total: ${this.queue.length}`);

        if (!this.isProcessing) {
            this.startProcessing();
        }
    }

    /**
     * Start processing queue
     */
    async startProcessing() {
        if (this.isProcessing) {
            logger.warning('Queue is already processing');
            return;
        }

        this.isProcessing = true;
        logger.success('Queue processing started');

        while (this.queue.length > 0 || this.activeWorkers > 0) {
            // Spawn workers up to max limit
            while (this.activeWorkers < this.maxWorkers && this.queue.length > 0) {
                const task = this.queue.shift();
                this.spawnWorker(task);
            }

            // Wait a bit before checking again
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        this.isProcessing = false;
        logger.success('Queue processing completed');
        this.printStats();
    }

    /**
     * Spawn worker for a task
     */
    async spawnWorker(task) {
        const { id: taskId, provider } = task;
        this.activeWorkers++;
        this.stats.inProgress++;

        logger.info(`Worker spawned for ${provider} task ${taskId}. Active workers: ${this.activeWorkers}`);

        try {
            // Update task status
            await this.db.run(
                'UPDATE registration_queue SET status = ?, started_at = CURRENT_TIMESTAMP WHERE id = ?',
                ['processing', taskId]
            );

            // Get the appropriate registrar
            const registrar = this.registrars[provider] || this.registrars['gmail'];

            // Perform registration
            const result = await registrar.registerAccount();

            if (result.success) {
                // Success
                await this.db.run(
                    'UPDATE registration_queue SET status = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?',
                    ['completed', taskId]
                );

                this.stats.completed++;
                this.stats.inProgress--;

                logger.success(`Task ${taskId} completed successfully`);
            } else {
                // Failed
                await this.db.run(
                    'UPDATE registration_queue SET status = ?, error = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?',
                    ['failed', result.error, taskId]
                );

                this.stats.failed++;
                this.stats.inProgress--;

                logger.error(`Task ${taskId} failed: ${result.error}`);

                // Retry logic
                const retryAttempts = this.config.get('app.retryAttempts') || 3;

                // Simplified retry: just add back to queue if total fails < limit (or track per task in DB for better accuracy)
                if (this.stats.failed < retryAttempts * this.stats.total) {
                    logger.info(`Retrying ${provider} task...`);
                    const newTaskId = require('uuid').v4();
                    await this.db.run(
                        'INSERT INTO registration_queue (id, status, provider) VALUES (?, ?, ?)',
                        [newTaskId, 'pending', provider]
                    );
                    this.queue.push({ id: newTaskId, provider });
                }
            }
        } catch (error) {
            logger.error(`Worker error for task ${taskId}`, error);

            await this.db.run(
                'UPDATE registration_queue SET status = ?, error = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?',
                ['failed', error.message, taskId]
            );

            this.stats.failed++;
            this.stats.inProgress--;
        } finally {
            this.activeWorkers--;
        }
    }

    /**
     * Stop processing
     */
    stopProcessing() {
        this.isProcessing = false;
        this.queue = [];
        logger.warning('Queue processing stopped');
    }

    /**
     * Get queue status
     */
    getStatus() {
        return {
            isProcessing: this.isProcessing,
            activeWorkers: this.activeWorkers,
            queueLength: this.queue.length,
            stats: this.stats
        };
    }

    /**
     * Print statistics
     */
    printStats() {
        logger.info('=== Queue Statistics ===');
        logger.info(`Total: ${this.stats.total}`);
        logger.info(`Completed: ${this.stats.completed}`);
        logger.info(`Failed: ${this.stats.failed}`);
        logger.info(`Success Rate: ${((this.stats.completed / this.stats.total) * 100).toFixed(2)}%`);
    }

    /**
     * Clear completed tasks
     */
    async clearCompleted() {
        await this.db.run('DELETE FROM registration_queue WHERE status = ?', ['completed']);
        logger.success('Cleared completed tasks');
    }

    /**
     * Get estimated time for completion
     */
    getEstimatedTime() {
        if (this.queue.length === 0) {
            return 0;
        }

        // Average 2-3 minutes per account
        const avgTimePerAccount = 150; // seconds
        const accountsRemaining = this.queue.length + this.stats.inProgress;
        const parallelFactor = this.maxWorkers;

        const estimatedSeconds = (accountsRemaining * avgTimePerAccount) / parallelFactor;
        return Math.ceil(estimatedSeconds / 60); // Return in minutes
    }
}

module.exports = TaskQueue;
