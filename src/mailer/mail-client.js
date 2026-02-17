const nodemailer = require('nodemailer');
const Imap = require('imap');
const { simpleParser } = require('mailparser');
const logger = require('../utils/logger');

/**
 * Mail Client
 * Handles SMTP sending and IMAP reading for all providers
 */
class MailClient {
    constructor(account, proxy = null) {
        this.account = account;
        this.proxy = proxy;
        this.config = this.getProviderConfig(account.provider);
    }

    /**
     * Get SMTP/IMAP settings for provider
     */
    getProviderConfig(provider) {
        const configs = {
            gmail: {
                smtp: { host: 'smtp.gmail.com', port: 465, secure: true },
                imap: { host: 'imap.gmail.com', port: 993, tls: true }
            },
            yahoo: {
                smtp: { host: 'smtp.mail.yahoo.com', port: 465, secure: true },
                imap: { host: 'imap.mail.yahoo.com', port: 993, tls: true }
            },
            outlook: {
                smtp: { host: 'smtp-mail.outlook.com', port: 587, secure: false },
                imap: { host: 'outlook.office365.com', port: 993, tls: true }
            }
        };
        return configs[provider] || configs.gmail;
    }

    /**
     * Send email via SMTP
     */
    async sendEmail(to, subject, body) {
        try {
            logger.info(`Sending email from ${this.account.email} to ${to}...`);

            const transporter = nodemailer.createTransport({
                ...this.config.smtp,
                auth: {
                    user: this.account.email,
                    pass: this.account.password
                }
                // Proxy can be added here using proxy-agent if needed
            });

            const info = await transporter.sendMail({
                from: `"${this.account.first_name} ${this.account.last_name}" <${this.account.email}>`,
                to: to,
                subject: subject,
                text: body,
                html: `<p>${body.replace(/\n/g, '<br>')}</p>`
            });

            logger.success(`Email sent: ${info.messageId}`);
            return { success: true, messageId: info.messageId };
        } catch (error) {
            logger.error(`Failed to send email from ${this.account.email}`, error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Read emails via IMAP
     */
    async getInbox(limit = 10) {
        return new Promise((resolve, reject) => {
            const imap = new Imap({
                user: this.account.email,
                password: this.account.password,
                ...this.config.imap,
                tlsOptions: { rejectUnauthorized: false }
            });

            const emails = [];

            imap.once('ready', () => {
                imap.openBox('INBOX', true, (err, box) => {
                    if (err) return reject(err);

                    const f = imap.seq.fetch(`${Math.max(1, box.messages.total - limit + 1)}:*`, {
                        bodies: '',
                        struct: true
                    });

                    f.on('message', (msg, seqno) => {
                        msg.on('body', (stream, info) => {
                            simpleParser(stream, async (err, parsed) => {
                                emails.push({
                                    subject: parsed.subject,
                                    from: parsed.from.text,
                                    date: parsed.date,
                                    body: parsed.text,
                                    html: parsed.html
                                });
                            });
                        });
                    });

                    f.once('error', (err) => reject(err));
                    f.once('end', () => {
                        imap.end();
                    });
                });
            });

            imap.once('error', (err) => reject(err));
            imap.once('end', () => resolve(emails));
            imap.connect();
        });
    }
}

module.exports = MailClient;
