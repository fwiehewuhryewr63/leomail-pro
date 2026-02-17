const Groq = require('groq-sdk');
const logger = require('../utils/logger');

/**
 * AI Email Generator
 * Uses Groq API (free) to generate realistic emails
 */

class AIEmailGenerator {
    constructor(config) {
        this.config = config;
        this.provider = config.get('ai.provider') || 'groq';
        this.apiKey = config.get('ai.apiKey') || process.env.GROQ_API_KEY;

        if (this.provider === 'groq' && this.apiKey) {
            this.groq = new Groq({ apiKey: this.apiKey });
        }

        this.emailTemplates = {
            personal: [
                'catching up with an old friend',
                'planning a weekend trip',
                'discussing a hobby or interest',
                'sharing life updates',
                'asking for advice'
            ],
            business: [
                'following up on a meeting',
                'requesting information',
                'scheduling a call',
                'project update',
                'introduction email'
            ],
            casual: [
                'sharing an interesting article',
                'recommending a movie or book',
                'discussing current events',
                'planning a get-together',
                'sharing a funny story'
            ]
        };
    }

    /**
     * Generate email using AI
     */
    async generateEmail(type = 'personal', context = null) {
        if (!this.apiKey) {
            // Fallback to template-based generation
            return this.generateTemplateEmail(type);
        }

        try {
            const prompt = this.buildPrompt(type, context);

            if (this.provider === 'groq') {
                return await this.generateWithGroq(prompt);
            }

            // Fallback
            return this.generateTemplateEmail(type);
        } catch (error) {
            logger.error('AI email generation failed, using template', error);
            return this.generateTemplateEmail(type);
        }
    }

    /**
     * Build prompt for AI
     */
    buildPrompt(type, context) {
        const templates = this.emailTemplates[type] || this.emailTemplates.personal;
        const topic = templates[Math.floor(Math.random() * templates.length)];

        let prompt = `Generate a realistic, natural-sounding email about ${topic}. `;

        if (context && context.isReply) {
            prompt += `This is a reply to the following email:\n\n"${context.previousEmail}"\n\n`;
            prompt += `Write a thoughtful, relevant reply. `;
        }

        prompt += `The email should be:
- Natural and conversational
- 2-4 sentences long
- Appropriate for ${type} communication
- Without formal greetings or signatures (just the body)
- Realistic and human-like

Only return the email body, nothing else.`;

        return prompt;
    }

    /**
     * Generate with Groq API
     */
    async generateWithGroq(prompt) {
        const completion = await this.groq.chat.completions.create({
            messages: [
                {
                    role: 'system',
                    content: 'You are a helpful assistant that generates realistic, natural emails. Keep them short and conversational.'
                },
                {
                    role: 'user',
                    content: prompt
                }
            ],
            model: this.config.get('ai.model') || 'mixtral-8x7b-32768',
            temperature: this.config.get('ai.temperature') || 0.7,
            max_tokens: 200
        });

        const body = completion.choices[0]?.message?.content || '';
        const subject = this.generateSubject(body);

        return { subject, body };
    }

    /**
     * Generate subject line from email body
     */
    generateSubject(body) {
        const subjects = [
            'Quick question',
            'Following up',
            'Thought you might like this',
            'Hey!',
            'Quick update',
            'Checking in',
            'Wanted to share',
            'Hope you\'re well',
            'Quick chat?',
            'This reminded me of you'
        ];

        // Try to extract a subject from the first sentence
        const firstSentence = body.split('.')[0];
        if (firstSentence.length > 10 && firstSentence.length < 60) {
            return firstSentence.trim();
        }

        return subjects[Math.floor(Math.random() * subjects.length)];
    }

    /**
     * Template-based email generation (fallback)
     */
    generateTemplateEmail(type) {
        const templates = {
            personal: [
                {
                    subject: 'Hey! How have you been?',
                    body: 'I was thinking about you the other day and wanted to catch up. How have things been going? Would love to hear what you\'ve been up to lately.'
                },
                {
                    subject: 'Quick question',
                    body: 'Hope you\'re doing well! I had a quick question about something and thought you might know. Do you have a few minutes to chat sometime this week?'
                },
                {
                    subject: 'This made me think of you',
                    body: 'I came across something interesting today and immediately thought of you. I think you\'d really enjoy it. Let me know what you think!'
                }
            ],
            business: [
                {
                    subject: 'Following up on our discussion',
                    body: 'Thanks for taking the time to chat earlier. I wanted to follow up on a few points we discussed. Let me know if you need any additional information.'
                },
                {
                    subject: 'Quick update',
                    body: 'Just wanted to give you a quick update on the project. Everything is moving along smoothly. I\'ll have more details for you by end of week.'
                }
            ],
            casual: [
                {
                    subject: 'You have to see this',
                    body: 'I just found something really cool and had to share it with you. I think you\'ll find it interesting. Check it out when you get a chance!'
                },
                {
                    subject: 'Random thought',
                    body: 'Had a random thought today and wanted to get your opinion on it. What do you think about this? Would love to hear your perspective.'
                }
            ]
        };

        const typeTemplates = templates[type] || templates.personal;
        return typeTemplates[Math.floor(Math.random() * typeTemplates.length)];
    }

    /**
     * Generate reply to an email
     */
    async generateReply(originalEmail) {
        return await this.generateEmail('personal', {
            isReply: true,
            previousEmail: originalEmail.body
        });
    }

    /**
     * Generate batch of emails
     */
    async generateBatch(count, type = 'personal') {
        const emails = [];

        for (let i = 0; i < count; i++) {
            const email = await this.generateEmail(type);
            emails.push(email);

            // Small delay to avoid rate limiting
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        return emails;
    }
}

module.exports = AIEmailGenerator;
