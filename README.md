# Leomail v2.2 — Email God Engine

## Quick Start (Windows Server 2022)

### Option 1: Auto Install
1. Download/copy the `Leomail` folder to your server
2. Right-click `INSTALL.bat` → **Run as Administrator**
3. Wait for installation to complete
4. Run `START.bat`
5. Open `http://localhost:8000` in your browser

### Option 2: Manual Install
```
pip install fastapi uvicorn sqlalchemy loguru pyyaml requests beautifulsoup4 psutil aiohttp pydantic
cd frontend && npm install && npm run build && cd ..
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## First Launch
1. Go to **Settings** → **API Keys**
2. Add your API keys (AIML, SimSMS, CapSolver)
3. Language: switch RU/EN in sidebar or Settings → General

## Requirements
- Python 3.10+
- Node.js 18+
- Windows Server 2022 / Windows 10+
