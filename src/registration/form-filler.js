const { faker } = require('@faker-js/faker');
const logger = require('../utils/logger');

/**
 * Form Filler
 * Generates realistic user data and fills registration forms
 */

class FormFiller {
    constructor() {
        this.usedUsernames = new Set();
    }

    /**
     * Generate complete user profile
     */
    generateUserProfile() {
        const firstName = faker.person.firstName();
        const lastName = faker.person.lastName();
        const birthDate = this.generateBirthDate();

        const profile = {
            firstName,
            lastName,
            username: this.generateUsername(firstName, lastName),
            password: this.generatePassword(),
            birthDate: {
                day: birthDate.day,
                month: birthDate.month,
                year: birthDate.year
            },
            gender: Math.random() > 0.5 ? 'male' : 'female',
            recoveryEmail: null // Will be generated separately
        };

        logger.info('Generated user profile', { username: profile.username });
        return profile;
    }

    /**
     * Generate unique username
     */
    generateUsername(firstName, lastName) {
        const baseUsername = `${firstName.toLowerCase()}${lastName.toLowerCase()}`;
        const variations = [
            baseUsername,
            `${baseUsername}${Math.floor(Math.random() * 1000)}`,
            `${firstName.toLowerCase()}.${lastName.toLowerCase()}`,
            `${firstName.toLowerCase()}${lastName.charAt(0).toLowerCase()}${Math.floor(Math.random() * 100)}`,
            `${firstName.toLowerCase()}_${lastName.toLowerCase()}`,
            `${firstName.toLowerCase()}${Math.floor(Math.random() * 10000)}`
        ];

        // Pick a variation that hasn't been used
        for (const variation of variations) {
            if (!this.usedUsernames.has(variation)) {
                this.usedUsernames.add(variation);
                return variation;
            }
        }

        // Fallback: add random number
        const fallback = `${baseUsername}${Math.floor(Math.random() * 100000)}`;
        this.usedUsernames.add(fallback);
        return fallback;
    }

    /**
     * Generate secure password
     */
    generatePassword() {
        const length = 12 + Math.floor(Math.random() * 4); // 12-15 chars
        const lowercase = 'abcdefghijklmnopqrstuvwxyz';
        const uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        const numbers = '0123456789';
        const special = '!@#$%^&*';

        const all = lowercase + uppercase + numbers + special;

        let password = '';
        // Ensure at least one of each type
        password += lowercase[Math.floor(Math.random() * lowercase.length)];
        password += uppercase[Math.floor(Math.random() * uppercase.length)];
        password += numbers[Math.floor(Math.random() * numbers.length)];
        password += special[Math.floor(Math.random() * special.length)];

        // Fill the rest randomly
        for (let i = password.length; i < length; i++) {
            password += all[Math.floor(Math.random() * all.length)];
        }

        // Shuffle the password
        return password.split('').sort(() => Math.random() - 0.5).join('');
    }

    /**
     * Generate realistic birth date (18-45 years old)
     */
    generateBirthDate() {
        const minAge = 18;
        const maxAge = 45;
        const age = minAge + Math.floor(Math.random() * (maxAge - minAge + 1));

        const year = new Date().getFullYear() - age;
        const month = 1 + Math.floor(Math.random() * 12);
        const day = 1 + Math.floor(Math.random() * 28); // Safe for all months

        return { day, month, year };
    }

    /**
     * Type text with human-like delays
     */
    async typeHuman(page, selector, text) {
        await page.waitForSelector(selector, { timeout: 10000 });
        await page.click(selector);

        for (const char of text) {
            await page.keyboard.type(char);
            // Random delay between 50-150ms per character
            await this.randomDelay(50, 150);
        }
    }

    /**
     * Click with human-like delay
     */
    async clickHuman(page, selector) {
        await page.waitForSelector(selector, { timeout: 10000 });

        // Move mouse to element (simulate human behavior)
        const element = await page.$(selector);
        const box = await element.boundingBox();

        if (box) {
            const x = box.x + box.width / 2 + (Math.random() * 10 - 5);
            const y = box.y + box.height / 2 + (Math.random() * 10 - 5);
            await page.mouse.move(x, y, { steps: 10 });
        }

        await this.randomDelay(100, 300);
        await page.click(selector);
    }

    /**
     * Select dropdown option
     */
    async selectDropdown(page, selector, value) {
        await page.waitForSelector(selector, { timeout: 10000 });
        await page.select(selector, value.toString());
        await this.randomDelay(200, 500);
    }

    /**
     * Random delay
     */
    randomDelay(min, max) {
        const delay = Math.floor(Math.random() * (max - min + 1)) + min;
        return new Promise(resolve => setTimeout(resolve, delay));
    }

    /**
     * Scroll page naturally
     */
    async scrollNaturally(page) {
        await page.evaluate(() => {
            window.scrollBy({
                top: 100 + Math.random() * 200,
                behavior: 'smooth'
            });
        });
        await this.randomDelay(500, 1000);
    }

    /**
     * Random mouse movements (simulate human behavior)
     */
    async randomMouseMovements(page) {
        const movements = 2 + Math.floor(Math.random() * 3);

        for (let i = 0; i < movements; i++) {
            const x = Math.floor(Math.random() * 800);
            const y = Math.floor(Math.random() * 600);
            await page.mouse.move(x, y, { steps: 10 });
            await this.randomDelay(200, 500);
        }
    }
}

module.exports = FormFiller;
