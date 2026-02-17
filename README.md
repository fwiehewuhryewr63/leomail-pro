# 🦁 LEOmail

> **Advanced Multi-Provider Email Registration & Management Platform**  
> Anti-detect technology • AI-powered warmup • Built-in SMTP/IMAP client

![LEOmail](https://img.shields.io/badge/LEOmail-Ready-orange?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Development-10b981?style=for-the-badge)

---

## 🎯 Overview

LEOmail is a professional-grade platform designed for automated email account registration, intelligent warmup, and direct mailing across multiple providers. It surpasses standard antidetect browsers by integrating a full-featured email lifecycle management system.

### Key Features

- 📱 **Multi-Engine Emulation**: Sophisticated mobile (Android/iOS) and desktop (Windows/Mac) fingerprinting.
- 🚀 **Multi-Provider Support**: Integrated registration for Gmail, Yahoo, Outlook, and more.
- 📬 **Built-in Mailer**: Native SMTP/IMAP support for direct sending and reading without switching apps.
- 🤖 **AI Content Engine**: Human-like email generation powered by Groq (free) for authentic warmup.
- 🌐 **Proxy Intelligence**: Built-in support for mobile and residential proxies with automated rotation.
- 📊 **Server-Optimized**: High-performance headless mode designed for Windows Server 2022 deployment.

---

## 🚀 Quick Start (Server)

```bash
# Clone the repository
git clone [your-repo-link]
cd leomail

# Install dependencies
npm install

# Start the application
npm start
```

---

## 🛠 Features Breakdown

### 1. Registration & Anti-Detect
- Custom Chromium/Firefox kernel-level spoofing.
- Automated registration flows for major providers.
- Integrated SMS and Captcha failover logic.

### 2. Warmup & AI
- Progressive 3-7 day activity plans.
- Realistic AI-generated conversations.
- Natural interaction simulation (scroll, read, reply).

### 3. Integrated Mailing
- Send emails directly via SMTP.
- Receive and manage inboxes via IMAP.
- Centralized dashboard for all account activity.

---

## 📁 Repository Structure

```
leomail/
├── src/
│   ├── database/         # SQLite persistence
│   ├── emulation/        # Fingerprinting & Anti-detect
│   ├── registration/     # Multi-provider registration logic
│   ├── mailer/           # SMTP/IMAP client
│   ├── warmup/           # AI activity scheduling
│   ├── ui/               # Premium Electron interface
│   └── main.js           # Electron main process
└── README.md
```

---

## ⚠️ Disclaimer

This software is for educational and research purposes. Use responsibly and in accordance with the Terms of Service of the respective email providers.

---

**LEOmail - The Future of Email Management**
